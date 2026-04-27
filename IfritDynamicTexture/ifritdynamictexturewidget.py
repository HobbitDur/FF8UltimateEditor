from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSpinBox, QComboBox, QPushButton, QScrollArea, QGridLayout,
    QFrame, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush

from FF8GameData.monsterdata import DynamicTextureSection
from Ifrit.ifritmanager import IfritManager


class DynamicTextureEntryWidget(QGroupBox):
    """Widget for editing a single texture animation entry (source -> target)"""

    dataChanged = pyqtSignal()

    def __init__(self, entry_index: int, parent=None):
        super().__init__(f"Animation Entry {entry_index}", parent)
        self.entry_index = entry_index

        layout = QVBoxLayout(self)

        # Source texture coordinates
        source_group = QGroupBox("Source Sub-texture (will be modified)")
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

        # Target texture coordinates
        target_group = QGroupBox("Target Sub-texture (will be used for drawing)")
        target_layout = QGridLayout(target_group)

        self.dst_x = QSpinBox()
        self.dst_x.setRange(0, 65535)
        self.dst_y = QSpinBox()
        self.dst_y.setRange(0, 65535)
        self.dst_width = QSpinBox()
        self.dst_width.setRange(1, 65535)
        self.dst_width.setValue(32)
        self.dst_height = QSpinBox()
        self.dst_height.setRange(1, 65535)
        self.dst_height.setValue(32)

        for spin in [self.dst_x, self.dst_y, self.dst_width, self.dst_height]:
            spin.valueChanged.connect(self.dataChanged.emit)

        target_layout.addWidget(QLabel("X:"), 0, 0)
        target_layout.addWidget(self.dst_x, 0, 1)
        target_layout.addWidget(QLabel("Y:"), 0, 2)
        target_layout.addWidget(self.dst_y, 0, 3)
        target_layout.addWidget(QLabel("Width:"), 1, 0)
        target_layout.addWidget(self.dst_width, 1, 1)
        target_layout.addWidget(QLabel("Height:"), 1, 2)
        target_layout.addWidget(self.dst_height, 1, 3)

        layout.addWidget(target_group)

        # Remove button
        self.remove_btn = QPushButton("Remove Entry")
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white;")
        layout.addWidget(self.remove_btn)

    def get_data(self) -> dict:
        return {
            'src_x': self.src_x.value(),
            'src_y': self.src_y.value(),
            'src_width': self.src_width.value(),
            'src_height': self.src_height.value(),
            'dst_x': self.dst_x.value(),
            'dst_y': self.dst_y.value(),
            'dst_width': self.dst_width.value(),
            'dst_height': self.dst_height.value(),
        }

    def set_data(self, data: dict):
        self.src_x.setValue(data.get('src_x', 0))
        self.src_y.setValue(data.get('src_y', 0))
        self.src_width.setValue(data.get('src_width', 32))
        self.src_height.setValue(data.get('src_height', 32))
        self.dst_x.setValue(data.get('dst_x', 0))
        self.dst_y.setValue(data.get('dst_y', 0))
        self.dst_width.setValue(data.get('dst_width', 32))
        self.dst_height.setValue(data.get('dst_height', 32))


