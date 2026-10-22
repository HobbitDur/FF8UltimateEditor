"""Fujin's Choreography > Native preview: what an effect whose behaviour is compiled in the exe
(Cure, Fire, most spells and enemy attacks) draws, frame by frame, from the game's own code.

FF8UltimateEditor's effect recorder (Tools/fxrecorder, a small 32-bit program shipped with the
release; from source, build it with Tools/fxrecorder/build.bat) maps the opened FF8_EN.exe, fakes a
battle and runs the effect's ORIGINAL code tick by tick, recording every PlayStation GPU packet it
queues and every texture it uploads (FF8GameData.psxgpu.fxdump). This view runs it for the selected
effect (Record), then draws the recording with the software GPU (FF8GameData.psxgpu.gpu) at the
battle's 15 frames per second.

The camera is the effect's own: its camera track (the exe's, a created one or a .bcam - the Camera
tab's) is played by Fujin's camera player (FF8GameData.dat.camerascript / battlecamera) around the
recorder's fake battle, and the recorder views each tick through that pose, so "Game window" shows
what the player would see. An effect with no camera track keeps the default battle view.

Files: FF8_EN.exe (the header's Import, as for the camera tracks), the effect's files (the folder
the effect files were imported from) and the battle folder, found through a8def.tim - the battle's
shared effect textures, opened from the header's Import complementary (shared file bank, never a
guessed folder); the target model c0mNNN.dat is read from that folder.

Exact: what is drawn, where, its colours, blending and timing (the game's code ran).
Approximated: the fake battle (actors stand at fixed places), the camera player is Fujin's
(floating point), and an effect that reads the real battle state may differ.
"""
import os
import struct
import tempfile

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QSpinBox,
                             QVBoxLayout, QWidget)

from Common.apppaths import app_path
from Common.filebinding import FileBinding
from FF8GameData.psxgpu.fxdump import load_recording
from FF8GameData.psxgpu.gpu import GAME_WINDOW

RECORDER = app_path("Tools", "fxrecorder", "fxrecorder.exe")
SHARED_TEXTURES = "a8def.tim"
TICKS_PER_SECOND = 15
FIT_WIDTH = 560          # pixels of the "Fit the effect" picture
GAME_SCALE = 0.25        # the game window (2560 x 1792 units: eighths of a pixel) drawn 640 x 448
# the recorder's fake battle (Tools/fxrecorder build_battle): entity positions, the caster and target
SLOT_POSITIONS = {0: (-1500, 0, 3000), 1: (0, 0, 3200), 2: (1500, 0, 3000), 4: (0, 0, -3000),
                  5: (-1800, 0, -3200), 6: (1800, 0, -3200)}
CASTER_SLOT, TARGET_SLOT = 0, 4
INITIAL_EYE, INITIAL_TARGET = (10000, -3000, 5000), (0, -500, 0)   # the battle camera words at the start


def recording_path(effect_id, model=0):
    folder = os.path.join(tempfile.gettempdir(), "fujin_native_preview")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"effect_{effect_id:03d}_m{model}.txt")


def model_scale(battle_folder, model):
    """The camera offset scale of a c0mNNN.dat (skeleton scale / 512), 0.5 for the recorder's stand-in."""
    path = os.path.join(battle_folder or "", f"c0m{model:03d}.dat")
    try:
        with open(path, "rb") as file:
            data = file.read(4096)
        skeleton = struct.unpack_from("<I", data, 4)[0]
        return max(1, struct.unpack_from("<H", data, skeleton + 2)[0]) / 512
    except (OSError, struct.error):
        return 0.5


