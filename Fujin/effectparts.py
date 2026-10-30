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

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QSlider, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from Fujin.partimages import SHEET_HEIGHT, PartImages
from FF8GameData.psxgpu.fxdiff import differences, tick_runs
from Fujin.partsequences import PartSequences, SequenceField
from Fujin.recorderbuild import FFNX_EFFECTS, RECORDER

PREVIEW_WIDTH = 320                 # the part preview's picture width (pixels)
PATH_COLOUR = QColor(190, 90, 255, 200)     # the part's sprite paths
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


class DiffStrip(QWidget):
    """Under a compared preview's slider: a cell per tick, red where the part draws differently with
    the other value, amber where only other parts do; a click goes to that tick."""
    clicked = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self.mine, self.others, self.count = set(), set(), 0
        self.setToolTip("Red: this part draws differently at that tick with the compared value; amber: only "
                        "other parts do. Click to go there.")

    def set_ticks(self, mine, others, count):
        self.mine, self.others, self.count = set(mine), set(others) - set(mine), count
        self.update()

    def mousePressEvent(self, event):
        if self.count:
            self.clicked.emit(min(self.count - 1, int(event.position().x() * self.count / max(1, self.width()))))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(60, 60, 66))
        for ticks, colour in ((self.others, QColor(230, 170, 40)), (self.mine, QColor(235, 60, 60))):
            for tick in ticks:
                left = round(tick * self.width() / max(1, self.count))
                right = round((tick + 1) * self.width() / max(1, self.count))
                painter.fillRect(left, 0, max(1, right - left), self.height(), colour)


