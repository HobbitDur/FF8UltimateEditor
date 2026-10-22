"""Fujin's Textures view for TIM files: the pictures and their palettes, edited through PNG files.

Each TIM of the file (a .tim can pack several back to back) shows its picture and its palette
(CLUT: one row of colours per line). A 4/8-bit TIM stores palette indices per texel, and the CLUT
holds the colours those indices name, several rows for alternate colourings: the game picks a
row per sprite. A 16-bit TIM stores its colours directly and has no CLUT.

Editing is high level, like Ifrit's texture tab: double-click the picture (or the palette) to
replace it with a PNG of the same size, export both as PNG files, or restore the file's original
TIM. A new picture is mapped onto the existing palette (texels that kept their colour keep their
index); a new palette keeps each colour's transparency bit. The raw sections stay in
Files / sections.
"""
import copy
import os

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from FF8GameData.tim.timfile import PalettedTim, decode_tim, encode_clut, encode_indices, word_to_rgba

DEPTHS = {0: "4-bit (16 colours)", 1: "8-bit (256 colours)", 2: "16-bit direct colour", 3: "24-bit direct colour"}
ZOOMS = (("Fit", 0), ("1x", 1), ("2x", 2), ("3x", 3), ("4x", 4))
SWATCH = 12
PER_LINE = 16       # swatches per line of the palette view (a 256-colour row takes 16 lines)
MAG_TEXTURE_NOTE = ("A MAG file's textures are raw VRAM blocks: their size and colour depth come from the "
                    "effect's game code, so they cannot be shown as pictures here (their bytes are in "
                    "Files / sections). Choreography's 3D playback draws the GF summons' textures.")
PNG_FILTER = "PNG image (*.png)"


def tim_blocks(manager):
    """[(offset, header section)] of every TIM in a 'PlayStation TIM' document."""
    return [(section.meta.get("tim_offset", 0), section) for section in manager.document.sections
            if section.kind == "header" and "tim_offset" in section.meta]


def _u32(data, offset):
    return int.from_bytes(data[offset:offset + 4], "little")


def _u16(data, offset):
    return int.from_bytes(data[offset:offset + 2], "little")


def tim_extent(data, offset):
    """Byte length of the TIM at `offset` (header + CLUT block + image block)."""
    flags = _u32(data, offset + 4)
    position = offset + 8
    if flags & 8:
        position += _u32(data, position)
    return position + _u32(data, position) - offset


