"""Choreography's Data tab: a new effect's own data (its description's "data", copied from the exe
when it was made: docs/fujin-effect-description.md), each entry edited by kind:

- seq: a sprite sequence (FF8GameData.psxgpu.spritesequence): its palette-row parameters, its
  frames and each frame's pieces (texels, size, palette, page flags, place, angle, scale,
  intensity, GPU code), the frames drawn from the last recording's video memory;
- sound: the world sound id its block holds (what the game plays: the Sound tab's archive entry);
- table: int16 values (Hypnotize's ring points: x, y, z, bone);
- name: a file name (the effect's texture file);
- pointers: a table of other entries (Hypnotize's ring and target layouts), each picked by key;
- layout: a prim-model layout's animation (FF8GameData.psxgpu.primlayout): its length, its objects
  (model, flags) and each object's tracks (position, rotation, scale, colour, fade, vertex-frame
  blend: value / velocity / acceleration) and their keys; its models kept as they are;
- camera: what it holds, read-only (the Camera tab edits it: its effect_NNN.bcam replaces it in the
  game).

Apply writes the entry back (changed(key, entry)): the previews record again, Save writes it in
the program.
"""
import dataclasses
import struct

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from FF8GameData.psxgpu.primlayout import TRACKS, Track, encode_layout, parse_layout
from FF8GameData.psxgpu.spritesequence import SpriteFrame, encode_sequence, parse_sequence

NO_DATA = ("No data of its own: only a new effect made with the exe open has some (Description, New effect). "
           "Fujin's descriptions read the exe's data (exe_data).")
# a piece's columns: (title, field, lowest, highest)
PIECE_COLUMNS = (("Width", "width", 0, 255), ("Height", "height", 0, 255), ("U", "u", 0, 255), ("V", "v", 0, 255),
                 ("CLUT", "clut", 0, 0xFFFF), ("X", "x", -0x8000, 0x7FFF), ("Y", "y", -0x8000, 0x7FFF),
                 ("Angle", "angle", -0x8000, 0x7FFF), ("Flags", "flags", 0, 0xFFFF),
                 ("Scale X", "scale_x", -0x8000, 0x7FFF), ("Scale Y", "scale_y", -0x8000, 0x7FFF),
                 ("Intensity", "intensity", 0, 255), ("GPU code", "gpu_code", 0x2C, 0x2F))


def entries(description):
    return {key: entry for key, entry in (description.get("data") or {}).items() if isinstance(entry, dict)}


def entry_bytes(entry):
    return bytes.fromhex(entry.get("hex", ""))


def name_entry(entry, text):
    data = text.encode("ascii", "replace") + b"\0"
    return dict(entry, hex=(data + bytes(-len(data) % 4)).hex())


