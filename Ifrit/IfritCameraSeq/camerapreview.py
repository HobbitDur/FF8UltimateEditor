"""The shared camera preview: a panel docked on the right of the Camera tab.

One panel is reused for every animation - clicking a slot's ▶ Preview loads that camera
animation here and plays it, rather than opening a window per animation. It renders the
actual monster model (reusing Ifrit3D) and, at 15 fps, drives:
  - the camera through the keyframes (interpolated across each keyframe's duration - that
    is where the smooth motion comes from; keyframes are sparse control points), and
  - optionally the monster's own animation, so you see a moving model filmed by the moving
    camera.

Camera coordinates map into the viewer's space the same way the model does: the vertex axis
convention (x, y, z) -> (-x, z, -y) at the world-position scale (1/204.8), anchored on the
model's centre so the camera looks at the monster.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QSpinBox, QCheckBox, QSizePolicy)

from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

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

    def __init__(self, ifrit_manager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.setMinimumWidth(320)
        self._view = None          # Ifrit3DWidget, created lazily on first preview
        self._gl = None
        self._needs_reload = True  # (re)load the model on the next preview
        self._animation = None
        self._values = []
        self._total = 0
        self._tick = 0
        self._center = (0.0, 0.0, 0.0)

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
        self._animate_model.stateChanged.connect(lambda _s: self._apply(self._tick))
        self._model_anim_spin = _NoWheelSpinBox()
        self._model_anim_spin.setToolTip("Which of the monster's animations to play in the "
                                         "preview while the camera moves")
        self._model_anim_spin.setMaximumWidth(60)
        self._model_anim_spin.valueChanged.connect(lambda _v: self._apply(self._tick))

        self._readout = QLabel()
        self._readout.setStyleSheet("color: gray")
        self._readout.setWordWrap(True)

        controls = QHBoxLayout()
        controls.addWidget(self._play_button)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._tick_label)
        model_row = QHBoxLayout()
        model_row.addWidget(self._animate_model)
        model_row.addWidget(QLabel("anim:"))
        model_row.addWidget(self._model_anim_spin)
        model_row.addStretch(1)

        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("Camera preview"))
        self._layout.addWidget(self._placeholder, 1)
        self._layout.addLayout(controls)
        self._layout.addLayout(model_row)
        self._layout.addWidget(self._readout)
        self._set_controls_enabled(False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.setInterval(int(1000 / self._FPS))

    # ── Called by the tab ─────────────────────────────────────────────
    def invalidate(self):
        """A new file was loaded: stop playback and reload the model on the next preview."""
        self._timer.stop()
        self._play_button.setText("▶ Play")
        self._needs_reload = True
        self._animation = None
        self._set_controls_enabled(False)
        if self._view is not None:
            self._view.hide()
        self._placeholder.setText("Click a slot's ▶ Preview to play its camera here.")
        self._placeholder.show()

    def preview(self, animation):
        try:
            self._ensure_model()
        except Exception as error:  # a file the 3D viewer cannot render
            self._placeholder.setText(f"3D preview unavailable: {error}")
            self._placeholder.show()
            if self._view is not None:
                self._view.hide()
            self._set_controls_enabled(False)
            return
        self._animation = animation
        self._values = _frame_values(animation)
        self._total = _total_ticks(self._values)
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
            self._timer.start()
            self._play_button.setText("⏸ Pause")

    # ── Model / camera ────────────────────────────────────────────────
    def _ensure_model(self):
        if self._view is None:
            self._view = Ifrit3DWidget(self.ifrit_manager, show_controls=False)
            self._layout.insertWidget(1, self._view, 1)  # where the placeholder sits
            self._gl = self._view.gl_widget
        if self._needs_reload:
            self._view.load_file()
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
        if self._animate_model.isChecked() and self.__nb_model_animations() > 0:
            anim_id = self._model_anim_spin.value()
            frame = tick % self.__model_frame_count(anim_id)
            try:
                self._gl.set_vertices(self.ifrit_manager.get_animated_vertices(anim_id, frame))
            except Exception:
                pass
        sample = _sample(_frame_values(self._animation), tick)
        if sample is not None:
            (cx, cy, cz), (tx, ty, tz) = sample
            self._readout.setText(
                f"camera ({cx:.0f}, {cy:.0f}, {cz:.0f})   look-at ({tx:.0f}, {ty:.0f}, {tz:.0f})")
            self._gl.set_camera(self._to_viewer(sample[0]), self._to_viewer(sample[1]))

    def _toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
            self._play_button.setText("▶ Play")
        else:
            if self._slider.value() >= self._total:
                self._slider.setValue(0)
            self._timer.start()
            self._play_button.setText("⏸ Pause")

    def _advance(self):
        nxt = self._slider.value() + 1
        if nxt > self._total:  # play once, then stop at the end (no loop)
            self._timer.stop()
            self._play_button.setText("▶ Play")
            return
        self._slider.setValue(nxt)

    def _on_slider(self, value):
        self._apply(value)

    def _set_controls_enabled(self, enabled: bool):
        self._play_button.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._animate_model.setEnabled(enabled)
        self._model_anim_spin.setEnabled(enabled)