class PartPreview(QWidget):
    """One part of the lab recording, alone (or with the target as a reference, as last drawn when
    the effect hides it), framed on where it goes, playable; markers: {tick: what happens then}
    shown under the picture. Compare (a field's "?"): the same part with another value of one
    field, beside it, the ticks that change marked under the slider."""
    reference_toggled = pyqtSignal(bool)

    def __init__(self, runner, part_ids, renderer, markers=lambda: {}, part_names=None):
        super().__init__()
        self.runner, self.part_ids, self.renderer, self.markers = runner, part_ids, renderer, markers
        self.part_names = part_names or {}
        self._frames, self._view, self._size = {}, None, None
        self.variant, self.compared = None, None      # the compared recording; (field, record(value))
        self.picture, self.picture_b = self._picture(), self._picture()
        self.caption, self.caption_b = QLabel(), QLabel()
        self.picture_b.hide()
        self.caption.hide()
        self.caption_b.hide()
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(lambda on: self.timer.start() if on else self.timer.stop())
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._show)
        self.strip = DiffStrip()
        self.strip.clicked.connect(self.slider.setValue)
        self.strip.hide()
        self.frame_label = QLabel()
        self.reference = QCheckBox("Target")
        self.reference.setToolTip("Draw the effect's target too, as a reference for where the part goes (as "
                                  "last drawn when the effect hides it, as Cure does while redrawing it)")
        self.reference.toggled.connect(self._reference_toggled)
        self.path = QCheckBox("Path")
        self.path.setChecked(True)
        self.path.setToolTip("Where each sprite of the part goes over the whole effect: a thin purple line from "
                             "where it is drawn one tick to where it is drawn the next, a dot where it appears")
        self.path.toggled.connect(lambda _on: self._redraw())
        self._paths = {}                                # id(recording) -> its sprite paths for this part
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / TICKS_PER_SECOND))
        self.timer.timeout.connect(lambda: self.slider.setValue((self.slider.value() + 1) % (self.slider.maximum() + 1)))
        # the compare bar: which field, the other value, what changes
        self.compare_title = QLabel()
        self.compare_value = FieldSpin()
        self.compare_value.valueChanged.connect(lambda _value: self._compare())
        self.compare_note = QLabel()
        self.compare_note.setWordWrap(True)
        done = QPushButton("Done")
        done.setToolTip("Stop comparing")
        done.clicked.connect(self.stop_compare)
        self.compare_bar = QWidget()
        bar = QHBoxLayout(self.compare_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.compare_title)
        bar.addWidget(self.compare_value)
        bar.addWidget(self.compare_note, 1)
        bar.addWidget(done)
        self.compare_bar.hide()
        pictures = QHBoxLayout()
        for caption, picture in ((self.caption, self.picture), (self.caption_b, self.picture_b)):
            column = QVBoxLayout()
            column.addWidget(caption)
            column.addWidget(picture, 1)
            pictures.addLayout(column, 1)
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        controls.addWidget(self.path)
        controls.addWidget(self.reference)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.compare_bar)
        layout.addLayout(pictures, 1)
        layout.addLayout(controls)
        layout.addWidget(self.strip)
        runner.recording_changed.connect(lambda: self.refresh(again=True))
        self.refresh()

    @staticmethod
    def _picture():
        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setMinimumSize(PREVIEW_WIDTH // 2, PREVIEW_WIDTH * 7 // 20)
        # drawn at its own size: the picture never asks for more room than the layout gives it
        picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        picture.setStyleSheet("background: #101018; color: #C0C0C8;")
        return picture

    def shown_parts(self):
        return self.part_ids | {TARGET_PART} if self.reference.isChecked() else self.part_ids

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()                          # drawn at the picture's size: again at the new one

    def _redraw(self):
        self._frames = {}
        self._show(self.slider.value())

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

    def _fit(self, recording):
        """The part's box, and the target's too when it is shown: each fitted alone (the target's many
        points would trim the part's few)."""
        boxes = [recording.fit_view(parts=self.part_ids)]
        if self.reference.isChecked() and recording.last_drawing(0, TARGET_PART) is not None:
            boxes.append(recording.fit_view(parts={TARGET_PART}))
        return boxes

    def refresh(self, again=False):
        """A new lab recording (or none): frame the part on it again (again: the values changed, the
        compared recording is made again with them)."""
        self._frames, self._view, self._paths = {}, None, {}
        cast = self.runner.cast()
        body = cast.slots.get(cast.target, (None, None))[0]
        self.reference.setText(f"Target ({os.path.basename(body)})" if body else "Target")
        self.reference.setEnabled(bool(body))
        recording = self.runner.recording
        if again and self.compared is not None and recording is not None:
            self._compare()
            return
        self.slider.blockSignals(True)
        length = max(len(recording.ticks) if recording else 0, len(self.variant.ticks) if self.variant else 0)
        self.slider.setRange(0, max(0, length - 1))
        self.slider.blockSignals(False)
        self.play_button.setEnabled(recording is not None)
        if recording is None:
            self.play_button.setChecked(False)
            self.picture.setPixmap(QPixmap())
            self.picture.setText(self.runner.status.text() or "Recording...")
            self.frame_label.setText("")
            return
        recordings = [r for r in (recording, self.variant) if r is not None]
        if not any(set(tick.parts) & self.part_ids for r in recordings for tick in r.ticks):
            self.picture.setPixmap(QPixmap())
            self.picture.setText("This part draws nothing with these values.")
            return
        boxes = [box for r in recordings for box in self._fit(r)]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right, bottom = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        pad_x, pad_y = (right - left) * 0.06, (bottom - top) * 0.06
        self._view = (int(left - pad_x), int(top - pad_y), int(right - left + 2 * pad_x), int(bottom - top + 2 * pad_y))
        self._show(self.slider.value())

    def _draw(self, recording, tick, size):
        if tick >= len(recording.ticks):
            return None
        # the whole view in the picture; the target as last drawn when the effect hides it (Cure
        # redraws it itself, as its Overlay part)
        scale = min(size[0] / max(1, self._view[2]), size[1] / max(1, self._view[3]))
        under = None
        if self.reference.isChecked() and TARGET_PART not in recording.ticks[tick].parts:
            last = recording.last_drawing(tick, TARGET_PART)
            under = (last, {TARGET_PART}) if last is not None else None
        image, _gpu = recording.frame(tick, view=self._view, scale=scale, renderer=self.renderer(),
                                      parts=self.shown_parts(), under=under)
        height, width = image.shape[:2]
        pixmap = QPixmap.fromImage(QImage(image.tobytes(), width, height, width * 3,
                                          QImage.Format.Format_RGB888).copy())
        if self.path.isChecked():
            self._draw_paths(pixmap, recording, scale)
        return pixmap

    def _draw_paths(self, pixmap, recording, scale):
        """The part's sprite paths over the whole effect (fxdump.sprite_paths) on its picture."""
        if id(recording) not in self._paths:
            self._paths[id(recording)] = recording.sprite_paths(self.part_ids)
        x, y = self._view[0], self._view[1]
        point = lambda px, py: QPointF((px - x) * scale, (py - y) * scale)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(PATH_COLOUR, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for path in self._paths[id(recording)]:
            if len(path) > 1:
                painter.drawPolyline(QPolygonF([point(px, py) for _tick, px, py in path]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PATH_COLOUR)
        for path in self._paths[id(recording)]:
            painter.drawEllipse(point(path[0][1], path[0][2]), 1.8, 1.8)
        painter.end()

    def _show(self, tick):
        recording = self.runner.recording
        if recording is None or self._view is None or not recording.ticks:
            return
        tick = max(0, min(tick, self.slider.maximum()))
        size = (max(PREVIEW_WIDTH // 2, self.picture.width()), max(PREVIEW_WIDTH * 7 // 20, self.picture.height()))
        if size != self._size:
            self._frames, self._size = {}, size
        pairs = ((self.picture, recording, "a"),) + (((self.picture_b, self.variant, "b"),) if self.variant else ())
        for picture, shown, side in pairs:
            if (side, tick) not in self._frames:
                self._frames[side, tick] = self._draw(shown, tick, size)
            pixmap = self._frames[side, tick]
            if pixmap is None:
                picture.setPixmap(QPixmap())
                picture.setText("The effect has ended.")
            else:
                picture.setPixmap(pixmap)
        marker = self.markers().get(tick)
        self.frame_label.setText(f"tick {tick} / {self.slider.maximum()}" + (f" - {marker}" if marker else ""))

    # ------------------------------------------------------------------ compare
    def start_compare(self, field, current, other, record):
        """Show the part with `field` at `other` beside it at `current`; record(value) -> the lab
        recording with that value (None when it cannot be made)."""
        self.compared = (field, record)
        self.compare_title.setText(f"Compare {field['label']}: now {shown_value(field, current)}, with")
        self.compare_value.blockSignals(True)
        self.compare_value.set_field(field)
        self.compare_value.setRange(field["min"], field["max"])
        self.compare_value.setValue(other)
        self.compare_value.blockSignals(False)
        for widget in (self.compare_bar, self.picture_b, self.caption, self.caption_b, self.strip):
            widget.show()
        self._compare()

    def stop_compare(self):
        self.compared, self.variant = None, None
        for widget in (self.compare_bar, self.picture_b, self.caption, self.caption_b, self.strip):
            widget.hide()
        self.refresh()

    def _compare(self):
        """Record the compared value, mark what changes, show both."""
        field, record = self.compared
        other = self.compare_value.value()
        base = self.runner.recording
        current = dict(self.runner.cast().params).get(field["key"], field["default"])
        self.compare_title.setText(f"Compare {field['label']}: now {shown_value(field, current)}, with")
        self.caption.setText(f"Now: {field['label']} {shown_value(field, current)}")
        self.caption_b.setText(f"With {field['label']} {shown_value(field, other)}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.variant = record(other) if base is not None else None
        finally:
            QApplication.restoreOverrideCursor()
        if base is None or self.variant is None:
            self.compare_note.setText("The effect recorder could not record it.")
            self.variant = None
            self.refresh()
            return
        changes, _lengths = differences(base, self.variant, self.part_names)
        mine = [entry for entry in changes if entry["part"] in self.part_ids]
        others = [entry for entry in changes if entry["part"] not in self.part_ids and entry["part"] != TARGET_PART]
        self.strip.set_ticks({t for e in mine for t in e["ticks"]}, {t for e in others for t in e["ticks"]},
                             max(len(base.ticks), len(self.variant.ticks)))
        if not changes:
            note = "Nothing changes."
        else:
            note = " · ".join(f"{e['name']} ticks {tick_runs(e['ticks'])}" for e in mine) or "This part does not change"
            if others:
                note += (" - also " + ", ".join(e["name"] for e in others)
                         + " (amber: the random numbers they draw shift)")
        if len(base.ticks) != len(self.variant.ticks):
            note += f" - lasts {len(self.variant.ticks)} ticks instead of {len(base.ticks)}"
        self.compare_note.setText(note)
        self.refresh()
        first = min((t for e in mine for t in e["ticks"]), default=None)
        if first is not None:
            self.slider.setValue(first)


UNITS = {"angle": (360 / 4096, 2, "", "°"),          # unit -> (shown per raw unit, decimals, prefix, suffix)
         "scale": (1 / 4096, 3, "x ", "")}
FIELD_WIDTH = 110                   # a field's value box (pixels): its raw value / hint beside it


def shown_value(field, raw):
    """A field's raw value as an editor shows it (fx_params.h Unit: an angle in degrees, a size
    as x 1 = its own)."""
    unit = UNITS.get(field.get("unit"))
    if unit is None:
        return str(raw)
    factor, decimals, prefix, suffix = unit
    return f"{prefix}{raw * factor:.{decimals}f}{suffix}"


class FieldSpin(QWidget):
    """A field's value: a narrow box in the field's unit (fx_params.h Unit: degrees for an angle,
    x for a size; the raw value greyed beside it) - the QSpinBox calls a part tab makes, in raw
    values (value, setValue, setRange, valueChanged). hint(): another grey note beside it."""
    valueChanged = pyqtSignal(int)

    def __init__(self, field=None):
        super().__init__()
        self.box = QDoubleSpinBox()
        self.box.setKeyboardTracking(False)
        self.box.setFixedWidth(FIELD_WIDTH)
        self.box.valueChanged.connect(self._edited)
        self.raw_label = QLabel()
        self.raw_label.setStyleSheet("color: gray;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.box)
        layout.addWidget(self.raw_label, 1)
        self._raw, self._range, self._hint, self.factor = 0, (0, 0), "", 1
        self.set_field(field or {})

    def set_field(self, field):
        self.field = field
        self.factor, decimals, prefix, suffix = UNITS.get(field.get("unit"), (1, 0, "", ""))
        self.box.blockSignals(True)
        self.box.setDecimals(decimals)
        self.box.setPrefix(prefix)
        self.box.setSuffix(suffix)
        self.box.setSingleStep(1 if self.factor == 1 or field.get("unit") == "angle" else 0.05)
        self.box.blockSignals(False)
        self.setRange(*self._range)
        self.setValue(self._raw)

    def value(self):
        return self._raw

    def setRange(self, low, high):
        self._range = (low, high)
        self.box.blockSignals(True)
        self.box.setRange(low * self.factor, high * self.factor)
        self.box.blockSignals(False)

    def setValue(self, raw):
        raw = max(self._range[0], min(self._range[1], int(raw)))
        changed = raw != self._raw
        self._raw = raw
        self.box.blockSignals(True)
        self.box.setValue(raw * self.factor)
        self.box.blockSignals(False)
        self._note()
        if changed:
            self.valueChanged.emit(raw)

    def setToolTip(self, text):
        super().setToolTip(text)
        self.box.setToolTip(text)

    def hint(self, text):
        self._hint = text
        self._note()

    def _note(self):
        raw = f"raw {self._raw}" if self.factor != 1 else ""
        self.raw_label.setText("  ".join(filter(None, (raw, self._hint))))

    def _edited(self, shown):
        # to the nearest raw value, the box showing it exactly
        self.setValue(round(shown / self.factor))


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
            spin = SequenceField(runner, self.part_names) if sequence else FieldSpin(field)
            spin.setRange(field["min"], field["max"])
            spin.setValue(values.get(field["key"], field["default"]))
            game = f"0x{field['default']:X}" if sequence else shown_value(field, field["default"])
            spin.setToolTip(f"{field['doc']}\nThe game's value: {game}".strip())
            spin.valueChanged.connect(lambda value, key=field["key"]: self._changed(key, value))
            label = QLabel(field["label"])
            label.setToolTip(spin.toolTip())
            probe = QToolButton()
            probe.setText("?")
            probe.setToolTip("What does it change? Shows the part with another value of this field beside "
                             "it, the ticks that change marked under the slider")
            probe.setEnabled(not sequence)
            probe.clicked.connect(lambda _checked, key=field["key"]: self.probe(key))
            row = QHBoxLayout()
            row.addWidget(spin, 1)
            row.addWidget(probe)
            self.spins[field["key"]], self.labels[field["key"]] = spin, label
            form.addRow(label, row)
            self._mark(field["key"])
        self._ratios()
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
        scroll.setMinimumWidth(380)
        part_ids = {part["id"]} if part["id"] else set(effect_parts)      # 0: draws nothing, the whole effect
        self.preview = PartPreview(runner, part_ids, renderer, markers=self.markers, part_names=self.part_names)
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
        """What `key` changes: the preview compares the part at its value with another - the game's
        when it is not at it, else a clearly different one (twice it, or 1 for 0) - recorded with
        the effect's other values as they are."""
        field = next(field for field in self.fields if field["key"] == key)
        value = self.spins[key].value()
        if value != field["default"]:
            other = field["default"]
        else:
            other = value * 2 if value else 1
            other = max(field["min"], min(field["max"], other))
            if other == value:
                other = max(field["min"], min(field["max"], value - 1 if value > field["min"] else value + 1))

        def record(compared):
            return self.runner.record_with(dict(self.runner.cast().params) | {key: compared})
        self.preview.start_compare(field, value, other, record)

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

    def _ratios(self):
        """A fraction's value (a "num" field and its "den": Cure's ring radius x / ) greyed beside
        its divisor."""
        for key, spin in self.spins.items():
            numerator = key[:-len("den")] + "num" if key.endswith(".den") else None
            if numerator in self.spins and spin.value():
                spin.hint(f"= x {self.spins[numerator].value() / spin.value():.2f}")

    def _changed(self, key, value):
        self._mark(key)
        self._ratios()
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
        self._ratios()
