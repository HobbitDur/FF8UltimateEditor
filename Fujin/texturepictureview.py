"""Fujin's Textures view for TIM files: the pictures and their palettes, edited through PNG files.

Each TIM of the file (a .tim can pack several back to back) shows its picture and its palette
(CLUT: one row of colours per line). A 4/8-bit TIM stores palette indices per texel, and the CLUT
holds the colours those indices name, several rows for alternate colourings: the game picks a
row per sprite. A 16-bit TIM stores its colours directly and has no CLUT.

Editing is high level, like Ifrit's texture tab: double-click the picture (or the palette) to
replace it with a PNG of the same size, export both as PNG files, or restore the file's original
TIM. A new picture is mapped onto the existing palette (texels that kept their colour keep their
index). Semi-transparency (the PSX STP bit) travels as PNG alpha: 128 = semi-transparent,
255 = opaque, 0 = fully transparent; a palette colour can also be switched on its own. The card
also sets where the TIM asks to be loaded in video memory. No raw bytes are edited here.
"""
import copy
import os
import struct

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
                             QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                             QWidget)

from FF8GameData.tim.timfile import PalettedTim, decode_tim, encode_clut, encode_indices, word_to_rgba

DEPTHS = {0: "4-bit (16 colours)", 1: "8-bit (256 colours)", 2: "16-bit direct colour", 3: "24-bit direct colour"}
ZOOMS = (("Fit", 0), ("1x", 1), ("2x", 2), ("3x", 3), ("4x", 4))
SWATCH = 12
PER_LINE = 16       # swatches per line of the palette view (a 256-colour row takes 16 lines)
MAG_TEXTURE_NOTE = ("A MAG file's textures are raw VRAM blocks: their size and colour depth come from the "
                    "effect's game code, so they cannot be shown as pictures here (their bytes are in "
                    "this tab's Sections). Choreography's 3D playback draws the GF summons' textures.")
PNG_FILTER = "PNG image (*.png)"
OUTLINE = QColor(255, 200, 40)          # pieces a Choreography part tab points at
USED = QColor(70, 200, 255)             # pieces the effect's recording draws from
VRAM_WIDTH, VRAM_HEIGHT = 1024, 512     # PlayStation video memory, in 16-bit units
STP = 0x8000
STP_HELP = ('Semi-transparent: the colour is blended with what is behind it when the effect draws the '
            'sprite with blending on (otherwise it draws opaque). In PNG files alpha 128 = semi-'
            'transparent, 255 = opaque, 0 = fully transparent. Black always carries the flag: a black '
            'without it would be fully transparent.')


def _stp_from_alpha(word, alpha):
    """A colour's STP bit from its PNG alpha: 1-254 semi-transparent, 255 opaque (black keeps
    the bit: 0x0000 would be transparent), 0 left to the caller (fully transparent)."""
    if word == 0 or alpha == 0:
        return word
    if alpha == 255 and word & 0x7FFF:
        return word & 0x7FFF
    return word | STP


def tim_blocks(manager):
    """[(offset, header section)] of every TIM in a 'PlayStation TIM' document."""
    return [(section.meta.get("tim_offset", 0), section) for section in manager.document.sections
            if section.kind == "header" and "tim_offset" in section.meta]


def _u32(data, offset):
    return int.from_bytes(data[offset:offset + 4], "little")


def _u16(data, offset):
    return int.from_bytes(data[offset:offset + 2], "little")


def sheet_in_tim(texture, x, y, depth, clut_xy, pieces):
    """(palette row, [(u0, v0, u1, v1)] in the TIM's texels) when the TIM loads the VRAM image
    the pieces are taken from - (x, y) in 16-bit units, its depth and palette place, pieces in its
    texels from (x, y) - or None."""
    places = texture.vram()
    picture, palette = places["picture"], places["palette"]
    if picture is None or texture.depth != depth:
        return None
    per_word = {0: 4, 1: 2}.get(depth, 1)
    left, top, width, height = picture
    shift_u, shift_v = (x - left) * per_word, y - top
    rects = [(u0 + shift_u, v0 + shift_v, u1 + shift_u, v1 + shift_v) for u0, v0, u1, v1 in pieces]
    rects = [r for r in rects if r[2] > 0 and r[3] > 0 and r[0] < width * per_word and r[1] < height]
    if not rects:
        return None
    if depth >= 2:
        return 0, rects
    if palette is None or clut_xy[0] != palette[0] or not 0 <= clut_xy[1] - palette[1] < palette[3]:
        return None
    return clut_xy[1] - palette[1], rects


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


