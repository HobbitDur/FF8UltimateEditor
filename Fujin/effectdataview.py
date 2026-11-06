"""Choreography's Data tab: a new effect's own data (its description's "data", copied from the exe
when it was made: docs/fujin-effect-description.md), each entry edited by kind:

- seq: a sprite sequence (FF8GameData.psxgpu.spritesequence): its palette-row parameters, its
  frames and each frame's pieces (texels, size, palette, page flags, place, angle, scale,
  intensity, GPU code), the frames drawn from the last recording's video memory. A port's sequence
  keeps at least the frames its code plays;
- sound: the world sound id its block holds (what the game plays: the Sound tab's archive entry);
- table: numbers, `columns` a row (Hypnotize's ring points: x, y, z, bone; a port's colours, curves, a
  morph's vertex sets): int16 unless its entry says another "format" (struct: b B h H i I), "skip" header
  bytes kept as they are (a vertex set's size and count), "labels" its columns; its length is kept;
- name: a file name (the effect's texture file);
- pointers: a table of other entries (Hypnotize's ring and target layouts), each picked by key;
- layout: a prim-model layout's animation (FF8GameData.psxgpu.primlayout): its length, its objects
  (model, flags) and each object's tracks (position, rotation, scale, colour, fade, vertex-frame
  blend: value / velocity / acceleration) and their keys; its models kept as they are. A port's
  layout has a capacity (the state block its code decodes it into): more objects or tracks than it
  holds are not applied;
- model: a prim model (FF8GameData.psxgpu.primmodel, Fujin.modeleditor): its vertices and primitives
  (kind, vertices, colours, texture corners), drawn in a preview, scaled or moved as a whole. A
  model keeps its vertices (its code reads them by number; same_size: its primitives too);
- camera: a camera track (FF8GameData.dat.cameratrack): its keyframes and its script, in the editor the
  Camera tab and Alexander share (Common.cameratrackeditor); a .bcam imported or exported. A new effect's
  own track may change size (its offsets are its own). Without the camera tools: what it holds;
- tim: a TIM image (Fujin.texturepictureview's card): its picture and palette through PNG files, where
  it loads in video memory; a .tim imported (with a palette when the game's has one) or exported;
- anim_set: an animation set bound to the caster ({count, offsets, end}: body animations, sequence
  scripts, weapon animations): its sections; a set of the game's count imported, or exported. The bytes
  after it ("tail": the game reads past a set's end) are kept. This is the new effect's own copy: the game's
  effect itself takes an effect_NNN.animset file (Fujin.animsetfiles, Import: FFNx animation sets).

The description's "not_editable" rows (data its code reads at a fixed place of the exe) are listed after
them in grey, their bytes shown read-only.

Apply writes the entry back (changed(key, entry)): the previews record again, Save writes it in
the program.
"""
import dataclasses
import os
import struct

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from FF8GameData.psxgpu.primlayout import TRACKS, Track, encode_layout, parse_layout, state_size
from FF8GameData.psxgpu.spritesequence import SpriteFrame, encode_sequence, parse_sequence
from Fujin.effectprogram import IMAGE_BASE
from Fujin.modeleditor import ModelEditor

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


def not_editable(description):
    """The description's data its code reads at a fixed place of the exe, by key."""
    return {entry["key"]: entry for entry in (description or {}).get("not_editable", [])}


def hex_dump(address, data):
    """`data` as 16 bytes a line, each line's exe address first."""
    return "\n".join(f"{address + at:08X}  {data[at:at + 16].hex(' ')}" for at in range(0, len(data), 16))


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
        self.min_frames = None                          # a port's: the frames its code plays, or None
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
        if self.min_frames is not None and len(self.sequence.frames) <= self.min_frames:
            self.error.setText(f"Its effect's code plays {self.min_frames} frames: it keeps at least as many.")
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


TABLE_RANGES = {"b": (-0x80, 0x7F), "B": (0, 0xFF), "h": (-0x8000, 0x7FFF), "H": (0, 0xFFFF),
                "i": (-0x80000000, 0x7FFFFFFF), "I": (0, 0xFFFFFFFF)}


