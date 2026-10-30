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

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QSlider, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from Fujin.partimages import SHEET_HEIGHT, PartImages
from Fujin.partlife import PartLife
from Fujin.partgeometry import GeometryView, geometry
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


_FOLDED = {}                        # Collapsible title -> folded: one choice for every part tab (this session)
PANEL = {"width": 300}              # a part tab's parameter panel width (pixels), the same in every tab


class Collapsible(QWidget):
    """A title to click and what it folds away (the part tabs' change rows, their images and
    sequences), folded or not in every part tab at once (_FOLDED)."""
    _all = []

    def __init__(self, title, content):
        super().__init__()
        self.title, self.content = title, content
        self.header = QToolButton()
        self.header.setAutoRaise(True)
        self.header.clicked.connect(lambda: self.fold(not self.is_folded()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(content)
        Collapsible._all.append(self)
        self.destroyed.connect(lambda _object=None, me=self: Collapsible._all.remove(me) if me in Collapsible._all else None)
        self.fold(_FOLDED.get(title, False))

    def fold(self, folded):
        _FOLDED[self.title] = folded
        self.content.setHidden(folded)
        self.header.setText(("▸ " if folded else "▾ ") + self.title)
        self.header.setToolTip(f"Show {self.title.lower()}" if folded else f"Fold {self.title.lower()} away to give the preview more room")
        for other in Collapsible._all:
            if other is not self and other.title == self.title and other.content.isHidden() != folded:
                other.fold(folded)

    def is_folded(self):
        return self.content.isHidden()


class ChangeRows(QWidget):
    """Under a compared preview's slider, part of it: one row per part, a cell lit at each tick it
    draws differently with the other values (the tab's own parts red, the others amber, a part that
    never changes greyed "no change"), its cells under the slider's own tick positions, the slider's
    tick a line across them; a click or a drag moves the slider. mine: the ticks the tab's parts
    change at. A row may give its own colour (name, ticks, own, colour): the Emitter's timeline,
    when each part draws; `verb` says what a lit cell means in the tooltip."""
    ROW = 13

    def __init__(self, slider):
        super().__init__()
        self.slider = slider
        self.rows, self.mine = [], set()                # rows: [(name, ticks, own part[, colour])]
        self.verb = ("draws differently", "is the same", "no change")
        self.setMouseTracking(True)
        slider.valueChanged.connect(lambda _value: self.update())
        slider.rangeChanged.connect(lambda _low, _high: self.update())

    def set_rows(self, rows):
        self.rows = rows
        self.mine = {tick for _name, ticks, own, *_colour in rows if own for tick in ticks}
        self.setFixedHeight(max(1, len(rows)) * self.ROW + 2)
        self.update()

    def _track(self):
        """(x of tick 0, pixels per tick) along the slider's groove, in this widget."""
        from PyQt6.QtWidgets import QStyle, QStyleOptionSlider
        option = QStyleOptionSlider()
        self.slider.initStyleOption(option)
        handle = self.slider.style().pixelMetric(QStyle.PixelMetric.PM_SliderLength, option, self.slider)
        left = self.mapFromGlobal(self.slider.mapToGlobal(QPoint(0, 0))).x() + handle / 2
        span = max(1, self.slider.width() - handle)
        return left, span / max(1, self.slider.maximum())

    def _tick_at(self, x):
        left, step = self._track()
        return max(0, min(self.slider.maximum(), round((x - left) / step)))

    def mousePressEvent(self, event):
        self.slider.setValue(self._tick_at(event.position().x()))

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.slider.setValue(self._tick_at(event.position().x()))
        row = int(event.position().y() // self.ROW)
        if 0 <= row < len(self.rows):
            name, ticks = self.rows[row][:2]
            tick = self._tick_at(event.position().x())
            self.setToolTip(f"tick {tick}: {name} " + (self.verb[0] if tick in ticks else self.verb[1])
                            if ticks else f"{name}: {self.verb[2]}")

    def paintEvent(self, event):
        painter = QPainter(self)
        left, step = self._track()
        names = int(left - step / 2 - 6)
        font = painter.font()
        font.setPixelSize(self.ROW - 2)
        for index, (name, ticks, own, *given) in enumerate(self.rows):
            y = index * self.ROW
            font.setBold(own)
            painter.setFont(font)
            painter.setPen(QColor(150, 150, 155) if not ticks else self.palette().windowText().color())
            painter.drawText(QRectF(0, y, max(0, names), self.ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, max(0, names)))
            track = QRectF(left - step / 2, y + 2, step * (self.slider.maximum() + 1), self.ROW - 4)
            painter.fillRect(track, QColor(60, 60, 66))
            if not ticks:
                small = QFont(font)
                small.setBold(False)
                small.setPixelSize(self.ROW - 3)
                painter.setFont(small)
                painter.setPen(QColor(170, 170, 175))
                painter.drawText(QRectF(track.left() + 4, y, track.width(), self.ROW),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.verb[2])
            colour = given[0] if given else QColor(235, 60, 60) if own else QColor(230, 170, 40)
            for tick in ticks:
                painter.fillRect(QRectF(left + (tick - 0.5) * step, y + 2, max(1.0, step - 1), self.ROW - 4), colour)
        x = left + self.slider.value() * step
        painter.setPen(QPen(QColor(90, 160, 255), 2))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))


class PartPreview(QWidget):
    """One part of the lab recording, alone (or with the target as a reference, as last drawn when
    the effect hides it), framed on where it goes, playable; markers: {tick: what happens then}
    shown under the picture. Compare (a field's "?"): the same part with another value of one
    field, beside it, the ticks that change marked under the slider."""
    reference_toggled = pyqtSignal(bool)

    def __init__(self, runner, part_ids, renderer, markers=lambda: {}, part_names=None, sounds=None, heals=False,
                 timeline=False):
        super().__init__()
        self.runner, self.part_ids, self.renderer, self.markers = runner, part_ids, renderer, markers
        self.part_names = part_names or {}
        self.sounds, self.heals = sounds, heals         # Fujin's Sound tab plays; a result's number is a heal
        self.highlight = False                          # a group of the tab hovered: the paths stand out
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
        self.strip = ChangeRows(self.slider)
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
        done = QPushButton("Done")
        done.setToolTip("Stop comparing")
        done.clicked.connect(self.stop_compare)
        self.compare_bar = QWidget()
        # one line each, cut at the edge (no word wrap: its height-for-width made the tab ask far more
        # height than it uses), the bar never widening the window; the whole text as a tooltip
        for label in (self.compare_title, self.compare_note, self.caption, self.caption_b):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        # two lines: what is compared and the other values, then what changes
        top = QHBoxLayout()
        top.addWidget(self.compare_title, 1)
        top.addLayout(self.compare_values)
        top.addWidget(done)
        bar = QVBoxLayout(self.compare_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        bar.addLayout(top)
        bar.addWidget(self.compare_note)
        self.compare_bar.hide()
        pictures = QHBoxLayout()
        # a column per picture, the compared one hidden when not comparing (not keeping half the width)
        self.columns = []
        for caption, picture in ((self.caption, self.picture), (self.caption_b, self.picture_b)):
            column_widget = QWidget()
            column = QVBoxLayout(column_widget)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(caption)
            column.addWidget(picture, 1)
            pictures.addWidget(column_widget, 1)
            self.columns.append(column_widget)
        self.columns[1].hide()
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
        self.changes = Collapsible("What changes, part by part", self.strip)
        self.changes.hide()
        layout.addWidget(self.changes)
        # the whole effect's timeline (a part drawing nothing: the Emitter): when each part draws,
        # when the sound plays and the HP number shows, under the slider as the change rows
        self.timeline = ChangeRows(self.slider) if timeline else None
        if self.timeline is not None:
            self.timeline.verb = ("draws", "draws nothing", "nothing")
            self.timeline_fold = Collapsible("Timeline: when each part draws", self.timeline)
            layout.addWidget(self.timeline_fold)
        # the pictures take what room is left (their preferred size is no minimum: the tab fits 1080p)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.setMinimumHeight(PREVIEW_WIDTH * 7 // 20 + 40)
        # a method, not a lambda: Qt drops the connection with the preview (a part tab is rebuilt
        # for another effect, the runner stays)
        runner.recording_changed.connect(self._recording_changed)
        self.refresh()
        self._fill_timeline()

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
        self._fill_timeline()

    TIMELINE_COLOURS = [QColor(70, 160, 230), QColor(60, 190, 150), QColor(170, 120, 230), QColor(230, 140, 80),
                        QColor(220, 90, 150), QColor(150, 190, 70), QColor(90, 200, 220), QColor(200, 180, 60)]

    def _fill_timeline(self):
        """The timeline's rows from the lab recording: each part's drawing ticks, the sounds, the
        battle's numbers (10 ticks each)."""
        recording = self.runner.recording
        if self.timeline is None or recording is None:
            return
        rows = []
        for index, part in enumerate(sorted(self.part_ids)):
            ticks = {tick for tick, drawn in enumerate(recording.ticks) if part in drawn.parts}
            rows.append((self.part_names.get(part, f"part {part}"), ticks, False,
                         self.TIMELINE_COLOURS[index % len(self.TIMELINE_COLOURS)]))
        rows.append(("♪ Sound", {tick for tick, drawn in enumerate(recording.ticks) if drawn.sounds}, False,
                     QColor(240, 240, 240)))
        shown = {start + age for start, drawn in enumerate(recording.ticks) if drawn.results for age in range(NUMBER_TICKS)}
        rows.append(("HP number", {tick for tick in shown if tick < len(recording.ticks)}, False, QColor(110, 210, 110)))
        self.timeline.set_rows(rows)

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

    def set_highlight(self, on):
        if on != self.highlight:
            self.highlight = on
            self._redraw()

    def _draw_paths(self, pixmap, recording, scale):
        """The part's sprite paths over the whole effect (fxdump.sprite_paths) on its picture."""
        if id(recording) not in self._paths:
            self._paths[id(recording)] = recording.sprite_paths(self.part_ids)
        x, y = self._view[0], self._view[1]
        point = lambda px, py: QPointF((px - x) * scale, (py - y) * scale)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 220, 60) if self.highlight else PATH_COLOUR, 2 if self.highlight else 1)
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
        for widget in (self.compare_bar, self.columns[1], self.picture_b, self.caption, self.caption_b, self.changes):
            widget.show()
        self._compare()

    @staticmethod
    def _values_text(fields, values):
        if len(fields) == 1:
            return shown_value(fields[0], values[fields[0]["key"]])
        return ", ".join(f"{field['label']} {shown_value(field, values[field['key']])}" for field in fields)

    def stop_compare(self):
        self.compared, self.variant = None, None
        for widget in (self.compare_bar, self.columns[1], self.picture_b, self.caption, self.caption_b, self.changes):
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
        # a row per part either recording draws (the target only when it changes), in part order
        changed = {entry["part"]: entry["ticks"] for entry in changes}
        drawn = {part for recording in (base, self.variant) for tick in recording.ticks for part in tick.parts}
        shown = sorted(part for part in drawn | set(changed) if part != TARGET_PART or part in changed)
        self.strip.set_rows([(self.part_names.get(part, f"part {part}"), set(changed.get(part, ())),
                              part in self.part_ids) for part in shown])
        if not changes:
            note = "Nothing changes."
        else:
            note = " · ".join(f"{e['name']} ticks {tick_runs(e['ticks'])}" for e in mine) or "This part does not change"
            if others:
                note += (" - also " + ", ".join(e["name"] for e in others)
                         + " (amber rows: they hang on this part, or the random numbers they draw shift)")
        if len(base.ticks) != len(self.variant.ticks):
            note += f" - lasts {len(self.variant.ticks)} ticks instead of {len(base.ticks)}"
        self.compare_note.setText(note)
        self.compare_note.setToolTip(note)
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


