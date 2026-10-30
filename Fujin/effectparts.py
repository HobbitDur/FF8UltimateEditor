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

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QSlider, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from Fujin.partimages import SHEET_HEIGHT, PartImages
from Fujin.partlife import PartLife
from Fujin.battleevents import HEAL_COLOUR, HIT_COLOUR, NUMBER_TICKS, SoundField, number_state, sound_archive_id
from FF8GameData.psxgpu.gpu import SUBPIXEL
from FF8GameData.psxgpu.fxdiff import differences, tick_runs
from Fujin.partsequences import PartSequences, SequenceField
from FF8GameData.psxgpu.spritesequence import exe_sequences
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

    def __init__(self, runner, part_ids, renderer, markers=lambda: {}, part_names=None, sounds=None, heals=False):
        super().__init__()
        self.runner, self.part_ids, self.renderer, self.markers = runner, part_ids, renderer, markers
        self.part_names = part_names or {}
        self.sounds, self.heals = sounds, heals         # Fujin's Sound tab plays; a result's number is a heal
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
        self.slider.valueChanged.connect(self._play_sounds)
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
        # the compare bar: which field or group, its other values, what changes
        self.compare_title = QLabel()
        self.compare_spins = {}                         # key -> its other value (FieldSpin)
        self.compare_values = QHBoxLayout()
        self.compare_note = QLabel()
        self.compare_note.setWordWrap(True)
        done = QPushButton("Done")
        done.setToolTip("Stop comparing")
        done.clicked.connect(self.stop_compare)
        self.compare_bar = QWidget()
        # long texts wrap: the bar never widens the window
        for label in (self.compare_title, self.compare_note, self.caption, self.caption_b):
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top = QHBoxLayout()
        top.addWidget(self.compare_title, 1)
        top.addWidget(done)
        values = QHBoxLayout()
        values.addLayout(self.compare_values)
        values.addStretch(1)
        bar = QVBoxLayout(self.compare_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addLayout(top)
        bar.addLayout(values)
        bar.addWidget(self.compare_note)
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
        # a method, not a lambda: Qt drops the connection with the preview (a part tab is rebuilt
        # for another effect, the runner stays)
        runner.recording_changed.connect(self._recording_changed)
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

    def _recording_changed(self):
        self.refresh(again=True)

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
        # where the battle's numbers rise (up to 21 pixels over the target, 12 high)
        for start, tick in enumerate(recording.ticks):
            drawn = recording.last_drawing(start, TARGET_PART) if tick.results else None
            box = recording.part_box(drawn, {TARGET_PART}) if drawn is not None else None
            if box is not None:
                middle = (box[0] + box[2]) / 2
                boxes.append((middle - 20 * SUBPIXEL, box[1] - 34 * SUBPIXEL, 40 * SUBPIXEL, 34 * SUBPIXEL))
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
        self._draw_numbers(pixmap, recording, tick, scale)
        return pixmap

    def _draw_numbers(self, pixmap, recording, tick, scale):
        """The battle's number of each action result given in the last 10 ticks, above its target as
        the game moves it (Fujin.battleevents) - a stand-in: the amount comes from the battle."""
        shown = [(start, result) for start in range(max(0, tick - NUMBER_TICKS + 1), tick + 1)
                 for result in recording.ticks[start].results]
        if not shown:
            return
        painter = QPainter(pixmap)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(8, round(12 * SUBPIXEL * scale)))
        painter.setFont(font)
        for start, (_slot, _amount, _flags, hit) in shown:
            heal = self.heals or bool(hit & 1)
            drawn = recording.last_drawing(start, TARGET_PART)
            box = recording.part_box(drawn, {TARGET_PART}) if drawn is not None else None
            state = number_state(tick - start, heal)
            if box is None or state is None:
                continue
            offset, opacity, dark = state
            red, green, blue = (HEAL_COLOUR if heal else HIT_COLOUR)
            colour = QColor(*(min(255, round(2 * c * (1 - dark))) for c in (red, green, blue)))
            colour.setAlphaF(opacity)
            x = ((box[0] + box[2]) / 2 - self._view[0]) * scale
            y = (box[1] + offset * SUBPIXEL - self._view[1]) * scale
            painter.setPen(colour)
            painter.drawText(QRectF(x - 200, y - font.pixelSize(), 400, font.pixelSize() * 1.2),
                             Qt.AlignmentFlag.AlignCenter, "+HP" if heal else "HP")
        painter.end()

    def _play_sounds(self, tick):
        """While playing: the sounds the effect plays at this tick (Fujin's Sound tab plays them)."""
        recording = self.runner.recording
        if (self.sounds is None or not self.timer.isActive() or recording is None
                or not 0 <= tick < len(recording.ticks) or not self.runner.exe_path()):
            return
        for address in recording.ticks[tick].sounds:
            archive = sound_archive_id(self.runner.exe_path(), address)
            if archive is not None and self.sounds._can_play(archive):
                self.sounds.play(archive)

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
        # what the effect asks the battle at this tick, as recorded; a recording without these lines
        # (an older recorder): the part's tick fields (counted from its own start, not the slider's)
        if any(t.sounds or t.results for t in recording.ticks):
            asked = recording.ticks[tick] if tick < len(recording.ticks) else None
            marker = ", ".join((["♪ sound"] if asked and asked.sounds else []) +
                               (["HP number shows"] if asked and asked.results else []))
        else:
            marker = self.markers().get(tick)
        self.frame_label.setText(f"tick {tick} / {self.slider.maximum()}" + (f" - {marker}" if marker else ""))

    # ------------------------------------------------------------------ compare
    @property
    def compare_value(self):
        """The compared field's other value (a group's first one)."""
        return next(iter(self.compare_spins.values()))

    def start_compare(self, label, fields, others, record):
        """Show the part with `fields` (one field, or a group's: values edited together, `label`)
        at `others` ({key: value}) beside it as it is; record({key: value}) -> the lab recording
        with them (None when it cannot be made)."""
        self.compared = (label, fields, record)
        while self.compare_values.count():
            item = self.compare_values.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.compare_spins = {}
        for field in fields:
            if len(fields) > 1:
                self.compare_values.addWidget(QLabel(field["label"]))
            spin = FieldSpin(field)
            spin.setRange(field["min"], field["max"])
            spin.setValue(others[field["key"]])
            spin.setToolTip(field["doc"])
            spin.valueChanged.connect(lambda _value: self._compare())
            self.compare_values.addWidget(spin)
            self.compare_spins[field["key"]] = spin
        for widget in (self.compare_bar, self.picture_b, self.caption, self.caption_b, self.strip):
            widget.show()
        self._compare()

    @staticmethod
    def _values_text(fields, values):
        if len(fields) == 1:
            return shown_value(fields[0], values[fields[0]["key"]])
        return ", ".join(f"{field['label']} {shown_value(field, values[field['key']])}" for field in fields)

    def stop_compare(self):
        self.compared, self.variant = None, None
        for widget in (self.compare_bar, self.picture_b, self.caption, self.caption_b, self.strip):
            widget.hide()
        self.refresh()

    def _compare(self):
        """Record the compared values, mark what changes, show both."""
        label, fields, record = self.compared
        others = {key: spin.value() for key, spin in self.compare_spins.items()}
        base = self.runner.recording
        params = dict(self.runner.cast().params)
        currents = {field["key"]: params.get(field["key"], field["default"]) for field in fields}
        self.compare_title.setText(f"Compare {label}: now {self._values_text(fields, currents)}, with")
        self.caption.setText(f"Now: {label} {self._values_text(fields, currents)}")
        self.caption_b.setText(f"With {label} {self._values_text(fields, others)}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.variant = record(others) if base is not None else None
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
                         + " (amber: they hang on this part, or the random numbers they draw shift)")
        if len(base.ticks) != len(self.variant.ticks):
            note += f" - lasts {len(self.variant.ticks)} ticks instead of {len(base.ticks)}"
        self.compare_note.setText(note)
        self.refresh()
        first = min((t for e in mine for t in e["ticks"]), default=None)
        if first is not None:
            self.slider.setValue(first)


