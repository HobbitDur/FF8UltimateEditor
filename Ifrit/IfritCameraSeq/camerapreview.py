"""The shared camera preview: a panel docked on the right of the Camera tab.

One panel is reused for every animation - clicking a slot's ▶ Preview loads that camera
animation here and plays it, rather than opening a window per animation. It renders the
actual monster model (reusing Ifrit3D) and, at 15 fps, drives:
  - the camera through the keyframes (interpolated across each keyframe's duration - that
    is where the smooth motion comes from; keyframes are sparse control points), and
  - optionally the monster's own animation, so you see a moving model filmed by the moving
    camera.

Raw DAT previews use BattlePreviewSetup: caster/target skeleton references, previous view,
projection and roll are evaluated before conversion to viewer space. Watts supplies already
baked composite coordinates and keeps its existing placement through battle_context=False.
"""
import math
from time import perf_counter

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QSpinBox, QCheckBox, QSizePolicy)

from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

BATTLE_SETUP_STATE_KEY = "camera preview/battle setup expanded"  # QSettings key of its folded state
_WORLD_SCALE = 1.0 / 204.8  # world-position scale (matches PositionType), not the vertex 1/2048


class _NoWheelSpinBox(QSpinBox):
    """Ignores the mouse wheel so scrolling the panel can't change the value by accident."""

    def wheelEvent(self, event):
        event.ignore()


def _frame_values(animation):
    """Live [(pos xyz, look xyz, duration)] for every keyframe of the animation, in order."""
    values = []
    for block in animation.blocks:
        for frame in block.frames:
            values.append((
                (frame.pos_x.get(), frame.pos_y.get(), frame.pos_z.get()),
                (frame.look_x.get(), frame.look_y.get(), frame.look_z.get()),
                max(frame.duration.get(), 0),
            ))
    return values


def _total_ticks(values) -> int:
    return sum(values[i][2] for i in range(len(values) - 1)) if len(values) > 1 else 0


def _lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _sample(values, tick):
    """(pos, look) at a global tick. Keyframes are sparse control points and `duration` is
    the number of frames to interpolate between one keyframe and the next, so the camera is
    interpolated (linearly) across each segment. Clamps past the end."""
    if not values:
        return None
    if len(values) == 1:
        return values[0][0], values[0][1]
    remaining = max(0, tick)
    for index in range(len(values) - 1):
        duration = values[index][2]
        if duration <= 0:
            continue
        if remaining < duration:
            fraction = remaining / duration
            return (_lerp3(values[index][0], values[index + 1][0], fraction),
                    _lerp3(values[index][1], values[index + 1][1], fraction))
        remaining -= duration
    return values[-1][0], values[-1][1]


