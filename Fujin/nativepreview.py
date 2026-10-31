"""Fujin's Overview > Effect preview: what an effect whose behaviour is compiled in the exe
(Cure, Fire, most spells and enemy attacks) draws, frame by frame, from the game's own code, in
the battle the Camera tab's preview sets up (party, encounter or monsters, caster and target).

FF8UltimateEditor's effect recorder (Tools/fxrecorder, a small 32-bit program shipped with the
release; from source, build it with Tools/fxrecorder/build.bat) maps the opened FF8_EN.exe, fakes a
battle and runs the effect's ORIGINAL code tick by tick, recording every PlayStation GPU packet it
queues and every texture it uploads (FF8GameData.psxgpu.fxdump). Play runs it for the selected
effect when there is no recording yet (edits of its files or its camera record it anew), then draws the recording at the
battle's 15 frames per second with OpenGL (FF8GameData.psxgpu.glrender; the software GPU,
FF8GameData.psxgpu.gpu, without OpenGL 3.3).

The camera is the effect's own: its camera track (the exe's, a created one or a .bcam - the Camera
tab's) is played by Fujin's camera player (FF8GameData.dat.camerascript / battlecamera) around the
recorder's fake battle, and the recorder views each tick through that pose, so "Game window" shows
what the player would see. An effect with no camera track keeps the default battle view.

Files: only the files opened in Fujin, one by one - nothing is read from their folders. FF8_EN.exe
(the header's Import), the effect's imported files as Fujin holds them (unsaved edits included,
staged in a private temporary folder: the imported files are never written), a8def.tim when opened
(Import complementary: the battle's shared effect textures; without it those parts are flat grey)
and the models imported in the Camera tab's preview. The cast is that preview's: its party
(characters with their imported weapons), its encounter's enemies or its imported monsters, its
caster and target; each actor stands in its battle slot and the recorder loads and draws it each
tick as the battle does. An actor whose file is not imported is left out (the status names it), a
file the effect asks for and was not imported too. Once an effect is recorded, edits and Undo /
Redo refresh it.

Exact: what is drawn, where, its colours, blending and timing (the game's code ran).
Approximated: the fake battle (actors stand at fixed places), the camera player is Fujin's
(floating point), and an effect that reads the real battle state may differ.
"""
import dataclasses
import hashlib
import math
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QSlider, QVBoxLayout, QWidget)

from Common.filebinding import FileBinding
from Fujin.recorderbuild import RECORDER, recorder_build    # built from source at startup, never in git
from FF8GameData.psxgpu.fxdump import load_recording
from FF8GameData.psxgpu.gpu import GAME_WINDOW

_GL_RENDERER = []   # [PsxGlRenderer or None]: made on the first frame drawn (None = no OpenGL 3.3)


def gl_renderer():
    """The shared OpenGL renderer (a frame in ~40 ms instead of ~1 s), None without OpenGL 3.3:
    the software Gpu draws then."""
    if not _GL_RENDERER:
        from FF8GameData.psxgpu.glrender import PsxGlRenderer
        _GL_RENDERER.append(PsxGlRenderer.create())
    return _GL_RENDERER[0]
SHARED_TEXTURES = "a8def.tim"
TICKS_PER_SECOND = 15
FIT_WIDTH = 560          # pixels of the "Fit the effect" picture
GAME_SCALE = 0.25        # the game window (2560 x 1792 units: eighths of a pixel) drawn 640 x 448
# the recorder's battle (Tools/fxrecorder build_battle): the entity slots as the game lays them out
# (party 0-2, enemies 3-6, the camera scripts' slot ids too) and where each one stands
SLOT_POSITIONS = {0: (-1500, 0, 3000), 1: (0, 0, 3200), 2: (1500, 0, 3000), 3: (0, 0, -3000),
                  4: (-1800, 0, -3200), 5: (1800, 0, -3200), 6: (0, 0, -4600)}
INITIAL_EYE, INITIAL_TARGET = (10000, -3000, 5000), (0, -500, 0)   # the battle camera words at the start


