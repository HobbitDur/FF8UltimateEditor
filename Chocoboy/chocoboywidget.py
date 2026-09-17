import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QListWidget, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
                             QPushButton, QSplitter, QTabWidget, QGroupBox, QSpinBox, QMessageBox,
                             QAbstractItemView)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Chocoboy.chocoboymanager import (ChocoboyManager, SCRIPT_SECTION_LIST, TEXT_SECTION_LIST,
                                      SECTION_NAME, SECTION_DESCRIPTION)
from Chocoboy.wmsetscript import (OPCODE_LIST, Instruction, to_pseudo_code,
                                  NO_PARAM, WORD, GOTO_CODE)


class ChocoboyWidget(QWidget):
    """wmsetxx.obj editor: the world-map event scripts and the dialogs they open.

    The world map runs its own little bytecode - one 4-byte instruction at a time, as an
    IF / THEN / ELSE machine - and that is where every world-map side quest lives: the UFO, the
    Obel Lake rock, Chocobo forests, the train stations, boarding the Ragnarok. Sections 7, 9,
    11 and 36 hold the scripts; sections 13 and 31 hold the text they show.

    Named after Chocoboy, the boy who turns up in every Chocobo Forest on the world map.
    """

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_sysfnt_data()  # the character table the world-map texts are encoded in
        self.game_data.load_item_data()  # to name the item an ADD_ITEM hands out
        self.manager = ChocoboyManager(self.game_data)

        self.setWindowTitle("Chocoboy")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # Same registry name as the Draw editor, which reads the draw-point section of the very
        # same file: opening it in one tool opens it in the other.
        self.wmset_binding = FileBinding("wmsetxx.obj", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file,
                                         file_filter="wmset*.obj;;*.obj")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_script_tab(), "Scripts")
        self.tabs.addTab(self._build_text_tab(), "Texts")
        self.tabs.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.wmset_binding.load_opened_file()  # another tool may have opened a wmset already

    def file_bindings(self):
        """The one file the shared header toolbar drives for this tool."""
        return [self.wmset_binding]

    def _mark_dirty(self):
        """Tell the shared header there are unsaved edits (it puts the * in the window title).

        The automatic tracker only knows the widgets that exist when a file loads, and this tool
        rebuilds its instruction rows every time another script is picked, so it says so itself."""
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    # -- building ---------------------------------------------------------------------------

    def _build_script_tab(self):
        self.script_section_combo = QComboBox()
        for index in SCRIPT_SECTION_LIST:
            self.script_section_combo.addItem(f"Section {index} - {SECTION_NAME[index]}", index)
        self.script_section_combo.currentIndexChanged.connect(self._on_script_section_changed)

        self.script_section_note = QLabel()
        self.script_section_note.setWordWrap(True)
        self.script_section_note.setStyleSheet("color: gray;")

        self.script_list = QListWidget()
        self.script_list.currentRowChanged.connect(self._on_script_changed)

        script_group = QGroupBox("Scripts")
        script_group_layout = QVBoxLayout()
        script_group_layout.addWidget(self.script_section_combo)
        script_group_layout.addWidget(self.script_section_note)
        script_group_layout.addWidget(self.script_list)
        script_group.setLayout(script_group_layout)
        script_group.setFixedWidth(330)

        self.instruction_table = QTableWidget()
        self.instruction_table.setColumnCount(5)
        self.instruction_table.setHorizontalHeaderLabels(
            ["Offset", "Instruction", "Parameter", "Parameter 2", "What it does"])
        self.instruction_table.verticalHeader().setVisible(False)
        self.instruction_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.instruction_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch)

        self.add_button = QPushButton("Add instruction")
        self.add_button.setToolTip("Insert a copy of the selected line just above it, ready to be "
                                   "changed. Every script entry point and every GOTO after it "
                                   "moves with the change.")
        self.add_button.clicked.connect(self._on_add_instruction)
        self.remove_button = QPushButton("Remove instruction")
        self.remove_button.setToolTip("Delete the selected line. Every script entry point and "
                                      "every GOTO after it moves with the change.")
        self.remove_button.clicked.connect(self._on_remove_instruction)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)

        table_panel = QWidget()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addLayout(button_row)
        table_layout.addWidget(self.instruction_table)
        table_panel.setLayout(table_layout)

        self.pseudo_code_view = QPlainTextEdit()
        self.pseudo_code_view.setReadOnly(True)
        self.pseudo_code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        pseudo_code_group = QGroupBox("The script as the game walks it")
        pseudo_code_layout = QVBoxLayout()
        pseudo_code_layout.addWidget(self.pseudo_code_view)
        pseudo_code_group.setLayout(pseudo_code_layout)

        editor_splitter = QSplitter(Qt.Orientation.Vertical)
        editor_splitter.addWidget(table_panel)
        editor_splitter.addWidget(pseudo_code_group)
        editor_splitter.setStretchFactor(0, 3)
        editor_splitter.setStretchFactor(1, 2)

        tab = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(script_group)
        layout.addWidget(editor_splitter, 1)
        tab.setLayout(layout)
        return tab

    def _build_text_tab(self):
        self.text_section_combo = QComboBox()
        for index in TEXT_SECTION_LIST:
            self.text_section_combo.addItem(f"Section {index} - {SECTION_NAME[index]}", index)
        self.text_section_combo.currentIndexChanged.connect(self._on_text_section_changed)

        self.text_list = QListWidget()
        self.text_list.currentRowChanged.connect(self._on_text_changed)

        text_group = QGroupBox("Texts")
        text_group_layout = QVBoxLayout()
        text_group_layout.addWidget(self.text_section_combo)
        text_group_layout.addWidget(self.text_list)
        text_group.setLayout(text_group_layout)
        text_group.setFixedWidth(330)

        self.text_edit = QPlainTextEdit()
        self.text_edit.textChanged.connect(self._on_text_edited)
        text_edit_group = QGroupBox("Text")
        text_edit_layout = QVBoxLayout()
        text_edit_layout.addWidget(self.text_edit)
        text_edit_group.setLayout(text_edit_layout)

        self.text_users_view = QPlainTextEdit()
        self.text_users_view.setReadOnly(True)
        users_group = QGroupBox("Opened by")
        users_layout = QVBoxLayout()
        users_layout.addWidget(self.text_users_view)
        users_group.setLayout(users_layout)

        text_splitter = QSplitter(Qt.Orientation.Vertical)
        text_splitter.addWidget(text_edit_group)
        text_splitter.addWidget(users_group)
        text_splitter.setStretchFactor(0, 3)
        text_splitter.setStretchFactor(1, 1)

        tab = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(text_group)
        layout.addWidget(text_splitter, 1)
        tab.setLayout(layout)
        return tab

    # -- file -------------------------------------------------------------------------------

    def load_file(self, file_path):
        try:
            self.manager.load_file(file_path)
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Chocoboy - Failed to read the wmset", str(error))
            return
        self.tabs.setEnabled(True)
        self._reload_script_section()
        self._reload_text_section()

    def save_file(self):
        if self.manager.is_loaded:
            self.manager.save_file()

    # -- scripts ----------------------------------------------------------------------------

    @property
    def current_script_section(self):
        index = self.script_section_combo.currentData()
        return self.manager.script_sections.get(index)

    def _on_script_section_changed(self):
        self._reload_script_section()

    def _reload_script_section(self):
        section = self.current_script_section
        section_index = self.script_section_combo.currentData()
        self.script_section_note.setText(SECTION_DESCRIPTION.get(section_index, ""))
        with QSignalBlocker(self.script_list):
            self.script_list.clear()
            if section is not None:
                for entry, offset in enumerate(section.entry_offsets):
                    self.script_list.addItem(f"Script #{entry}  (offset {offset})")
        if self.script_list.count():
            self.script_list.setCurrentRow(0)
        else:
            self._reload_instructions()

    def _on_script_changed(self):
        self._reload_instructions()

    def _reload_instructions(self):
        section = self.current_script_section
        entry = self.script_list.currentRow()
        self.instruction_table.setRowCount(0)
        if section is None or entry < 0:
            self.pseudo_code_view.setPlainText("")
            return
        start, end = section.script_range(entry)
        self.instruction_table.setRowCount(end - start)
        for row, index in enumerate(range(start, end)):
            self._fill_instruction_row(row, section, index)
        self.instruction_table.resizeColumnsToContents()
        self.instruction_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch)
        self._refresh_pseudo_code()

    def _fill_instruction_row(self, row, section, index):
        """One line of the table: where it is, what it is, and its parameters as the game reads them."""
        instruction = section.instructions[index]
        opcode = instruction.opcode

        offset_item = QTableWidgetItem(str(section.instruction_offset(index)))
        offset_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        offset_item.setData(Qt.ItemDataRole.UserRole, index)  # which instruction of the stream
        self.instruction_table.setItem(row, 0, offset_item)

        opcode_combo = QComboBox()
        for known in OPCODE_LIST:
            opcode_combo.addItem(known.name, known.code)
        if opcode is None:  # bytes this tool does not know: keep them, show them as they are
            opcode_combo.addItem(instruction.name, instruction.code)
        opcode_combo.setCurrentIndex(opcode_combo.findData(instruction.code))
        opcode_combo.activated.connect(
            lambda _index, r=row, combo=opcode_combo: self._on_opcode_changed(r, combo))
        self.instruction_table.setCellWidget(row, 1, opcode_combo)

        uses_word = opcode is not None and opcode.params == WORD
        no_parameter = opcode is not None and opcode.params == NO_PARAM
        first_spinbox = QSpinBox()
        first_spinbox.setRange(0, 65535 if uses_word else 255)
        first_spinbox.setValue(instruction.word if uses_word else instruction.param1)
        first_spinbox.setEnabled(not no_parameter)
        first_spinbox.valueChanged.connect(
            lambda value, r=row: self._on_parameter_changed(r, 0, value))
        self.instruction_table.setCellWidget(row, 2, first_spinbox)

        second_spinbox = QSpinBox()
        second_spinbox.setRange(0, 255)
        second_spinbox.setValue(instruction.param2)
        second_spinbox.setEnabled(not uses_word and not no_parameter)
        second_spinbox.valueChanged.connect(
            lambda value, r=row: self._on_parameter_changed(r, 1, value))
        self.instruction_table.setCellWidget(row, 3, second_spinbox)

        description_item = QTableWidgetItem(self._describe(section, instruction))
        description_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.instruction_table.setItem(row, 4, description_item)

    def _describe(self, section, instruction):
        """The plain-English line shown next to an instruction, with what its parameters point at."""
        opcode = instruction.opcode
        if opcode is None:
            return "Not an instruction this tool knows. Kept as it is."
        description = opcode.description
        if instruction.code in (0xFF1F, 0xFF23):
            text = self.manager.dialog_lookup().get(instruction.param2)
            if text is not None:
                description += f'  ->  "{text}"'
        elif instruction.code == 0xFF37:
            description += f"  ->  {self._item_name(instruction.param1)}"
        elif instruction.code == GOTO_CODE and section.index_at_offset(instruction.word) is None:
            description += "  ->  WARNING: that offset is not the start of an instruction."
        return description

    def _item_name(self, item_id):
        items = getattr(self.game_data, "item_data_json", {}).get("items", [])
        if 0 <= item_id < len(items):
            return items[item_id]["name"]
        return f"item {item_id}"

    def _instruction_index(self, row):
        """The stream index the table row stands for (rows show one script, the stream is shared)."""
        item = self.instruction_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_opcode_changed(self, row, combo):
        section = self.current_script_section
        index = self._instruction_index(row)
        if section is None or index is None:
            return
        section.instructions[index].code = combo.currentData()
        self._mark_dirty()
        self._reload_instructions()  # the new opcode may read its parameters differently

    def _on_parameter_changed(self, row, parameter, value):
        section = self.current_script_section
        index = self._instruction_index(row)
        if section is None or index is None:
            return
        instruction = section.instructions[index]
        opcode = instruction.opcode
        if parameter == 0 and opcode is not None and opcode.params == WORD:
            instruction.set_word(value)
        elif parameter == 0:
            instruction.param1 = value
        else:
            instruction.param2 = value
        description_item = self.instruction_table.item(row, 4)
        if description_item is not None:
            description_item.setText(self._describe(section, instruction))
        self._mark_dirty()
        self._refresh_pseudo_code()

    def _on_add_instruction(self):
        section = self.current_script_section
        row = self.instruction_table.currentRow()
        index = self._instruction_index(row if row >= 0 else 0)
        if section is None or index is None:
            return
        copied = section.instructions[index]
        section.insert_instruction(index, Instruction(copied.code, copied.param1, copied.param2))
        self._mark_dirty()
        self._reload_script_section_keeping_selection()

    def _on_remove_instruction(self):
        section = self.current_script_section
        index = self._instruction_index(self.instruction_table.currentRow())
        if section is None or index is None:
            return
        section.delete_instruction(index)
        self._mark_dirty()
        self._reload_script_section_keeping_selection()

    def _reload_script_section_keeping_selection(self):
        """Redraw after an edit that moved offsets: every script's header line changed too."""
        entry = self.script_list.currentRow()
        self._reload_script_section()
        if 0 <= entry < self.script_list.count():
            self.script_list.setCurrentRow(entry)

    def _refresh_pseudo_code(self):
        section = self.current_script_section
        entry = self.script_list.currentRow()
        if section is None or entry < 0:
            self.pseudo_code_view.setPlainText("")
            return
        self.pseudo_code_view.setPlainText(
            to_pseudo_code(section, entry, self.manager.dialog_lookup()))

    # -- texts ------------------------------------------------------------------------------

    @property
    def current_text_section(self):
        return self.manager.text_sections.get(self.text_section_combo.currentData())

    def _on_text_section_changed(self):
        self._reload_text_section()

    def _reload_text_section(self):
        section = self.current_text_section
        with QSignalBlocker(self.text_list):
            self.text_list.clear()
            if section is not None:
                for index, entry in enumerate(section.entries):
                    self.text_list.addItem(f"{index}: {entry.text.splitlines()[0] if entry.text else ''}")
        if self.text_list.count():
            self.text_list.setCurrentRow(0)
        else:
            self._on_text_changed()

    def _on_text_changed(self):
        section = self.current_text_section
        row = self.text_list.currentRow()
        with QSignalBlocker(self.text_edit):
            if section is None or row < 0:
                self.text_edit.setPlainText("")
                self.text_users_view.setPlainText("")
                return
            self.text_edit.setPlainText(section.entries[row].text)
        users = self.manager.find_text_users(row) if section.index == 13 else []
        self.text_users_view.setPlainText(
            "\n".join(users) if users else "No script opens this text.")

    def _on_text_edited(self):
        section = self.current_text_section
        row = self.text_list.currentRow()
        if section is None or row < 0:
            return
        section.entries[row].text = self.text_edit.toPlainText()
        self._mark_dirty()
        with QSignalBlocker(self.text_list):
            item = self.text_list.item(row)
            first_line = section.entries[row].text.splitlines()
            item.setText(f"{row}: {first_line[0] if first_line else ''}")