class TableEditor(QTableWidget):
    """Numbers of one format (struct: int16 by default), `columns` a row, after `skip` header bytes kept as they
    are (and whatever is left past the last whole number); `labels` the columns' titles."""
    edited = pyqtSignal()

    def __init__(self):
        super().__init__(0, 4)
        self.itemChanged.connect(self._changed)
        self.values = []
        self.format, self.head, self.rest = "h", b"", b""

    def load(self, data, columns=4, format="h", skip=0, labels=None):
        self.format = format if format in TABLE_RANGES else "h"
        size = struct.calcsize(self.format)
        count = max(0, len(data) - skip) // size
        self.head, self.rest = data[:skip], data[skip + count * size:]
        self.values = list(struct.unpack_from(f"<{count}{self.format}", data, skip))
        self.blockSignals(True)
        self.setColumnCount(columns)
        self.setHorizontalHeaderLabels(list(labels or [str(c + 1) for c in range(columns)])[:columns])
        self.setRowCount((len(self.values) + columns - 1) // columns)
        for index, value in enumerate(self.values):
            self.setItem(index // columns, index % columns, QTableWidgetItem(str(value)))
        self.blockSignals(False)

    def data(self):
        return self.head + struct.pack(f"<{len(self.values)}{self.format}", *self.values) + self.rest

    def _changed(self, item):
        index = item.row() * self.columnCount() + item.column()
        try:
            value = int(item.text(), 0)
            low, high = TABLE_RANGES[self.format]
            if not low <= value <= high:
                raise ValueError
            self.values[index] = value
            self.edited.emit()
        except (ValueError, IndexError):
            self.blockSignals(True)
            item.setText(str(self.values[index]) if index < len(self.values) else "")
            self.blockSignals(False)


class _Bytes:
    """A TIM card's document (Fujin.texturepictureview.TimTexture): the bytes edited in place."""
    def __init__(self, data, edited):
        self.data, self.original, self._edited = bytearray(data), bytes(data), edited

    def patch_bytes(self, offset, raw):
        self.data[offset:offset + len(raw)] = raw
        self._edited()


def _file_folder(registry, key):
    return registry.last_folder(key) if registry is not None else ""


class TimPage(QWidget):
    """A TIM entry: Fujin's TIM card (picture, palette, PNG import / export, video memory place), a .tim
    imported (a palette when the game's has one: fx_params.h tim() keeps the game's otherwise) or exported."""
    edited = pyqtSignal()

    def __init__(self, registry=None):
        super().__init__()
        self.registry, self.bytes, self.card = registry, None, None
        self.import_button = QPushButton("Import .tim…")
        self.import_button.clicked.connect(self.import_tim)
        self.export_button = QPushButton("Export .tim…")
        self.export_button.clicked.connect(self.export_tim)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c77800")
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addWidget(self.error, 1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.scroll, 1)

    def load(self, data):
        from Fujin.texturepictureview import TimTexture, _TimCard
        self.bytes = _Bytes(data, self._card_edited)
        self.error.clear()
        try:
            self.card = _TimCard(TimTexture(self.bytes, 0), "TIM", 0, self.registry)
            self.card.changed.connect(self.edited)
            self.scroll.setWidget(self.card)
        except Exception as error:   # (not a TIM this card reads: its bytes kept)
            self.card = None
            self.scroll.setWidget(QLabel(f"A TIM of {len(data)} bytes: {error}"))

    def _card_edited(self):
        self.edited.emit()

    def data(self):
        return bytes(self.bytes.data) if self.bytes is not None else None

    def import_tim(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Import a TIM", _file_folder(self.registry, "Fujin data TIM"),
                                                    "TIM (*.tim);;All files (*)")
        if not path:
            return
        data = open(path, "rb").read()
        old = self.data() or b""
        if len(data) < 8 or struct.unpack_from("<I", data)[0] != 0x10:
            self.error.setText("Not a TIM (its id is not 0x10).")
            return
        if len(old) >= 8 and (struct.unpack_from("<I", data, 4)[0] & 8) != (struct.unpack_from("<I", old, 4)[0] & 8):
            self.error.setText("The game's TIM " + ("has" if struct.unpack_from("<I", old, 4)[0] & 8 else "has no")
                               + " palette: this one must too (its code uploads it as such).")
            return
        if self.registry is not None:
            self.registry.remember_folder("Fujin data TIM", os.path.dirname(path))
        self.load(data)
        self.edited.emit()

    def export_tim(self):
        if self.data() is None:
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Export the TIM", _file_folder(self.registry, "Fujin data TIM"),
                                                    "TIM (*.tim)")
        if path:
            open(path, "wb").write(self.data())


class CameraPage(QWidget):
    """A camera track entry: its keyframes and script in the shared track editor (Common.cameratrackeditor;
    `tools` a CameraScriptTools: Fujin's camera manager), a .bcam imported or exported. A new effect's own
    track may change size."""
    edited = pyqtSignal()

    def __init__(self, tools=None, registry=None):
        super().__init__()
        self.tools, self.registry, self.track = tools, registry, None
        self.raw = b""
        self.import_button = QPushButton("Import .bcam…")
        self.import_button.clicked.connect(self.import_bcam)
        self.export_button = QPushButton("Export .bcam…")
        self.export_button.clicked.connect(self.export_bcam)
        self.info = QLabel()
        self.info.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addWidget(self.info, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        self.editor = None
        if tools is not None:
            from Common.cameratrackeditor import CameraTrackEditor
            self.editor = CameraTrackEditor(tools, room_name="effect's own data",
                                            growth_note="a new effect's own track may grow: its offsets are its own")
            self.editor.keyframes_changed.connect(self.edited)
            self.editor.track_changed.connect(self.edited)
            layout.addWidget(self.editor, 1)
        else:
            layout.addStretch(1)

    def load(self, data):
        self.raw, self.track = bytes(data), None
        if self.tools is not None:
            from FF8GameData.dat.cameratrack import CameraTrack
            try:
                self.track = CameraTrack.from_bytes(self.tools.vm, self.raw)
            except ValueError as error:
                self.info.setText(f"Not a camera track this editor reads ({error}): its bytes are kept.")
        if self.editor is not None:
            self.editor.set_track(self.track)
        if self.track is not None or self.tools is None:
            self.info.setText(f"A camera track: {len(self.raw)} bytes."
                              + ("" if self.tools is not None else " Open the exe (Camera tab) to edit it here."))

    def data(self):
        return self.track.to_bytes() if self.track is not None else self.raw

    def import_bcam(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Import a camera track", _file_folder(self.registry, "Fujin data camera"),
                                                    "Camera track (*.bcam);;All files (*)")
        if not path:
            return
        data = open(path, "rb").read()
        if len(data) < 8 or struct.unpack_from("<H", data, 2)[0] != 8 or struct.unpack_from("<H", data, 6)[0] != len(data):
            self.info.setText("Not a camera track (its header: script at 8, its size the file's).")
            return
        if self.registry is not None:
            self.registry.remember_folder("Fujin data camera", os.path.dirname(path))
        self.load(data)
        self.edited.emit()

    def export_bcam(self):
        path, _filter = QFileDialog.getSaveFileName(self, "Export the camera track", _file_folder(self.registry, "Fujin data camera"),
                                                    "Camera track (*.bcam)")
        if path:
            open(path, "wb").write(self.data())


def anim_set_sections(data):
    """[(name, start, end)] of an animation set's sections ({count, offsets[count], end}), or None."""
    if len(data) < 8:
        return None
    count = struct.unpack_from("<I", data)[0]
    if not 1 <= count <= 8 or len(data) < 4 * (count + 2):
        return None
    offsets = struct.unpack_from(f"<{count + 1}I", data, 4)
    if offsets[0] < 4 * (count + 2) or list(offsets) != sorted(offsets) or offsets[-1] > len(data):
        return None
    names = ("body animations", "sequence scripts", "weapon animations")
    return [(names[k] if k < len(names) else f"section {k}", offsets[k], offsets[k + 1]) for k in range(count)]


class AnimSetPage(QWidget):
    """An animation set entry: its sections, a set of the game's count imported (the bytes after the set -
    its entry's "tail": the game reads past a set's end - kept) or the set exported."""
    edited = pyqtSignal()

    def __init__(self, registry=None):
        super().__init__()
        self.registry, self.raw, self.tail = registry, b"", 0
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.import_button = QPushButton("Import a set…")
        self.import_button.clicked.connect(self.import_set)
        self.export_button = QPushButton("Export the set…")
        self.export_button.clicked.connect(self.export_set)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.info, 1)

    def load(self, data, tail=0):
        self.raw, self.tail = bytes(data), tail
        self._describe()

    def _describe(self, note=""):
        sections = anim_set_sections(self.raw[:len(self.raw) - self.tail])
        if sections is None:
            self.info.setText(f"{len(self.raw)} bytes that do not read as an animation set." + note)
            return
        lines = [f"An animation set of {len(sections)} sections ({len(self.raw) - self.tail} bytes"
                 + (f", then the {self.tail} bytes after it the game may read, kept" if self.tail else "") + "):"]
        for name, start, end in sections:
            count = struct.unpack_from("<I", self.raw, start)[0] if end - start >= 4 else 0
            lines.append(f"- {name}: {end - start} bytes" + (f", {count} entries" if count < 256 else ""))
        self.info.setText("\n".join(lines) + note)

    def data(self):
        return self.raw

    def import_set(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Import an animation set", _file_folder(self.registry, "Fujin data anim"),
                                                    "Animation set (*.anim *.bin);;All files (*)")
        if not path:
            return
        data = open(path, "rb").read()
        sections = anim_set_sections(data)
        game = anim_set_sections(self.raw[:len(self.raw) - self.tail])
        if sections is None or (game is not None and len(sections) != len(game)):
            self._describe(f"\n\nNot imported: not a set of {len(game or ())} sections.")
            return
        if self.registry is not None:
            self.registry.remember_folder("Fujin data anim", os.path.dirname(path))
        end = struct.unpack_from("<I", data, 4 * (len(sections) + 1))[0]
        self.raw = data[:end] + self.raw[len(self.raw) - self.tail:] if self.tail else data[:end]
        self._describe()
        self.edited.emit()

    def export_set(self):
        path, _filter = QFileDialog.getSaveFileName(self, "Export the animation set", _file_folder(self.registry, "Fujin data anim"),
                                                    "Animation set (*.anim)")
        if path:
            open(path, "wb").write(self.raw[:len(self.raw) - self.tail])


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
        self.capacity = None                            # a port's state block for it (bytes), or None
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

    def too_big(self):
        """What is wrong when the layout needs more player state than its port holds (else "")."""
        if self.layout_data is None or self.capacity is None or state_size(self.layout_data) <= self.capacity:
            return ""
        return (f"It needs {state_size(self.layout_data)} bytes of player state, its effect's code holds "
                f"{self.capacity}: fewer objects or tracks.")

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

    def __init__(self, vram=None, play_sound=None, camera_tools=None, registry=None, exe=None):
        """camera_tools: a CameraScriptTools (Fujin's camera manager) for the camera page; registry: the
        file registry (the import / export folders); exe: gives FF8_EN.exe's bytes, or None (what the
        not editable rows show)."""
        super().__init__()
        self.play_sound = play_sound
        self.exe = exe
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
        self.model_editor = ModelEditor()
        self.model_editor.edited.connect(self._edited)
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
        self.camera_page = CameraPage(camera_tools, registry)
        self.tim_page = TimPage(registry)
        self.anim_page = AnimSetPage(registry)
        for page in (self.camera_page, self.tim_page, self.anim_page):
            page.edited.connect(self._edited)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.fixed_doc = QLabel()
        self.fixed_doc.setWordWrap(True)
        self.fixed_bytes = QPlainTextEdit()
        self.fixed_bytes.setReadOnly(True)
        self.fixed_bytes.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        fixed_page = QWidget()
        fixed_layout = QVBoxLayout(fixed_page)
        fixed_layout.addWidget(self.fixed_doc)
        fixed_layout.addWidget(self.fixed_bytes, 1)
        self.pages = QStackedWidget()
        self.pages_by_kind = {}
        for kind, page in (("seq", self.sequence), ("layout", self.layout_editor), ("model", self.model_editor),
                           ("sound", sound_page),
                           ("table", self.table), ("name", name_page), ("pointers", self.pointers_page),
                           ("camera", self.camera_page), ("tim", self.tim_page), ("anim_set", self.anim_page),
                           ("summary", self.summary), ("not_editable", fixed_page)):
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
        fixed = not_editable(description)
        self.note.setText((NO_DATA if not data else
                           "The effect's own data: Apply writes an entry back; the previews record again and Save writes "
                           "it in the effect's program.") +
                          (" The rows in grey are not editable: its code reads them at a fixed place of the exe." if fixed else ""))
        self.list.blockSignals(True)
        self.list.clear()
        for key, entry in data.items():
            size = f", {len(entry_bytes(entry))} bytes" if "hex" in entry else ""
            item = QListWidgetItem(f"{key} ({entry.get('kind', '?')}{size})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
        for key, entry in fixed.items():
            item = QListWidgetItem(f"{entry['label']} (not editable)")
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setForeground(self.palette().placeholderText())
            item.setToolTip(f"{entry['doc']}\nAt {entry['address']} in the exe")
            self.list.addItem(item)
        self.list.blockSignals(False)
        keys = [*data, *fixed]
        self.list.setCurrentRow(keys.index(keep) if keep in keys else 0 if keys else -1)
        self._show_entry(self.list.currentRow())
        self.list.setEnabled(bool(keys))

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
        fixed = not_editable(self.description).get(self.key)
        if fixed is not None:
            self._show_not_editable(fixed)
            return
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
            self.sequence.min_frames = entry.get("frames")
            self.sequence.load(data)
        elif kind == "layout":
            self.layout_editor.capacity = entry.get("capacity")
            self.layout_editor.load(data)
        elif kind == "model":
            self.model_editor.fixed_vertices = entry.get("vertices")
            self.model_editor.same_size = bool(entry.get("same_size"))
            self.model_editor.load(data)
        elif kind == "sound":
            self.sound.blockSignals(True)
            self.sound.setValue(struct.unpack_from("<I", data)[0] if len(data) >= 4 else 0)
            self.sound.blockSignals(False)
            self._show_archive()
        elif kind == "table":
            self.table.load(data, entry.get("columns", 4), entry.get("format", "h"), entry.get("skip", 0), entry.get("labels"))
        elif kind == "camera":
            self.camera_page.load(data)
        elif kind == "tim":
            self.tim_page.load(data)
        elif kind == "anim_set":
            self.anim_page.load(data, entry.get("tail", 0))
        elif kind == "name":
            self.name.setText(data.split(b"\0", 1)[0].decode("ascii", "replace"))
        elif kind == "pointers":
            self._fill_pointers(entry)
        else:
            self.summary.setText(self._summary(kind, data))
        self.pages.setCurrentIndex(self.pages_by_kind.get(kind if kind in self.pages_by_kind else "summary"))

    def _show_not_editable(self, entry):
        """A row its code reads at a fixed place: what it is, and the bytes there up to the next data it names."""
        self.title.setText(f"<b>{entry['label']}</b> (not editable) - at {entry['address']} in the exe")
        self.fixed_doc.setText(f"{entry['doc']}. Its code reads it at this place of the exe, not through a parameter: "
                               "a new effect's copy reads the game's too.")
        exe, address = self.exe() if self.exe is not None else None, int(entry["address"], 16)
        at = address - IMAGE_BASE
        self.fixed_bytes.setPlainText(hex_dump(address, exe[at:at + entry["size"]]) if exe else
                                      "Open FF8_EN.exe to see its bytes.")
        self.pages.setCurrentIndex(self.pages_by_kind["not_editable"])

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
        if kind in ("seq", "layout", "model"):
            data = {"seq": self.sequence, "layout": self.layout_editor, "model": self.model_editor}[kind].data()
            if data is not None:
                entry["hex"] = data.hex()
        elif kind == "sound":
            entry["hex"] = (struct.pack("<I", self.sound.value()) + entry_bytes(entry)[4:]).hex()
        elif kind == "table":
            entry["hex"] = self.table.data().hex()
        elif kind in ("camera", "tim", "anim_set"):
            data = {"camera": self.camera_page, "tim": self.tim_page, "anim_set": self.anim_page}[kind].data()
            if data is not None:
                entry["hex"] = data.hex()
        elif kind == "name":
            entry = name_entry(entry, self.name.text())
        elif kind == "pointers":
            entry["pointers"] = [self.pointers.itemAt(row, QFormLayout.ItemRole.FieldRole).widget().currentText()
                                 for row in range(self.pointers.rowCount())]
        return entry

    def apply(self):
        if self.entry() is None:
            return False
        if self.entry().get("kind") == "layout" and self.layout_editor.too_big():
            self.layout_editor.error.setText(self.layout_editor.too_big())
            return False
        entry = self.edited_entry()
        self.apply_button.setEnabled(False)
        if entry != self.entry():
            self.changed.emit(self.key, entry)
        return True