@dataclass
class BattleCast:
    """The battle an effect is recorded in: {slot: (body .dat, weapon .dat or None)}, the caster's
    slot and the target's (a slot with no model when there is no target actor). From the Camera
    tab's preview also where each actor stands and faces ({slot: engine xyz}, {slot: yaw radians})
    and the effect camera it plays there (camera poses), so both previews show the same shot;
    without them the recorder's fixed places (SLOT_POSITIONS) and Fujin's camera player are used."""
    slots: dict = field(default_factory=dict)
    caster: int = 0
    target: int = 3
    positions: dict = field(default_factory=dict)
    yaws: dict = field(default_factory=dict)
    camera: list = None
    not_imported: list = field(default_factory=list)   # actors' files the cast names, not imported
    idle: dict = field(default_factory=dict)           # {slot: the animation it loops}
    cast_before: list = field(default_factory=list)    # [(animation, ticks, offset)] the caster plays before the effect
    cast_during: list = field(default_factory=list)    # ... while it runs (last ticks 0 = to the end)
    cast_camera: tuple = None                          # (eye, target) seen during the cast
    actors: bool = True                                # False: the actors are loaded, not drawn (the effect alone)
    native: bool = False                               # the effect's C++ port (FFNx) instead of the exe's code
    params: tuple = ()                                 # ((key, value), ..) its parameters not at the game's value
    lab: bool = False                                  # only the target drawn (actors=2): Choreography's part tabs
    program: str = ""                                  # the effect run from this program (a description of Fujin's)

    def key(self):
        """The cache tag of this cast: its files (where they are and their state on disk), roles,
        whether the actors are drawn and the recorder build (a new one records anew)."""
        parts = [f"c{self.caster}t{self.target}a{int(self.actors)}n{int(self.native)}l{int(self.lab)}"]
        parts += [f"{key}={value}" for key, value in self.params]
        if self.program:
            parts.append("program|" + hashlib.sha256(self.program.encode("ascii")).hexdigest())
        try:
            parts.append(f"recorder|{RECORDER.stat().st_mtime_ns}")
        except OSError:
            pass
        for slot, files in sorted(self.slots.items()):
            for path in files:
                if not path:
                    continue
                try:
                    stat = os.stat(path)
                    parts.append(f"{slot}|{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}")
                except OSError:
                    parts.append(f"{slot}|{os.path.abspath(path)}")
        names = "_".join(os.path.splitext(os.path.basename(self.slots[slot][0]))[0]
                         for slot in (self.caster, self.target) if slot in self.slots) or "none"
        return f"{names}_{hashlib.sha256('/'.join(parts).encode('utf-8')).hexdigest()[:10]}"


def _plan_text(plan):
    """The recorder's a:n[:x:y:z] list of a cast plan (the offset only when it moves)."""
    return ",".join(f"{animation}:{ticks}" + ("".join(f":{v}" for v in offset) if any(offset) else "")
                    for animation, ticks, offset in plan)


def camera_path(recording):
    """The camera lines a cached recording was made with, kept next to it."""
    return os.path.splitext(recording)[0] + ".camera"


def recording_path(effect_id, cast_key="none"):
    folder = os.path.join(tempfile.gettempdir(), "fujin_native_preview")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"effect_{effect_id:03d}_{cast_key}.txt")


def model_scale(path):
    """The camera offset scale of a battle .dat (skeleton scale / 512), 0.5 without one."""
    if not path:
        return 0.5
    try:
        with open(path, "rb") as file:
            data = file.read(4096)
        skeleton = struct.unpack_from("<I", data, 4)[0]
        return max(1, struct.unpack_from("<H", data, skeleton + 2)[0]) / 512
    except (OSError, struct.error):
        return 0.5


def pose_lines(poses, ticks=600):
    """Camera poses as the lines the recorder reads: "t ex ey ez ax ay az roll H"."""
    clamp = lambda value: max(-32768, min(32767, int(round(value))))
    return [f"{tick} {' '.join(str(clamp(v)) for v in (*pose.eye, *pose.target))} {clamp(pose.roll)} "
            f"{max(1, clamp(pose.projection))}" for tick, pose in enumerate(poses[:ticks])]


