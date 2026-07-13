import os

from PyQt6.QtCore import QSize, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QListWidget,
    QSpinBox, QLineEdit, QGroupBox, QFormLayout, QTabWidget, QCheckBox, QGridLayout,
    QScrollArea, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
)

from FF8GameData.gamedata import GameData
from Quezacotl.quezacotlmanager import (
    QuezacotlManager, GF_ABILITY_NAMES, CHARACTER_STATUS_NAMES,
)


class QuezacotlWidget(QWidget):
    """init.out editor (new-game save state: GF / character / config / misc / items).

    Ported from the original Quezacotl C# tool (InitWorker.cs)."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.manager = QuezacotlManager(self.game_data)
        self.icon_path = icon_path

        self.setWindowTitle("Quezacotl")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'Quezacotl.ico')))

        self.file_dialog = QFileDialog()
        self.load_button = self._icon_btn('folder.png', "Open an init.out file", self.load_file)
        self.save_button = self._icon_btn('save.svg', "Save all modifications in the opened init.out (irreversible)", self.save_file)
        self.save_button.setEnabled(False)
        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gf_tab(), "G-Forces")
        self.tabs.addTab(self._build_character_tab(), "Characters")
        self.tabs.addTab(self._build_config_tab(), "Config")
        self.tabs.addTab(self._build_misc_tab(), "Misc")
        self.tabs.addTab(self._build_items_tab(), "Items")
        self.tabs.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def _icon_btn(self, name, tip, slot):
        btn = QPushButton()
        btn.setIcon(QIcon(os.path.join(self.icon_path, name)))
        btn.setIconSize(QSize(30, 30))
        btn.setFixedSize(40, 40)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    # ── File operations ────────────────────────────────────────────────

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Open init.out file",
                                                     filter="*.out", directory=os.getcwd())[0]
        if not file_name:
            return
        self.manager.load_file(file_name)
        self.file_label.setText(os.path.basename(file_name))
        self.tabs.setEnabled(True)
        self.save_button.setEnabled(True)

        with QSignalBlocker(self.gf_list):
            self.gf_list.clear()
            self.gf_list.addItems([gf.gf_name for gf in self.manager.gf_entries])
        self.gf_list.setCurrentRow(0)

        with QSignalBlocker(self.character_list):
            self.character_list.clear()
            self.character_list.addItems([c.name for c in self.manager.character_entries])
        self.character_list.setCurrentRow(0)

        self._reload_config()
        self._reload_misc()
        self._reload_items()

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    # ── GF tab ───────────────────────────────────────────────────────────

    def _build_gf_tab(self):
        self.gf_list = QListWidget()
        self.gf_list.setFixedWidth(160)
        self.gf_list.currentRowChanged.connect(self._reload_gf)

        self.gf_name_edit = QLineEdit()
        self.gf_name_edit.editingFinished.connect(self._on_gf_name_changed)

        self.gf_exp_spin = self._spinbox(0, 2147483647, self._on_gf_data_changed)
        self.gf_hp_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed)
        self.gf_kills_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed)
        self.gf_kos_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed)
        self.gf_learning_ability_spin = self._spinbox(0, 0xFF, self._on_gf_data_changed)
        self.gf_unknown1_spin = self._spinbox(0, 0xFF, self._on_gf_data_changed)
        self.gf_available_check = QCheckBox("Available")
        self.gf_available_check.stateChanged.connect(self._on_gf_data_changed)

        status_form = QFormLayout()
        status_form.addRow("Name:", self.gf_name_edit)
        status_form.addRow("EXP:", self.gf_exp_spin)
        status_form.addRow("Current HP:", self.gf_hp_spin)
        status_form.addRow("Kills:", self.gf_kills_spin)
        status_form.addRow("KOs:", self.gf_kos_spin)
        status_form.addRow("Learning ability:", self.gf_learning_ability_spin)
        status_form.addRow("Unknown:", self.gf_unknown1_spin)
        status_form.addRow(self.gf_available_check)
        status_group = QGroupBox("Status")
        status_group.setLayout(status_form)

        # Learned abilities: 120 checkboxes over a shared 128-bit (16 byte) bitfield.
        self.gf_ability_checks = {}
        ability_grid = QGridLayout()
        columns = 4
        for i, ability_id in enumerate(sorted(GF_ABILITY_NAMES)):
            check = QCheckBox(GF_ABILITY_NAMES[ability_id])
            check.stateChanged.connect(self._on_gf_ability_changed)
            self.gf_ability_checks[ability_id] = check
            ability_grid.addWidget(check, i // columns, i % columns)
        ability_container = QWidget()
        ability_container.setLayout(ability_grid)
        ability_scroll = QScrollArea()
        ability_scroll.setWidgetResizable(True)
        ability_scroll.setWidget(ability_container)

        # AP invested per ability slot (22 slots, never named by the original tool).
        self.gf_ap_spins = []
        ap_form = QFormLayout()
        for slot in range(1, 23):
            spin = self._spinbox(0, 0xFF, self._on_gf_ap_changed)
            self.gf_ap_spins.append(spin)
            ap_form.addRow(f"Ability {slot}:", spin)
        ap_container = QWidget()
        ap_container.setLayout(ap_form)
        ap_scroll = QScrollArea()
        ap_scroll.setWidgetResizable(True)
        ap_scroll.setWidget(ap_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_group, "Status")
        sub_tabs.addTab(ability_scroll, "Learned Abilities")
        sub_tabs.addTab(ap_scroll, "AP")

        layout = QHBoxLayout()
        layout.addWidget(self.gf_list)
        layout.addWidget(sub_tabs, 1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def _selected_gf(self):
        index = self.gf_list.currentRow()
        if self.manager.gf_entries and 0 <= index < len(self.manager.gf_entries):
            return self.manager.gf_entries[index]
        return None

    def _reload_gf(self):
        gf = self._selected_gf()
        if not gf:
            return
        with QSignalBlocker(self.gf_name_edit):
            self.gf_name_edit.setText(gf.name)
        with QSignalBlocker(self.gf_exp_spin):
            self.gf_exp_spin.setValue(gf.exp)
        with QSignalBlocker(self.gf_hp_spin):
            self.gf_hp_spin.setValue(gf.current_hp)
        with QSignalBlocker(self.gf_kills_spin):
            self.gf_kills_spin.setValue(gf.kills)
        with QSignalBlocker(self.gf_kos_spin):
            self.gf_kos_spin.setValue(gf.kos)
        with QSignalBlocker(self.gf_learning_ability_spin):
            self.gf_learning_ability_spin.setValue(gf.learning_ability)
        with QSignalBlocker(self.gf_unknown1_spin):
            self.gf_unknown1_spin.setValue(gf.unknown1)
        with QSignalBlocker(self.gf_available_check):
            self.gf_available_check.setChecked(gf.available)
        for ability_id, check in self.gf_ability_checks.items():
            with QSignalBlocker(check):
                check.setChecked(gf.has_ability(ability_id))
        for slot, spin in enumerate(self.gf_ap_spins, start=1):
            with QSignalBlocker(spin):
                spin.setValue(gf.get_ap_ability(slot))

    def _on_gf_name_changed(self):
        gf = self._selected_gf()
        if gf:
            gf.name = self.gf_name_edit.text()

    def _on_gf_data_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        gf.exp = self.gf_exp_spin.value()
        gf.current_hp = self.gf_hp_spin.value()
        gf.kills = self.gf_kills_spin.value()
        gf.kos = self.gf_kos_spin.value()
        gf.learning_ability = self.gf_learning_ability_spin.value()
        gf.unknown1 = self.gf_unknown1_spin.value()
        gf.available = self.gf_available_check.isChecked()

    def _on_gf_ability_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for ability_id, check in self.gf_ability_checks.items():
            gf.set_ability(ability_id, check.isChecked())

    def _on_gf_ap_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for slot, spin in enumerate(self.gf_ap_spins, start=1):
            gf.set_ap_ability(slot, spin.value())

    # ── Character tab ────────────────────────────────────────────────────

    def _build_character_tab(self):
        self.character_list = QListWidget()
        self.character_list.setFixedWidth(160)
        self.character_list.currentRowChanged.connect(self._reload_character)

        # Status
        self.char_hp_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed)
        self.char_hp_bonus_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed)
        self.char_exp_spin = self._spinbox(0, 2147483647, self._on_character_status_changed)
        self.char_model_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_weapon_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_kills_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed)
        self.char_kos_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed)
        self.char_alt_model_check = QCheckBox("Alternative Model (SeeD, Galbadian)")
        self.char_alt_model_check.stateChanged.connect(self._on_character_status_changed)
        self.char_exist_check = QCheckBox("Exists")
        self.char_exist_check.stateChanged.connect(self._on_character_status_changed)

        self.char_str_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_vit_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_mag_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_spr_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_spd_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)
        self.char_luck_spin = self._spinbox(0, 0xFF, self._on_character_status_changed)

        status_form = QFormLayout()
        status_form.addRow("Current HP:", self.char_hp_spin)
        status_form.addRow("HP Bonus:", self.char_hp_bonus_spin)
        status_form.addRow("EXP:", self.char_exp_spin)
        status_form.addRow("Model:", self.char_model_spin)
        status_form.addRow("Weapon:", self.char_weapon_spin)
        status_form.addRow("Kills:", self.char_kills_spin)
        status_form.addRow("KOs:", self.char_kos_spin)
        status_form.addRow(self.char_alt_model_check)
        status_form.addRow(self.char_exist_check)
        stats_form = QFormLayout()
        stats_form.addRow("Str:", self.char_str_spin)
        stats_form.addRow("Vit:", self.char_vit_spin)
        stats_form.addRow("Mag:", self.char_mag_spin)
        stats_form.addRow("Spr:", self.char_spr_spin)
        stats_form.addRow("Spd:", self.char_spd_spin)
        stats_form.addRow("Luck:", self.char_luck_spin)
        status_group = QGroupBox("Status")
        status_layout = QHBoxLayout()
        status_layout.addLayout(status_form)
        status_layout.addLayout(stats_form)
        status_group.setLayout(status_layout)

        self.char_status_checks = []
        status_checks_form = QGridLayout()
        for i, name in enumerate(CHARACTER_STATUS_NAMES):
            check = QCheckBox(name)
            check.stateChanged.connect(self._on_character_status_flags_changed)
            self.char_status_checks.append(check)
            status_checks_form.addWidget(check, i // 4, i % 4)
        status_checks_group = QGroupBox("Current Status")
        status_checks_group.setLayout(status_checks_form)

        status_tab_layout = QVBoxLayout()
        status_tab_layout.addWidget(status_group)
        status_tab_layout.addWidget(status_checks_group)
        status_tab_layout.addStretch(1)
        status_tab = QWidget()
        status_tab.setLayout(status_tab_layout)

        # Magic
        self.char_magic_table = QTableWidget(32, 2)
        self.char_magic_table.setHorizontalHeaderLabels(["Magic", "Quantity"])
        self.char_magic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        magic_names = [m["name"] for m in self.game_data.magic_data_json.get("magic", [])] if self.game_data.magic_data_json else []
        self.char_magic_combos = []
        self.char_magic_qty_spins = []
        for row in range(32):
            combo = QComboBox()
            combo.addItems(magic_names)
            combo.currentIndexChanged.connect(self._on_character_magic_changed)
            self.char_magic_table.setCellWidget(row, 0, combo)
            self.char_magic_combos.append(combo)
            qty = self._spinbox(0, 0xFF, self._on_character_magic_changed)
            self.char_magic_table.setCellWidget(row, 1, qty)
            self.char_magic_qty_spins.append(qty)

        # Commands / Abilities
        self.char_command_spins = [self._spinbox(0, 0xFF, self._on_character_commands_changed) for _ in range(3)]
        self.char_ability_spins = [self._spinbox(0, 0xFF, self._on_character_commands_changed) for _ in range(4)]
        commands_form = QFormLayout()
        for i, spin in enumerate(self.char_command_spins, start=1):
            commands_form.addRow(f"Command {i}:", spin)
        for i, spin in enumerate(self.char_ability_spins, start=1):
            commands_form.addRow(f"Ability {i}:", spin)
        commands_group = QGroupBox("Commands / Abilities")
        commands_group.setLayout(commands_form)
        commands_layout = QVBoxLayout()
        commands_layout.addWidget(commands_group)
        commands_layout.addStretch(1)
        commands_tab = QWidget()
        commands_tab.setLayout(commands_layout)

        # G-Forces (junction + compatibility)
        gf_names = [gf["name"] for gf in self.game_data.gforce_data_json.get("gforce", [])] if self.game_data.gforce_data_json else []
        self.char_jun_gf1_combo = QComboBox()
        self.char_jun_gf1_combo.addItems(gf_names)
        self.char_jun_gf1_combo.currentIndexChanged.connect(self._on_character_gf_changed)
        self.char_jun_gf2_combo = QComboBox()
        self.char_jun_gf2_combo.addItems(gf_names)
        self.char_jun_gf2_combo.currentIndexChanged.connect(self._on_character_gf_changed)
        junction_form = QFormLayout()
        junction_form.addRow("Junctioned GF 1:", self.char_jun_gf1_combo)
        junction_form.addRow("Junctioned GF 2:", self.char_jun_gf2_combo)

        self.char_gf_compat_spins = []
        compat_form = QFormLayout()
        for i, gf_name in enumerate(gf_names):
            spin = self._spinbox(0, 0xFFFF, self._on_character_gf_changed)
            self.char_gf_compat_spins.append(spin)
            compat_form.addRow(f"{gf_name}:", spin)

        gf_layout = QVBoxLayout()
        gf_layout.addLayout(junction_form)
        compat_group = QGroupBox("Compatibility")
        compat_group.setLayout(compat_form)
        gf_layout.addWidget(compat_group)
        gf_layout.addStretch(1)
        gf_tab = QWidget()
        gf_tab.setLayout(gf_layout)

        # Junction stats (from GFs)
        self.char_junction_spins = {}
        junction_stat_fields = [
            ("jun_hp", "HP"), ("jun_str", "Str"), ("jun_vit", "Vit"), ("jun_mag", "Mag"),
            ("jun_spr", "Spr"), ("jun_spd", "Spd"), ("jun_eva", "Eva"), ("jun_hit", "Hit"),
            ("jun_luck", "Luck"), ("jun_ele_atk", "Elem Atk"), ("jun_status_atk", "Status Atk"),
            ("jun_ele_def1", "Elem Def 1"), ("jun_ele_def2", "Elem Def 2"),
            ("jun_ele_def3", "Elem Def 3"), ("jun_ele_def4", "Elem Def 4"),
            ("jun_status_def1", "Status Def 1"), ("jun_status_def2", "Status Def 2"),
            ("jun_status_def3", "Status Def 3"), ("jun_status_def4", "Status Def 4"),
        ]
        junction_stats_form = QFormLayout()
        for field, label in junction_stat_fields:
            spin = self._spinbox(0, 0xFF, self._on_character_junction_stats_changed)
            self.char_junction_spins[field] = spin
            junction_stats_form.addRow(f"{label}:", spin)
        junction_stats_container = QWidget()
        junction_stats_container.setLayout(junction_stats_form)
        junction_stats_scroll = QScrollArea()
        junction_stats_scroll.setWidgetResizable(True)
        junction_stats_scroll.setWidget(junction_stats_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_tab, "Status")
        sub_tabs.addTab(self.char_magic_table, "Magic")
        sub_tabs.addTab(commands_tab, "Commands")
        sub_tabs.addTab(gf_tab, "G-Forces")
        sub_tabs.addTab(junction_stats_scroll, "Junction")

        layout = QHBoxLayout()
        layout.addWidget(self.character_list)
        layout.addWidget(sub_tabs, 1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def _selected_character(self):
        index = self.character_list.currentRow()
        if self.manager.character_entries and 0 <= index < len(self.manager.character_entries):
            return self.manager.character_entries[index]
        return None

    def _reload_character(self):
        char = self._selected_character()
        if not char:
            return
        for spin, value in [
            (self.char_hp_spin, char.current_hp), (self.char_hp_bonus_spin, char.hp_bonus),
            (self.char_exp_spin, char.exp), (self.char_model_spin, char.model_id),
            (self.char_weapon_spin, char.weapon_id), (self.char_kills_spin, char.kills),
            (self.char_kos_spin, char.kos), (self.char_str_spin, char.str_stat),
            (self.char_vit_spin, char.vit), (self.char_mag_spin, char.mag),
            (self.char_spr_spin, char.spr), (self.char_spd_spin, char.spd),
            (self.char_luck_spin, char.luck),
        ]:
            with QSignalBlocker(spin):
                spin.setValue(value)
        with QSignalBlocker(self.char_alt_model_check):
            self.char_alt_model_check.setChecked(char.alt_model)
        with QSignalBlocker(self.char_exist_check):
            self.char_exist_check.setChecked(char.exist)
        for i, check in enumerate(self.char_status_checks):
            with QSignalBlocker(check):
                check.setChecked(char.has_status(i))

        for i, magic in enumerate(char.magics):
            with QSignalBlocker(self.char_magic_combos[i]):
                self.char_magic_combos[i].setCurrentIndex(magic.magic_id)
            with QSignalBlocker(self.char_magic_qty_spins[i]):
                self.char_magic_qty_spins[i].setValue(magic.quantity)

        for spin, value in zip(self.char_command_spins, [char.command1, char.command2, char.command3]):
            with QSignalBlocker(spin):
                spin.setValue(value)
        for spin, value in zip(self.char_ability_spins, [char.ability1, char.ability2, char.ability3, char.ability4]):
            with QSignalBlocker(spin):
                spin.setValue(value)

        with QSignalBlocker(self.char_jun_gf1_combo):
            self.char_jun_gf1_combo.setCurrentIndex(char.jun_gf1)
        with QSignalBlocker(self.char_jun_gf2_combo):
            self.char_jun_gf2_combo.setCurrentIndex(char.jun_gf2)
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            with QSignalBlocker(spin):
                spin.setValue(char.get_gf_compatibility(gf_id))

        for field, spin in self.char_junction_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(char, field))

    def _on_character_status_changed(self):
        char = self._selected_character()
        if not char:
            return
        char.current_hp = self.char_hp_spin.value()
        char.hp_bonus = self.char_hp_bonus_spin.value()
        char.exp = self.char_exp_spin.value()
        char.model_id = self.char_model_spin.value()
        char.weapon_id = self.char_weapon_spin.value()
        char.kills = self.char_kills_spin.value()
        char.kos = self.char_kos_spin.value()
        char.str_stat = self.char_str_spin.value()
        char.vit = self.char_vit_spin.value()
        char.mag = self.char_mag_spin.value()
        char.spr = self.char_spr_spin.value()
        char.spd = self.char_spd_spin.value()
        char.luck = self.char_luck_spin.value()
        char.alt_model = self.char_alt_model_check.isChecked()
        char.exist = self.char_exist_check.isChecked()

    def _on_character_status_flags_changed(self):
        char = self._selected_character()
        if not char:
            return
        for i, check in enumerate(self.char_status_checks):
            char.set_status(i, check.isChecked())

    def _on_character_magic_changed(self):
        char = self._selected_character()
        if not char:
            return
        for i, magic in enumerate(char.magics):
            magic.magic_id = self.char_magic_combos[i].currentIndex()
            magic.quantity = self.char_magic_qty_spins[i].value()

    def _on_character_commands_changed(self):
        char = self._selected_character()
        if not char:
            return
        char.command1, char.command2, char.command3 = (s.value() for s in self.char_command_spins)
        char.ability1, char.ability2, char.ability3, char.ability4 = (s.value() for s in self.char_ability_spins)

    def _on_character_gf_changed(self):
        char = self._selected_character()
        if not char:
            return
        char.jun_gf1 = self.char_jun_gf1_combo.currentIndex()
        char.jun_gf2 = self.char_jun_gf2_combo.currentIndex()
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            char.set_gf_compatibility(gf_id, spin.value())

    def _on_character_junction_stats_changed(self):
        char = self._selected_character()
        if not char:
            return
        for field, spin in self.char_junction_spins.items():
            setattr(char, field, spin.value())

    # ── Config tab ───────────────────────────────────────────────────────

    def _build_config_tab(self):
        self.config_spins = {}
        fields = [
            "battle_speed", "battle_message", "field_message", "volume", "camera",
            "key_unk1", "key_escape", "key_pov", "key_window", "key_trigger", "key_cancel",
            "key_menu", "key_talk", "key_triple_triad", "key_select", "key_unk2", "key_unk3", "key_start",
        ]
        form = QFormLayout()
        for field in fields:
            spin = self._spinbox(0, 0xFF, self._on_config_changed)
            self.config_spins[field] = spin
            form.addRow(f"{field.replace('_', ' ').title()}:", spin)

        self.config_flag_check = QCheckBox("Flag")
        self.config_flag_check.stateChanged.connect(self._on_config_changed)
        self.config_scan_check = QCheckBox("Scan")
        self.config_scan_check.stateChanged.connect(self._on_config_changed)
        form.addRow(self.config_flag_check)
        form.addRow(self.config_scan_check)

        container = QWidget()
        container.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _reload_config(self):
        config = self.manager.config
        for field, spin in self.config_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(config, field))
        with QSignalBlocker(self.config_flag_check):
            self.config_flag_check.setChecked(bool(config.flag))
        with QSignalBlocker(self.config_scan_check):
            self.config_scan_check.setChecked(bool(config.scan))

    def _on_config_changed(self):
        config = self.manager.config
        if not config:
            return
        for field, spin in self.config_spins.items():
            setattr(config, field, spin.value())
        config.flag = 1 if self.config_flag_check.isChecked() else 0
        config.scan = 1 if self.config_scan_check.isChecked() else 0

    # ── Misc tab ─────────────────────────────────────────────────────────

    def _build_misc_tab(self):
        self.misc_party_spins = [self._spinbox(0, 0xFF, self._on_misc_changed) for _ in range(4)]
        self.misc_known_weapons_spins = [self._spinbox(0, 0xFF, self._on_misc_changed) for _ in range(4)]
        self.misc_griever_name_edit = QLineEdit()
        self.misc_griever_name_edit.editingFinished.connect(self._on_misc_griever_name_changed)
        self.misc_gil_spin = self._spinbox(0, 2147483647, self._on_misc_changed)
        self.misc_gil_laguna_spin = self._spinbox(0, 2147483647, self._on_misc_changed)
        self.misc_weapon_laguna_spin = self._spinbox(0, 0xFF, self._on_misc_changed)
        self.misc_weapon_kiros_spin = self._spinbox(0, 0xFF, self._on_misc_changed)
        self.misc_weapon_ward_spin = self._spinbox(0, 0xFF, self._on_misc_changed)

        general_form = QFormLayout()
        for i, spin in enumerate(self.misc_party_spins, start=1):
            general_form.addRow(f"Party member {i}:", spin)
        for i, spin in enumerate(self.misc_known_weapons_spins, start=1):
            general_form.addRow(f"Known weapons {i}:", spin)
        general_form.addRow("Griever name:", self.misc_griever_name_edit)
        general_form.addRow("Gil:", self.misc_gil_spin)
        general_form.addRow("Gil (Laguna squad):", self.misc_gil_laguna_spin)
        general_form.addRow("Laguna weapon:", self.misc_weapon_laguna_spin)
        general_form.addRow("Kiros weapon:", self.misc_weapon_kiros_spin)
        general_form.addRow("Ward weapon:", self.misc_weapon_ward_spin)
        general_group = QGroupBox("General")
        general_group.setLayout(general_form)

        self.misc_limit_spins = {}
        limit_fields = [
            ("limit_quistis1", "Quistis limit 1"), ("limit_quistis2", "Quistis limit 2"),
            ("limit_zell1", "Zell limit 1"), ("limit_zell2", "Zell limit 2"),
            ("limit_irvine", "Irvine limit"), ("limit_selphie", "Selphie limit"),
            ("limit_angelo_completed", "Angelo Search completed"),
            ("limit_angelo_known", "Angelo Search known"),
        ]
        limit_form = QFormLayout()
        for field, label in limit_fields:
            spin = self._spinbox(0, 0xFF, self._on_misc_changed)
            self.misc_limit_spins[field] = spin
            limit_form.addRow(f"{label}:", spin)
        self.misc_angelo_point_spins = [self._spinbox(0, 0xFF, self._on_misc_changed) for _ in range(8)]
        for i, spin in enumerate(self.misc_angelo_point_spins, start=1):
            limit_form.addRow(f"Angelo Search point {i}:", spin)
        limit_group = QGroupBox("Limit Breaks")
        limit_group.setLayout(limit_form)

        layout = QVBoxLayout()
        layout.addWidget(general_group)
        layout.addWidget(limit_group)
        layout.addStretch(1)
        container = QWidget()
        container.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _reload_misc(self):
        misc = self.manager.misc
        for spin, value in zip(self.misc_party_spins,
                               [misc.party_mem1, misc.party_mem2, misc.party_mem3, misc.party_mem4]):
            with QSignalBlocker(spin):
                spin.setValue(value)
        for spin, value in zip(self.misc_known_weapons_spins,
                               [misc.known_weapons1, misc.known_weapons2, misc.known_weapons3, misc.known_weapons4]):
            with QSignalBlocker(spin):
                spin.setValue(value)
        with QSignalBlocker(self.misc_griever_name_edit):
            self.misc_griever_name_edit.setText(misc.griever_name)
        with QSignalBlocker(self.misc_gil_spin):
            self.misc_gil_spin.setValue(misc.gil)
        with QSignalBlocker(self.misc_gil_laguna_spin):
            self.misc_gil_laguna_spin.setValue(misc.gil_laguna)
        with QSignalBlocker(self.misc_weapon_laguna_spin):
            self.misc_weapon_laguna_spin.setValue(misc.weapon_id_laguna)
        with QSignalBlocker(self.misc_weapon_kiros_spin):
            self.misc_weapon_kiros_spin.setValue(misc.weapon_id_kiros)
        with QSignalBlocker(self.misc_weapon_ward_spin):
            self.misc_weapon_ward_spin.setValue(misc.weapon_id_ward)
        for field, spin in self.misc_limit_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(misc, field))
        for i, spin in enumerate(self.misc_angelo_point_spins):
            with QSignalBlocker(spin):
                spin.setValue(misc.get_angelo_point(i))

    def _on_misc_griever_name_changed(self):
        self.manager.misc.griever_name = self.misc_griever_name_edit.text()

    def _on_misc_changed(self):
        misc = self.manager.misc
        if not misc:
            return
        (misc.party_mem1, misc.party_mem2,
         misc.party_mem3, misc.party_mem4) = (s.value() for s in self.misc_party_spins)
        (misc.known_weapons1, misc.known_weapons2,
         misc.known_weapons3, misc.known_weapons4) = (s.value() for s in self.misc_known_weapons_spins)
        misc.gil = self.misc_gil_spin.value()
        misc.gil_laguna = self.misc_gil_laguna_spin.value()
        misc.weapon_id_laguna = self.misc_weapon_laguna_spin.value()
        misc.weapon_id_kiros = self.misc_weapon_kiros_spin.value()
        misc.weapon_id_ward = self.misc_weapon_ward_spin.value()
        for field, spin in self.misc_limit_spins.items():
            setattr(misc, field, spin.value())
        for i, spin in enumerate(self.misc_angelo_point_spins):
            misc.set_angelo_point(i, spin.value())

    # ── Items tab ────────────────────────────────────────────────────────

    def _build_items_tab(self):
        self.items_table = QTableWidget(0, 2)
        self.items_table.setHorizontalHeaderLabels(["Item", "Quantity"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return self.items_table

    def _reload_items(self):
        item_names = [item["name"] for item in self.game_data.item_data_json.get("items", [])]
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(self.manager.item_entries))
        for row, entry in enumerate(self.manager.item_entries):
            combo = QComboBox()
            combo.addItems(item_names)
            combo.setCurrentIndex(entry.item_id)
            combo.currentIndexChanged.connect(self._make_item_id_handler(entry))
            self.items_table.setCellWidget(row, 0, combo)

            qty = self._spinbox(0, 0xFF, None)
            qty.setValue(entry.quantity)
            qty.valueChanged.connect(self._make_item_qty_handler(entry))
            self.items_table.setCellWidget(row, 1, qty)

    def _make_item_id_handler(self, entry):
        def handler(index):
            entry.item_id = index
        return handler

    def _make_item_qty_handler(self, entry):
        def handler(value):
            entry.quantity = value
        return handler

    # ── Utilities ────────────────────────────────────────────────────────

    def _spinbox(self, minimum, maximum, slot):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        if slot:
            spin.valueChanged.connect(slot)
        return spin
