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

The short scan (a repeat scan with the Config Scan option on short) keeps the zoom-in camera
and, every tick (ShortScanner_State3, 0x8511A0): turns the camera around the target by 64/4096
when short_scan_orbit is 1, and when offset_y < -384 (tall target) moves the camera height
by -height/32 towards the aim level, stopping at 0.
"""
import math

import numpy as np
from PyQt6.QtCore import Qt, QTimer, QSignalBlocker
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
                             QSizePolicy, QSpinBox)

from Xu.xumanager import ScanCameraRow

SCAN_PROJECTION = 576
SCAN_SPIN_PER_TICK = 64        # rotation units (4096 = one turn) per game tick
TALL_TARGET_OFFSET_Y = -384    # short scan lowers the camera for aim heights above this
GAME_TICK_MS = 1000 // 15
MONSTER_YAW = math.pi          # monsters face the party
SCAN_BLUE = (0.0, 0.02, 0.32, 1.0)
CENTRE_SELECTOR = 5            # skeleton header byte read for bone selector 0xF1

MODE_SCAN_SCREEN, MODE_ZOOM_IN, MODE_SHORT_SCAN = range(3)


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


def zoom_in_distance(row: ScanCameraRow) -> int:
    return int(3 * row.distance / 4)


def short_scan_height(row: ScanCameraRow, tick: int) -> int:
    """Camera height of the short scan after `tick` ticks (starts at the zoom-in height)."""
    start = int(zoom_in_distance(row) / 2)
    if row.offset_y >= TALL_TARGET_OFFSET_Y:
        return start
    return min(0, start + tick * int(start / -32))


def scan_camera(row: ScanCameraRow, centre, yaw=MONSTER_YAW, zoom_in=False, orbit=0, height=None):
    """(eye, target) in battle world units for a target at the origin facing `yaw`.

    orbit (4096 = one turn) turns the zoom-in camera around the target and height replaces
    its height: both are the short scan's."""
    rotation = _rotation(yaw)
    aim = rotation @ np.asarray(centre, float) if row.aim_at_model else np.zeros(3)
    aim[1] = 0.
    if zoom_in:
        distance = zoom_in_distance(row)
        camera_height = int(distance / 2) if height is None else height
        target = aim + rotation @ np.array((0., row.offset_y, 0.))
        eye = target + _rotation(yaw + orbit * 2 * math.pi / 4096) @ np.array((0., camera_height, distance))
    else:
        target = aim + rotation @ np.array((row.offset_x, row.offset_y, 0.))
        eye = target + rotation @ np.array((0., 0., row.distance))
    return eye, target