class RangeGlyph(QWidget):
    """A group's random ranges drawn: per axis, its [min, max] lit on the field's span with 0
    marked; an angle's range as an arc of a circle (0 at the top, turning clockwise)."""
    ROW = 12

    def __init__(self, pairs):
        super().__init__()
        self.pairs = pairs                              # [(name, min spin, max spin, min field)]
        angles = all(field.get("unit") == "angle" for _name, _low, _high, field in pairs)
        self.angles = angles
        self.setFixedHeight(34 if angles else len(pairs) * self.ROW + 4)
        self.setToolTip("The ranges these values roll in: min to max, lit" + ("" if angles else ", 0 marked"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.angles:
            _name, low, high, _field = self.pairs[0]
            box = QRectF(4, 2, 30, 30)
            painter.setPen(QPen(QColor(110, 110, 115), 1))
            painter.drawEllipse(box)
            start, span = low.value() * 360 / 4096, (high.value() - low.value()) * 360 / 4096
            painter.setPen(QPen(PATH_COLOUR, 3))
            painter.drawArc(box, int((90 - start) * 16), int(-span * 16))
            painter.setPen(self.palette().windowText().color())
            painter.drawText(QRectF(40, 2, self.width() - 40, 30), Qt.AlignmentFlag.AlignVCenter,
                             f"{low.value() * 360 / 4096:.0f}° to {high.value() * 360 / 4096:.0f}°")
            return
        for index, (name, low, high, _field) in enumerate(self.pairs):
            y = 2 + index * self.ROW
            lowest, highest = min(low.limits()[0], high.limits()[0]), max(low.limits()[1], high.limits()[1])
            span = max(1, highest - lowest)
            track = QRectF(30, y + 3, self.width() - 34, self.ROW - 6)
            painter.setPen(self.palette().windowText().color())
            painter.drawText(QRectF(0, y, 28, self.ROW), Qt.AlignmentFlag.AlignVCenter, name)
            painter.fillRect(track, QColor(60, 60, 66))
            x = lambda value: track.left() + (value - lowest) * track.width() / span
            painter.fillRect(QRectF(x(min(low.value(), high.value())), track.top(),
                                    max(2.0, abs(x(high.value()) - x(low.value()))), track.height()), PATH_COLOUR)
            if lowest < 0 < highest:
                painter.setPen(QPen(QColor(240, 240, 240), 1))
                painter.drawLine(QPointF(x(0), track.top() - 2), QPointF(x(0), track.bottom() + 2))


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
        self._add_ranges()
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
        part_ids = {part["id"]} if part["id"] else set(effect_parts)      # 0: draws nothing, the whole effect
        # a result's number is a heal when the part gives HP (Cure's emitter: Heal tick)
        heals = any(f["key"].endswith("heal_tick") for f in fields)
        self.preview = PartPreview(runner, part_ids, renderer, markers=self.markers, part_names=self.part_names,
                                   sounds=sounds, heals=heals, timeline=not part["id"])
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
        # Cure's ring and motes: where they go around the target, from the sizes the port measured
        self.geometry = GeometryView() if part["key"] in ("ring", "motes") else None
        if self.geometry is not None:
            self.below.insertTab(0, self.geometry, "Geometry")
            self.below.setCurrentIndex(0)
            self.geometry.set_geometry(geometry(runner.recording, self.values()))
            runner.recording_changed.connect(self._geometry_changed)
        self.below.setFixedHeight(SHEET_HEIGHT + 150)
        self.below_fold = Collapsible("Images, sprite sequences, life", self.below)
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.preview, 1)
        right.addWidget(self.below_fold)
        # the parameters beside the preview, the line between them dragged at will (no width forced,
        # the same in every part tab); the preview takes the room the parameters leave
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(scroll)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.splitterMoved.connect(lambda _position, _index: self._panel_moved())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
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
        box.installEventFilter(self)                    # hovered: the part's paths stand out
        self._boxes = getattr(self, "_boxes", {})
        self._boxes[group["key"]] = (box, layout)
        return fields

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave) and hasattr(self, "preview"):
            self.preview.set_highlight(event.type() == QEvent.Type.Enter)
        return super().eventFilter(watched, event)

    def _add_ranges(self):
        """Under a group of min / max pairs (a random range: Cure's sparkle speeds, the motes' angles,
        drop, rise), the ranges drawn (RangeGlyph)."""
        self.ranges = []
        for key, (box, layout) in getattr(self, "_boxes", {}).items():
            pairs = [(f["key"][:-len(".min")], f) for f in self.fields
                     if f["key"].endswith(".min") and _in_group(f["key"], key) and f["key"][:-4] + ".max" in self.spins]
            if pairs:
                glyph = RangeGlyph([(name.rsplit(".", 1)[-1], self.spins[name + ".min"], self.spins[name + ".max"], f)
                                    for name, f in pairs])
                layout.addWidget(glyph)
                self.ranges.append(glyph)

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
        # a colour multiplier (r, g, b: 128 = unchanged): its swatch - a mid grey texel as it comes out
        # (a white one saturates past 128)
        for key, spin in self.spins.items():
            base = key[:-len(".b")] if key.endswith(".b") else None
            if base and base + ".r" in self.spins and base + ".g" in self.spins:
                rgb = [self.spins[base + c].value() for c in (".r", ".g", ".b")]
                spin.hint(f'<span style="background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]})">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>'
                          f' a mid grey comes out as this')
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

    def showEvent(self, event):
        super().showEvent(event)
        total = sum(self.splitter.sizes())
        if total and self.splitter.sizes()[0] != PANEL["width"]:
            self.splitter.setSizes([PANEL["width"], max(1, total - PANEL["width"])])

    def _panel_moved(self):
        PANEL["width"] = self.splitter.sizes()[0]

    def _geometry_changed(self):
        self.geometry.set_geometry(geometry(self.runner.recording, self.values()))

    def values(self):
        """{key: value} of the tab's fields as they are."""
        return {key: spin.value() for key, spin in self.spins.items()}

    def _changed(self, key, value):
        self._mark(key)
        self._ratios()
        for glyph in self.ranges:
            glyph.update()
        if self.geometry is not None:
            self.geometry.set_geometry(geometry(self.runner.recording, self.values()))
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
