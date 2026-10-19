"""Read-only caster/target setup for the shared DAT camera preview."""
import math
from pathlib import Path

import numpy as np
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QSpinBox, QPushButton, QFileDialog, QSizePolicy)

from FF8GameData.dat.battlecamera import BattleCameraContext, CameraActor, CameraPose
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

    def __init__(self, manager, parent=None, file_registry=None):
        super().__init__(parent)
        self.manager = manager
        self.opponent = None
        self.context = None
        self.unit = 1.
        self._asset_cache = {}
        self._scene_mesh_actors = []
        self.main_position = (0., 0., 0.)
        self.main_yaw = 0.
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
        self.encounters = EncounterPicker(manager, file_registry)
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
        self.party_slot.valueChanged.connect(lambda _v: self.changed.emit())
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel('Loaded model:'))
        self.role = QComboBox()
        self.role.addItems(['Caster', 'Target'])
        role_row.addWidget(self.role)
        options.addLayout(role_row)
        slot_row = QHBoxLayout()
        self.caster_slot, self.target_slot = QSpinBox(), QSpinBox()
        is_monster = getattr(self.manager.enemy.entity_type, 'name', '').startswith('MONSTER')
        for label, spin, default in (('Caster slot:', self.caster_slot, 3 if is_monster else 0),
                                     ('Target slot:', self.target_slot, 0 if is_monster else 3)):
            spin.setRange(0, 10)
            spin.setValue(default)
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            slot_row.addWidget(QLabel(label))
            slot_row.addWidget(spin)
        options.addLayout(slot_row)
        position_row = QHBoxLayout()
        position_row.addWidget(QLabel('Opponent position:'))
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
        self.position_label = position_row.itemAt(0).widget()
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
        options.addWidget(self.status)
        self.role.currentIndexChanged.connect(lambda _value: self.changed.emit())
        self.initial_view.currentIndexChanged.connect(lambda _value: self.changed.emit())
        self.view_mode.currentIndexChanged.connect(lambda _value: self.changed.emit())

    def _party_changed(self, value):
        self.party_slot.blockSignals(True)
        self.party_slot.setMaximum(value - 1)
        self.party_slot.blockSignals(False)
        self.changed.emit()

    def _encounter_changed(self):
        active = self.encounters.selected is not None
        for spin in self.position:
            spin.setEnabled(not active)
        self.position_label.setEnabled(not active)
        for spin in (self.caster_slot, self.target_slot):
            spin.setEnabled(not active)
        for button in self.opponent_buttons:
            button.setEnabled(not active or self.encounters.is_monster)
            button.setToolTip('Load a party stand-in for a monster preview. Encounter enemies are loaded automatically.')
        self.changed.emit()

    @staticmethod
    def _load_model(path, game_data):
        from Ifrit.ifritmanager import IfritManager
        manager = IfritManager(game_data=game_data)
        # Auxiliary actors are untextured: avoid the texture extraction subprocess.
        manager.enemy = manager.parse_file(str(path))
        if not manager.enemy.bone_data.bones or not manager.enemy.animation_data.nb_animations:
            raise ValueError('select a monster or character with skeletal animations')
        manager._ensure_matrices()
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
        self.status.setText(f'Opponent: {Path(path).name} (untextured preview). Assumed battle placement.')
        self.changed.emit()
        return True

    def _clear_opponent(self):
        self.opponent = None
        self.status.setText('Opponent model not loaded. Manual placement.')
        self.changed.emit()

    def build(self, animation=0, animate=False):
        self.unit = 2 / model_scale(self.manager)
        self._scene_mesh_actors = []
        self.main_position, self.main_yaw = (0., 0., 0.), 0.
        if self.encounters.selected is not None and self.encounters.selected_slot is not None:
            return self._build_encounter(animation, animate)
        self.status.setText('Opponent: ' + (f'{self.opponent.enemy.origin_file_name} (untextured).'
                            if self.opponent else 'model not loaded.') + ' Manual placement.')
        self.main_yaw = math.pi if self.encounters.is_monster else 0.
        other_yaw = 0. if self.encounters.is_monster else math.pi
        main = actor_from_model(self.manager, yaw=self.main_yaw, animation=animation, animate=animate)
        position = tuple(spin.value() for spin in self.position)
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
        self.context = BattleCameraContext(caster, target, CameraPose(tuple(eye), tuple(centre)), slots)
        self._other = other
        if self.opponent is not None:
            self._scene_mesh_actors.append((self.opponent, other))
        return self.context

    def _asset(self, name):
        folders = [self.encounters.path.parent,
                   Path(getattr(self.manager.enemy, 'origin_path', '')).parent]
        path = next((folder / name for folder in folders if (folder / name).is_file()), None)
        if path is None:
            return None
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
                        notes.append(f'{name}: missing model' if slot.loaded else f'{name}: not initially loaded')
                except Exception as error:
                    manager = None
                    notes.append(f'{name}: {error}')
                actor = (actor_from_model(manager, slot.position, math.pi, animate=animate) if manager else
                         CameraActor(slot.position, math.pi))
                if manager is not None and slot.loaded and slot.visible:
                    self._scene_mesh_actors.append((manager, actor))
            slots[3 + slot.slot_index] = actor
        if monster:
            player = self.opponent
            if player is None:
                try:
                    player = self._asset('d0c000.dat')
                except Exception as error:
                    notes.append(f'Player model: {error}')
            other = (actor_from_model(player, player_position, animate=animate) if player else
                     CameraActor(player_position))
            if player is not None:
                self._scene_mesh_actors.append((player, other))
            else:
                notes.append('Player model missing; load a player DAT')
            main_slot, other_slot = 3 + selected.slot_index, player_slot
            slots[player_slot] = other
        else:
            other = slots[3 + selected.slot_index]
            main_slot, other_slot = player_slot, 3 + selected.slot_index
            slots[player_slot] = main
        caster, target = (main, other) if self.role.currentIndex() == 0 else (other, main)
        ids = (main_slot, other_slot) if self.role.currentIndex() == 0 else (other_slot, main_slot)
        for spin, value in zip((self.caster_slot, self.target_slot), ids):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        centre = (main.point(0, 0) + other.point(0, 0)) / 2
        if self.initial_view.currentIndex() == 1:
            centre = main.point(0, 0)
        eye = centre + np.array((-4000., -2000., -7000.))
        self.context = BattleCameraContext(caster, target, CameraPose(tuple(eye), tuple(centre)), slots)
        self._other = other
        self.encounters.status.setText(
            f'Encounter {encounter.index}. Party {self.party_size.value()}, player slot {player_slot}: '
            f'{player_position}. ' + '; '.join(notes))
        self.status.setText('Player: imported model or Squall from the battle folder.' if monster else
                            'Enemy models are loaded from the selected encounter (untextured).')
        return self.context

    def to_viewer(self, point):
        return np.asarray(point) * np.array((-1., -1., 1.)) * self.unit

    def opponent_mesh(self, tick=0, animate=False):
        if not self._scene_mesh_actors:
            return None
        all_vertices, triangles, quads = [], [], []
        offset = 0
        for manager, actor in self._scene_mesh_actors:
            count = len(manager.enemy.animation_data.animations[0].frames)
            frame = tick % max(1, count) if animate else 0
            vertices = np.asarray(manager.get_animated_vertices(0, frame)) + model_root(manager, 0, frame)
            engine = vertices * np.array((-1., -1., 1.)) * (model_scale(manager) / 2)
            engine = engine @ actor.rotation.T + actor.position
            geo = manager.enemy.geometry_data
            all_vertices.extend(self.to_viewer(engine))
            triangles.extend(tuple(i + offset for i in face) for face in geo.get_triangles())
            quads.extend(tuple(i + offset for i in face) for face in geo.get_quads())
            offset += len(vertices)
        return np.asarray(all_vertices), triangles, quads
