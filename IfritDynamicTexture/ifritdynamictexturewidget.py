from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSpinBox, QComboBox, QPushButton, QScrollArea, QGridLayout,
    QFrame, QSplitter, QListWidget, QListWidgetItem, QCheckBox, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush

from FF8GameData.monsterdata import DynamicTextureSection
from Ifrit.ifritmanager import IfritManager


class DestinationSelectorWidget(QGroupBox):
    """Widget for selecting which destinations to display for current entry"""

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Destinations to Show", parent)
        self.checkboxes = []

        layout = QVBoxLayout(self)
        self.dest_layout = QVBoxLayout()
        layout.addLayout(self.dest_layout)
        layout.addStretch()

    def update_destinations(self, dest_count: int, selected_indices: set):
        """Update the list of destination checkboxes"""
        # Clear existing
        for cb in self.checkboxes:
            cb.deleteLater()
        self.checkboxes.clear()

        # Clear layout
        for i in reversed(range(self.dest_layout.count())):
            item = self.dest_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        if dest_count == 0:
            label = QLabel("No destinations for this entry")
            self.dest_layout.addWidget(label)
            return

        # Add "Select All" checkbox
        self.select_all_cb = QCheckBox("Select All")
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        self.dest_layout.addWidget(self.select_all_cb)

        # Add destination checkboxes
        for i in range(dest_count):
            cb = QCheckBox(f"Destination {i}")
            cb.setChecked(i in selected_indices)
            cb.stateChanged.connect(self._on_selection_changed)
            self.checkboxes.append(cb)
            self.dest_layout.addWidget(cb)

        # Manually update select all state after creating checkboxes
        self.select_all_cb.blockSignals(True)
        all_checked = all(cb.isChecked() for cb in self.checkboxes) if self.checkboxes else False
        self.select_all_cb.setChecked(all_checked)
        self.select_all_cb.blockSignals(False)

    def _on_select_all(self, state):
        """Handle select all checkbox"""
        # Block signals while setting all checkboxes
        for cb in self.checkboxes:
            cb.blockSignals(True)
            cb.setChecked(state == Qt.CheckState.Checked.value)
            cb.blockSignals(False)
        self.selectionChanged.emit()

    def _on_selection_changed(self):
        """Handle individual checkbox changes"""
        # Temporarily block signals to avoid recursion
        self.select_all_cb.blockSignals(True)

        # Update select all state
        all_checked = all(cb.isChecked() for cb in self.checkboxes) if self.checkboxes else False
        self.select_all_cb.setChecked(all_checked)

        self.select_all_cb.blockSignals(False)
        self.selectionChanged.emit()

    def get_selected_indices(self) -> set:
        """Get set of selected destination indices"""
        return {i for i, cb in enumerate(self.checkboxes) if cb.isChecked()}


class DestinationWidget(QGroupBox):
    """Widget for editing a single destination UV"""

    dataChanged = pyqtSignal()
    removeRequested = pyqtSignal(int)

    def __init__(self, dest_index: int, parent=None):
        super().__init__(f"Destination {dest_index}", parent)
        self.dest_index = dest_index

        layout = QHBoxLayout(self)

        self.dst_x = QSpinBox()
        self.dst_x.setRange(0, 65535)
        self.dst_x.setToolTip("Destination X coordinate")
        self.dst_x.valueChanged.connect(self.dataChanged.emit)

        self.dst_y = QSpinBox()
        self.dst_y.setRange(0, 65535)
        self.dst_y.setToolTip("Destination Y coordinate")
        self.dst_y.valueChanged.connect(self.dataChanged.emit)

        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white; font-weight: bold;")
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self.dest_index))

        layout.addWidget(QLabel("X:"))
        layout.addWidget(self.dst_x)
        layout.addWidget(QLabel("Y:"))
        layout.addWidget(self.dst_y)
        layout.addWidget(self.remove_btn)

    def get_data(self) -> dict:
        return {
            'x': self.dst_x.value(),
            'y': self.dst_y.value()
        }

    def set_data(self, x: int, y: int):
        self.dst_x.setValue(x)
        self.dst_y.setValue(y)


