"""Scan-screen preview: films a monster model with the camera a scan camera row gives.

The camera is rebuilt from the decoded engine code (MAG_040_SCAN_Camera_Setup /
CameraBlendStep / CameraApply, FF8_EN.exe 0x84E870..0x84EC80), in battle world units:

  * aim point P = the model's centre bone (skeleton header byte 5, the 0xF1 selector of
    GetEffectSpawnPosition) - or the target position when aim_at_model is 0 - with its
    height forced to 0 (the floor);
  * Scan screen (camera mode 1): target = P + R(offset_x, offset_y, 0),
    eye = target + R(0, 0, distance);
  * zoom-in while the reticle locks on (mode 0): d = 3 * distance / 4,
    target = P + R(0, offset_y, 0), eye = target + R(0, d / 2, d);

R = rotation of the target's facing, lens (projection H) 576. In the Scan screen the model
then turns by 64/4096 of a turn per game tick when can_yaw is set.
"""
import math

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
                             QSizePolicy)

from Xu.xumanager import ScanCameraRow

SCAN_PROJECTION = 576
SCAN_SPIN_PER_TICK = 64        # rotation_y units (4096 = one turn) per game tick
GAME_TICK_MS = 1000 // 15
MONSTER_YAW = math.pi          # monsters face the party
SCAN_BLUE = (0.0, 0.02, 0.32, 1.0)
CENTRE_SELECTOR = 5            # skeleton header byte read for bone selector 0xF1