def _in_group(key, group_key):
    """Whether field `key` is one of a group's (FFNx fx_params.h Group: a sub-structure's fields)."""
    return key == group_key or key.startswith(group_key + ".") or key.startswith(group_key + "[")


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

    def limits(self):
        """(lowest, highest) raw value."""
        return self._range

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
    frames its sequence plays. The values edited together (a group: FFNx fx_params.h Group, one
    sub-structure - Cure's ring radius: times, divided by, at most) share a box; a group's "?",
    or an ungrouped field's, records the effect with other values and shows what draws
    differently (part_names: {part id: title})."""
    value_changed = pyqtSignal(str, int)      # key, new value

    def __init__(self, part, fields, values, runner, renderer, effect_parts=frozenset(), locate=None,
                 part_names=None, groups=(), sounds=None, spawner=None):
        super().__init__()
        self.part, self.fields, self.runner = part, fields, runner
        self.spawner = spawner                          # (part id, title) whose ticks its windows count
        self.sounds = sounds                            # Fujin's Sound tab: plays audio.dat entries
        self.part_names = part_names or {}
        self.groups = {group["key"]: group for group in groups if any(_in_group(f["key"], group["key"]) for f in fields)}
        self.spins, self.labels = {}, {}
        doc = QLabel(part["doc"] + ("" if part["id"] else
                                    ". It draws nothing: the preview shows the whole effect, its ticks marked."))
        doc.setWordWrap(True)
        form = QFormLayout()
        boxes = {}                                      # group key -> its form
        for field in fields:
            sequence = field.get("type") in ("seq", "sound")      # an address: no compare
            spin = (SequenceField(runner, self.part_names) if field.get("type") == "seq" else
                    SoundField(runner, sounds) if field.get("type") == "sound" else FieldSpin(field))
            spin.setRange(field["min"], field["max"])
            spin.setValue(values.get(field["key"], field["default"]))
            game = f"0x{field['default']:X}" if sequence else shown_value(field, field["default"])
            spin.setToolTip(f"{field['doc']}\nThe game's value: {game}".strip())
            spin.valueChanged.connect(lambda value, key=field["key"]: self._changed(key, value))
            label = QLabel(field["label"])
            label.setToolTip(spin.toolTip())
            self.spins[field["key"]], self.labels[field["key"]] = spin, label
            group = self.group_of(field["key"])
            if group is None:
                row = QHBoxLayout()
                row.addWidget(spin, 1)
                row.addWidget(self._probe_button(field["key"], "this field", enabled=not sequence))
                form.addRow(label, row)
            else:
                if group["key"] not in boxes:
                    boxes[group["key"]] = self._group_box(group, form)
                boxes[group["key"]].addRow(label, spin)
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
        # a result's number is a heal when the part gives HP (Cure's emitter: Heal tick)
        heals = any(f["key"].endswith("heal_tick") for f in fields)
        self.preview = PartPreview(runner, part_ids, renderer, markers=self.markers, part_names=self.part_names,
                                   sounds=sounds, heals=heals)
        self.images = PartImages(runner, part_ids, self.named_images, locate, part["title"])
        self.sequences = PartSequences(runner, part_ids, self.part_names)
        self.sequences.picked.connect(self.images.select)
        self.preview.slider.valueChanged.connect(self.images.set_tick)
        self.preview.slider.valueChanged.connect(self.sequences.set_tick)
        self.below = QTabWidget()
        self.below.addTab(self.images, "Images")
        self.below.addTab(self.sequences, "Sprite sequences")
        self.life = PartLife(self.values())
        if self.life.has_content():                     # spawn windows, a glint's style
            self.below.addTab(self.life, "Life")
        self.below.setFixedHeight(SHEET_HEIGHT + 150)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.below)
        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addLayout(right, 1)
        runner.recording_changed.connect(self._update_limits)      # the exe may come after the tab
        self._update_limits()

    def group_of(self, key):
        """The group (values edited together) field `key` belongs to, or None."""
        groups = [group for group in self.groups.values() if _in_group(key, group["key"])]
        return max(groups, key=lambda group: len(group["key"]), default=None)

    def group_fields(self, group_key):
        return [field for field in self.fields if self.group_of(field["key"]) is self.groups[group_key]]

    def _probe_button(self, key, what, enabled=True):
        probe = QToolButton()
        probe.setText("?")
        probe.setToolTip(f"What does it change? Shows the part with other values of {what} beside it, the "
                         "ticks that change marked under the slider")
        probe.setEnabled(enabled)
        probe.clicked.connect(lambda _checked: self.probe(key))
        return probe

    def _group_box(self, group, form):
        """A group's box in the form: its doc and "?" on top, its fields under (their form)."""
        box = QGroupBox(group["label"])
        box.setToolTip(group["doc"])
        doc = QLabel(group["doc"])
        doc.setWordWrap(True)
        doc.setStyleSheet("color: gray;")
        top = QHBoxLayout()
        top.addWidget(doc, 1)
        top.addWidget(self._probe_button(group["key"], "these values together"), 0, Qt.AlignmentFlag.AlignTop)
        fields = QFormLayout()
        layout = QVBoxLayout(box)
        layout.addLayout(top)
        layout.addLayout(fields)
        form.addRow(box)
        return fields

    def _title(self, key):
        """A field's name with its group's (the Sequences tab's notes: "Ring Ending flipbook")."""
        group = self.group_of(key)
        return group["label"] if group else next(field["label"] for field in self.fields if field["key"] == key)

    def frame_limits(self):
        """{sequence address: (Frames field label, last frame played)}: a "frames" field and the
        "seq" field beside it (ring.ending.frames - ring.ending.seq, sparkle.frames - sparkle.seq)."""
        limits = {}
        for field in self.fields:
            key = field["key"]
            sequence = key[:-len("frames")] + "seq" if key.endswith("frames") else None
            if sequence in self.spins:
                limits[self.spins[sequence].value()] = (f"{self.part['title']} {self._title(key)}",
                                                         self.spins[key].value())
        return limits

    def _update_limits(self):
        """A frames field goes no further than its sequence's last frame (FFNx plays no more:
        fx_params.h last_frame); the Sequences tab marks the frames played."""
        sequences = exe_sequences(self.runner.exe_path()) if self.runner.exe_path() else {}
        for field in self.fields:
            key = field["key"]
            owner = self.spins.get(key[:-len("frames")] + "seq") if key.endswith("frames") else None
            sequence = sequences.get(owner.value()) if owner is not None else None
            if sequence is not None and sequence.frames:
                last = min(field["max"], len(sequence.frames) - 1)
                spin = self.spins[key]
                spin.setRange(field["min"], last)
                spin.hint(f"last frame {last}")
                if spin.value() > last:
                    spin.setValue(last)
        self.sequences.set_limits(self.frame_limits())
        self._spawn_hints()

    def _spawn_hints(self):
        """A window of the spawner's ticks (Cure's sparkles, motes, glints: the ring's) past the
        spawner's life does nothing: its last tick, from the recording, beside each window's end."""
        recording = self.runner.recording
        if self.spawner is None or recording is None:
            return
        drawn = [index for index, tick in enumerate(recording.ticks) if self.spawner[0] in tick.parts]
        if not drawn:
            return
        last = drawn[-1] - drawn[0]
        for key, spin in self.spins.items():
            if key.endswith("window.last") and isinstance(spin, FieldSpin):
                spin.hint(f"{self.spawner[1]} lives to tick {last}" + (": later ones do nothing" if spin.value() > last else ""))

    def probe(self, key):
        """What a field or a group (values edited together; a grouped field probes its group)
        changes: the preview compares the part as it is with other values - the game's when they
        are not at them, else clearly different ones (the first value twice, or 1 for 0, and a
        "max" twice: Cure's ring radius x 4, at most 2048) - recorded with the effect's other
        values as they are."""
        group = self.groups.get(key) or self.group_of(key)
        fields = self.group_fields(group["key"]) if group else [f for f in self.fields if f["key"] == key]
        # the form's limits (a frames field: its sequence's last frame), not only the port's
        fields = [dict(field, min=self.spins[field["key"]].limits()[0], max=self.spins[field["key"]].limits()[1])
                  if isinstance(self.spins[field["key"]], FieldSpin) else field for field in fields]
        values = {field["key"]: self.spins[field["key"]].value() for field in fields}
        clamp = lambda field, value: max(field["min"], min(field["max"], value))
        if any(values[field["key"]] != field["default"] for field in fields):
            others = {field["key"]: field["default"] for field in fields}
        else:
            others = dict(values)
            first = next(field for field in fields if field.get("type") not in ("seq", "sound"))
            for field in fields:
                if field is first or field["key"].endswith(".max") and field.get("type") not in ("seq", "sound"):
                    value = values[field["key"]]
                    others[field["key"]] = clamp(field, value * 2 if value else 1)
            if others == values:
                value = values[first["key"]]
                others[first["key"]] = clamp(first, value - 1 if value > first["min"] else value + 1)

        def record(compared):
            return self.runner.record_with(dict(self.runner.cast().params) | compared)
        label = group["label"] if group else fields[0]["label"]
        self.preview.start_compare(label, [f for f in fields if f.get("type") not in ("seq", "sound")], others, record)

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
                images.append((self._title(key), value("tex_x"), value("tex_y"),
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
        # a climb speed (Cure's ring: target height + above every N ticks) over the ring's life (its
        # ending flipbook's start + frames): where it ends, about
        value = lambda name: self.spins[name].value() if name in self.spins else None
        every, start, frames = value("ring.climb.ticks"), value("ring.ending.tick"), value("ring.ending.frames")
        if every and start is not None and frames is not None:
            above = value("ring.climb.above")
            self.spins["ring.climb.ticks"].hint(f"ends ~ {(start + frames + 1) / every:.2f} x (height + {above}) up")
        # a fading brightness (Cure's ground glow: grey = start - tick x fade, bytes): where it
        # reaches its lowest, and whether it wraps and comes back within its duration
        ticks, start, fade = value("glow.brightness.ticks"), value("glow.brightness.start"), value("glow.brightness.fade")
        if ticks is not None and start is not None and fade is not None:
            grey = [(start - ((tick * fade) & 0xFF)) & 0xFF for tick in range(max(1, ticks))]
            back = next((tick for tick in range(1, len(grey)) if grey[tick] > grey[tick - 1]), None)
            self.spins["glow.brightness.ticks"].hint(
                f"comes back at tick {back}: grey wraps {grey[back - 1]} -> {grey[back]}" if back is not None else
                f"grey {grey[-1]} at its last tick ({len(grey) - 1})")

    def values(self):
        """{key: value} of the tab's fields as they are."""
        return {key: spin.value() for key, spin in self.spins.items()}

    def _changed(self, key, value):
        self._mark(key)
        self._ratios()
        self.life.set_values(self.values())
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
        self.life.set_values(self.values())
