"""A part tab's sprite sequences: the flipbooks (FF8_EN.exe data) the part draws its sprites from.

The lab recording says which sequence and frame each sprite of a tick is (the recorder's Q lines:
it hooks InitEffectSequenceFromData and its copies), the exe holds the sequences
(FF8GameData.psxgpu.spritesequence). Each sequence is a row of its frames, drawn from the
recording's video memory: the frames the part draws over the effect bright, the others dimmed,
the ones drawn at the preview's tick framed. A click on a frame lists its pieces (where each
takes its texels, where it goes in the sprite, its palette, page, intensity, blending, rotation,
scale) and outlines them on the Images tab.
"""
import math

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from FF8GameData.psxgpu.spritesequence import exe_sequences, piece_rect
from FF8GameData.psxgpu.texuse import DEPTH_NAMES, texels_rgba

THUMB = 56                          # a frame's picture (pixels)
NOW = QColor(40, 220, 255)          # a frame drawn at the preview's tick
PICKED = QColor(255, 150, 30)       # the frame whose pieces are listed
BLENDS = ("B/2 + F/2", "B + F (additive)", "B - F", "B + F/4")
COLUMNS = ("Texels (u, v, size)", "In the sprite (x, y)", "Palette", "Page", "Intensity", "Blending",
           "Angle", "Scale")


def _ticks_text(ticks):
    runs, start = [], None
    for index, tick in enumerate(ticks):
        if start is None:
            start = tick
        if index + 1 == len(ticks) or ticks[index + 1] != tick + 1:
            runs.append(f"{start}" if start == tick else f"{start}-{tick}")
            start = None
    return ", ".join(runs)


