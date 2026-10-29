"""A part tab's images: the pictures an effect part takes its texels from, whole, with the pieces it
takes outlined - like Ifrit's dynamic texture view.

Each image is an upload of the lab recording's VRAM (a TIM's picture, the target's texture) read
with the depth and palette the part's primitives use (FF8GameData.psxgpu.texuse): one card per
image and palette. Outlined: every piece the part takes during the effect; filled: the ones it
draws at the preview's tick; dashed: an image the part's own values name (Cure's overlay: the
image it projects, a pass the PC never draws). Hovering a piece says where it is and the ticks it is drawn.
"""
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolTip, QVBoxLayout, QWidget

from FF8GameData.psxgpu.texuse import DEPTH_NAMES, named_sheet, sheet_rgba, texture_sheets

SHEET_HEIGHT = 200                  # an image's height on screen (pixels), its width keeping the ratio
TAKEN = QColor(255, 200, 40)        # a piece the part takes during the effect
NOW = QColor(40, 220, 255)          # a piece it draws at the preview's tick
NAMED = QColor(255, 80, 220)        # an image the part's values name (dashed)
CHECKER = (QColor(70, 70, 78), QColor(52, 52, 58))
LEGEND = ("<span style='color:#FFC828'>&#9633;</span> taken during the effect &nbsp; "
          "<span style='color:#28DCFF'>&#9632;</span> drawn at this tick")


def _ticks_text(ticks):
    """'3-7, 9' from [3, 4, 5, 6, 7, 9]."""
    runs, start = [], None
    for index, tick in enumerate(ticks):
        if start is None:
            start = tick
        if index + 1 == len(ticks) or ticks[index + 1] != tick + 1:
            runs.append(f"{start}" if start == tick else f"{start}-{tick}")
            start = None
    return ", ".join(runs)


