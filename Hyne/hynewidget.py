import json
import os

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QSpinBox, QLineEdit, QGroupBox, QFormLayout, QTabWidget, QCheckBox, QGridLayout,
    QScrollArea, QComboBox, QTableWidget, QHeaderView, QAbstractSpinBox, QSizePolicy,
    QMessageBox,
)

# Tooltip shown on the read-only (greyed) padding fields.
RESERVED_TOOLTIP = ("Read-only: this byte has no meaning in the game (confirmed unused / padding — "
                    "no code reads it). It is shown for completeness and preserved on save, but "
                    "editing it would have no effect.")

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from SolomonRing.kernellookups import LookupRegistry
from Quezacotl.quezacotlmanager import (
    CHARACTER_NAMES, ACTIVE_ABILITY_RANGE, PASSIVE_ABILITY_RANGE,
    GF_COMPATIBILITY_MIN, GF_COMPATIBILITY_MAX,
)
from Hyne.hynemanager import HyneManager

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


class HyneWidget(QWidget):
    """.ff8 Steam save-file editor, native to this project's PyQt6 toolset (replaces the
    need for the third-party Hyne.exe GUI tool in ExternalTools/Hyne, which shares the name).

    Same GF / character / config / misc / items data as Quezacotl (init.out editor) — a
    save's savemap+80 region is byte-identical in layout to init.out, so this widget reuses
    Quezacotl's exact entry classes via HyneManager, which only differs in how it reads and
    writes the outer .ff8 envelope (LZSS compression + CRC16 checksum + a mandatory .bak
    backup before every save)."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry

        self.game_data = GameData(game_data_folder)
        self.manager = HyneManager(self.game_data)
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

        json_dir = os.path.join(game_data_folder, "Resources", "json")

        def _load_json(name):
            with open(os.path.join(json_dir, name), encoding="utf-8") as json_file:
                return json.load(json_file)

        # Button-remap action list (dedicated json — the config bytes store a logical action id).
        button_config = _load_json("button_config.json")
        self._button_action_entries = [{"value": a["id"], "name": a["name"]} for a in button_config["action"]]
        self._button_action_notes = {a["id"]: a.get("note", "") for a in button_config["action"]}

        # Weapon names for the "unlocked weapons" bitmask: bit i = kernel weapon id i (1:1).
        # Only bits 0-27 (the 28 junk-shop-upgradeable party weapons) are used by the game.
        weapon_data = _load_json("kernel_bin_data.json")["weapon_data"]
        self._weapon_bits = [(w["id"], f"{w['weapon_name']} ({w['character']})")
                             for w in weapon_data if w["id"] < 28]

        # Limit-break unlock bitfields. Irvine's shot names come from item.json (ids 101-108).
        limit_data = _load_json("limit_break.json")
        item_name = {e["value"]: e["name"] for e in self._item_entries}
        irvine_shot = [{"bit": i, "name": item_name.get(101 + i, f"Ammo {101 + i}")} for i in range(8)]
        self._limit_bitfield_defs = [
            ("limit_quistis", "Quistis — Blue Magic", limit_data["quistis_blue_magic"],
             "Learned Blue Magic (Quistis limit break) — 16-bit mask"),
            ("limit_zell", "Zell — Duel", limit_data["zell_duel"],
             "Known Duel moves (Zell limit break)"),
            ("limit_irvine", "Irvine — Shot", irvine_shot,
             "Unlocked Shot ammo types (Irvine limit break); each also usable if you carry that ammo"),
            ("limit_selphie", "Selphie — Slot", limit_data["selphie_slot"],
             "Unlocked Slot special spells (Selphie limit break)"),
            ("limit_angelo_known", "Angelo — Known", limit_data["angelo_command"],
             "Angelo commands known / in learning"),
            ("limit_angelo_completed", "Angelo — Completed", limit_data["angelo_command"],
             "Angelo commands fully learned"),
        ]

        self.setWindowTitle("Hyne")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # Open/Save run from the shared header toolbar. A .ff8 save has no fixed FF8 name (each is
        # slotX_saveYY.ff8, user save names…), so the binding is a single-select wildcard, like
        # Joker's *.sp2. Save writes straight back to the loaded file (a .bak backup is made first
        # by HyneManager). It is the only editor of .ff8 saves, so nothing else shares this key.
        self.ff8_binding = FileBinding("save file (.ff8)", file_registry, load_callback=self.load_file,
                                       save_callback=self.save_file, file_filter="*.ff8")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gf_tab(), "G-Forces")
        self.tabs.addTab(self._build_character_tab(), "Characters")
        self.tabs.addTab(self._build_config_tab(), "Config")
        self.tabs.addTab(self._build_misc_tab(), "Misc")
        self.tabs.addTab(self._build_items_tab(), "Items")
        self.tabs.setTabToolTip(0, "The 16 Guardian Forces: stats, learned abilities and AP")
        self.tabs.setTabToolTip(1, "The 8 playable characters: stats, magic, junctions and abilities")
        self.tabs.setTabToolTip(2, "Saved game configuration (speeds, volume, controls, map seal)")
        self.tabs.setTabToolTip(3, "Party, gil, weapons, Griever name and limit-break unlocks")
        self.tabs.setTabToolTip(4, "Current inventory (item id + quantity per slot)")
        self.tabs.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.ff8_binding.load_opened_file()  # pick up a .ff8 another instance already opened

    def file_bindings(self):
        """The file the shared header toolbar opens/saves for this tool: the .ff8 save."""
        return [self.ff8_binding]

    # ── Small widget helpers ─────────────────────────────────────────────

    @staticmethod
    def _compact_spin(spin):
        """Cap a spinbox width to just fit its largest value, so it doesn't stretch."""
        digits = max(len(str(spin.maximum())), 2)
        spin.setMaximumWidth(spin.fontMetrics().horizontalAdvance("9" * digits) + 36)

    @staticmethod
    def _compact_line(line_edit, chars=14):
        line_edit.setMaximumWidth(line_edit.fontMetrics().horizontalAdvance("W" * chars))

    def _spinbox(self, minimum, maximum, slot=None, tooltip="", step=1):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        self._compact_spin(spin)
        if tooltip:
            spin.setToolTip(tooltip)
        if slot:
            spin.valueChanged.connect(slot)
        return spin

    def _enum_combo(self, entries, slot=None, tooltip="", adjust_size=False):
        combo = QComboBox()
        for entry in entries:
            combo.addItem(f"{entry['value']}: {entry['name']}", entry["value"])
        # Size to the widest entry and don't stretch to fill the row/cell.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if tooltip:
            combo.setToolTip(tooltip)
        if slot:
            combo.currentIndexChanged.connect(slot)
        return combo

    @staticmethod
    def _configure_list_table(table):
        """Size an (item/magic, quantity) table to its content so the quantity column sits
        right next to the name column instead of the name stretching across the pane."""
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def _select_combo(combo, value):
        index = combo.findData(value)
        if index < 0:  # value outside the known list — keep it so we never lose data
            combo.addItem(f"{value}: (unknown)", value)
            index = combo.findData(value)
        combo.setCurrentIndex(index)

    def _readonly_spin(self, tooltip, maximum=0xFF):
        """A greyed, non-editable spinbox for showing a byte the tool won't let you change.
        Kept enabled (read-only) so the hover tooltip still works."""
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.setReadOnly(True)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._compact_spin(spin)
        spin.setToolTip(tooltip)
        spin.setStyleSheet("color: gray;")
        return spin

    @staticmethod
    def _grey_label(text, tooltip):
        label = QLabel(text)
        label.setToolTip(tooltip)
        label.setStyleSheet("color: gray;")
        return label

    def _reserved_group(self, rows):
        """Build a 'Reserved (read-only)' group from rows of (label, offset_tooltip). Returns
        (group, [(spin, ...)]) so the caller can populate values on reload."""
        form = QFormLayout()
        spins = []
        for label_text in rows:
            spin = self._readonly_spin(RESERVED_TOOLTIP)
            form.addRow(self._grey_label(label_text, RESERVED_TOOLTIP), spin)
            spins.append(spin)
        group = QGroupBox("Reserved (read-only)")
        group.setToolTip("Bytes with no game meaning — shown for completeness, not editable")
        group.setLayout(form)
        return group, spins

    def _left_column_scroll(self, group_widgets):
        """Stack groups vertically, hugged to the left with a stretch filling the right, inside
        a scroll area — so the content stays at its natural width instead of spreading."""
        column = QVBoxLayout()
        for widget in group_widgets:
            column.addWidget(widget)
        column.addStretch(1)
        column_widget = QWidget()
        column_widget.setLayout(column)
        column_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(column_widget)
        outer.addStretch(1)
        container = QWidget()
        container.setLayout(outer)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _bitfield_group(self, title, tooltip, entries, changed_slot, columns=2):
        """Build a QGroupBox of checkboxes over a bitfield. Returns (group, [(bit, checkbox)])."""
        group = QGroupBox(title)
        group.setToolTip(tooltip)
        grid = QGridLayout()
        checks = []
        for i, entry in enumerate(entries):
            bit = entry["bit"]
            check = QCheckBox(entry["name"])
            check.setToolTip(f"Bit {bit}")
            check.stateChanged.connect(changed_slot)
            checks.append((bit, check))
            grid.addWidget(check, i // columns, i % columns)
        group.setLayout(grid)
        return group, checks

    # ── File operations ────────────────────────────────────────────────

    def load_file(self, file_name):
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Hyne", f"Not a valid .ff8 save file:\n{error}")
            return
        self.tabs.setEnabled(True)

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
        self._compact_line(self.gf_name_edit)
        self.gf_name_edit.editingFinished.connect(self._on_gf_name_changed)

        self.gf_exp_spin = self._spinbox(0, 2147483647, self._on_gf_data_changed, "Total experience earned by this GF")
        self.gf_hp_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Current HP")
        self.gf_kills_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of enemies this GF has killed")
        self.gf_kos_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of times this GF was KO'd")
        self.gf_learning_ability_combo = self._enum_combo(
            self._ability_entries, self._on_gf_data_changed,
            "Ability the GF is currently set to learn — earned AP is applied to it. This is an "
            "ability id, not an AP amount; the AP invested per ability is on the AP tab.")
        self.gf_available_check = QCheckBox("Available")
        self.gf_available_check.setToolTip("GF has been obtained — set once the GF is junctioned/acquired at least once")
        self.gf_available_check.stateChanged.connect(self._on_gf_data_changed)

        status_form = QFormLayout()
        status_form.addRow("Name:", self.gf_name_edit)
        status_form.addRow("EXP:", self.gf_exp_spin)
        status_form.addRow("Current HP:", self.gf_hp_spin)
        status_form.addRow("Kills:", self.gf_kills_spin)
        status_form.addRow("KOs:", self.gf_kos_spin)
        status_form.addRow("Learning:", self.gf_learning_ability_combo)
        status_form.addRow(self.gf_available_check)
        status_group = QGroupBox("Status")
        status_group.setToolTip("Core stats and state of the selected GF")
        status_group.setLayout(status_form)

        gf_reserved_group, gf_reserved_spins = self._reserved_group(["Unused (0x10):"])
        self.gf_unused_spin = gf_reserved_spins[0]
        status_tab_container = QWidget()
        status_tab_layout = QVBoxLayout()
        status_tab_layout.setContentsMargins(0, 0, 0, 0)
        status_tab_layout.addWidget(status_group)
        status_tab_layout.addWidget(gf_reserved_group)
        status_tab_layout.addStretch(1)
        status_tab_container.setLayout(status_tab_layout)

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

        # AP invested per ability slot. The slots are NOT global ability ids: slot N is the
        # N-th entry in *this GF's* learnable-ability list, whose id/AP-cost order is defined
        # in kernel.bin (Junctionable GFs section) and is not part of the savemap, so the slots
        # can only be numbered here, not named.
        self.gf_ap_spins = []
        ap_form = QFormLayout()
        ap_note = QLabel("Slot N = AP invested in this GF's N-th learnable ability (order set by kernel.bin).")
        ap_note.setWordWrap(True)
        ap_form.addRow(ap_note)
        for slot in range(1, 23):
            spin = self._spinbox(0, 0xFF, self._on_gf_ap_changed,
                                "AP invested in this GF's learnable-ability slot "
                                f"{slot} (its ability is defined by the GF's kernel.bin ability list)")
            self.gf_ap_spins.append(spin)
            ap_form.addRow(f"Slot {slot}:", spin)
        ap_container = QWidget()
        ap_container.setLayout(ap_form)
        ap_scroll = QScrollArea()
        ap_scroll.setWidgetResizable(True)
        ap_scroll.setWidget(ap_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_tab_container, "Status")
        sub_tabs.addTab(ability_scroll, "Learned Abilities")
        sub_tabs.addTab(ap_scroll, "AP")
        sub_tabs.setTabToolTip(0, "Name, EXP, HP, kills and availability of the GF")
        sub_tabs.setTabToolTip(1, "Abilities this GF has finished learning (128-bit ability bitfield)")
        sub_tabs.setTabToolTip(2, "AP invested toward each of the GF's learnable abilities")

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
        ]:
            with QSignalBlocker(spin):
                spin.setValue(value)
        with QSignalBlocker(self.gf_learning_ability_combo):
            self._select_combo(self.gf_learning_ability_combo, gf.learning_ability)
        self.gf_unused_spin.setValue(gf.unknown1)
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
        gf.learning_ability = self.gf_learning_ability_combo.currentData()
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
        status_group.setToolTip("HP, EXP, model/weapon and base stats of the selected character")
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

        char_reserved_group, char_reserved_spins = self._reserved_group(
            ["Unused (0x5A):", "Unused (0x6F):", "Unused (0x95):"])
        self.char_unused_spins = char_reserved_spins

        status_tab_layout = QVBoxLayout()
        status_tab_layout.addWidget(status_group)
        status_tab_layout.addWidget(status_checks_group)
        status_tab_layout.addWidget(char_reserved_group)
        status_tab_layout.addStretch(1)
        status_tab = QWidget()
        status_tab.setLayout(status_tab_layout)

        # Magic
        self.char_magic_table = QTableWidget(32, 2)
        self.char_magic_table.setHorizontalHeaderLabels(["Magic", "Quantity"])
        self._configure_list_table(self.char_magic_table)
        self.char_magic_combos = []
        self.char_magic_qty_spins = []
        for row in range(32):
            combo = self._enum_combo(self._magic_entries, self._on_character_magic_changed, adjust_size=True)
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
        abilities_group.setToolTip("The 4 equipped command abilities and 4 equipped passive abilities")
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
        compat_group.setToolTip(f"Per-GF compatibility ({GF_COMPATIBILITY_MIN}-{GF_COMPATIBILITY_MAX}); higher summons faster")
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
        sub_tabs.setTabToolTip(0, "HP, stats and current status")
        sub_tabs.setTabToolTip(1, "Stocked magic (spell + quantity, 32 slots)")
        sub_tabs.setTabToolTip(2, "Equipped command and passive abilities")
        sub_tabs.setTabToolTip(3, "Junctioned GFs and per-GF compatibility")
        sub_tabs.setTabToolTip(4, "Which magic is junctioned to each stat")

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
        for spin, value in zip(self.char_unused_spins, [char.unknown2, char.unknown3, char.unknown4]):
            spin.setValue(value)
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
        from Quezacotl.quezacotlmanager import ConfigEntry
        self.config_spins = {}
        speed_tip = "0 = slowest, 4 = fastest"
        sliders = [
            ("battle_speed", "Battle speed", 4, "Battle ATB speed. 0 = slowest, 4 = fastest (ATB gauge = 4000 x (value+1))"),
            ("battle_message_speed", "Battle message speed", 4, f"Battle message scroll speed. {speed_tip}"),
            ("field_message_speed", "Field message speed", 4, f"Field/menu message scroll speed. {speed_tip}"),
            ("volume", "Sound volume", 100, "Sound volume (0-100)"),
            ("camera", "Battle camera speed", 4, f"Battle camera movement speed. {speed_tip}"),
        ]
        form = QFormLayout()
        for field, label, maximum, tip in sliders:
            spin = self._spinbox(0, maximum, self._on_config_changed, tip)
            self.config_spins[field] = spin
            form.addRow(f"{label}:", spin)

        self.config_scan_check = QCheckBox("Always show full Scan detail")
        self.config_scan_check.setToolTip("Scan detail mode (offset 0x05 bit 0). Off = repeat Scans on an already-"
                                          "scanned enemy show an abbreviated result; on = always show the full "
                                          "Scan info window.")
        self.config_scan_check.stateChanged.connect(self._on_config_changed)
        form.addRow("Scan:", self.config_scan_check)

        settings_group = QGroupBox("Settings")
        settings_group.setToolTip("In-game options: speeds, volume, camera, scan detail")
        settings_group.setLayout(form)

        # Config flag (offset 4): editable as a bitfield of named checkboxes.
        self.config_flag_checks = []
        flag_grid = QGridLayout()
        for i, (mask, name) in enumerate(ConfigEntry.FLAG_BITS):
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X}" + (" — normally managed by the game, not the player"
                                                     if "auto" in name else ""))
            check.stateChanged.connect(self._on_config_changed)
            self.config_flag_checks.append((mask, check))
            flag_grid.addWidget(check, i // 2, i % 2)
        flag_group = QGroupBox("Config flags")
        flag_group.setToolTip("Controller / config bitfield (offset 0x04). Some bits are set automatically "
                              "by the game from the detected hardware.")
        flag_group.setLayout(flag_grid)

        # Map seal (offset 7): 8 named lock bits.
        self.config_map_seal_checks = []
        seal_grid = QGridLayout()
        for i, (mask, name) in enumerate(ConfigEntry.MAP_SEAL_BITS):
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X} — set by story events that seal this menu action")
            check.stateChanged.connect(self._on_config_changed)
            self.config_map_seal_checks.append((mask, check))
            seal_grid.addWidget(check, i // 2, i % 2)
        seal_group = QGroupBox("Map seal (locked menu actions)")
        seal_group.setToolTip("Which menu actions are currently sealed by the map/story (offset 0x07)")
        seal_group.setLayout(seal_grid)

        # Button remap table (offsets 8-19): each physical button picks a logical action.
        # unk1/unk2 (0x11/0x12) are phantom slots: a PSX pad has only 10 configurable buttons,
        # so nothing maps to or consumes them — shown read-only.
        phantom_tip = ("Read-only: phantom config slot. A PSX controller exposes only 10 configurable "
                       "buttons, so no physical button maps here and no game code reads it. Preserved on save.")
        self.config_key_combos = {}
        key_form = QFormLayout()
        for field, label in ConfigEntry.KEY_FIELDS:
            phantom = field in ("key_unk1", "key_unk2")
            combo = self._enum_combo(self._button_action_entries,
                                     None if phantom else self._on_config_changed,
                                     phantom_tip if phantom else f"Logical action triggered by the {label} button")
            self.config_key_combos[field] = combo
            if phantom:
                combo.setEnabled(False)
                key_form.addRow(self._grey_label(f"{label} button:", phantom_tip), combo)
            else:
                key_form.addRow(f"{label} button:", combo)
        key_group = QGroupBox("Button config (physical button → action)")
        key_group.setToolTip("FF8's remap swaps roles between the 12 physical buttons; each button here is "
                             "assigned the logical action it performs (default = its own role). Known roles: "
                             "L2+R2 held = flee battle, R1 = Renzokuken critical timing.")
        key_group.setLayout(key_form)

        return self._left_column_scroll([settings_group, flag_group, seal_group, key_group])

    def _reload_config(self):
        config = self.manager.config
        for field, spin in self.config_spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(config, field))
        with QSignalBlocker(self.config_scan_check):
            self.config_scan_check.setChecked(bool(config.scan & 0x01))
        for mask, check in self.config_flag_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(config.flag & mask))
        for mask, check in self.config_map_seal_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(config.map_seal & mask))
        for field, combo in self.config_key_combos.items():
            with QSignalBlocker(combo):
                self._select_combo(combo, getattr(config, field))

    def _on_config_changed(self):
        config = self.manager.config
        if not config:
            return
        for field, spin in self.config_spins.items():
            setattr(config, field, spin.value())
        # Only bit 0 of scan is meaningful; preserve any other bits.
        config.scan = (config.scan & ~0x01) | (0x01 if self.config_scan_check.isChecked() else 0)
        flag = 0
        for mask, check in self.config_flag_checks:
            if check.isChecked():
                flag |= mask
        config.flag = flag
        seal = 0
        for mask, check in self.config_map_seal_checks:
            if check.isChecked():
                seal |= mask
        config.map_seal = seal
        for field, combo in self.config_key_combos.items():
            setattr(config, field, combo.currentData())

    # ── Misc tab ─────────────────────────────────────────────────────────

    def _build_misc_tab(self):
        # Party slots 1-3 are the real party; slot 4 (party[3]) is unused padding (the top byte
        # of the 32-bit party word) — FF8's party is fixed at 3, so it is shown read-only.
        party4_tip = ("Read-only: party slot 4 is unused padding (the high byte of the 32-bit party word). "
                      "FF8's party is fixed at 3 members; the game never stores a character here.")
        self.misc_party_combos = []
        self._party_rows = []
        for i in range(4):
            phantom = i == 3
            combo = self._enum_combo(self._party_entries, None if phantom else self._on_misc_changed,
                                     party4_tip if phantom else f"Party slot {i + 1} character (None = empty)")
            self.misc_party_combos.append(combo)
            if phantom:
                combo.setEnabled(False)
                self._party_rows.append((self._grey_label("Party member 4:", party4_tip), combo))
            else:
                self._party_rows.append((f"Party member {i + 1}:", combo))
        self.misc_griever_name_edit = QLineEdit()
        self.misc_griever_name_edit.setToolTip("Griever GF name (FF8 text, max 12 bytes)")
        self._compact_line(self.misc_griever_name_edit)
        self.misc_griever_name_edit.editingFinished.connect(self._on_misc_griever_name_changed)
        self.misc_gil_spin = self._spinbox(0, 2147483647, self._on_misc_changed, "Party gil")
        self.misc_gil_laguna_spin = self._spinbox(0, 2147483647, self._on_misc_changed, "Laguna-squad gil")
        self.misc_weapon_laguna_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Laguna's weapon id")
        self.misc_weapon_kiros_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Kiros's weapon id")
        self.misc_weapon_ward_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Ward's weapon id")

        general_form = QFormLayout()
        for label, combo in self._party_rows:
            general_form.addRow(label, combo)
        general_form.addRow("Griever name:", self.misc_griever_name_edit)
        general_form.addRow("Gil:", self.misc_gil_spin)
        general_form.addRow("Gil (Laguna squad):", self.misc_gil_laguna_spin)
        general_form.addRow("Laguna weapon:", self.misc_weapon_laguna_spin)
        general_form.addRow("Kiros weapon:", self.misc_weapon_kiros_spin)
        general_form.addRow("Ward weapon:", self.misc_weapon_ward_spin)
        general_group = QGroupBox("General")
        general_group.setToolTip("Party, Griever name, gil and Laguna-squad weapons")
        general_group.setLayout(general_form)

        # Unlocked weapons: bit i = kernel weapon id i (28 upgradeable party weapons).
        weapon_entries = [{"bit": wid, "name": name} for wid, name in self._weapon_bits]
        weapons_group, self.misc_weapon_checks = self._bitfield_group(
            "Unlocked weapons",
            "Weapon-upgrade recipes already built/owned (Junk Shop). Bit i = kernel weapon id i.",
            weapon_entries, self._on_misc_changed, columns=3)

        # Limit-break unlocks: each is a bitfield → a checkbox group.
        self.misc_limit_bitfields = []  # (manager field, [(bit, checkbox)])
        limit_groups = []
        for field, title, entries, tip in self._limit_bitfield_defs:
            group, checks = self._bitfield_group(title, tip, entries, self._on_misc_changed)
            self.misc_limit_bitfields.append((field, checks))
            limit_groups.append(group)

        # Angelo Search points are per-command learning counters (not a bitfield).
        self.misc_angelo_point_spins = [
            self._spinbox(0, 0xFF, self._on_misc_changed,
                         "Remaining points to learn this Angelo command (counts down to 0)")
            for _ in range(8)]
        points_form = QFormLayout()
        for i, spin in enumerate(self.misc_angelo_point_spins):
            angelo_name = self._limit_bitfield_defs[-1][2][i]["name"]
            points_form.addRow(f"{angelo_name}:", spin)
        points_group = QGroupBox("Angelo Search — learning points")
        points_group.setToolTip("Per-command AP-like learning progress; 0 = learned")
        points_group.setLayout(points_form)

        return self._left_column_scroll([general_group, weapons_group, *limit_groups, points_group])

    def _reload_misc(self):
        misc = self.manager.misc
        for combo, value in zip(self.misc_party_combos,
                                [misc.party_mem1, misc.party_mem2, misc.party_mem3, misc.party_mem4]):
            with QSignalBlocker(combo):
                self._select_combo(combo, value)
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
        unlocked = misc.unlocked_weapons
        for bit, check in self.misc_weapon_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(unlocked & (1 << bit)))
        for field, checks in self.misc_limit_bitfields:
            value = getattr(misc, field)
            for bit, check in checks:
                with QSignalBlocker(check):
                    check.setChecked(bool(value & (1 << bit)))
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
        misc.gil = self.misc_gil_spin.value()
        misc.gil_laguna = self.misc_gil_laguna_spin.value()
        misc.weapon_id_laguna = self.misc_weapon_laguna_spin.value()
        misc.weapon_id_kiros = self.misc_weapon_kiros_spin.value()
        misc.weapon_id_ward = self.misc_weapon_ward_spin.value()
        # unlocked_weapons keeps any high bits (28-31) the game doesn't use but we shouldn't drop.
        unlocked = misc.unlocked_weapons
        for bit, check in self.misc_weapon_checks:
            unlocked = (unlocked | (1 << bit)) if check.isChecked() else (unlocked & ~(1 << bit))
        misc.unlocked_weapons = unlocked
        for field, checks in self.misc_limit_bitfields:
            value = getattr(misc, field)  # preserve any bits not shown as a checkbox
            for bit, check in checks:
                value = (value | (1 << bit)) if check.isChecked() else (value & ~(1 << bit))
            setattr(misc, field, value)
        for i, spin in enumerate(self.misc_angelo_point_spins):
            misc.set_angelo_point(i, spin.value())

    # ── Items tab ────────────────────────────────────────────────────────

    def _build_items_tab(self):
        self.items_table = QTableWidget(0, 2)
        self.items_table.setHorizontalHeaderLabels(["Item", "Quantity"])
        self._configure_list_table(self.items_table)
        return self.items_table

    def _reload_items(self):
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(self.manager.item_entries))
        for row, entry in enumerate(self.manager.item_entries):
            combo = self._enum_combo(self._item_entries, adjust_size=True)
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
