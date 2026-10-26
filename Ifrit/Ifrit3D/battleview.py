"""Ifrit3D's battle view: the loaded model inside a scene.out encounter, under the free camera.

The scene is the Camera tab's battle preview (BattlePreviewSetup, model_view): the model stands
on its encounter slot, turned the way the game turns it (resetBasedRotation, EN 502070), with the
engine's root offset (model_root, raw/128), and the encounter's other enemies and the party stand
where scene.out and the battle formation put them. Only the models the user opened are drawn (no
file is looked up in a folder); a slot without one is a post on the ground. The camera stays the
orbit camera, centred on the field.
"""
import numpy as np
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup, model_root

MARKER_HEIGHT = 1500.   # battle units: about a party member's height
GRID_STEP = 1000.       # battle units between two ground lines
GRID_MARGIN = 3000.     # battle units of ground around the outermost slot


class BattleView(QWidget):
    """The battle setup panel shown under the 3D view, and what it puts into the GL widget."""
    changed = pyqtSignal()

    def __init__(self, ifrit_manager, file_registry=None, parent=None, settings=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self._settings = settings   # remembers the encounter picked for each model
        self._restoring = False
        self.setup = BattlePreviewSetup(ifrit_manager, file_registry=file_registry, model_view=True)
        self.setup.group.set_expanded(True)
        self.setup.changed.connect(self._on_setup_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self.setup)
        self._dirty = True
        self._scene_key = None      # (encounter, slot) the view was last framed on
        self.reframe_needed = True  # the field moved: centre the camera on it again

    def set_model_source(self, source):
        self.setup.model_source = source
        self.mark_dirty()

    def mark_dirty(self):
        self._dirty = True

    def _on_setup_changed(self):
        self._dirty = True
        encounter, slot = self.setup.encounters.selected, self.setup.encounters.selected_slot
        key = (getattr(encounter, 'index', None), getattr(slot, 'slot_index', None))
        if key != self._scene_key:
            self._scene_key = key
            self.reframe_needed = True
        if self._settings is not None and not self._restoring:
            self._settings.setValue(self._encounter_setting(), -1 if key[0] is None else key[0])
        self.changed.emit()

    def _encounter_setting(self):
        enemy = self.ifrit_manager.enemy
        return f"ifrit/3d/battle_view_encounter/{getattr(enemy.entity_type, 'name', '')}{getattr(enemy, 'id', '')}"

    def model_loaded(self):
        """A file was (re)loaded in the viewer: its encounters and model may differ. The encounter
        last picked for this model is picked again."""
        saved = -1 if self._settings is None else self._settings.value(self._encounter_setting(), -1, type=int)
        self._restoring = True
        try:
            picker = self.setup.encounters
            picker.refresh_model()
            if picker.selected is None and saved >= 0:
                for index in range(picker.encounter.count()):
                    if getattr(picker.encounter.itemData(index), 'index', None) == saved:
                        picker.encounter.setCurrentIndex(index)
                        break
        finally:
            self._restoring = False
        self._dirty = True

    def _build(self, anim_id):
        self.setup.build(anim_id, animate=True)
        self._dirty = False

    def apply(self, gl, anim_id, frame, show_ground=True):
        """Place this frame's scene in the GL widget: the model on its slot, the other actors
        posed at the same tick, posts on the empty slots and the ground."""
        if self._dirty:
            self._build(anim_id)
        setup = self.setup
        gl.set_model_translation(*model_root(self.ifrit_manager, anim_id, frame))
        gl.set_preview_model_transform(setup.to_viewer(setup.main_position), -setup.main_yaw)
        gl.set_preview_actor(setup.opponent_mesh(frame, animate=True))
        unit = setup.unit
        half = self._field_half_size()
        gl.set_preview_slot_markers([setup.to_viewer(point) for point in setup.marker_positions()],
                                    MARKER_HEIGHT * unit, half * unit if show_ground else None, GRID_STEP * unit)

    def _positions(self):
        context = self.setup.context
        points = [np.asarray(self.setup.main_position, float)]
        if context is not None:
            points += [np.asarray(actor.position, float) for actor in context.slots.values()]
        return np.array(points)

    def _field_half_size(self):
        points = self._positions()
        extent = np.abs(points[:, [0, 2]]).max() if len(points) else 0.
        return float(np.ceil((extent + GRID_MARGIN) / GRID_STEP) * GRID_STEP)

    def frame(self, gl):
        """Centre the orbit camera on the field and back it off to see every slot."""
        if self._dirty:
            return
        points = self._positions()
        low, high = points.min(axis=0), points.max(axis=0)
        centre = self.setup.to_viewer((low + high) / 2)
        size = float(np.max(high - low)) * self.setup.unit
        gl.set_reference_position(*centre)
        gl.zoom = max(size * 1.6, getattr(gl, 'MODEL_SIZE', 1.) * 3)
        gl.rot_x, gl.rot_y = 20., 180.
        gl.pan_x = gl.pan_y = 0.
        gl.update()
        self.reframe_needed = False

    @staticmethod
    def clear(gl):
        """Back to the model alone, at the origin."""
        gl.set_preview_model_transform((0., 0., 0.), 0.)
        gl.set_preview_actor(None)
        gl.set_preview_slot_markers()
