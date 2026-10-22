"""Fujin's Choreography > Native preview: what an effect whose behaviour is compiled in the exe
(Cure, Fire, most spells and enemy attacks) draws, frame by frame, from the game's own code.

The FFNx effect harness (fxaudit_held.exe, D:/.../harness/fxaudit) maps FF8_EN.exe, fakes a battle
and runs the effect's ORIGINAL code tick by tick; with vram=1 it records every PlayStation GPU
packet the effect queues and the textures it uploads (FF8GameData.psxgpu.fxdump). This view runs
it for the selected effect (Record), then draws the recording with the software GPU
(FF8GameData.psxgpu.gpu) at the battle's 15 frames per second.

Exact: what is drawn, where, its colours, blending and timing (the game's code ran).
Approximated: the battle around it - stand-in actors and a fixed default camera (the effect's
own camera moves are not applied, so "Fit the effect" frames what it draws); textures the effect
did not upload itself (the target's model, the battle's shared effect textures) are drawn flat grey.

The harness is a complementary file opened from the header's Import (shared file bank), never
looked for in a guessed folder.
"""
import os
import tempfile

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QVBoxLayout,
                             QWidget)

from Common.filebinding import FileBinding
from FF8GameData.psxgpu.fxdump import load_recording
from FF8GameData.psxgpu.gpu import SCREEN_H, SCREEN_W

HARNESS_NAME = "fxaudit_held.exe"
TICKS_PER_SECOND = 15
FIT_WIDTH = 560          # pixels of the "Fit the effect" picture
GAME_SCALE = 2           # the game window drawn 640 x 448
HARNESS_ARGS = ("orig", "model=0", "targets=1", "livecam=1", "vram=1", "ticks=3000")


def recording_path(effect_id):
    folder = os.path.join(tempfile.gettempdir(), "fujin_native_preview")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"effect_{effect_id:03d}.txt")