class DynamicTextureEntryWidget(QGroupBox):
    """Widget for editing a single texture animation entry (source -> multiple targets)"""

    dataChanged = pyqtSignal()

    def __init__(self, entry_index: int, parent=None):
        super().__init__(f"Animation Entry {entry_index}", parent)
        self.entry_index = entry_index
        self.destination_widgets = []

        layout = QVBoxLayout(self)

        # Source texture coordinates
        source_group = QGroupBox("Source Sub-texture (will be copied)")
        source_layout = QGridLayout(source_group)

        self.src_x = QSpinBox()
        self.src_x.setRange(0, 65535)
        self.src_x.setToolTip("Source X coordinate")
        self.src_y = QSpinBox()
        self.src_y.setRange(0, 65535)
        self.src_y.setToolTip("Source Y coordinate")
        self.src_width = QSpinBox()
        self.src_width.setRange(1, 65535)
        self.src_width.setValue(32)
        self.src_height = QSpinBox()
        self.src_height.setRange(1, 65535)
        self.src_height.setValue(32)

        for spin in [self.src_x, self.src_y, self.src_width, self.src_height]:
            spin.valueChanged.connect(self.dataChanged.emit)

        source_layout.addWidget(QLabel("X:"), 0, 0)
        source_layout.addWidget(self.src_x, 0, 1)
        source_layout.addWidget(QLabel("Y:"), 0, 2)
        source_layout.addWidget(self.src_y, 0, 3)
        source_layout.addWidget(QLabel("Width:"), 1, 0)
        source_layout.addWidget(self.src_width, 1, 1)
        source_layout.addWidget(QLabel("Height:"), 1, 2)
        source_layout.addWidget(self.src_height, 1, 3)

        layout.addWidget(source_group)

        # Destinations section
        destinations_group = QGroupBox("Destination Sub-textures (where it will be copied)")
        destinations_layout = QVBoxLayout(destinations_group)

        # Header for destinations
        dest_header = QHBoxLayout()
        dest_header.addWidget(QLabel("Destinations:"))
        dest_header.addStretch()
        self.add_dest_btn = QPushButton("+ Add Destination")
        self.add_dest_btn.clicked.connect(self._add_destination)
        dest_header.addWidget(self.add_dest_btn)
        destinations_layout.addLayout(dest_header)

        # Scroll area for destinations
        self.dest_scroll = QScrollArea()
        self.dest_scroll.setWidgetResizable(True)
        self.dest_scroll.setMaximumHeight(200)

        self.dest_container = QWidget()
        self.dest_layout = QVBoxLayout(self.dest_container)
        self.dest_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.dest_scroll.setWidget(self.dest_container)
        destinations_layout.addWidget(self.dest_scroll)

        layout.addWidget(destinations_group)

        # Remove entry button
        self.remove_btn = QPushButton("Remove Entry")
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white;")
        layout.addWidget(self.remove_btn)

    def _add_destination(self):
        """Add a new destination widget"""
        dest_index = len(self.destination_widgets)
        dest_widget = DestinationWidget(dest_index)
        dest_widget.dataChanged.connect(self.dataChanged.emit)
        dest_widget.removeRequested.connect(self._remove_destination)
        self.destination_widgets.append(dest_widget)
        self.dest_layout.addWidget(dest_widget)
        self.dataChanged.emit()

    def _remove_destination(self, dest_index: int):
        """Remove a destination widget"""
        if 0 <= dest_index < len(self.destination_widgets):
            widget = self.destination_widgets.pop(dest_index)
            widget.deleteLater()
            # Renumber remaining widgets
            for i, w in enumerate(self.destination_widgets):
                w.dest_index = i
                w.setTitle(f"Destination {i}")
            self.dataChanged.emit()

    def get_data(self) -> dict:
        destinations = []
        for w in self.destination_widgets:
            destinations.append(w.get_data())

        return {
            'src_x': self.src_x.value(),
            'src_y': self.src_y.value(),
            'src_width': self.src_width.value(),
            'src_height': self.src_height.value(),
            'destinations': destinations
        }

    def set_data(self, src_x: int, src_y: int, src_width: int, src_height: int, destinations: list):
        self.src_x.setValue(src_x)
        self.src_y.setValue(src_y)
        self.src_width.setValue(src_width)
        self.src_height.setValue(src_height)

        # Clear existing destinations
        for w in self.destination_widgets:
            w.deleteLater()
        self.destination_widgets.clear()

        # Add new destinations
        for i, dest in enumerate(destinations):
            dest_widget = DestinationWidget(i)
            dest_widget.set_data(dest.get('x', 0), dest.get('y', 0))
            dest_widget.dataChanged.connect(self.dataChanged.emit)
            dest_widget.removeRequested.connect(self._remove_destination)
            self.destination_widgets.append(dest_widget)
            self.dest_layout.addWidget(dest_widget)


