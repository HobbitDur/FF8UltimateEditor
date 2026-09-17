import os

from PyQt6.QtCore import Qt, QSignalBlocker, QTimer
from PyQt6.QtGui import QIcon, QFontMetrics
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QListWidget, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
                             QPushButton, QSplitter, QTabWidget, QGroupBox, QSpinBox, QMessageBox,
                             QAbstractItemView, QFileDialog, QListWidgetItem)

from Common.filebinding import FileBinding
from Common.undo import UndoStack
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Chocoboy.chocoboymanager import (ChocoboyManager, SCRIPT_SECTION_LIST, TEXT_SECTION_LIST,
                                      SECTION_NAME, SECTION_DESCRIPTION, SPAWN_SCRIPT_SECTION,
                                      DIALOG_SECTION)
from Chocoboy.scripttext import section_to_text, text_to_section
from SmallWidget.listsearchbar import ListSearchBar
from Chocoboy.wmsetscript import (OPCODE_LIST, Instruction, to_pseudo_code, value_text,
                                  NO_PARAM, WORD, GOTO_CODE)


class ChocoboyWidget(QWidget):
    """wmsetxx.obj editor: the world-map event scripts and the dialogs they open.

    The world map runs its own little bytecode - one 4-byte instruction at a time, as an
    IF / THEN / ELSE machine - and that is where every world-map side quest lives: the UFO, the
    Obel Lake rock, Chocobo forests, the train stations, boarding the Ragnarok. Sections 7, 9,
    11 and 36 hold the scripts; sections 13 and 31 hold the text they show.

    Named after Chocoboy, the boy who turns up in every Chocobo Forest on the world map.
    """

    VALUE_COLUMN_MAX_WIDTH = 320  # a resolved dialog line runs to hundreds of characters
    # Held down, a spin box fires one change per step; without this every one of them would be
    # its own undo step and Ctrl+Z would walk back through the number one unit at a time.
    UNDO_DEBOUNCE_MS = 400
    COMBO_DECORATION_WIDTH = 46  # the drop-down arrow, the frame and the cell margins

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_sysfnt_data()  # the character table the world-map texts are encoded in
        self.game_data.load_item_data()  # to name the item an ADD_ITEM hands out
        self.manager = ChocoboyManager(self.game_data)

        # Ctrl+Z / Ctrl+Shift+Z: the main window routes them to undo() / redo() on the shown
        # tool. The snapshot is the six sections this tool can change, not the whole megabyte of
        # wmsetxx.obj, so keeping forty of them costs well under a megabyte.
        self._undo_stack = None
        self._restoring_undo = False
        self._undo_debounce = QTimer(self)
        self._undo_debounce.setSingleShot(True)
        self._undo_debounce.setInterval(self.UNDO_DEBOUNCE_MS)
        self._undo_debounce.timeout.connect(self._commit_undo)

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

    def undo(self):
        """Ctrl+Z, routed here by the main window when this tool is the one shown."""
        self._flush_pending_undo()  # an edit not yet folded into a step must be undoable first
        if self._undo_stack is not None:
            self._undo_stack.undo()

    def redo(self):
        self._flush_pending_undo()
        if self._undo_stack is not None:
            self._undo_stack.redo()

    def _flush_pending_undo(self):
        if self._undo_debounce.isActive():
            self._undo_debounce.stop()
            self._commit_undo()

    def _commit_undo(self):
        """Fold everything edited since the last step into one undo step."""
        if self._undo_stack is not None and not self._restoring_undo:
            self._undo_stack.commit(self.script_section_combo.currentData())

    def _undo_restore(self, snapshot, tag=None):
        """Put a snapshot back and redraw, showing the section the undone edit happened in."""
        self._restoring_undo = True
        try:
            self.manager.restore_snapshot(snapshot)
            if tag is not None:
                index = self.script_section_combo.findData(tag)
                if index >= 0:
                    with QSignalBlocker(self.script_section_combo):
                        self.script_section_combo.setCurrentIndex(index)
            self._reload_script_section()
            self._reload_text_section()
        finally:
            self._restoring_undo = False

    def _mark_dirty(self):
        """Tell the shared header there are unsaved edits (it puts the * in the window title).

        The automatic tracker only knows the widgets that exist when a file loads, and this tool
        rebuilds its instruction rows every time another script is picked, so it says so itself."""
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()
        if not self._restoring_undo:
            self._undo_debounce.start()

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
        # Each line says what its script does, so this searches the section's behaviour: type
        # "Three Stars", "flag 61" or "battle" and only the scripts doing it are left.
        self.script_search = ListSearchBar(self.script_list, match_index=True,
                                           placeholder="Search the scripts (Ctrl+F)")

        script_group = QGroupBox("Scripts")
        script_group_layout = QVBoxLayout()
        script_group_layout.addWidget(self.script_section_combo)
        script_group_layout.addWidget(self.script_section_note)
        script_group_layout.addWidget(self.script_search)
        script_group_layout.addWidget(self.script_list)
        script_group_layout.addLayout(self._build_script_buttons())
        script_group.setLayout(script_group_layout)
        script_group.setFixedWidth(360)

        self.instruction_table = QTableWidget()
        self.instruction_table.setColumnCount(6)
        self.instruction_table.setHorizontalHeaderLabels(
            ["Offset", "Instruction", "Parameter", "Parameter 2", "What the parameters are",
             "What the instruction does"])
        self.instruction_table.verticalHeader().setVisible(False)
        self.instruction_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Every column can be dragged to whatever width suits the script being read, and the
        # last one takes up the slack. Sharing the spare width between the two text columns
        # instead would blow the parameter column up to half the table for a two-word value.
        header = self.instruction_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        self.add_button = QPushButton("Add instruction")
        self.add_button.setToolTip("Insert a copy of the selected line just above it, ready to be "
                                   "changed. Every script entry point and every GOTO after it "
                                   "moves with the change.")
        self.add_button.clicked.connect(self._on_add_instruction)
        self.remove_button = QPushButton("Remove instruction")
        self.remove_button.setToolTip("Delete the selected line. Every script entry point and "
                                      "every GOTO after it moves with the change.")
        self.remove_button.clicked.connect(self._on_remove_instruction)

        self.export_button = QPushButton("Export to text")
        self.export_button.setToolTip("Write every script of this section to a text file: "
                                      "opcodes, named jump targets, and room for your own "
                                      "comments and a name per script")
        self.export_button.clicked.connect(self._on_export_section)
        self.import_button = QPushButton("Import from text")
        self.import_button.setToolTip("Read a section back from a text file written here. "
                                      "Jump targets are resolved from their labels, so the "
                                      "scripts may have grown, shrunk, appeared or disappeared")
        self.import_button.clicked.connect(self._on_import_section)

        self.check_button = QPushButton("Check section")
        self.check_button.setToolTip("Look for what would break the game: a jump to nowhere, a "
                                     "script not ending on RETURN, a branch with no actions")
        self.check_button.clicked.connect(self._on_check_section)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addSpacing(16)
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.import_button)
        button_row.addSpacing(16)
        button_row.addWidget(self.check_button)
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

        self.usage_view = QListWidget()
        self.usage_view.setToolTip("Double-click a line to go to that instruction")
        self.usage_view.itemDoubleClicked.connect(self._on_usage_double_clicked)
        self.usage_group = QGroupBox("What else touches this")
        usage_layout = QVBoxLayout()
        usage_layout.addWidget(self.usage_view)
        self.usage_group.setLayout(usage_layout)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(pseudo_code_group)
        bottom_splitter.addWidget(self.usage_group)
        bottom_splitter.setStretchFactor(0, 3)
        bottom_splitter.setStretchFactor(1, 2)

        editor_splitter = QSplitter(Qt.Orientation.Vertical)
        editor_splitter.addWidget(table_panel)
        editor_splitter.addWidget(bottom_splitter)
        editor_splitter.setStretchFactor(0, 3)
        editor_splitter.setStretchFactor(1, 2)
        self.instruction_table.currentCellChanged.connect(self._on_instruction_selected)
        self.instruction_table.cellDoubleClicked.connect(self._on_instruction_double_clicked)

        tab = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(script_group)
        layout.addWidget(editor_splitter, 1)
        tab.setLayout(layout)
        return tab

    def _build_script_buttons(self):
        """Adding, copying, removing and reordering whole scripts.

        Reordering is not cosmetic in sections 7 and 11: the interpreter stops at the first
        script whose condition list passes, so the order of the table is what decides which one
        runs, and a script moved up can shadow the one that used to answer.
        """
        self.add_script_button = QPushButton("Add")
        self.add_script_button.setToolTip("Insert an empty script before the selected one. It is "
                                          "an IF / FAIL / RETURN, which never matches, so it "
                                          "cannot shadow anything until you fill it in")
        self.add_script_button.clicked.connect(self._on_add_script)

        self.duplicate_script_button = QPushButton("Duplicate")
        self.duplicate_script_button.setToolTip("Copy the selected script in right after it, "
                                                "with its jumps pointing inside the copy")
        self.duplicate_script_button.clicked.connect(self._on_duplicate_script)

        self.remove_script_button = QPushButton("Remove")
        self.remove_script_button.setToolTip("Delete the selected script")
        self.remove_script_button.clicked.connect(self._on_remove_script)

        self.move_up_button = QPushButton("Up")
        self.move_up_button.setToolTip("Move the script one place earlier in the table")
        self.move_up_button.clicked.connect(lambda: self._on_move_script(-1))
        self.move_down_button = QPushButton("Down")
        self.move_down_button.setToolTip("Move the script one place later in the table")
        self.move_down_button.clicked.connect(lambda: self._on_move_script(1))

        row = QHBoxLayout()
        for button in (self.add_script_button, self.duplicate_script_button,
                       self.remove_script_button, self.move_up_button, self.move_down_button):
            row.addWidget(button)
        return row

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
        # Baseline = what was just read, which is what is on disk
        self._undo_stack = UndoStack(capture=self.manager.snapshot, restore=self._undo_restore)

    def save_file(self):
        if not self.manager.is_loaded:
            return
        self._flush_pending_undo()  # so the state written to disk is the one undo calls clean
        self.manager.save_file()
        if self._undo_stack is not None:
            self._undo_stack.mark_saved()

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
                for entry in range(len(section.entry_offsets)):
                    self.script_list.addItem(self._script_line(section, entry))
        self.script_search.search()  # a refilled list has to be filtered again
        if self.script_list.count():
            self.script_list.setCurrentRow(0)
        else:
            self._reload_instructions()

    def _script_line(self, section, entry):
        """One line of the script list: its number, its name, and what it does.

        Without the last part the list is 92 identical lines, and there is no way to find the
        script that gives the Three Stars except by opening all of them. It doubles as what the
        search box matches on.
        """
        name = section.script_names.get(entry)
        summary = ", ".join(self._script_summary(section, entry)[:4])
        head = f"#{entry}" + (f" {name}" if name else "")
        return f"{head} - {summary}" if summary else head

    def _script_summary(self, section, entry):
        """The handful of things a script does that tell you which script it is."""
        dialogs = self.manager.dialog_lookup()
        seen = []
        start, end = section.script_range(entry)
        for index in range(start, end):
            instruction = section.instructions[index]
            code = instruction.code
            if code == 0xFF37:
                note = f"gives {self._item_name(instruction.param1)}"
            elif code in (0xFF1F, 0xFF23):
                text = dialogs.get(instruction.param2, "")
                note = f"says \"{text.splitlines()[0][:40] if text else instruction.param2}\""
            elif code == 0xFF08:
                note = f"warps to entrance {instruction.word}"
            elif code == 0xFF2B:
                note = f"battle {instruction.word}"
            elif code == 0xFF28:
                note = f"sets flag {instruction.param1}"
            elif code in (0xFF13, 0xFF14):
                note = f"spawns model {instruction.param1}"
            elif code == 0xFF26:
                note = f"world state {instruction.param1}"
            else:
                continue
            if note not in seen:
                seen.append(note)
        return seen

    def _on_script_changed(self):
        self._reload_instructions()

    def _on_instruction_selected(self, row, _column, _previous_row, _previous_column):
        """Show everywhere else in the file that touches what the selected line touches."""
        section = self.current_script_section
        index = self._instruction_index(row)
        if section is None or index is None:
            self.usage_view.clear()
            return
        instruction = section.instructions[index]
        title, users = self._usage_of(instruction)
        self.usage_group.setTitle(title)
        self.usage_view.clear()
        if not users:
            self.usage_view.addItem("Nothing else in the file touches it.")
            return
        for usage in users:
            item = QListWidgetItem(str(usage))
            item.setData(Qt.ItemDataRole.UserRole, (usage.section, usage.offset))
            self.usage_view.addItem(item)

    def _on_instruction_double_clicked(self, row, _column):
        """Double-clicking a jump follows it, which is the only way to read one at a glance."""
        section = self.current_script_section
        index = self._instruction_index(row)
        if section is None or index is None:
            return
        instruction = section.instructions[index]
        if instruction.code != GOTO_CODE:
            return
        target = section.index_at_offset(instruction.word)
        if target is not None:
            self._show_instruction(self.script_section_combo.currentData(),
                                   section.instruction_offset(target))

    def _on_usage_double_clicked(self, item):
        place = item.data(Qt.ItemDataRole.UserRole)
        if place is not None:
            self._show_instruction(*place)

    def _show_instruction(self, section_index, offset):
        """Bring one instruction of one section into view and select it."""
        combo_index = self.script_section_combo.findData(section_index)
        if combo_index < 0:
            return
        self.script_section_combo.setCurrentIndex(combo_index)
        section = self.current_script_section
        target = section.index_at_offset(offset)
        if target is None:
            return
        owners = [entry for entry in range(len(section.entry_offsets))
                  if section.script_range(entry)[0] <= target < section.script_range(entry)[1]]
        if not owners:
            return
        self.script_list.setCurrentRow(owners[0])
        for row in range(self.instruction_table.rowCount()):
            if self._instruction_index(row) == target:
                self.instruction_table.setCurrentCell(row, 0)
                self.instruction_table.scrollToItem(self.instruction_table.item(row, 0))
                return

    def _usage_of(self, instruction):
        """(what is being looked up, everywhere it is used) for the selected instruction."""
        if instruction.code in (0xFF27, 0xFF28):
            return (f"What else touches save flag {instruction.param1}",
                    self.manager.find_flag_users(instruction.param1))
        if instruction.code in (0xFF2D, 0xFF2E, 0xFF30, 0xFF31):
            return (f"What else touches script var {instruction.param1}",
                    self.manager.find_script_var_users(instruction.param1))
        if instruction.code in (0xFF1F, 0xFF23):
            return (f"What else opens dialog {instruction.param2}",
                    self.manager.find_text_users(instruction.param2))
        if instruction.code in (0xFF24, 0xFF2C):
            window = instruction.word if instruction.code == 0xFF24 else instruction.param1
            return (f"What else uses message window {window}",
                    self.manager.find_message_window_users(window))
        return ("What else touches this", [])

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
        # Two columns come out far too wide on their own. A combo box asks for the width of its
        # whole drop-down list - every opcode name at once - so the opcode column is sized to the
        # names actually on screen instead. And a resolved dialog line runs long enough to push
        # everything else out of the table, so that column is capped. Both stay draggable.
        self.instruction_table.setColumnWidth(1, self._opcode_column_width())
        self.instruction_table.setColumnWidth(
            4, min(self.instruction_table.columnWidth(4), self.VALUE_COLUMN_MAX_WIDTH))
        self._refresh_pseudo_code()

    def _opcode_column_width(self):
        """Wide enough for the longest opcode name shown right now, and no wider."""
        metrics = QFontMetrics(self.instruction_table.font())
        widest = max((metrics.horizontalAdvance(
            self.instruction_table.cellWidget(row, 1).currentText())
            for row in range(self.instruction_table.rowCount())), default=0)
        return widest + self.COMBO_DECORATION_WIDTH

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

        value_item = QTableWidgetItem(self._value_of(section, instruction))
        value_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.instruction_table.setItem(row, 4, value_item)

        description_item = QTableWidgetItem(
            instruction.opcode.description if instruction.opcode
            else "Not an instruction this tool knows. Kept as it is.")
        description_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.instruction_table.setItem(row, 5, description_item)

    def _value_of(self, section, instruction):
        """What this instruction's parameters actually stand for, when the tool can say.

        The parameters are the whole difficulty of reading these scripts: a bare 61, 124 or 60, 2
        says nothing. Whatever can be resolved from the file itself or from the game data - the
        dialog a number opens, the item it hands out, the buttons a mask stands for, the place an
        entity spawns at, the instruction a jump lands on - is spelled out here."""
        if instruction.opcode is None:
            return f"raw bytes {instruction.param1}, {instruction.param2}"
        if instruction.code in (0xFF1F, 0xFF23):
            text = self.manager.dialog_lookup().get(instruction.param2)
            return f'"{text}"' if text is not None else f"no text {instruction.param2} in section 13"
        if instruction.code == 0xFF37:
            return self._item_name(instruction.param1)
        if instruction.code in (0xFF13, 0xFF14) and self.manager.spawn_positions:
            return self.manager.spawn_positions.describe(instruction.param1, instruction.param2)
        if instruction.code == GOTO_CODE:
            return self._goto_target_text(section, instruction)
        return value_text(instruction)

    def _goto_target_text(self, section, instruction):
        """Where a jump lands, which the raw number never tells you."""
        target = section.index_at_offset(instruction.word)
        if target is None:
            return "WARNING: that offset is not the start of an instruction"
        owners = [entry for entry in range(len(section.entry_offsets))
                  if section.script_range(entry)[0] <= target < section.script_range(entry)[1]]
        landing = section.instructions[target].name
        if not owners:
            return f"lands on {landing}, in no script of this section"
        return f"lands on {landing}, in script #{owners[0]}"

    def _item_name(self, item_id):
        items = getattr(self.game_data, "item_data_json", {}).get("items", [])
        if 0 <= item_id < len(items):
            return items[item_id]["name"]
        return f"item {item_id}"

    def _instruction_index(self, row):
        """The stream index the table row stands for, or None when the row is not one.

        Emptying the table makes Qt report the selection moving to row -1, so "no row" has to be
        an answer here rather than something the caller has to think about."""
        if row < 0:
            return None
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
        value_item = self.instruction_table.item(row, 4)
        if value_item is not None:
            value_item.setText(self._value_of(section, instruction))
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

    def _new_script(self):
        """A script that does nothing and, more to the point, matches nothing.

        A bare RETURN would be worse than useless in sections 7 and 11: with no condition list
        in front of it, it matches at once and stops the scan, so every script after it would
        stop running. IF / FAIL / RETURN can never pass, so it shadows nothing.
        """
        if self.script_section_combo.currentData() == SPAWN_SCRIPT_SECTION:
            return [Instruction(0xFF05)]  # a spawn list, which ends on END rather than RETURN
        return [Instruction(0xFF01), Instruction(0xFF1E), Instruction(0xFF16)]

    def _on_add_script(self):
        section = self.current_script_section
        if section is None or not self._can_rearrange(section):
            return
        entry = max(self.script_list.currentRow(), 0)
        section.add_script(entry, self._new_script())
        self._after_script_change(entry)

    def _on_duplicate_script(self):
        section = self.current_script_section
        entry = self.script_list.currentRow()
        if section is None or entry < 0 or not self._can_rearrange(section):
            return
        section.duplicate_script(entry)
        self._after_script_change(entry + 1)

    def _on_remove_script(self):
        section = self.current_script_section
        entry = self.script_list.currentRow()
        if section is None or entry < 0 or not self._can_rearrange(section):
            return
        jumps_in = [usage for usage in self._jumps_into_script(section, entry)]
        warning = ("\n\nSomething jumps into it, and that jump will be left pointing at whatever "
                   "takes its place:\n" + "\n".join(jumps_in)) if jumps_in else ""
        if QMessageBox.question(self, "Chocoboy - Remove a script",
                                f"Remove script #{entry} of section "
                                f"{self.script_section_combo.currentData()}?" + warning
                                ) != QMessageBox.StandardButton.Yes:
            return
        section.remove_script(entry)
        self._after_script_change(min(entry, len(section.entry_offsets) - 1))

    def _on_move_script(self, delta):
        section = self.current_script_section
        entry = self.script_list.currentRow()
        if section is None or entry < 0 or not self._can_rearrange(section):
            return
        destination = entry + delta
        if not 0 <= destination < len(section.entry_offsets):
            return
        section.move_script(entry, destination)
        self._after_script_change(destination)

    def _jumps_into_script(self, section, entry):
        """The jumps from elsewhere that land inside this script, as text lines."""
        start, end = section.script_range(entry)
        lines = []
        for other in range(len(section.entry_offsets)):
            if other == entry:
                continue
            other_start, other_end = section.script_range(other)
            for index in range(other_start, other_end):
                instruction = section.instructions[index]
                if instruction.code != GOTO_CODE:
                    continue
                target = section.index_at_offset(instruction.word)
                if target is not None and start <= target < end:
                    lines.append(f"script #{other}, offset {section.instruction_offset(index)}")
        return lines

    def _can_rearrange(self, section):
        """Refuse to rebuild a section whose scripts do not account for all of its bytes.

        Nothing in the shipped file is like that, but an entry pointing into the middle of
        another script would leave instructions belonging to no script, and rebuilding from a
        list of scripts would drop them.
        """
        if section.scripts_cover_everything():
            return True
        QMessageBox.warning(self, "Chocoboy - Cannot rearrange this section",
                            "Some of this section's instructions belong to no script, so adding "
                            "or moving one would lose them. Edit it as text instead.")
        return False

    def _after_script_change(self, entry):
        self._mark_dirty()
        self._reload_script_section()
        if 0 <= entry < self.script_list.count():
            self.script_list.setCurrentRow(entry)

    def _on_export_section(self):
        section = self.current_script_section
        if section is None:
            return
        index = self.script_section_combo.currentData()
        default_name = f"section{index}_scripts.txt"
        folder = os.path.dirname(self.manager.file_path) or os.getcwd()
        path = QFileDialog.getSaveFileName(self, f"Export section {index} scripts",
                                           os.path.join(folder, default_name), "*.txt")[0]
        if not path:
            return
        with open(path, "w", encoding="utf8") as out_file:
            out_file.write(section_to_text(section, SECTION_NAME[index]))

    def _on_import_section(self):
        section = self.current_script_section
        if section is None:
            return
        index = self.script_section_combo.currentData()
        folder = os.path.dirname(self.manager.file_path) or os.getcwd()
        path = QFileDialog.getOpenFileName(self, f"Import section {index} scripts", folder,
                                           "*.txt")[0]
        if not path:
            return
        with open(path, encoding="utf8") as in_file:
            result = text_to_section(in_file.read())
        if not result.ok:
            QMessageBox.critical(self, f"Chocoboy - Section {index} not imported",
                                 "Nothing was changed.\n\n" + "\n".join(result.errors[:20]))
            return
        section.replace_scripts(result.scripts, result.names, result.trailing_comments)
        self._mark_dirty()
        self._reload_script_section()
        QMessageBox.information(self, f"Chocoboy - Section {index} imported",
                                "\n".join(result.warnings))

    def _on_check_section(self):
        section = self.current_script_section
        if section is None:
            return
        index = self.script_section_combo.currentData()
        problems = section.problems(must_return=index != SPAWN_SCRIPT_SECTION)
        if not problems:
            QMessageBox.information(
                self, f"Chocoboy - Section {index}",
                f"Nothing wrong with the {len(section.entry_offsets)} script(s) of this section.")
            return
        lines = [f"Script #{entry}, offset {offset}: {message}"
                 for entry, offset, message in problems[:40]]
        if len(problems) > 40:
            lines.append(f"... and {len(problems) - 40} more")
        QMessageBox.warning(self, f"Chocoboy - Section {index}",
                            f"{len(problems)} problem(s):\n\n" + "\n".join(lines))

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
        users = self.manager.find_text_users(row) if section.index == DIALOG_SECTION else []
        self.text_users_view.setPlainText(
            "\n".join(str(usage) for usage in users) if users
            else "No script opens this text.")

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
