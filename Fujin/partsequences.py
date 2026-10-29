"""A part tab's sprite sequences: the flipbooks (FF8_EN.exe data) the part draws its sprites from.

The lab recording says which sequence and frame each sprite of a tick is (the recorder's Q lines:
it hooks InitEffectSequenceFromData and its copies), the exe holds the sequences
(FF8GameData.psxgpu.spritesequence). Each sequence is a row of its frames, drawn from the
recording's video memory: the frames the part draws over the effect bright, the others dimmed,
the ones drawn at the preview's tick framed. A click on a frame lists its pieces (where each
takes its texels, where it goes in the sprite, its palette, page, intensity, blending, rotation,
scale) and outlines them on the Images tab. A part's Frames fields mark the frames it plays (the
others crossed); its Sequence fields choose another sequence from the exe's (SequenceBrowser,
which also browses them all).
"""
import math

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from FF8GameData.psxgpu.spritesequence import exe_sequences, piece_rect
from FF8GameData.psxgpu.texuse import DEPTH_NAMES, texels_rgba

THUMB = 56                          # a frame's picture (pixels)
NOW = QColor(40, 220, 255)          # a frame drawn at the preview's tick
BEYOND = QColor(230, 60, 60)        # a frame past the part's Frames value: never played
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
        self.beyond = ""            # the Frames field this frame lies past (never played), if any
        self.setFixedSize(THUMB + 4, THUMB + 18)
        self.set_beyond("")

    def set_beyond(self, label):
        self.beyond = label
        self.setToolTip(f"Frame {self.index}" + (f" - past {label}: never played" if label else
                                                  "" if self.drawn else " - this part never draws it here"))
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.drawn:
            painter.setOpacity(0.35)
        painter.drawImage(2, 2, self.image)
        painter.setOpacity(1)
        if self.beyond:
            painter.setPen(QPen(BEYOND, 2))
            painter.drawLine(4, 4, THUMB, THUMB)
            painter.drawLine(THUMB, 4, 4, THUMB)
        if self.now or self.picked:
            painter.setPen(QPen(PICKED if self.picked else NOW, 2))
            painter.drawRect(1, 1, THUMB + 2, THUMB + 2)
        painter.setPen(QColor(NOW) if self.now else self.palette().text().color())
        painter.drawText(QRectF(0, THUMB + 4, THUMB + 4, 14), Qt.AlignmentFlag.AlignCenter, str(self.index))