class SheetView(QWidget):
    """One image, its pieces outlined; the pieces of `tick` filled."""

    def __init__(self, sheet, rgba, named=None):
        super().__init__()
        self.sheet, self.tick, self.named = sheet, None, named
        height, width = rgba.shape[:2]
        self.image = QImage(rgba.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
        self.zoom = SHEET_HEIGHT / max(1, height)
        self.setFixedSize(max(1, round(width * self.zoom)), SHEET_HEIGHT)
        self.setMouseTracking(True)
        self.pieces = sorted(sheet.all_pieces())

    def set_tick(self, tick):
        self.tick = tick
        self.update()

    def _rect(self, piece):
        u0, v0, u1, v1 = piece
        return QRectF(u0 * self.zoom, v0 * self.zoom, (u1 - u0) * self.zoom, (v1 - v0) * self.zoom)

    def paintEvent(self, event):
        painter = QPainter(self)
        cell = 8
        for y in range(0, self.height(), cell):
            for x in range(0, self.width(), cell):
                painter.fillRect(x, y, cell, cell, CHECKER[(x // cell + y // cell) % 2])
        painter.drawImage(QRect(0, 0, self.width(), self.height()), self.image)
        painter.setPen(QPen(TAKEN, 1))
        for piece in self.pieces:
            painter.drawRect(self._rect(piece))
        now = self.sheet.pieces.get(self.tick, ())
        fill = QColor(NOW)
        fill.setAlpha(70)
        painter.setPen(QPen(NOW, 2))
        for piece in now:
            painter.fillRect(self._rect(piece), fill)
            painter.drawRect(self._rect(piece))
        if self.named:
            painter.setPen(QPen(NAMED, 2, Qt.PenStyle.DashLine))
            painter.drawRect(self._rect(self.named))

    def mouseMoveEvent(self, event):
        u, v = event.position().x() / self.zoom, event.position().y() / self.zoom
        under = [p for p in self.pieces if p[0] <= u < p[2] and p[1] <= v < p[3]]
        if not under:
            QToolTip.hideText()
            return
        lines = [f"u {u0}-{u1 - 1}, v {v0}-{v1 - 1} ({u1 - u0} x {v1 - v0}): ticks "
                 f"{_ticks_text(self.sheet.ticks_of((u0, v0, u1, v1)))}" for u0, v0, u1, v1 in under[:8]]
        if len(under) > 8:
            lines.append(f"... {len(under) - 8} more")
        QToolTip.showText(event.globalPosition().toPoint() + QPoint(12, 12), "\n".join(lines), self)


class PartImages(QWidget):
    """The images of these effect parts in the runner's lab recording, following a tick."""

    def __init__(self, runner, part_ids, named=lambda: [], locate=None, label=""):
        """named: [(label, VRAM x, y, CLUT word, width, height)] of images the part's values name
        (Cure's overlay: the image it projects), outlined dashed on the image they lie in; locate:
        (sheet, pieces, label) -> (file name, show) of the TIM an image is loaded from, show() opening
        it in the Textures tab with the pieces outlined (None: not one of the effect's TIMs)."""
        super().__init__()
        self.runner, self.part_ids, self.named, self.locate, self.label = runner, part_ids, named, locate, label
        self.views, self.tick = [], 0
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        cards = QWidget()
        cards.setLayout(self.row)
        self.scroll = QScrollArea()
        self.scroll.setWidget(cards)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(SHEET_HEIGHT + 90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.note)
        layout.addWidget(self.scroll)
        runner.recording_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.views = []
        recording = self.runner.recording
        sheets = texture_sheets(recording, self.part_ids) if recording is not None and recording.ticks else []
        if recording is None:
            self.note.setText("Images: when the recording is ready.")
        elif not sheets:
            self.note.setText("Images: this part draws no textured primitive (plain colours only).")
        else:
            self.note.setText("Images this part takes its pieces from, as they are in video memory: " + LEGEND)
            target = {(s.x, s.y, s.depth, s.clut) for s in texture_sheets(recording, {0})}
            vram = recording.vram_at(len(recording.ticks) - 1)
            for sheet in sheets:
                pieces = len(sheet.all_pieces())
                self._card(sheet, vram, f"{pieces} piece{'s' if pieces != 1 else ''}"
                           + (" - the target's own texture" if (sheet.x, sheet.y, sheet.depth, sheet.clut)
                              in target else ""))
        if recording is not None and recording.ticks:
            vram = recording.vram_at(len(recording.ticks) - 1)
            for label, x, y, clut, width, height in self.named():
                found = named_sheet(recording, x, y, clut, width, height)
                if found:
                    self._card(found[0], vram, f"{label} named by this part's values (dashed)", found[1])
            self.row.addStretch(1)
        self.set_tick(self.tick)

    def _card(self, sheet, vram, what, named=None):
        view = SheetView(sheet, sheet_rgba(vram, sheet), named)
        palette = f", palette {sheet.clut_xy[0]},{sheet.clut_xy[1]}" if sheet.depth < 2 else ""
        title = QLabel(f"VRAM {sheet.x},{sheet.y} - {DEPTH_NAMES[sheet.depth]}{palette} - {what}")
        card = QWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 8, 0)
        card_layout.addWidget(title)
        pieces = sorted(sheet.all_pieces()) or ([named] if named else [])
        found = self.locate(sheet, pieces, self.label) if self.locate else None
        if found:
            name, show = found
            source = QHBoxLayout()
            source.addWidget(QLabel(f"From {name}"))
            button = QPushButton("Show in Textures")
            button.setToolTip(f"Open {name} in the Textures tab, the pieces outlined on its picture")
            button.clicked.connect(lambda _checked, s=show: s())
            source.addWidget(button)
            source.addStretch(1)
            card_layout.addLayout(source)
        card_layout.addWidget(view)
        card_layout.addStretch(1)
        self.row.addWidget(card)
        self.views.append(view)

    def set_tick(self, tick):
        self.tick = tick
        for view in self.views:
            view.set_tick(tick)