class CameraPreviewPanel(QWidget):
    """Shared 3D preview panel; call preview(animation) to load and play one animation."""

    _FPS = 15

    def __init__(self, ifrit_manager, parent=None, show_model_animation=True, battle_context=True,
                 file_registry=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.setMinimumWidth(420 if battle_context else 320)
        self._view = None          # Ifrit3DWidget, created lazily on first preview
        self._weapon_manager = None
        self._gl = None
        self._needs_reload = True  # (re)load the model on the next preview
        self._animation = None
        self._values = []
        self._total = 0
        self._tick = 0
        self._center = (0.0, 0.0, 0.0)
        self._poses = []
        self._empty_camera = False
        self._clock_tick = 0
        self._play_origin = 0.
        self._advancing = False
        self._battle_setup = None
        if battle_context:
            from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
            self._battle_setup = BattlePreviewSetup(ifrit_manager, file_registry=file_registry)
            self._battle_setup.changed.connect(self._rebuild_battle)
            # Folded or not, the Battle setup stays as the user left it (all camera previews)
            self._battle_setup.group.remember(getattr(file_registry, "settings", None),
                                              BATTLE_SETUP_STATE_KEY)

        self._placeholder = QLabel("Click a slot's ▶ Preview to play its camera here.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: gray")
        self._placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._play_button = QPushButton("▶ Play")
        self._play_button.clicked.connect(self._toggle_play)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.valueChanged.connect(self._on_slider)
        self._tick_label = QLabel("0 / 0")

        self._animate_model = QCheckBox("Animate model")
        self._animate_model.setChecked(True)
        self._animate_model.setToolTip("Also play the monster's own animation while previewing")
        self._animate_model.stateChanged.connect(lambda _s: self._rebuild_battle())
        self._model_anim_spin = _NoWheelSpinBox()
        self._model_anim_spin.setToolTip("Which of the monster's animations to play in the "
                                         "preview while the camera moves")
        self._model_anim_spin.setMaximumWidth(60)
        self._model_anim_spin.valueChanged.connect(lambda _v: self._rebuild_battle())

        self._readout = QLabel()
        self._readout.setStyleSheet("color: gray")
        self._readout.setWordWrap(True)

        controls = QHBoxLayout()
        controls.addWidget(self._play_button)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._tick_label)
        # The model-animation picker only makes sense when previewing a single model that
        # carries several animations (Ifrit's monster camera tab). Callers previewing a fixed
        # scene - e.g. Watts' composite victory pose, always anim 0 - hide it via
        # show_model_animation=False while the controls stay functional at their defaults.
        self._model_row = QWidget()
        model_row = QHBoxLayout(self._model_row)
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(self._animate_model)
        model_row.addWidget(QLabel("anim:"))
        model_row.addWidget(self._model_anim_spin)
        model_row.addStretch(1)
        if not show_model_animation:
            self._model_row.hide()

        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("Camera preview"))
        self._layout.addWidget(self._placeholder, 1)
        self._layout.addLayout(controls)
        if self._battle_setup is not None:
            self._layout.addWidget(self._battle_setup)
        self._layout.addWidget(self._model_row)
        self._layout.addWidget(self._readout)
        self._set_controls_enabled(False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)  # the wall clock selects the 15 Hz game tick

    # ── Called by the tab ─────────────────────────────────────────────
    def set_weapon(self, manager):
        """Use a character's selected weapon (with textures loaded) on the next preview."""
        if manager is not self._weapon_manager:
            self._weapon_manager = manager
            self.invalidate()

    def invalidate(self):
        """A new file was loaded: stop playback and reload the model on the next preview."""
        self._timer.stop()
        self._play_button.setText("▶ Play")
        self._needs_reload = True
        self._animation = None
        self._poses = []
        if self._battle_setup is not None:
            self._battle_setup.encounters.refresh_model()
        self._set_controls_enabled(False)
        if self._view is not None:
            self._view.hide()
        self._placeholder.setText("Click a slot's ▶ Preview to play its camera here.")
        self._placeholder.show()

    def preview(self, animation):
        self._timer.stop()
        self._play_button.setText('▶ Play')
        try:
            self._ensure_model()
        except Exception as error:  # a file the 3D viewer cannot render
            self._placeholder.setText(f"3D preview unavailable: {error}")
            self._placeholder.show()
            if self._view is not None:
                self._view.hide()
            self._set_controls_enabled(False)
            return
        if self._battle_setup is not None:
            self._animation = None
            self._battle_setup.encounters.refresh_model()
        self._animation = animation
        self._values = _frame_values(animation)
        self._total = _total_ticks(self._values)
        self._build_battle_poses()
        self._placeholder.hide()
        self._view.show()
        self._slider.blockSignals(True)
        self._slider.setRange(0, max(self._total, 0))
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._set_controls_enabled(True)
        self._slider.setEnabled(self._total > 0)
        self._apply(0)
        if self._total > 0:  # auto-play multi-keyframe animations
            self._start_playback()

    def refresh(self):
        """The previewed animation's keyframes were edited in place: replay them from the same tick."""
        if self._animation is None or self._gl is None:
            return
        if self._battle_setup is not None:
            self._rebuild_battle()
            return
        self._values = _frame_values(self._animation)
        self._total = _total_ticks(self._values)
        self._slider.setRange(0, max(self._total, 0))
        self._slider.setEnabled(self._total > 0)
        self._apply(min(self._tick, self._total))

    def _build_battle_poses(self):
        self._poses = []
        if self._battle_setup is None or self._animation is None:
            return
        from FF8GameData.dat.battlecamera import play_camera_animation
        context = self._battle_setup.build(self._model_anim_spin.value(), self._animate_model.isChecked())
        self._poses = play_camera_animation(self._animation, context)
        self._empty_camera = not self._poses
        if self._empty_camera:
            self._poses = [context.initial]
        self._total = max(0, len(self._poses) - 1)

    def _rebuild_battle(self):
        if self._animation is None or self._gl is None:
            return
        playing = self._timer.isActive()
        self._timer.stop()  # loading an encounter/texture is outside playback time
        self._build_battle_poses()
        self._slider.setRange(0, self._total)
        self._slider.setEnabled(self._total > 0)
        self._apply(min(self._tick, self._total))
        if playing and self._total > 0:
            self._start_playback()

    # ── Model / camera ────────────────────────────────────────────────
    def _ensure_model(self):
        if self._view is None:
            self._view = Ifrit3DWidget(self.ifrit_manager, show_controls=False)
            self._layout.insertWidget(1, self._view, 1)  # where the placeholder sits
            self._gl = self._view.gl_widget
            # Outside the game's 4:3 screen of a game camera: black bars and a thin frame, so
            # a model cut at the edge reads as off screen rather than hidden in the background
            self._gl.letterbox_color = (0., 0., 0., 1.)
            self._gl.letterbox_outline_color = (.45, .45, .5, 1.)
            if self._battle_setup is not None:
                self._gl.setMinimumHeight(300)
                self._gl.show_axis = False
        if self._needs_reload:
            # Lean imports have no expanded frames yet. Ifrit3D checks them before its
            # first mesh update, so expand first or a static preview shows raw bone-local vertices.
            self.ifrit_manager._ensure_matrices()
            self._view.load_file()
            if self._weapon_manager is not None or self._view._weapon_manager is not None:
                self._view.set_weapon_options([("Preview weapon", self._weapon_manager)])
            if getattr(self._view, "timer", None) is not None:
                self._view.timer.stop()  # we drive frames ourselves, one timer for both
            center = getattr(self._gl, "MODEL_CENTER", None)
            self._center = ((float(center[0]), float(center[1]), float(center[2]))
                            if center is not None else (0.0, 0.0, 0.0))
            nb = self.__nb_model_animations()
            self._model_anim_spin.setRange(0, max(nb - 1, 0))
            self._model_anim_spin.setEnabled(nb > 0)
            self._animate_model.setEnabled(nb > 0)
            self._needs_reload = False

    def __nb_model_animations(self) -> int:
        try:
            return int(self.ifrit_manager.enemy.animation_data.nb_animations)
        except Exception:
            return 0

    def __model_frame_count(self, anim_id: int) -> int:
        try:
            return max(1, len(self.ifrit_manager.enemy.animation_data.animations[anim_id].frames))
        except Exception:
            return 1

    def _to_viewer(self, raw):
        x, y, z = raw
        return (self._center[0] - x * _WORLD_SCALE,
                self._center[1] + z * _WORLD_SCALE,
                self._center[2] - y * _WORLD_SCALE)

    def _apply(self, tick):
        self._tick = tick
        self._tick_label.setText(f"{tick} / {self._total}")
        if self._animation is None or self._gl is None:
            return
        # Model animation: step the monster's own animation in step with the camera.
        if self.__nb_model_animations() > 0:
            anim_id = self._model_anim_spin.value()
            frame = tick % self.__model_frame_count(anim_id) if self._animate_model.isChecked() else 0
            try:
                if self._view.current_anim_id != anim_id:
                    self._view.set_animation(anim_id)
                self._view.set_frame(frame)
                self._view._update_model_translation()
            except Exception:
                pass
        if self._poses:
            self._apply_battle(tick)
            return
        sample = _sample(_frame_values(self._animation), tick)
        if sample is not None:
            (cx, cy, cz), (tx, ty, tz) = sample
            self._readout.setText(
                f"camera ({cx:.0f}, {cy:.0f}, {cz:.0f})   look-at ({tx:.0f}, {ty:.0f}, {tz:.0f})")
            self._gl.set_camera(self._to_viewer(sample[0]), self._to_viewer(sample[1]))

    def _apply_battle(self, tick):
        from Ifrit.IfritCameraSeq.battlepreview import model_root
        setup = self._battle_setup
        pose = self._poses[min(tick, len(self._poses) - 1)]
        frame = tick if self._animate_model.isChecked() else 0
        self._gl.set_model_translation(*model_root(self.ifrit_manager, self._model_anim_spin.value(), frame))
        self._gl.set_preview_model_transform(setup.to_viewer(setup.main_position), -setup.main_yaw)
        self._gl.set_preview_markers(None, None)
        self._gl.set_preview_actor(setup.opponent_mesh(tick, self._animate_model.isChecked()))
        if setup.view_mode.currentIndex() == 0:
            angle = pose.roll * 2 * math.pi / 4096
            up = (-math.sin(angle), math.cos(angle), 0.)
            self._gl.set_camera(setup.to_viewer(pose.eye), setup.to_viewer(pose.target), up,
                                projection=pose.projection, translate_model=True)
        else:
            self._gl.clear_explicit_camera()
        warning = '; '.join(sorted(setup.context.warnings))
        title = 'Empty camera: holding starting view' if self._empty_camera else f'Block {pose.block}'
        self._readout.setText(f'{title} · Lens {pose.projection:.0f} · Roll {pose.roll:.0f}'
                             + (f' · {warning}' if warning else ''))

    def _toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
            self._play_button.setText("▶ Play")
        else:
            if self._slider.value() >= self._total:
                self._slider.setValue(0)
            self._start_playback()

    def _start_playback(self):
        self._clock_tick = self._slider.value()
        self._play_origin = perf_counter()
        self._timer.start()
        self._play_button.setText('⏸ Pause')

    def _advance(self):
        # Qt may coalesce timeouts during a busy redraw. One frame per callback
        # stretched a 40-tick camera to nine seconds; elapsed time keeps native speed.
        due = self._clock_tick + int((perf_counter() - self._play_origin) * self._FPS)
        nxt = min(due, self._total)
        if nxt != self._slider.value():
            self._advancing = True
            try:
                self._slider.setValue(nxt)
            finally:
                self._advancing = False
        if due > self._total:  # final tick is held, then playback stops
            self._timer.stop()
            self._play_button.setText("▶ Play")

    def _on_slider(self, value):
        if not self._advancing and self._timer.isActive():
            self._clock_tick, self._play_origin = value, perf_counter()
        self._apply(value)

    def _set_controls_enabled(self, enabled: bool):
        self._play_button.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._animate_model.setEnabled(enabled)
        self._model_anim_spin.setEnabled(enabled)
