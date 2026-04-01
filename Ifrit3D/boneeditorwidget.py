from PyQt6.QtWidgets import (QFormLayout, QSpinBox, QDoubleSpinBox,
                             QPushButton, QVBoxLayout, QHBoxLayout,
                             QLabel, QWidget, QTabWidget)
from PyQt6.QtCore import Qt, pyqtSignal


class BoneEditor(QWidget):
    """Independent bone editor widget that communicates via signals"""

    # Signals that the main widget can connect to
    bone_selected = pyqtSignal(int)
    bone_length_changed = pyqtSignal(int, float)
    bone_parent_changed = pyqtSignal(int, int)
    animation_rotation_changed = pyqtSignal(int, int, int, float, float, float)

    def __init__(self):
        super().__init__()

        # Data that will be set by the controller
        self.current_anim_id = 0
        self.current_frame = 0
        self.bone_count = 0
        self._updating = False  # Flag to prevent recursive updates

        # Track expanded state
        self.expanded = False

        # Build UI
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (always visible, clickable)
        self.header = QWidget()
        self.header.setStyleSheet("background:#2a2a2f; padding:5px;")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        # Expand/collapse arrow
        self.expand_arrow = QLabel("▶")
        self.expand_arrow.setStyleSheet("color:white; font-size:12px; font-weight:bold;")
        self.expand_arrow.setFixedWidth(20)
        header_layout.addWidget(self.expand_arrow)

        # Title
        self.title = QLabel("Bone Editor")
        self.title.setStyleSheet("color:white; font-weight:bold;")
        header_layout.addWidget(self.title)

        # Quick info label
        self.info_label = QLabel("No bone selected")
        self.info_label.setStyleSheet("color:#aaa; font-size:10px;")
        header_layout.addWidget(self.info_label)

        header_layout.addStretch()

        # Make header clickable
        self.header.mousePressEvent = self.toggle_expand

        layout.addWidget(self.header)

        # Content (expandable)
        self.content = QWidget()
        self.content.setVisible(False)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)

        # Bone selection
        bone_sel_layout = QHBoxLayout()
        self.bone_spin = QSpinBox()
        self.bone_spin.setRange(0, 0)
        self.bone_spin.valueChanged.connect(self._on_bone_selected)
        bone_sel_layout.addWidget(QLabel("Bone ID:"))
        bone_sel_layout.addWidget(self.bone_spin)

        # Current frame info
        self.frame_info = QLabel("Frame: 0")
        self.frame_info.setStyleSheet("color:#aaa;")
        bone_sel_layout.addWidget(self.frame_info)

        bone_sel_layout.addStretch()
        content_layout.addLayout(bone_sel_layout)

        # Create tabs
        self.tabs = QTabWidget()

        # Static Properties Tab
        self.static_tab = QWidget()
        static_layout = QFormLayout(self.static_tab)

        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(-100, 100)
        self.length_spin.setSingleStep(0.1)
        self.length_spin.setDecimals(3)
        self.length_spin.valueChanged.connect(self._on_length_changed)
        static_layout.addRow("Length:", self.length_spin)

        self.parent_spin = QSpinBox()
        self.parent_spin.setRange(-1, 0)
        self.parent_spin.valueChanged.connect(self._on_parent_changed)
        static_layout.addRow("Parent ID:", self.parent_spin)

        static_layout.addRow("", QLabel("(Static properties affect all animations)"))

        self.tabs.addTab(self.static_tab, "Static Properties")

        # Animation Tab
        self.anim_tab = QWidget()
        anim_layout = QFormLayout(self.anim_tab)

        self.anim_rotx = QDoubleSpinBox()
        self.anim_rotx.setRange(-360, 360)
        self.anim_rotx.setSingleStep(1)
        self.anim_rotx.setDecimals(2)
        self.anim_rotx.valueChanged.connect(self._on_anim_rotation_changed)
        self.anim_roty = QDoubleSpinBox()
        self.anim_roty.setRange(-360, 360)
        self.anim_roty.setSingleStep(1)
        self.anim_roty.setDecimals(2)
        self.anim_roty.valueChanged.connect(self._on_anim_rotation_changed)
        self.anim_rotz = QDoubleSpinBox()
        self.anim_rotz.setRange(-360, 360)
        self.anim_rotz.setSingleStep(1)
        self.anim_rotz.setDecimals(2)
        self.anim_rotz.valueChanged.connect(self._on_anim_rotation_changed)

        anim_layout.addRow("Rot X:", self.anim_rotx)
        anim_layout.addRow("Rot Y:", self.anim_roty)
        anim_layout.addRow("Rot Z:", self.anim_rotz)

        # Animation info
        self.anim_info = QLabel("Current Animation: 0, Frame: 0")
        self.anim_info.setStyleSheet("color:#aaa; font-size:10px;")
        anim_layout.addRow("", self.anim_info)

        self.tabs.addTab(self.anim_tab, "Animation Frame")

        content_layout.addWidget(self.tabs)

        layout.addWidget(self.content)

    def toggle_expand(self, event=None):
        """Toggle expand/collapse"""
        self.expanded = not self.expanded
        self.content.setVisible(self.expanded)

        if self.expanded:
            self.expand_arrow.setText("▼")
            self.setMaximumHeight(500)
            # Try to find parent and request skeleton visibility
            parent = self.parent()
            while parent:
                if hasattr(parent, 'set_show_skeleton'):
                    parent.set_show_skeleton(True)
                    if hasattr(parent, 'cb_skeleton'):
                        parent.cb_skeleton.setChecked(True)
                    break
                parent = parent.parent()
        else:
            self.expand_arrow.setText("▶")
            self.setMaximumHeight(50)

    def set_bone_data(self, bone_id: int, length: float, parent_id: int,
                      rot_x: float, rot_y: float, rot_z: float):
        """Update the editor with new bone data"""
        self._updating = True

        try:
            # Update static tab
            self.parent_spin.blockSignals(True)
            self.length_spin.blockSignals(True)

            # Update spinbox range if needed
            max_parent = self.parent_spin.maximum()
            if parent_id != 0xFFFF and parent_id > max_parent:
                self.parent_spin.setRange(-1, parent_id)

            self.parent_spin.setValue(parent_id if parent_id != 0xFFFF else -1)
            self.length_spin.setValue(length)

            self.parent_spin.blockSignals(False)
            self.length_spin.blockSignals(False)

            # Update animation tab
            self.anim_rotx.blockSignals(True)
            self.anim_roty.blockSignals(True)
            self.anim_rotz.blockSignals(True)

            self.anim_rotx.setValue(rot_x)
            self.anim_roty.setValue(rot_y)
            self.anim_rotz.setValue(rot_z)

            self.anim_rotx.blockSignals(False)
            self.anim_roty.blockSignals(False)
            self.anim_rotz.blockSignals(False)

            # Update info
            self.info_label.setText(f"Bone {bone_id}")

            # Update bone spin if different
            if self.bone_spin.value() != bone_id:
                self.bone_spin.blockSignals(True)
                self.bone_spin.setValue(bone_id)
                self.bone_spin.blockSignals(False)

        finally:
            self._updating = False

    def set_animation_info(self, anim_id: int, frame_id: int):
        """Update animation info display"""
        self.current_anim_id = anim_id
        self.current_frame = frame_id
        self.frame_info.setText(f"Anim: {anim_id}, Frame: {frame_id}")
        self.anim_info.setText(f"Current Animation: {anim_id}, Frame: {frame_id}")
        self._update_tab_states()

    def set_bone_range(self, max_bone: int):
        """Set the maximum bone ID"""
        self.bone_count = max_bone + 1
        self.bone_spin.setRange(0, max_bone)

    def _update_tab_states(self):
        """Update which tabs are enabled based on data availability"""
        has_animation = (hasattr(self, 'current_anim_id') and self.current_anim_id >= 0)
        self.tabs.setTabEnabled(1, has_animation)

    def _on_bone_selected(self, bone_id: int):
        """Handle bone selection"""
        if not self._updating:
            self.bone_selected.emit(bone_id)

    def _on_length_changed(self, value: float):
        """Handle length change"""
        if not self._updating:
            bone_id = self.bone_spin.value()
            self.bone_length_changed.emit(bone_id, value)

    def _on_parent_changed(self, value: int):
        """Handle parent change"""
        if not self._updating:
            bone_id = self.bone_spin.value()
            parent_id = value if value != -1 else 0xFFFF
            self.bone_parent_changed.emit(bone_id, parent_id)

    def _on_anim_rotation_changed(self):
        """Handle animation rotation change"""
        if not self._updating:
            bone_id = self.bone_spin.value()
            rx = self.anim_rotx.value()
            ry = self.anim_roty.value()
            rz = self.anim_rotz.value()
            self.animation_rotation_changed.emit(
                self.current_anim_id, self.current_frame, bone_id, rx, ry, rz
            )