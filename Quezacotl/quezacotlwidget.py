import json
import os

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QSpinBox, QLineEdit, QGroupBox, QFormLayout, QTabWidget, QCheckBox, QGridLayout,
    QScrollArea, QComboBox, QTableWidget, QHeaderView, QAbstractSpinBox, QSizePolicy, QToolButton,
    QPushButton, QAbstractScrollArea,
)

# Tooltip shown on the fields the vanilla game never uses (greyed until "Unlock" is ticked).
RESERVED_TOOLTIP = ("Unused by the vanilla game: no code reads this value (checked in FF8_EN.exe). It is "
                    "greyed out so you only edit what does something; tick \"Unlock fields unused by the "
                    "vanilla game\" to edit it anyway, for a mod that gives it a meaning.")

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.kernelnamesource import KernelNameSource
from FF8GameData.gamedata import GameData
from FF8GameData.kernelgfabilities import ABILITY_LIST_COUNT, gf_ability_slots
from FF8GameData.kernellevels import level_curves, load_kernel
from Quezacotl.levelformulapopup import LevelFormulaPopup
from SolomonRing.kernellookups import LookupRegistry
from Quezacotl.quezacotlmanager import (
    QuezacotlManager, CharacterEntry, ACTIVE_ABILITY_RANGE, PASSIVE_ABILITY_RANGE, ABILITY_COUNT,
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

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.manager = QuezacotlManager(self.game_data)
        self.icon_path = icon_path

        # Named option lists shared with the rest of the suite.
        self.lookups = LookupRegistry(self.game_data, game_data_folder)
        self._magic_entries = self.lookups.resolve("magic")["entries"]
        self._item_entries = self.lookups.resolve("item")["entries"]
        self._gforce_entries = self.lookups.resolve("gforce")["entries"]
        self._status_entries = self.lookups.resolve("status_1")["entries"]
        self._party_entries = (self.lookups.resolve("weapon_character")["entries"]
                               + [{"value": 0xFF, "name": "None"}])
        # The ability and weapon NAMES come only from a kernel.bin, opened as a complementary
        # file (see _on_kernel_names_changed) - there is no built-in list of them.

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
        # The names come from kernel.bin; only whose weapon each bit is stays built in.
        weapon_data = _load_json("kernel_bin_data.json")["weapon_data"]
        self._weapon_characters = {w["id"]: w["character"] for w in weapon_data if w["id"] < 28}

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

        self.setWindowTitle("Quezacotl")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'Quezacotl.ico')))

        # init.out, this tool's one editable file, driven by the shared header toolbar.
        self.init_binding = FileBinding("init.out", file_registry,
                                        load_callback=self.load_file, save_callback=self.save_file)
        # kernel.bin, complementary: the only source of the ability and weapon names.
        self.kernel_names = KernelNameSource(self.game_data, file_registry)
        self.kernel_names.changed.connect(self._on_kernel_names_changed)
        self.kernel_notice = KernelNameSource.make_notice("ability and weapon")
        # ...of the EXP curves, which turn the EXP into a level (hints under the EXP fields), and of
        # each GF's learnable-ability list, which the AP slots count toward
        self.level_curves = None
        self.gf_slots = None
        self.level_popup = None  # the f(x) window of the EXP fields, made on first use
        self.kernel_names.binding.file_opened.connect(self._load_kernel_data)
        self.kernel_names.binding.file_closed.connect(self._clear_kernel_data)

        # Fields the vanilla game never uses are greyed out (SolomonRing's rule): _lock() registers
        # them, the "Unlock" switch hands them back for a mod that gives them a meaning.
        self._locked_widgets = []
        self.unlock_check = QCheckBox("Unlock fields unused by the vanilla game")
        self.unlock_check.setToolTip(
            "Off (default): a field the unmodified game never reads is shown - so you can see its "
            "value - but greyed out, so you cannot change something that does nothing.\n"
            "On: every field becomes editable, for a mod that gave those bytes/flags a purpose. "
            "This only changes what the UI lets you edit; loading and saving are identical either way.")
        self.unlock_check.toggled.connect(self.set_unlock_all)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gf_tab(), "G-Forces")
        self.tabs.addTab(self._build_character_tab(), "Characters")
        self.tabs.addTab(self._build_config_tab(), "Config")
        self.tabs.addTab(self._build_misc_tab(), "Misc")
        self.tabs.addTab(self._build_items_tab(), "Items")
        self.tabs.setTabToolTip(0, "The 16 Guardian Forces: stats, learned abilities and AP")
        self.tabs.setTabToolTip(1, "The 8 playable characters: stats, magic, junctions and abilities")
        self.tabs.setTabToolTip(2, "Default game configuration (speeds, controls, map seal)")
        self.tabs.setTabToolTip(3, "Party, gil, weapons, Griever name and limit-break unlocks")
        self.tabs.setTabToolTip(4, "Starting inventory (item id + quantity per slot)")
        self.tabs.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.kernel_notice)
        unlock_row = QHBoxLayout()
        unlock_row.addWidget(self.unlock_check)
        unlock_row.addStretch(1)
        main_layout.addLayout(unlock_row)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self._on_kernel_names_changed()  # no kernel.bin yet: ids only, greyed out
        self.init_binding.load_opened_file()  # Another tool may have opened init.out already
        self.kernel_names.binding.load_opened_file()  # ...or a kernel.bin

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool: init.out, and kernel.bin as a
        complementary file naming the abilities and weapons."""
        return [self.init_binding, self.kernel_names.binding]

    # ── Names from kernel.bin ────────────────────────────────────────────

    def _ability_choices(self, allowed):
        """The abilities a combo offers: 'None' plus those in `allowed` (every one when None),
        named by the open kernel.bin - an empty list without one."""
        entries = self.kernel_names.ability_entries()
        if not entries:
            return []
        return [entries[0]] + [e for e in entries[1:] if allowed is None or e["value"] in allowed]

    def _fill_ability_combo(self, combo, value, allowed):
        """Fill an ability combo and select `value`. Without a kernel.bin there is no name to
        offer: only the value itself, greyed out - it is never changed."""
        choices = self._ability_choices(allowed)
        with QSignalBlocker(combo):
            combo.clear()
            for entry in choices:
                combo.addItem(f"{entry['value']}: {entry['name']}", entry["value"])
            if not choices:
                combo.addItem(f"{value}: open kernel.bin to name it", value)
            self._select_combo(combo, value)
        combo.setEnabled(bool(choices))

    def _on_kernel_names_changed(self):
        """A kernel.bin was opened or removed: re-label the abilities and weapons. The values in
        the file (and unsaved edits) are untouched - only the names change."""
        names = self.kernel_names
        self.kernel_notice.setVisible(not (names.abilities and names.weapons))
        for combo, allowed in ([(self.gf_learning_ability_combo, None)]
                               + [(c, ACTIVE_ABILITY_RANGE) for c in self.char_active_combos]
                               + [(c, PASSIVE_ABILITY_RANGE) for c in self.char_passive_combos]):
            current = combo.currentData()
            self._fill_ability_combo(combo, 0 if current is None else current, allowed)
        for ability_id, check in self.gf_ability_checks.items():
            check.setText(names.ability_name(ability_id) or f"Ability {ability_id}")
            check.setEnabled(bool(names.abilities))
        for bit, check in self.misc_weapon_checks:
            name = names.weapon_name(bit)
            check.setText(f"{name} ({self._weapon_characters.get(bit, '?')})" if name
                          else f"Weapon {bit}")
            check.setEnabled(bool(names.weapons))
        if self.manager.item_entries:
            self._reload_items()   # the item names, and the items 199-255 a mod adds, come from it too

    # ── Levels from kernel.bin ───────────────────────────────────────────

    def _load_kernel_data(self, kernel_path):
        try:
            kernel_manager = load_kernel(self.game_data, kernel_path)
            self.level_curves = level_curves(kernel_manager)
            self.gf_slots = gf_ability_slots(kernel_manager)
        except Exception as error:  # noqa: BLE001 - a bad kernel.bin just gives no levels nor slots
            print(f"[Quezacotl] could not read the EXP curves / GF abilities of {kernel_path}: {error}")
            self.level_curves = self.gf_slots = None
        self._update_level_hints()
        self._update_ap_slots()
        if self._selected_gf():
            self._fill_learning_combo(self._selected_gf())

    def _clear_kernel_data(self, _path=None):
        self.level_curves = self.gf_slots = None
        self._update_level_hints()
        self._update_ap_slots()
        if self._selected_gf():
            self._fill_learning_combo(self._selected_gf())

    def _fill_learning_combo(self, gf):
        """The Learning choice. With a kernel.bin open: None and the GF's own 21 abilities, each marked
        when the GF cannot earn AP toward it (GF_AddApToLearningAbility only credits an ability of
        the GF's list, and the battle results only one it can learn now). Without one: every ability."""
        slots = (self.gf_slots or {}).get("slots", [])
        if not slots or gf.gf_id >= len(slots):
            self._fill_ability_combo(self.gf_learning_ability_combo, gf.learning_ability, None)
            return
        names = self.kernel_names
        combo = self.gf_learning_ability_combo
        with QSignalBlocker(combo):
            combo.clear()
            combo.addItem("0: None", 0)
            for slot, entry in enumerate(slots[gf.gf_id], start=1):
                if entry.ability == 0 or combo.findData(entry.ability) >= 0:
                    continue
                name = names.ability_name(entry.ability) or f"Ability {entry.ability}"
                if gf.has_ability(entry.ability):
                    name += " (learned)"
                elif gf.is_forgotten(slot):
                    name += " (forgotten)"
                combo.addItem(f"{entry.ability}: {name}", entry.ability)
            if combo.findData(gf.learning_ability) < 0:  # never lose the file's value
                combo.addItem(f"{gf.learning_ability}: not in this GF's list - earns no AP",
                              gf.learning_ability)
            combo.setCurrentIndex(combo.findData(gf.learning_ability))

    def _update_ap_slots(self):
        """Name each AP slot after the ability of the selected GF's kernel.bin list it counts toward,
        with that ability's AP cost and when it unlocks."""
        gf = self._selected_gf()
        slots = (self.gf_slots or {}).get("slots", [])
        costs = (self.gf_slots or {}).get("ap", [])
        gf_list = slots[gf.gf_id] if gf and gf.gf_id < len(slots) else None
        names = self.kernel_names

        def ability_name(ability_id):
            return names.ability_name(ability_id) or f"Ability {ability_id}"

        for index, (label, info) in enumerate(zip(self.gf_ap_labels, self.gf_ap_infos)):
            slot = index + 1
            if index >= ABILITY_LIST_COUNT:
                label.setText(f"Slot {slot}: -")
                info.setText(f"unused: a GF's ability list has {ABILITY_LIST_COUNT} entries, no code reads this one")
                continue
            if gf_list is None:
                label.setText(f"Slot {slot}:")
                info.setText("")
                continue
            entry = gf_list[index]
            if entry.ability == 0:
                label.setText(f"Slot {slot}: -")
                info.setText("no ability in this slot of the GF's kernel.bin list")
                continue
            label.setText(f"Slot {slot}: {ability_name(entry.ability)}")
            parts = [f"/ {costs[entry.ability]} AP" if entry.ability < len(costs) else "/ ? AP"]
            if entry.unlock_level is not None:
                parts.append(f"from GF level {entry.unlock_level}" if entry.unlock_level > 1 else "from the start")
            elif entry.unlock_after_slot is not None:
                parts.append(f"after {ability_name(gf_list[entry.unlock_after_slot].ability)}")
            if gf.has_ability(entry.ability):
                parts.append("learned")
            info.setText(" - ".join(parts))

    def _with_level_hint(self, spin, kind):
        """The spinbox and an f(x) button opening the level formula, with a small grey
        "Lvl N + X xp" line under them (like SolomonRing's "≈ N s" hints and f(x) buttons).
        Returns (widget to place, hint label)."""
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(2)
        row.addWidget(spin)
        button = QToolButton()
        button.setText("ƒ(x)")
        button.setAutoRaise(True)
        button.setToolTip("Show the level formula, its two kernel.bin parameters and the EXP curve")
        button.setStyleSheet("QToolButton { color: palette(highlight); font-style: italic; }")
        button.clicked.connect(lambda _=False, k=kind: self._open_level_popup(k))
        row.addWidget(button)
        row.addStretch(1)
        box.addLayout(row)
        hint = QLabel()
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        box.addWidget(hint)
        return container, hint

    def _level_curve(self, kind, index):
        curves = (self.level_curves or {}).get(kind, [])
        return curves[index] if 0 <= index < len(curves) else None

    @staticmethod
    def _show_level(hint, curve, exp, owner):
        if curve is None:
            hint.setText("Lvl ? (needs kernel.bin)")
            hint.setToolTip(f"The level comes from {owner}'s EXP curve in kernel.bin: open one with the "
                            f"toolbar's \"Import complementary\" button.")
            return
        level, past = curve.level_from_exp(exp)
        hint.setText(f"Lvl {level} + {past} xp" if level < 100 else "Lvl 100 (max)")
        if level < 100:
            hint.setToolTip(f"Level {level}: {past} EXP past it, level {level + 1} at "
                            f"{curve.exp_to_leave(level)} EXP ({owner}'s curve in kernel.bin: "
                            f"{curve.linear} linear, {curve.quadratic} quadratic)")
        else:
            hint.setToolTip(f"Level 100, the maximum ({owner}'s curve in kernel.bin)")

    def _open_level_popup(self, kind):
        if self.level_popup is None:
            self.level_popup = LevelFormulaPopup(self)
        self.level_popup.show_for(lambda k=kind: self._level_source(k))

    def _level_source(self, kind):
        """(kind, owner name, kernel.bin entry, LevelCurve or None, EXP) of the selected GF/character."""
        if kind == "gf":
            gf = self._selected_gf()
            index = gf.gf_id if gf else 0
            owner = gf.gf_name if gf else "GF"
            return kind, owner, index, self._level_curve("gf", index), self.gf_exp_spin.value()
        char = self._selected_character()
        index = self.char_model_spin.value()
        owner = char.name if char else "character"
        return kind, owner, index, self._level_curve("character", index), self.char_exp_spin.value()

    def _update_level_hints(self, *_):
        gf = self._selected_gf()
        if gf:
            self._show_level(self.gf_exp_hint, self._level_curve("gf", gf.gf_id), self.gf_exp_spin.value(),
                             "this GF")
        char = self._selected_character()
        if char:
            com_id = self.char_model_spin.value()
            self._show_level(self.char_exp_hint, self._level_curve("character", com_id),
                             self.char_exp_spin.value(), f"character entry {com_id}")
        if self.level_popup is not None:
            self.level_popup.refresh()

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

    def _lock(self, widget, kind="plain"):
        """Grey ``widget`` out because the unmodified game never reads that value, and remember it
        so the Unlock switch can hand it back ("spin" is also made read-only, without arrows)."""
        widget.setEnabled(self.unlock_check.isChecked())
        if kind == "spin" and not self.unlock_check.isChecked():
            widget.setReadOnly(True)
            widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._locked_widgets.append((widget, kind))

    def set_unlock_all(self, unlocked):
        """Enable (or grey again) every field the vanilla game does not use. Values are read and
        written the same either way: this only changes what the UI lets you touch."""
        for widget, kind in self._locked_widgets:
            widget.setEnabled(unlocked)
            if kind == "spin":
                widget.setReadOnly(not unlocked)
                widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows if unlocked
                                        else QAbstractSpinBox.ButtonSymbols.NoButtons)

    def _unused_spin(self, slot, tooltip=RESERVED_TOOLTIP, maximum=0xFF):
        """A spinbox for a byte the vanilla game never reads: greyed until unlocked, written back
        through ``slot`` like any other field once it is."""
        spin = self._spinbox(0, maximum, slot, tooltip)
        self._lock(spin, "spin")
        return spin

    @staticmethod
    def _grey_label(text, tooltip):
        label = QLabel(text)
        label.setToolTip(tooltip)
        label.setStyleSheet("color: gray;")
        return label

    def _reserved_group(self, rows, slot):
        """Build an 'Unused by the vanilla game' group, one greyed spinbox per row label, each
        written back through ``slot`` once unlocked. Returns (group, [spin, ...])."""
        form = QFormLayout()
        spins = []
        for label_text in rows:
            spin = self._unused_spin(slot)
            form.addRow(self._grey_label(label_text, RESERVED_TOOLTIP), spin)
            spins.append(spin)
        group = QGroupBox("Unused by the vanilla game")
        group.setToolTip("Bytes no game code reads - greyed out until \"Unlock fields unused by the vanilla "
                         "game\" is ticked")
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
        self.manager.load_file(file_name)
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
            [], self._on_gf_data_changed,
            "Ability the GF is currently set to learn — earned AP is applied to it. This is an "
            "ability id, not an AP amount; the AP invested per ability is on the AP tab.\n"
            "With a kernel.bin open the list is this GF's own abilities: the game only credits AP to "
            "one of them (GF_AddApToLearningAbility), and only while it can learn it (not learned, "
            "not forgotten, unlocked).")
        self.gf_available_check = QCheckBox("Available")
        self.gf_available_check.setToolTip("GF has been obtained — set once the GF is junctioned/acquired at least once")
        self.gf_available_check.stateChanged.connect(self._on_gf_data_changed)

        status_form = QFormLayout()
        status_form.addRow("Name:", self.gf_name_edit)
        gf_exp_widget, self.gf_exp_hint = self._with_level_hint(self.gf_exp_spin, "gf")
        self.gf_exp_spin.valueChanged.connect(self._update_level_hints)
        status_form.addRow("EXP:", gf_exp_widget)
        status_form.addRow("Current HP:", self.gf_hp_spin)
        status_form.addRow("Kills:", self.gf_kills_spin)
        status_form.addRow("KOs:", self.gf_kos_spin)
        status_form.addRow("Learning:", self.gf_learning_ability_combo)
        status_form.addRow(self.gf_available_check)
        status_group = QGroupBox("Status")
        status_group.setToolTip("Core stats and state of the selected GF")
        status_group.setLayout(status_form)

        gf_reserved_group, gf_reserved_spins = self._reserved_group(["Unused (0x10):"], self._on_gf_unused_changed)
        self.gf_unused_spin = gf_reserved_spins[0]
        status_tab_container = self._left_column_scroll([status_group, gf_reserved_group])

        # Learned abilities: one checkbox per junctionable_ability id (bit id in the GF's
        # 128-bit "complete abilities" field). Value 0 (None) is skipped.
        self.gf_ability_checks = {}
        ability_grid = QGridLayout()
        columns = 4
        for i, ability_id in enumerate(range(1, ABILITY_COUNT)):
            check = QCheckBox(f"Ability {ability_id}")  # named once a kernel.bin is open
            check.setToolTip(f"Ability id {ability_id} learned")
            check.stateChanged.connect(self._on_gf_ability_changed)
            self.gf_ability_checks[ability_id] = check
            ability_grid.addWidget(check, i // columns, i % columns)
        ability_grid.setColumnStretch(columns, 1)  # the spare width goes right of the columns
        ability_grid.setRowStretch((ABILITY_COUNT - 2) // columns + 1, 1)
        ability_container = QWidget()
        ability_container.setLayout(ability_grid)
        ability_scroll = QScrollArea()
        ability_scroll.setWidgetResizable(True)
        ability_scroll.setWidget(ability_container)

        # AP invested per ability slot. The slots are NOT global ability ids: slot N is the
        # N-th entry in *this GF's* learnable-ability list (BuildGFAbilityList), whose abilities,
        # AP costs and unlocks are in kernel.bin (Junctionable GFs section), not in init.out: the
        # slots are named from an opened kernel.bin (_update_ap_slots), numbered without one.
        # Slot 22 exists in init.out (24 AP bytes) but a GF's list has 21 abilities: nothing reads or
        # writes it (GF_AddApToLearningAbility / BuildGFAbilityList / DrawGFAbilityLearnStatus all
        # stop at 21), so it is shown read-only. "Forgotten" = the GF's forgotten bits (offset 65).
        self.gf_ap_spins = []
        self.gf_ap_labels = []
        self.gf_ap_infos = []
        self.gf_forgotten_checks = []
        ap_form = QFormLayout()
        ap_note = QLabel("Slot N = AP invested in this GF's N-th learnable ability, named from kernel.bin\n"
                         "(Junctionable GFs section) with the AP it costs and when it unlocks.")
        ap_form.addRow(ap_note)
        for slot in range(1, 23):
            label = QLabel(f"Slot {slot}:")
            info = QLabel()
            info.setStyleSheet("color: gray;")
            row = QHBoxLayout()
            if slot <= 21:
                spin = self._spinbox(0, 0xFF, self._on_gf_ap_changed,
                                    "AP invested in this GF's learnable-ability slot "
                                    f"{slot} (its ability is defined by the GF's kernel.bin ability list)")
                forgotten = QCheckBox("Forgotten")
                forgotten.setToolTip("The GF forgot this ability: it is left out of the abilities it can learn, "
                                     "so it can never learn it again (offset 0x41 bit field, one bit per slot).")
                forgotten.stateChanged.connect(self._on_gf_forgotten_changed)
                self.gf_forgotten_checks.append(forgotten)
                row.addWidget(spin)
                row.addWidget(forgotten)
            else:
                spin = self._unused_spin(self._on_gf_ap_changed)
                label.setStyleSheet("color: gray;")
                label.setToolTip(RESERVED_TOOLTIP)
                row.addWidget(spin)
            self.gf_ap_spins.append(spin)
            row.addWidget(info)
            row.addStretch(1)
            self.gf_ap_labels.append(label)
            self.gf_ap_infos.append(info)
            ap_form.addRow(label, row)
        ap_container = QWidget()
        ap_container.setLayout(ap_form)
        ap_scroll = self._left_column_scroll([ap_container])

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
        self._fill_learning_combo(gf)
        with QSignalBlocker(self.gf_unused_spin):
            self.gf_unused_spin.setValue(gf.unknown1)
        with QSignalBlocker(self.gf_available_check):
            self.gf_available_check.setChecked(gf.available)
        for ability_id, check in self.gf_ability_checks.items():
            with QSignalBlocker(check):
                check.setChecked(gf.has_ability(ability_id))
        for slot, spin in enumerate(self.gf_ap_spins, start=1):
            with QSignalBlocker(spin):
                spin.setValue(gf.get_ap_ability(slot))
        for slot, check in enumerate(self.gf_forgotten_checks, start=1):
            with QSignalBlocker(check):
                check.setChecked(gf.is_forgotten(slot))
        self._update_level_hints()
        self._update_ap_slots()

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
        self._update_ap_slots()  # the "learned" marks of the AP tab

    def _on_gf_ap_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for slot, spin in enumerate(self.gf_ap_spins, start=1):  # slot 22: greyed until unlocked
            gf.set_ap_ability(slot, spin.value())

    def _on_gf_unused_changed(self):
        gf = self._selected_gf()
        if gf:
            gf.unknown1 = self.gf_unused_spin.value()

    def _on_gf_forgotten_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for slot, check in enumerate(self.gf_forgotten_checks, start=1):
            gf.set_forgotten(slot, check.isChecked())
        self._update_ap_slots()
        self._fill_learning_combo(gf)

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
        self.char_model_spin = self._spinbox(0, 0xFF, self._on_character_status_changed,
                                             "Field/battle model id; also the kernel.bin character entry "
                                             "the game takes the EXP curve and stats from (comId)")
        self.char_weapon_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Equipped weapon id")
        self.char_kills_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of enemies killed")
        self.char_kos_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of times KO'd")
        self.char_alt_model_check = QCheckBox("Alternative Model (SeeD, Galbadian)")
        self.char_alt_model_check.setToolTip("Use the alternative outfit model (e.g. SeeD uniform, Galbadian soldier)")
        self.char_alt_model_check.stateChanged.connect(self._on_character_status_changed)
        # Offset 0x94 is a bit field the field scripts drive (ADDMEMBER/SUBMEMBER/HOLD), not a 0/1
        # "exists": see CharacterEntry.EXIST_BITS. Each bit is its own checkbox so editing one never
        # wipes the others (the old single checkbox wrote 0 or 1).
        self.char_exist_checks = []
        party_flags_layout = QVBoxLayout()
        exist_tips = {
            0x01: "In the party roster: can be picked in the party select (set by the field script ADDMEMBER, "
                  "cleared by SUBMEMBER, tested by ISMEMBER).",
            0x02: "Locked in the party: the party select won't swap it out (field script HOLD sets 0x02 and 0x04).",
            0x04: "Locked like 0x02, and keeps its place in the walking field party (Squall gets it from ADDMEMBER).",
            0x08: "Replaced by Laguna's party in the dream sequences (ADDMEMBER sets it for everyone but Rinoa, "
                  "Seifer and Edea).",
        }
        for mask, name in CharacterEntry.EXIST_BITS:
            check = QCheckBox(name)
            check.setToolTip(f"Offset 0x94, bit 0x{mask:02X}: {exist_tips[mask]}")
            check.stateChanged.connect(self._on_character_party_flags_changed)
            self.char_exist_checks.append((mask, check))
            party_flags_layout.addWidget(check)
        party_flags_group = QGroupBox("Party flags")
        party_flags_group.setToolTip("Offset 0x94 bit field set by the field scripts. Bits 0x10-0x80 are never "
                                     "read or written by the game.")
        party_flags_group.setLayout(party_flags_layout)

        self.char_str_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Strength")
        self.char_vit_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Vitality")
        self.char_mag_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Magic")
        self.char_spr_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Spirit")
        self.char_spd_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Speed")
        self.char_luck_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Luck")

        status_form = QFormLayout()
        status_form.addRow("Current HP:", self.char_hp_spin)
        status_form.addRow("Max HP bonus:", self.char_hp_bonus_spin)
        char_exp_widget, self.char_exp_hint = self._with_level_hint(self.char_exp_spin, "character")
        self.char_exp_spin.valueChanged.connect(self._update_level_hints)
        self.char_model_spin.valueChanged.connect(self._update_level_hints)
        status_form.addRow("EXP:", char_exp_widget)
        status_form.addRow("Model:", self.char_model_spin)
        status_form.addRow("Weapon:", self.char_weapon_spin)
        status_form.addRow("Kills:", self.char_kills_spin)
        status_form.addRow("KOs:", self.char_kos_spin)
        status_form.addRow(self.char_alt_model_check)
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
        status_layout.addSpacing(24)
        status_layout.addLayout(stats_form)
        status_layout.addStretch(1)
        status_group.setLayout(status_layout)

        # Persistent status flags: bits 0-6 of the 16-bit status_1 field are the persistable
        # statuses; bit 7 has no known effect (greyed, see CharacterEntry); bits 8-9 are HP-derived
        # flags the game recomputes; 10-15 unused.
        self.char_status_checks = {}
        status_checks_form = QGridLayout()
        persistent_statuses = [e for e in self._status_entries if e["mask"] <= 0x40]
        for i, entry in enumerate(persistent_statuses):
            check = QCheckBox(entry["name"])
            check.stateChanged.connect(self._on_character_status_flags_changed)
            bit = entry["mask"].bit_length() - 1
            self.char_status_checks[bit] = check
            status_checks_form.addWidget(check, i // 4, i % 4)
        bit7_check = QCheckBox("Bit 7 (no known effect)")
        bit7_check.setToolTip("status_1 bit 0x80 (IDA STATUS1_UNUSED1): no code gives it an effect. The monster "
                              "AI can test it like any status and resting keeps it (it clears every other "
                              "status), so it is not plain padding.\n" + RESERVED_TOOLTIP)
        bit7_check.stateChanged.connect(self._on_character_status_flags_changed)
        self.char_status_checks[7] = bit7_check
        status_checks_form.addWidget(bit7_check, len(persistent_statuses) // 4, len(persistent_statuses) % 4)
        self._lock(bit7_check)
        status_checks_group = QGroupBox("Current Status")
        status_checks_group.setToolTip("Persistent statuses (status_1 bits 0-6). Higher bits are unused or "
                                       "HP-derived and are recomputed by the game.")
        status_checks_group.setLayout(status_checks_form)

        char_reserved_group, char_reserved_spins = self._reserved_group(
            ["Unused (0x5A):", "Unused (0x6F):", "Unused (0x95):"], self._on_character_unused_changed)
        self.char_unused_spins = char_reserved_spins
        self.char_unused_spins[0].setToolTip(
            RESERVED_TOOLTIP + "\nVanilla init.out holds 0, 0, 2, 1, 0, 2, 1, 1 here (Squall to Edea): a PSX "
                               "leftover, the PC game neither reads nor writes it.")

        status_tab = self._left_column_scroll([status_group, status_checks_group, party_flags_group,
                                               char_reserved_group])

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
            self._enum_combo([], self._on_character_abilities_changed,
                             "Equipped command ability (Magic, GF, Draw, Item, Card…)")
            for _ in range(4)]
        self.char_passive_combos = [
            self._enum_combo([], self._on_character_abilities_changed,
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
        abilities_tab = self._left_column_scroll([abilities_group])

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
        junction_widget = QWidget()
        junction_widget.setLayout(junction_form)
        compat_group = QGroupBox("Compatibility")
        compat_group.setToolTip(f"Per-GF compatibility ({GF_COMPATIBILITY_MIN}-{GF_COMPATIBILITY_MAX}); higher summons faster")
        compat_group.setLayout(compat_form)
        gf_tab = self._left_column_scroll([junction_widget, compat_group])

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
        for mask, check in self.char_exist_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(char.exist_flags & mask))
        self._update_level_hints()
        for spin, value in zip(self.char_unused_spins, [char.unknown2, char.unknown3, char.unknown4]):
            with QSignalBlocker(spin):
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
            self._fill_ability_combo(combo, char.get_active_ability(slot), ACTIVE_ABILITY_RANGE)
        for slot, combo in enumerate(self.char_passive_combos):
            self._fill_ability_combo(combo, char.get_passive_ability(slot), PASSIVE_ABILITY_RANGE)

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

    def _on_character_party_flags_changed(self):
        char = self._selected_character()
        if not char:
            return
        for mask, check in self.char_exist_checks:
            char.set_exist_flag(mask, check.isChecked())

    def _on_character_unused_changed(self):
        char = self._selected_character()
        if char:
            char.unknown2, char.unknown3, char.unknown4 = (spin.value() for spin in self.char_unused_spins)

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
            ("volume", "Analog stick dead zone", 0xFF, ConfigEntry.ANALOG_DEAD_ZONE_HELP),
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
        settings_group.setToolTip("In-game options: speeds, analog dead zone, camera, scan detail")
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
            if mask in ConfigEntry.UNUSED_FLAG_BITS:
                check.setToolTip(check.toolTip() + "\n" + RESERVED_TOOLTIP)
                self._lock(check)
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
        # Slots 9/10 (0x11/0x12) are L3 and R3 - the slot order is the PSX DualShock button word
        # (remap_pad_input @0x4A2D60). They are real buttons on a PSX analog pad, but the PC input
        # layer can never emit them, so their combos are locked like the other unused fields.
        pc_inert_tip = ("Analog-pad only. This is a real config slot and the PSX engine remaps it, but "
                        "the PC input layer never emits pad bit 0x200/0x400 (Input_Cfg_ApplyBindingToPadBit "
                        "has no binding for them), so on PC the button can never fire whatever you set here.")
        self.config_key_combos = {}
        key_form = QFormLayout()
        for field, label in ConfigEntry.KEY_FIELDS:
            pc_inert = field in ("key_l3", "key_r3")
            combo = self._enum_combo(self._button_action_entries, self._on_config_changed,
                                     pc_inert_tip if pc_inert else
                                     f"Logical action triggered by the {label} button")
            self.config_key_combos[field] = combo
            if pc_inert:
                self._lock(combo)
                key_form.addRow(self._grey_label(f"{label} button:", pc_inert_tip), combo)
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
        party4_tip = ("Party slot 4 is unused padding (the high byte of the 32-bit party word): FF8's party is "
                      "fixed at 3 members, the game never stores a character here.\n" + RESERVED_TOOLTIP)
        self.misc_party_combos = []
        self._party_rows = []
        for i in range(4):
            phantom = i == 3
            combo = self._enum_combo(self._party_entries, self._on_misc_changed,
                                     party4_tip if phantom else f"Party slot {i + 1} character (None = empty)")
            self.misc_party_combos.append(combo)
            if phantom:
                self._lock(combo)
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
        weapon_entries = [{"bit": wid, "name": f"Weapon {wid}"} for wid in self._weapon_characters]
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

        # The in-battle Item list order of the 32 battle items (Misc offset 0x30). Edited as a
        # reordering only, so it always stays the permutation of 0-31 the game needs.
        self.battle_order_list = QListWidget()
        self.battle_order_list.setToolTip("Order of the 32 battle items in the in-battle Item list (and the "
                                          "Item menu's battle arrangement). A newly obtained battle item is "
                                          "moved to the first place no owned item uses.")
        self.battle_order_up = QPushButton("Move up")
        self.battle_order_down = QPushButton("Move down")
        self.battle_order_up.clicked.connect(lambda: self._move_battle_order(-1))
        self.battle_order_down.clicked.connect(lambda: self._move_battle_order(1))
        self.battle_order_warning = QLabel()
        self.battle_order_warning.setWordWrap(True)
        self.battle_order_warning.setStyleSheet("color:#c0392b; font-weight:bold;")
        self.battle_order_warning.setVisible(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.battle_order_up)
        buttons.addWidget(self.battle_order_down)
        buttons.addStretch(1)
        order_layout = QVBoxLayout()
        order_layout.addWidget(self.battle_order_warning)
        order_layout.addWidget(self.battle_order_list)
        order_layout.addLayout(buttons)
        order_group = QGroupBox("Battle item order")
        order_group.setToolTip(self.battle_order_list.toolTip())
        order_group.setLayout(order_layout)

        # Both lists as wide as their content, so the stretch takes the spare width, not them
        for widget in (self.items_table, self.battle_order_list):
            widget.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        layout = QHBoxLayout()
        layout.addWidget(self.items_table)
        layout.addWidget(order_group)
        layout.addStretch(1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def _reload_battle_order(self, select_place=None):
        """Fill the order list: place 1..32, each with the battle item (id 1-32) the file puts there."""
        order = self.manager.misc.get_battle_order()
        valid = sorted(order) == list(range(len(order)))
        self.battle_order_warning.setVisible(not valid)
        self.battle_order_warning.setText(
            "This file's battle item order is not a valid ordering (each place 0-31 exactly once): "
            "the game would write past its arrays. Left as is, not editable here.")
        self.battle_order_up.setEnabled(valid)
        self.battle_order_down.setEnabled(valid)
        self.battle_order_list.clear()
        by_place = {place: item_id for item_id, place in enumerate(order, start=1)}
        for place in range(len(order)):
            item_id = by_place.get(place)
            name = self.kernel_names.item_name(item_id) if item_id else "(none)"
            self.battle_order_list.addItem(f"{place + 1}. {name}" + (f"  [{item_id}]" if item_id else ""))
        if select_place is not None:
            self.battle_order_list.setCurrentRow(select_place)

    def _move_battle_order(self, step):
        """Swap the places of the selected battle item and its neighbour."""
        place = self.battle_order_list.currentRow()
        other = place + step
        order = self.manager.misc.get_battle_order()
        if place < 0 or not 0 <= other < len(order):
            return
        first, second = order.index(place), order.index(other)
        order[first], order[second] = other, place
        self.manager.misc.set_battle_order(order)
        self._reload_battle_order(select_place=other)

    def _reload_items(self):
        self._reload_battle_order()
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(self.manager.item_entries))
        for row, entry in enumerate(self.manager.item_entries):
            # The game's items, renamed by an open kernel.bin, then the ones it adds with FFNx's
            # AddMoreItems (199-255) - a starting inventory may hold those too.
            combo = self._enum_combo(self.kernel_names.item_entries(), adjust_size=True)
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