def _rotation(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array(((c, 0., s), (0., 1., 0.), (-s, 0., c)))


def centre_point(manager, animation=0, frame=0):
    """The model's 0xF1 point (engine units, relative to the target, before its facing).

    The scan asks GetEffectSpawnPosition for it with interpolation 0: the bone's start,
    unless the header byte has bit 0x80, which selects the bone's end."""
    from Ifrit.IfritCameraSeq.battlepreview import model_root, model_scale
    raw = manager.enemy.section_raw_data[1]
    selected = raw[CENTRE_SELECTOR] if len(raw) > CENTRE_SELECTOR else 0
    bone_id = selected & 0x7F
    matrices = manager._get_bone_matrices(animation, frame)
    bones = manager.enemy.bone_data.bones
    if bone_id >= len(matrices) or bone_id >= len(bones):
        return np.zeros(3)
    m, bone = matrices[bone_id], bones[bone_id]
    length = bone.get_size() if selected & 0x80 and not bone.parent_id & 0x8000 else 0
    point = np.array((m.M41 + m.M13 * length, m.M42 + m.M23 * length,
                      m.M43 + m.M33 * length)) + model_root(manager, animation, frame)
    return point * np.array((-1., -1., 1.)) * (model_scale(manager) / 2)


def scan_camera(row: ScanCameraRow, centre, yaw=MONSTER_YAW, zoom_in=False):
    """(eye, target) in battle world units for a target at the origin facing `yaw`."""
    rotation = _rotation(yaw)
    aim = rotation @ np.asarray(centre, float) if row.aim_at_model else np.zeros(3)
    aim[1] = 0.
    if zoom_in:
        distance = int(3 * row.distance / 4)
        target = aim + rotation @ np.array((0., row.offset_y, 0.))
        eye = target + rotation @ np.array((0., int(distance / 2), distance))
    else:
        target = aim + rotation @ np.array((row.offset_x, row.offset_y, 0.))
        eye = target + rotation @ np.array((0., 0., row.distance))
    return eye, target


class XuPreviewPanel(QWidget):
    """Shows the selected row on a monster model, the way the Scan screen does."""

    def __init__(self, game_data_folder="FF8GameData", parent=None):
        super().__init__(parent)
        self._game_data_folder = game_data_folder
        self._game_data = None
        self._manager = None
        self._view = None
        self._gl = None
        self._row = ScanCameraRow()
        self._spin = 0
        self._tick = 0
        self.model_path = ""

        self._placeholder = QLabel("Choose a monster model (c0m###.dat) to preview the scan camera.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: gray")
        self._placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Scan screen", "Zoom-in (target lock)"])
        self.mode_combo.setToolTip("Scan screen: the framing of the info screen (camera mode 1).\n"
                                   "Zoom-in: where the camera ends while the reticle locks on (mode 0).")
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._apply())
        self.turn_check = QCheckBox("Turn like the game")
        self.turn_check.setChecked(True)
        self.turn_check.setToolTip("The Scan screen turns the model when the row allows it (can yaw)")
        self.turn_check.stateChanged.connect(lambda _s: self._update_timer())
        self.animate_check = QCheckBox("Animate")
        self.animate_check.setToolTip("Play the monster's idle animation (animation 0)")
        self.animate_check.stateChanged.connect(lambda _s: self._update_timer())

        controls = QHBoxLayout()
        controls.addWidget(self.mode_combo)
        controls.addWidget(self.turn_check)
        controls.addWidget(self.animate_check)
        controls.addStretch(1)

        self._name_label = QLabel()
        self._name_label.setStyleSheet("color: white; font: bold 13pt 'Consolas'; background: transparent")
        self.readout = QLabel()
        self.readout.setStyleSheet("color: gray")
        self.readout.setWordWrap(True)

        self._layout = QVBoxLayout(self)
        self._layout.addLayout(controls)
        self._layout.addWidget(self._placeholder, 1)
        self._layout.addWidget(self.readout)

        self._timer = QTimer(self)
        self._timer.setInterval(GAME_TICK_MS)
        self._timer.timeout.connect(self._advance)

    # ------------------------------------------------------------- model
    def load_model(self, path: str):
        """Load a battle model; raises on a file the 3D viewer cannot show."""
        from Ifrit.ifritmanager import IfritManager
        from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
        if self._game_data is None:
            from FF8GameData.gamedata import GameData
            self._game_data = GameData(self._game_data_folder)
            self._game_data.load_all()
        manager = IfritManager(self._game_data_folder, game_data=self._game_data)
        manager.init_from_file(path)
        manager._ensure_matrices()
        self._manager = manager
        if self._view is not None:
            self._layout.removeWidget(self._view)
            self._view.deleteLater()
        self._view = Ifrit3DWidget(manager, show_controls=False)
        self._gl = self._view.gl_widget
        self._gl.setMinimumHeight(300)
        self._gl.show_axis = False
        self._gl.clear_color = SCAN_BLUE
        self._gl.letterbox_color = (0., 0., 0., 1.)  # outside the game's 4:3 screen
        self._layout.insertWidget(1, self._view, 1)
        self._name_label.setParent(self._gl)
        self._name_label.move(12, 8)
        self._name_label.show()
        self._view.load_file()
        if getattr(self._view, "timer", None) is not None:
            self._view.timer.stop()  # frames are driven here
        self._placeholder.hide()
        self.model_path = path
        self._spin = 0
        self._tick = 0
        self._apply()
        self._update_timer()

    @property
    def has_model(self):
        return self._manager is not None

    def set_title(self, text: str):
        self._name_label.setText(text)
        self._name_label.adjustSize()

    # ------------------------------------------------------------- row
    def set_row(self, row: ScanCameraRow):
        self._row = row.copy()
        self._spin = 0
        self._apply()
        self._update_timer()

    def _turning(self):
        return self.mode_combo.currentIndex() == 0 and self._row.can_yaw == 1 and self.turn_check.isChecked()

    def _update_timer(self):
        if self._manager is not None and (self._turning() or self.animate_check.isChecked()):
            self._timer.start()
        else:
            self._timer.stop()
            self._apply()

    def _advance(self):
        self._tick += 1
        if self._turning():
            self._spin = (self._spin + SCAN_SPIN_PER_TICK) % 4096
        self._apply()

    def _frame(self):
        if not self.animate_check.isChecked():
            return 0
        try:
            frames = len(self._manager.enemy.animation_data.animations[0].frames)
        except (AttributeError, IndexError):
            return 0
        return self._tick % max(frames, 1)

    def _apply(self):
        if self._manager is None or self._gl is None:
            return
        from Ifrit.IfritCameraSeq.battlepreview import model_root, model_scale
        frame = self._frame()
        try:
            if self._manager.enemy.animation_data.animations:
                if self._view.current_anim_id != 0:
                    self._view.set_animation(0)
                self._view.set_frame(frame)
        except Exception:
            pass
        unit = 2 / model_scale(self._manager)

        def to_viewer(point):
            return np.asarray(point, float) * np.array((-1., -1., 1.)) * unit

        zoom_in = self.mode_combo.currentIndex() == 1
        # The camera is placed once, from the pose the scan starts on (frame 0, no turn).
        eye, target = scan_camera(self._row, centre_point(self._manager), zoom_in=zoom_in)
        self._gl.set_model_translation(*model_root(self._manager, 0, frame))
        yaw = MONSTER_YAW + self._spin * 2 * math.pi / 4096
        self._gl.set_preview_model_transform(to_viewer((0., 0., 0.)), -yaw)
        self._gl.set_camera(to_viewer(eye), to_viewer(target), (0., 1., 0.),
                            projection=SCAN_PROJECTION, translate_model=True)
        viewport = getattr(self._gl, "_game_viewport", None)  # keep the title inside the 4:3 frame
        if viewport is not None:
            self._name_label.move(viewport[0] + 12, self._gl.height() - viewport[1] - viewport[3] + 8)
        self.readout.setText(
            f"Eye ({eye[0]:.0f}, {eye[1]:.0f}, {eye[2]:.0f})   aim ({target[0]:.0f}, {target[1]:.0f}, "
            f"{target[2]:.0f})   distance {abs(row_distance(self._row, zoom_in))}   lens {SCAN_PROJECTION}")


def row_distance(row: ScanCameraRow, zoom_in: bool) -> int:
    return int(3 * row.distance / 4) if zoom_in else row.distance
