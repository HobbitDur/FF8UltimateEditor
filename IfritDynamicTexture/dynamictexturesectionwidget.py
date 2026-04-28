from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QTabWidget, QLabel, QGroupBox, QSplitter, QComboBox, QHBoxLayout, QPushButton

from FF8GameData.monsterdata import DynamicTextureSection
from Ifrit.ifritmanager import IfritManager
from IfritDynamicTexture.dynamictextureentrywidget import DynamicTextureEntryWidget
from IfritDynamicTexture.texturepreviewwidget import TexturePreviewWidget


class DynamicTextureSectionWidget(QWidget):
    """Widget for managing DynamicTextureSection (dynamic texture animations)"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.current_texture_index = 0
        self.current_entry_index = 0
        self.selected_destinations = set()
        self.source_selected = True
        self.entry_indices = []  # Maps combo box index to actual entry index in dynamic_texture_data

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
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

        # Main splitter — no more tabs, just preview + editor side by side
        splitter = QSplitter(Qt.Orientation.Horizontal)

        preview_group = QGroupBox("Texture Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.texture_preview = TexturePreviewWidget()
        self.texture_preview.rectangleClicked.connect(self._on_rectangle_clicked)
        self.texture_preview.legendSelectionChanged.connect(self._on_legend_selection_changed)
        preview_layout.addWidget(self.texture_preview)
        splitter.addWidget(preview_group)

        editor_group = QGroupBox("Entry Editor")
        editor_layout = QVBoxLayout(editor_group)
        self.entry_editor = QWidget()
        self.entry_editor_layout = QVBoxLayout(self.entry_editor)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(self.entry_editor)
        editor_layout.addWidget(editor_scroll)
        splitter.addWidget(editor_group)

        splitter.setSizes([500, 400])
        layout.addWidget(splitter)

    def _on_legend_selection_changed(self, selected_dest_indices: set, source_selected: bool):
        self.selected_destinations = selected_dest_indices
        self.source_selected = source_selected  # ← store it
        self._update_rectangles()

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
        self.texture_preview.stop_animation()
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
        self.texture_preview.clear_rectangles()
        entries = self._get_entries_for_current_texture()
        if not (0 <= self.current_entry_index < len(entries)):
            return

        entry = entries[self.current_entry_index]
        self.texture_preview.add_rectangle(
            entry.source_uv.get_u_pixel(), entry.source_uv.get_v_pixel(),
            entry.sprite_width, entry.sprite_height,
            QColor(0, 0, 255, 255), 3, "Source",
            self.current_entry_index, -1
        )
        for dest_idx, dest_uv in enumerate(entry.dest_uv):
            self.texture_preview.add_rectangle(
                dest_uv.get_u_pixel(), dest_uv.get_v_pixel(),
                entry.sprite_width, entry.sprite_height,
                QColor(255, 0, 0, 255), 3, f"Dest {dest_idx}",
                self.current_entry_index, dest_idx
            )

        # Pass actual source_selected, not hardcoded True
        self.texture_preview.set_selection(self.selected_destinations, self.source_selected)

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

    def _on_destination_selection_changed(self):
        """Handle destination selection changes"""
        self._update_rectangles()

    def _show_empty_editor(self):
        for i in reversed(range(self.entry_editor_layout.count())):
            widget = self.entry_editor_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        label = QLabel("No animation entries for this texture. Click '+ Add Entry' to create one.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry_editor_layout.addWidget(label)

    def _on_entry_changed(self, index):
        self.texture_preview.stop_animation()
        self.current_entry_index = index
        entries = self._get_entries_for_current_texture()
        if entries and 0 <= self.current_entry_index < len(entries):
            entry = entries[self.current_entry_index]
            self.selected_destinations = set(range(len(entry.dest_uv)))
        self.source_selected = True  # ← reset on entry change
        self._load_current_entry_editor()
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
            destinations.append({'x': dest_uv.get_u_pixel(), 'y': dest_uv.get_v_pixel()})

        entry_widget.set_data(
            entry.source_uv.get_u_pixel(),
            entry.source_uv.get_v_pixel(),
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
        entry.source_uv.set_u_pixel(data['src_x'])
        entry.source_uv.set_v_pixel(data['src_y'])
        entry.sprite_width = data['src_width']
        entry.sprite_height = data['src_height']
        entry.texture_num = self.current_texture_index  # Ensure texture_num is set

        # Update destinations
        entry.dest_uv.clear()
        for dest in data['destinations']:
            from FF8GameData.monsterdata import UV
            uv = UV()
            uv.set_u_pixel(dest['x'])
            uv.set_v_pixel(dest['y'])
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
        new_entry.source_uv.set_u_pixel(0)
        new_entry.source_uv.set_v_pixel(0)
        new_entry.sprite_width = 32
        new_entry.sprite_height = 32
        new_entry.dest_uv = [UV()]
        new_entry.dest_uv[0].set_u_pixel(0)
        new_entry.dest_uv[0].set_v_pixel(0)
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
        self.texture_preview.rectangles.clear()

        # Clear the combo boxes
        self.texture_combo.clear()
        self.entry_combo.clear()

        # Reload data (this will repopulate the texture combo)
        self._load_data()

    def save_file(self):
        pass # Nothing to do, all is already updated automatically