def frame_image(vram, sequence, frame, size=THUMB):
    """A QImage of a frame as the emitter lays it out (sprite space, 1 texel per unit, rotated /
    scaled pieces about their centre), fitted in size x size on black, additive pieces added."""
    pieces = sequence.frames[frame].pieces
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    if not pieces:
        return image
    corners = []
    for piece in pieces:
        scale_x, scale_y = (piece.scale_x / 4096, piece.scale_y / 4096) if piece.transformed else (1, 1)
        half_w, half_h = piece.width * abs(scale_x) / 2, piece.height * abs(scale_y) / 2
        reach = math.hypot(half_w, half_h) if piece.transformed and piece.angle else max(half_w, half_h)
        cx, cy = piece.x + piece.width / 2, piece.y + piece.height / 2
        corners += [(cx - reach, cy - reach), (cx + reach, cy + reach)]
    left, top = min(c[0] for c in corners), min(c[1] for c in corners)
    width, height = max(c[0] for c in corners) - left, max(c[1] for c in corners) - top
    zoom = (size - 4) / max(width, height, 1)
    painter = QPainter(image)
    painter.translate((size - width * zoom) / 2, (size - height * zoom) / 2)
    painter.scale(zoom, zoom)
    painter.translate(-left, -top)
    for piece in pieces:
        u0, v0, u1, v1 = piece_rect(piece)
        if u1 <= u0 or v1 <= v0:
            continue
        rgba = texels_rgba(vram, piece.tpage, piece.clut_for(sequence.parameters), u0, v0, u1, v1)
        if not piece.gpu_code & 1:                      # modulated: colour * intensity / 128
            rgba[..., :3] = (rgba[..., :3].astype(int) * piece.intensity // 128).clip(0, 255)
        texels = QImage(rgba.tobytes(), u1 - u0, v1 - v0, (u1 - u0) * 4, QImage.Format.Format_RGBA8888).copy()
        painter.save()
        painter.translate(piece.x + piece.width / 2, piece.y + piece.height / 2)
        if piece.transformed:
            painter.rotate(piece.angle * 360 / 4096)
            painter.scale(piece.scale_x / 4096, piece.scale_y / 4096)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus
                                   if piece.semi_transparent and piece.blend_mode == 1
                                   else QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(QRectF(-piece.width / 2, -piece.height / 2, piece.width, piece.height), texels)
        painter.restore()
    painter.end()
    return image


class FrameThumb(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, image, index, drawn):
        super().__init__()
        self.image, self.index, self.drawn = image, index, drawn
        self.now = self.picked = False
        self.setFixedSize(THUMB + 4, THUMB + 18)
        self.setToolTip(f"Frame {index}" + ("" if drawn else " - this part never draws it here"))

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.drawn:
            painter.setOpacity(0.35)
        painter.drawImage(2, 2, self.image)
        painter.setOpacity(1)
        if self.now or self.picked:
            painter.setPen(QPen(PICKED if self.picked else NOW, 2))
            painter.drawRect(1, 1, THUMB + 2, THUMB + 2)
        painter.setPen(QColor(NOW) if self.now else self.palette().text().color())
        painter.drawText(QRectF(0, THUMB + 4, THUMB + 4, 14), Qt.AlignmentFlag.AlignCenter, str(self.index))


class PartSequences(QWidget):
    """The sprite sequences of these effect parts in the runner's lab recording, following a tick;
    picked(pieces): [(tpage, clut, (u0, v0, u1, v1))] of the frame clicked."""
    picked = pyqtSignal(object)

    def __init__(self, runner, part_ids):
        super().__init__()
        self.runner, self.part_ids = runner, part_ids
        self.rows, self.tick, self.choice = [], 0, None
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.list = QVBoxLayout()
        self.list.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail = QLabel()
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        side = QVBoxLayout()
        side.addWidget(self.detail)
        side.addWidget(self.table, 1)
        body = QHBoxLayout()
        body.addWidget(scroll, 1)
        body.addLayout(side, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.note)
        layout.addLayout(body, 1)
        runner.recording_changed.connect(self.refresh)
        self.refresh()

    def drawn(self):
        """{sequence address: {frame: [ticks]}} of the sprites these parts draw."""
        recording = self.runner.recording
        found = {}
        for index, tick in enumerate(recording.ticks if recording else ()):
            for part, address, frame in tick.sprites:
                if part in self.part_ids:
                    ticks = found.setdefault(address, {}).setdefault(frame, [])
                    if not ticks or ticks[-1] != index:
                        ticks.append(index)
        return found

    def refresh(self):
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows, self.choice = [], None
        self.table.setRowCount(0)
        self.detail.setText("Click a frame to list its pieces.")
        recording = self.runner.recording
        drawn = self.drawn() if recording else {}
        sequences = exe_sequences(self.runner.exe_path()) if drawn else {}
        if recording is None:
            self.note.setText("Sprite sequences: when the recording is ready.")
            return
        if not drawn:
            self.note.setText("Sprite sequences: this part draws no sprite (no InitEffectSequenceFromData call).")
            return
        self.note.setText("The flipbooks (FF8_EN.exe data) this part draws its sprites from: every frame, the ones "
                          "it draws bright, framed in blue the ones drawn at this tick.")
        vram = recording.vram_at(len(recording.ticks) - 1)
        for address, frames in sorted(drawn.items(), key=lambda item: min(min(t) for t in item[1].values())):
            sequence = sequences.get(address)
            title = QLabel()
            if sequence is None:
                title.setText(f"Sequence 0x{address:X}: not a sprite sequence of this exe")
                self.list.addWidget(title)
                continue
            ticks = sorted({t for tick_list in frames.values() for t in tick_list})
            title.setText(f"Sequence 0x{address:X} (exe offset 0x{address - 0x400000:X}) - "
                          f"{len(sequence.frames)} frames, {len(frames)} drawn - ticks {_ticks_text(ticks)}")
            strip = QHBoxLayout()
            strip.setContentsMargins(0, 0, 0, 0)
            thumbs = []
            for index in range(len(sequence.frames)):
                thumb = FrameThumb(frame_image(vram, sequence, index), index, index in frames)
                thumb.clicked.connect(lambda index, a=address: self.pick(a, index))
                strip.addWidget(thumb)
                thumbs.append(thumb)
            strip.addStretch(1)
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 6)
            row_layout.addWidget(title)
            strip_widget = QWidget()
            strip_widget.setLayout(strip)
            strip_scroll = QScrollArea()
            strip_scroll.setWidget(strip_widget)
            strip_scroll.setFrameShape(QFrame.Shape.NoFrame)
            strip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            strip_scroll.setFixedHeight(THUMB + 40)
            row_layout.addWidget(strip_scroll)
            self.list.addWidget(row)
            self.rows.append((sequence, frames, thumbs))
        self.list.addStretch(1)
        self.set_tick(self.tick)

    def set_tick(self, tick):
        self.tick = tick
        for _sequence, frames, thumbs in self.rows:
            for thumb in thumbs:
                now = tick in frames.get(thumb.index, ())
                if now != thumb.now:
                    thumb.now = now
                    thumb.update()

    def pick(self, address, index):
        """List frame `index` of a sequence and outline its pieces on the Images tab."""
        self.choice = (address, index)
        for sequence, frames, thumbs in self.rows:
            for thumb in thumbs:
                picked = sequence.address == address and thumb.index == index
                if picked != thumb.picked:
                    thumb.picked = picked
                    thumb.update()
        sequence, frames = next((s, f) for s, f, _t in self.rows if s.address == address)
        frame = sequence.frames[index]
        ticks = frames.get(index)
        self.detail.setText(f"Sequence 0x{address:X}, frame {index}: {len(frame.pieces)} piece"
                            f"{'s' if len(frame.pieces) != 1 else ''}"
                            + (f", drawn at ticks {_ticks_text(ticks)}" if ticks else ", not drawn by this part")
                            + (" - a draw-mode word first" if frame.draw_mode else ""))
        self.table.setRowCount(len(frame.pieces))
        for row, piece in enumerate(frame.pieces):
            clut = piece.clut_for(sequence.parameters)
            page_x, page_y = piece.page_xy
            values = (f"{piece.u}, {piece.v} - {piece.width} x {piece.height}",
                      f"{piece.x}, {piece.y}",
                      f"{(clut & 0x3F) * 16}, {clut >> 6}" + (f" (row +{sequence.parameters[piece.parameter & 3]})"
                                                              if sequence.parameters[piece.parameter & 3] else ""),
                      f"{page_x}, {page_y} - {DEPTH_NAMES[piece.depth]}",
                      "raw" if piece.gpu_code & 1 else str(piece.intensity),
                      BLENDS[piece.blend_mode] if piece.semi_transparent else "opaque",
                      f"{piece.angle * 360 / 4096:g}°" if piece.transformed else "-",
                      f"{piece.scale_x / 4096:g} x {piece.scale_y / 4096:g}" if piece.transformed else "-")
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.picked.emit([(piece.tpage, piece.clut_for(sequence.parameters), piece_rect(piece))
                          for piece in frame.pieces])
