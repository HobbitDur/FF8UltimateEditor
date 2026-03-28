from PyQt6.QtCore import QTimer, Qt

from Ifrit3D.ff8openwidget import FF8OpenGLWidget
from Ifrit3D.ifrit3dmanager import Ifrit3DManager
import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton, QSlider
from PyQt6.QtGui import QSurfaceFormat


class Ifrit3DWidget(QWidget):
    def __init__(self, parent=None, show_controls=True):
        super().__init__(parent)
        self.ifrit3d_manager = Ifrit3DManager("c0m071.dat")
        # Animation variables
        self.current_anim_id = 0
        self.current_frame = 0
        self.animating = False
        self.fps = 30  # Frames per second

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.gl_widget = FF8OpenGLWidget(self)
        self.gl_widget.set_vertices(self.ifrit3d_manager.monster_data.geometry_data.get_vertices())
        self.gl_widget.set_triangles(self.ifrit3d_manager.monster_data.geometry_data.get_triangles())
        self.gl_widget.set_quads(self.ifrit3d_manager.monster_data.geometry_data.get_quads())

        # Set initial skeleton
        self.update_skeleton()
        # Setup animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)

        if show_controls:
            toolbar = QWidget()
            toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(8, 4, 8, 4)

            # Left side controls
            # Toggle for 3D mesh
            self.cb_mesh = QCheckBox("3D Mesh")
            self.cb_mesh.setChecked(True)
            self.cb_mesh.setStyleSheet("color:white;")
            self.cb_mesh.toggled.connect(self._on_mesh_toggle)
            toolbar_layout.addWidget(self.cb_mesh)

            # Toggle for wireframe
            self.cb_wire = QCheckBox("Wireframe")
            self.cb_wire.setChecked(True)
            self.cb_wire.setStyleSheet("color:white;")
            self.cb_wire.toggled.connect(self._on_wire_toggle)
            toolbar_layout.addWidget(self.cb_wire)

            # Toggle for axis
            self.cb_axis = QCheckBox("Axis")
            self.cb_axis.setChecked(True)
            self.cb_axis.setStyleSheet("color:white;")
            self.cb_axis.toggled.connect(self._on_axis_toggle)
            toolbar_layout.addWidget(self.cb_axis)

            # Toggle for skeleton
            self.cb_skeleton = QCheckBox("Skeleton")
            self.cb_skeleton.setChecked(True)
            self.cb_skeleton.setStyleSheet("color:white;")
            self.cb_skeleton.toggled.connect(self._on_skeleton_toggle)
            toolbar_layout.addWidget(self.cb_skeleton)

            # Animation controls
            self.play_btn = QPushButton("Play")
            self.play_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.play_btn.clicked.connect(self.toggle_animation)
            toolbar_layout.addWidget(self.play_btn)

            self.reset_anim_btn = QPushButton("Reset Anim")
            self.reset_anim_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.reset_anim_btn.clicked.connect(self.reset_animation)
            toolbar_layout.addWidget(self.reset_anim_btn)

            self.frame_label = QLabel("Frame: 0")
            self.frame_label.setStyleSheet("color:white; padding:4px 8px;")
            toolbar_layout.addWidget(self.frame_label)

            # Frame slider
            self.frame_slider = QSlider(Qt.Orientation.Horizontal)
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
            self.frame_slider.setStyleSheet("color:white;")
            self.frame_slider.valueChanged.connect(self.set_frame)
            toolbar_layout.addWidget(self.frame_slider)

            # Spacer to push right-side controls to the right
            toolbar_layout.addStretch()

            # Right side controls
            reset_btn = QPushButton("Reset View")
            reset_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            reset_btn.clicked.connect(self.gl_widget.reset_view)
            toolbar_layout.addWidget(reset_btn)

            # Info label at the bottom
            info = QLabel(
                f"Tri: {len(self.gl_widget.triangles)} | "
                f"Quads: {len(self.gl_widget.quads)} | "
                f"Bones: {len(self.gl_widget.skeleton_lines)} | "
                f"LMB: Rotate | RMB: Pan | Scroll: Zoom"
            )
            info.setStyleSheet("background:#1a1a1f; color:#aaa; padding:4px 8px; font-size:10px;")

            layout.addWidget(toolbar)
            layout.addWidget(self.gl_widget, 1)
            layout.addWidget(info)
        else:
            layout.addWidget(self.gl_widget, 1)

    def get_max_frames(self):
        """Get maximum frames for current animation"""
        anim_section = self.ifrit3d_manager.monster_data.animation_data
        if anim_section and self.current_anim_id < len(anim_section.animations):
            return anim_section.animations[self.current_anim_id].nb_frames
        return 0

    def update_skeleton(self):
        """Update skeleton for current frame"""
        skeleton_lines = self.ifrit3d_manager.get_skeleton_lines(
            anim_id=self.current_anim_id,
            frame_id=self.current_frame
        )

        self.gl_widget.set_skeleton_lines(skeleton_lines)
        self.gl_widget.update()

        # Update UI - only if controls exist
        if hasattr(self, 'frame_label'):
            self.frame_label.setText(f"Frame: {self.current_frame}")

        # Update slider without triggering its signal
        if hasattr(self, 'frame_slider'):
            # Block signals to prevent recursive call
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_frame)
            self.frame_slider.blockSignals(False)

    def next_frame(self):
        """Advance to next frame"""
        max_frames = self.get_max_frames()

        if max_frames > 0:
            old_frame = self.current_frame
            self.current_frame = (self.current_frame + 1) % max_frames
            self.update_skeleton()

    def toggle_animation(self):
        """Start/stop animation"""

        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False
        else:
            self.timer.start(1000 // self.fps)
            self.play_btn.setText("Pause")
            self.animating = True

    def reset_animation(self):
        """Reset to first frame"""
        self.current_frame = 0
        self.update_skeleton()
        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False

    def set_frame(self, value):
        """Jump to specific frame"""
        # Only respond if this was triggered by user (not during animation)
        if not self.animating:
            self.current_frame = value
            self.update_skeleton()
            if self.animating:
                self.timer.stop()
                self.play_btn.setText("Play")
                self.animating = False
    def _on_mesh_toggle(self, checked):
        """Toggle 3D mesh visibility"""
        self.gl_widget.set_show_mesh(checked)

    def _on_wire_toggle(self, checked):
        self.gl_widget.set_show_wireframe(checked)

    def _on_axis_toggle(self, checked):
        self.gl_widget.set_show_axis(checked)

    def _on_skeleton_toggle(self, checked):
        self.gl_widget.set_show_skeleton(checked)

    def set_show_skeleton(self, show):
        self.gl_widget.set_show_skeleton(show)
        if hasattr(self, 'cb_skeleton'):
            self.cb_skeleton.setChecked(show)
    # Public methods for external control
    def reset_view(self):
        """Reset camera position"""
        self.gl_widget.reset_view()

    def set_show_wireframe(self, show):
        self.gl_widget.set_show_wireframe(show)
        if hasattr(self, 'cb_wire'):
            self.cb_wire.setChecked(show)

    def set_show_axis(self, show):
        self.gl_widget.set_show_axis(show)
        if hasattr(self, 'cb_axis'):
            self.cb_axis.setChecked(show)

    def get_gl_widget(self):
        """Return the underlying OpenGL widget for advanced control"""
        return self.gl_widget