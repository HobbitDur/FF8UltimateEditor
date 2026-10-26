"""Read-only caster/target setup for the shared DAT camera preview.

A host (Ifrit's Camera tab, SolomonRing, Fujin's effect cameras) gives the model it films; the
setup places it with an opponent by hand or in a scene.out encounter. The other models are only
the ones the host's user opened one by one: `models` / `model_source` (file name -> manager: the
encounter's enemies, the default player), `party_models` (party slot -> (body, weapon)) and
`opponent_weapon`. Nothing is read from scene.out's folder or the loaded model's: an encounter
enemy whose file is not opened stays a marker at its scene.out place, named in the status. In an
encounter every battle slot is placed, and the caster/target slot spins pick any of them
(defaults: the loaded model and its opponent)."""
import math
from pathlib import Path

import numpy as np
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QSpinBox, QPushButton, QFileDialog, QSizePolicy)

from FF8GameData.dat.battlecamera import BattleCameraContext, CameraActor, CameraPose
from FF8GameData.monsterdata import EntityType
from Common.collapsiblesection import CollapsibleSection


# computeSomeStatusData (EN 47DBA0), table B81030..B81047. The game chooses
# a formation by occupied party count, then assigns entries in party-slot order.
PARTY_FORMATIONS = {
    1: ((0, 0, 1800),),
    2: ((-1000, 0, 1800), (1000, 0, 1800)),
    3: ((-1200, 0, 2100), (0, 0, 1500), (1200, 0, 2100)),
}


def model_scale(manager):
    raw = manager.enemy.section_raw_data[1]
    return max(1, int.from_bytes(raw[2:4], 'little'))


def model_root(manager, animation, tick):
    """Root in posed-vertex units. Engine root=raw*model_scale/256, vertex unit=model_scale/2."""
    frames = manager.enemy.animation_data.animations
    if not frames:
        return np.zeros(3)
    frames = frames[min(animation, len(frames) - 1)].frames
    if not frames:
        return np.zeros(3)
    pos = frames[tick % len(frames)].position
    return np.array([p.get_pos_raw() for p in pos[:3]]) * np.array((-1., -1., 1.)) / 128


def actor_from_model(manager, position=(0., 0., 0.), yaw=0., animation=0, animate=False):
    """Skeleton header F0..FE selectors match GetEffectSpawnPosition (EN 502170).

    The high bit picks the bone end; otherwise the camera uses its midpoint.
    Bone matrices are the same posed matrices already used by Ifrit3D.
    """
    scale = model_scale(manager)
    actor = CameraActor(position, yaw, scale / 512)
    raw = manager.enemy.section_raw_data[1]

    def anchor(selector, tick):
        if selector == 15:
            return np.asarray(position)
        frame = tick if animate else 0
        animations = manager.enemy.animation_data.animations
        count = len(animations[animation].frames) if animations else 0
        matrices = manager._get_bone_matrices(animation, frame % max(1, count))
        selected = raw[4 + selector] if 4 + selector < 16 else 0
        bone_id = selected & 127
        bones = manager.enemy.bone_data.bones
        if bone_id >= len(matrices) or bone_id >= len(bones):
            return np.asarray(position)
        m, bone = matrices[bone_id], bones[bone_id]
        length = 0 if bone.parent_id & 0x8000 else bone.get_size() * (1 if selected & 128 else .5)
        point = np.array((m.M41 + m.M13 * length, m.M42 + m.M23 * length,
                          m.M43 + m.M33 * length)) + model_root(manager, animation, frame)
        engine = point * np.array((-1., -1., 1.)) * (scale / 2)
        return np.asarray(position) + actor.rotation @ engine

    actor.anchor = anchor
    return actor


