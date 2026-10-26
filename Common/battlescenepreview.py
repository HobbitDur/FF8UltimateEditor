"""A battle as an encounter sets it up, for any tool: the battle stage, the enemies standing on their
scene.out slots (playing their idle animation) and the party's places, under the free camera or
filmed by the encounter's intro camera.

The pieces are the battle previews' own: the stage is read as Alexander reads it, the models as the
camera previews read them (BattlePreviewSetup._load_model), the actors are placed and turned as
there (actor_from_model, resetBasedRotation: enemies face the party), the intro camera is played by
the battle camera player (play_camera_animation) from the stage's camera section (stagecamera), and
everything is drawn by Ifrit3D's GL canvas as one preview mesh.

Files: only the ones the host opened - file_source(name) gives the path of a0stgNNN.x / c0mNNN.dat
or None; nothing is looked up in a folder. A slot whose model is not opened is a post on the ground,
a stage not opened is a ground grid. Coordinates: battle (engine) space, +Y down; the stage's
vertices are in the viewer space of to_viewer() as read (checked over all 163 stages: the intro
cameras frame the stage, the scene.out slots stand on its floor).

Approximated: the intro camera's caster/target (an intro animation rarely uses them) are the
first enemy and the middle party member; the sky does not turn; the party has no models.
"""
import math
from dataclasses import replace
from time import perf_counter

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QComboBox, QCheckBox, QSizePolicy)

from FF8GameData.battlestage.battlestageanalyser import VERTEX_SCALE
from FF8GameData.battlestage.stagecamera import read_stage_camera, INTRO_CAMERA_NOTE
from FF8GameData.dat.battlecamera import BattleCameraContext, CameraActor, CameraPose, play_camera_animation
from FF8GameData.sceneout import NB_SLOT, ENEMY_ID_BASE

UNIT = VERTEX_SCALE            # viewer units per battle unit (the stage's own vertex scale)
MARKER_HEIGHT = 1500.          # battle units: about a party member's height
GRID_STEP = 1000.
GRID_HALF_SIZE = 8000.
ENEMY_YAW = math.pi            # resetBasedRotation (EN 502070): monsters 2048, the party 0
PARTY_SIZE = 3
FPS = 15
CAMERA_NAMES = ("Main", "Secondary")


def stage_file_name(stage_id):
    return f"a0stg{stage_id:03d}.x"


def model_file_name(com_id):
    return f"c0m{com_id:03d}.dat"


def to_viewer(point):
    """Battle space -> the GL canvas' viewer space (the camera previews' convention)."""
    return np.asarray(point, float) * np.array((-1., -1., 1.)) * UNIT


def _shifted(batches, offset):
    """A model's batches (built once, at vertex 0) for its place in the scene's vertex array."""
    return [replace(batch, indices=batch.indices + offset, normal_indices=batch.normal_indices + offset)
            for batch in batches]


class _Stage:
    """A battle stage read for the preview: its mesh in viewer space and its camera section."""

    def __init__(self, path, stage_id):
        from Alexander.alexandermanager import AlexanderManager
        from Alexander.alexanderwidget import StageTextureData
        from Ifrit.Ifrit3D.previewmesh import prepare_batches
        manager = AlexanderManager()
        manager.load_stage_file(path)
        manager.set_show_sky(True)   # the battle draws it
        self.vertices = np.asarray(manager.get_animated_vertices(0, 0), dtype=np.float32)
        textures = [StageTextureData(image) for image in manager.visible_textures()]
        self.batches = prepare_batches(manager.enemy.geometry_data, textures, False, 0)
        self.camera = read_stage_camera(path, stage_id)


class _Model:
    """A battle model read for the preview, posed on its animation 0 (idle) on demand."""

    def __init__(self, path, game_data):
        from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
        from Ifrit.Ifrit3D.previewmesh import prepare_batches
        self.manager = BattlePreviewSetup._load_model(path, game_data)
        enemy = self.manager.enemy
        self.batches = prepare_batches(enemy.geometry_data, self.manager.texture_data,
                                       self.manager.texture_black_is_transparent, 0)
        self.vertex_count = len(enemy.geometry_data.get_vertices())
        animations = enemy.animation_data.animations
        self.frame_count = max(1, len(animations[0].frames)) if animations else 1
        self._poses = {}

    def posed(self, tick):
        """Battle-space vertices at this tick, before the actor's own placement."""
        from Ifrit.IfritCameraSeq.battlepreview import model_root, model_scale
        frame = tick % self.frame_count
        if frame not in self._poses:
            vertices = np.asarray(self.manager.get_animated_vertices(0, frame)) + model_root(self.manager, 0, frame)
            self._poses[frame] = vertices * np.array((-1., -1., 1.)) * (model_scale(self.manager) / 2)
        return self._poses[frame]


