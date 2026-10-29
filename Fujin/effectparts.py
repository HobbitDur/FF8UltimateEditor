"""An effect part by part: Choreography's part tabs (one per part of an effect FFNx has a C++ port
with parameters for - Cure: ring, ground glow, overlay, sparkles, motes, glints).

Each tab edits the part's parameters (FFNx src/ff8/battle/fx/fx_params.h: the numbers the port is
made of, the game's values by default) and shows that part alone: the effect is recorded once by
the effect recorder running the port with the edited parameters and only its target drawn (Fujin's
lab recording), every primitive carrying the part that drew it (0: the target itself), and each
tab draws only its own, framed on where that part goes - with the target as a reference when its
Target box is ticked. Under it, the images the part takes its pieces from (Fujin.partimages) and
the sprite sequences it draws (Fujin.partsequences). A
part that draws nothing (Cure's emitter: when the sound plays, when the HP
are given) shows the whole effect, its ticks marked. The parameter table comes from the recorder
itself (`fxrecorder <effect> schema=<file>`), so it is always the one of the port it runs.
"""
import json
import os
import subprocess
import tempfile

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSlider, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from Fujin.partimages import SHEET_HEIGHT, PartImages
from FF8GameData.psxgpu.fxdiff import describe, differences
from Fujin.partsequences import PartSequences, SequenceField
from Fujin.recorderbuild import FFNX_EFFECTS, RECORDER

PREVIEW_WIDTH = 320                 # the part preview's picture width (pixels)
TICKS_PER_SECOND = 15

_SCHEMAS = {}                       # (recorder build, effect) -> schema or None
_PORTS = {}                         # recorder build -> whether it has FFNx's effect ports
PORTS_MISSING = ("Part tabs (an effect part by part, with its parameters - Cure, Potion, Hypnotize) need FFNx's effect "
                 "sources: tick the FFNx button in the header's External program bar, then Update (it downloads "
                 "them and builds Fujin's effect recorder with them; Visual Studio's C++ tools are needed when "
                 "running from source).")
PORTS_BUILDING = "Fujin's effect recorder is being built: the part tabs come when it is ready."


def recorder_has_ports():
    """Whether the effect recorder was built with FFNx's effect sources (its C++ ports and their
    parameters): the updater's FFNxEffects, or a release's recorder."""
    try:
        build = RECORDER.stat().st_mtime_ns
    except OSError:
        return False
    if build not in _PORTS:
        try:
            run = subprocess.run([str(RECORDER), "1", "schema=" + os.devnull], cwd=str(RECORDER.parent),
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            _PORTS[build] = "without FFNx" not in run.stdout
        except (OSError, subprocess.SubprocessError):
            _PORTS[build] = False
    return _PORTS[build]


def ffnx_sources():
    """(repository, ref, commit) of the FFNx effect sources the updater installed, or None."""
    try:
        lines = (FFNX_EFFECTS / "SOURCE.txt").read_text(encoding="utf-8").splitlines()
        return lines[0], lines[1], lines[2]
    except (OSError, IndexError):
        return None


def effect_schema(effect_id):
    """The parameter table of an effect's C++ port: {"parts": [...], "fields": [...]} (see
    fx_params.h), or None when the recorder has none for it (no port with parameters, or a
    recorder built without FFNx's effect sources)."""
    try:
        build = RECORDER.stat().st_mtime_ns
    except OSError:
        return None
    key = (build, effect_id)
    if key not in _SCHEMAS:
        schema = None
        with tempfile.TemporaryDirectory(prefix="fujin_schema_") as folder:
            path = os.path.join(folder, "schema.json")
            try:
                subprocess.run([str(RECORDER), str(effect_id), f"schema={path}"], cwd=str(RECORDER.parent),
                               capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                with open(path, encoding="utf-8") as file:
                    schema = json.load(file)
            except (OSError, ValueError, subprocess.SubprocessError):
                schema = None
        _SCHEMAS[key] = schema if schema and schema.get("parts") else None
    return _SCHEMAS[key]


def defaults(schema):
    return {field["key"]: field["default"] for field in schema["fields"]}


TARGET_PART = 0                     # what no effect part drew: in the lab recording, the target's model


class PartPreview(QWidget):
    """One part of the lab recording, alone (or with the target as a reference), framed on where it
    goes, playable; markers: {tick: what happens then} shown under the picture."""
    reference_toggled = pyqtSignal(bool)

    def __init__(self, runner, part_ids, renderer, markers=lambda: {}):
        super().__init__()
        self.runner, self.part_ids, self.renderer, self.markers = runner, part_ids, renderer, markers
        self._frames, self._view = {}, None
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumSize(PREVIEW_WIDTH, PREVIEW_WIDTH * 7 // 10)
        self.picture.setStyleSheet("background: #101018; color: #C0C0C8;")
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(lambda on: self.timer.start() if on else self.timer.stop())
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._show)
        self.frame_label = QLabel()
        self.reference = QCheckBox("Target")
        self.reference.setToolTip("Draw the effect's target too, as a reference for where the part goes")
        self.reference.toggled.connect(self._reference_toggled)
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / TICKS_PER_SECOND))
        self.timer.timeout.connect(lambda: self.slider.setValue((self.slider.value() + 1) % (self.slider.maximum() + 1)))
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        controls.addWidget(self.reference)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.picture, 1)
        layout.addLayout(controls)
        runner.recording_changed.connect(self.refresh)
        self.refresh()

    def shown_parts(self):
        return self.part_ids | {TARGET_PART} if self.reference.isChecked() else self.part_ids

    def set_reference(self, on):
        """The Target box, set from another tab's (one choice for all of them)."""
        if self.reference.isChecked() != on:
            self.reference.blockSignals(True)
            self.reference.setChecked(on)
            self.reference.blockSignals(False)
            self.refresh()

    def _reference_toggled(self, on):
        self.refresh()
        self.reference_toggled.emit(on)

    def refresh(self):
        """A new lab recording (or none): frame the part on it again."""
        self._frames, self._view = {}, None
        cast = self.runner.cast()
        body = cast.slots.get(cast.target, (None, None))[0]
        self.reference.setText(f"Target ({os.path.basename(body)})" if body else "Target")
        self.reference.setEnabled(bool(body))
        recording = self.runner.recording
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(recording.ticks) - 1) if recording else 0)
        self.slider.blockSignals(False)
        self.play_button.setEnabled(recording is not None)
        if recording is None:
            self.play_button.setChecked(False)
            self.picture.setPixmap(QPixmap())
            self.picture.setText(self.runner.status.text() or "Recording...")
            self.frame_label.setText("")
            return
        if not any(set(tick.parts) & self.part_ids for tick in recording.ticks):
            self.picture.setPixmap(QPixmap())
            self.picture.setText("This part draws nothing with these values.")
            return
        self._view = recording.fit_view(parts=self.shown_parts())
        self._show(self.slider.value())

    def _show(self, tick):
        recording = self.runner.recording
        if recording is None or self._view is None or not recording.ticks:
            return
        tick = min(tick, len(recording.ticks) - 1)
        if tick not in self._frames:
            scale = PREVIEW_WIDTH / max(1, self._view[2])
            image, _gpu = recording.frame(tick, view=self._view, scale=scale, renderer=self.renderer(),
                                          parts=self.shown_parts())
            height, width = image.shape[:2]
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            self._frames[tick] = QPixmap.fromImage(qimage)
        self.picture.setPixmap(self._frames[tick])
        marker = self.markers().get(tick)
        self.frame_label.setText(f"tick {tick} / {len(recording.ticks) - 1}" + (f" - {marker}" if marker else ""))