def camera_lines(manager, track, battle_folder="", model=0, ticks=600):
    """Per-tick camera of an effect's track played around the recorder's fake battle, as the lines
    the recorder reads: "t ex ey ez ax ay az roll H". [] when the script plays nothing."""
    from FF8GameData.dat.battlecamera import BattleCameraContext, CameraActor, CameraPose, play_camera_animation
    from FF8GameData.dat.camerascript import CameraScriptInputs, camera_animation_at, run_camera_script
    run = run_camera_script(manager.vm, track.script, CameraScriptInputs(
        opening=0, attacker_slot=CASTER_SLOT, target_slot=TARGET_SLOT, affected_targets=1))
    if run.chosen is None:
        return []
    animation = camera_animation_at(track.collection, run.chosen)
    if animation is None:
        return []
    scale = model_scale(battle_folder, model) if model >= 0 else 0.5
    actors = {slot: CameraActor(position, 0.0, scale) for slot, position in SLOT_POSITIONS.items()}
    context = BattleCameraContext(actors[CASTER_SLOT], actors[TARGET_SLOT],
                                  CameraPose(INITIAL_EYE, INITIAL_TARGET), actors)
    poses = play_camera_animation(animation, context)[:ticks]
    clamp = lambda value: max(-32768, min(32767, int(round(value))))
    return [f"{tick} {' '.join(str(clamp(v)) for v in (*pose.eye, *pose.target))} {clamp(pose.roll)} "
            f"{max(1, clamp(pose.projection))}" for tick, pose in enumerate(poses)]


