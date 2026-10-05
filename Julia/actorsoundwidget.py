"""Edit the sound IDs used by FFNx's extended battle actor table."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QFileDialog, QMessageBox, QAbstractItemView, QSplitter,
                             QGroupBox)

from Common.filebinding import FileBinding
from Julia.actorsoundtable import ActorSoundTable, world_sound_to_archive_id, WORLD_SOUND_BASES
from Julia.juliamanager import CHARACTER_NAMES


class ActorSoundWidget(QWidget):
    play_requested = pyqtSignal(int)
    file_state_changed = pyqtSignal()

    def __init__(self, game_data, file_registry, audio_manager):
        super().__init__()
        self.model = ActorSoundTable(game_data.resource_folder_json)
        self.audio_manager = audio_manager
        self.path = None
        self.dirty = False
        self.binding = FileBinding("battle_actor_sounds.bin", file_registry,
                                   load_callback=self.load_file, save_callback=self.save_file,
                                   file_filter="Actor sound table (*.bin)", complementary=True)
        monsters = {monster["entity_id"]: monster["name"]
                    for monster in game_data.monster_data_json.get("monster", [])}
        self.actor_names = []
        for row in range(self.model.ROWS):
            if row < 16:
                name = CHARACTER_NAMES[row] if row < len(CHARACTER_NAMES) else f"Character {row}"
            else:
                name = f"c0m{row - 16:03d}"
                if row in monsters and monsters[row].lower() != name:
                    name += f" — {monsters[row]}"
            self.actor_names.append(name)

        layout = QVBoxLayout(self)
        explanation = QLabel("Side file: battle_actor_sounds.bin assigns seven world sound IDs per actor. "
                             "Audio comes from the main audio.fmt + audio.dat archive. "
                             "Save the BIN in your mod's direct/exe folder.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        actions = QHBoxLayout()
        self.new_button = QPushButton("New (original sounds)")
        self.new_button.setToolTip("Create a table with the original 160 actors' sounds and empty slots for added actors. Unsaved changes require confirmation.")
        self.new_button.clicked.connect(self.new_file)
        actions.addWidget(self.new_button)
        actions.addWidget(QLabel("Copy sounds from:"))
        self.copy_source = QComboBox()
        self.copy_source.setToolTip("Choose the actor whose seven sound IDs you want to reuse.")
        for row, name in enumerate(self.actor_names):
            self.copy_source.addItem(f"{row}: {name}", row)
        actions.addWidget(self.copy_source)
        self.copy_button = QPushButton("Copy to selected actor")
        self.copy_button.setToolTip("Copy all seven IDs from the source actor to the actor selected in the table. Save to write the BIN.")
        self.copy_button.clicked.connect(self.copy_selected)
        actions.addWidget(self.copy_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.table = QTableWidget(self.model.ROWS, 2 + self.model.SLOTS)
        self.table.setHorizontalHeaderLabels(["Actor ID", "Actor"] + [f"Slot {slot}" for slot in range(7)])
        self.table.setToolTip("Select a slot to see how its ID resolves. Double-click a slot to edit its decimal world sound ID; 0 means unused.")
        self.table.horizontalHeaderItem(0).setToolTip("Characters use rows 0-15. Monster c0mNNN uses actor row NNN + 16.")
        for column in range(2, 9):
            self.table.horizontalHeaderItem(column).setToolTip("One of seven sound references for this actor. Store a world sound ID, not a direct audio archive index.")
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 230)
        for column in range(2, 9):
            self.table.setColumnWidth(column, self.fontMetrics().horizontalAdvance("999999") + 20)
        self.table.cellChanged.connect(self._slot_changed)
        self.table.currentCellChanged.connect(lambda *_args: self.update_preview())
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.table)
        self.details_panel = self._build_details_panel()
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([760, 400])
        layout.addWidget(self.splitter, 1)
        preview_layout = QHBoxLayout()
        self.preview_label = QLabel()
        self.play_button = QPushButton("Play slot")
        self.play_button.setToolTip("Play the resolved sound from the loaded audio.fmt + audio.dat archive. Unused, empty or out-of-range entries cannot be played.")
        self.play_button.clicked.connect(self.play_selected_slot)
        preview_layout.addWidget(self.play_button)
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        layout.addLayout(preview_layout)
        self.status = QLabel()
        layout.addWidget(self.status)
        self._refresh()
        self.table.setCurrentCell(16, 2)
        self.binding.load_opened_file()

    def file_bindings(self):
        return [self.binding]

    def _build_details_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(340)
        layout = QVBoxLayout(panel)
        selected = QGroupBox("Selected slot: how its sound is found")
        selected_layout = QVBoxLayout(selected)
        self.selection_label = QLabel()
        self.selection_label.setWordWrap(True)
        selected_layout.addWidget(self.selection_label)
        self.detail_table = QTableWidget(5, 2)
        self.detail_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.detail_table.verticalHeader().hide()
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detail_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_table.setFixedHeight(self.detail_table.horizontalHeader().height()
                                         + 5 * self.detail_table.verticalHeader().defaultSectionSize() + 2)
        tooltips = {
            "world": "Unsigned 32-bit ID stored in the BIN. 0 marks an unused slot. Example: 400025 uses category 40 and offset 25.",
            "category": "Integer division by 10000 selects the game's sound group. Categories share the same audio archive.",
            "offset": "The remainder after division by 10000. Counts archive entries, not bytes. Example: 400025 has offset 25.",
            "base": "The game's hardcoded starting archive index for the category. Usually, final index = starting index + offset.",
            "archive": "The resolved entry number in Audio archive. Example: world ID 400025 resolves to 1230 + 25 = #1255.",
        }
        self.detail_values = {}
        for row, (key, title) in enumerate([("world", "Stored world ID"), ("category", "Category (ID // 10000)"),
                           ("offset", "Offset (ID % 10000)"), ("base", "Starting archive sound"),
                           ("archive", "Final archive sound")]):
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            self.detail_values[key] = label
            label.setToolTip(tooltips[key])
            title_label = QLabel(title)
            title_label.setToolTip(tooltips[key])
            title_label.setContentsMargins(6, 0, 6, 0)
            label.setContentsMargins(6, 0, 6, 0)
            self.detail_table.setCellWidget(row, 0, title_label)
            self.detail_table.setCellWidget(row, 1, label)
        selected_layout.addWidget(self.detail_table)
        layout.addWidget(selected)
        relation = QGroupBox("Hardcoded category → starting archive sound")
        relation_layout = QVBoxLayout(relation)
        self.category_table = QTableWidget(0, 2)
        self.category_table.setHorizontalHeaderLabels(["Category", "Starting archive sound"])
        self.category_table.verticalHeader().hide()
        self.category_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.category_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.category_rows = {}
        relationships = [(0, "0")] + [(category, str(base)) for category, base in WORLD_SOUND_BASES.items()]
        relationships += [(69, "Special rule"), ("Other", "0")]
        for row, (category, base) in enumerate(relationships):
            self.category_table.insertRow(row)
            self.category_table.setItem(row, 0, QTableWidgetItem(str(category)))
            self.category_table.setItem(row, 1, QTableWidgetItem(base))
            if category == 69:
                tooltip = "Category 69 has no single starting index: ID 690000 plays archive #2060; every other ID in this category resolves to ID - 688040. Example: 690001 plays #1961."
            elif category == "Other":
                tooltip = "Categories absent from this list use starting index 0, so their archive index equals the offset."
            elif category == 0:
                tooltip = "Category 0 uses the offset directly as its archive index. World ID 0 is an unused actor slot."
            else:
                tooltip = f"Category {category} starts at archive #{base}. Add the world ID's offset (ID % 10000) to find the final archive entry."
            for column in range(2):
                self.category_table.item(row, column).setToolTip(tooltip)
            self.category_rows[category] = row
        relation_layout.addWidget(self.category_table)
        explanation = QLabel("The game defines these starting indices; they are not calculated from the "
                             "category number. Offset counts sound entries, not bytes. All categories "
                             "resolve to the same audio archive.\n\n"
                             "Category 69: ID 690000 → #2060; other IDs → ID − 688040.")
        explanation.setWordWrap(True)
        relation_layout.addWidget(explanation)
        layout.addWidget(relation, 1)
        for label in panel.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        return panel

    def _update_details(self, row, column):
        if row < 0 or column < 2:
            self.selection_label.setText("Select a slot in the table.")
            for label in self.detail_values.values():
                label.setText("—")
            self.category_table.clearSelection()
            return
        world_id = self.model.rows[row][column - 2]
        category, offset = divmod(world_id, 10000)
        archive_id = world_sound_to_archive_id(world_id)
        self.selection_label.setText(f"{self.actor_names[row]} — slot {column - 2}")
        self.detail_values["world"].setText(str(world_id))
        self.detail_values["category"].setText(str(category))
        self.detail_values["offset"].setText(str(offset))
        self.detail_values["base"].setText("Special rule" if category == 69 else str(WORLD_SOUND_BASES.get(category, 0)))
        self.detail_values["archive"].setText(f"#{archive_id}" if world_id else "Unused slot")
        category_row = self.category_rows.get(category, self.category_rows["Other"])
        self.detail_values["base"].setToolTip(self.category_table.item(category_row, 1).toolTip())
        self.category_table.selectRow(category_row)
        self.category_table.scrollToItem(self.category_table.item(category_row, 0))

    def selected_archive_id(self):
        row, column = self.table.currentRow(), self.table.currentColumn()
        self._update_details(row, column)
        if row < 0 or column < 2:
            return None
        world_id = self.model.rows[row][column - 2]
        return world_sound_to_archive_id(world_id) if world_id else None

    def update_preview(self):
        archive_id = self.selected_archive_id()
        row, column = self.table.currentRow(), self.table.currentColumn()
        self.play_button.setEnabled(False)
        if row < 0 or column < 2:
            self.preview_label.setText("Select a sound slot to preview it.")
            return
        world_id = self.model.rows[row][column - 2]
        if archive_id is None:
            self.preview_label.setText("Unused slot (0).")
            return
        text = f"Slot {column - 2}: world ID {world_id} → archive sound #{archive_id}"
        if not self.audio_manager.sounds:
            text += " — Import audio.fmt + audio.dat to preview."
        elif archive_id >= len(self.audio_manager.sounds):
            text += " — This sound is outside the loaded archive."
        elif not self.audio_manager.sounds[archive_id].is_valid:
            text += " — This archive entry is empty."
        else:
            self.play_button.setEnabled(True)
        self.preview_label.setText(text)

    def play_selected_slot(self):
        self.update_preview()
        if self.play_button.isEnabled():
            self.play_requested.emit(self.selected_archive_id())

    def _refresh(self, actor_row=None):
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            for row in range(self.model.ROWS) if actor_row is None else (actor_row,):
                values = [str(row), self.actor_names[row]] + [str(value) for value in self.model.rows[row]]
                for column, value in enumerate(values):
                    item = self.table.item(row, column)
                    if item is None:
                        item = QTableWidgetItem(value)
                        if column < 2:
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.table.setItem(row, column, item)
                    elif item.text() != value:
                        item.setText(value)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self._update_status()
        self.update_preview()

    def _update_status(self):
        name = str(self.path) if self.path else "New battle_actor_sounds.bin"
        self.status.setText(f"{name} {'(unsaved changes)' if self.dirty else ''} — 216 actors, 6,048 bytes")
        self.file_state_changed.emit()

    def _slot_changed(self, row, column):
        if column < 2:
            return
        try:
            text = self.table.item(row, column).text().strip()
            if not text.isascii() or not text.isdecimal():
                raise ValueError("Enter a decimal sound ID between 0 and 4294967295.")
            self.model.set_slot(row, column - 2, int(text))
        except ValueError as error:
            self.table.blockSignals(True)
            self.table.item(row, column).setText(str(self.model.rows[row][column - 2]))
            self.table.blockSignals(False)
            QMessageBox.warning(self, "Julia", str(error))
            return
        self.dirty = True
        self._update_status()
        self.update_preview()

    def _can_discard(self):
        return not self.dirty or QMessageBox.question(
            self, "Julia", "Discard unsaved actor sound changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def new_file(self):
        if not self._can_discard():
            return
        self.model.reset()
        self.binding.registry.close_file(self.binding.file_name)
        self.path = None
        self.dirty = False
        self._refresh()

    def load_file(self, path):
        if not self._can_discard():
            return
        try:
            self.model.load(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Julia", f"Could not open the actor sound table:\n{error}")
            return
        self.path = Path(path)
        self.dirty = False
        self._refresh()

    def copy_selected(self):
        destination = self.table.currentRow()
        if destination < 0:
            return
        self.model.copy_actor(self.copy_source.currentData(), destination)
        self.dirty = True
        self._refresh(destination)

    def save_file(self):
        if self.path is None:
            self.save_as()
        else:
            self._save(self.path)

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save actor sound table",
                                             str(self.path or "battle_actor_sounds.bin"),
                                             "Actor sound table (*.bin)")
        if path:
            self._save(Path(path))

    def _save(self, path):
        try:
            self.model.save(path)
        except OSError as error:
            QMessageBox.critical(self, "Julia", f"Could not save the actor sound table:\n{error}")
            return
        self.path = path
        self.dirty = False
        self.binding.open_path(str(path))
        self._update_status()