def palette_grid(palette):
    """The palette PNG: (rows, colours, 4) laid out as on screen, PER_LINE colours per line, each
    palette row under the previous one (a 256-colour row = 16 lines, a 16-colour row = 1 line)."""
    rows, colours = palette.shape[:2]
    if colours <= PER_LINE:
        return palette
    return palette.reshape(rows * colours // PER_LINE, PER_LINE, 4)


def palette_from_image(rgba, colours):
    """(rows, colours, 4) from a palette PNG: the on-screen grid (PER_LINE wide) or one palette
    row per line (`colours` wide, the layout older exports and other tools use)."""
    height, width = rgba.shape[:2]
    if width == colours:
        return rgba
    lines = colours // PER_LINE
    if width == PER_LINE and colours % PER_LINE == 0 and height % lines == 0:
        return rgba.reshape(height // lines, colours, 4)
    raise ValueError(f"a palette image is {PER_LINE} pixels wide with {lines} lines per palette row "
                     f"(or {colours} wide, one row per line), not {width} × {height}")


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

    def _blocks(self):
        """{"palette": offset of its block or None, "picture": offset of its block}, file offsets."""
        clut = self.offset + 8 if _u32(self.manager.data, self.offset + 4) & 8 else None
        picture = self.offset + 8 + (_u32(self.manager.data, clut) if clut is not None else 0)
        return {"palette": clut, "picture": picture}

    def vram(self):
        """{"picture": (x, y, width, height), "palette": (...) or None}: where the TIM asks to be
        loaded in video memory, in 16-bit units (a 4/8-bit picture is 4/2 texels per unit)."""
        data = self.manager.data
        return {part: None if block is None else tuple(_u16(data, block + 4 + 2 * k) for k in range(4))
                for part, block in self._blocks().items()}

    def set_vram(self, part, x, y):
        block = self._blocks()[part]
        if block is None:
            raise ValueError("this TIM has no palette")
        _x, _y, width, height = self.vram()[part]
        if part == "palette" and x % 16:
            raise ValueError("a palette's X position is a multiple of 16")
        if not (0 <= x and x + width <= VRAM_WIDTH and 0 <= y and y + height <= VRAM_HEIGHT):
            raise ValueError(f"a {width} × {height} block at ({x}, {y}) leaves the {VRAM_WIDTH} × {VRAM_HEIGHT} "
                             "video memory")
        raw = bytearray(self.data)
        at = block - self.offset + 4
        raw[at:at + 4] = struct.pack("<HH", x, y)
        self._write(bytes(raw))

    def semi_transparent(self, row, index):
        return bool(self.palette_rows()[row][index] & STP)

    def set_semi_transparent(self, row, index, on):
        tim = self.paletted()
        word = tim.clut_rows[row][index]
        if word == 0:
            raise ValueError("this colour is fully transparent: give it a colour first (Replace palette…)")
        if not on and not word & 0x7FFF:
            raise ValueError("black is always stored semi-transparent: without the flag it would be fully "
                             "transparent")
        tim.clut_rows[row][index] = word | STP if on else word & 0x7FFF
        self._write(tim.to_bytes())

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
        alpha = rgba[:, :, 3]
        words = np.where((words == 0) | ((alpha > 0) & (alpha < 255)), words | STP, words)  # see _stp_from_alpha
        words = np.where(alpha == 0, 0, words)
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
        rows = encode_clut(rgba_rows, tim.clut_rows[start_row:end])
        tim.clut_rows[start_row:end] = [[_stp_from_alpha(word, int(rgba_rows[r, i, 3])) for i, word in enumerate(row)]
                                        for r, row in enumerate(rows)]
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
    clicked = pyqtSignal(int, int)          # position in the pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint() - self.contentsRect().topLeft()
            self.clicked.emit(point.x(), point.y())
        super().mousePressEvent(event)

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
                                    "framed; a corner mark = semi-transparent. Click a colour to see it, "
                                    "double-click to replace the palette with a PNG (16 colours per line)")
        self.swatches.replace_requested.connect(self.import_palette)
        self.swatches.menu_requested.connect(self._menu)
        self.swatches.clicked.connect(self._pick_colour)
        self.colour = None                  # (row, index) of the clicked swatch
        self.outline = None                 # (label, [(u0, v0, u1, v1)]): pieces a part tab points at
        self.uses = None                    # (rects, palette rows): what the effect draws from it, None: unknown
        self.colour_info = QLabel("Click a colour of the palette.")
        self.colour_info.setWordWrap(True)
        self.semi = QCheckBox("Semi-transparent")
        self.semi.setToolTip(STP_HELP)
        self.semi.setEnabled(False)
        self.semi.toggled.connect(self._semi_toggled)
        self.vram_boxes = {}
        vram_row = QHBoxLayout()
        vram_label = QLabel("Video memory position:")
        vram_label.setToolTip("Where the TIM asks to be loaded in the PlayStation video memory (1024 × 512, "
                              "in 16-bit units; a palette's X is a multiple of 16). The size is the TIM's own.")
        vram_row.addWidget(vram_label)
        for part, name in (("picture", "picture"), ("palette", "palette")):
            if texture.vram()[part] is None:
                continue
            vram_row.addWidget(QLabel(f"{name} X"))
            for axis in (0, 1):
                if axis:
                    vram_row.addWidget(QLabel("Y"))
                box = QSpinBox()
                box.setRange(0, (VRAM_WIDTH if axis == 0 else VRAM_HEIGHT) - 1)
                box.setSingleStep(16 if (part, axis) == ("palette", 0) else 1)
                box.setKeyboardTracking(False)
                box.setToolTip(vram_label.toolTip())
                box.valueChanged.connect(lambda _value, p=part: self._vram_changed(p))
                vram_row.addWidget(box)
                self.vram_boxes[part, axis] = box
        vram_row.addStretch(1)
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
        layout.addLayout(vram_row)
        body = QHBoxLayout()
        body.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)
        if self.rows:
            palette_column = QVBoxLayout()
            legend = QLabel("Palette (CLUT) · corner dot = semi-transparent")
            legend.setToolTip(STP_HELP)
            palette_column.addWidget(legend)
            palette_column.addWidget(self.swatches)
            palette_column.addWidget(self.colour_info)
            palette_column.addWidget(self.semi)
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
            self.picture.setText("This TIM cannot be decoded (see its bytes in this tab's Sections).")
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
        if self.uses is not None:
            rects, rows = self.uses
            # what the effect never draws from, dimmed; what it does, outlined
            used = QRegion()
            for u0, v0, u1, v1 in rects:
                used = used.united(QRegion(u0 * zoom, v0 * zoom, (u1 - u0) * zoom, (v1 - v0) * zoom))
            painter.setClipRegion(QRegion(canvas.rect()).subtracted(used))
            painter.fillRect(canvas.rect(), QColor(0, 0, 0, 170))
            painter.setClipping(False)
            painter.setPen(QPen(USED, 1))
            for u0, v0, u1, v1 in rects:
                painter.drawRect(u0 * zoom, v0 * zoom, (u1 - u0) * zoom - 1, (v1 - v0) * zoom - 1)
            area = self._used_share(rects, width, height)
            palettes = (" with palette rows " + ", ".join(str(r) for r in sorted(rows))) if rows and self.rows else ""
            self.info.setText(self.info.text() + (f" · used by the effect: {len(rects)} pieces, {area:.0f}% of the "
                                                  f"picture{palettes} (the rest dimmed)" if rects else
                                                  " · the effect draws nothing from it (dimmed)"))
        if self.outline:
            label, rects = self.outline
            painter.setPen(QPen(OUTLINE, 2))
            for u0, v0, u1, v1 in rects:
                painter.drawRect(u0 * zoom, v0 * zoom, (u1 - u0) * zoom, (v1 - v0) * zoom)
            self.info.setText(self.info.text() + f" · outlined: the pieces {label} takes")
        painter.end()
        self.picture.setPixmap(QPixmap.fromImage(canvas))
        for (part, axis), box in self.vram_boxes.items():
            with QSignalBlocker(box):
                box.setValue(self.texture.vram()[part][axis])
        palette = self.texture.palette_image()
        if palette is None:
            return
        self._show_colour()
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
                if 0 < alpha < 255:             # semi-transparent: a corner mark
                    painter.fillRect(x + SWATCH - 5, y, 4, 4, QColor(255, 255, 255))
                    painter.fillRect(x + SWATCH - 4, y + 1, 2, 2, QColor(0, 0, 0))
                if self.colour == (row, index):
                    painter.setPen(QColor(0, 0, 0))
                    painter.drawRect(x - 1, y - 1, SWATCH, SWATCH)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawRect(x, y, SWATCH - 2, SWATCH - 2)
            if row == self.row and rows > 1:
                painter.setPen(QColor(61, 123, 217))
                painter.drawRect(0, top - 1, PER_LINE * SWATCH + 1, lines * SWATCH + 1)
        painter.end()
        self.swatches.setPixmap(QPixmap.fromImage(strip))

    @staticmethod
    def _used_share(rects, width, height):
        """How much of the picture the rectangles cover, in %."""
        covered = np.zeros((height, width), bool)
        for u0, v0, u1, v1 in rects:
            covered[max(0, v0):max(0, v1), max(0, u0):max(0, u1)] = True
        return 100 * covered.mean() if covered.size else 0

    def _swatch_layout(self):
        colours = len(self.rows[0])
        lines = (colours + PER_LINE - 1) // PER_LINE
        return colours, lines, lines * SWATCH + 4          # colours per row, lines per row, row pitch

    def _pick_colour(self, x, y):
        if not self.rows:
            return
        colours, lines, pitch = self._swatch_layout()
        row, inside = divmod(y - 1, pitch)
        column, line = (x - 1) // SWATCH, inside // SWATCH
        index = line * PER_LINE + column
        if 0 <= row < len(self.rows) and 0 <= column < PER_LINE and line < lines and index < colours:
            self.colour = (row, index)
            self._draw()

    def _show_colour(self):
        if self.colour is None or self.colour[0] >= len(self.rows):
            self.colour = None
            self.semi.setEnabled(False)
            return
        row, index = self.colour
        word = self.texture.palette_rows()[row][index]
        red, green, blue, _alpha = word_to_rgba(word)
        state = ("fully transparent" if word == 0 else "semi-transparent" if word & STP else "opaque")
        self.colour_info.setText(f"Row {row}, colour {index}: RGB {red}, {green}, {blue} · {state}")
        with QSignalBlocker(self.semi):
            self.semi.setChecked(bool(word & STP))
        self.semi.setEnabled(word != 0 and bool(word & 0x7FFF or not word & STP))

    def _semi_toggled(self, on):
        if self.colour is not None:
            row, index = self.colour
            self._apply(lambda: self.texture.set_semi_transparent(row, index, on))

    def _vram_changed(self, part):
        x, y = self.vram_boxes[part, 0].value(), self.vram_boxes[part, 1].value()
        if (x, y) != self.texture.vram()[part][:2]:
            self._apply(lambda: self.texture.set_vram(part, x, y))

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
            self._draw()                                    # back to the stored values
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
        try:
            rgba = palette_from_image(_png_rgba(path), len(self.rows[0]))
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Fujin", f"Not applied: {error}")
            return False
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
        """Write <stem>.png (the picture in the selected palette row) and <stem>_palette.png (laid
        out like the swatches: 16 colours per line, palette rows one under the other)."""
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
            Image.fromarray(np.ascontiguousarray(palette_grid(palette)), "RGBA").save(written[-1])
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
        self.manager = None
        # uses_provider(manager) -> ({TIM index: (rects, palette rows)}, note) or None: what the
        # effect's recording draws from each TIM of the file (Fujin sets it)
        self.uses_provider = None
        self.used = QCheckBox("Used by the effect")
        self.used.setChecked(True)
        self.used.setToolTip("Dim what the effect never draws from and outline the pieces it does, from its "
                             "recording (an image may be shared by several effects: each uses its own part)")
        self.used.toggled.connect(lambda _on: self.refresh_uses())
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
        top.addWidget(self.used)
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
        self.manager = manager
        for card in self.cards:
            card.hide()                 # gone at once, not when the deferred delete runs
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
        self.refresh_uses()

    def refresh_uses(self):
        """Show what the effect draws from each TIM (uses_provider), or nothing when the box is off."""
        found = self.uses_provider(self.manager) if self.uses_provider and self.used.isChecked() and self.cards else None
        uses, note = found if found else ({}, "")
        self.used.setToolTip(note or self.used.toolTip())
        for index, card in enumerate(self.cards):
            card.uses = uses.get(index, ([], set())) if found else None
            rows = card.uses[1] if card.uses else set()
            if rows and card.row not in rows and min(rows) < card.palette.count():
                card.palette.setCurrentIndex(min(rows))         # drawn with a palette it uses (redraws)
            else:
                card._draw()

    def outline(self, index, row, rects, label):
        """Show TIM `index` with palette `row`, the pieces a part takes outlined (Choreography's
        part tabs); the other TIMs without outline."""
        for number, card in enumerate(self.cards):
            card.outline = (label, rects) if number == index else None
            if number == index and 0 <= row < card.palette.count() and card.palette.currentIndex() != row:
                card.palette.setCurrentIndex(row)           # redraws it
            else:
                card._draw()

    def _zoom_changed(self, _index):
        for card in self.cards:
            card.set_zoom(self.zoom.currentData())