class TexturePreviewWidget(QLabel):
    """Widget that displays texture with source (blue) and target (red) rectangles"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 300)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet("background-color: #2a2a2a;")

        self.original_pixmap = None
        self.scaled_pixmap = None
        self.rectangles = []  # (x, y, width, height, color)
        self.scale_factor = 1.0

    def set_texture(self, pixmap: QPixmap):
        """Set the texture image to display"""
        self.original_pixmap = pixmap
        self.update_display()

    def add_rectangle(self, x: int, y: int, width: int, height: int, color: QColor, label: str = ""):
        """Add a rectangle to overlay on the texture"""
        self.rectangles.append((x, y, width, height, color, label))
        self.update_display()

    def clear_rectangles(self):
        """Clear all overlay rectangles"""
        self.rectangles.clear()
        self.update_display()

    def update_display(self):
        """Update the displayed image with rectangles"""
        if self.original_pixmap is None or self.original_pixmap.isNull():
            self.setText("No texture loaded")
            return

        # Calculate scale factor to fit in widget
        widget_size = self.size()
        if widget_size.width() <= 1 or widget_size.height() <= 1:
            widget_size = self.minimumSize()

        pix_size = self.original_pixmap.size()
        self.scale_factor = min(widget_size.width() / pix_size.width(),
                                widget_size.height() / pix_size.height())

        # Scale the pixmap
        scaled_size = QSize(int(pix_size.width() * self.scale_factor),
                            int(pix_size.height() * self.scale_factor))
        self.scaled_pixmap = self.original_pixmap.scaled(scaled_size,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)

        # Create a copy to draw on
        result = self.scaled_pixmap.copy()
        painter = QPainter(result)

        for x, y, w, h, color, label in self.rectangles:
            # Scale coordinates
            scaled_x = int(x * self.scale_factor)
            scaled_y = int(y * self.scale_factor)
            scaled_w = max(1, int(w * self.scale_factor))
            scaled_h = max(1, int(h * self.scale_factor))

            # Draw rectangle
            pen = QPen(color, 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.GlobalColor.transparent))
            painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)

            # Draw label
            if label:
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.setBrush(QBrush(color))
                painter.drawText(scaled_x + 2, scaled_y + 15, label)

        painter.end()
        self.setPixmap(result)

    def resizeEvent(self, event):
        self.update_display()
        super().resizeEvent(event)


class DynamicTextureSectionWidget(QWidget):
    """Widget for managing TextureAnimSection (dynamic texture animations)"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.current_texture_index = 0
        self.current_entry_index = -1

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

        controls_layout.addStretch()

        self.add_entry_btn = QPushButton("+ Add Animation Entry")
        self.add_entry_btn.clicked.connect(self._add_entry)
        controls_layout.addWidget(self.add_entry_btn)

        layout.addLayout(controls_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Texture preview with rectangles
        preview_group = QGroupBox("Texture Preview")
        preview_layout = QVBoxLayout(preview_group)

        info_label = QLabel("Blue = Source (The drawing to copy) | Red = Target (Where it will be copied)")
        info_label.setStyleSheet("color: #888; font-size: 16px;")
        preview_layout.addWidget(info_label)

        self.texture_preview = TexturePreviewWidget()
        preview_layout.addWidget(self.texture_preview)

        splitter.addWidget(preview_group)

        # Right: Animation entries list
        entries_group = QGroupBox("Animation Entries")
        entries_layout = QVBoxLayout(entries_group)

        self.entries_scroll = QScrollArea()
        self.entries_scroll.setWidgetResizable(True)
        self.entries_scroll.setMinimumWidth(350)

        self.entries_container = QWidget()
        self.entries_layout_grid = QGridLayout(self.entries_container)
        self.entries_layout_grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.entries_scroll.setWidget(self.entries_container)
        entries_layout.addWidget(self.entries_scroll)

        splitter.addWidget(entries_group)
        splitter.setSizes([500, 400])

        layout.addWidget(splitter)

    def _load_data(self):
        print("_load_data")
        self.texture_combo.clear()
        for i in range(len(self.ifrit_manager.texture_data)-1): # Not using the green default one
            self.texture_combo.addItem(f"Texture {i}")

        if self.texture_combo.count() > 0:
            self.texture_combo.setCurrentIndex(0)
            self._on_texture_changed(0)

    def _on_texture_changed(self, index):
        print("_on_texture_changed")
        self.current_texture_index = index
        self._update_texture_preview()
        self._load_animation_entries()

    def _update_texture_preview(self):
        """Update the texture preview with current texture"""
        print("_update_texture_preview")
        if 0 <= self.current_texture_index < len(self.ifrit_manager.texture_data)-1:
            texture_data = self.ifrit_manager.texture_data[self.current_texture_index]
            if texture_data and texture_data.texture_image:
                self.texture_preview.set_texture(texture_data.texture_image)
                self._update_rectangles()

    def _update_rectangles(self):
        print("_update_rectangles")
        """Update the rectangle overlays on the texture preview"""
        self.texture_preview.clear_rectangles()

        dynamic_texture = self.ifrit_manager.enemy.dynamic_texture_data
        entry  = dynamic_texture.anim_data[0]
        # Blue rectangle for source (sub-texture that will be modified)
        self.texture_preview.add_rectangle(
            entry.source_uv.u,  entry.source_uv.v,
            entry.sprite_width, entry.sprite_height,
            QColor(0, 0, 255, 255),  # Blue
            f""
        )

        # Red rectangle for target (where it will be used)
        self.texture_preview.add_rectangle(
            entry.dest_uv[0].u, entry.dest_uv[0].v,
            entry.sprite_width, entry.sprite_height,
            QColor(255, 0, 0, 255),  # Red
            f""
        )

    def _load_animation_entries(self):
        """Load animation entries from TextureAnimSection"""
        # Clear existing widgets
        for i in reversed(range(self.entries_layout_grid.count())):
            widget = self.entries_layout_grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        dynamic_texture:DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data

        # Create widgets for each animation entry
        for i, entry in enumerate(dynamic_texture.anim_data):
            entry_widget = DynamicTextureEntryWidget(i)
            entry_widget.remove_btn.clicked.connect(lambda checked, idx=i: self._remove_entry(idx))
            entry_widget.dataChanged.connect(lambda idx=i: self._on_entry_changed(idx))


            # Set data from TextureAnimData object
            entry_widget.src_x.setValue(int(entry.source_uv.u))
            entry_widget.src_y.setValue(int(entry.source_uv.v))
            entry_widget.src_width.setValue(entry.sprite_width)
            entry_widget.src_height.setValue(entry.sprite_height)
            entry_widget.dst_x.setValue(int(entry.dest_uv[0].u))
            entry_widget.dst_y.setValue(int(entry.dest_uv[0].v))
            entry_widget.dst_width.setValue(entry.sprite_width)
            entry_widget.dst_height.setValue(entry.sprite_height)

            self.entries_layout_grid.addWidget(entry_widget, i // 2, i % 2)

        self._update_rectangles()

    def _on_entry_changed(self, entry_index: int):
        """Handle changes to an animation entry"""
        # Get the widget
        widget = self.entries_layout_grid.itemAt(entry_index)
        if not widget:
            return

        entry_widget = widget.widget()
        if not isinstance(entry_widget, DynamicTextureEntryWidget):
            return

        # Update the data in TextureAnimSection
        dynamic_texture:DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data
        if dynamic_texture and entry_index < len(dynamic_texture.anim_data):
            entry = dynamic_texture.anim_data[entry_index]
            entry.source_uv.u = entry_widget.src_x.value()
            entry.source_uv.v = entry_widget.src_y.value()
            entry.sprite_width = entry_widget.src_width.value()
            entry.sprite_height = entry_widget.src_height.value()
            entry.dest_uv[0].u = entry_widget.dst_x.value()
            entry.dest_uv[0].v = entry_widget.dst_y.value()
            entry.sprite_width = entry_widget.dst_width.value()
            entry.sprite_height = entry_widget.dst_height.value()

        self._update_rectangles()

    def _add_entry(self):
        """Add a new animation entry"""
        texture_anim = self.ifrit_manager.enemy.dynamic_texture_data
        self._load_animation_entries()

    def _remove_entry(self, entry_index: int):
        """Remove an animation entry"""
        self._load_animation_entries()

    def load_file(self, file_path: str):
        """Load animation data from file"""
        self._load_data()

    def save_file(self):
        """Save animation data (handled by ifrit_manager)"""
        # Data is already saved to ifrit_manager.enemy.texture_anim_data
        # The parent widget will call ifrit_manager.save_file()
        pass


class IfritDynamicTextureWidget(QWidget):
    """Main widget for texture animation management"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager

        layout = QVBoxLayout(self)

        # Main animation section
        self.anim_section = DynamicTextureSectionWidget(ifrit_manager)
        layout.addWidget(self.anim_section)

    def load_file(self, file_path: str):
        """Load animation data from file"""
        self.anim_section.load_file(file_path)

    def save_file(self):
        """Save animation data"""
        self.anim_section.save_file()