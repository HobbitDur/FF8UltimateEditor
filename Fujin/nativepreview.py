"""Fujin's Overview > Effect preview: what an effect whose behaviour is compiled in the exe
(Cure, Fire, most spells and enemy attacks) draws, frame by frame, from the game's own code, in
the battle the Camera tab's preview sets up (party, encounter or monsters, caster and target).

FF8UltimateEditor's effect recorder (Tools/fxrecorder, a small 32-bit program shipped with the
release; from source, build it with Tools/fxrecorder/build.bat) maps the opened FF8_EN.exe, fakes a
battle and runs the effect's ORIGINAL code tick by tick, recording every PlayStation GPU packet it
queues and every texture it uploads (FF8GameData.psxgpu.fxdump). Play runs it for the selected
effect when there is no recording yet (Record again runs it anew), then draws the recording at the
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
import hashlib
import math
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCursor, QImage, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
                             QVBoxLayout, QWidget)

from Common.apppaths import app_path
from Common.filebinding import FileBinding
from FF8GameData.psxgpu.fxdump import load_recording
from FF8GameData.psxgpu.gpu import GAME_WINDOW

RECORDER = app_path("Tools", "fxrecorder", "fxrecorder.exe")
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

    def key(self):
        """The cache tag of this cast: its files (where they are and their state on disk) and roles."""
        parts = [f"c{self.caster}t{self.target}"]
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


class _BattleCombo(QComboBox):
    """A picker that sets the battle up (before_popup) the moment it is opened."""

    def __init__(self, before_popup):
        super().__init__()
        self._before_popup = before_popup

    def showPopup(self):
        self._before_popup()
        super().showPopup()


class NativePreviewView(QWidget):
    """providers: exe_path() -> the opened FF8_EN.exe; effect_files() -> {file name: bytes} of the
    effect's imported files as Fujin holds them (unsaved edits included);
    camera_track(effect_id) -> (camera manager, track) or (None, None);
    file_edits() -> {file name: unsaved bytes}, staged privately for the recorder;
    cast_source: the Camera tab's preview (its caster / target pickers are mirrored here and
    battle_cast() gives the battle), or None for the battle folder's test dummy."""

    def __init__(self, file_registry, exe_path=None, effect_files=None, camera_track=None, file_edits=None,
                 cast_source=None):
        super().__init__()
        self.effect_id, self.effect_name = None, ""
        self.recording = None
        self._frames = {}           # (tick, view mode) -> (QPixmap, Gpu)
        self._process = None
        self._scratch = None
        self._recorded_edits = None
        self._preview_requested = False
        self._edit_refresh = QTimer(self)
        self._edit_refresh.setSingleShot(True)
        self._edit_refresh.setInterval(250)
        self._edit_refresh.timeout.connect(self._refresh_edits)
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
        self.record_button = QPushButton("Record again")
        self.record_button.setToolTip("Run the effect's code again: Play records it the first time, and edits of "
                                      "its files refresh it by themselves; this is for what Fujin does not see "
                                      "change (a camera keyframe, the Camera tab's script inputs...)")
        self.record_button.clicked.connect(lambda: self.record())
        # the Camera tab preview's caster and target pickers, mirrored: one battle for both previews
        self.caster_combo, self.target_combo = QComboBox(), QComboBox()
        self.caster_combo.setToolTip("Who casts the effect: a party member, an enemy of the encounter or an "
                                     "imported monster (the Camera tab's preview: Import complementary, Camera "
                                     "preview models). Record again to apply.")
        self.target_combo.setToolTip("Who the effect is cast on. Record again to apply.")
        self.caster_combo.activated.connect(lambda _i: self._pick(self.caster_combo, "caster_combo"))
        self.target_combo.activated.connect(lambda _i: self._pick(self.target_combo, "target_combo"))
        # the Camera tab setup's scene.out encounter: enemies and party where that battle puts them
        self.encounter_combo = _BattleCombo(self._load_battle)
        self.encounter_combo.setToolTip("Where the actors stand: an encounter of scene.out (Import complementary: "
                                        "scene.out) puts the enemies where that battle has them and the party in "
                                        "its formation; Manual placement puts the target across from the caster. "
                                        "Same list as the Camera tab's preview. Record again to apply.")
        self.encounter_combo.activated.connect(lambda _i: self._pick_encounter())
        self._watched_encounters = None
        if cast_source is not None:
            for combo in (cast_source.caster_combo, cast_source.target_combo):
                combo.currentIndexChanged.connect(lambda _i: self._cast_refresh.start())
            cast_source.models_changed.connect(self._cast_refresh.start)
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
        cast_row = QHBoxLayout()
        cast_row.addWidget(QLabel("Battle:"))
        cast_row.addWidget(self.encounter_combo, 2)
        cast_row.addWidget(QLabel("Caster:"))
        cast_row.addWidget(self.caster_combo, 1)
        cast_row.addWidget(QLabel("Target:"))
        cast_row.addWidget(self.target_combo, 1)
        controls = QHBoxLayout()
        controls.addWidget(self.record_button)
        controls.addWidget(self.view_mode)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.frame_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(cast_row)
        layout.addLayout(controls)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.status)
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

    def refresh_cast(self):
        """Mirror the Camera tab preview's caster / target pickers; a new cast shows the recording
        already made with it, if any."""
        before = self.cast().key()
        for mine, name in ((self.caster_combo, "caster_combo"), (self.target_combo, "target_combo")):
            source = getattr(self.cast_source, name, None)
            mine.blockSignals(True)
            try:
                mine.clear()
                if source is None or source.count() == 0 or source.currentData() is None and source.count() == 1:
                    mine.addItem("(import models: Import complementary, Camera preview models)", None)
                else:
                    for index in range(source.count()):
                        mine.addItem(source.itemText(index), source.itemData(index))
                    mine.setCurrentIndex(source.currentIndex())
            finally:
                mine.blockSignals(False)
        self._refresh_encounters()
        if self.cast().key() != before:
            self._cast_changed()
        self._update_controls()          # a newly imported actor can make Record possible

    def _refresh_encounters(self):
        source = self.cast_source.encounter_combo() if self.cast_source is not None else None
        if source is not None and source is not self._watched_encounters:
            source.currentIndexChanged.connect(lambda _i: self._cast_refresh.start())
            self._watched_encounters = source
        combo = self.encounter_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            if source is None:
                combo.addItem("Manual placement (the battle is set up when a model is imported in the Camera "
                              "tab's preview)", None)
            elif source.count() <= 1:
                combo.addItem("Manual placement (Import complementary: scene.out for its encounters)", None)
            else:
                for index in range(source.count()):
                    combo.addItem(source.itemText(index), source.itemData(index))
                combo.setCurrentIndex(source.currentIndex())
        finally:
            combo.blockSignals(False)

    def _load_battle(self):
        """The encounter list is the Camera tab setup's: set the battle up first if it waits."""
        if self.cast_source is None:
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            self.cast_source.load_battle()
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_cast()

    def _pick_encounter(self):
        source = self.cast_source.encounter_combo() if self.cast_source is not None else None
        if source is None:
            return
        picked = self.encounter_combo.currentData()
        index = next((i for i in range(source.count()) if source.itemData(i) is picked), 0)
        source.setCurrentIndex(index)
        self.refresh_cast()

    def _pick(self, mine, name):
        """A pick here is the Camera tab preview's pick (it moves the other role when needed)."""
        source = getattr(self.cast_source, name, None)
        if source is None:
            return
        # the actor keys are Python tuples: compared here (QComboBox.findData does not match them)
        index = next((i for i in range(source.count()) if source.itemData(i) == mine.currentData()), -1)
        if index >= 0:
            source.setCurrentIndex(index)
        self.refresh_cast()

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
        return BattleCast(slots, cast.caster, cast.target, cast.positions, cast.yaws, cast.camera,
                          sorted(set(not_imported)))

    def _cast_changed(self):
        """Show the recording already made with this cast, if any."""
        if self.effect_id is None or self._process is not None:
            return
        effect_id, name = self.effect_id, self.effect_name
        self.effect_id = None
        self.set_effect(effect_id, name)

    def missing(self):
        """What Record still needs, in words ([] = ready)."""
        needs = []
        if not RECORDER.is_file():
            needs.append(f"the effect recorder ({RECORDER}; from source, run Tools/fxrecorder/build.bat)")
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
        self._recorded_edits = None
        self._preview_requested = False
        self._prerender.stop()
        self._prerender_tick = 0
        path = recording_path(effect_id, self.cast().key()) if effect_id is not None else None
        if path and os.path.isfile(path):
            self.load_recording_file(path)       # recorded earlier: shown again, Record redoes it
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
        scratch = tempfile.TemporaryDirectory(prefix="fujin_preview_")
        self._scratch = scratch
        output = os.path.join(scratch.name, "recording.txt")
        # The recorder reads only what was opened in Fujin: the effect's imported files as Fujin
        # holds them (unsaved edits included) and a8def.tim, staged privately; models by path
        effect_folder, battle_folder = Path(scratch.name, "effect"), Path(scratch.name, "battle")
        try:
            effect_folder.mkdir()
            battle_folder.mkdir()
            for name, data in self.effect_files().items():
                if name != os.path.basename(name) or name in ("", ".", ".."):
                    raise ValueError(f"invalid effect file name: {name}")
                (effect_folder / name).write_bytes(data)
            if self.textures_binding.current_path:
                shutil.copyfile(self.textures_binding.current_path, battle_folder / SHARED_TEXTURES)
        except (OSError, ValueError) as error:
            self._clean_scratch()
            self.status.setText(f"Could not prepare the preview: {error}")
            return False
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
        self._not_imported = cast.not_imported
        self.camera_used = False
        manager, track = self.camera_track(self.effect_id)
        if cast.camera is not None:
            lines = pose_lines(cast.camera)            # the Camera tab preview's own shot
        elif track is not None:
            lines = camera_lines(manager, track, cast)
        else:
            lines = []
        if lines:
            camera = output[:-4] + "_camera.txt"
            with open(camera, "w", encoding="ascii") as file:
                file.write("\n".join(lines) + "\n")
            args.append(f"camera={camera}")
            self.camera_used = True
        tick = self.slider.value() if keep_tick else 0
        self.timer.stop()
        self._prerender.stop()
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(RECORDER.parent))
        self._process.finished.connect(lambda code, _status, out=output, effect=self.effect_id:
                                       self._recorded(effect, out, code, signature, tick, model))
        self._process.errorOccurred.connect(self._record_error)
        self.status.setText(f"Recording effect {self.effect_id}…")
        self._update_controls()
        self._process.start(str(RECORDER), args)
        return True

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

    def _recorded(self, effect_id, output, code, signature=(), tick=0, model="none"):
        process, self._process = self._process, None
        log = bytes(process.readAllStandardOutput()).decode("ascii", "replace") if process else ""
        if process is not None:
            process.deleteLater()
        try:
            self._load_recorded(effect_id, output, code, signature, tick, model, log)
        finally:
            self._clean_scratch()

    def _load_recorded(self, effect_id, output, code, signature, tick, model, log):
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
        if not signature:
            # Shared cached recordings must never contain another editor's unsaved texture.
            try:
                shutil.copyfile(output, recording_path(effect_id, model))
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

    def load_recording_file(self, path, tick=0, signature=()):
        """Show a recording (made by Record, or any recorder / harness dump)."""
        self.recording = load_recording(path, self.effect_id)
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
        if self._recorded_edits:
            self.status.setText(self.status.text() + " Includes unsaved effect-file edits.")

    def showEvent(self, event):
        super().showEvent(event)
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
        self.record_button.setEnabled(can_record)
        self.record_button.setVisible(recording)        # the first recording is Play's
        for widget in (self.view_mode, self.slider):
            widget.setEnabled(recording and not busy)
        # Play records first when there is no recording yet
        self.play_button.setEnabled((recording or can_record) and not busy or self.play_button.isChecked())
        if needs and not recording:
            self.status.setText("To record, open: " + "; ".join(needs) + ".")
        elif not recording and not busy:
            self.status.setText("Play runs this effect's code (a second or less), then plays what it draws.")