def camera_lines(manager, track, cast=None, ticks=600):
    """Per-tick camera of an effect's track played around the recorder's battle (cast: a BattleCast,
    each actor framed with its own model's scale), as the lines the recorder reads:
    "t ex ey ez ax ay az roll H". [] when the script plays nothing."""
    from FF8GameData.dat.battlecamera import BattleCameraContext, CameraActor, CameraPose, play_camera_animation
    from FF8GameData.dat.camerascript import CameraScriptInputs, camera_animation_at, run_camera_script
    cast = cast or BattleCast()
    run = run_camera_script(manager.vm, track.script, CameraScriptInputs(
        opening=0, attacker_slot=cast.caster, target_slot=cast.target, affected_targets=1))
    if run.chosen is None:
        return []
    animation = camera_animation_at(track.collection, run.chosen)
    if animation is None:
        return []
    actors = {slot: CameraActor(position, 0.0, model_scale(cast.slots.get(slot, (None, None))[0]))
              for slot, position in SLOT_POSITIONS.items()}
    context = BattleCameraContext(actors[cast.caster], actors[cast.target],
                                  CameraPose(INITIAL_EYE, INITIAL_TARGET), actors)
    return pose_lines(play_camera_animation(animation, context), ticks)


class NativePreviewView(QWidget):
    recording_changed = pyqtSignal()        # another recording is shown (or none)

    """providers: exe_path() -> the opened FF8_EN.exe; effect_files() -> {file name: bytes} of the
    effect's imported files as Fujin holds them (unsaved edits included);
    camera_track(effect_id) -> (camera manager, track) or (None, None);
    file_edits() -> {file name: unsaved bytes}, staged privately for the recorder;
    cast_source: the Camera tab's preview (its caster / target pickers are mirrored here and
    battle_cast() gives the battle), or None for the battle folder's test dummy;
    params(effect_id) -> {key: value} of the effect's edited parameters (FFNx fx_params.h): when
    there are some, the recorder runs the effect's C++ port with them (native=1);
    program(effect_id) -> the text of the program the effect runs from (a description Fujin holds:
    a new effect, or one whose description was edited), or None: the recorder runs it (program=);
    lab: always the C++ port, of the actors only its target (the part tabs' reference) - its parts tagged (Fujin's
    Choreography part tabs show it part by part)."""

    def __init__(self, file_registry, exe_path=None, effect_files=None, camera_track=None, file_edits=None,
                 cast_source=None, params=None, lab=False, program=None):
        super().__init__()
        self.params = params or (lambda _effect: {})
        self.program = program or (lambda _effect: None)
        self.lab = lab
        self.effect_id, self.effect_name = None, ""
        self.recording = None
        self._frames = {}           # (tick, view mode) -> (QPixmap, Gpu)
        self._process = None
        self._scratch = None
        self._recorded_edits = None
        self._recorded_camera = None    # the camera lines the shown recording was made with
        self._preview_requested = False
        self._edit_refresh = QTimer(self)
        self._edit_refresh.setSingleShot(True)
        self._edit_refresh.setInterval(250)
        self._edit_refresh.timeout.connect(self._refresh_edits)
        self._camera_refresh = QTimer(self)
        self._camera_refresh.setSingleShot(True)
        self._camera_refresh.setInterval(250)
        self._camera_refresh.timeout.connect(self._refresh_camera)
        self._fit = GAME_WINDOW
        self._prerender_tick = 0
        self.camera_used = False
        self.exe_path = exe_path or (lambda: "")
        self.effect_files = effect_files or (lambda: {})
        self.camera_track = camera_track or (lambda _effect: (None, None))
        self.file_edits = file_edits or (lambda: {})
        self.cast_source = cast_source
        self._cast_refresh = QTimer(self)
        self._cast_refresh.setSingleShot(True)
        self._cast_refresh.setInterval(0)
        self._cast_refresh.timeout.connect(self.refresh_cast)
        self.textures_binding = FileBinding(SHARED_TEXTURES, file_registry, file_filter=SHARED_TEXTURES,
                                            read_only=True, complementary=True)
        self.textures_binding.file_opened.connect(lambda _path: (self.refresh_cast(), self._update_controls()))
        self.intro = QLabel(
            "What the effect draws, from the game's own code: FF8UltimateEditor's effect recorder runs it in the "
            "battle of the Camera tab's preview (its party, encounter or monsters, caster and target) and records "
            "every primitive and texture it sends to the PlayStation GPU, seen through the effect's own camera. "
            "Exact: shapes, colours, blending, timing. Approximated: where the actors stand. Unsaved effect-file "
            "edits are included; after the first recording, editing a texture or using Undo / Redo refreshes "
            "this preview automatically.")
        self.intro.setWordWrap(True)
        # the battle's actors, drawn or not: their pickers live in this group, folded away while it is off
        # (the Camera tab shows them too)
        self.actors_group = QGroupBox("Battle actors")
        self.actors_group.setCheckable(True)
        self.actors_group.setChecked(False)
        self.actors_group.setToolTip("On: draw the party and enemies, the caster playing its cast before the "
                                     "effect. Off: the effect alone - the actors picked here are still loaded, "
                                     "unseen (the effect's code places itself on its caster and target; one it "
                                     "redraws itself, as Cure does its target, is left out too - its own models, "
                                     "as Protect's shield, stay). The caster and target are also picked in the "
                                     "Camera tab.")
        self.actors_group.toggled.connect(lambda _on: (self._fold_actors(), self._cast_changed(),
                                                       self._update_controls()))
        self._cast_key = None
        if cast_source is not None:
            # the battle setup is the Camera tab preview's own panel, shown here while this preview is:
            # one battle for both previews
            cast_source.cast.changed.connect(self._cast_refresh.start)
            cast_source.models_changed.connect(self._cast_refresh.start)
            # the Camera tab's script inputs choose the camera animation: a new one records anew
            cast_source.animation_chosen.connect(lambda _chosen: self.camera_changed())
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
        # drawn at the view's size: the picture never asks for more room than the view gives it
        self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        self._actors_layout = QVBoxLayout(self.actors_group)
        if cast_source is None:
            self._actors_layout.addWidget(QLabel("The battle comes from the Camera tab's preview."))
        controls = QHBoxLayout()
        controls.addWidget(self.view_mode)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addWidget(self.actors_group)
        layout.addLayout(controls)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.status)
        recorder_build().changed.connect(self._update_controls)
        self.textures_binding.load_opened_file()
        self.refresh_cast()
        self._update_controls()

    # ------------------------------------------------------------------ files
    def import_shared_textures(self):
        """Header Import complementary: a8def.tim, the battle's shared effect textures."""
        registry = self.textures_binding.registry
        path = self.textures_binding.open_dialog(self, registry.last_folder(SHARED_TEXTURES))
        if path:
            registry.remember_folder(SHARED_TEXTURES, os.path.dirname(path))

    def _take_battle_setup(self):
        # the very same battle setup panel as the Camera tab preview's, moved here while shown
        if self.cast_source is not None and not self.lab:
            panel = self.cast_source.cast
            if panel.parentWidget() is not self.actors_group:
                self._actors_layout.addWidget(panel)
            self._fold_actors()

    def _fold_actors(self):
        """Battle actors off: its pickers hidden, the group a single line."""
        if self.cast_source is not None and self.cast_source.cast.parentWidget() is self.actors_group:
            self.cast_source.cast.setVisible(self.actors_group.isChecked())

    # the battle setup's pickers (the Camera tab preview's panel)
    @property
    def caster_combo(self):
        return self.cast_source.caster_combo if self.cast_source is not None else None

    @property
    def target_combo(self):
        return self.cast_source.target_combo if self.cast_source is not None else None

    @property
    def party_combos(self):
        return self.cast_source.party_combos if self.cast_source is not None else []

    @property
    def encounter_combo(self):
        return self.cast_source.encounter_combo() if self.cast_source is not None else None

    def refresh_cast(self):
        """The battle setup changed: a new cast shows the recording already made with it, if any."""
        key = self.cast().key()
        if key != self._cast_key:
            self._cast_key = key
            self._cast_changed()
        self._update_controls()          # a newly imported actor can make Record possible

    def cast(self, placed=False):
        """The battle to record: the Camera tab preview's (placed: with where its setup stands the
        actors and its effect camera - built, so only when recording). Only imported files: an
        actor the battle names but whose file is not imported (an encounter enemy) is left out and
        listed in not_imported; no caster = nothing to record."""
        cast = self.cast_source.battle_cast(placed) if self.cast_source is not None else None
        if cast is None:
            return BattleCast({}, 0, 3)
        slots, not_imported = {}, []
        for slot, (body, weapon) in cast.slots.items():
            if body and os.path.dirname(body) and os.path.isfile(body):
                slots[slot] = (body, weapon if weapon and os.path.isfile(weapon) else None)
            elif body:
                not_imported.append(os.path.basename(body))
        params = tuple(sorted(self.params(self.effect_id).items())) if self.effect_id is not None else ()
        program = (self.program(self.effect_id) if self.effect_id is not None else None) or ""
        return BattleCast(slots, cast.caster, cast.target, cast.positions, cast.yaws, cast.camera,
                          sorted(set(not_imported)), cast.idle, cast.cast_before, cast.cast_during, cast.cast_camera,
                          self.actors_group.isChecked() and not self.lab, self.lab or bool(params), params, self.lab,
                          program)

    def _cast_changed(self):
        """Show the recording already made with this cast, if any."""
        self._cast_key = self.cast().key()     # the battle shown: a refresh of the same one changes nothing
        if self.effect_id is None or self._process is not None:
            return
        effect_id, name = self.effect_id, self.effect_name
        self.effect_id = None
        self.set_effect(effect_id, name)

    def missing(self):
        """What Record still needs, in words ([] = ready)."""
        needs = []
        build = recorder_build()
        if build.building:
            needs.append("the effect recorder, being built from its source (Tools/fxrecorder, under a minute)")
        elif not RECORDER.is_file():
            needs.append(f"the effect recorder ({RECORDER}): " + (
                build.error or "FF8UltimateEditor builds it from its source when it starts (Visual Studio C++ "
                               "build tools needed); restart it"))
        if not self.exe_path():
            needs.append("FF8_EN.exe (the header's Import)")
        if not self.effect_files():
            needs.append("the effect's files (the header's Import)")
        cast = self.cast()
        imported = (f" - {', '.join(cast.not_imported)}" if cast.not_imported else "") + ")"
        if cast.caster not in cast.slots:
            needs.append("a caster model (Import complementary: Camera preview models" + imported)
        elif cast.target not in cast.slots:
            # the effects draw on their target's model (Cure redraws it): a battle always has one
            needs.append("a target model (Target above; Import complementary: Camera preview models" + imported)
        return needs

    # ------------------------------------------------------------------ effect / recording
    @staticmethod
    def _edit_signature(edits):
        return tuple((name, hashlib.sha256(data).digest()) for name, data in sorted(edits.items()))

    def edits_changed(self):
        """Coalesce edits/Undo/Redo; keep the current frame when refreshing an existing preview."""
        self._edit_refresh.start()

    def camera_changed(self):
        """A camera keyframe or a Camera tab script input changed: coalesced, then the recording
        is made again if its camera is not the one it would now get."""
        self._camera_refresh.start()

    def _refresh_camera(self):
        if self.recording is None or self._process is not None or self.effect_id is None or self.missing():
            return
        if self._camera_lines(self.cast(placed=True)) != self._recorded_camera:
            self.record(keep_tick=True)

    def _camera_lines(self, cast):
        """The camera file lines a recording of this cast gets (the Camera tab preview's own shot,
        else the effect's track played by Fujin, else none)."""
        manager, track = self.camera_track(self.effect_id)
        if cast.camera is not None:
            return pose_lines(cast.camera)
        if track is not None:
            return camera_lines(manager, track, cast)
        return []

    def _refresh_edits(self):
        if ((self.recording is not None or self._preview_requested) and self._process is None
                and self._edit_signature(self.file_edits()) != self._recorded_edits):
            self.record(keep_tick=True)

    def set_effect(self, effect_id, name=""):
        if effect_id == self.effect_id:
            return
        self.play_button.setChecked(False)
        self.effect_id, self.effect_name = effect_id, name
        self.recording, self._frames = None, {}
        self.recording_changed.emit()
        self._recorded_edits = None
        self._preview_requested = False
        self._prerender.stop()
        self._prerender_tick = 0
        path = recording_path(effect_id, self.cast().key()) if effect_id is not None else None
        if path and os.path.isfile(path):
            self.load_recording_file(path)       # recorded earlier: shown again, a camera edit redoes it
            try:
                with open(camera_path(path), encoding="ascii") as file:
                    self._recorded_camera = file.read().splitlines()
            except OSError:
                self._recorded_camera = None
        else:
            self.picture.clear()
            self._update_controls()
        self.edits_changed()

    def record(self, keep_tick=False):
        """Record a private snapshot of the working edits; never save the imported effect files."""
        if self.effect_id is None or self.missing() or self._process is not None:
            self._update_controls()
            return False
        cast = self.cast(placed=True)
        model = cast.key()
        self._preview_requested = True
        edits = self.file_edits()
        signature = self._edit_signature(edits)
        # A recorder killed with the preview can still hold its output open: never fail on cleanup
        scratch = tempfile.TemporaryDirectory(prefix="fujin_preview_", ignore_cleanup_errors=True)
        self._scratch = scratch
        try:
            args, output, lines = self._recorder_args(cast, scratch.name)
        except (OSError, ValueError) as error:
            self._clean_scratch()
            self.status.setText(f"Could not prepare the preview: {error}")
            return False
        tick = self.slider.value() if keep_tick else 0
        self.timer.stop()
        self._prerender.stop()
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(RECORDER.parent))
        self._process.finished.connect(lambda code, _status, out=output, effect=self.effect_id, camera=lines:
                                       self._recorded(effect, out, code, signature, tick, model, camera))
        self._process.errorOccurred.connect(self._record_error)
        self.status.setText(f"Recording effect {self.effect_id}…")
        self._update_controls()
        self._process.start(str(RECORDER), args)
        return True

    def record_with(self, params):
        """The effect recorded now as the shown recording was, but with these parameters ({key:
        value}, the port's): waits for it (a few seconds); None when it cannot be made."""
        if self.effect_id is None or self.missing():
            return None
        cast = dataclasses.replace(self.cast(placed=True), params=tuple(sorted(params.items())))
        with tempfile.TemporaryDirectory(prefix="fujin_variant_", ignore_cleanup_errors=True) as folder:
            try:
                args, output, _lines = self._recorder_args(cast, folder)
                subprocess.run([str(RECORDER), *args], cwd=str(RECORDER.parent), capture_output=True, timeout=120,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return load_recording(output, self.effect_id) if os.path.isfile(output) else None
            except (OSError, ValueError, subprocess.SubprocessError):
                return None

    def _recorder_args(self, cast, folder):
        """(recorder arguments, output path, camera lines) of a recording of `cast`, its files
        staged in `folder`."""
        output = os.path.join(folder, "recording.txt")
        # The recorder reads only what was opened in Fujin: the effect's imported files as Fujin
        # holds them (unsaved edits included) and a8def.tim, staged privately; models by path
        effect_folder, battle_folder = Path(folder, "effect"), Path(folder, "battle")
        effect_folder.mkdir()
        battle_folder.mkdir()
        for name, data in self.effect_files().items():
            if name != os.path.basename(name) or name in ("", ".", ".."):
                raise ValueError(f"invalid effect file name: {name}")
            (effect_folder / name).write_bytes(data)
        if self.textures_binding.current_path:
            shutil.copyfile(self.textures_binding.current_path, battle_folder / SHARED_TEXTURES)
        # absolute paths: the recorder runs from its own folder
        args = [str(self.effect_id), f"exe={os.path.abspath(self.exe_path())}",
                f"magic={effect_folder}", f"battle={battle_folder}", f"out={output}"]
        # the cast: each slot's body (and weapon) through the game's own loaders, caster and target
        for slot, (body, weapon) in sorted(cast.slots.items()):
            args.append(f"slot{slot}={os.path.abspath(body)}")
            if weapon:
                args.append(f"weapon{slot}={os.path.abspath(weapon)}")
        args += [f"caster={cast.caster}", f"target={cast.target}"]
        # where the Camera tab's preview puts each actor (engine units; yaw in 4096ths of a turn)
        for slot, xyz in sorted(cast.positions.items()):
            args.append(f"pos{slot}={','.join(str(int(round(v))) for v in xyz)}")
            args.append(f"yaw{slot}={int(round(cast.yaws.get(slot, 0.0) / (2 * math.pi) * 4096)) & 4095}")
        if not cast.slots:
            args.append("model=-1")
        if cast.lab:
            args.append("actors=2")          # only the target drawn (untagged: part 0), no cast
        elif not cast.actors:
            args.append("actors=0")          # the effect alone: no cast either
        if cast.program:
            path = os.path.join(folder, "effect.fxprog")
            with open(path, "w", encoding="ascii") as file:
                file.write(cast.program)
            args.append(f"program={path}")   # the effect run from its description (its parameters in it)
        elif cast.native:
            args.append("native=1")          # the effect's C++ port (FFNx), with its parameters
        if cast.params and (cast.program or cast.native):
            path = os.path.join(folder, "params.txt")
            with open(path, "w", encoding="ascii") as file:
                # a file name as its text, an empty one (the game's) not at all
                file.write("".join(f"{key} {value if isinstance(value, str) else int(value)}\n"
                                   for key, value in cast.params if value != ""))
            args.append(f"params={path}")
        # what each actor plays (worked out from its dat's sequences, FF8GameData.dat.actoranimplan):
        # its idle loop, and the caster's cast before and while the effect runs, seen wide
        args += [f"idle{slot}={animation}" for slot, animation in sorted(cast.idle.items()) if slot in cast.slots]
        if cast.cast_before and cast.actors:
            args.append("castplan=" + _plan_text(cast.cast_before))
            eye, target = cast.cast_camera or (INITIAL_EYE, INITIAL_TARGET)
            args.append("castcam=" + ",".join(str(int(round(v))) for v in (*eye, *target)))
        if cast.cast_during and cast.actors:
            args.append("castafter=" + _plan_text(cast.cast_during))
        self._not_imported = cast.not_imported
        self.camera_used = False
        lines = self._camera_lines(cast)
        if lines:
            camera = output[:-4] + "_camera.txt"
            with open(camera, "w", encoding="ascii") as file:
                file.write("\n".join(lines) + "\n")
            args.append(f"camera={camera}")
            self.camera_used = True
        return args, output, lines

    def _clean_scratch(self):
        if self._scratch is not None:
            self._scratch.cleanup()
            self._scratch = None

    def _record_error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return  # a crash/exit is handled by finished
        message = self._process.errorString()
        self._process.deleteLater()
        self._process = None
        self._clean_scratch()
        self._update_controls()
        self.status.setText(f"Could not start the effect recorder: {message}")

    def _recorded(self, effect_id, output, code, signature=(), tick=0, model="none", camera=None):
        if sip.isdeleted(self) or (self._process is not None and sip.isdeleted(self._process)):
            # The preview is being destroyed with a recording running: Qt killed the recorder,
            # whose finished signal still arrives here. There is no view left to show it in.
            return
        process, self._process = self._process, None
        log = bytes(process.readAllStandardOutput()).decode("ascii", "replace") if process else ""
        if process is not None:
            process.deleteLater()
        try:
            self._load_recorded(effect_id, output, code, signature, tick, model, log, camera)
        finally:
            self._clean_scratch()

    def _load_recorded(self, effect_id, output, code, signature, tick, model, log, camera=None):
        if effect_id != self.effect_id:
            self._update_controls()
            self.edits_changed()
            return
        if signature != self._edit_signature(self.file_edits()):
            # Edits arrived during the run: draw only the newest snapshot.
            self._update_controls()
            self.edits_changed()
            return
        if not os.path.isfile(output) or (code != 0 and not os.path.getsize(output)):
            last = [line for line in log.splitlines() if line.strip()][-1:] or [f"exit code {code}"]
            self._update_controls()
            self.status.setText(f"The recorder made no recording: {last[0]}")
            return
        self.load_recording_file(output, tick=tick, signature=signature)
        self._recorded_camera = camera
        if not signature:
            # Shared cached recordings must never contain another editor's unsaved texture.
            try:
                shutil.copyfile(output, recording_path(effect_id, model))
                with open(camera_path(recording_path(effect_id, model)), "w", encoding="ascii") as file:
                    file.write("\n".join(camera or []))
            except OSError:
                pass  # caching is optional; the in-memory preview is already loaded
        if self.play_button.isChecked():
            self.timer.start()
        lines = log.splitlines()
        missing = sorted({line.split(" file ", 1)[1].split(" (")[0] for line in lines if line.startswith("missing ")})
        not_imported = getattr(self, "_not_imported", [])
        if not_imported:
            self.status.setText(self.status.text() + " Not drawn (not imported): " + ", ".join(not_imported) + ".")
        if missing:
            self.status.setText(self.status.text() + " Not imported, asked for by the effect: "
                                + ", ".join(os.path.basename(name) for name in missing) + ".")
        problems = [line for line in lines if "faulted" in line or "failed" in line]
        if problems:
            self.status.setText(self.status.text() + " Recorder: " + "; ".join(problems[:3]))

    def params_changed(self):
        """The effect's parameters changed: a recording made with these is shown if there is one,
        else (when one was shown) it is made again."""
        if self.effect_id is None or self._process is not None:
            return
        shown = self.recording is not None or self._preview_requested
        effect_id, name = self.effect_id, self.effect_name
        self.effect_id = None
        self.set_effect(effect_id, name)
        if shown and self.recording is None:
            self.record()

    def load_recording_file(self, path, tick=0, signature=()):
        """Show a recording (made by Record, or any recorder / harness dump)."""
        self.recording = load_recording(path, self.effect_id)
        self.recording_changed.emit()
        self._recorded_edits = signature
        self._frames = {}
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.recording.ticks) - 1))
        self.slider.setValue(min(tick, self.slider.maximum()))
        self.slider.blockSignals(False)
        self._fit = self.recording.fit_view()
        self._show(self.slider.value())
        self._prerender_tick = 0
        if self.isVisible():            # drawing every tick takes seconds: only for a shown view
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
            image, gpu = self.recording.frame(tick, view=view, scale=scale, renderer=gl_renderer())
            height, width = image.shape[:2]
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            self._frames[key] = (QPixmap.fromImage(qimage), gpu)
        return self._frames[key]

    def _prerender_step(self):
        if self.recording is None or self._prerender_tick >= len(self.recording.ticks) or not self.isVisible():
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
        if area.width() > 1 and area.height() > 1 and pixmap.size() != pixmap.size().scaled(
                area, Qt.AspectRatioMode.KeepAspectRatio):
            # fit the view whole, keeping the shape: larger, or smaller when the view is (its bottom
            # was cut by a smaller view)
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
        if self._recorded_edits:
            self.status.setText(self.status.text() + " Includes unsaved effect-file edits.")

    def showEvent(self, event):
        super().showEvent(event)
        self._take_battle_setup()
        if self.recording is not None and self._prerender_tick < len(self.recording.ticks):
            self._prerender.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.recording is not None:
            self._show(self.slider.value())

    def _toggle_play(self, playing):
        self.play_button.setText("Pause" if playing else "Play")
        if playing and self.recording is None and self._process is None and not self.record():
            self.play_button.setChecked(False)   # nothing to record yet: the status says what is missing
            return
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
        can_record = not needs and self.effect_id is not None and not busy
        for widget in (self.view_mode, self.slider):
            widget.setEnabled(recording and not busy)
        # Play records first when there is no recording yet
        self.play_button.setEnabled((recording or can_record) and not busy or self.play_button.isChecked())
        if needs and not recording:
            self.status.setText("To record, open: " + "; ".join(needs) + ".")
        elif not recording and not busy:
            self.status.setText("Play runs this effect's code (a second or less), then plays what it draws.")
