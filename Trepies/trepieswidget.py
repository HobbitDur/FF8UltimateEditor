import os

from PyQt6.QtCore import QSize, QSignalBlocker, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QSpinBox, QComboBox, QGroupBox, QFormLayout, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QCheckBox,
                             QScrollArea, QMessageBox)

from FF8GameData.gamedata import GameData
from Trepies.trepiesmanager import (TrepiesManager, DemoScriptOp, DEMO_OPCODE_NAMES,
                                    DEMO_OPCODES_WITH_OPERAND, SCRIPT_SLOTS, MOCK_CHAR_SLOTS,
                                    MOCK_GF_SLOTS, NB_MAGIC_SLOTS, NB_GF_COMPATIBILITY,
                                    NB_GF_AP_SLOTS, GF_NAMES, GF_COMPLETE_ABILITIES_SIZE)

MOCK_VARIANT_LABELS = {
    176: "Variant A (raw 176) - junction/GF/limit demos",
    178: "Variant B (raw 178) - elemental/status/switch demos",
    177: "Variant A (raw 177) - junction/GF/limit demos",
    179: "Variant B (raw 179) - elemental/status/switch demos",
}


class TrepiesWidget(QWidget):
    """mngrp.bin tutorial demo editor (Trepies).

    Edits the demo input scripts (raw mngrphd slots 168-175 and 205) as a
    readable op list, and the mock save data the demos run on: the 8 savemap
    character records of raw 176/178 and the 16 GF records of raw 177/179.
    The game forces HP to 9999 and replaces the GF names with the real save's
    names when a demo starts, so those fields are mostly cosmetic in game."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_magic_data()
        self.manager = TrepiesManager(self.game_data)
        self._loaded = False

        self.magic_names = [magic["name"] for magic in self.game_data.magic_data_json["magic"]]

        self.setWindowTitle("Trepies")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a mngrp.bin file (mngrphd.bin is searched next to it)")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened mngrp.bin + mngrphd.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._build_script_tab(), "Demo scripts")
        self.tab_widget.addTab(self._build_character_tab(), "Mock characters")
        self.tab_widget.addTab(self._build_gf_tab(), "Mock GFs")
        self.tab_widget.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

    # ----------------------------------------------------------------- file

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mngrp.bin file",
                                                     filter="mngrp.bin;;*.bin", directory=os.getcwd())[0]
        if not file_name:
            return
        header_file = os.path.join(os.path.dirname(file_name), "mngrphd.bin")
        if not os.path.exists(header_file):
            header_file = self.file_dialog.getOpenFileName(parent=self, caption="Search mngrphd.bin file",
                                                           filter="mngrphd.bin;;*.bin",
                                                           directory=os.path.dirname(file_name))[0]
            if not header_file:
                return
        try:
            self.manager.load_file(header_file, file_name)
        except ValueError as e:
            QMessageBox.warning(self, "Trepies", str(e))
            return
        self._loaded = True
        self.file_label.setText(os.path.basename(file_name))
        self.tab_widget.setEnabled(True)
        with QSignalBlocker(self.script_list):
            self.script_list.clear()
            self.script_list.addItems([f"{self.manager.scripts[slot].name} (raw {slot})"
                                       for slot in SCRIPT_SLOTS])
        self.script_list.setCurrentRow(0)
        self.reload_selected_script()
        self._reload_char_list()
        self._reload_gf_list()

    def save_file(self):
        if self._loaded:
            self.manager.save_file()

    # -------------------------------------------------------- demo script tab

    def _build_script_tab(self):
        self.script_list = QListWidget()
        self.script_list.setFixedWidth(230)
        self.script_list.currentRowChanged.connect(self.reload_selected_script)

        self.op_table = QTableWidget(0, 3)
        self.op_table.setHorizontalHeaderLabels(["Opcode", "Operand", "Hint"])
        self.op_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.op_table.verticalHeader().setDefaultSectionSize(24)

        add_button = QPushButton("Add op")
        add_button.setToolTip("Insert a new op after the selected row")
        add_button.clicked.connect(self._add_op)
        remove_button = QPushButton("Remove op")
        remove_button.clicked.connect(self._remove_op)
        up_button = QPushButton("Move up")
        up_button.clicked.connect(lambda: self._move_op(-1))
        down_button = QPushButton("Move down")
        down_button.clicked.connect(lambda: self._move_op(1))

        button_layout = QHBoxLayout()
        for button in (add_button, remove_button, up_button, down_button):
            button_layout.addWidget(button)
        button_layout.addStretch(1)

        right_layout = QVBoxLayout()
        right_layout.addLayout(button_layout)
        right_layout.addWidget(self.op_table)

        layout = QHBoxLayout()
        layout.addWidget(self.script_list)
        layout.addLayout(right_layout)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _selected_script(self):
        index = self.script_list.currentRow()
        if self._loaded and 0 <= index < len(SCRIPT_SLOTS):
            return self.manager.scripts[SCRIPT_SLOTS[index]]
        return None

    def reload_selected_script(self):
        script = self._selected_script()
        if not script:
            return
        captions = self.manager.get_captions(script.raw_slot)
        with QSignalBlocker(self.op_table):
            self.op_table.setRowCount(len(script.ops))
            for row, op in enumerate(script.ops):
                self._fill_op_row(row, op, captions)

    def _fill_op_row(self, row, op, captions):
        opcode_combo = QComboBox()
        for opcode, name in sorted(DEMO_OPCODE_NAMES.items()):
            opcode_combo.addItem(name, opcode)
        if op.opcode not in DEMO_OPCODE_NAMES:
            opcode_combo.addItem(op.name, op.opcode)
        opcode_combo.setCurrentIndex(opcode_combo.findData(op.opcode))
        opcode_combo.currentIndexChanged.connect(lambda _index, r=row: self._on_op_changed(r))
        self.op_table.setCellWidget(row, 0, opcode_combo)

        operand_spinbox = QSpinBox()
        operand_spinbox.setRange(0, 0xFFF)
        operand_spinbox.setValue(op.operand)
        operand_spinbox.valueChanged.connect(lambda _value, r=row: self._on_op_changed(r))
        self.op_table.setCellWidget(row, 1, operand_spinbox)

        hint_item = QTableWidgetItem(op.describe(captions))
        hint_item.setFlags(hint_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.op_table.setItem(row, 2, hint_item)

    def _on_op_changed(self, row):
        script = self._selected_script()
        if not script or row >= len(script.ops):
            return
        opcode = self.op_table.cellWidget(row, 0).currentData()
        operand = self.op_table.cellWidget(row, 1).value()
        script.ops[row] = DemoScriptOp(opcode, operand)
        hint = script.ops[row].describe(self.manager.get_captions(script.raw_slot))
        with QSignalBlocker(self.op_table):
            self.op_table.item(row, 2).setText(hint)

    def _add_op(self):
        script = self._selected_script()
        if not script:
            return
        row = self.op_table.currentRow()
        insert_at = row + 1 if row >= 0 else len(script.ops)
        script.ops.insert(insert_at, DemoScriptOp(0x9, 1))  # neutral WAIT 1
        self.reload_selected_script()
        self.op_table.setCurrentCell(insert_at, 0)

    def _remove_op(self):
        script = self._selected_script()
        row = self.op_table.currentRow()
        if not script or not 0 <= row < len(script.ops):
            return
        script.ops.pop(row)
        self.reload_selected_script()

    def _move_op(self, direction):
        script = self._selected_script()
        row = self.op_table.currentRow()
        if not script or not 0 <= row < len(script.ops):
            return
        new_row = row + direction
        if not 0 <= new_row < len(script.ops):
            return
        script.ops[row], script.ops[new_row] = script.ops[new_row], script.ops[row]
        self.reload_selected_script()
        self.op_table.setCurrentCell(new_row, 0)

    # ------------------------------------------------------ mock character tab

    def _build_character_tab(self):
        self.char_variant_combo = QComboBox()
        for slot in MOCK_CHAR_SLOTS:
            self.char_variant_combo.addItem(MOCK_VARIANT_LABELS[slot], slot)
        self.char_variant_combo.currentIndexChanged.connect(self._reload_char_list)

        self.char_list = QListWidget()
        self.char_list.setFixedWidth(150)
        self.char_list.currentRowChanged.connect(self.reload_selected_character)

        # Base stats form
        self.char_fields = {}
        stats_form = QFormLayout()
        for key, label, maximum in (("current_hp", "Current HP (forced to 9999 in game)", 0xFFFF),
                                    ("max_hp", "Max HP", 0xFFFF),
                                    ("exp", "Experience", 0x7FFFFFFF),
                                    ("model_id", "Model ID", 0xFF),
                                    ("weapon_id", "Weapon ID", 0xFF),
                                    ("stat_str", "STR", 0xFF), ("stat_vit", "VIT", 0xFF),
                                    ("stat_mag", "MAG", 0xFF), ("stat_spr", "SPR", 0xFF),
                                    ("stat_spd", "SPD", 0xFF), ("stat_lck", "LCK", 0xFF),
                                    ("alternative_model", "Alternative model", 0xFF),
                                    ("kills", "Kills", 0xFFFF), ("kos", "KOs", 0xFFFF)):
            spinbox = QSpinBox()
            spinbox.setRange(0, maximum)
            spinbox.valueChanged.connect(self._on_character_changed)
            self.char_fields[key] = spinbox
            stats_form.addRow(label + ":", spinbox)
        self.char_exists_checkbox = QCheckBox("Exists (in the demo party)")
        self.char_exists_checkbox.stateChanged.connect(self._on_character_changed)
        stats_form.addRow(self.char_exists_checkbox)
        stats_group = QGroupBox("Stats")
        stats_group.setLayout(stats_form)

        # Junction form (values are ids of the junctioned magics)
        self.junction_fields = {}
        junction_form = QFormLayout()
        for key, label in (("junctioned_gfs", "Junctioned GFs (bitfield)"),
                           ("junction_hp", "HP-J magic"), ("junction_str", "STR-J magic"),
                           ("junction_vit", "VIT-J magic"), ("junction_mag", "MAG-J magic"),
                           ("junction_spr", "SPR-J magic"), ("junction_spd", "SPD-J magic"),
                           ("junction_eva", "EVA-J magic"), ("junction_hit", "HIT-J magic"),
                           ("junction_lck", "LCK-J magic"),
                           ("junction_elem_attack", "Elem-Atk-J magic"),
                           ("junction_mental_attack", "ST-Atk-J magic")):
            spinbox = QSpinBox()
            spinbox.setRange(0, 0xFFFF if key == "junctioned_gfs" else 0xFF)
            spinbox.valueChanged.connect(self._on_character_changed)
            self.junction_fields[key] = spinbox
            junction_form.addRow(label + ":", spinbox)
        junction_group = QGroupBox("Junctions")
        junction_group.setLayout(junction_form)

        # Magic inventory table
        self.magic_table = QTableWidget(NB_MAGIC_SLOTS, 2)
        self.magic_table.setHorizontalHeaderLabels(["Magic", "Quantity"])
        self.magic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.magic_table.verticalHeader().setDefaultSectionSize(24)
        for row in range(NB_MAGIC_SLOTS):
            magic_combo = QComboBox()
            magic_combo.addItems(self.magic_names)
            magic_combo.currentIndexChanged.connect(self._on_character_changed)
            self.magic_table.setCellWidget(row, 0, magic_combo)
            quantity_spinbox = QSpinBox()
            quantity_spinbox.setRange(0, 255)
            quantity_spinbox.valueChanged.connect(self._on_character_changed)
            self.magic_table.setCellWidget(row, 1, quantity_spinbox)
        magic_layout = QVBoxLayout()
        magic_layout.addWidget(self.magic_table)
        magic_group = QGroupBox("Magic inventory")
        magic_group.setLayout(magic_layout)

        # GF compatibility table
        self.compat_table = QTableWidget(NB_GF_COMPATIBILITY, 1)
        self.compat_table.setHorizontalHeaderLabels(["Compatibility"])
        self.compat_table.setVerticalHeaderLabels(list(GF_NAMES))
        self.compat_table.verticalHeader().setDefaultSectionSize(24)
        for row in range(NB_GF_COMPATIBILITY):
            compat_spinbox = QSpinBox()
            compat_spinbox.setRange(0, 0xFFFF)
            compat_spinbox.valueChanged.connect(self._on_character_changed)
            self.compat_table.setCellWidget(row, 0, compat_spinbox)
        compat_layout = QVBoxLayout()
        compat_layout.addWidget(self.compat_table)
        compat_group = QGroupBox("GF compatibility")
        compat_group.setLayout(compat_layout)

        editor_layout = QHBoxLayout()
        left_column = QVBoxLayout()
        left_column.addWidget(stats_group)
        left_column.addWidget(junction_group)
        left_column.addStretch(1)
        editor_layout.addLayout(left_column)
        editor_layout.addWidget(magic_group)
        editor_layout.addWidget(compat_group)

        self.char_editor_container = QWidget()
        self.char_editor_container.setLayout(editor_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.char_editor_container)
        scroll_area.setWidgetResizable(True)

        layout = QVBoxLayout()
        layout.addWidget(self.char_variant_combo)
        content_layout = QHBoxLayout()
        content_layout.addWidget(self.char_list)
        content_layout.addWidget(scroll_area)
        layout.addLayout(content_layout)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _selected_character(self):
        index = self.char_list.currentRow()
        if not self._loaded or index < 0:
            return None
        slot = self.char_variant_combo.currentData()
        records = self.manager.mock_char_files[slot].records
        if index < len(records):
            return records[index]
        return None

    def _reload_char_list(self):
        if not self._loaded:
            return
        slot = self.char_variant_combo.currentData()
        records = self.manager.mock_char_files[slot].records
        with QSignalBlocker(self.char_list):
            self.char_list.clear()
            self.char_list.addItems([record.name for record in records])
        self.char_list.setCurrentRow(0)
        self.reload_selected_character()

    def reload_selected_character(self):
        record = self._selected_character()
        if not record:
            return
        for key, spinbox in {**self.char_fields, **self.junction_fields}.items():
            with QSignalBlocker(spinbox):
                spinbox.setValue(getattr(record, key))
        with QSignalBlocker(self.char_exists_checkbox):
            self.char_exists_checkbox.setChecked(record.exists != 0)
        for row in range(NB_MAGIC_SLOTS):
            magic_id, quantity = record.get_magic(row)
            magic_combo = self.magic_table.cellWidget(row, 0)
            with QSignalBlocker(magic_combo):
                magic_combo.setCurrentIndex(magic_id if magic_id < magic_combo.count() else 0)
            quantity_spinbox = self.magic_table.cellWidget(row, 1)
            with QSignalBlocker(quantity_spinbox):
                quantity_spinbox.setValue(quantity)
        for row in range(NB_GF_COMPATIBILITY):
            compat_spinbox = self.compat_table.cellWidget(row, 0)
            with QSignalBlocker(compat_spinbox):
                compat_spinbox.setValue(record.get_gf_compatibility(row))

    def _on_character_changed(self):
        record = self._selected_character()
        if not record:
            return
        for key, spinbox in {**self.char_fields, **self.junction_fields}.items():
            setattr(record, key, spinbox.value())
        record.exists = 1 if self.char_exists_checkbox.isChecked() else 0
        for row in range(NB_MAGIC_SLOTS):
            record.set_magic(row, self.magic_table.cellWidget(row, 0).currentIndex(),
                             self.magic_table.cellWidget(row, 1).value())
        for row in range(NB_GF_COMPATIBILITY):
            record.set_gf_compatibility(row, self.compat_table.cellWidget(row, 0).value())

    # ------------------------------------------------------------ mock GF tab

    def _build_gf_tab(self):
        self.gf_variant_combo = QComboBox()
        for slot in MOCK_GF_SLOTS:
            self.gf_variant_combo.addItem(MOCK_VARIANT_LABELS[slot], slot)
        self.gf_variant_combo.currentIndexChanged.connect(self._reload_gf_list)

        self.gf_list = QListWidget()
        self.gf_list.setFixedWidth(150)
        self.gf_list.currentRowChanged.connect(self.reload_selected_gf)

        self.gf_name_edit = QLineEdit()
        self.gf_name_edit.setMaxLength(11)
        self.gf_name_edit.setToolTip("Development name stored in the file: the game replaces it "
                                     "with the real save's GF name when the demo starts")
        self.gf_name_edit.editingFinished.connect(self._on_gf_changed)

        self.gf_fields = {}
        gf_form = QFormLayout()
        gf_form.addRow("Stored name:", self.gf_name_edit)
        for key, label, maximum in (("exp", "Experience", 0x7FFFFFFF),
                                    ("hp", "HP (forced to 9999 in game)", 0xFFFF),
                                    ("kills", "Kills", 0xFFFF), ("kos", "KOs", 0xFFFF),
                                    ("learning_ability", "Learning ability", 0xFF)):
            spinbox = QSpinBox()
            spinbox.setRange(0, maximum)
            spinbox.valueChanged.connect(self._on_gf_changed)
            self.gf_fields[key] = spinbox
            gf_form.addRow(label + ":", spinbox)
        self.gf_exists_checkbox = QCheckBox("Exists (unlocked in the demo)")
        self.gf_exists_checkbox.stateChanged.connect(self._on_gf_changed)
        gf_form.addRow(self.gf_exists_checkbox)

        self.gf_complete_edit = QLineEdit()
        self.gf_complete_edit.setToolTip("Completed abilities bitfield, 16 bytes as hex")
        self.gf_complete_edit.editingFinished.connect(self._on_gf_changed)
        gf_form.addRow("Completed abilities (hex):", self.gf_complete_edit)
        self.gf_forgotten_edit = QLineEdit()
        self.gf_forgotten_edit.setToolTip("Forgotten abilities bitfield, 2 bytes as hex")
        self.gf_forgotten_edit.editingFinished.connect(self._on_gf_changed)
        gf_form.addRow("Forgotten abilities (hex):", self.gf_forgotten_edit)
        gf_group = QGroupBox("GF record")
        gf_group.setLayout(gf_form)

        self.ap_table = QTableWidget(NB_GF_AP_SLOTS, 1)
        self.ap_table.setHorizontalHeaderLabels(["AP"])
        self.ap_table.setVerticalHeaderLabels([f"Ability {i}" for i in range(NB_GF_AP_SLOTS)])
        self.ap_table.verticalHeader().setDefaultSectionSize(24)
        for row in range(NB_GF_AP_SLOTS):
            ap_spinbox = QSpinBox()
            ap_spinbox.setRange(0, 255)
            ap_spinbox.valueChanged.connect(self._on_gf_changed)
            self.ap_table.setCellWidget(row, 0, ap_spinbox)
        ap_layout = QVBoxLayout()
        ap_layout.addWidget(self.ap_table)
        ap_group = QGroupBox("APs per ability slot")
        ap_group.setLayout(ap_layout)

        editor_layout = QHBoxLayout()
        left_column = QVBoxLayout()
        left_column.addWidget(gf_group)
        left_column.addStretch(1)
        editor_layout.addLayout(left_column)
        editor_layout.addWidget(ap_group)

        layout = QVBoxLayout()
        layout.addWidget(self.gf_variant_combo)
        content_layout = QHBoxLayout()
        content_layout.addWidget(self.gf_list)
        content_layout.addLayout(editor_layout)
        layout.addLayout(content_layout)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _selected_gf(self):
        index = self.gf_list.currentRow()
        if not self._loaded or index < 0:
            return None
        slot = self.gf_variant_combo.currentData()
        records = self.manager.mock_gf_files[slot].records
        if index < len(records):
            return records[index]
        return None

    def _reload_gf_list(self):
        if not self._loaded:
            return
        slot = self.gf_variant_combo.currentData()
        records = self.manager.mock_gf_files[slot].records
        with QSignalBlocker(self.gf_list):
            self.gf_list.clear()
            self.gf_list.addItems([record.gf_name for record in records])
        self.gf_list.setCurrentRow(0)
        self.reload_selected_gf()

    def reload_selected_gf(self):
        record = self._selected_gf()
        if not record:
            return
        with QSignalBlocker(self.gf_name_edit):
            self.gf_name_edit.setText(record.name)
        for key, spinbox in self.gf_fields.items():
            with QSignalBlocker(spinbox):
                spinbox.setValue(getattr(record, key))
        with QSignalBlocker(self.gf_exists_checkbox):
            self.gf_exists_checkbox.setChecked(record.exists != 0)
        with QSignalBlocker(self.gf_complete_edit):
            self.gf_complete_edit.setText(record.complete_abilities.hex())
        with QSignalBlocker(self.gf_forgotten_edit):
            self.gf_forgotten_edit.setText(record.forgotten_abilities.hex())
        for row in range(NB_GF_AP_SLOTS):
            ap_spinbox = self.ap_table.cellWidget(row, 0)
            with QSignalBlocker(ap_spinbox):
                ap_spinbox.setValue(record.aps[row])

    def _on_gf_changed(self):
        record = self._selected_gf()
        if not record:
            return
        try:
            if self.gf_name_edit.text() != record.name:
                record.name = self.gf_name_edit.text()
        except ValueError as e:
            QMessageBox.warning(self, "Trepies", str(e))
            with QSignalBlocker(self.gf_name_edit):
                self.gf_name_edit.setText(record.name)
        for key, spinbox in self.gf_fields.items():
            setattr(record, key, spinbox.value())
        record.exists = 1 if self.gf_exists_checkbox.isChecked() else 0
        for hex_edit, attribute, size in ((self.gf_complete_edit, "complete_abilities", GF_COMPLETE_ABILITIES_SIZE),
                                          (self.gf_forgotten_edit, "forgotten_abilities", 2)):
            try:
                raw = bytes.fromhex(hex_edit.text())
                if len(raw) != size:
                    raise ValueError(f"expected {size} bytes")
                setattr(record, attribute, raw)
            except ValueError:
                with QSignalBlocker(hex_edit):
                    hex_edit.setText(getattr(record, attribute).hex())
        record.aps = [self.ap_table.cellWidget(row, 0).value() for row in range(NB_GF_AP_SLOTS)]