class TexturePreviewWidget(QLabel):
    """Widget that displays texture with source (blue) and target (red) rectangles"""

    rectangleClicked = pyqtSignal(int, int)  # entry_index, dest_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 300)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet("background-color: #2a2a2a;")

        self.original_pixmap = None
        self.scaled_pixmap = None
        self.rectangles = []  # (x, y, width, height, color, line_width, label, entry_idx, dest_idx)
        self.scale_factor = 1.0

    def set_texture(self, pixmap: QPixmap):
        """Set the texture image to display"""
        self.original_pixmap = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.update_display()

    def add_rectangle(self, x: int, y: int, width: int, height: int, color: QColor,
                      line_width: int = 2, label: str = "", entry_idx: int = -1, dest_idx: int = -1):
        """Add a rectangle to overlay on the texture"""
        self.rectangles.append((x, y, width, height, color, line_width, label, entry_idx, dest_idx))
        self.update_display()

    def clear_rectangles(self):
        """Clear all overlay rectangles"""
        self.rectangles.clear()
        self.update_display()

    def mousePressEvent(self, event):
        """Handle mouse click to select rectangles"""
        if not self.scaled_pixmap:
            return

        pos = event.position()
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            scaled_x = int(x * self.scale_factor)
            scaled_y = int(y * self.scale_factor)
            scaled_w = max(1, int(w * self.scale_factor))
            scaled_h = max(1, int(h * self.scale_factor))

            if scaled_x <= pos.x() <= scaled_x + scaled_w and scaled_y <= pos.y() <= scaled_y + scaled_h:
                self.rectangleClicked.emit(entry_idx, dest_idx)
                break

        super().mousePressEvent(event)

    def _draw_text_with_background(self, painter: QPainter, text: str, rect: QRect):
        """Draw text with a dark semi-transparent background for better visibility"""
        # Draw dark background with some transparency
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 3, 3)

        # Draw white text with black outline
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def update_display(self):
        """Update the displayed image with rectangles"""
        if self.original_pixmap is None or self.original_pixmap.isNull():
            self.setText("No texture loaded")
            return
        self.scale_factor = 1.0
        widget_size = self.size()
        if widget_size.width() <= 1 or widget_size.height() <= 1:
            widget_size = self.minimumSize()

        pix_size = self.original_pixmap.size()
        self.scale_factor = min(widget_size.width() / pix_size.width(),
                                widget_size.height() / pix_size.height())

        scaled_size = QSize(int(pix_size.width() * self.scale_factor),
                            int(pix_size.height() * self.scale_factor))
        self.scaled_pixmap = self.original_pixmap.scaled(scaled_size,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)

        result = self.scaled_pixmap.copy()
        painter = QPainter(result)

        # First pass: Draw ALL destination rectangles (red)
        dest_rects = []
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            if color == QColor(255, 0, 0, 255):  # Red destination
                scaled_x = int(x * self.scale_factor)
                scaled_y = int(y * self.scale_factor)
                scaled_w = max(1, int(w * self.scale_factor))
                scaled_h = max(1, int(h * self.scale_factor))
                dest_rects.append((scaled_x, scaled_y, scaled_w, scaled_h, color, line_width, label, entry_idx, dest_idx))

                pen = QPen(color, line_width)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                if label:
                    text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                    self._draw_text_with_background(painter, label, text_rect)

        # Second pass: Draw ALL source rectangles (blue) - on top of destinations
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            if color == QColor(0, 0, 255, 255):  # Blue source
                scaled_x = int(x * self.scale_factor)
                scaled_y = int(y * self.scale_factor)
                scaled_w = max(1, int(w * self.scale_factor))
                scaled_h = max(1, int(h * self.scale_factor))

                # Check if this source overlaps with any destination at the same position
                overlapping = False
                for dx, dy, dw, dh, dcolor, dline_width, dlabel, dentry_idx, ddest_idx in dest_rects:
                    if (scaled_x == dx and scaled_y == dy and scaled_w == dw and scaled_h == dh):
                        overlapping = True
                        break

                if overlapping:
                    # Draw mixed purple color for the rectangle
                    pen = QPen(QColor(0, 255, 0, 255), line_width)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                    painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                    if label:
                        # Get the destination label too
                        dest_label = ""
                        for dx, dy, dw, dh, dcolor, dline_width, dlabel, dentry_idx, ddest_idx in dest_rects:
                            if (scaled_x == dx and scaled_y == dy and scaled_w == dw and scaled_h == dh):
                                dest_label = dlabel
                                break
                        combined_label = f"{label}/{dest_label}" if dest_label else label
                        text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                        self._draw_text_with_background(painter, combined_label, text_rect)
                else:
                    # Draw normal blue solid line
                    pen = QPen(color, line_width)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                    painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                    if label:
                        text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                        self._draw_text_with_background(painter, label, text_rect)

        painter.end()
        self.setPixmap(result)

    def resizeEvent(self, event):
        self.update_display()
        super().resizeEvent(event)