class PartTab(QWidget):
    """A part's parameters (a form) beside its preview. A part that draws nothing (id 0) previews
    the whole effect (effect_parts: every drawing part's id), its tick parameters marked on it.
    A Sequence field (type "seq") picks a sprite sequence of the exe; a Frames field marks the
    frames its sequence plays; each field's "?" records the effect with it nudged and says what
    draws differently (part_names: {part id: title})."""
    value_changed = pyqtSignal(str, int)      # key, new value

    def __init__(self, part, fields, values, runner, renderer, effect_parts=frozenset(), locate=None,
                 part_names=None):
        super().__init__()
        self.part, self.fields, self.runner = part, fields, runner
        self.part_names = part_names or {}
        self.spins, self.labels = {}, {}
        doc = QLabel(part["doc"] + ("" if part["id"] else
                                    ". It draws nothing: the preview shows the whole effect, its ticks marked."))
        doc.setWordWrap(True)
        form = QFormLayout()
        for field in fields:
            sequence = field.get("type") == "seq"
            spin = SequenceField(runner, self.part_names) if sequence else QSpinBox()
            spin.setRange(field["min"], field["max"])
            spin.setValue(values.get(field["key"], field["default"]))
            game = f"0x{field['default']:X}" if sequence else field["default"]
            spin.setToolTip(f"{field['doc']}\nThe game's value: {game}".strip())
            spin.valueChanged.connect(lambda value, key=field["key"]: self._changed(key, value))
            label = QLabel(field["label"])
            label.setToolTip(spin.toolTip())
            probe = QToolButton()
            probe.setText("?")
            probe.setToolTip("What does it change? Records the effect with this value nudged by one and "
                             "lists what draws differently")
            probe.setEnabled(not sequence)
            probe.clicked.connect(lambda _checked, key=field["key"]: self.probe(key))
            row = QHBoxLayout()
            row.addWidget(spin, 1)
            row.addWidget(probe)
            self.spins[field["key"]], self.labels[field["key"]] = spin, label
            form.addRow(label, row)
            self._mark(field["key"])
        self.probe_text = QLabel()
        self.probe_text.setWordWrap(True)
        self.probe_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        reset = QPushButton("Game values")
        reset.setToolTip("Put this part's parameters back to the game's values")
        reset.clicked.connect(self.reset)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.addWidget(doc)
        form_layout.addLayout(form)
        form_layout.addWidget(reset)
        form_layout.addWidget(self.probe_text)
        form_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setMinimumWidth(380)
        part_ids = {part["id"]} if part["id"] else set(effect_parts)      # 0: draws nothing, the whole effect
        self.preview = PartPreview(runner, part_ids, renderer, markers=self.markers)
        self.images = PartImages(runner, part_ids, self.named_images, locate, part["title"])
        self.sequences = PartSequences(runner, part_ids, self.part_names)
        self.sequences.picked.connect(self.images.select)
        self.preview.slider.valueChanged.connect(self.images.set_tick)
        self.preview.slider.valueChanged.connect(self.sequences.set_tick)
        self.below = QTabWidget()
        self.below.addTab(self.images, "Images")
        self.below.addTab(self.sequences, "Sprite sequences")
        self.below.setFixedHeight(SHEET_HEIGHT + 150)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.below)
        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addLayout(right, 1)
        self._update_limits()

    def frame_limits(self):
        """{sequence address: (Frames field label, last frame played)}: a "frames" field and the
        "seq" field beside it (ring.end_frames - ring.end_seq, sparkle.frames - sparkle.seq)."""
        limits = {}
        for field in self.fields:
            key = field["key"]
            sequence = key[:-len("frames")] + "seq" if key.endswith("frames") else None
            if sequence in self.spins:
                limits[self.spins[sequence].value()] = (f"{self.part['title']} {field['label']}",
                                                         self.spins[key].value())
        return limits

    def _update_limits(self):
        self.sequences.set_limits(self.frame_limits())

    def probe(self, key):
        """What `key` changes: the effect recorded with it one lower (higher at its minimum), compared
        with the shown recording, the differences listed under the form and the preview moved to
        the first tick that changes."""
        field = next(field for field in self.fields if field["key"] == key)
        base = self.runner.recording
        if base is None:
            self.probe_text.setText("What does it change: the recording is not ready yet.")
            return
        value = self.spins[key].value()
        nudged = value - 1 if value > field["min"] else value + 1
        params = dict(self.runner.cast().params)
        params[key] = nudged
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            variant = self.runner.record_with(params)
        finally:
            QApplication.restoreOverrideCursor()
        if variant is None:
            self.probe_text.setText("What does it change: the effect recorder could not record it.")
            return
        changes, lengths = differences(base, variant, self.part_names)
        self.probe_text.setText(f"<b>{field['label']} {value} → {nudged}</b><br>"
                                + "<br>".join(line.replace("    ", "&nbsp;&nbsp;&nbsp;&nbsp;")
                                              for line in describe(changes, lengths)))
        first = min((entry["ticks"][0] for entry in changes), default=None)
        if first is not None:
            self.preview.slider.setValue(min(first, self.preview.slider.maximum()))

    def markers(self):
        """{tick: what happens}: a part drawing nothing has its tick parameters marked on the preview."""
        if self.part["id"]:
            return {}
        marks = {}
        for field in self.fields:
            if field["key"].endswith("_tick"):
                tick = self.spins[field["key"]].value()
                marks[tick] = ", ".join(filter(None, (marks.get(tick), field["label"].replace(" tick", ""))))
        return marks

    def named_images(self):
        """[(label, VRAM x, y, CLUT word, width, height)] of the images this part's values name: a
        tex_x / tex_y / clut_x / clut_y group (Cure's overlay: its projected image), sized by the
        group's width / height."""
        names = {field["key"]: field for field in self.fields}
        images = []
        for key in names:
            if not key.endswith(".tex_x"):
                continue
            group = key[:-len("tex_x")]
            value = lambda name, default=0: (self.spins[group + name].value() if group + name in self.spins
                                             else default)
            if group + "tex_y" in names:
                clut = (value("clut_x") // 16) | (value("clut_y") << 6)
                images.append((names[key]["label"].replace(" VRAM x", ""), value("tex_x"), value("tex_y"),
                               clut, value("width", 256), value("height", 256)))
        return images

    def _default(self, key):
        return next(field["default"] for field in self.fields if field["key"] == key)

    def _mark(self, key):
        font = self.labels[key].font()
        font.setBold(self.spins[key].value() != self._default(key))     # bold: not the game's value
        self.labels[key].setFont(font)

    def _changed(self, key, value):
        self._mark(key)
        self._update_limits()
        self.preview._show(self.preview.slider.value())      # its tick markers
        self.value_changed.emit(key, value)

    def reset(self):
        for field in self.fields:
            self.spins[field["key"]].setValue(field["default"])

    def set_values(self, values):
        for field in self.fields:
            spin = self.spins[field["key"]]
            spin.blockSignals(True)
            spin.setValue(values.get(field["key"], field["default"]))
            spin.blockSignals(False)
            self._mark(field["key"])
