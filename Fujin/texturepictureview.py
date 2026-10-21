"""Fujin's Textures / palettes view for TIM files: the decoded pictures, not their header fields.

Each TIM of the file (a .tim can pack several back to back) is shown as a picture with its
palette row picker, the palette as colour swatches, and its size, depth and VRAM place. The raw
sections and bytes stay in Files / sections.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QScrollArea,
                             QVBoxLayout, QWidget)

from FF8GameData.tim.timfile import decode_tim, texel_alpha

DEPTHS = {0: "4-bit (16 colours)", 1: "8-bit (256 colours)", 2: "16-bit direct colour", 3: "24-bit direct colour"}
MAG_TEXTURE_NOTE = ("A MAG file's textures are raw VRAM blocks: their size and colour depth come from the "
                    "effect's game code, so they are listed in the next tab as data. Choreography's 3D "
                    "playback draws the GF summons' textures.")
ZOOMS = (("Fit", 0), ("1x", 1), ("2x", 2), ("3x", 3), ("4x", 4))
SWATCH = 12


def tim_blocks(manager):
    """[(offset, header section)] of every TIM in a 'PlayStation TIM' document."""
    return [(section.meta.get("tim_offset", 0), section) for section in manager.document.sections
            if section.kind == "header" and "tim_offset" in section.meta]


def _clut_rows(data, offset):
    """The CLUT rows of the TIM at `offset` as lists of 16-bit words ([] for direct colour)."""
    flags = int.from_bytes(data[offset + 4:offset + 8], "little")
    if not flags & 8 or len(data) < offset + 20:
        return []
    width = int.from_bytes(data[offset + 16:offset + 18], "little")
    height = int.from_bytes(data[offset + 18:offset + 20], "little")
    start = offset + 20
    return [[int.from_bytes(data[start + 2 * (row * width + i):start + 2 * (row * width + i) + 2], "little")
             for i in range(width)] for row in range(height) if start + 2 * (row + 1) * width <= len(data)]


def _rgba(word):
    return ((word & 0x1F) * 255 // 31, ((word >> 5) & 0x1F) * 255 // 31, ((word >> 10) & 0x1F) * 255 // 31,
            texel_alpha(word))


def _checker(width, height, size=8):
    """Grey checkerboard under a picture, so transparent texels read as transparent."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    for y in range(0, height, size):
        for x in range(0, width, size):
            painter.fillRect(x, y, size, size, QColor(70, 70, 70) if (x // size + y // size) % 2 else QColor(95, 95, 95))
    painter.end()
    return image


class _TimCard(QGroupBox):
    """One TIM: picture, palette row choice and swatches."""

    def __init__(self, data, offset, title, zoom):
        super().__init__(title)
        self.data, self.offset, self.zoom = data, offset, zoom
        self.rows = _clut_rows(data, offset)
        self.palette = QComboBox()
        self.palette.setToolTip("The palette (CLUT row) the picture is drawn with: the game picks one per "
                                "sprite, so each row can colour the same pixels differently")
        for row in range(len(self.rows)):
            self.palette.addItem(f"Palette {row}", row)
        self.palette.currentIndexChanged.connect(lambda _index: self._draw())
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.swatches = QLabel()
        self.swatches.setToolTip("The selected palette's colours, in index order (16 per line)")
        top = QHBoxLayout()
        if self.rows:
            top.addWidget(QLabel("Palette:"))
            top.addWidget(self.palette)
        top.addWidget(self.info, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        body = QHBoxLayout()
        body.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)
        if self.rows:
            body.addWidget(self.swatches, 0, Qt.AlignmentFlag.AlignTop)
        body.addStretch(1)
        layout.addLayout(body)
        self._draw()

    def set_zoom(self, zoom):
        self.zoom = zoom
        self._draw()

    def _draw(self):
        row = self.palette.currentData() or 0
        tim = decode_tim(self.data, self.offset, row)
        if tim is None:
            self.picture.setText("This TIM cannot be decoded (see its bytes in Files / sections).")
            self.info.setText("")
            return
        rgba = tim.image.convert("RGBA")
        image = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
        depth = int.from_bytes(self.data[self.offset + 4:self.offset + 8], "little") & 7
        self.info.setText(f"{rgba.width} × {rgba.height} texels · {DEPTHS.get(depth, 'unknown depth')} · "
                          f"VRAM x {tim.image_x}, y {tim.image_y}"
                          + (f" · {len(self.rows)} palette rows" if self.rows else ""))
        zoom = self.zoom or max(1, min(4, 720 // max(rgba.width, 1)))
        canvas = _checker(rgba.width * zoom, rgba.height * zoom)
        painter = QPainter(canvas)
        painter.drawImage(canvas.rect(), image)
        painter.end()
        self.picture.setPixmap(QPixmap.fromImage(canvas))
        if self.rows:
            colours = self.rows[min(row, len(self.rows) - 1)]
            per_line = 16
            lines = (len(colours) + per_line - 1) // per_line
            strip = QImage(per_line * SWATCH, max(lines, 1) * SWATCH, QImage.Format.Format_ARGB32)
            strip.fill(QColor(0, 0, 0, 0))
            painter = QPainter(strip)
            for index, word in enumerate(colours):
                red, green, blue, alpha = _rgba(word)
                x, y = (index % per_line) * SWATCH, (index // per_line) * SWATCH
                painter.fillRect(x, y, SWATCH - 1, SWATCH - 1, QColor(red, green, blue, max(alpha, 60)))
            painter.end()
            self.swatches.setPixmap(QPixmap.fromImage(strip))


class TexturePictureView(QWidget):
    """Every TIM of one file, as pictures (rebuilt from the shared bytes on show_manager)."""

    def __init__(self, parent=None):
        super().__init__(parent)
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
        """Draw the pictures of a file (the EffectResourceView panel contract)."""
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        is_tim = manager is not None and manager.document.format == "PlayStation TIM"
        blocks = tim_blocks(manager) if is_tim else []
        data = bytes(manager.data) if manager is not None else b""
        for index, (offset, _section) in enumerate(blocks):
            title = f"TIM {index} (at 0x{offset:X})" if len(blocks) > 1 else "Picture"
            card = _TimCard(data, offset, title, self.zoom.currentData())
            self.content_layout.insertWidget(len(self.cards), card)
            self.cards.append(card)
        if blocks:
            self.note.setText("Edit the palettes and pixels in the next tab (or export a section, edit it "
                              "and replace it); the pictures redraw from the same bytes.")
        elif manager is not None and not is_tim:
            self.note.setText(MAG_TEXTURE_NOTE)
        else:
            self.note.setText("No picture: no file with textures is imported for this effect.")

    def _zoom_changed(self, _index):
        for card in self.cards:
            card.set_zoom(self.zoom.currentData())