class DynamicTextureSectionWidget(QWidget):
    """Widget for managing DynamicTextureSection (dynamic texture animations)"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.current_texture_index = 0
        self.current_entry_index = 0
        self.selected_destinations = set()
        self.entry_indices = []  # Maps combo box index to actual entry index in dynamic_texture_data

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Top controls
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("Texture:"))

        self.texture_combo = QComboBox()
        self.texture_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.texture_combo.currentIndexChanged.connect(self._on_texture_changed)
        controls_layout.addWidget(self.texture_combo)

        controls_layout.addWidget(QLabel("Animation Entry:"))

        self.entry_combo = QComboBox()
        self.entry_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.entry_combo.currentIndexChanged.connect(self._on_entry_changed)
        controls_layout.addWidget(self.entry_combo)

        controls_layout.addStretch()

        self.add_entry_btn = QPushButton("+ Add Entry")
        self.add_entry_btn.clicked.connect(self._add_entry)
        controls_layout.addWidget(self.add_entry_btn)

        layout.addLayout(controls_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Texture preview with rectangles
        preview_group = QGroupBox("Texture Preview")
        preview_layout = QVBoxLayout(preview_group)

        info_label = QLabel("Blue = Source | Red = Destinations (use checkboxes to show/hide)")
        info_label.setStyleSheet("color: #888; font-size: 12px;")
        preview_layout.addWidget(info_label)

        self.texture_preview = TexturePreviewWidget()
        self.texture_preview.rectangleClicked.connect(self._on_rectangle_clicked)
        preview_layout.addWidget(self.texture_preview)

        splitter.addWidget(preview_group)

        # Right panel with tabs
        right_panel = QTabWidget()

        # Tab 1: Current entry editor
        editor_group = QWidget()
        editor_layout = QVBoxLayout(editor_group)

        self.entry_editor = QWidget()
        self.entry_editor_layout = QVBoxLayout(self.entry_editor)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(self.entry_editor)

        editor_layout.addWidget(editor_scroll)
        right_panel.addTab(editor_group, "Editor")

        # Tab 2: Destination selector for current entry
        dest_selector_group = QWidget()
        dest_selector_layout = QVBoxLayout(dest_selector_group)

        self.dest_selector = DestinationSelectorWidget()
        self.dest_selector.selectionChanged.connect(self._on_destination_selection_changed)
        dest_selector_layout.addWidget(self.dest_selector)

        right_panel.addTab(dest_selector_group, "Destination Selector")

        splitter.addWidget(right_panel)
        splitter.setSizes([500, 400])

        layout.addWidget(splitter)

    def _get_entries_for_current_texture(self) -> list:
        """Get all animation entries that belong to the current texture"""
        dynamic_texture: DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data
        if not dynamic_texture or not dynamic_texture.dynamic_texture_data:
            return []

        return [entry for entry in dynamic_texture.dynamic_texture_data
                if entry.texture_num == self.current_texture_index]

    def _load_data(self):
        self.texture_combo.clear()
        if self.ifrit_manager.texture_data:
            for i in range(len(self.ifrit_manager.texture_data) - 1):
                self.texture_combo.addItem(f"Texture {i}")

            if self.texture_combo.count() > 0:
                # Block signals to prevent _on_texture_changed from being called
                self.texture_combo.blockSignals(True)
                self.texture_combo.setCurrentIndex(0)
                self.texture_combo.blockSignals(False)
                # Manually call after ensuring data is ready
                self._on_texture_changed(0)

    def _on_texture_changed(self, index):
        self.current_texture_index = index
        self._update_texture_preview()
        self._load_animation_entries()

    def _update_texture_preview(self):
        if 0 <= self.current_texture_index < len(self.ifrit_manager.texture_data) - 1:
            texture_data = self.ifrit_manager.texture_data[self.current_texture_index]
            if texture_data and texture_data.texture_image:
                self.texture_preview.set_texture(texture_data.texture_image)
                self._update_rectangles()

    def _update_rectangles(self):
        """Update the rectangle overlays on the texture preview - only for current entry"""
        self.texture_preview.clear_rectangles()

        entries = self._get_entries_for_current_texture()

        if self.current_entry_index >= len(entries):
            return

        entry = entries[self.current_entry_index]

        # Blue rectangle for source
        self.texture_preview.add_rectangle(
            entry.source_uv.get_u_raw(), entry.source_uv.get_v_raw(),
            entry.sprite_width, entry.sprite_height,
            QColor(0, 0, 255, 255),
            3,
            f"Source",
            self.current_entry_index, -1
        )

        # Red rectangles only for selected destinations of current entry
        for dest_idx, dest_uv in enumerate(entry.dest_uv):
            if dest_idx in self.selected_destinations:
                self.texture_preview.add_rectangle(
                    dest_uv.get_u_raw(), dest_uv.get_v_raw(),
                    entry.sprite_width, entry.sprite_height,
                    QColor(255, 0, 0, 255),
                    3,
                    f"Dest {dest_idx}",
                    self.current_entry_index, dest_idx
                )

    def _load_animation_entries(self):
        """Load only entries that belong to the current texture"""
        entries = self._get_entries_for_current_texture()

        self.entry_combo.blockSignals(True)  # ← add this
        self.entry_combo.clear()
        self.entry_combo.blockSignals(False)  # ← and this
        self.entry_indices.clear()

        for i, entry in enumerate(entries):
            self.entry_combo.addItem(f"Entry {i}")
            self.entry_indices.append(i)

        if self.entry_combo.count() > 0:
            # Always reset to 0 when loading new entries, don't use existing current_entry_index
            self.current_entry_index = 0
            self.entry_combo.setCurrentIndex(0)

            # Initialize with all destinations selected
            entry = entries[0]
            if len(entry.dest_uv) > 0:
                self.selected_destinations = set(range(len(entry.dest_uv)))
        else:
            self.current_entry_index = 0
            self.selected_destinations = set()
            self._show_empty_editor()

        self._update_destination_selector()
        self._update_rectangles()
        self._load_current_entry_editor()

    def _update_destination_selector(self):
        """Update the destination selector for current entry"""
        entries = self._get_entries_for_current_texture()

        if self.current_entry_index >= len(entries):
            return

        entry = entries[self.current_entry_index]
        dest_count = len(entry.dest_uv)
        self.dest_selector.update_destinations(dest_count, self.selected_destinations)

    def _on_destination_selection_changed(self):
        """Handle destination selection changes"""
        self.selected_destinations = self.dest_selector.get_selected_indices()
        self._update_rectangles()

    def _show_empty_editor(self):
        for i in reversed(range(self.entry_editor_layout.count())):
            widget = self.entry_editor_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        label = QLabel("No animation entries for this texture. Click '+ Add Entry' to create one.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry_editor_layout.addWidget(label)
        self.dest_selector.update_destinations(0, set())

    def _on_entry_changed(self, index):
        self.current_entry_index = index
        entries = self._get_entries_for_current_texture()

        if entries and self.current_entry_index < len(entries):
            # Select all destinations by default
            entry = entries[self.current_entry_index]
            if len(entry.dest_uv) > 0:
                self.selected_destinations = set(range(len(entry.dest_uv)))

        self._load_current_entry_editor()
        self._update_destination_selector()
        self._update_rectangles()

    def _load_current_entry_editor(self):
        entries = self._get_entries_for_current_texture()

        if self.current_entry_index >= len(entries):
            self._show_empty_editor()
            return

        for i in reversed(range(self.entry_editor_layout.count())):
            widget = self.entry_editor_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        entry = entries[self.current_entry_index]
        entry_widget = DynamicTextureEntryWidget(self.current_entry_index)

        # Build destinations list
        destinations = []
        for dest_uv in entry.dest_uv:
            destinations.append({'x': dest_uv.get_u_raw(), 'y': dest_uv.get_v_raw()})

        entry_widget.set_data(
            entry.source_uv.get_u_raw(),
            entry.source_uv.get_v_raw(),
            entry.sprite_width,
            entry.sprite_height,
            destinations
        )

        entry_widget.dataChanged.connect(lambda: self._on_entry_data_changed(entry_widget))
        entry_widget.remove_btn.clicked.connect(self._remove_current_entry)

        self.entry_editor_layout.addWidget(entry_widget)

    def _on_entry_data_changed(self, entry_widget: DynamicTextureEntryWidget):
        entries = self._get_entries_for_current_texture()

        if self.current_entry_index >= len(entries):
            return

        entry = entries[self.current_entry_index]
        data = entry_widget.get_data()

        # Update entry data
        entry.source_uv.set_u_pixel_raw(data['src_x'])
        entry.source_uv.set_v_pixel_raw(data['src_y'])
        entry.sprite_width = data['src_width']
        entry.sprite_height = data['src_height']
        entry.texture_num = self.current_texture_index  # Ensure texture_num is set

        # Update destinations
        entry.dest_uv.clear()
        for dest in data['destinations']:
            from FF8GameData.monsterdata import UV
            uv = UV()
            uv.set_u_pixel_raw(dest['x'])
            uv.set_v_pixel_raw(dest['y'])
            entry.dest_uv.append(uv)

        # Select all destinations by default
        new_dest_count = len(entry.dest_uv)
        if new_dest_count > 0:
            self.selected_destinations = set(range(new_dest_count))
        else:
            self.selected_destinations = set()

        self._update_destination_selector()
        self._update_rectangles()

    def _on_rectangle_clicked(self, entry_idx: int, dest_idx: int):
        if entry_idx >= 0 and dest_idx >= 0:
            if dest_idx in self.selected_destinations:
                self.selected_destinations.discard(dest_idx)
            else:
                self.selected_destinations.add(dest_idx)
            self._update_destination_selector()
            self._update_rectangles()

    def _add_entry(self):
        dynamic_texture: DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data

        from FF8GameData.monsterdata import DynamicTextureData, UV

        new_entry = DynamicTextureData()
        new_entry.source_uv = UV()
        new_entry.source_uv.set_u_pixel_raw(0)
        new_entry.source_uv.set_v_pixel_raw(0)
        new_entry.sprite_width = 32
        new_entry.sprite_height = 32
        new_entry.dest_uv = [UV()]
        new_entry.dest_uv[0].set_u_pixel_raw(0)
        new_entry.dest_uv[0].set_v_pixel_raw(0)
        new_entry.texture_num = self.current_texture_index  # Link to current texture

        dynamic_texture.dynamic_texture_data.append(new_entry)

        self._load_animation_entries()

        # Select the newly added entry
        entries = self._get_entries_for_current_texture()
        self.entry_combo.setCurrentIndex(len(entries) - 1)

    def _remove_current_entry(self):
        dynamic_texture: DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data
        entries = self._get_entries_for_current_texture()

        if self.current_entry_index < len(entries):
            # Find and remove the actual entry
            entry_to_remove = entries[self.current_entry_index]
            dynamic_texture.dynamic_texture_data.remove(entry_to_remove)

            self._load_animation_entries()

            entries = self._get_entries_for_current_texture()
            if self.current_entry_index >= len(entries):
                self.current_entry_index = max(0, len(entries) - 1)

            if self.entry_combo.count() > 0:
                self.entry_combo.setCurrentIndex(self.current_entry_index)
            else:
                self._show_empty_editor()

            self._update_destination_selector()
            self._update_rectangles()

    def load_file(self, file_path: str):
        # Reset state
        self.current_texture_index = 0
        self.current_entry_index = 0
        self.selected_destinations = set()
        self.entry_indices = []

        # Clear UI
        self.texture_preview.clear_rectangles()
        self.texture_preview.set_texture(QPixmap())
        self._show_empty_editor()
        self.dest_selector.update_destinations(0, set())
        self.texture_preview.rectangles.clear()

        # Clear the combo boxes
        self.texture_combo.clear()
        self.entry_combo.clear()

        # Reload data (this will repopulate the texture combo)
        self._load_data()

    def save_file(self):
        pass


class IfritDynamicTextureWidget(QWidget):
    """Main widget for texture animation management"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager

        layout = QVBoxLayout(self)
        self.anim_section = DynamicTextureSectionWidget(ifrit_manager)
        layout.addWidget(self.anim_section)

    def load_file(self, file_path: str):
        self.anim_section.load_file(file_path)

    def save_file(self):
        self.anim_section.save_file()