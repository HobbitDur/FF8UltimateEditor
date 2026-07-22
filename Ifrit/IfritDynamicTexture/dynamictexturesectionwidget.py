from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QLabel, QGroupBox, QSplitter, QComboBox, QHBoxLayout, QPushButton

from FF8GameData.monsterdata import DynamicTextureSection, UV, DynamicTextureData
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritDynamicTexture.dynamictextureentrywidget import DynamicTextureEntryWidget
from Ifrit.IfritDynamicTexture.texturepreviewwidget import TexturePreviewWidget


class DynamicTextureSectionWidget(QWidget):
    """Widget for managing DynamicTextureSection (dynamic texture animations)"""

    # Emitted on a real data edit (entry field changed / entry added / removed). All three already
    # mutate enemy.dynamic_texture_data in place, so the model is live; this just lets the host pane
    # dirty the file + record an undo step. Navigation (texture/entry/frame selection) does NOT fire.
    data_edited = pyqtSignal()

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self.current_texture_index = 0
        self.current_entry_index = 0
        self.selected_frames = set()
        self.anchor_selected = True
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

    def _on_legend_selection_changed(self, selected_frame_indices: set, anchor_selected: bool):
        self.selected_frames = selected_frame_indices
        self.anchor_selected = anchor_selected  # ← store it
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
            entry.anchor_uv.get_u_pixel(), entry.anchor_uv.get_v_pixel(),
            entry.sprite_width, entry.sprite_height,
            QColor(0, 0, 255, 255), 3, "Anchor",
            self.current_entry_index, -1
        )
        for frame_idx, frame_uv in enumerate(entry.frames):
            self.texture_preview.add_rectangle(
                frame_uv.get_u_pixel(), frame_uv.get_v_pixel(),
                entry.sprite_width, entry.sprite_height,
                QColor(255, 0, 0, 255), 3, f"Frame {frame_idx}",
                self.current_entry_index, frame_idx
            )

        # Pass actual anchor_selected, not hardcoded True
        self.texture_preview.set_selection(self.selected_frames, self.anchor_selected)

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

            # Initialize with all frames selected
            entry = entries[0]
            if len(entry.frames) > 0:
                self.selected_frames = set(range(len(entry.frames)))
        else:
            self.current_entry_index = 0
            self.selected_frames = set()
            self._show_empty_editor()

        self._update_frame_selector()
        self._update_rectangles()
        self._load_current_entry_editor()

    def _update_frame_selector(self):
        """Update the frame selector for current entry"""
        entries = self._get_entries_for_current_texture()

        if self.current_entry_index >= len(entries):
            return

        entry = entries[self.current_entry_index]
        frame_count = len(entry.frames)

    def _on_frame_selection_changed(self):
        """Handle frame selection changes"""
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
            self.selected_frames = set(range(len(entry.frames)))
        self.anchor_selected = True  # ← reset on entry change
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

        # Build frame list
        frames = []
        for frame_uv in entry.frames:
            frames.append({'x': frame_uv.get_u_pixel(), 'y': frame_uv.get_v_pixel()})

        entry_widget.set_data(
            entry.anchor_uv.get_u_pixel(),
            entry.anchor_uv.get_v_pixel(),
            entry.sprite_width,
            entry.sprite_height,
            frames
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
        entry.anchor_uv.set_u_pixel(data['anchor_x'])
        entry.anchor_uv.set_v_pixel(data['anchor_y'])
        entry.sprite_width = data['anchor_width']
        entry.sprite_height = data['anchor_height']
        entry.texture_num = self.current_texture_index  # Ensure texture_num is set

        # Update frames
        entry.frames.clear()
        for frame in data['frames']:
            from FF8GameData.monsterdata import UV
            uv = UV(member_size=1, vram_size=True)
            uv.set_u_pixel(frame['x'])
            uv.set_v_pixel(frame['y'])
            entry.frames.append(uv)
        entry.number_frames = len(entry.frames)  # ← THIS LINE is what's still missing

        # Select all frames by default
        new_frame_count = len(entry.frames)
        if new_frame_count > 0:
            self.selected_frames = set(range(new_frame_count))
        else:
            self.selected_frames = set()

        self._update_frame_selector()
        self._update_rectangles()
        self.data_edited.emit()   # entry data changed (live in enemy.dynamic_texture_data)

    def _on_rectangle_clicked(self, entry_idx: int, frame_idx: int):
        if entry_idx >= 0 and frame_idx >= 0:
            if frame_idx in self.selected_frames:
                self.selected_frames.discard(frame_idx)
            else:
                self.selected_frames.add(frame_idx)
            self._update_frame_selector()
            self._update_rectangles()

    def _add_entry(self):
        dynamic_texture: DynamicTextureSection = self.ifrit_manager.enemy.dynamic_texture_data
        new_entry = DynamicTextureData()
        new_entry.anchor_uv = UV(member_size=1, vram_size=True)
        new_entry.anchor_uv.set_u_pixel(0)
        new_entry.anchor_uv.set_v_pixel(0)
        new_entry.sprite_width = 32
        new_entry.sprite_height = 32
        frame = UV(member_size=1, vram_size=True)
        frame.set_u_pixel(0)
        frame.set_v_pixel(0)
        new_entry.frames = [frame]
        new_entry.number_frames = 1
        new_entry.texture_num = self.current_texture_index

        dynamic_texture.dynamic_texture_data.append(new_entry)

        self._load_animation_entries()

        # Select the newly added entry
        entries = self._get_entries_for_current_texture()
        self.entry_combo.setCurrentIndex(len(entries) - 1)
        self.data_edited.emit()   # entry added to enemy.dynamic_texture_data

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

            self._update_frame_selector()
            self._update_rectangles()
            self.data_edited.emit()   # entry removed from enemy.dynamic_texture_data

    def load_file(self, file_path: str):
        # Reset state
        self.current_texture_index = 0
        self.current_entry_index = 0
        self.selected_frames = set()
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


