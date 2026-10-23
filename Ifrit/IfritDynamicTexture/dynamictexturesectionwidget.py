from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QLabel, QGroupBox, QSplitter, QComboBox, QHBoxLayout, QPushButton

from FF8GameData.monsterdata import DynamicTextureSection, UV, DynamicTextureData
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritDynamicTexture.dynamictextureentrywidget import DynamicTextureEntryWidget
from Ifrit.IfritDynamicTexture.texturepreviewwidget import TexturePreviewWidget


class DynamicTextureSectionWidget(QWidget):
    """Widget for managing DynamicTextureSection (section 4: the eye blink and other repainted
    texture spots). Each entry is a destination rectangle the model's polygons sample, and sprites
    the game copies onto it one at a time (VRAM-to-VRAM, QueueTextureAnimation 0x50C780)."""

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
        hint = QLabel("The game repaints the <b>destination</b> (green: what the model's polygons sample) "
                      "by copying one <b>sprite</b> onto it: sprite 0 at rest, the others in turn "
                      "(the eye blink: the closed eye every 15-59 ticks; the sequences' opcodes "
                      "80 / 9B / 9F / BD / BE). Entry numbers are the ids the sequences use.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        layout.addWidget(hint)

        # Main splitter — no more tabs, just preview + editor side by side
        splitter = QSplitter(Qt.Orientation.Horizontal)

        preview_group = QGroupBox("Texture Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.texture_preview = TexturePreviewWidget()
        self.texture_preview.rectangleClicked.connect(self._on_rectangle_clicked)
        self.texture_preview.legendSelectionChanged.connect(self._on_legend_selection_changed)
        self.texture_preview.spriteShown.connect(self._show_sprite_on_destination)
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
        layout.addWidget(splitter, 1)   # the preview + editor take the height, not the hint

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

    def _texture_count(self) -> int:
        """The file's textures, without the Static Texture grid's empty "Add New" slot (no image),
        which may or may not be appended yet depending on which tab loaded first."""
        textures = self.ifrit_manager.texture_data
        return sum(1 for texture in textures if getattr(texture, 'texture_image', None) is not None)

    def _load_data(self):
        self.texture_combo.clear()
        if self.ifrit_manager.texture_data:
            for i in range(self._texture_count()):
                self.texture_combo.addItem(f"Texture {i}")

            if self.texture_combo.count() > 0:
                # Open on the first texture that has entries (a character's eye blink is on its
                # second texture)
                dynamic_texture = self.ifrit_manager.enemy.dynamic_texture_data
                used = [entry.texture_num for entry in getattr(dynamic_texture, 'dynamic_texture_data', [])
                        if 0 <= entry.texture_num < self.texture_combo.count()]
                first = min(used) if used else 0
                # Block signals to prevent _on_texture_changed from being called
                self.texture_combo.blockSignals(True)
                self.texture_combo.setCurrentIndex(first)
                self.texture_combo.blockSignals(False)
                # Manually call after ensuring data is ready
                self._on_texture_changed(first)

    def _on_texture_changed(self, index):
        self.texture_preview.stop_animation()
        self.current_texture_index = index
        self._update_texture_preview()
        self._load_animation_entries()

    def _current_texture_image(self):
        if 0 <= self.current_texture_index < self._texture_count():
            texture_data = self.ifrit_manager.texture_data[self.current_texture_index]
            if texture_data and texture_data.texture_image:
                return texture_data.texture_image
        return None

    def _update_texture_preview(self):
        image = self._current_texture_image()
        if image is not None:
            self.texture_preview.set_texture(image)
            self._update_rectangles()

    def _show_sprite_on_destination(self, sprite_index: int):
        """Play: show the texture as the game has it after copying that sprite onto the
        destination (-1: as in the file)."""
        image = self._current_texture_image()
        entries = self._get_entries_for_current_texture()
        if image is None:
            return
        if sprite_index < 0 or not (0 <= self.current_entry_index < len(entries)):
            self.texture_preview.set_texture(image)
            return
        entry = entries[self.current_entry_index]
        if sprite_index >= len(entry.sprites):
            return
        sprite = entry.sprites[sprite_index]
        composed = QPixmap(image)
        painter = QPainter(composed)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(entry.destination.get_u_pixel(), entry.destination.get_v_pixel(), image,
                           sprite.get_u_pixel(), sprite.get_v_pixel(), entry.sprite_width, entry.sprite_height)
        painter.end()
        self.texture_preview.set_texture(composed)

    def _update_rectangles(self):
        self.texture_preview.clear_rectangles()
        entries = self._get_entries_for_current_texture()
        if not (0 <= self.current_entry_index < len(entries)):
            return

        entry = entries[self.current_entry_index]
        self.texture_preview.add_rectangle(
            entry.destination.get_u_pixel(), entry.destination.get_v_pixel(),
            entry.sprite_width, entry.sprite_height,
            QColor(60, 220, 120, 255), 3, "Destination",
            self.current_entry_index, -1
        )
        for frame_idx, sprite_uv in enumerate(entry.sprites):
            self.texture_preview.add_rectangle(
                sprite_uv.get_u_pixel(), sprite_uv.get_v_pixel(),
                entry.sprite_width, entry.sprite_height,
                QColor(255, 0, 0, 255), 3, "Sprite 0 (rest)" if frame_idx == 0 else f"Sprite {frame_idx}",
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
            self.entry_combo.addItem(f"Entry {entry.table_index}")
            self.entry_indices.append(i)

        if self.entry_combo.count() > 0:
            # Always reset to 0 when loading new entries, don't use existing current_entry_index
            self.current_entry_index = 0
            self.entry_combo.setCurrentIndex(0)

            # Initialize with all frames selected
            entry = entries[0]
            if len(entry.sprites) > 0:
                self.selected_frames = set(range(len(entry.sprites)))
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
        frame_count = len(entry.sprites)

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
            self.selected_frames = set(range(len(entry.sprites)))
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
        entry_widget = DynamicTextureEntryWidget(entry.table_index)
        entry_widget.set_data(
            entry.destination.get_u_pixel(),
            entry.destination.get_v_pixel(),
            entry.sprite_width,
            entry.sprite_height,
            [{'x': sprite.get_u_pixel(), 'y': sprite.get_v_pixel()} for sprite in entry.sprites],
            entry.anim_speed,
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
        entry.destination.set_u_pixel(data['destination_x'])
        entry.destination.set_v_pixel(data['destination_y'])
        entry.sprite_width = data['width']
        entry.sprite_height = data['height']
        entry.anim_speed = data['anim_speed']
        entry.texture_num = self.current_texture_index  # Ensure texture_num is set
        entry.sprites = []
        for sprite in data['sprites']:
            uv = UV(member_size=1, vram_size=True)
            uv.set_u_pixel(sprite['x'])
            uv.set_v_pixel(sprite['y'])
            entry.sprites.append(uv)

        # Select all sprites by default
        new_frame_count = len(entry.sprites)
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
        new_entry.sprite_width = 32
        new_entry.sprite_height = 32
        new_entry.sprites = [UV(member_size=1, vram_size=True), UV(member_size=1, vram_size=True)]
        new_entry.texture_num = self.current_texture_index
        new_entry.table_index = dynamic_texture.next_table_index()

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


