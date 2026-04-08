from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QCheckBox, QPushButton, QSlider, QSpinBox,
                             QListWidget, QListWidgetItem, QGroupBox,
                             QInputDialog, QMessageBox, QFrame)

from FF8GameData.gamedata import AnimationFrame
from Ifrit3D.boneeditorwidget import BoneEditor
from Ifrit3D.ff8openwidget import FF8OpenGLWidget


class Ifrit3DWidget(QWidget):
    frame_changed = pyqtSignal(int)
    animation_finished = pyqtSignal(int)  # Emitted when an animation in playlist finishes
    animation_changed = pyqtSignal()
    def __init__(self, ifrit_manager, show_controls=True):
        super().__init__()
        self.ifrit_manager = ifrit_manager

        # Animation variables
        self.current_anim_id = 0
        self.current_frame = 0
        self.animating = False
        self.fps = 30  # Frames per second
        self.interp_step = 0.0
        self.next_frame_index = 1

        # Playlist variables
        self.playlist = []  # List of animation IDs in order
        self.current_playlist_index = 0
        self.playlist_mode = False
        self.loop_playlist = False
        self.playlist_expanded = False  # Start collapsed

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create OpenGL widget
        self.gl_widget = FF8OpenGLWidget(self)

        # Setup animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)

        if show_controls:
            # Main toolbar
            toolbar = QWidget()
            toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(8, 4, 8, 4)

            # Left side controls
            self.cb_mesh = QCheckBox("3D Mesh")
            self.cb_mesh.setChecked(True)
            self.cb_mesh.setStyleSheet("color:white;")
            self.cb_mesh.toggled.connect(self._on_mesh_toggle)
            toolbar_layout.addWidget(self.cb_mesh)

            self.cb_wire = QCheckBox("Wireframe")
            self.cb_wire.setChecked(True)
            self.cb_wire.setStyleSheet("color:white;")
            self.cb_wire.toggled.connect(self._on_wire_toggle)
            toolbar_layout.addWidget(self.cb_wire)

            self.cb_axis = QCheckBox("Axis")
            self.cb_axis.setChecked(False)
            self.cb_axis.setStyleSheet("color:white;")
            self.cb_axis.toggled.connect(self._on_axis_toggle)
            toolbar_layout.addWidget(self.cb_axis)

            self.cb_skeleton = QCheckBox("Skeleton")
            self.cb_skeleton.setChecked(False)
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

            self.anim_label = QLabel("Anim:")
            self.anim_label.setStyleSheet("color:white; padding:4px 4px;")
            toolbar_layout.addWidget(self.anim_label)

            self.anim_selector = QSpinBox()
            self.anim_selector.setValue(0)
            self.anim_selector.setStyleSheet("color:white; background:#333; padding:2px;")
            self.anim_selector.valueChanged.connect(self.set_animation)
            toolbar_layout.addWidget(self.anim_selector)

            # Spacer
            toolbar_layout.addStretch()

            # Right side controls
            reset_btn = QPushButton("Reset View")
            reset_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            reset_btn.clicked.connect(self.gl_widget.reset_view)
            toolbar_layout.addWidget(reset_btn)

            # Add toolbar to main layout
            layout.addWidget(toolbar)

            # Add the OpenGL widget (this is the 3D view!)
            layout.addWidget(self.gl_widget, 1)  # The 1 makes it stretch to fill available space

            # Collapsible Playlist Section
            self.playlist_container = QWidget()
            self.playlist_container.setStyleSheet("background:#2a2a2f; border-top: 1px solid #3a3a3f;")

            # Create bone editor (independent widget)
            self.bone_editor = BoneEditor()

            # Connect bone editor signals to handlers
            self.bone_editor.bone_selected.connect(self._on_bone_selected)
            self.bone_editor.bone_length_changed.connect(self._on_bone_length_changed)
            self.bone_editor.bone_parent_changed.connect(self._on_bone_parent_changed)
            self.bone_editor.animation_rotation_changed.connect(self._on_animation_rotation_changed)

            # Connect signals to update bone editor
            self.frame_changed.connect(self._update_bone_editor_frame)
            self.animation_changed.connect(self._update_bone_editor_animation)

            # Add bone editor to layout
            layout.addWidget(self.bone_editor)

            playlist_main_layout = QVBoxLayout(self.playlist_container)
            playlist_main_layout.setContentsMargins(0, 0, 0, 0)
            playlist_main_layout.setSpacing(0)

            # Playlist header (always visible)
            playlist_header = QWidget()
            playlist_header.setStyleSheet("background:#2a2a2f; padding:5px;")
            playlist_header.setCursor(Qt.CursorShape.PointingHandCursor)
            header_layout = QHBoxLayout(playlist_header)
            header_layout.setContentsMargins(8, 4, 8, 4)

            # Expand/collapse arrow
            self.expand_arrow = QLabel("▶")
            self.expand_arrow.setStyleSheet("color:white; font-size:12px; font-weight:bold;")
            self.expand_arrow.setFixedWidth(20)
            header_layout.addWidget(self.expand_arrow)

            # Playlist title with count
            self.playlist_title = QLabel("Playlist (0 animations)")
            self.playlist_title.setStyleSheet("color:white; font-weight:bold;")
            header_layout.addWidget(self.playlist_title)

            # Quick action buttons (always visible)
            self.play_playlist_quick_btn = QPushButton("▶ Play")
            self.play_playlist_quick_btn.setStyleSheet("background:#6a8a4e; color:white; padding:2px 8px; border-radius:3px; font-size:10px;")
            self.play_playlist_quick_btn.clicked.connect(self.play_playlist)
            self.play_playlist_quick_btn.setMaximumWidth(60)
            header_layout.addWidget(self.play_playlist_quick_btn)

            self.stop_playlist_quick_btn = QPushButton("■ Stop")
            self.stop_playlist_quick_btn.setStyleSheet("background:#8a6e4a; color:white; padding:2px 8px; border-radius:3px; font-size:10px;")
            self.stop_playlist_quick_btn.clicked.connect(self.stop_playlist)
            self.stop_playlist_quick_btn.setMaximumWidth(60)
            header_layout.addWidget(self.stop_playlist_quick_btn)

            self.loop_quick_cb = QCheckBox("Loop")
            self.loop_quick_cb.setStyleSheet("color:white; font-size:10px;")
            self.loop_quick_cb.toggled.connect(self.set_loop_playlist)
            header_layout.addWidget(self.loop_quick_cb)

            header_layout.addStretch()

            # Make header clickable
            playlist_header.mousePressEvent = self.toggle_playlist

            playlist_main_layout.addWidget(playlist_header)

            # Expandable content (initially hidden)
            self.playlist_content = QWidget()
            self.playlist_content.setVisible(False)
            content_layout = QVBoxLayout(self.playlist_content)
            content_layout.setContentsMargins(8, 4, 8, 8)
            content_layout.setSpacing(4)

            # Playlist list
            self.playlist_list = QListWidget()
            self.playlist_list.setStyleSheet("background:#1a1a1f; color:white; border: 1px solid #3a3a3f;")
            self.playlist_list.setMaximumHeight(120)
            content_layout.addWidget(self.playlist_list)

            # Playlist management buttons
            playlist_buttons = QHBoxLayout()

            self.add_to_playlist_btn = QPushButton("Add Current")
            self.add_to_playlist_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px;")
            self.add_to_playlist_btn.clicked.connect(self.add_current_to_playlist)
            playlist_buttons.addWidget(self.add_to_playlist_btn)

            self.add_custom_btn = QPushButton("Add Custom")
            self.add_custom_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px;")
            self.add_custom_btn.clicked.connect(self.add_custom_to_playlist)
            playlist_buttons.addWidget(self.add_custom_btn)

            self.remove_playlist_btn = QPushButton("Remove")
            self.remove_playlist_btn.setStyleSheet("background:#8a4a6e; color:white; padding:4px;")
            self.remove_playlist_btn.clicked.connect(self.remove_from_playlist)
            playlist_buttons.addWidget(self.remove_playlist_btn)

            self.clear_playlist_btn = QPushButton("Clear All")
            self.clear_playlist_btn.setStyleSheet("background:#8a4a6e; color:white; padding:4px;")
            self.clear_playlist_btn.clicked.connect(self.clear_playlist)
            playlist_buttons.addWidget(self.clear_playlist_btn)

            content_layout.addLayout(playlist_buttons)

            # Playback controls
            playback_controls = QHBoxLayout()

            self.play_playlist_btn = QPushButton("Play Playlist")
            self.play_playlist_btn.setStyleSheet("background:#6a8a4e; color:white; padding:4px;")
            self.play_playlist_btn.clicked.connect(self.play_playlist)
            playback_controls.addWidget(self.play_playlist_btn)

            self.stop_playlist_btn = QPushButton("Stop Playlist")
            self.stop_playlist_btn.setStyleSheet("background:#8a6e4a; color:white; padding:4px;")
            self.stop_playlist_btn.clicked.connect(self.stop_playlist)
            playback_controls.addWidget(self.stop_playlist_btn)

            self.loop_playlist_cb = QCheckBox("Loop Playlist")
            self.loop_playlist_cb.setStyleSheet("color:white;")
            self.loop_playlist_cb.toggled.connect(self.set_loop_playlist)
            playback_controls.addWidget(self.loop_playlist_cb)

            playback_controls.addStretch()
            content_layout.addLayout(playback_controls)

            playlist_main_layout.addWidget(self.playlist_content)

            layout.addWidget(self.playlist_container)

            # Info label
            self.info = QLabel(
                f"LMB: Rotate | RMB: Pan | Scroll: Zoom"
            )
            self.info.setStyleSheet("background:#1a1a1f; color:#aaa; padding:4px 8px; font-size:10px;")
            layout.addWidget(self.info)
        else:
            # Without controls, just show the OpenGL widget
            layout.addWidget(self.gl_widget, 1)

    def toggle_playlist(self, event=None):
        """Toggle playlist expand/collapse"""
        self.playlist_expanded = not self.playlist_expanded
        self.playlist_content.setVisible(self.playlist_expanded)

        # Update arrow direction
        if self.playlist_expanded:
            self.expand_arrow.setText("▼")
            # Adjust container height
            self.playlist_container.setMaximumHeight(300)
        else:
            self.expand_arrow.setText("▶")
            # Collapse to just header height
            self.playlist_container.setMaximumHeight(50)

    # Playlist management methods
    def add_current_to_playlist(self):
        """Add current animation to playlist"""
        self.playlist.append(self.current_anim_id)
        self._update_playlist_display()

    def add_custom_to_playlist(self):
        """Add custom animation ID to playlist"""
        anim_id, ok = QInputDialog.getInt(self, "Add Animation",
                                          "Enter animation ID:",
                                          value=0,
                                          min=0,
                                          max=len(self.ifrit_manager.enemy.animation_data.animations) - 1)
        if ok:
            self.playlist.append(anim_id)
            self._update_playlist_display()

    def remove_from_playlist(self):
        """Remove selected animation from playlist"""
        current_row = self.playlist_list.currentRow()
        if current_row >= 0 and current_row < len(self.playlist):
            self.playlist.pop(current_row)
            self._update_playlist_display()

    def clear_playlist(self):
        """Clear entire playlist"""
        self.playlist.clear()
        self._update_playlist_display()

    def _update_playlist_display(self):
        """Update the playlist display list"""
        self.playlist_list.clear()
        for i, anim_id in enumerate(self.playlist):
            item_text = f"{i + 1}. Animation {anim_id}"
            # Highlight current playing item
            if self.playlist_mode and i == self.current_playlist_index:
                item_text = f"▶ {item_text}"
            item = QListWidgetItem(item_text)
            self.playlist_list.addItem(item)

        # Update title with count
        count_text = f"Playlist ({len(self.playlist)} animation{'s' if len(self.playlist) != 1 else ''})"
        self.playlist_title.setText(count_text)

    def play_playlist(self):
        """Start playing the playlist"""
        if not self.playlist:
            QMessageBox.information(self, "Playlist Empty",
                                    "Please add animations to the playlist first.")
            return

        # Stop any current playlist playback
        self.stop_playlist()

        self.playlist_mode = True
        self.current_playlist_index = 0
        self.loop_playlist = self.loop_playlist_cb.isChecked()
        self.loop_quick_cb.setChecked(self.loop_playlist)

        # Start first animation in playlist
        self._play_playlist_item()

    def _play_playlist_item(self):
        """Play the current playlist item"""
        if self.current_playlist_index >= len(self.playlist):
            # Playlist finished
            if self.loop_playlist:
                # Loop back to start
                self.current_playlist_index = 0
                self._play_playlist_item()
            else:
                # Stop playlist
                self.playlist_mode = False
                self.stop_playlist()
            return

        # Set the animation
        anim_id = self.playlist[self.current_playlist_index]
        self.set_animation(anim_id)
        self.animation_changed.emit()

        # Reset frame
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        self.update_animated_mesh()
        self.update_skeleton()

        # Start animation if not already playing
        if not self.animating:
            self.timer.start(1000 // self.fps)
            self.play_btn.setText("Pause")
            self.animating = True

        self._update_playlist_display()

    def stop_playlist(self):
        """Stop playlist playback"""
        self.playlist_mode = False
        self.current_playlist_index = 0

        # Stop animation if playing
        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False

        self._update_playlist_display()

    def set_loop_playlist(self, checked):
        """Set whether playlist should loop"""
        self.loop_playlist = checked
        # Sync the quick checkbox
        if hasattr(self, 'loop_quick_cb'):
            self.loop_quick_cb.blockSignals(True)
            self.loop_quick_cb.setChecked(checked)
            self.loop_quick_cb.blockSignals(False)

    def next_frame(self):
        """Advance to next frame with interpolation"""
        max_frames = self.get_max_frames()

        if max_frames > 0:
            # Update interpolation step
            if self.animating:
                self.interp_step += 1.0 / (self.fps / 30.0)  # Assuming 30 fps base
                if self.interp_step >= 1.0:
                    self.interp_step = 0.0
                    self.current_frame = (self.current_frame + 1) % max_frames
                    self.next_frame_index = (self.current_frame + 1) % max_frames

                    # Check if animation finished (when we wrap around to frame 0)
                    if self.current_frame == 0 and self.playlist_mode:
                        # Current animation finished, move to next in playlist
                        self.current_playlist_index += 1
                        self._play_playlist_item()
                        self.animation_changed.emit()
                        return
            else:
                # When not animating, just update to current frame
                self.update_animated_mesh()
                self.update_skeleton()
                return

            # Update both mesh and skeleton
            self.update_animated_mesh()
            self.update_skeleton()

    # Keep all your existing methods from the original code
    def load_file(self, path: str):
        if self.animating:
            self.timer.stop()
            if hasattr(self, 'play_btn'):
                self.play_btn.setText("Play")
            self.animating = False

        self.current_anim_id = 0
        self.current_frame = 0
        self.interp_step = 0.0
        self.next_frame_index = 1
        verts = self.ifrit_manager.get_animated_vertices(self.current_anim_id, self.current_frame)
        self.gl_widget.set_vertices(verts)
        self.gl_widget.reset_view()
        self.gl_widget.set_triangles(self.ifrit_manager.enemy.geometry_data.get_triangles())
        self.gl_widget.set_quads(self.ifrit_manager.enemy.geometry_data.get_quads())
        self.update_skeleton()

        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
        if hasattr(self, 'anim_selector'):
            nb = len(self.ifrit_manager.enemy.animation_data.animations)
            self.anim_selector.setRange(0, nb - 1)
            self.anim_selector.setValue(0)
            self.anim_selector.setToolTip(f"Nb animation: {nb}")
        self.info.setText(f"Tri: {len(self.gl_widget.triangles)} | "
                          f"Quads: {len(self.gl_widget.quads)} | "
                          f"Bones: {len(self.gl_widget.skeleton_lines)} | "
                          f"LMB: Rotate | RMB: Pan | Scroll: Zoom")
        if hasattr(self, 'bone_editor'):
            bone_count = len(self.ifrit_manager.enemy.bone_data.bones) - 1
            self.bone_editor.set_bone_range(bone_count)
            # Set the initial bone ID to 0 and update
            self.bone_editor.bone_spin.setValue(0)
            self._update_bone_editor_selection()

    def get_max_frames(self):
        if not self.ifrit_manager:
            return 0
        anim_section = self.ifrit_manager.enemy.animation_data
        if anim_section and self.current_anim_id < len(anim_section.animations):
            return anim_section.animations[self.current_anim_id].get_nb_frame()
        return 0

    def set_animation(self, anim_id: int):
        """Switch to a different animation while preserving playback state."""
        # Store the current animation state
        was_animating = self.animating

        # Stop playback temporarily if it was running
        if was_animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False

        # Switch animation and reset to frame 0
        self.current_anim_id = anim_id
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0

        # Update slider range for new animation
        max_frames = self.get_max_frames()
        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, max_frames - 1)

        # Update the mesh and skeleton to the new animation's first frame
        self.update_animated_mesh()
        self.update_skeleton()

        self.animation_changed.emit()

        # Restart animation if it was previously playing
        if was_animating:
            self.timer.start(1000 // self.fps)
            self.play_btn.setText("Pause")
            self.animating = True

    def update_skeleton(self):
        if not self.ifrit_manager:
            return
        skeleton_lines, bone_parents = self.ifrit_manager.get_skeleton_lines(
            anim_id=self.current_anim_id, frame_id=self.current_frame)

        # Set both lines and parents
        self.gl_widget.set_skeleton_data(skeleton_lines, bone_parents)
        self.gl_widget.update()
        if hasattr(self, 'frame_label'):
            self.frame_label.setText(f"Frame: {self.current_frame}")
        if hasattr(self, 'frame_slider'):
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_frame)
            self.frame_slider.blockSignals(False)
        self.frame_changed.emit(self.current_frame)

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

    def update_animated_mesh(self):
        """Update mesh vertices based on current frame"""
        # Get current and next frame for interpolation
        max_frames = self.get_max_frames()
        if max_frames == 0:
            return

        next_frame = (self.current_frame + 1) % max_frames

        # Get animated vertices with interpolation
        animated_verts = self.ifrit_manager.get_animated_vertices(
            anim_id=self.current_anim_id,
            frame_id=self.current_frame,
            next_frame_id=next_frame,
            step=self.interp_step
        )

        self.current_animated_vertices = animated_verts

        # Update the OpenGL widget with new vertices
        self.gl_widget.set_vertices(animated_verts)

        # Triangles and quads indices remain the same (only vertex positions change)
        self.gl_widget.set_triangles(self.ifrit_manager.enemy.geometry_data.get_triangles())
        self.gl_widget.set_quads(self.ifrit_manager.enemy.geometry_data.get_quads())

        self.gl_widget.update()

    def set_frame(self, value):
        """Jump to specific frame"""
        if not self.animating:
            self.current_frame = value
            self.next_frame_index = (self.current_frame + 1) % self.get_max_frames()
            self.interp_step = 0.0
            self.update_animated_mesh()
            self.update_skeleton()
            if hasattr(self, 'frame_slider'):
                self.frame_slider.blockSignals(True)
                self.frame_slider.setValue(self.current_frame)
                self.frame_slider.blockSignals(False)

    def reset_animation(self):
        """Reset to first frame"""
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        self.update_animated_mesh()
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

    def _update_bone_editor_frame(self, frame):
        """Update bone editor when frame changes"""
        if hasattr(self, 'bone_editor'):
            self.bone_editor.set_animation_info(self.current_anim_id, frame)
            self._update_bone_editor_selection()

    def _update_bone_editor_animation(self):
        """Update bone editor when animation changes"""
        if hasattr(self, 'bone_editor'):
            self.bone_editor.set_animation_info(self.current_anim_id, self.current_frame)
            self._update_bone_editor_selection()

    def _update_bone_editor_selection(self):
        """Update the bone editor with current bone data"""
        bone_id = self.bone_editor.bone_spin.value()
        if bone_id < 0 or bone_id >= len(self.ifrit_manager.enemy.bone_data.bones):
            return

        bone = self.ifrit_manager.enemy.bone_data.bones[bone_id]

        # Get animation rotation if available
        rot_x, rot_y, rot_z = 0, 0, 0
        if (self.current_anim_id < len(self.ifrit_manager.enemy.animation_data.animations) and
                self.current_frame < len(self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames)):
            frame: AnimationFrame = self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames[self.current_frame]
            if bone_id < len(frame.rotation_vector_data):
                rot_x, rot_y, rot_z = frame.rotation_vector_data[bone_id][0].get_rotate_deg(), frame.rotation_vector_data[bone_id][1].get_rotate_deg(),frame.rotation_vector_data[bone_id][2].get_rotate_deg()

        self.bone_editor.set_bone_data(
            bone_id, bone.size, bone.parent_id, rot_x, rot_y, rot_z
        )

    def _on_bone_selected(self, bone_id: int):
        """Handle bone selection from editor"""
        self._update_bone_editor_selection()
        self.gl_widget.set_selected_bone(bone_id)
        self.gl_widget.update()

    def _on_bone_length_changed(self, bone_id: int, length: float):
        """Handle bone length change from editor"""
        self.ifrit_manager.set_bone_length(bone_id, length)
        self.update_skeleton()
        self.update_animated_mesh()

    def _on_bone_parent_changed(self, bone_id: int, parent_id: int):
        """Handle bone parent change from editor"""
        self.ifrit_manager.set_bone_parent(bone_id, parent_id)
        self.update_skeleton()
        self.update_animated_mesh()

    def _on_animation_rotation_changed(self, anim_id: int, frame_id: int,
                                       bone_id: int, rx: float, ry: float, rz: float):
        """Handle animation rotation change from editor"""
        self.ifrit_manager.set_animation_frame_bone_rotation(anim_id, frame_id, bone_id, rx, ry, rz)
        self.update_animated_mesh()
        self.update_skeleton()

    # Add to Ifrit3DWidget class

    def export_to_fbx(self, filepath: str):
        """Export current monster to FBX"""
        exporter = FF8ToFBXExporter(self.ifrit_manager)
        exporter.export(filepath)
        QMessageBox.information(self, "Export Complete", f"Exported to {filepath}")

    def import_from_fbx(self, filepath: str):
        """Import FBX and update model"""
        importer = FBXImporter(self.ifrit_manager)
        importer.import_file(filepath)
        # Refresh the display
        self.load_file(filepath)  # Or refresh current view
        QMessageBox.information(self, "Import Complete", f"Imported from {filepath}")