class XuPreviewPanel(QWidget):
    """Shows the selected row on a monster model, the way the Scan screen does."""

    def __init__(self, game_data_folder="FF8GameData", parent=None, hud=None):
        super().__init__(parent)
        self._game_data_folder = game_data_folder
        self._game_data = None
        self._manager = None
        self._view = None
        self._gl = None
        self._row = ScanCameraRow()
        self._spin = 0
        self._tick = 0
        self._short_tick = 0
        self.model_path = ""
        self.hud = hud              # ScanHud, set by the widget
        self._title = ""
        self._scan_text = ""

        self._placeholder = QLabel("Choose a monster model (c0m###.dat) to preview the scan camera.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: gray")
        self._placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Scan screen", "Zoom-in (target lock)", "Short scan (repeat)"])
        self.mode_combo.setToolTip(
            "Scan screen: the info screen (camera mode 1), with the name and scan text.\n"
            "Zoom-in: where the camera ends while the reticle locks on (mode 0).\n"
            "Short scan: a repeat scan with the Config Scan option on short - the zoom-in\n"
            "camera, circling the target when the row says so.")
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._restart())
        self.turn_check = QCheckBox("Move like the game")
        self.turn_check.setChecked(True)
        self.turn_check.setToolTip("Scan screen: the model turns (Turns). Short scan: the camera circles "
                                   "(Circles in short scan) and lowers for tall targets.")
        self.turn_check.stateChanged.connect(lambda _s: self._update_timer())
        self.animate_check = QCheckBox("Animate")
        self.animate_check.setChecked(True)
        self.animate_check.setToolTip("Play the monster's idle animation (animation 0)")
        self.animate_check.stateChanged.connect(lambda _s: self._update_timer())
        self.text_check = QCheckBox("Text")
        self.text_check.setChecked(True)
        self.text_check.setToolTip("Draw the monster name and scan text where the Scan screen draws them")
        self.text_check.stateChanged.connect(lambda _s: self._refresh_hud())
        self.page_spin = QSpinBox()
        self.page_spin.setPrefix("Text page ")
        self.page_spin.setRange(1, 1)
        self.page_spin.setToolTip("The Scan screen shows 7 lines of scan text at a time. A longer text is\n"
                                  "split into pages: the game turns them on a button press or by itself\n"
                                  "after a delay, and starts over after the last one. Pick the page to\n"
                                  "preview - only enabled when the text has more than 7 lines.")
        self.page_spin.valueChanged.connect(lambda _v: self._refresh_hud())

        # Weapon shown in a character's hand: the imported d?w###.dat of that character.
        # Hidden when none is imported (the body is shown alone).
        self.weapon_label = QLabel("Weapon:")
        self.weapon_combo = QComboBox()
        self.weapon_combo.setToolTip("Weapon shown in the character's hand (the imported d?w###.dat files of\n"
                                     "this character), played on the same animation")
        self.weapon_combo.currentIndexChanged.connect(lambda _i: self._apply_weapon())
        self._weapon_managers = {}  # path -> IfritManager, loaded once

        controls = QHBoxLayout()
        controls.addWidget(self.mode_combo)
        controls.addWidget(self.turn_check)
        controls.addWidget(self.animate_check)
        controls.addWidget(self.text_check)
        controls.addWidget(self.page_spin)
        controls.addWidget(self.weapon_label)
        controls.addWidget(self.weapon_combo)
        controls.addStretch(1)
        self.set_weapon_choices([])

        self._hud_image = None
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
        from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
        manager = self._new_manager(path)
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
        self._view.load_file()
        if getattr(self._view, "timer", None) is not None:
            self._view.timer.stop()  # frames are driven here
        self._placeholder.hide()
        self.model_path = path
        self._apply_weapon()  # the new body gets the selected weapon back
        self._restart()

    def _new_manager(self, path):
        from Ifrit.ifritmanager import IfritManager
        if self._game_data is None:
            from FF8GameData.gamedata import GameData
            self._game_data = GameData(self._game_data_folder)
            self._game_data.load_all()
        manager = IfritManager(self._game_data_folder, game_data=self._game_data)
        manager.init_from_file(path)
        manager._ensure_matrices()
        return manager

    @property
    def has_model(self):
        return self._manager is not None

    # ------------------------------------------------------------- weapon
    def set_weapon_choices(self, choices):
        """[(label, path)] of the shown character's weapons; the first one is shown when any."""
        current = self.weapon_combo.currentData()
        with QSignalBlocker(self.weapon_combo):
            self.weapon_combo.clear()
            if choices:
                self.weapon_combo.addItem("No weapon", None)
            for label, path in choices:
                self.weapon_combo.addItem(label, path)
            paths = [path for _label, path in choices]
            self.weapon_combo.setCurrentIndex(
                self.weapon_combo.findData(current) if current in paths else (1 if choices else 0))
        visible = bool(choices)
        self.weapon_label.setVisible(visible)
        self.weapon_combo.setVisible(visible)
        self._apply_weapon()

    def _apply_weapon(self):
        if self._view is None:
            return
        path = self.weapon_combo.currentData()
        manager = None
        if path:
            manager = self._weapon_managers.get(path)
            if manager is None:
                try:
                    manager = self._weapon_managers[path] = self._new_manager(path)
                except Exception:  # a weapon file the viewer cannot read: show the body alone
                    manager = None
        if manager is not getattr(self._view, "_weapon_manager", None):
            self._view.set_weapon_options([("Weapon", manager)])
            self._apply()

    def model_name(self) -> str:
        """The name the loaded .dat carries (what the Scan screen shows), or ""."""
        try:
            return self._manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00')
        except Exception:
            return ""

    # ------------------------------------------------------------- row + text
    def set_row(self, row: ScanCameraRow):
        self._row = row.copy()
        self._restart()

    def set_texts(self, title: str, scan_text: str):
        self._title, self._scan_text = title, scan_text
        pages = self.hud.page_count(scan_text) if self.hud is not None else 1
        self.page_spin.setRange(1, pages)
        self.page_spin.setEnabled(pages > 1)
        self._refresh_hud()

    def _refresh_hud(self):
        if self.hud is None or not self.text_check.isChecked() or self.mode_combo.currentIndex() != MODE_SCAN_SCREEN:
            self._hud_image = None
        else:
            image = self.hud.render(self._title, self._scan_text, self.page_spin.value() - 1)
            self._hud_image = QImage(image.tobytes("raw", "RGBA"), image.width, image.height,
                                     QImage.Format.Format_RGBA8888).copy()
        self._place_hud()

    def _place_hud(self):
        if self._gl is not None:
            self._gl.overlay_image = self._hud_image  # drawn over the 4:3 game frame
            self._gl.update()

    # ------------------------------------------------------------- motion
    def _turning(self):
        return (self.mode_combo.currentIndex() == MODE_SCAN_SCREEN and self._row.can_yaw == 1
                and self.turn_check.isChecked())

    def _short_scan_moving(self):
        return self.mode_combo.currentIndex() == MODE_SHORT_SCAN and self.turn_check.isChecked() and (
            self._row.short_scan_orbit == 1 or self._row.offset_y < TALL_TARGET_OFFSET_Y)

    def _restart(self):
        self._spin = 0
        self._short_tick = 0
        self._apply()
        self._update_timer()
        self._refresh_hud()

    def _update_timer(self):
        if self._manager is not None and (self._turning() or self._short_scan_moving()
                                          or self.animate_check.isChecked()):
            self._timer.start()
        else:
            self._timer.stop()
            self._apply()

    def _advance(self):
        self._tick += 1
        if self._turning():
            self._spin = (self._spin + SCAN_SPIN_PER_TICK) % 4096
        if self._short_scan_moving():
            self._short_tick += 1
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

        mode = self.mode_combo.currentIndex()
        orbit, height = 0, None
        if mode == MODE_SHORT_SCAN:
            orbit = (self._short_tick * SCAN_SPIN_PER_TICK) % 4096 if self._row.short_scan_orbit == 1 else 0
            height = short_scan_height(self._row, self._short_tick)
        # The camera aims at the pose the scan starts on (frame 0, before any turn).
        eye, target = scan_camera(self._row, centre_point(self._manager), zoom_in=mode != MODE_SCAN_SCREEN,
                                  orbit=orbit, height=height)
        self._gl.set_model_translation(*model_root(self._manager, 0, frame))
        yaw = MONSTER_YAW + self._spin * 2 * math.pi / 4096
        self._gl.set_preview_model_transform(to_viewer((0., 0., 0.)), -yaw)
        self._gl.set_camera(to_viewer(eye), to_viewer(target), (0., 1., 0.),
                            projection=SCAN_PROJECTION, translate_model=True)
        self._place_hud()
        distance = abs(self._row.distance if mode == MODE_SCAN_SCREEN else zoom_in_distance(self._row))
        self.readout.setText(
            f"Eye ({eye[0]:.0f}, {eye[1]:.0f}, {eye[2]:.0f})   aim ({target[0]:.0f}, {target[1]:.0f}, "
            f"{target[2]:.0f})   distance {distance}   lens {SCAN_PROJECTION}")