class BattlePreviewSetup(QWidget):
    changed = pyqtSignal()

    def __init__(self, manager, parent=None, file_registry=None, host_cast=False, model_view=False):
        """host_cast: the host tool feeds the actors and slots itself (Fujin's party, Caster and
        Target) and opens files from the header toolbar, so those controls are hidden here.
        model_view: no camera is played (Ifrit3D's battle view, a free camera on the encounter),
        so the camera-only controls - game/free camera, caster/target, starting view - are hidden."""
        super().__init__(parent)
        self.manager = manager
        self.host_cast = host_cast
        self.opponent = None
        self.context = None
        self._main = None               # the loaded model's actor, after build()
        self.unit = 1.
        self._asset_cache = {}
        self._scene_mesh_actors = []
        self._scene_weapons = []        # [(weapon manager, actor, body manager)] drawn with the scene
        self._mesh = None
        self._pose_cache = {}
        self.main_position = (0., 0., 0.)
        self.main_yaw = 0.
        self.models = {}                # lower-case file name -> manager imported by the host
        # or a callable: lower-case file name -> a manager or the path of a file the host opened
        # (its model list), None when not opened
        self.model_source = None
        self.party_models = {}          # party slot -> (body manager, weapon manager or None)
        self.opponent_weapon = None     # weapon of a character opponent (manual / monster encounters)
        self._kind = None               # whether the defaults below were set for a monster
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.view_mode = QComboBox()
        self.view_mode.addItems(['Game camera', 'Free camera'])
        self.view_mode.setToolTip('Free camera: orbit with the mouse to inspect the scene.')
        row.addWidget(self.view_mode)
        self.group = CollapsibleSection('Battle setup', expanded=False)
        self.group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.options = QWidget()
        self.group.content_layout().addWidget(self.options)
        layout.addLayout(row)
        layout.addWidget(self.group)
        options = QVBoxLayout(self.options)
        options.setContentsMargins(0, 0, 0, 0)
        from .encounterpreview import EncounterPicker
        self.encounters = EncounterPicker(manager, file_registry, host_cast=host_cast)
        self.encounters.changed.connect(self._encounter_changed)
        options.addWidget(self.encounters)
        party_row = QHBoxLayout()
        party_row.addWidget(QLabel('Party size:'))
        self.party_size = QSpinBox()
        self.party_size.setRange(1, 3)
        self.party_size.setValue(3)
        party_row.addWidget(self.party_size)
        party_row.addWidget(QLabel('Player slot:'))
        self.party_slot = QSpinBox()
        self.party_slot.setRange(0, 2)
        self.party_slot.setToolTip('Zero-based party order. Uses the game\'s normal battle formation.')
        party_row.addWidget(self.party_slot)
        options.addLayout(party_row)
        self.party_size.valueChanged.connect(self._party_changed)
        self.party_slot.valueChanged.connect(lambda _v: self._roles_changed())
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel('Loaded model:'))
        self.role = QComboBox()
        self.role.addItems(['Caster', 'Target'])
        role_row.addWidget(self.role)
        options.addLayout(role_row)
        slot_row = QHBoxLayout()
        self.caster_slot, self.target_slot = QSpinBox(), QSpinBox()
        is_monster = getattr(self.manager.enemy.entity_type, 'name', '').startswith('MONSTER')
        self._kind = is_monster
        for label, spin, default in (('Caster slot:', self.caster_slot, 3 if is_monster else 0),
                                     ('Target slot:', self.target_slot, 0 if is_monster else 3)):
            spin.setRange(0, 10)
            spin.setValue(default)
            spin.setToolTip('Battle slot: party 0-2, enemies 3-10. In an encounter, any placed slot.')
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            slot_row.addWidget(QLabel(label))
            slot_row.addWidget(spin)
        options.addLayout(slot_row)
        # The label on its own line: beside the three spins it was cut off in a narrow panel
        self.position_label = QLabel('Opponent position:')
        options.addWidget(self.position_label)
        position_row = QHBoxLayout()
        self.position = []
        for axis, default in zip('XYZ', (0, 0, 5000 if is_monster else -5000)):
            position_row.addWidget(QLabel(axis))
            spin = QSpinBox()
            spin.setRange(-30000, 30000)
            spin.setValue(default)
            spin.setSingleStep(250)
            spin.setKeyboardTracking(False)
            spin.setToolTip('Battle world units; Y points down. Preview placement only.')
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            position_row.addWidget(spin)
            self.position.append(spin)
        options.addLayout(position_row)
        initial_row = QHBoxLayout()
        initial_row.addWidget(QLabel('Starting view:'))
        self.initial_view = QComboBox()
        self.initial_view.addItems(['Battle overview', 'Loaded model'])
        initial_row.addWidget(self.initial_view)
        options.addLayout(initial_row)
        import_row = QHBoxLayout()
        load = QPushButton('Load opponent…')
        clear = QPushButton('Clear')
        self.opponent_buttons = (load, clear)
        load.clicked.connect(self._choose_opponent)
        clear.clicked.connect(self._clear_opponent)
        import_row.addWidget(load)
        import_row.addWidget(clear)
        options.addLayout(import_row)
        self.status = QLabel('Opponent model not loaded. Manual placement.')
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)  # never clipped
        options.addWidget(self.status)
        if host_cast:
            for host_row in (party_row, role_row, slot_row, import_row):
                for index in range(host_row.count()):
                    if host_row.itemAt(index).widget() is not None:
                        host_row.itemAt(index).widget().hide()
            self.status.hide()
        if model_view:
            self.view_mode.setCurrentIndex(1)
            for camera_row in (row, role_row, slot_row, initial_row):
                for index in range(camera_row.count()):
                    if camera_row.itemAt(index).widget() is not None:
                        camera_row.itemAt(index).widget().hide()
        self.role.currentIndexChanged.connect(lambda _value: self._roles_changed())
        self.initial_view.currentIndexChanged.connect(lambda _value: self.changed.emit())
        self.view_mode.currentIndexChanged.connect(lambda _value: self.changed.emit())

    def _party_changed(self, value):
        self.party_slot.blockSignals(True)
        self.party_slot.setMaximum(value - 1)
        self.party_slot.blockSignals(False)
        self._roles_changed()

    def _roles_changed(self):
        self.reset_encounter_slots()
        self.changed.emit()

    def _encounter_changed(self):
        active = self.encounters.selected is not None
        for spin in self.position:
            spin.setEnabled(not active)
        self.position_label.setEnabled(not active)
        for button in self.opponent_buttons:
            button.setEnabled(not active or self.encounters.is_monster)
            button.setToolTip('Load a party stand-in for a monster preview. Encounter enemies are the opened models.')
        self.reset_encounter_slots()
        self.changed.emit()

    def encounter_roles(self):
        """(loaded model's slot, opponent's slot) in the selected encounter, or None."""
        selected = self.encounters.selected_slot
        if self.encounters.selected is None or selected is None:
            return None
        enemy, player = 3 + selected.slot_index, self.party_slot.value()
        return (enemy, player) if self.encounters.is_monster else (player, enemy)

    def reset_encounter_slots(self):
        """Point the caster/target slot spins at the loaded model and its opponent (by the role)
        when the encounter, the loaded model's slot or the role changes. They stay editable."""
        roles = self.encounter_roles()
        if roles is None:
            return
        ids = roles if self.role.currentIndex() == 0 else roles[::-1]
        for spin, value in zip((self.caster_slot, self.target_slot), ids):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _sync_kind(self):
        """The loaded model changed kind (monster <-> character): the opponent stands on the
        other side and the default slots swap, as for a setup built for that kind."""
        is_monster = self.encounters.is_monster
        if is_monster == self._kind:
            return
        self._kind = is_monster
        defaults = [(self.position[2], 5000 if is_monster else -5000)]
        if self.encounter_roles() is None and not self.host_cast:  # an encounter / the host sets them
            defaults += [(self.caster_slot, 3 if is_monster else 0), (self.target_slot, 0 if is_monster else 3)]
        for spin, value in defaults:
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    @staticmethod
    def _load_model(path, game_data, weapon=False):
        """A read-only model with its textures. weapon=True also accepts the reduced weapons
        with no skeleton of their own (Zell's gloves: posed by the body's bones)."""
        from Ifrit.ifritmanager import IfritManager
        manager = IfritManager(game_data=game_data)
        manager.enemy = manager.parse_file(str(path))
        reduced = weapon and manager.enemy.entity_type == EntityType.WEAPON_NO_ANIM
        if not reduced and (not manager.enemy.bone_data.bones or not manager.enemy.animation_data.nb_animations):
            raise ValueError('select a monster or character with skeletal animations')
        manager._ensure_matrices()
        manager.texture_data, manager.texture_black_is_transparent = manager.extract_textures(manager.enemy, str(path))
        return manager

    def _choose_opponent(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load preview opponent (read-only)', '', 'Battle models (*.dat)')
        if path:
            self.load_opponent(path)

    def load_opponent(self, path):
        try:
            manager = self._load_model(path, self.manager.game_data)
        except Exception as error:
            self.status.setText(f'Cannot load opponent: {error}')
            return False
        self.opponent = manager
        self.status.setText(f'Opponent: {Path(path).name}. Preview placement.')
        self.changed.emit()
        return True

    def _clear_opponent(self):
        self.opponent = None
        self.status.setText('Opponent model not loaded. Manual placement.')
        self.changed.emit()

    def build(self, animation=0, animate=False):
        self.unit = 2 / model_scale(self.manager)
        self._scene_mesh_actors = []
        self._scene_weapons = []
        self._mesh = None
        self._pose_cache = {}
        self.main_position, self.main_yaw = (0., 0., 0.), 0.
        self._sync_kind()
        if self.encounters.selected is not None and self.encounters.selected_slot is not None:
            return self._build_encounter(animation, animate)
        self.status.setText('Opponent: ' + (f'{self.opponent.enemy.origin_file_name}.'
                            if self.opponent else 'model not loaded.') + ' Manual placement.')
        self.main_yaw = math.pi if self.encounters.is_monster else 0.
        other_yaw = 0. if self.encounters.is_monster else math.pi
        main = actor_from_model(self.manager, yaw=self.main_yaw, animation=animation, animate=animate)
        self._main = main
        position = tuple(spin.value() for spin in self.position)
        ids = (self.caster_slot.value(), self.target_slot.value())
        main_id, other_id = ids if self.role.currentIndex() == 0 else ids[::-1]
        same_side = main_id != other_id and (main_id < 3) == (other_id < 3)
        formation, origin = None, np.zeros(3)
        if main_id < 3:
            # The party stands in the game's formation, every member facing the enemies (yaw 0):
            # the loaded model at the origin, the others where the formation puts them
            size = max(self.party_size.value(), main_id + 1, other_id + 1 if other_id < 3 else 0)
            formation = PARTY_FORMATIONS[min(3, size)]
            origin = np.asarray(formation[main_id], float)
        if same_side:
            # Two allies (a party member casting on another, a monster on a monster): side by
            # side, looking the same way - not face to face
            other_yaw = self.main_yaw
            position = (tuple((np.asarray(formation[other_id], float) - origin).tolist()) if formation else
                        (1600. if other_id > main_id else -1600., 0., 0.))
            self.status.setText(self.status.text().replace('Manual placement.', 'Manual placement: allies side by '
                                                           'side (battle formation).' if formation else
                                                           'Manual placement: allies side by side.'))
        if main_id == other_id:                 # the caster targets itself
            other = main
        else:
            other = (actor_from_model(self.opponent, position, other_yaw, animate=animate)
                     if self.opponent is not None else CameraActor(position, other_yaw))
            if self.opponent is None:
                other.anchor = lambda selector, tick: np.asarray(position) + np.array((0., -800. if selector == 0 else -400., 0.))
        caster, target = (main, other) if self.role.currentIndex() == 0 else (other, main)
        centre = (main.point(0, 0) + other.point(0, 0)) / 2
        if self.initial_view.currentIndex() == 1:
            centre = main.point(0, 0)
        eye = centre + np.array((-4000., -2000., -7000.))
        slots = {self.caster_slot.value(): caster, self.target_slot.value(): target}
        if formation is not None:
            # the host's other party members in their formation places, for context
            for party_slot, (body, weapon) in self.party_models.items():
                if party_slot in slots or party_slot >= len(formation) or body is None:
                    continue
                actor = actor_from_model(body, tuple((np.asarray(formation[party_slot], float) - origin).tolist()),
                                         animate=animate)
                self._scene_mesh_actors.append((body, actor))
                if weapon is not None:
                    self._scene_weapons.append((weapon, actor, body))
                slots[party_slot] = actor
        self.context = BattleCameraContext(caster, target, CameraPose(tuple(eye), tuple(centre)), slots)
        self._other = other
        if self.opponent is not None and other is not main:
            self._scene_mesh_actors.append((self.opponent, other))
            if self.opponent_weapon is not None:
                self._scene_weapons.append((self.opponent_weapon, other, self.opponent))
        return self.context

    def _asset(self, name):
        """The model of a file the host opened (`models`, then `model_source`), or None: never a
        file looked up in a folder."""
        if name.lower() in self.models:  # imported by the host
            return self.models[name.lower()]
        found = self.model_source(name.lower()) if self.model_source is not None else None
        if found is None or not isinstance(found, (str, Path)):
            return found
        path = Path(found)
        key = (path, path.stat().st_mtime_ns)
        if key not in self._asset_cache:
            manager = self._load_model(path, self.manager.game_data)
            # Keep revisiting encounters cheap without retaining an entire battle
            # archive's expanded skeletons over a long editing session.
            if len(self._asset_cache) >= 16:
                self._asset_cache.pop(next(iter(self._asset_cache)))
            self._asset_cache[key] = manager
        return self._asset_cache[key]

    def _build_encounter(self, animation, animate):
        encounter, selected = self.encounters.selected, self.encounters.selected_slot
        monster = self.encounters.is_monster
        player_slot = self.party_slot.value()
        player_position = PARTY_FORMATIONS[self.party_size.value()][player_slot]
        self.main_position = selected.position if monster else player_position
        # resetBasedRotation (EN 502070): party=0, monster=2048.
        self.main_yaw = math.pi if monster else 0.
        main = actor_from_model(self.manager, self.main_position, self.main_yaw, animation, animate)
        self._main = main
        slots, notes = {}, []
        for slot in encounter.enabled_slots():
            if monster and slot.slot_index == selected.slot_index:
                actor, manager = main, None
            else:
                name = f'c0m{slot.com_file_id:03}.dat'
                try:
                    manager = (self.manager if monster and slot.com_file_id == self.manager.enemy.id else
                               self._asset(name)) if slot.loaded else None
                    if manager is None:
                        notes.append(f'{name}: not imported (a marker)' if slot.loaded else
                                     f'{name}: not initially loaded')
                except Exception as error:
                    manager = None
                    notes.append(f'{name}: {error}')
                actor = (actor_from_model(manager, slot.position, math.pi, animate=animate) if manager else
                         CameraActor(slot.position, math.pi))
                if manager is not None and slot.loaded and slot.visible:
                    self._scene_mesh_actors.append((manager, actor))
            slots[3 + slot.slot_index] = actor
        party = dict(self.party_models)
        if monster and player_slot not in party:
            player = self.opponent
            if player is None:
                try:
                    player = self._asset('d0c000.dat')
                except Exception as error:
                    notes.append(f'Player model: {error}')
            party[player_slot] = (player, self.opponent_weapon if player is self.opponent else None)
            if player is None:
                notes.append('Player: d0c000.dat not imported (a marker); load a player DAT')
        for party_slot, position in enumerate(PARTY_FORMATIONS[self.party_size.value()]):
            if not monster and party_slot == player_slot:
                slots[party_slot] = main
                continue
            body, weapon = party.get(party_slot, (None, None))
            actor = actor_from_model(body, position, animate=animate) if body else CameraActor(position)
            if body is not None:
                self._scene_mesh_actors.append((body, actor))
                if weapon is not None:
                    self._scene_weapons.append((weapon, actor, body))
            slots[party_slot] = actor
        main_slot, other_slot = self.encounter_roles()
        defaults = (main_slot, other_slot) if self.role.currentIndex() == 0 else (other_slot, main_slot)
        # The spins pick any placed slot; one naming an empty slot falls back to its default
        ids = tuple(spin.value() if spin.value() in slots else default
                    for spin, default in zip((self.caster_slot, self.target_slot), defaults))
        for spin, value in zip((self.caster_slot, self.target_slot), ids):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        caster, target = slots[ids[0]], slots[ids[1]]
        other = target if caster is main else caster
        centre = (main.point(0, 0) + other.point(0, 0)) / 2
        if self.initial_view.currentIndex() == 1:
            centre = main.point(0, 0)
        eye = centre + np.array((-4000., -2000., -7000.))
        self.context = BattleCameraContext(caster, target, CameraPose(tuple(eye), tuple(centre)), slots)
        self._other = other
        self.encounters.status.setText(
            f'Encounter {encounter.index}. Party {self.party_size.value()}, player slot {player_slot}: '
            f'{player_position}. ' + '; '.join(notes))
        self.status.setText('Player: the loaded opponent, else an opened d0c000.dat.' if monster else
                            'Enemies: the opened models of the encounter; the others are markers.')
        return self.context

    def marker_positions(self):
        """Battle positions of the slots placed but not drawn (no model opened for them), after
        build(): the loaded model and the drawn actors are left out."""
        if self.context is None:
            return []
        drawn = {id(actor) for _manager, actor in self._scene_mesh_actors} | {id(self._main)}
        return [actor.position for _slot, actor in sorted(self.context.slots.items()) if id(actor) not in drawn]

    def to_viewer(self, point):
        return np.asarray(point) * np.array((-1., -1., 1.)) * self.unit

    def opponent_mesh(self, tick=0, animate=False):
        if not self._scene_mesh_actors and not self._scene_weapons:
            return None
        if self._mesh is None:
            from Ifrit.Ifrit3D.previewmesh import PreviewMesh, prepare_batches
            batches, self._mesh_slices, offset = [], [], 0
            drawn = ([(manager, actor, None) for manager, actor in self._scene_mesh_actors]
                     + list(self._scene_weapons))
            for manager, actor, body in drawn:
                count = len(manager.enemy.geometry_data.get_vertices())
                batches.extend(prepare_batches(manager.enemy.geometry_data, manager.texture_data,
                                               manager.texture_black_is_transparent, offset))
                self._mesh_slices.append((manager, actor, body, slice(offset, offset + count)))
                offset += count
            self._mesh = PreviewMesh(np.empty((offset, 3), dtype=np.float32), batches)
        for manager, actor, body, dest in self._mesh_slices:
            key = (id(manager), id(body), self._pose_frame(body or manager, tick, animate))
            if key not in self._pose_cache:
                if len(self._pose_cache) >= 120:
                    self._pose_cache.pop(next(iter(self._pose_cache)))
                self._pose_cache[key] = self._posed(manager, body, tick, animate)
            engine = self._pose_cache[key]
            engine = engine @ actor.rotation.T + actor.position
            self._mesh.vertices[dest] = self.to_viewer(engine)
        return self._mesh

    @staticmethod
    def _pose_frame(manager, tick, animate):
        animations = manager.enemy.animation_data.animations
        count = len(animations[0].frames) if animations else 0
        return tick % max(1, count) if animate else 0

    def _posed(self, manager, body, tick, animate):
        """Engine-space vertices of a scene model on animation 0, before its actor transform.

        Each model is placed by its own root (a weapon's root track is the hand: see
        Ifrit3DWidget._current_attached_verts); a reduced weapon (no skeleton) is posed by the
        body's bones at the body's frame."""
        if body is not None and manager.enemy.entity_type == EntityType.WEAPON_NO_ANIM:
            frame = self._pose_frame(body, tick, animate)
            vertices = (np.asarray(body.get_animated_vertices(0, frame, geometry=manager.enemy.geometry_data))
                        + model_root(body, 0, frame))
            return vertices * np.array((-1., -1., 1.)) * (model_scale(body) / 2)
        frame = self._pose_frame(manager, tick, animate)
        vertices = np.asarray(manager.get_animated_vertices(0, frame)) + model_root(manager, 0, frame)
        return vertices * np.array((-1., -1., 1.)) * (model_scale(manager) / 2)