class NativePreviewView(QWidget):
    def __init__(self, file_registry):
        super().__init__()
        self.effect_id, self.effect_name = None, ""
        self.recording = None
        self._frames = {}           # (tick, view mode) -> (QPixmap, Gpu)
        self._process = None
        self.harness_binding = FileBinding(HARNESS_NAME, file_registry, file_filter=HARNESS_NAME,
                                           read_only=True, complementary=True)
        self.harness_binding.file_opened.connect(lambda _path: self._update_controls())
        self.intro = QLabel(
            "What the effect draws, from the game's own code: the FFNx effect harness runs it in a fake "
            "battle and records every primitive and texture it sends to the PlayStation GPU. Exact: shapes, "
            "colours, blending, timing. Approximated: stand-in actors, a fixed camera (the effect's own camera "
            "moves are not applied), textures the effect does not upload itself drawn flat grey.")
        self.intro.setWordWrap(True)
        self.record_button = QPushButton("Record")
        self.record_button.setToolTip("Run the effect's code in the FFNx effect harness and record what it draws")
        self.record_button.clicked.connect(lambda: self.record())
        self.view_mode = QComboBox()
        self.view_mode.addItem("Fit the effect", "fit")
        self.view_mode.addItem("Game window (320 × 224)", "game")
        self.view_mode.setToolTip("Fit the effect: frame everything it draws (the harness camera is not the "
                                  "effect's). Game window: the 320 × 224 screen exactly as recorded.")
        self.view_mode.currentIndexChanged.connect(lambda _i: self._show(self.slider.value()))
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._toggle_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._show)
        self.frame_label = QLabel()
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet("background: #101018;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.picture)
        self.scroll = scroll
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / TICKS_PER_SECOND))
        self.timer.timeout.connect(self._advance)
        self._prerender = QTimer(self)
        self._prerender.setInterval(0)
        self._prerender.timeout.connect(self._prerender_step)
        controls = QHBoxLayout()
        controls.addWidget(self.record_button)
        controls.addWidget(self.view_mode)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(controls)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.status)
        self.harness_binding.load_opened_file()
        self._update_controls()

    # ------------------------------------------------------------------ effect / recording
    def set_effect(self, effect_id, name=""):
        if effect_id == self.effect_id:
            return
        self.play_button.setChecked(False)
        self.effect_id, self.effect_name = effect_id, name
        self.recording, self._frames = None, {}
        self._prerender.stop()
        path = recording_path(effect_id) if effect_id is not None else None
        if path and os.path.isfile(path):
            self.load_recording_file(path)       # recorded earlier: shown again, Record redoes it
        else:
            self.picture.clear()
            self._update_controls()

    def import_harness(self):
        """Header Import complementary: the FFNx effect harness, through the shared file bank."""
        registry = self.harness_binding.registry
        path = self.harness_binding.open_dialog(self, registry.last_folder(HARNESS_NAME))
        if path:
            registry.remember_folder(HARNESS_NAME, os.path.dirname(path))

    def harness_path(self):
        return self.harness_binding.current_path or ""

    def record(self):
        """Run the harness for the selected effect in the background; the recording loads when done."""
        harness = self.harness_path()
        if self.effect_id is None or not harness or self._process is not None:
            self._update_controls()
            return False
        output = recording_path(self.effect_id)
        if os.path.isfile(output):
            os.remove(output)
        self._process = QProcess(self)
        self._process.setWorkingDirectory(os.path.dirname(harness))
        self._process.finished.connect(lambda code, _status, out=output, effect=self.effect_id:
                                       self._recorded(effect, out, code))
        self._process.start(harness, [str(self.effect_id), *HARNESS_ARGS, f"between={output}"])
        self.status.setText(f"Recording effect {self.effect_id} in the harness…")
        self._update_controls()
        return True

    def _recorded(self, effect_id, output, code):
        log = bytes(self._process.readAllStandardOutput()).decode("ascii", "replace") if self._process else ""
        self._process = None
        if effect_id != self.effect_id:
            self._update_controls()
            return
        if not os.path.isfile(output):
            last = [line for line in log.splitlines() if line.strip()][-1:] or [f"exit code {code}"]
            self.status.setText(f"The harness made no recording: {last[0]}")
            self._update_controls()
            return
        self.load_recording_file(output)
        ended = next((line for line in log.splitlines() if line.startswith("done:")), "")
        if ended:
            self.status.setText(self.status.text() + " Harness: " + ended[len("done:"):].strip())

    def load_recording_file(self, path):
        """Show a harness recording (made by Record, or a dump with vram=1)."""
        self.recording = load_recording(path, self.effect_id)
        self._frames = {}
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.recording.ticks) - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._fit = self.recording.fit_view()
        self._show(0)
        self._prerender_tick = 0
        self._prerender.start()
        self._update_controls()
        return self.recording

    # ------------------------------------------------------------------ drawing
    def _view(self):
        if self.view_mode.currentData() == "game":
            return (0, 0, SCREEN_W, SCREEN_H), GAME_SCALE
        return self._fit, FIT_WIDTH / max(1, self._fit[2])

    def frame(self, tick):
        """(QPixmap, Gpu) of a tick in the current view (drawn once, then cached)."""
        key = (tick, self.view_mode.currentData())
        if key not in self._frames:
            view, scale = self._view()
            image, gpu = self.recording.frame(tick, view=view, scale=scale)
            height, width = image.shape[:2]
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            self._frames[key] = (QPixmap.fromImage(qimage), gpu)
        return self._frames[key]

    def _prerender_step(self):
        if self.recording is None or self._prerender_tick >= len(self.recording.ticks):
            self._prerender.stop()
            return
        self.frame(self._prerender_tick)
        self._prerender_tick += 1

    def _show(self, tick):
        if self.recording is None or not self.recording.ticks:
            return
        tick = min(tick, len(self.recording.ticks) - 1)
        pixmap, gpu = self.frame(tick)
        area = self.scroll.viewport().size()
        if area.width() > pixmap.width() and area.height() > pixmap.height():   # fill the view, keep the shape
            pixmap = pixmap.scaled(area, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.picture.setPixmap(pixmap)
        self.frame_label.setText(f"tick {tick + 1}/{len(self.recording.ticks)}")
        missing = ", ".join(f"0x{page:X}" for page in sorted(gpu.missing_pages))
        self.status.setText(
            f"Effect {self.effect_id} {self.effect_name}: {len(self.recording.ticks)} ticks "
            f"({len(self.recording.ticks) / TICKS_PER_SECOND:.1f} s). This tick: {gpu.counts['polygons']} polygons, "
            f"{gpu.counts['sprites']} sprites, {gpu.counts['lines']} lines."
            + (f" Flat grey: texture pages {missing} hold nothing the effect uploaded itself (the target's "
               "model, or the battle's shared effect textures)." if missing else "")
            + ("" if self.recording.has_vram else " No textures in this recording (made without vram=1)."))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.recording is not None:
            self._show(self.slider.value())

    def _toggle_play(self, playing):
        self.play_button.setText("Pause" if playing else "Play")
        if playing and self.recording is not None:
            self.timer.start()
        else:
            self.timer.stop()

    def _advance(self):
        maximum = self.slider.maximum()
        self.slider.setValue(0 if self.slider.value() >= maximum else self.slider.value() + 1)

    def _update_controls(self):
        harness = bool(self.harness_path())
        recording = self.recording is not None
        busy = self._process is not None
        self.record_button.setEnabled(harness and self.effect_id is not None and not busy)
        self.record_button.setText("Record again" if recording else "Record")
        for widget in (self.view_mode, self.play_button, self.slider):
            widget.setEnabled(recording and not busy)
        if not harness and not recording:
            self.status.setText(f"Import the FFNx effect harness ({HARNESS_NAME}) from the header's Import "
                                "complementary to record what this effect draws.")
        elif not recording and not busy:
            self.status.setText("Record runs this effect's code in the harness (a few seconds).")
