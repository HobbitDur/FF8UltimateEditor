"""An effect part by part: Choreography's part tabs (one per part of an effect FFNx has a C++ port
with parameters for - Cure: ring, ground glow, overlay, sparkles, motes, glints).

Each tab edits the part's parameters (FFNx src/ff8/battle/fx/fx_params.h: the numbers the port is
made of, the game's values by default) and shows that part alone: the effect is recorded once by
the effect recorder running the port with the edited parameters and no actors (Fujin's lab
recording), every primitive carrying the part that drew it, and each tab draws only its own,
framed on where that part goes. The parameter table comes from the recorder itself
(`fxrecorder <effect> schema=<file>`), so it is always the one of the port it runs.
"""
import json
import os
import subprocess
import tempfile

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QSpinBox,
                             QVBoxLayout, QWidget)

from Fujin.recorderbuild import FFNX_EFFECTS, RECORDER

PREVIEW_WIDTH = 320                 # the part preview's picture width (pixels)
TICKS_PER_SECOND = 15

_SCHEMAS = {}                       # (recorder build, effect) -> schema or None
_PORTS = {}                         # recorder build -> whether it has FFNx's effect ports
PORTS_MISSING = ("Part tabs (an effect part by part, with its parameters - Cure for now) need FFNx's effect "
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


class PartPreview(QWidget):
    """One part of the lab recording, alone, framed on where it goes, playable."""

    def __init__(self, runner, part_ids, renderer):
        super().__init__()
        self.runner, self.part_ids, self.renderer = runner, part_ids, renderer
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
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / TICKS_PER_SECOND))
        self.timer.timeout.connect(lambda: self.slider.setValue((self.slider.value() + 1) % (self.slider.maximum() + 1)))
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.picture, 1)
        layout.addLayout(controls)
        runner.recording_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        """A new lab recording (or none): frame the part on it again."""
        self._frames, self._view = {}, None
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
        if not any(set(tick.parts) & self.part_ids for tick in recording.ticks) and self.part_ids:
            self.picture.setText("This part draws nothing with these values.")
            return
        self._view = recording.fit_view(parts=self.part_ids or None)
        self._show(self.slider.value())

    def _show(self, tick):
        recording = self.runner.recording
        if recording is None or self._view is None or not recording.ticks:
            return
        tick = min(tick, len(recording.ticks) - 1)
        if tick not in self._frames:
            scale = PREVIEW_WIDTH / max(1, self._view[2])
            image, _gpu = recording.frame(tick, view=self._view, scale=scale, renderer=self.renderer(),
                                          parts=self.part_ids or None)
            height, width = image.shape[:2]
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            self._frames[tick] = QPixmap.fromImage(qimage)
        self.picture.setPixmap(self._frames[tick])
        self.frame_label.setText(f"tick {tick} / {len(recording.ticks) - 1}")


class PartTab(QWidget):
    """A part's parameters (a form) beside its preview."""
    value_changed = pyqtSignal(str, int)      # key, new value

    def __init__(self, part, fields, values, runner, renderer):
        super().__init__()
        self.part, self.fields = part, fields
        self.spins, self.labels = {}, {}
        doc = QLabel(part["doc"])
        doc.setWordWrap(True)
        form = QFormLayout()
        for field in fields:
            spin = QSpinBox()
            spin.setRange(field["min"], field["max"])
            spin.setValue(values.get(field["key"], field["default"]))
            spin.setToolTip(f"{field['doc']}\nThe game's value: {field['default']}".strip())
            spin.valueChanged.connect(lambda value, key=field["key"]: self._changed(key, value))
            label = QLabel(field["label"])
            label.setToolTip(spin.toolTip())
            self.spins[field["key"]], self.labels[field["key"]] = spin, label
            form.addRow(label, spin)
            self._mark(field["key"])
        reset = QPushButton("Game values")
        reset.setToolTip("Put this part's parameters back to the game's values")
        reset.clicked.connect(self.reset)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.addWidget(doc)
        form_layout.addLayout(form)
        form_layout.addWidget(reset)
        form_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setMinimumWidth(280)
        part_ids = {part["id"]} if part["id"] else set()      # 0: the whole effect
        self.preview = PartPreview(runner, part_ids, renderer)
        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(self.preview, 1)

    def _default(self, key):
        return next(field["default"] for field in self.fields if field["key"] == key)

    def _mark(self, key):
        font = self.labels[key].font()
        font.setBold(self.spins[key].value() != self._default(key))     # bold: not the game's value
        self.labels[key].setFont(font)

    def _changed(self, key, value):
        self._mark(key)
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