class SequenceEditor(QWidget):
    """A sprite sequence's parameters, frames and pieces."""
    edited = pyqtSignal()

    def __init__(self, vram=None):
        super().__init__()
        self.vram = vram or (lambda: None)
        self.sequence = None
        self.parameters = []
        params = QHBoxLayout()
        params.addWidget(QLabel("Palette-row parameters:"))
        for _ in range(4):
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.valueChanged.connect(self._parameters_changed)
            self.parameters.append(spin)
            params.addWidget(spin)
        params.addStretch(1)
        self.frames = QListWidget()
        self.frames.setMaximumWidth(170)
        self.frames.currentRowChanged.connect(self._show_frame)
        self.pieces = QTableWidget(0, len(PIECE_COLUMNS))
        self.pieces.setHorizontalHeaderLabels([column[0] for column in PIECE_COLUMNS])
        self.pieces.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.pieces.itemChanged.connect(self._piece_changed)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c0392b")
        buttons = QHBoxLayout()
        for text, slot in (("Add frame", self.add_frame), ("Remove frame", self.remove_frame),
                           ("Add piece", self.add_piece), ("Remove piece", self.remove_piece)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.strip = QHBoxLayout()
        strip = QWidget()
        strip.setLayout(self.strip)
        scroll = QScrollArea()
        scroll.setWidget(strip)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(84)
        self.strip_note = QLabel()
        body = QSplitter()
        body.addWidget(self.frames)
        body.addWidget(self.pieces)
        body.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(params)
        layout.addWidget(self.strip_note)
        layout.addWidget(scroll)
        layout.addWidget(body, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.error)

    def load(self, data):
        self.sequence = parse_sequence(data, 0, 0)
        self.error.setText("" if self.sequence is not None else "Not a sprite sequence: its bytes are kept as they are.")
        for spin, value in zip(self.parameters, self.sequence.parameters if self.sequence else (0, 0, 0, 0)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._fill_frames(0)

    def data(self):
        return encode_sequence(self.sequence) if self.sequence is not None else None

    def _fill_frames(self, row):
        self.frames.blockSignals(True)
        self.frames.clear()
        for index, frame in enumerate(self.sequence.frames if self.sequence else []):
            self.frames.addItem(f"Frame {index}: {len(frame.pieces)} piece{'s' if len(frame.pieces) != 1 else ''}")
        self.frames.blockSignals(False)
        self.frames.setCurrentRow(min(row, self.frames.count() - 1))
        self._show_frame(self.frames.currentRow())
        self._fill_strip()

    def _fill_strip(self):
        while self.strip.count():
            widget = self.strip.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        vram = self.vram()
        self.strip_note.setText("" if vram is not None or self.sequence is None else
                                "Its frames show once the effect is recorded (Overview or a part tab).")
        if vram is None or self.sequence is None:
            return
        from Fujin.partsequences import FrameThumb, frame_image
        for index in range(len(self.sequence.frames)):
            self.strip.addWidget(FrameThumb(frame_image(vram, self.sequence, index), index, True))
        self.strip.addStretch(1)

    def _show_frame(self, row):
        self.pieces.blockSignals(True)
        frame = self.sequence.frames[row] if self.sequence and 0 <= row < len(self.sequence.frames) else None
        self.pieces.setRowCount(len(frame.pieces) if frame else 0)
        for r, piece in enumerate(frame.pieces if frame else []):
            for c, (_title, name, _low, _high) in enumerate(PIECE_COLUMNS):
                value = getattr(piece, name)
                self.pieces.setItem(r, c, QTableWidgetItem(f"0x{value:X}" if name in ("flags", "clut", "gpu_code") else str(value)))
        self.pieces.blockSignals(False)

    def _parameters_changed(self):
        if self.sequence is not None:
            self.sequence.parameters = tuple(spin.value() for spin in self.parameters)
            self._fill_strip()
            self.edited.emit()

    def _piece_changed(self, item):
        frame = self.sequence.frames[self.frames.currentRow()]
        title, name, low, high = PIECE_COLUMNS[item.column()]
        try:
            value = int(item.text(), 0)
            if not low <= value <= high:
                raise ValueError
        except ValueError:
            self.error.setText(f"{title}: a number from {low} to {high}")
            self._show_frame(self.frames.currentRow())
            return
        self.error.clear()
        frame.pieces[item.row()] = dataclasses.replace(frame.pieces[item.row()], **{name: value})
        self._fill_strip()
        self.edited.emit()

    def set_piece(self, frame, piece, **values):
        """A piece's values changed (as an edit in the table would)."""
        pieces = self.sequence.frames[frame].pieces
        pieces[piece] = dataclasses.replace(pieces[piece], **values)
        self._fill_frames(frame)
        self.edited.emit()

    def add_frame(self):
        if self.sequence is None:
            return
        row = self.frames.currentRow()
        source = self.sequence.frames[row] if row >= 0 else SpriteFrame()
        self.sequence.frames.insert(row + 1, SpriteFrame(list(source.pieces), source.draw_mode))
        self._fill_frames(row + 1)
        self.edited.emit()

    def remove_frame(self):
        row = self.frames.currentRow()
        if self.sequence is None or row < 0 or len(self.sequence.frames) <= 1:
            return
        del self.sequence.frames[row]
        self._fill_frames(row)
        self.edited.emit()

    def add_piece(self):
        row = self.frames.currentRow()
        if self.sequence is None or row < 0:
            return
        pieces = self.sequence.frames[row].pieces
        if not pieces:
            return
        at = max(self.pieces.currentRow(), 0)
        pieces.insert(at + 1, pieces[at])
        self._fill_frames(row)
        self.edited.emit()

    def remove_piece(self):
        row, at = self.frames.currentRow(), self.pieces.currentRow()
        if self.sequence is None or row < 0 or at < 0:
            return
        del self.sequence.frames[row].pieces[at]
        self._fill_frames(row)
        self.edited.emit()


class TableEditor(QTableWidget):
    """int16 values, `columns` a row."""
    edited = pyqtSignal()

    def __init__(self):
        super().__init__(0, 4)
        self.itemChanged.connect(self._changed)
        self.values = []

    def load(self, data, columns=4):
        self.values = list(struct.unpack(f"<{len(data) // 2}h", data[:len(data) // 2 * 2]))
        self.blockSignals(True)
        self.setColumnCount(columns)
        self.setRowCount((len(self.values) + columns - 1) // columns)
        for index, value in enumerate(self.values):
            self.setItem(index // columns, index % columns, QTableWidgetItem(str(value)))
        self.blockSignals(False)

    def data(self):
        return struct.pack(f"<{len(self.values)}h", *self.values)

    def _changed(self, item):
        index = item.row() * self.columnCount() + item.column()
        try:
            value = int(item.text(), 0)
            if not -0x8000 <= value <= 0x7FFF:
                raise ValueError
            self.values[index] = value
            self.edited.emit()
        except (ValueError, IndexError):
            self.blockSignals(True)
            item.setText(str(self.values[index]) if index < len(self.values) else "")
            self.blockSignals(False)


# a key's columns by channel: (title, kind) - fixed: a 16.16 number shown as a decimal (5 places
# give the int32 back exactly), int: as is, hidden: kept, not shown
KEY_COLUMNS = {
    "position": (("x", "fixed"), ("y (down)", "fixed"), ("z", "fixed")),
    "rotation": (("x (4096 = a turn)", "fixed"), ("y", "fixed"), ("z", "fixed")),
    "scale": (("x (4096 = 1)", "fixed"), ("y", "fixed"), ("z", "fixed")),
    "colour": (("red (x 256)", "int"), ("green", "int"), ("blue", "int"), ("pad", "hidden")),
    "a": (("value (fade)", "fixed"), ("velocity", "fixed"), ("acceleration", "fixed")),
    "b": (("vertex frame a", "int"), ("vertex frame b", "int"), ("blend", "fixed"), ("velocity", "fixed"),
          ("acceleration", "fixed")),
}
CHANNEL_NAMES = {"position": "Position", "rotation": "Rotation", "scale": "Scale", "colour": "Colour",
                 "a": "Channel A (fade)", "b": "Channel B (vertex frames)"}


def track_title(track):
    slot = "" if track.slot == "keys" else f" {track.slot}"
    return f"{CHANNEL_NAMES[track.channel]}{slot} ({len(track.keys)} key{'s' if len(track.keys) != 1 else ''})"


class LayoutEditor(QWidget):
    """A prim-model layout's animation: its length, its objects (their model, flags) and each
    object's tracks and keys. Its models are kept as they are."""
    edited = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.layout_data = None
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(1, 10000)
        self.frames_spin.valueChanged.connect(self._frames_changed)
        self.info = QLabel()
        self.objects = QListWidget()
        self.objects.currentRowChanged.connect(self._show_object)
        self.flags = QLineEdit()
        self.flags.setToolTip("The object's flags: low byte = its model; 0x200 = its offset taken as is (not rotated)")
        self.flags.editingFinished.connect(self._flags_changed)
        self.tracks = QListWidget()
        self.tracks.currentRowChanged.connect(self._show_track)
        self.add_track_box = QComboBox()
        add_track = QPushButton("Add track")
        add_track.clicked.connect(self.add_track)
        remove_track = QPushButton("Remove track")
        remove_track.clicked.connect(self.remove_track)
        self.keys = QTableWidget(0, 1)
        self.keys.itemChanged.connect(self._key_changed)
        add_key = QPushButton("Add key")
        add_key.clicked.connect(self.add_key)
        remove_key = QPushButton("Remove key")
        remove_key.clicked.connect(self.remove_key)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c0392b")
        top = QHBoxLayout()
        top.addWidget(QLabel("Frames"))
        top.addWidget(self.frames_spin)
        top.addWidget(self.info, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Objects"))
        left_layout.addWidget(self.objects, 1)
        flags_row = QHBoxLayout()
        flags_row.addWidget(QLabel("Flags"))
        flags_row.addWidget(self.flags)
        left_layout.addLayout(flags_row)
        left_layout.addWidget(QLabel("Tracks"))
        left_layout.addWidget(self.tracks, 2)
        track_row = QHBoxLayout()
        track_row.addWidget(self.add_track_box, 1)
        track_row.addWidget(add_track)
        left_layout.addLayout(track_row)
        left_layout.addWidget(remove_track)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.keys, 1)
        key_row = QHBoxLayout()
        key_row.addWidget(add_key)
        key_row.addWidget(remove_key)
        key_row.addStretch(1)
        right_layout.addLayout(key_row)
        body = QSplitter()
        body.addWidget(left)
        body.addWidget(right)
        body.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(body, 1)
        layout.addWidget(self.error)

    def load(self, data):
        try:
            self.layout_data = parse_layout(data)
            self.error.clear()
        except ValueError as error:
            self.layout_data = None
            self.error.setText(f"{error}: its bytes are kept as they are.")
        self.frames_spin.blockSignals(True)
        self.frames_spin.setValue(self.layout_data.frames if self.layout_data else 1)
        self.frames_spin.blockSignals(False)
        self.info.setText(f"{self.layout_data.model_count} model(s), kept as they are ({len(self.layout_data.models)} bytes)"
                          if self.layout_data else "")
        self._fill_objects(0)

    def data(self):
        return encode_layout(self.layout_data) if self.layout_data is not None else None

    def _object(self):
        row = self.objects.currentRow()
        return self.layout_data.objects[row] if self.layout_data and 0 <= row < len(self.layout_data.objects) else None

    def _track(self):
        obj, row = self._object(), self.tracks.currentRow()
        return obj.tracks[row] if obj and 0 <= row < len(obj.tracks) else None

    def _fill_objects(self, row):
        self.objects.blockSignals(True)
        self.objects.clear()
        for index, obj in enumerate(self.layout_data.objects if self.layout_data else []):
            self.objects.addItem(f"Object {index}: model {obj.model}")
        self.objects.blockSignals(False)
        self.objects.setCurrentRow(min(row, self.objects.count() - 1))
        self._show_object(self.objects.currentRow())

    def _show_object(self, _row, track_row=0):
        obj = self._object()
        self.flags.setText(f"0x{obj.flags:X}" if obj else "")
        self.tracks.blockSignals(True)
        self.tracks.clear()
        for track in obj.tracks if obj else []:
            self.tracks.addItem(track_title(track))
        self.tracks.blockSignals(False)
        self.add_track_box.clear()
        present = {(t.channel, t.slot) for t in obj.tracks} if obj else set()
        for channel, slot, *_rest in TRACKS:
            if obj and (channel, slot) not in present:
                self.add_track_box.addItem(CHANNEL_NAMES[channel] + ("" if slot == "keys" else f" {slot}"), (channel, slot))
        self.tracks.setCurrentRow(min(track_row, self.tracks.count() - 1))
        self._show_track(self.tracks.currentRow())

    def _show_track(self, _row):
        track = self._track()
        columns = KEY_COLUMNS[track.channel] if track else ()
        shown = [title for title, kind in columns if kind != "hidden"]
        self.keys.blockSignals(True)
        self.keys.setColumnCount(1 + len(shown))
        self.keys.setHorizontalHeaderLabels(["Frame"] + shown)
        self.keys.setRowCount(len(track.keys) if track else 0)
        for r, (frame, values) in enumerate(track.keys if track else []):
            self.keys.setItem(r, 0, QTableWidgetItem(str(frame)))
            c = 1
            for (title, kind), value in zip(columns, values):
                if kind == "hidden":
                    continue
                self.keys.setItem(r, c, QTableWidgetItem(f"{value / 65536:.5f}" if kind == "fixed" else str(value)))
                c += 1
        self.keys.blockSignals(False)

    def _frames_changed(self, value):
        if self.layout_data is not None:
            self.layout_data.frames = value
            self.edited.emit()

    def _flags_changed(self):
        obj = self._object()
        if obj is None:
            return
        try:
            flags = int(self.flags.text(), 0)
            if not 0 <= flags <= 0xFFFFFFFF:
                raise ValueError
        except ValueError:
            self.flags.setText(f"0x{obj.flags:X}")
            return
        if flags != obj.flags:
            obj.flags = flags
            self._fill_objects(self.objects.currentRow())
            self.edited.emit()

    def _key_changed(self, item):
        track = self._track()
        columns = [(title, kind) for title, kind in KEY_COLUMNS[track.channel]]
        frame, values = track.keys[item.row()]
        values = list(values)
        try:
            if item.column() == 0:
                frame = int(item.text(), 0)
                if not 0 <= frame <= 0x7FFFFFFF:
                    raise ValueError
            else:
                index = [i for i, (_t, kind) in enumerate(columns) if kind != "hidden"][item.column() - 1]
                kind = columns[index][1]
                value = round(float(item.text()) * 65536) if kind == "fixed" else int(item.text(), 0)
                low, high = ((-0x80000000, 0x7FFFFFFF) if kind == "fixed" else (0, 0xFFFF))
                if not low <= value <= high:
                    raise ValueError
                values[index] = value
        except ValueError:
            self.error.setText("Not a value for this column")
            self._show_track(self.tracks.currentRow())
            return
        self.error.clear()
        track.keys[item.row()] = (frame, tuple(values))
        if item.column() == 0:
            track.keys.sort()
            self._show_track(self.tracks.currentRow())
        self.edited.emit()

    def set_key(self, obj, track, key, frame=None, values=None):
        """A key changed (as edits in the table would): its frame and / or its values."""
        keys = self.layout_data.objects[obj].tracks[track].keys
        old_frame, old_values = keys[key]
        keys[key] = (old_frame if frame is None else frame, old_values if values is None else tuple(values))
        keys.sort()
        self.objects.setCurrentRow(obj)
        self._show_object(obj, track)
        self.edited.emit()

    def add_key(self):
        track = self._track()
        if track is None:
            return
        row = self.keys.currentRow()
        frame, values = track.keys[row] if 0 <= row < len(track.keys) else (track.keys[-1] if track.keys else (-1, None))
        if values is None:
            values = (0,) * len(KEY_COLUMNS[track.channel])
        used = {f for f, _v in track.keys}
        frame += 1
        while frame in used:
            frame += 1
        track.keys.append((frame, values))
        track.keys.sort()
        self._show_object(self.objects.currentRow(), self.tracks.currentRow())
        self.edited.emit()

    def remove_key(self):
        track, row = self._track(), self.keys.currentRow()
        if track is None or not 0 <= row < len(track.keys):
            return
        del track.keys[row]
        self._show_object(self.objects.currentRow(), self.tracks.currentRow())
        self.edited.emit()

    def add_track(self):
        obj, choice = self._object(), self.add_track_box.currentData()
        if obj is None or choice is None:
            return
        obj.tracks.append(Track(*choice, [(0, (0,) * len(KEY_COLUMNS[choice[0]]))]))
        obj.tracks.sort(key=lambda track: track.spec[2])
        row = next(i for i, t in enumerate(obj.tracks) if (t.channel, t.slot) == choice)
        self._show_object(self.objects.currentRow(), row)
        self.edited.emit()

    def remove_track(self):
        obj, row = self._object(), self.tracks.currentRow()
        if obj is None or not 0 <= row < len(obj.tracks):
            return
        del obj.tracks[row]
        self._show_object(self.objects.currentRow(), row)
        self.edited.emit()


class EffectDataView(QWidget):
    """changed(key, entry): an entry edited and applied."""
    changed = pyqtSignal(str, dict)

    def __init__(self, vram=None, play_sound=None):
        super().__init__()
        self.play_sound = play_sound
        self.description, self.key = None, None
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.currentRowChanged.connect(self._show_entry)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.sequence = SequenceEditor(vram)
        self.layout_editor = LayoutEditor()
        self.layout_editor.edited.connect(self._edited)
        self.sound = QSpinBox()
        self.sound.setRange(0, 0x7FFFFFFF)
        self.sound_archive = QLabel()
        self.sound_play = QPushButton("Play")
        self.sound_play.clicked.connect(self._play)
        self.sound.valueChanged.connect(self._sound_changed)
        sound_page = QWidget()
        sound_form = QFormLayout(sound_page)
        sound_form.addRow("World sound id", self.sound)
        sound_row = QHBoxLayout()
        sound_row.addWidget(self.sound_archive)
        sound_row.addWidget(self.sound_play)
        sound_row.addStretch(1)
        sound_form.addRow("audio.dat entry", sound_row)
        self.table = TableEditor()
        self.name = QLineEdit()
        self.name.setMaxLength(31)
        self.name.textEdited.connect(self._edited)
        name_page = QWidget()
        QFormLayout(name_page).addRow("File name", self.name)
        self.pointers_page = QWidget()
        self.pointers = QFormLayout(self.pointers_page)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.pages = QStackedWidget()
        self.pages_by_kind = {}
        for kind, page in (("seq", self.sequence), ("layout", self.layout_editor), ("sound", sound_page),
                           ("table", self.table), ("name", name_page), ("pointers", self.pointers_page),
                           ("summary", self.summary)):
            self.pages_by_kind[kind] = self.pages.addWidget(page)
        self.sequence.edited.connect(self._edited)
        self.table.edited.connect(self._edited)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.title)
        right_layout.addWidget(self.pages, 1)
        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        apply_row.addWidget(self.apply_button)
        right_layout.addLayout(apply_row)
        body = QSplitter()
        body.addWidget(self.list)
        body.addWidget(right)
        body.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addWidget(body, 1)
        self.show_data(None)

    def show_data(self, description):
        """The data of `description` (a new effect's), or none."""
        self.description = description
        keep = self.key
        data = entries(description) if description else {}
        self.note.setText(NO_DATA if not data else
                          "The effect's own data: Apply writes an entry back; the previews record again and Save writes "
                          "it in the effect's program.")
        self.list.blockSignals(True)
        self.list.clear()
        for key, entry in data.items():
            size = f", {len(entry_bytes(entry))} bytes" if "hex" in entry else ""
            item = QListWidgetItem(f"{key} ({entry.get('kind', '?')}{size})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
        self.list.blockSignals(False)
        keys = list(data)
        self.list.setCurrentRow(keys.index(keep) if keep in keys else 0 if keys else -1)
        self._show_entry(self.list.currentRow())
        self.list.setEnabled(bool(data))

    def select(self, key):
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.list.setCurrentRow(row)
                return

    def entry(self):
        return entries(self.description).get(self.key) if self.description and self.key else None

    def _show_entry(self, row):
        item = self.list.item(row) if row >= 0 else None
        self.key = item.data(Qt.ItemDataRole.UserRole) if item else None
        entry = self.entry()
        self.apply_button.setEnabled(False)
        if entry is None:
            self.title.clear()
            self.summary.clear()
            self.pages.setCurrentIndex(self.pages_by_kind["summary"])
            return
        kind = entry.get("kind")
        origin = f" - copied from the exe at {entry['from']}" if entry.get("from") else ""
        self.title.setText(f"<b>{self.key}</b> ({kind}){origin}")
        data = entry_bytes(entry)
        if kind == "seq":
            self.sequence.load(data)
        elif kind == "layout":
            self.layout_editor.load(data)
        elif kind == "sound":
            self.sound.blockSignals(True)
            self.sound.setValue(struct.unpack_from("<I", data)[0] if len(data) >= 4 else 0)
            self.sound.blockSignals(False)
            self._show_archive()
        elif kind == "table":
            self.table.load(data, entry.get("columns", 4))
        elif kind == "name":
            self.name.setText(data.split(b"\0", 1)[0].decode("ascii", "replace"))
        elif kind == "pointers":
            self._fill_pointers(entry)
        else:
            self.summary.setText(self._summary(kind, data))
        self.pages.setCurrentIndex(self.pages_by_kind.get(kind if kind in self.pages_by_kind else "summary"))

    def _fill_pointers(self, entry):
        while self.pointers.rowCount():
            self.pointers.removeRow(0)
        data = entries(self.description)
        targets = [key for key, other in data.items() if "pointers" not in other]
        for index, key in enumerate(entry["pointers"]):
            combo = QComboBox()
            combo.addItems(targets)
            combo.setCurrentText(key)
            combo.currentTextChanged.connect(self._edited)
            self.pointers.addRow(f"Entry {index}", combo)

    @staticmethod
    def _summary(kind, data):
        if kind == "camera" and len(data) >= 8:
            return (f"A camera track: {len(data)} bytes. The Camera tab edits the effect's camera: its effect_NNN.bcam "
                    "file replaces this track in the game (FFNx).")
        if kind == "tim":
            return f"A TIM image: {len(data)} bytes, uploaded to VRAM as it is when the effect starts (no file)."
        return f"{len(data)} bytes, read-only."

    def _sound_changed(self):
        self._show_archive()
        self._edited()

    def _show_archive(self):
        from Julia.actorsoundtable import world_sound_to_archive_id
        try:
            archive = world_sound_to_archive_id(self.sound.value())
        except ValueError:
            archive = None
        self.sound_archive.setText(str(archive) if archive is not None else "none")
        self.sound_play.setEnabled(archive is not None and self.play_sound is not None)
        self._archive = archive

    def _play(self):
        if self.play_sound is not None and self._archive is not None:
            self.play_sound(self._archive)

    def _edited(self, *_args):
        self.apply_button.setEnabled(self.entry() is not None)

    def edited_entry(self):
        """The shown entry as edited (not applied yet)."""
        entry = dict(self.entry())
        kind = entry.get("kind")
        if kind in ("seq", "layout"):
            data = (self.sequence if kind == "seq" else self.layout_editor).data()
            if data is not None:
                entry["hex"] = data.hex()
        elif kind == "sound":
            entry["hex"] = (struct.pack("<I", self.sound.value()) + entry_bytes(entry)[4:]).hex()
        elif kind == "table":
            entry["hex"] = self.table.data().hex()
        elif kind == "name":
            entry = name_entry(entry, self.name.text())
        elif kind == "pointers":
            entry["pointers"] = [self.pointers.itemAt(row, QFormLayout.ItemRole.FieldRole).widget().currentText()
                                 for row in range(self.pointers.rowCount())]
        return entry

    def apply(self):
        if self.entry() is None:
            return False
        entry = self.edited_entry()
        self.apply_button.setEnabled(False)
        if entry != self.entry():
            self.changed.emit(self.key, entry)
        return True
