from PyQt6.QtWidgets import (QFormLayout, QSpinBox, QDoubleSpinBox,
                             QPushButton, QVBoxLayout, QHBoxLayout,
                             QLabel, QWidget, QTabWidget, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal


class AnimEditor(QWidget):
    """Independent bone editor widget that communicates via signals"""

    # Signals that the main widget can connect to
    bone_selected = pyqtSignal(int)
    bone_length_changed = pyqtSignal(int, float)
    bone_parent_changed = pyqtSignal(int, int)
    add_bone_requested = pyqtSignal(int)       # parent bone id
    reset_skeleton_requested = pyqtSignal()
    animation_rotation_changed = pyqtSignal(int, int, int, float, float, float)
    animation_position_changed = pyqtSignal(int, int, float, float, float)
    animation_scale_changed = pyqtSignal(int, int, int, float, float, float)
    frame_scale_mode_changed = pyqtSignal(int, int, bool)

    def __init__(self):
        super().__init__()

        # Data that will be set by the controller
        self.current_anim_id = 0
        self.current_frame = 0
        self.bone_count = 0
        self._updating = False  # Flag to prevent recursive updates
        self._compare_bone_ids = []   # bones currently shown in the multi-select comparison tables

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
        self.title = QLabel("Anim Editor")
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
        self.length_spin_layout = QHBoxLayout()

        self.length_spin_layout.addWidget(self.length_spin)
        self.length_raw = QLabel("raw: 0")
        self.length_raw.setStyleSheet("color:#888; font-size:9px;")
        self.length_raw.setFixedWidth(60)
        self.length_spin_layout.addWidget(self.length_raw)
        self.length_spin_layout.addStretch(1)
        static_layout.addRow("Length:", self.length_spin_layout)

        self.parent_spin = QSpinBox()
        self.parent_spin.setRange(-1, -1)
        self.parent_spin.valueChanged.connect(self._on_parent_changed)
        self.parent_spin_layout = QHBoxLayout()

        self.parent_spin_layout.addWidget( self.parent_spin)
        self.parent_spin_layout.addStretch(1)
        static_layout.addRow("Parent ID:", self.parent_spin_layout)

        skeleton_btn_layout = QHBoxLayout()
        self.add_bone_btn = QPushButton("Add child bone")
        self.add_bone_btn.setToolTip("Create a new bone attached to the selected joint (shortcut: B).\n"
                                     "It starts with zero rotation on every frame of every animation.")
        self.add_bone_btn.clicked.connect(self._on_add_bone_clicked)
        skeleton_btn_layout.addWidget(self.add_bone_btn)
        self.reset_skeleton_btn = QPushButton("New skeleton")
        self.reset_skeleton_btn.setToolTip("Start a skeleton from scratch: delete every bone except\n"
                                           "the root joint. The whole mesh gets attached to the root.")
        self.reset_skeleton_btn.clicked.connect(self.reset_skeleton_requested.emit)
        skeleton_btn_layout.addWidget(self.reset_skeleton_btn)
        skeleton_btn_layout.addStretch(1)
        static_layout.addRow("Skeleton:", skeleton_btn_layout)

        static_layout.addRow("", QLabel("(Bones properties affect all animations)"))

        # Multi-select comparison (Ctrl+click several bones): an editable row per selected bone.
        # Hidden while a single bone is selected (the form above is used then).
        self.static_compare = self._new_compare_table(["Bone", "Length", "Parent"])
        static_layout.addRow(self.static_compare)

        self.tabs.addTab(self.static_tab, "Bones Properties")

        # Frame Position Tab (NEW)
        self.position_tab = QWidget()
        position_layout = QFormLayout(self.position_tab)

        pos_x_layout = QHBoxLayout()
        self.frame_pos_x = QDoubleSpinBox()
        self.frame_pos_x.setRange(-10000, 10000)
        # 1 raw position unit = 1/204.8 world (PositionType.get_pos_world), i.e. 204.8 raw values
        # per world unit. 4 decimals (>=3 are the minimum: 10^3 slots > 204.8) lets every raw
        # position be reached by typing; the 0.005 step nudges ~1 raw. Previously 1 decimal
        # (0.1 world = ~20 raw) could only address ~1 in every 20 raw positions.
        self.frame_pos_x.setSingleStep(0.005)
        self.frame_pos_x.setDecimals(4)
        self.frame_pos_x.valueChanged.connect(self._on_anim_position_changed)
        self.pos_x_raw = QLabel("raw: 0")
        self.pos_x_raw.setStyleSheet("color:#888; font-size:9px;")
        self.pos_x_raw.setFixedWidth(60)
        pos_x_layout.addWidget(self.frame_pos_x)
        pos_x_layout.addWidget(self.pos_x_raw)
        pos_x_layout.addStretch(1)
        position_layout.addRow("Pos X:", pos_x_layout)

        pos_y_layout = QHBoxLayout()
        self.frame_pos_y = QDoubleSpinBox()
        self.frame_pos_y.setRange(-10000, 10000)
        self.frame_pos_y.setSingleStep(0.005)   # see Pos X: 204.8 raw/unit -> 4 decimals
        self.frame_pos_y.setDecimals(4)
        self.frame_pos_y.valueChanged.connect(self._on_anim_position_changed)
        self.pos_y_raw = QLabel("raw: 0")
        self.pos_y_raw.setStyleSheet("color:#888; font-size:9px;")
        self.pos_y_raw.setFixedWidth(60)
        pos_y_layout.addWidget(self.frame_pos_y)
        pos_y_layout.addWidget(self.pos_y_raw)
        pos_y_layout.addStretch(1)
        position_layout.addRow("Pos Y:", pos_y_layout)

        pos_z_layout = QHBoxLayout()
        self.frame_pos_z = QDoubleSpinBox()
        self.frame_pos_z.setRange(-10000, 10000)
        self.frame_pos_z.setSingleStep(0.005)   # see Pos X: 204.8 raw/unit -> 4 decimals
        self.frame_pos_z.setDecimals(4)
        self.frame_pos_z.valueChanged.connect(self._on_anim_position_changed)
        self.pos_z_raw = QLabel("raw: 0")
        self.pos_z_raw.setStyleSheet("color:#888; font-size:9px;")
        self.pos_z_raw.setFixedWidth(60)
        pos_z_layout.addWidget(self.frame_pos_z)
        pos_z_layout.addWidget(self.pos_z_raw)
        pos_z_layout.addStretch(1)
        position_layout.addRow("Pos Z:", pos_z_layout)

        # Position info
        self.position_info = QLabel("Frame Position is defined for each frame, affecting the full 3D model")
       # self.position_info.setStyleSheet("color:#aaa; font-size:10px;")
        position_layout.addRow("", self.position_info)

        self.tabs.addTab(self.position_tab, "Frame Position")

        # Animation Rotation Tab
        self.anim_tab = QWidget()
        anim_layout = QFormLayout(self.anim_tab)

        rot_x_layout = QHBoxLayout()
        self.anim_rotx = QDoubleSpinBox()
        self.anim_rotx.setRange(-360, 360)
        # 1 raw rotation unit = 360/4096 = 0.088 deg (11.4 raw per degree). 3 decimals resolves
        # every raw with margin (10^3 slots >> 11.4); the 0.1 step nudges ~1 raw.
        self.anim_rotx.setSingleStep(0.1)
        self.anim_rotx.setDecimals(3)
        self.anim_rotx.valueChanged.connect(self._on_anim_rotation_changed)
        self.rot_x_raw = QLabel("raw: 0")
        self.rot_x_raw.setStyleSheet("color:#888; font-size:9px;")
        self.rot_x_raw.setFixedWidth(60)
        rot_x_layout.addWidget(self.anim_rotx)
        rot_x_layout.addWidget(self.rot_x_raw)
        rot_x_layout.addStretch(1)
        anim_layout.addRow("Rot X:", rot_x_layout)

        rot_y_layout = QHBoxLayout()
        self.anim_roty = QDoubleSpinBox()
        self.anim_roty.setRange(-360, 360)
        self.anim_roty.setSingleStep(0.1)       # see Rot X: 11.4 raw/deg -> 3 decimals
        self.anim_roty.setDecimals(3)
        self.anim_roty.valueChanged.connect(self._on_anim_rotation_changed)
        self.rot_y_raw = QLabel("raw: 0")
        self.rot_y_raw.setStyleSheet("color:#888; font-size:9px;")
        self.rot_y_raw.setFixedWidth(60)
        rot_y_layout.addWidget(self.anim_roty)
        rot_y_layout.addWidget(self.rot_y_raw)
        rot_y_layout.addStretch(1)
        anim_layout.addRow("Rot Y:", rot_y_layout)

        rot_z_layout = QHBoxLayout()
        self.anim_rotz = QDoubleSpinBox()
        self.anim_rotz.setRange(-360, 360)
        self.anim_rotz.setSingleStep(0.1)       # see Rot X: 11.4 raw/deg -> 3 decimals
        self.anim_rotz.setDecimals(3)
        self.anim_rotz.valueChanged.connect(self._on_anim_rotation_changed)
        self.rot_z_raw = QLabel("raw: 0")
        self.rot_z_raw.setStyleSheet("color:#888; font-size:9px;")
        self.rot_z_raw.setFixedWidth(60)
        rot_z_layout.addWidget(self.anim_rotz)
        rot_z_layout.addWidget(self.rot_z_raw)
        rot_z_layout.addStretch(1)
        anim_layout.addRow("Rot Z:", rot_z_layout)

        self.propagate_rotation_cb = QCheckBox("Apply to all following frames")
        self.propagate_rotation_cb.setChecked(True)
        self.propagate_rotation_cb.setToolTip(
            "Checked: the rotation change is also added to every following frame,\n"
            "so the rest of the animation moves along with this edit.\n"
            "Unchecked: only this frame is posed, the following frames keep\n"
            "their own rotations.")
        anim_layout.addRow("", self.propagate_rotation_cb)

        # Animation info
        self.anim_info = QLabel("Rotation is linked to a bone and a frame")
        #self.anim_info.setStyleSheet("color:#aaa; font-size:10px;")
        anim_layout.addRow("", self.anim_info)

        # Multi-select comparison: an editable Rot X/Y/Z row per selected bone (this frame).
        self.rot_compare = self._new_compare_table(["Bone", "Rot X", "Rot Y", "Rot Z"])
        anim_layout.addRow(self.rot_compare)

        self.tabs.addTab(self.anim_tab, "Bones rotation per frame")

        # Bone Scale Tab (squash-and-stretch)
        self.scale_tab = QWidget()
        scale_layout = QFormLayout(self.scale_tab)

        self.scale_mode_cb = QCheckBox("Frame carries scale data (mode bit)")
        self.scale_mode_cb.toggled.connect(self._on_scale_mode_toggled)
        scale_layout.addRow("", self.scale_mode_cb)

        self.scale_spins = []
        self.scale_raws = []
        for axis_name in ("X", "Y", "Z"):
            axis_layout = QHBoxLayout()
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 32.0)
            # 1 raw scale unit = 1/1024 (ScaleType.SCALE_NEUTRAL_RAW = 1024), i.e. 1024 raw
            # values per 1.0 factor. 4 decimals (10^4 slots > 1024) are needed to reach every
            # raw; 3 decimals (1000 < 1024) left ~24 raw values per unit unreachable.
            spin.setSingleStep(0.01)
            spin.setDecimals(4)
            spin.setValue(1.0)
            spin.valueChanged.connect(self._on_scale_changed)
            raw_label = QLabel("raw: 1024")
            raw_label.setStyleSheet("color:#888; font-size:9px;")
            raw_label.setFixedWidth(70)
            axis_layout.addWidget(spin)
            axis_layout.addWidget(raw_label)
            axis_layout.addStretch(1)
            scale_layout.addRow(f"Scale {axis_name}:", axis_layout)
            self.scale_spins.append(spin)
            self.scale_raws.append(raw_label)

        self.scale_info = QLabel("Squash-and-stretch: per bone and frame, 1.0 = neutral.\n"
                                 "Hierarchical: children inherit their parent's scale.\n"
                                 "Only applied on frames with the mode bit set.")
        scale_layout.addRow("", self.scale_info)

        # Multi-select comparison: an editable Scale X/Y/Z row per selected bone (this frame).
        self.scale_compare = self._new_compare_table(["Bone", "Scale X", "Scale Y", "Scale Z"])
        scale_layout.addRow(self.scale_compare)

        self.tabs.addTab(self.scale_tab, "Bones scale per frame")

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


    def set_bone_data(self, bone_id: int, length: float, length_raw:int,parent_id: int,
                      rot_x: float, rot_y: float, rot_z: float,
                      rot_x_raw: int, rot_y_raw: int, rot_z_raw: int):
        """Update the editor with new bone data"""
        self._updating = True

        try:
            # Update static tab
            self.parent_spin.blockSignals(True)
            self.length_spin.blockSignals(True)


            self.parent_spin.setRange(-1, self.bone_spin.maximum())

            self.parent_spin.setValue(parent_id if parent_id != 0xFFFF else -1)
            self.length_spin.setValue(length)
            self.length_raw.setText(f"raw: {length_raw:d}")
            self.parent_spin.blockSignals(False)
            self.length_spin.blockSignals(False)

            # Update rotation tab
            self.anim_rotx.blockSignals(True)
            self.anim_roty.blockSignals(True)
            self.anim_rotz.blockSignals(True)

            self.anim_rotx.setValue(rot_x)
            self.anim_roty.setValue(rot_y)
            self.anim_rotz.setValue(rot_z)

            self.rot_x_raw.setText(f"raw: {rot_x_raw:d}")
            self.rot_y_raw.setText(f"raw: {rot_y_raw:d}")
            self.rot_z_raw.setText(f"raw: {rot_z_raw:d}")

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

    def set_frame_position(self, pos_x: float, pos_y: float, pos_z: float, pos_raw_x:int=0,  pos_raw_y:int=0,  pos_raw_z:int=0):
        # Update position tab
        self.frame_pos_x.blockSignals(True)
        self.frame_pos_y.blockSignals(True)
        self.frame_pos_z.blockSignals(True)

        self.frame_pos_x.setValue(pos_x)
        self.frame_pos_y.setValue(pos_y)
        self.frame_pos_z.setValue(pos_z)

        self.pos_x_raw.setText(f"raw: {pos_raw_x:d}")
        self.pos_y_raw.setText(f"raw: {pos_raw_y:d}")
        self.pos_z_raw.setText(f"raw: {pos_raw_z:d}")

        self.frame_pos_x.blockSignals(False)
        self.frame_pos_y.blockSignals(False)
        self.frame_pos_z.blockSignals(False)

    def set_bone_scale(self, scale_x: float, scale_y: float, scale_z: float,
                       raw_x: int, raw_y: int, raw_z: int, mode_bit_enabled: bool):
        """Update the scale tab with the selected bone/frame data"""
        self._updating = True
        try:
            self.scale_mode_cb.blockSignals(True)
            self.scale_mode_cb.setChecked(mode_bit_enabled)
            self.scale_mode_cb.blockSignals(False)

            for spin, raw_label, value, raw in zip(self.scale_spins, self.scale_raws,
                                                   (scale_x, scale_y, scale_z),
                                                   (raw_x, raw_y, raw_z)):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
                raw_label.setText(f"raw: {raw:d}")
        finally:
            self._updating = False

    # ── Multi-bone comparison (Ctrl+click selects several bones) ──────────
    def _new_compare_table(self, headers):
        """A hidden, per-bone editable table shown only when >1 bone is selected. Sized to just fit
        its content: columns shrink to their content (last one fills the leftover), and the height
        is fixed to the rows after each fill (no reserved empty area, no vertical scrollbar)."""
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        # Every column shrinks to its content (id + spin boxes) instead of stretching to fill the
        # row, and the table's width/height are pinned to that content after each fill - so the
        # table takes only the space it needs rather than the whole panel width.
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # cells hold spin widgets
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        table.setVisible(False)
        return table

    @staticmethod
    def _fit_table_height(table):
        """Fix the table's height to exactly its header + rows, so it takes only the space it needs."""
        height = table.horizontalHeader().height() + 2 * table.frameWidth()
        for row in range(table.rowCount()):
            height += table.rowHeight(row)
        table.setFixedHeight(height)

    @staticmethod
    def _fit_table_width(table):
        """Cap the table's width to its columns' content, so compact columns (Bone/Length/Parent...)
        don't leave a big empty area stretched across the panel."""
        width = table.verticalHeader().width() + 2 * table.frameWidth()
        for col in range(table.columnCount()):
            width += table.columnWidth(col)
        table.setMaximumWidth(width)

    @staticmethod
    def _bone_id_item(bone_id):
        item = QTableWidgetItem(str(bone_id))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)   # read-only label cell
        return item

    @staticmethod
    def _compare_dspin(lo, hi, decimals, step, value):
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def set_compare_bones(self, rows):
        """rows = list of per-bone dicts (in Ctrl-click order), each:
            {'bone', 'length', 'parent', 'rot':(x,y,z), 'scale':(x,y,z)}.
        With <=1 bone the tables stay hidden (the single-bone form above is used); with several,
        each tab shows an editable row per bone so they can be compared and edited together."""
        multi = len(rows) > 1
        for table in (self.static_compare, self.rot_compare, self.scale_compare):
            table.setVisible(multi)
        if not multi:
            self._compare_bone_ids = []
            return
        ids = [row['bone'] for row in rows]
        self._updating = True
        try:
            if ids != self._compare_bone_ids:
                # Bone set changed: rebuild the rows (creates the per-cell spin widgets).
                self._compare_bone_ids = ids
                self._fill_static_compare(rows)
                self._fill_axis_compare(self.rot_compare, rows, 'rot', -360, 360, 3, 0.1,
                                        self._emit_compare_rotation)
                self._fill_axis_compare(self.scale_compare, rows, 'scale', 0.01, 32.0, 4, 0.01,
                                        self._emit_compare_scale)
                for table in (self.static_compare, self.rot_compare, self.scale_compare):
                    table.resizeColumnsToContents()
                    self._fit_table_height(table)
                    self._fit_table_width(table)
            else:
                # Same bones (e.g. a frame step or a live drag): only refresh the values, so the
                # widgets are not torn down and rebuilt on every tick.
                for r, row in enumerate(rows):
                    self._set_cell_value(self.static_compare, r, 1, row['length'])
                    self._set_cell_value(self.static_compare, r, 2,
                                         row['parent'] if row['parent'] != 0xFFFF else -1)
                    for axis in range(3):
                        self._set_cell_value(self.rot_compare, r, 1 + axis, row['rot'][axis])
                        self._set_cell_value(self.scale_compare, r, 1 + axis, row['scale'][axis])
        finally:
            self._updating = False

    @staticmethod
    def _set_cell_value(table, row, col, value):
        widget = table.cellWidget(row, col)
        if widget is not None:
            widget.setValue(value)

    def _fill_static_compare(self, rows):
        table = self.static_compare
        table.setRowCount(len(rows))
        max_bone = self.bone_spin.maximum()
        for r, row in enumerate(rows):
            bone = row['bone']
            table.setItem(r, 0, self._bone_id_item(bone))
            length = self._compare_dspin(-100, 100, 3, 0.1, row['length'])
            length.valueChanged.connect(lambda v, b=bone: self._emit_compare_length(b, v))
            table.setCellWidget(r, 1, length)
            parent = QSpinBox()
            parent.setRange(-1, max_bone)
            parent.setValue(row['parent'] if row['parent'] != 0xFFFF else -1)
            parent.valueChanged.connect(lambda v, b=bone: self._emit_compare_parent(b, v))
            table.setCellWidget(r, 2, parent)

    def _fill_axis_compare(self, table, rows, key, lo, hi, decimals, step, emit_fn):
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            bone = row['bone']
            table.setItem(r, 0, self._bone_id_item(bone))
            for axis in range(3):
                spin = self._compare_dspin(lo, hi, decimals, step, row[key][axis])
                spin.valueChanged.connect(lambda v, t=table, rr=r, b=bone: emit_fn(t, rr, b))
                table.setCellWidget(r, 1 + axis, spin)

    def _emit_compare_length(self, bone, value):
        if not self._updating:
            self.bone_length_changed.emit(bone, value)

    def _emit_compare_parent(self, bone, value):
        if not self._updating:
            self.bone_parent_changed.emit(bone, value if value != -1 else 0xFFFF)

    def _emit_compare_rotation(self, table, row, bone):
        if self._updating:
            return
        rx = table.cellWidget(row, 1).value()
        ry = table.cellWidget(row, 2).value()
        rz = table.cellWidget(row, 3).value()
        self.animation_rotation_changed.emit(self.current_anim_id, self.current_frame, bone, rx, ry, rz)

    def _emit_compare_scale(self, table, row, bone):
        if self._updating:
            return
        # A non-neutral scale only shows with the frame's mode bit set - enable it like the form does.
        if not self.scale_mode_cb.isChecked():
            self.scale_mode_cb.blockSignals(True)
            self.scale_mode_cb.setChecked(True)
            self.scale_mode_cb.blockSignals(False)
            self.frame_scale_mode_changed.emit(self.current_anim_id, self.current_frame, True)
        sx = table.cellWidget(row, 1).value()
        sy = table.cellWidget(row, 2).value()
        sz = table.cellWidget(row, 3).value()
        self.animation_scale_changed.emit(self.current_anim_id, self.current_frame, bone, sx, sy, sz)

    def set_animation_info(self, anim_id: int, frame_id: int):
        """Update animation info display"""
        self.current_anim_id = anim_id
        self.current_frame = frame_id
        self.frame_info.setText(f"Anim: {anim_id}, Frame: {frame_id}")
        #self.anim_info.setText(f"Current Animation: {anim_id}, Frame: {frame_id}")
        #self.position_info.setText(f"Current Animation: {anim_id}, Frame: {frame_id}")
        self._update_tab_states()

    def set_bone_range(self, max_bone: int):
        """Set the maximum bone ID"""
        self.bone_count = max_bone + 1
        self.bone_spin.setRange(0, max_bone)

    def _update_tab_states(self):
        """Update which tabs are enabled based on data availability"""
        has_animation = (hasattr(self, 'current_anim_id') and self.current_anim_id >= 0)
        self.tabs.setTabEnabled(1, has_animation)  # Position tab
        self.tabs.setTabEnabled(2, has_animation)  # Rotation tab
        self.tabs.setTabEnabled(3, has_animation)  # Scale tab

    def _on_bone_selected(self, bone_id: int):
        """Handle bone selection"""
        if not self._updating:
            self.bone_selected.emit(bone_id)

    def _on_add_bone_clicked(self):
        self.add_bone_requested.emit(self.bone_spin.value())

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

    def _on_anim_position_changed(self):
        """Handle frame position change"""
        if not self._updating:
            px = self.frame_pos_x.value()
            py = self.frame_pos_y.value()
            pz = self.frame_pos_z.value()
            self.animation_position_changed.emit(
                self.current_anim_id, self.current_frame, px, py, pz
            )

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

    def _on_scale_changed(self):
        """Handle bone scale change"""
        if self._updating:
            return
        # A non-neutral scale is only visible when the frame's mode bit is set:
        # enable it automatically so the edit takes effect immediately
        if not self.scale_mode_cb.isChecked():
            self.scale_mode_cb.blockSignals(True)
            self.scale_mode_cb.setChecked(True)
            self.scale_mode_cb.blockSignals(False)
            self.frame_scale_mode_changed.emit(self.current_anim_id, self.current_frame, True)
        bone_id = self.bone_spin.value()
        sx = self.scale_spins[0].value()
        sy = self.scale_spins[1].value()
        sz = self.scale_spins[2].value()
        for raw_label, value in zip(self.scale_raws, (sx, sy, sz)):
            raw_label.setText(f"raw: {round(value * 1024):d}")
        self.animation_scale_changed.emit(
            self.current_anim_id, self.current_frame, bone_id, sx, sy, sz
        )

    def _on_scale_mode_toggled(self, checked: bool):
        """Handle the frame mode-bit checkbox"""
        if not self._updating:
            self.frame_scale_mode_changed.emit(self.current_anim_id, self.current_frame, checked)