import os

from PyQt6.QtCore import QSize, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QListWidget,
    QSpinBox, QLineEdit, QGroupBox, QFormLayout, QTabWidget, QCheckBox, QGridLayout,
    QScrollArea, QComboBox, QTableWidget, QHeaderView,
)

from FF8GameData.gamedata import GameData
from SolomonRing.kernellookups import LookupRegistry
from Quezacotl.quezacotlmanager import (
    QuezacotlManager, CHARACTER_NAMES, ACTIVE_ABILITY_RANGE, PASSIVE_ABILITY_RANGE,
    GF_COMPATIBILITY_MIN, GF_COMPATIBILITY_MAX,
)

# Junction stat slots: (manager field, label). Each stores a magic id (0 = none); the
# potency comes from that spell's kernel junction value scaled by the quantity stocked.
JUNCTION_FIELDS = [
    ("jun_hp", "HP"), ("jun_str", "Str"), ("jun_vit", "Vit"), ("jun_mag", "Mag"),
    ("jun_spr", "Spr"), ("jun_spd", "Spd"), ("jun_eva", "Eva"), ("jun_hit", "Hit"),
    ("jun_luck", "Luck"), ("jun_ele_atk", "Elem Atk"), ("jun_status_atk", "Status Atk"),
    ("jun_ele_def1", "Elem Def 1"), ("jun_ele_def2", "Elem Def 2"),
    ("jun_ele_def3", "Elem Def 3"), ("jun_ele_def4", "Elem Def 4"),
    ("jun_status_def1", "Status Def 1"), ("jun_status_def2", "Status Def 2"),
    ("jun_status_def3", "Status Def 3"), ("jun_status_def4", "Status Def 4"),
]