def _checker(width, height, size=8):
    """Grey checkerboard under a picture, so transparent texels read as transparent."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    for y in range(0, height, size):
        for x in range(0, width, size):
            painter.fillRect(x, y, size, size, QColor(70, 70, 70) if (x // size + y // size) % 2 else QColor(95, 95, 95))
    painter.end()
    return image


def _qimage(rgba):
    """QImage of an (H, W, 4) uint8 array."""
    rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
    return QImage(rgba.tobytes(), rgba.shape[1], rgba.shape[0], rgba.shape[1] * 4,
                  QImage.Format.Format_RGBA8888).copy()


def _png_rgba(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8)


class TimTexture:
    """One TIM of a document: decode, export and re-encode it in place (same byte size)."""

    def __init__(self, manager, offset):
        self.manager, self.offset = manager, offset

    @property
    def data(self):
        return bytes(self.manager.data[self.offset:self.offset + tim_extent(self.manager.data, self.offset)])

    @property
    def depth(self):
        return _u32(self.manager.data, self.offset + 4) & 7

    def paletted(self):
        return PalettedTim.parse(self.data)

    def palette_rows(self):
        tim = self.paletted()
        return tim.clut_rows if tim else []

    def picture(self, row=0):
        """(H, W, 4) RGBA through palette `row` (None when it cannot be decoded)."""
        tim = decode_tim(bytes(self.manager.data), self.offset, row)
        return None if tim is None else np.array(tim.image.convert("RGBA"), dtype=np.uint8)

    def palette_image(self):
        """(rows, colours, 4) RGBA of the CLUT, one pixel per colour (the exported palette PNG)."""
        rows = self.palette_rows()
        return np.array([[word_to_rgba(word) for word in row] for row in rows], dtype=np.uint8) if rows else None

    # ---------------------------------------------------------------- edits (undoable)
    def _write(self, raw):
        if len(raw) != len(self.data):
            raise ValueError(f"the new TIM would be {len(raw)} bytes instead of {len(self.data)}")
        if raw != self.data:
            self.manager.patch_bytes(self.offset, raw)

    def set_picture(self, rgba, row=0):
        """Replace the texels with an image of the same size, mapped onto palette `row`."""
        rgba = np.asarray(rgba, dtype=np.uint8)
        tim = self.paletted()
        if tim is not None:
            if rgba.shape[:2] != (tim.height, tim.width):
                raise ValueError(f"the picture must be {tim.width} × {tim.height} pixels, "
                                 f"not {rgba.shape[1]} × {rgba.shape[0]}")
            source = copy.copy(tim)
            source.clut_rows = [tim.clut_rows[row]]    # an unchanged texel = same colour in the shown row
            tim.indices = encode_indices(rgba, tim.clut_rows[row], source)
            self._write(tim.to_bytes())
            return
        if self.depth != 2:
            raise ValueError("only 4-bit, 8-bit and 16-bit TIMs can be edited")
        data = bytearray(self.data)
        position = 8                                   # 16-bit: no CLUT block
        width, height = _u16(data, position + 8), _u16(data, position + 10)
        if rgba.shape[:2] != (height, width):
            raise ValueError(f"the picture must be {width} × {height} pixels, not {rgba.shape[1]} × {rgba.shape[0]}")
        five = np.rint(rgba[:, :, :3].astype(np.float64) * 31 / 255).astype(np.uint16)
        words = five[:, :, 0] | (five[:, :, 1] << 5) | (five[:, :, 2] << 10)
        old = np.frombuffer(bytes(data[position + 12:position + 12 + width * height * 2]), "<u2").reshape(height, width)
        words = np.where(words == 0, 0x8000, words | (old & 0x8000))   # black stays opaque, STP kept
        words = np.where(rgba[:, :, 3] == 0, 0, words)
        data[position + 12:position + 12 + width * height * 2] = words.astype("<u2").tobytes()
        self._write(bytes(data))

    def set_palette(self, rgba_rows, start_row=0):
        """Replace palette rows start_row.. with an (rows, colours, 4) image."""
        tim = self.paletted()
        if tim is None:
            raise ValueError("this TIM has no palette (16-bit direct colour)")
        rgba_rows = np.asarray(rgba_rows, dtype=np.uint8)
        colours = len(tim.clut_rows[0])
        if rgba_rows.shape[1] != colours:
            raise ValueError(f"the palette has {colours} colours per row; the image is {rgba_rows.shape[1]} pixels wide")
        if start_row + rgba_rows.shape[0] > len(tim.clut_rows):
            raise ValueError(f"the palette has {len(tim.clut_rows)} rows; the image has {rgba_rows.shape[0]}")
        end = start_row + rgba_rows.shape[0]
        tim.clut_rows[start_row:end] = encode_clut(rgba_rows, tim.clut_rows[start_row:end])
        self._write(tim.to_bytes())

    def original(self):
        return bytes(self.manager.original[self.offset:self.offset + len(self.data)])

    def restore(self):
        self._write(self.original())

    def is_modified(self):
        return self.original() != self.data


class _ImageLabel(QLabel):
    """A picture that opens a PNG on double-click (and a menu on right-click)."""
    replace_requested = pyqtSignal()
    menu_requested = pyqtSignal(object)

    def __init__(self, tooltip):
        super().__init__()
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.replace_requested.emit()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(event.globalPos())


class _TimCard(QGroupBox):
    """One TIM: picture, palette, row choice, PNG import/export and restore."""
    changed = pyqtSignal()

    def __init__(self, texture, title, zoom, registry=None):
        super().__init__(title)
        self.texture, self.zoom, self.registry = texture, zoom, registry
        self.rows = texture.palette_rows()
        self.palette = QComboBox()
        self.palette.setToolTip("The palette row the picture is drawn with (and that an imported picture "
                                "is mapped onto): the game picks one row per sprite")
        for row in range(len(self.rows)):
            self.palette.addItem(f"Palette row {row}", row)
        self.palette.currentIndexChanged.connect(lambda _index: self._draw())
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.picture = _ImageLabel("Double-click to replace the picture with a PNG of the same size; "
                                   "right-click for more")
        self.picture.replace_requested.connect(self.import_picture)
        self.picture.menu_requested.connect(self._menu)
        self.swatches = _ImageLabel("The palette (CLUT): a block per row, one square per colour, the selected row "
                                    "framed. Double-click to replace it with a PNG (colours wide, rows tall)")
        self.swatches.replace_requested.connect(self.import_palette)
        self.swatches.menu_requested.connect(self._menu)
        buttons = QHBoxLayout()
        self.buttons = {}
        for text, tooltip, slot in (
                ("Replace picture…", "Load a PNG of the same size as the picture", self.import_picture),
                ("Replace palette…", "Load a PNG with one pixel per colour and one line per palette row",
                 self.import_palette),
                ("Export PNGs…", "Save the picture (in the selected palette row) and the palette as PNG files",
                 self.export_pngs),
                ("Restore original", "Put this TIM back as it is in the file on disk", self.restore)):
            button = QPushButton(text)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked, s=slot: s())
            buttons.addWidget(button)
            self.buttons[text] = button
        self.buttons["Replace palette…"].setEnabled(bool(self.rows))
        buttons.addStretch(1)
        top = QHBoxLayout()
        if self.rows:
            top.addWidget(self.palette)
        top.addWidget(self.info, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        body = QHBoxLayout()
        body.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)
        if self.rows:
            palette_column = QVBoxLayout()
            palette_column.addWidget(QLabel("Palette (CLUT)"))
            palette_column.addWidget(self.swatches)
            palette_column.addStretch(1)
            body.addLayout(palette_column)
        body.addStretch(1)
        layout.addLayout(body)
        layout.addLayout(buttons)
        self._draw()

    @property
    def row(self):
        return self.palette.currentData() or 0

    def set_zoom(self, zoom):
        self.zoom = zoom
        self._draw()

    def _draw(self):
        rgba = self.texture.picture(self.row)
        if rgba is None:
            self.picture.setText("This TIM cannot be decoded (see its bytes in Files / sections).")
            self.info.setText("")
            return
        height, width = rgba.shape[:2]
        modified = self.texture.is_modified()
        self.info.setText(f"{width} × {height} texels · {DEPTHS.get(self.texture.depth, 'unknown depth')}"
                          + (f" · {len(self.rows)} palette rows" if self.rows else " · no palette")
                          + (" · modified" if modified else ""))
        self.buttons["Restore original"].setEnabled(modified)
        zoom = self.zoom or max(1, min(4, 720 // max(width, 1)))
        canvas = _checker(width * zoom, height * zoom)
        painter = QPainter(canvas)
        painter.drawImage(canvas.rect(), _qimage(rgba))
        painter.end()
        self.picture.setPixmap(QPixmap.fromImage(canvas))
        palette = self.texture.palette_image()
        if palette is None:
            return
        rows, colours = palette.shape[:2]
        lines = (colours + PER_LINE - 1) // PER_LINE          # swatch lines per palette row
        gap = 4
        strip = QImage(PER_LINE * SWATCH + 2, rows * (lines * SWATCH + gap) + 2, QImage.Format.Format_ARGB32)
        strip.fill(QColor(0, 0, 0, 0))
        painter = QPainter(strip)
        for row in range(rows):
            top = 1 + row * (lines * SWATCH + gap)
            for index in range(colours):
                red, green, blue, alpha = (int(v) for v in palette[row, index])
                x, y = 1 + (index % PER_LINE) * SWATCH, top + (index // PER_LINE) * SWATCH
                painter.fillRect(x, y, SWATCH - 1, SWATCH - 1, QColor(red, green, blue, max(alpha, 60)))
            if row == self.row and rows > 1:
                painter.setPen(QColor(61, 123, 217))
                painter.drawRect(0, top - 1, PER_LINE * SWATCH + 1, lines * SWATCH + 1)
        painter.end()
        self.swatches.setPixmap(QPixmap.fromImage(strip))

    def _menu(self, position):
        menu = QMenu(self)
        menu.addAction("Replace picture…", self.import_picture)
        if self.rows:
            menu.addAction("Replace palette…", self.import_palette)
        menu.addAction("Export PNGs…", self.export_pngs)
        restore = menu.addAction("Restore original", self.restore)
        restore.setEnabled(self.texture.is_modified())
        menu.exec(position)

    def _folder(self):
        return self.registry.last_folder("Fujin texture PNG") if self.registry else ""

    def _remember(self, path):
        if self.registry:
            self.registry.remember_folder("Fujin texture PNG", os.path.dirname(path))

    def _apply(self, edit):
        try:
            edit()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Fujin", f"Not applied: {error}")
            return False
        self.rows = self.texture.palette_rows()
        self._draw()
        self.changed.emit()
        return True

    def import_picture(self, path=None):
        if not path:
            path = QFileDialog.getOpenFileName(self, "Replace the picture", self._folder(), PNG_FILTER)[0]
        if not path:
            return False
        self._remember(path)
        return self._apply(lambda: self.texture.set_picture(_png_rgba(path), self.row))

    def import_palette(self, path=None, start_row=None):
        if not self.rows:
            return False
        if not path:
            path = QFileDialog.getOpenFileName(self, "Replace the palette", self._folder(), PNG_FILTER)[0]
        if not path:
            return False
        self._remember(path)
        rgba = _png_rgba(path)
        if start_row is None:
            start_row = 0
            if rgba.shape[0] < len(self.rows):
                choices = [f"Rows {start}-{start + rgba.shape[0] - 1}" if rgba.shape[0] > 1 else f"Row {start}"
                           for start in range(len(self.rows) - rgba.shape[0] + 1)]
                choice, ok = QInputDialog.getItem(
                    self, "Replace palette rows",
                    f"The image has {rgba.shape[0]} of the palette's {len(self.rows)} rows. Replace:",
                    choices, min(self.row, len(choices) - 1), False)
                if not ok:
                    return False
                start_row = choices.index(choice)
        return self._apply(lambda: self.texture.set_palette(rgba, start_row))

    def default_stem(self):
        name = os.path.splitext(os.path.basename(self.texture.manager.file_path))[0]
        return f"{name}_{self.title().split(' ')[0].lower()}"

    def export_pngs(self, folder=None, stem=None):
        """Write <stem>.png (the picture in the selected palette row) and <stem>_palette.png."""
        stem = stem or self.default_stem()
        if not folder:
            path = QFileDialog.getSaveFileName(self, "Export the picture and its palette",
                                               os.path.join(self._folder(), stem + ".png"), PNG_FILTER)[0]
            if not path:
                return []
            folder, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
            self._remember(path)
        written = []
        picture = self.texture.picture(self.row)
        if picture is not None:
            written.append(os.path.join(folder, stem + ".png"))
            Image.fromarray(picture, "RGBA").save(written[-1])
        palette = self.texture.palette_image()
        if palette is not None:
            written.append(os.path.join(folder, stem + "_palette.png"))
            Image.fromarray(np.ascontiguousarray(palette), "RGBA").save(written[-1])
        return written

    def restore(self):
        return self._apply(self.texture.restore)


class TexturePictureView(QWidget):
    """Every TIM of one file as an editable picture (the EffectResourceView panel contract)."""
    data_changed = pyqtSignal()

    def __init__(self, registry=None, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.cards = []
        self.zoom = QComboBox()
        for label, value in ZOOMS:
            self.zoom.addItem(label, value)
        self.zoom.setToolTip("Picture size: Fit draws small textures larger (up to 4x)")
        self.zoom.currentIndexChanged.connect(self._zoom_changed)
        self.note = QLabel()
        self.note.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(QLabel("Zoom:"))
        top.addWidget(self.zoom)
        top.addWidget(self.note, 1)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)

    def set_manager(self, manager):
        """Draw the pictures of a file (EffectResourceView calls it with the selected source)."""
        rows = [card.palette.currentIndex() for card in self.cards]
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        is_tim = manager is not None and manager.document.format == "PlayStation TIM"
        blocks = tim_blocks(manager) if is_tim else []
        for index, (offset, _section) in enumerate(blocks):
            title = f"TIM{index} (at 0x{offset:X})" if len(blocks) > 1 else "TIM"
            card = _TimCard(TimTexture(manager, offset), title, self.zoom.currentData(), self.registry)
            if index < len(rows) and 0 <= rows[index] < card.palette.count():
                card.palette.setCurrentIndex(rows[index])
            card.changed.connect(self.data_changed)
            self.content_layout.insertWidget(len(self.cards), card)
            self.cards.append(card)
        if blocks:
            self.note.setText("Double-click the picture or the palette to replace it with a PNG; Export PNGs… "
                              "saves both. Edits keep the TIM's size; Undo / Redo above, Save in the header.")
        elif manager is not None and not is_tim:
            self.note.setText(MAG_TEXTURE_NOTE)
        else:
            self.note.setText("No picture: no file with textures is imported for this effect.")

    def _zoom_changed(self, _index):
        for card in self.cards:
            card.set_zoom(self.zoom.currentData())