class BattleScenePreview(QWidget):
    """The 3D battle preview. A host gives it an encounter (show_encounter) and where the opened
    battle files are (file_source); play_intro(0 / 1) films it with the main / secondary intro
    camera."""

    def __init__(self, game_data_folder="FF8GameData", parent=None):
        super().__init__(parent)
        self.setProperty("read_only_preview", True)   # its controls only look: never an edit (dirtytracking)
        self.file_source = lambda _name: None
        self._game_data_folder = game_data_folder
        self._game_data = None
        self._stages = {}           # path -> _Stage (or the error reading it)
        self._models = {}           # path -> _Model (or the error reading it)
        self._record = None
        self._encounter_index = None
        self._stage = None
        self._actors = []           # [(model, CameraActor, vertex slice)] drawn
        self._slots = {}            # battle slot -> CameraActor (the camera's references)
        self._mesh = None
        self._poses = []            # the intro camera, one pose per tick ([] = free camera)
        self._tick = 0
        self._clock_tick = 0
        self._play_origin = 0.
        self._advancing = False
        self._framed = None         # (encounter, stage) the free camera was last framed on

        from Ifrit.Ifrit3D.ff8openwidget import FF8OpenGLWidget
        self.gl = FF8OpenGLWidget()
        self.gl.show_axis = False
        self.gl.setMinimumSize(320, 240)
        self.gl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.camera_mode = QComboBox()
        self.camera_mode.addItems(["Free camera"] + [f"{name} intro camera" for name in CAMERA_NAMES])
        self.camera_mode.setToolTip("Free camera: orbit with the mouse. An intro camera plays the "
                                    "camera the battle starts with.\n\n" + INTRO_CAMERA_NOTE)
        self.camera_mode.currentIndexChanged.connect(self._camera_mode_changed)
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self._toggle_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._on_slider)
        self.tick_label = QLabel("0 / 0")
        self.animate = QCheckBox("Animate")
        self.animate.setChecked(True)
        self.animate.setToolTip("The enemies play their idle animation (animation 0)")
        self.animate.toggled.connect(self._animate_toggled)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: gray")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)

        controls = QHBoxLayout()
        controls.addWidget(self.camera_mode)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.tick_label)
        controls.addWidget(self.animate)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gl, 1)
        layout.addLayout(controls)
        layout.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)   # the wall clock selects the 15 Hz battle tick
        self._timer.timeout.connect(self._advance)
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(30)   # typing a position rebuilds once, not per digit
        self._rebuild_timer.timeout.connect(self._rebuild)
        self._update_controls()

    # --- Host side ---

    def show_encounter(self, record, index=None):
        """Show an encounter (an FF8GameData.sceneout.EncounterRecord, read as it is now)."""
        self._record = record
        self._encounter_index = index
        self._rebuild_timer.start()

    def files_changed(self):
        """The host's opened battle files changed: read the scene again."""
        self._rebuild_timer.start()

    def play_intro(self, camera_index):
        """Film the encounter with its main (0) or secondary (1) intro camera, from the start."""
        if self.camera_mode.currentIndex() != camera_index + 1:
            self.camera_mode.setCurrentIndex(camera_index + 1)   # -> _camera_mode_changed
        else:
            self._rebuild()
        self.slider.setValue(0)
        if self._poses:
            self._start_playback()

    # --- Files ---

    def _game_data_loaded(self):
        if self._game_data is None:
            from FF8GameData.gamedata import GameData
            self._game_data = GameData(self._game_data_folder)
            self._game_data.load_all()
        return self._game_data

    def _read(self, cache, name, reader):
        """The opened file `name` read by reader (cached by path), None when not opened; an error
        reading it is returned as a string."""
        path = self.file_source(name)
        if not path:
            return None
        path = str(path)
        if path not in cache:
            try:
                cache[path] = reader(path)
            except Exception as error:  # a file the preview cannot read: say so, draw the rest
                cache[path] = f"{name}: {error}"
        return cache[path]

    # --- Scene ---

    def _rebuild(self):
        if self._record is None:
            self.gl.set_preview_actor(None)
            self.gl.set_preview_slot_markers()
            self.status.setText("No encounter.")
            return
        record, notes = self._record, []
        stage_id = record.stage_id
        stage = self._read(self._stages, stage_file_name(stage_id), lambda path: _Stage(path, stage_id))
        if isinstance(stage, str):
            notes.append(stage)
            stage = None
        elif stage is None:
            notes.append(f"{stage_file_name(stage_id)} not opened: a ground grid")
        self._stage = stage

        vertices = [stage.vertices] if stage is not None else []
        batches = list(stage.batches) if stage is not None else []
        offset = len(stage.vertices) if stage is not None else 0
        self._actors, self._slots, markers = [], {}, []
        for slot_index in range(NB_SLOT):
            if not record.slot_flag("enabled", slot_index):
                continue
            position = record.position(slot_index)
            enemy_byte = record.enemy_byte(slot_index)
            name = model_file_name(enemy_byte - ENEMY_ID_BASE) if enemy_byte >= ENEMY_ID_BASE else None
            model = None
            if name and not record.slot_flag("not_loaded", slot_index):
                model = self._read(self._models, name, lambda path: _Model(path, self._game_data_loaded()))
                if isinstance(model, str):
                    notes.append(model)
                    model = None
                elif model is None and name not in notes:
                    notes.append(name)
            if model is not None:
                from Ifrit.IfritCameraSeq.battlepreview import actor_from_model
                actor = actor_from_model(model.manager, position, ENEMY_YAW, animate=True)
            else:
                actor = CameraActor(position, ENEMY_YAW)
            self._slots[3 + slot_index] = actor
            if model is not None and not record.slot_flag("not_visible", slot_index):
                vertices.append(np.empty((model.vertex_count, 3), dtype=np.float32))
                batches += _shifted(model.batches, offset)
                self._actors.append((model, actor, slice(offset, offset + model.vertex_count)))
                offset += model.vertex_count
            elif model is None:
                markers.append(position)
        from Ifrit.IfritCameraSeq.battlepreview import PARTY_FORMATIONS
        for party_slot, position in enumerate(PARTY_FORMATIONS[PARTY_SIZE]):
            self._slots[party_slot] = CameraActor(position)
            markers.append(position)
        missing = [note for note in notes if note.endswith(".dat")]
        notes = [note for note in notes if not note.endswith(".dat")]
        if missing:
            notes.append(", ".join(missing) + " not opened: posts on the ground")

        if vertices:
            from Ifrit.Ifrit3D.previewmesh import PreviewMesh
            self._mesh = PreviewMesh(np.vstack(vertices).astype(np.float32), batches)
        else:
            self._mesh = None
        self.gl.set_preview_slot_markers([to_viewer(point) for point in markers], MARKER_HEIGHT * UNIT,
                                         None if stage is not None else GRID_HALF_SIZE * UNIT, GRID_STEP * UNIT)
        self._build_camera(notes)
        title = f"Encounter {self._encounter_index} · " if self._encounter_index is not None else ""
        self.status.setText(title + f"stage {stage_id} · party: posts (3 members)"
                            + ("" if not notes else " · " + "; ".join(notes)))
        if not self._poses:   # nothing to film with: the orbit camera
            self.gl.letterbox_color = None
            self.gl.clear_explicit_camera()
        self._apply(min(self._tick, max(0, len(self._poses) - 1)))
        if not self._poses:
            key = (self._encounter_index, stage_id)
            if key != self._framed:
                self._frame_free_camera()
                self._framed = key

    def _pose_actors(self, tick):
        if self._mesh is None:
            return
        animate = self.animate.isChecked()
        for model, actor, dest in self._actors:
            engine = model.posed(tick if animate else 0) @ actor.rotation.T + np.asarray(actor.position, float)
            self._mesh.vertices[dest] = to_viewer(engine)

    # --- Camera ---

    def _camera_index(self):
        return self.camera_mode.currentIndex() - 1   # -1 = free camera

    def _build_camera(self, notes):
        self._poses = []
        index = self._camera_index()
        if index < 0:
            return
        camera_byte = self._record.camera_byte(index)
        camera_set, camera_anim = camera_byte >> 4, camera_byte & 0x07
        name = f"{CAMERA_NAMES[index].lower()} intro camera (set {camera_set}, anim {camera_anim})"
        if self._stage is None:
            notes.append(f"the {name} needs the stage file")
            return
        animation = self._stage.camera.intro_animation(camera_byte)
        if animation is None:
            notes.append(f"the {name} plays nothing: the stage has {self._stage.camera.set_count} "
                         "camera set(s), the battle keeps the default camera")
            return
        enemies = [actor for slot, actor in sorted(self._slots.items()) if slot >= 3]
        caster = enemies[0] if enemies else CameraActor()
        context = BattleCameraContext(caster, self._slots.get(1, CameraActor()),
                                      CameraPose((-4000., -2500., -7000.), (0., -500., 2500.)), self._slots)
        self._poses = play_camera_animation(animation, context)
        if not self._poses:
            notes.append(f"the {name} is empty")
        elif context.warnings:
            notes.append("; ".join(sorted(context.warnings)))

    def _camera_mode_changed(self):
        self._timer.stop()
        self._tick = 0
        self._rebuild()
        if not self._poses:
            self.gl.letterbox_color = None
            self.gl.clear_explicit_camera()
            self._frame_free_camera()
        self._update_controls()
        self.slider.setValue(0)

    def _frame_free_camera(self):
        """The orbit camera on the whole field: every slot, the enemies at their full size (a Jumbo
        Cactuar is several times a party member), seen from behind the party."""
        points = [to_viewer(actor.position) for actor in self._slots.values()] or [np.zeros(3)]
        if self._mesh is not None:
            points += [self._mesh.vertices[dest] for _model, _actor, dest in self._actors]
        points = np.vstack(points)
        low, high = points.min(axis=0), points.max(axis=0)
        self.gl.set_reference_position(*((low + high) / 2))
        self.gl.zoom = max(float(np.max(high - low)) * 1.5, 6.)
        self.gl.rot_x, self.gl.rot_y = 25., 0.   # 0: from the party's side (+Z), the enemies ahead
        self.gl.pan_x = self.gl.pan_y = 0.
        self.gl.update()

    # --- Playback ---

    def _update_controls(self):
        total = max(0, len(self._poses) - 1)
        self.slider.blockSignals(True)
        self.slider.setRange(0, total)
        self.slider.blockSignals(False)
        camera = bool(self._poses)
        self.slider.setEnabled(camera)
        self.tick_label.setText(f"{self.slider.value()} / {total}")
        self.play_button.setText("⏸ Pause" if self._timer.isActive() else "▶ Play")

    def _apply(self, tick):
        self._tick = tick
        self._pose_actors(tick)
        self.gl.set_preview_actor(self._mesh)
        if self._poses:
            pose = self._poses[min(tick, len(self._poses) - 1)]
            angle = pose.roll * 2 * math.pi / 4096
            self.gl.letterbox_color = (0., 0., 0., 1.)
            self.gl.set_camera(to_viewer(pose.eye), to_viewer(pose.target),
                               (-math.sin(angle), math.cos(angle), 0.), projection=pose.projection)
        self.gl.update()
        self._update_controls()

    def _toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
        else:
            if self._poses and self.slider.value() >= self.slider.maximum():
                self.slider.setValue(0)
            self._start_playback()
        self._update_controls()

    def _start_playback(self):
        self._clock_tick = self.slider.value() if self._poses else self._tick
        self._play_origin = perf_counter()
        self._timer.start()
        self._update_controls()

    def _advance(self):
        due = self._clock_tick + int((perf_counter() - self._play_origin) * FPS)
        if not self._poses:                  # free camera: the enemies' animation loops
            if due != self._tick:
                self._apply(due)
            return
        tick = min(due, self.slider.maximum())
        if tick != self.slider.value():
            self._advancing = True
            try:
                self.slider.setValue(tick)
            finally:
                self._advancing = False
        if due > self.slider.maximum():      # the last pose is held, then playback stops
            self._timer.stop()
            self._update_controls()

    def _on_slider(self, value):
        if not self._advancing and self._timer.isActive():
            self._clock_tick, self._play_origin = value, perf_counter()
        self._apply(value)

    def _animate_toggled(self, checked):
        if checked and not self._poses and not self._timer.isActive():
            self._start_playback()
        self._apply(self._tick)

    def showEvent(self, event):
        super().showEvent(event)
        if self.animate.isChecked() and not self._poses and not self._timer.isActive():
            self._start_playback()   # the enemies idle while the preview is shown

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)