class NativePreviewView(QWidget):
    """providers: exe_path() -> the opened FF8_EN.exe; magic_folder() -> the effect files' folder;
    camera_track(effect_id) -> (camera manager, track) or (None, None)."""

    def __init__(self, file_registry, exe_path=None, magic_folder=None, camera_track=None):
        super().__init__()
        self.effect_id, self.effect_name = None, ""
        self.recording = None
        self._frames = {}           # (tick, view mode) -> (QPixmap, Gpu)
        self._process = None
        self._fit = GAME_WINDOW
        self.camera_used = False
        self.exe_path = exe_path or (lambda: "")
        self.magic_folder = magic_folder or (lambda: "")
        self.camera_track = camera_track or (lambda _effect: (None, None))
        self.textures_binding = FileBinding(SHARED_TEXTURES, file_registry, file_filter=SHARED_TEXTURES,
                                            read_only=True, complementary=True)
        self.textures_binding.file_opened.connect(lambda _path: self._update_controls())
        self.intro = QLabel(
            "What the effect draws, from the game's own code: FF8UltimateEditor's effect recorder runs it in a "
            "fake battle and records every primitive and texture it sends to the PlayStation GPU, seen through "
            "the effect's own camera (Camera tab). Exact: shapes, colours, blending, timing. Approximated: the "
            "battle around it (actors at fixed places).")
        self.intro.setWordWrap(True)
        self.record_button = QPushButton("Record")
        self.record_button.setToolTip("Run the effect's code in the recorder and record what it draws")
        self.record_button.clicked.connect(lambda: self.record())
        self.model_spin = QSpinBox()
        self.model_spin.setRange(-1, 199)
        self.model_spin.setValue(0)
        self.model_spin.setPrefix("Target c0m")
        self.model_spin.setSpecialValueText("No target model")
        self.model_spin.setToolTip("The monster model every slot of the fake battle gets (read from the battle "
                                   "folder; c0m000 is the game's test dummy). Record again to apply.")
        self.view_mode = QComboBox()
        self.view_mode.addItem("Game window (320 × 224)", "game")
        self.view_mode.addItem("Fit the effect", "fit")
        self.view_mode.setToolTip("Game window: the screen through the effect's camera. Fit the effect: frame "
                                  "everything it draws.")
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
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.picture)
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
        controls.addWidget(self.model_spin)
        controls.addWidget(self.view_mode)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(controls)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.status)
        self.textures_binding.load_opened_file()
        self._update_controls()

    # ------------------------------------------------------------------ files
    def import_shared_textures(self):
        """Header Import complementary: a8def.tim, which also tells the battle folder."""
        registry = self.textures_binding.registry
        path = self.textures_binding.open_dialog(self, registry.last_folder(SHARED_TEXTURES))
        if path:
            registry.remember_folder(SHARED_TEXTURES, os.path.dirname(path))

    def battle_folder(self):
        path = self.textures_binding.current_path
        return os.path.dirname(path) if path else ""

    def missing(self):
        """What Record still needs, in words ([] = ready)."""
        needs = []
        if not RECORDER.is_file():
            needs.append(f"the effect recorder ({RECORDER}; from source, run Tools/fxrecorder/build.bat)")
        if not self.exe_path():
            needs.append("FF8_EN.exe (the header's Import)")
        if not self.magic_folder():
            needs.append("the effect files' folder (the header's Import, Effect files)")
        if not self.battle_folder():
            needs.append(f"the battle folder ({SHARED_TEXTURES} from the header's Import complementary)")
        return needs

    # ------------------------------------------------------------------ effect / recording
    def set_effect(self, effect_id, name=""):
        if effect_id == self.effect_id:
            return
        self.play_button.setChecked(False)
        self.effect_id, self.effect_name = effect_id, name
        self.recording, self._frames = None, {}
        self._prerender.stop()
        path = recording_path(effect_id, self.model_spin.value()) if effect_id is not None else None
        if path and os.path.isfile(path):
            self.load_recording_file(path)       # recorded earlier: shown again, Record redoes it
        else:
            self.picture.clear()
            self._update_controls()

    def record(self):
        """Run the recorder for the selected effect in the background; the recording loads when done."""
        if self.effect_id is None or self.missing() or self._process is not None:
            self._update_controls()
            return False
        model = self.model_spin.value()
        output = recording_path(self.effect_id, model)
        if os.path.isfile(output):
            os.remove(output)
        # absolute paths: the recorder runs from its own folder
        args = [str(self.effect_id), f"exe={os.path.abspath(self.exe_path())}",
                f"magic={os.path.abspath(self.magic_folder())}", f"battle={os.path.abspath(self.battle_folder())}",
                f"out={output}", f"model={model}"]
        self.camera_used = False
        manager, track = self.camera_track(self.effect_id)
        if track is not None:
            lines = camera_lines(manager, track, self.battle_folder(), model)
            if lines:
                camera = output[:-4] + "_camera.txt"
                with open(camera, "w", encoding="ascii") as file:
                    file.write("\n".join(lines) + "\n")
                args.append(f"camera={camera}")
                self.camera_used = True
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(RECORDER.parent))
        self._process.finished.connect(lambda code, _status, out=output, effect=self.effect_id:
                                       self._recorded(effect, out, code))
        self._process.start(str(RECORDER), args)
        self.status.setText(f"Recording effect {self.effect_id}…")
        self._update_controls()
        return True

    def _recorded(self, effect_id, output, code):
        log = bytes(self._process.readAllStandardOutput()).decode("ascii", "replace") if self._process else ""
        self._process = None
        if effect_id != self.effect_id:
            self._update_controls()
            return
        if not os.path.isfile(output) or (code != 0 and not os.path.getsize(output)):
            last = [line for line in log.splitlines() if line.strip()][-1:] or [f"exit code {code}"]
            self._update_controls()
            self.status.setText(f"The recorder made no recording: {last[0]}")
            return
        self.load_recording_file(output)
        problems = [line for line in log.splitlines() if "faulted" in line or "failed" in line or "missing" in line]
        if problems:
            self.status.setText(self.status.text() + " Recorder: " + "; ".join(problems[:3]))

    def load_recording_file(self, path):
        """Show a recording (made by Record, or any recorder / harness dump)."""
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
            return GAME_WINDOW, GAME_SCALE
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
            f"{gpu.counts['sprites']} sprites, {gpu.counts['lines']} lines. "
            + ("Camera: the effect's own track." if self.camera_used else
               "Camera: the default battle view (no camera track played).")
            + (f" Flat grey: texture pages {missing} were never uploaded." if missing else "")
            + ("" if self.recording.has_vram else " No textures in this recording."))

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
        needs = self.missing()
        recording = self.recording is not None
        busy = self._process is not None
        self.record_button.setEnabled(not needs and self.effect_id is not None and not busy)
        self.record_button.setText("Record again" if recording else "Record")
        for widget in (self.view_mode, self.play_button, self.slider):
            widget.setEnabled(recording and not busy)
        if needs and not recording:
            self.status.setText("To record, open: " + "; ".join(needs) + ".")
        elif not recording and not busy:
            self.status.setText("Record runs this effect's code (a second or less) and shows what it draws.")