class QuezacotlWidget(QWidget):
    """init.out editor (new-game save state: GF / character / config / misc / items).

    Ported from the original Quezacotl C# tool (InitWorker.cs). Option names/enums are
    pulled from the shared FF8GameData json (magic, item, gforce, kernel_lookups) so they
    stay in sync with the rest of the suite."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.manager = QuezacotlManager(self.game_data)
        self.icon_path = icon_path

        # Named option lists shared with the rest of the suite.
        self.lookups = LookupRegistry(self.game_data, game_data_folder)
        self._magic_entries = self.lookups.resolve("magic")["entries"]
        self._item_entries = self.lookups.resolve("item")["entries"]
        self._gforce_entries = self.lookups.resolve("gforce")["entries"]
        self._ability_entries = self.lookups.resolve("junctionable_ability")["entries"]
        self._status_entries = self.lookups.resolve("status_1")["entries"]
        self._party_entries = (self.lookups.resolve("weapon_character")["entries"]
                               + [{"value": 0xFF, "name": "None"}])
        # Ability slots use the shared enum, restricted to the game-validated sub-ranges,
        # with "None" (0) always available to clear a slot.
        none_ability = [self._ability_entries[0]]
        self._active_ability_entries = none_ability + [
            e for e in self._ability_entries if e["value"] in ACTIVE_ABILITY_RANGE]
        self._passive_ability_entries = none_ability + [
            e for e in self._ability_entries if e["value"] in PASSIVE_ABILITY_RANGE]

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

    # ── Small widget helpers ─────────────────────────────────────────────

    def _icon_btn(self, name, tip, slot):
        btn = QPushButton()
        btn.setIcon(QIcon(os.path.join(self.icon_path, name)))
        btn.setIconSize(QSize(30, 30))
        btn.setFixedSize(40, 40)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    def _spinbox(self, minimum, maximum, slot=None, tooltip="", step=1):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        if tooltip:
            spin.setToolTip(tooltip)
        if slot:
            spin.valueChanged.connect(slot)
        return spin

    def _enum_combo(self, entries, slot=None, tooltip=""):
        combo = QComboBox()
        for entry in entries:
            combo.addItem(f"{entry['value']}: {entry['name']}", entry["value"])
        if tooltip:
            combo.setToolTip(tooltip)
        if slot:
            combo.currentIndexChanged.connect(slot)
        return combo

    @staticmethod
    def _select_combo(combo, value):
        index = combo.findData(value)
        if index < 0:  # value outside the known list — keep it so we never lose data
            combo.addItem(f"{value}: (unknown)", value)
            index = combo.findData(value)
        combo.setCurrentIndex(index)

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
        self.gf_name_edit.setToolTip("GF name shown in menus (FF8 text, max 12 bytes)")
        self.gf_name_edit.editingFinished.connect(self._on_gf_name_changed)

        self.gf_exp_spin = self._spinbox(0, 2147483647, self._on_gf_data_changed, "Total experience earned by this GF")
        self.gf_hp_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Current HP")
        self.gf_kills_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of enemies this GF has killed")
        self.gf_kos_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of times this GF was KO'd")
        self.gf_learning_ability_spin = self._spinbox(0, 0xFF, self._on_gf_data_changed,
                                                      "Ability id this GF is currently learning (0-based, junctionable_ability)")
        self.gf_unknown1_spin = self._spinbox(0, 0xFF, self._on_gf_data_changed, "Unknown byte (offset 0x10)")
        self.gf_available_check = QCheckBox("Available")
        self.gf_available_check.setToolTip("GF has been obtained — set once the GF is junctioned/acquired at least once")
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

        # Learned abilities: one checkbox per junctionable_ability id (bit id in the GF's
        # 128-bit "complete abilities" field). Value 0 (None) is skipped.
        self.gf_ability_checks = {}
        ability_grid = QGridLayout()
        columns = 4
        ability_list = [e for e in self._ability_entries if e["value"] != 0]
        for i, entry in enumerate(ability_list):
            check = QCheckBox(entry["name"])
            check.setToolTip(f"Ability id {entry['value']} learned")
            check.stateChanged.connect(self._on_gf_ability_changed)
            self.gf_ability_checks[entry["value"]] = check
            ability_grid.addWidget(check, i // columns, i % columns)
        ability_container = QWidget()
        ability_container.setLayout(ability_grid)
        ability_scroll = QScrollArea()
        ability_scroll.setWidgetResizable(True)
        ability_scroll.setWidget(ability_container)

        # AP invested per ability slot (22 slots, in the GF's own learnable-ability order).
        self.gf_ap_spins = []
        ap_form = QFormLayout()
        for slot in range(1, 23):
            spin = self._spinbox(0, 0xFF, self._on_gf_ap_changed, f"AP invested in learnable-ability slot {slot}")
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
        for spin, value in [
            (self.gf_exp_spin, gf.exp), (self.gf_hp_spin, gf.current_hp),
            (self.gf_kills_spin, gf.kills), (self.gf_kos_spin, gf.kos),
            (self.gf_learning_ability_spin, gf.learning_ability), (self.gf_unknown1_spin, gf.unknown1),
        ]:
            with QSignalBlocker(spin):
                spin.setValue(value)
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
        self.char_hp_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Current HP")
        self.char_hp_bonus_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed,
                                               "Max-HP bonus from HP-Bonus ability (added to base max HP)")
        self.char_exp_spin = self._spinbox(0, 2147483647, self._on_character_status_changed, "Total experience")
        self.char_model_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Field/battle model id")
        self.char_weapon_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Equipped weapon id")
        self.char_kills_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of enemies killed")
        self.char_kos_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of times KO'd")
        self.char_alt_model_check = QCheckBox("Alternative Model (SeeD, Galbadian)")
        self.char_alt_model_check.setToolTip("Use the alternative outfit model (e.g. SeeD uniform, Galbadian soldier)")
        self.char_alt_model_check.stateChanged.connect(self._on_character_status_changed)
        self.char_exist_check = QCheckBox("Exists (recruited)")
        self.char_exist_check.setToolTip("Character has joined the party at least once — available in menus/party select")
        self.char_exist_check.stateChanged.connect(self._on_character_status_changed)

        self.char_str_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Strength")
        self.char_vit_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Vitality")
        self.char_mag_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Magic")
        self.char_spr_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Spirit")
        self.char_spd_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Speed")
        self.char_luck_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Luck")

        status_form = QFormLayout()
        status_form.addRow("Current HP:", self.char_hp_spin)
        status_form.addRow("Max HP bonus:", self.char_hp_bonus_spin)
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

        # Persistent status flags: only bits 0-6 of the 16-bit status_1 field are real,
        # persistable statuses (bit 7 padding; bits 8-9 are HP-derived synthetic flags the
        # game recomputes; 10-15 unused).
        self.char_status_checks = {}
        status_checks_form = QGridLayout()
        persistent_statuses = [e for e in self._status_entries if e["mask"] <= 0x40]
        for i, entry in enumerate(persistent_statuses):
            check = QCheckBox(entry["name"])
            check.stateChanged.connect(self._on_character_status_flags_changed)
            bit = entry["mask"].bit_length() - 1
            self.char_status_checks[bit] = check
            status_checks_form.addWidget(check, i // 4, i % 4)
        status_checks_group = QGroupBox("Current Status")
        status_checks_group.setToolTip("Persistent statuses (status_1 bits 0-6). Higher bits are unused or "
                                       "HP-derived and are recomputed by the game.")
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
        self.char_magic_combos = []
        self.char_magic_qty_spins = []
        for row in range(32):
            combo = self._enum_combo(self._magic_entries, self._on_character_magic_changed)
            self.char_magic_table.setCellWidget(row, 0, combo)
            self.char_magic_combos.append(combo)
            qty = self._spinbox(0, 0xFF, self._on_character_magic_changed, "Amount of this spell stocked")
            self.char_magic_table.setCellWidget(row, 1, qty)
            self.char_magic_qty_spins.append(qty)

        # Command / passive abilities (4 slots each, shared FF8Abilities enum)
        self.char_active_combos = [
            self._enum_combo(self._active_ability_entries, self._on_character_abilities_changed,
                             "Equipped command ability (Magic, GF, Draw, Item, Card…)")
            for _ in range(4)]
        self.char_passive_combos = [
            self._enum_combo(self._passive_ability_entries, self._on_character_abilities_changed,
                             "Equipped passive/junction ability (HP+20%, Str+40%…)")
            for _ in range(4)]
        abilities_form = QFormLayout()
        for i, combo in enumerate(self.char_active_combos, start=1):
            abilities_form.addRow(f"Command {i}:", combo)
        for i, combo in enumerate(self.char_passive_combos, start=1):
            abilities_form.addRow(f"Ability {i}:", combo)
        abilities_group = QGroupBox("Equipped abilities")
        abilities_group.setLayout(abilities_form)
        abilities_layout = QVBoxLayout()
        abilities_layout.addWidget(abilities_group)
        abilities_layout.addStretch(1)
        abilities_tab = QWidget()
        abilities_tab.setLayout(abilities_layout)

        # G-Forces (junctioned GFs + compatibility)
        self.char_jun_gf1_combo = self._enum_combo(self._gforce_entries, self._on_character_gf_changed,
                                                   "First junctioned GF")
        self.char_jun_gf2_combo = self._enum_combo(self._gforce_entries, self._on_character_gf_changed,
                                                   "Second junctioned GF")
        junction_form = QFormLayout()
        junction_form.addRow("Junctioned GF 1:", self.char_jun_gf1_combo)
        junction_form.addRow("Junctioned GF 2:", self.char_jun_gf2_combo)

        self.char_gf_compat_spins = []
        compat_form = QFormLayout()
        compat_tooltip = (f"Compatibility with this GF. Game range: {GF_COMPATIBILITY_MIN} (minimum / neutral) "
                          f"to {GF_COMPATIBILITY_MAX} (maximum). Higher = summons faster.")
        for entry in self._gforce_entries:
            spin = self._spinbox(0, 0xFFFF, self._on_character_gf_changed, compat_tooltip)
            self.char_gf_compat_spins.append(spin)
            compat_form.addRow(f"{entry['name']}:", spin)
        compat_container = QWidget()
        compat_container.setLayout(compat_form)
        compat_scroll = QScrollArea()
        compat_scroll.setWidgetResizable(True)
        compat_scroll.setWidget(compat_container)

        gf_layout = QVBoxLayout()
        gf_layout.addLayout(junction_form)
        compat_group = QGroupBox("Compatibility")
        compat_group_layout = QVBoxLayout()
        compat_group_layout.addWidget(compat_scroll)
        compat_group.setLayout(compat_group_layout)
        gf_layout.addWidget(compat_group)
        gf_tab = QWidget()
        gf_tab.setLayout(gf_layout)

        # Junction stat assignments (each stores a magic id)
        self.char_junction_combos = {}
        junction_stats_form = QFormLayout()
        junction_tooltip = ("Magic junctioned to this stat (0 = none). The bonus = the spell's kernel "
                            "junction value for this stat, scaled by the quantity stocked.")
        for field, label in JUNCTION_FIELDS:
            combo = self._enum_combo(self._magic_entries, self._on_character_junction_changed, junction_tooltip)
            self.char_junction_combos[field] = combo
            junction_stats_form.addRow(f"{label}:", combo)
        junction_stats_container = QWidget()
        junction_stats_container.setLayout(junction_stats_form)
        junction_stats_scroll = QScrollArea()
        junction_stats_scroll.setWidgetResizable(True)
        junction_stats_scroll.setWidget(junction_stats_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_tab, "Status")
        sub_tabs.addTab(self.char_magic_table, "Magic")
        sub_tabs.addTab(abilities_tab, "Abilities")
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
        for bit, check in self.char_status_checks.items():
            with QSignalBlocker(check):
                check.setChecked(char.has_status(bit))

        for i, magic in enumerate(char.magics):
            with QSignalBlocker(self.char_magic_combos[i]):
                self._select_combo(self.char_magic_combos[i], magic.magic_id)
            with QSignalBlocker(self.char_magic_qty_spins[i]):
                self.char_magic_qty_spins[i].setValue(magic.quantity)

        for slot, combo in enumerate(self.char_active_combos):
            with QSignalBlocker(combo):
                self._select_combo(combo, char.get_active_ability(slot))
        for slot, combo in enumerate(self.char_passive_combos):
            with QSignalBlocker(combo):
                self._select_combo(combo, char.get_passive_ability(slot))

        with QSignalBlocker(self.char_jun_gf1_combo):
            self._select_combo(self.char_jun_gf1_combo, char.jun_gf1)
        with QSignalBlocker(self.char_jun_gf2_combo):
            self._select_combo(self.char_jun_gf2_combo, char.jun_gf2)
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            with QSignalBlocker(spin):
                spin.setValue(char.get_gf_compatibility(gf_id))

        for field, combo in self.char_junction_combos.items():
            with QSignalBlocker(combo):
                self._select_combo(combo, getattr(char, field))

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
        for bit, check in self.char_status_checks.items():
            char.set_status(bit, check.isChecked())

    def _on_character_magic_changed(self):
        char = self._selected_character()
        if not char:
            return
        for i, magic in enumerate(char.magics):
            magic.magic_id = self.char_magic_combos[i].currentData()
            magic.quantity = self.char_magic_qty_spins[i].value()

    def _on_character_abilities_changed(self):
        char = self._selected_character()
        if not char:
            return
        for slot, combo in enumerate(self.char_active_combos):
            char.set_active_ability(slot, combo.currentData())
        for slot, combo in enumerate(self.char_passive_combos):
            char.set_passive_ability(slot, combo.currentData())

    def _on_character_gf_changed(self):
        char = self._selected_character()
        if not char:
            return
        char.jun_gf1 = self.char_jun_gf1_combo.currentData()
        char.jun_gf2 = self.char_jun_gf2_combo.currentData()
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            char.set_gf_compatibility(gf_id, spin.value())

    def _on_character_junction_changed(self):
        char = self._selected_character()
        if not char:
            return
        for field, combo in self.char_junction_combos.items():
            setattr(char, field, combo.currentData())

    # ── Config tab ───────────────────────────────────────────────────────

    def _build_config_tab(self):
        self.config_spins = {}
        speed_tip = "0 = slowest, 4 = fastest"
        sliders = [
            ("battle_speed", "Battle speed", 4, "Battle ATB speed. 0 = slowest, 4 = fastest (ATB gauge = 4000 x (value+1))"),
            ("battle_message_speed", "Battle message speed", 4, f"Battle message scroll speed. {speed_tip}"),
            ("field_message_speed", "Field message speed", 4, f"Field/menu message scroll speed. {speed_tip}"),
            ("volume", "Sound volume", 100, "Sound volume (0-100)"),
            ("camera", "Battle camera", 4, f"Battle camera movement style. {speed_tip}"),
        ]
        form = QFormLayout()
        for field, label, maximum, tip in sliders:
            spin = self._spinbox(0, maximum, self._on_config_changed, tip)
            self.config_spins[field] = spin
            form.addRow(f"{label}:", spin)

        self.config_flag_spin = self._spinbox(
            0, 0xFF, self._on_config_changed,
            "Controller/config bitfield.\n"
            "bit0 = battle vibration trigger\n"
            "bit4 = vibration hardware present (auto-set)\n"
            "bit5 = use custom button config\n"
            "bit6 = no controller detected (auto-set)\n"
            "bit7 = controls modified from default")
        form.addRow("Config flags (bitfield):", self.config_flag_spin)
        self.config_scan_spin = self._spinbox(0, 0xFF, self._on_config_changed,
                                             "Unused / vestigial in the PC build (no code reads it)")
        form.addRow("Scan (unused):", self.config_scan_spin)

        settings_group = QGroupBox("Settings")
        settings_group.setLayout(form)

        # Map seal (offset 7): 8 named lock bits.
        from Quezacotl.quezacotlmanager import ConfigEntry
        self.config_map_seal_checks = []
        seal_grid = QGridLayout()
        for i, (mask, name) in enumerate(ConfigEntry.MAP_SEAL_BITS):
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X} — set by story events that seal this menu action")
            check.stateChanged.connect(self._on_config_changed)
            self.config_map_seal_checks.append((mask, check))
            seal_grid.addWidget(check, i // 2, i % 2)
        seal_group = QGroupBox("Map seal (locked menu actions)")
        seal_group.setLayout(seal_grid)

        # Button remap table (offsets 8-19).
        self.config_key_spins = {}
        key_form = QFormLayout()
        for field, label in ConfigEntry.KEY_FIELDS:
            spin = self._spinbox(0, 0xFF, self._on_config_changed,
                                "Button remap slot: 1-based index of the logical button assigned to this "
                                "physical position (default = its own slot number)")
            self.config_key_spins[field] = spin
            key_form.addRow(f"{label}:", spin)
        key_group = QGroupBox("Button config (remap table)")
        key_group.setLayout(key_form)

        layout = QVBoxLayout()
        layout.addWidget(settings_group)
        layout.addWidget(seal_group)
        layout.addWidget(key_group)
        layout.addStretch(1)
        container = QWidget()
        container.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _reload_config(self):
        config = self.manager.config
        for field, spin in self.config_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(config, field))
        with QSignalBlocker(self.config_flag_spin):
            self.config_flag_spin.setValue(config.flag)
        with QSignalBlocker(self.config_scan_spin):
            self.config_scan_spin.setValue(config.scan)
        for mask, check in self.config_map_seal_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(config.map_seal & mask))
        for field, spin in self.config_key_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(config, field))

    def _on_config_changed(self):
        config = self.manager.config
        if not config:
            return
        for field, spin in self.config_spins.items():
            setattr(config, field, spin.value())
        config.flag = self.config_flag_spin.value()
        config.scan = self.config_scan_spin.value()
        seal = 0
        for mask, check in self.config_map_seal_checks:
            if check.isChecked():
                seal |= mask
        config.map_seal = seal
        for field, spin in self.config_key_spins.items():
            setattr(config, field, spin.value())

    # ── Misc tab ─────────────────────────────────────────────────────────

    def _build_misc_tab(self):
        self.misc_party_combos = [
            self._enum_combo(self._party_entries, self._on_misc_changed, f"Party slot {i} character (None = empty)")
            for i in range(1, 5)]
        self.misc_known_weapons_spins = [
            self._spinbox(0, 0xFF, self._on_misc_changed, f"Unlocked-weapon bitmask byte {i}")
            for i in range(1, 5)]
        self.misc_griever_name_edit = QLineEdit()
        self.misc_griever_name_edit.setToolTip("Griever GF name (FF8 text, max 12 bytes)")
        self.misc_griever_name_edit.editingFinished.connect(self._on_misc_griever_name_changed)
        self.misc_gil_spin = self._spinbox(0, 2147483647, self._on_misc_changed, "Party gil")
        self.misc_gil_laguna_spin = self._spinbox(0, 2147483647, self._on_misc_changed, "Laguna-squad gil")
        self.misc_weapon_laguna_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Laguna's weapon id")
        self.misc_weapon_kiros_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Kiros's weapon id")
        self.misc_weapon_ward_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Ward's weapon id")

        general_form = QFormLayout()
        for i, combo in enumerate(self.misc_party_combos, start=1):
            general_form.addRow(f"Party member {i}:", combo)
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
            ("limit_quistis1", "Quistis limit 1", "Quistis Blue Magic unlock flags (low byte)"),
            ("limit_quistis2", "Quistis limit 2", "Quistis Blue Magic unlock flags (high byte)"),
            ("limit_zell1", "Zell limit 1", "Zell Duel unlock flags (low byte)"),
            ("limit_zell2", "Zell limit 2", "Zell Duel unlock flags (high byte)"),
            ("limit_irvine", "Irvine limit", "Irvine Shot unlock flags"),
            ("limit_selphie", "Selphie limit", "Selphie Slot unlock flags"),
            ("limit_angelo_completed", "Angelo Search completed", "Angelo Search learned/completed flag"),
            ("limit_angelo_known", "Angelo Search known", "Angelo commands known flags"),
        ]
        limit_form = QFormLayout()
        for field, label, tip in limit_fields:
            spin = self._spinbox(0, 0xFF, self._on_misc_changed, tip)
            self.misc_limit_spins[field] = spin
            limit_form.addRow(f"{label}:", spin)
        self.misc_angelo_point_spins = [
            self._spinbox(0, 0xFF, self._on_misc_changed, f"Angelo Search learning progress byte {i}")
            for i in range(1, 9)]
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
        for combo, value in zip(self.misc_party_combos,
                                [misc.party_mem1, misc.party_mem2, misc.party_mem3, misc.party_mem4]):
            with QSignalBlocker(combo):
                self._select_combo(combo, value)
        for spin, value in zip(self.misc_known_weapons_spins,
                               [misc.known_weapons1, misc.known_weapons2, misc.known_weapons3, misc.known_weapons4]):
            with QSignalBlocker(spin):
                spin.setValue(value)
        with QSignalBlocker(self.misc_griever_name_edit):
            self.misc_griever_name_edit.setText(misc.griever_name)
        for spin, value in [
            (self.misc_gil_spin, misc.gil), (self.misc_gil_laguna_spin, misc.gil_laguna),
            (self.misc_weapon_laguna_spin, misc.weapon_id_laguna),
            (self.misc_weapon_kiros_spin, misc.weapon_id_kiros),
            (self.misc_weapon_ward_spin, misc.weapon_id_ward),
        ]:
            with QSignalBlocker(spin):
                spin.setValue(value)
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
         misc.party_mem3, misc.party_mem4) = (c.currentData() for c in self.misc_party_combos)
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
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(self.manager.item_entries))
        for row, entry in enumerate(self.manager.item_entries):
            combo = self._enum_combo(self._item_entries)
            self._select_combo(combo, entry.item_id)
            combo.currentIndexChanged.connect(self._make_item_id_handler(entry, combo))
            self.items_table.setCellWidget(row, 0, combo)

            qty = self._spinbox(0, 0xFF, tooltip="Amount held")
            qty.setValue(entry.quantity)
            qty.valueChanged.connect(self._make_item_qty_handler(entry))
            self.items_table.setCellWidget(row, 1, qty)

    def _make_item_id_handler(self, entry, combo):
        def handler(_index):
            entry.item_id = combo.currentData()
        return handler

    def _make_item_qty_handler(self, entry):
        def handler(value):
            entry.quantity = value
        return handler