class PartSequences(QWidget):
    """The sprite sequences of these effect parts in the runner's lab recording, following a tick;
    picked(pieces): [(tpage, clut, (u0, v0, u1, v1))] of the frame clicked."""
    picked = pyqtSignal(object)

    def __init__(self, runner, part_ids, part_names=None):
        super().__init__()
        self.runner, self.part_ids, self.part_names = runner, part_ids, part_names or {}
        self.rows, self.tick, self.choice, self.limits = [], 0, None, {}
        self.note = QLabel()
        self.note.setWordWrap(True)
        browse = QPushButton("Browse all sequences…")
        browse.setToolTip("Every sprite sequence of FF8_EN.exe, frame by frame")
        browse.clicked.connect(lambda: SequenceBrowser(self.runner, names=used_by(runner.recording, self.part_names),
                                                       parent=self).exec())
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
        top = QHBoxLayout()
        top.addWidget(self.note, 1)
        top.addWidget(browse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
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

    def set_limits(self, limits):
        """{sequence address: (Frames field label, last frame played)}: the frames past it crossed."""
        self.limits = dict(limits)
        for sequence, frames, thumbs, title, text in self.rows:
            label, last = self.limits.get(sequence.address, ("", None))
            for thumb in thumbs:
                thumb.set_beyond(label if last is not None and thumb.index > last else "")
            title.setText(text + (f" - plays frames 0-{min(last, len(sequence.frames) - 1)} ({label})"
                                  if last is not None else ""))

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
            text = (f"Sequence 0x{address:X} (exe offset 0x{address - 0x400000:X}) - "
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
            self.rows.append((sequence, frames, thumbs, title, text))
        self.list.addStretch(1)
        self.set_limits(self.limits)
        self.set_tick(self.tick)

    def set_tick(self, tick):
        self.tick = tick
        for _sequence, frames, thumbs, _title, _text in self.rows:
            for thumb in thumbs:
                now = tick in frames.get(thumb.index, ())
                if now != thumb.now:
                    thumb.now = now
                    thumb.update()

    def pick(self, address, index):
        """List frame `index` of a sequence and outline its pieces on the Images tab."""
        self.choice = (address, index)
        for sequence, frames, thumbs, _title, _text in self.rows:
            for thumb in thumbs:
                picked = sequence.address == address and thumb.index == index
                if picked != thumb.picked:
                    thumb.picked = picked
                    thumb.update()
        sequence, frames = next((row[0], row[1]) for row in self.rows if row[0].address == address)
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


def used_by(recording, part_names):
    """{sequence address: "Ring, Sparkles"}: the parts of a recording drawing each sequence."""
    found = {}
    for tick in recording.ticks if recording else ():
        for part, address, _frame in tick.sprites:
            found.setdefault(address, set()).add(part_names.get(part, f"part {part}"))
    return {address: ", ".join(sorted(parts)) for address, parts in found.items()}


def loaded(sequence, vram):
    """Whether every piece of a sequence takes its texels and palette from video memory the effect
    filled (the recording's uploads): its sprites draw their pictures, not leftovers."""
    written = vram.written
    for piece in sequence.pieces():
        page_x, page_y = piece.page_xy
        per_word = {0: 4, 1: 2}.get(piece.depth, 1)
        u0, v0, u1, v1 = piece_rect(piece)
        if not written[page_y + v0:page_y + v1, page_x + u0 // per_word:page_x + -(-u1 // per_word)].all():
            return False
        if piece.depth < 2:
            clut_x, clut_y = (piece.clut & 0x3F) * 16, (piece.clut >> 6) & 0x1FF
            if not written[clut_y, clut_x:clut_x + (16 if piece.depth == 0 else 256)].all():
                return False
    return True


class SequenceBrowser(QDialog):
    """Every sprite sequence of the exe: a list (address, frames, where its pictures lie, which this
    effect loads, which its parts draw) and the chosen one's frames drawn from the recording's video
    memory. With choose=True, Use this sequence returns it (self.address)."""

    def __init__(self, runner, current=None, choose=False, names=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sprite sequences of FF8_EN.exe")
        self.resize(1000, 600)
        self.runner, self.address, self.names = runner, current, names or {}
        self.sequences = exe_sequences(runner.exe_path())
        recording = runner.recording
        self.vram = recording.vram_at(len(recording.ticks) - 1) if recording and recording.ticks else None
        self.loaded = {a: loaded(s, self.vram) for a, s in self.sequences.items()} if self.vram is not None else {}
        self.search = QLineEdit()
        self.search.setPlaceholderText("Address (hex), e.g. 1642238")
        self.search.textChanged.connect(self._fill)
        self.only_loaded = QCheckBox("Only sequences drawing from video memory this effect fills")
        self.only_loaded.setToolTip("A sequence takes its pictures from a fixed place of video memory. Every "
                                    "magic loads its own pictures at the same places, so another effect's "
                                    "sequence draws this effect's pictures, cut its own way (as shown here)")
        self.only_loaded.setChecked(choose and bool(self.loaded))
        self.only_loaded.setEnabled(bool(self.loaded))
        self.only_loaded.toggled.connect(self._fill)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.strip = QHBoxLayout()
        strip_widget = QWidget()
        strip_widget.setLayout(self.strip)
        strip_scroll = QScrollArea()
        strip_scroll.setWidget(strip_widget)
        strip_scroll.setWidgetResizable(True)
        strip_scroll.setFixedHeight(THUMB + 44)
        self.use = QPushButton("Use this sequence")
        self.use.setVisible(choose)
        self.use.clicked.connect(self.accept)
        close = QPushButton("Cancel" if choose else "Close")
        close.clicked.connect(self.reject)
        left = QVBoxLayout()
        left.addWidget(self.search)
        left.addWidget(self.only_loaded)
        left.addWidget(self.list, 1)
        right = QVBoxLayout()
        right.addWidget(self.info)
        right.addWidget(strip_scroll)
        right.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.use)
        buttons.addWidget(close)
        right.addLayout(buttons)
        body = QHBoxLayout(self)
        body.addLayout(left, 2)
        body.addLayout(right, 3)
        self._fill()

    def _text(self, address, sequence):
        pages = sorted({(p.page_xy, p.depth) for p in sequence.pieces()})
        where = ", ".join(f"{x},{y} {DEPTH_NAMES[d]}" for (x, y), d in pages[:2]) + (" ..." if len(pages) > 2 else "")
        marks = [self.names[address]] if address in self.names else []
        if self.loaded.get(address):
            marks.append("video memory filled")
        return (f"0x{address:X} - {len(sequence.frames)} frame{'s' if len(sequence.frames) != 1 else ''} - {where}"
                + (f" [{'; '.join(marks)}]" if marks else ""))

    def _fill(self, *_args):
        wanted = self.search.text().strip().lower().removeprefix("0x")
        self.list.blockSignals(True)
        self.list.clear()
        chosen = None
        for address, sequence in sorted(self.sequences.items()):
            if wanted and wanted not in f"{address:x}":
                continue
            if self.only_loaded.isChecked() and not self.loaded.get(address) and address != self.address:
                continue
            item = QListWidgetItem(self._text(address, sequence))
            item.setData(Qt.ItemDataRole.UserRole, address)
            self.list.addItem(item)
            if address == self.address:
                chosen = item
        self.list.blockSignals(False)
        self.list.setCurrentItem(chosen or self.list.item(0))

    def _show(self, item, _previous=None):
        while self.strip.count():
            old = self.strip.takeAt(0)
            if old.widget():
                old.widget().deleteLater()
        if item is None:
            self.info.setText("No sequence.")
            self.use.setEnabled(False)
            return
        self.address = item.data(Qt.ItemDataRole.UserRole)
        sequence = self.sequences[self.address]
        self.use.setEnabled(True)
        pieces = sum(len(frame.pieces) for frame in sequence.frames)
        palettes = sorted({p.clut_xy for p in sequence.pieces()})
        self.info.setText(f"Sequence 0x{self.address:X} (exe offset 0x{self.address - 0x400000:X}): "
                          f"{len(sequence.frames)} frames, {pieces} pieces, palettes "
                          + ", ".join(f"{x},{y}" for x, y in palettes[:4]) + (" ..." if len(palettes) > 4 else "")
                          + (f". Drawn by this effect: {self.names[self.address]}." if self.address in self.names else
                             ". Not drawn by this effect: shown (as the game would draw it) with this effect's "
                             "video memory" + ("." if self.loaded.get(self.address) else
                                                ", which does not fill all the places it reads.")))
        if self.vram is None:
            return
        for index in range(len(sequence.frames)):
            self.strip.addWidget(FrameThumb(frame_image(self.vram, sequence, index), index, True))
        self.strip.addStretch(1)


class SequenceField(QWidget):
    """A part's Sequence parameter: the address shown, Choose... opens the SequenceBrowser. The
    QSpinBox calls a part tab makes (value, setValue, setRange, valueChanged)."""
    valueChanged = pyqtSignal(int)

    def __init__(self, runner, part_names=None):
        super().__init__()
        self.runner, self._value, self.part_names = runner, 0, part_names or {}
        self.label = QLabel()
        choose = QPushButton("Choose…")
        choose.setToolTip("Pick another sprite sequence of the exe")
        choose.clicked.connect(self.choose)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label, 1)
        layout.addWidget(choose)
        runner.recording_changed.connect(self._show)        # the exe may come after the field
        self._show()

    def value(self):
        return self._value

    def setValue(self, value):
        if value != self._value:
            self._value = value
            self._show()
            if not self.signalsBlocked():
                self.valueChanged.emit(value)

    def setRange(self, _low, _high):
        pass

    def _show(self):
        sequence = exe_sequences(self.runner.exe_path()).get(self._value) if self._value else None
        self.label.setText(f"0x{self._value:X}" + (f" ({len(sequence.frames)} frames)" if sequence else ""))

    def choose(self):
        browser = SequenceBrowser(self.runner, self._value, choose=True,
                                  names=used_by(self.runner.recording, self.part_names), parent=self)
        if browser.exec() == QDialog.DialogCode.Accepted and browser.address is not None:
            self.setValue(browser.address)
