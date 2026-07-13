"""Local editor for section 7 (Informations & stats) of a monster c0mxxx.dat file.

Unlike the Excel round-trip tab (StatExcel), this tab edits the already-parsed
``ifrit_manager.enemy.info_stat_data`` dictionary in place, so every change is
immediately reflected in the loaded monster and written out by the shared Save
button. It mirrors the exact analyse/prepare logic of ``MonsterAnalyser`` so the
values shown here match what gets serialized back to the .dat file.
"""
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QGroupBox,
    QTabWidget, QScrollArea,
)

from FF8GameData.monsterdata import AIData


class IfritStatWidget(QWidget):
    """Rich local editor for every field of section 7."""

    def __init__(self, ifrit_manager, icon_path="Resources"):
        super().__init__()
        self.ifrit_manager = ifrit_manager
        self.game_data = ifrit_manager.game_data
        self._data = None            # reference to enemy.info_stat_data
        self._loading = False        # guard so populating widgets doesn't write back

        # Widget references, filled while building
        self._name_edit = None
        self._stat_spins = {}        # stat_name -> [4 QSpinBox]
        self._elem_spins = []        # [8 QSpinBox]
        self._status_spins = []      # [20 QSpinBox]
        self._flag_checks = {}       # byte_flag_name -> {bit_name: QCheckBox}
        self._camera_spin = None     # byte_flag_0 (camera category)
        self._devour_cat_spin = None  # byte_flag_3 (devour category)
        self._misc_spins = {}        # misc name -> QSpinBox / QDoubleSpinBox
        self._card_combos = []       # [3 QComboBox]
        self._devour_combos = []     # [3 QComboBox]
        self._loot_widgets = {}      # loot key -> [(id_combo, value_spin) x4]
        self._ability_widgets = {}   # ability key -> [(type_combo, id_combo, anim_spin) x16]
        self._renzokuken_combos = []  # [8 QComboBox]

        root = QVBoxLayout(self)
        info = QLabel(
            "Local editor for section 7 (Informations & stats). "
            "Edits are applied to the loaded monster immediately — press the "
            "<b>Save</b> button in the toolbar to write them to the .dat file.")
        info.setWordWrap(True)
        root.addWidget(info)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_stats_tab(), "Stats")
        self._tabs.addTab(self._build_defense_tab(), "Defense")
        self._tabs.addTab(self._build_flags_tab(), "Flags")
        self._tabs.addTab(self._build_loot_tab(), "Loot")
        self._tabs.addTab(self._build_abilities_tab(), "Abilities")
        self._tabs.addTab(self._build_renzokuken_tab(), "Renzokuken")
        root.addWidget(self._tabs, 1)

    # ── Small helpers ────────────────────────────────────────────────────

    @staticmethod
    def _scrollable(inner: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _spin(minimum, maximum, step=1) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        return spin

    @staticmethod
    def _combo_from_json(json_list) -> QComboBox:
        combo = QComboBox()
        for el in json_list:
            combo.addItem(f"{el['id']}: {el['name']}", el['id'])
        return combo

    @staticmethod
    def _set_combo_id(combo: QComboBox, id_value):
        index = combo.findData(id_value)
        if index < 0:  # unknown id, keep it so we don't lose data
            combo.addItem(f"{id_value}: (unknown)", id_value)
            index = combo.findData(id_value)
        combo.setCurrentIndex(index)

    def _ability_id_json(self, type_id):
        """Return the id list appropriate for an ability of the given type."""
        if type_id == 2:    # Magic
            return self.game_data.magic_data_json['magic']
        if type_id == 4:    # Item
            return self.game_data.item_data_json['items']
        return self.game_data.enemy_abilities_data_json['abilities']  # Custom/Seifer/other

    # ── Tab: Stats ───────────────────────────────────────────────────────

    def _build_stats_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        # Name
        name_group = QGroupBox("Monster name")
        name_layout = QHBoxLayout(name_group)
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(24)
        self._name_edit.textEdited.connect(self._on_name_edited)
        name_layout.addWidget(self._name_edit)
        layout.addWidget(name_group)

        # Base stats (each is 4 raw bytes)
        stat_group = QGroupBox("Base stats (4 raw bytes each, feed the level formula)")
        grid = QGridLayout(stat_group)
        grid.addWidget(QLabel("Stat"), 0, 0)
        for i in range(4):
            grid.addWidget(QLabel(f"Byte {i}"), 0, i + 1)
        for row, stat in enumerate(self.game_data.stat_data_json['stat']):
            name = stat['name']
            grid.addWidget(QLabel(stat['name'].upper()), row + 1, 0)
            self._stat_spins[name] = []
            for i in range(4):
                spin = self._spin(AIData.STAT_MIN_VAL, AIData.STAT_MAX_VAL)
                spin.valueChanged.connect(partial(self._on_stat_changed, name, i))
                grid.addWidget(spin, row + 1, i + 1)
                self._stat_spins[name].append(spin)
        layout.addWidget(stat_group)

        # Misc values
        misc_group = QGroupBox("Miscellaneous")
        form = QFormLayout(misc_group)
        self._add_misc_int(form, 'med_lvl', "Med level start", 0, 255)
        self._add_misc_int(form, 'high_lvl', "High level start", 0, 255)
        self._add_misc_int(form, 'extra_xp', "Extra EXP", 0, 65535)
        self._add_misc_int(form, 'xp', "EXP", 0, 65535)
        self._add_misc_int(form, 'ap', "AP", 0, 255)
        self._add_misc_rate(form, 'mug_rate', "Mug rate %")
        self._add_misc_rate(form, 'drop_rate', "Drop rate %")
        self._add_misc_int(form, 'padding', "Padding (should be 0)", 0, 255)

        # Camera category (byte_flag_0) and Devour category (byte_flag_3) are
        # small integers, not real bitfields, so present them as spin boxes.
        self._camera_spin = self._spin(0, 255)
        self._camera_spin.setToolTip("Byte 246 - camera framing class (vanilla 0-4)")
        self._camera_spin.valueChanged.connect(partial(self._on_category_changed, 'byte_flag_0'))
        form.addRow("Camera category", self._camera_spin)

        self._devour_cat_spin = self._spin(0, 255)
        self._devour_cat_spin.setToolTip("Byte 255 - devour category (vanilla 0-8, 8 = inedible)")
        self._devour_cat_spin.valueChanged.connect(partial(self._on_category_changed, 'byte_flag_3'))
        form.addRow("Devour category", self._devour_cat_spin)

        layout.addWidget(misc_group)
        layout.addStretch(1)
        return self._scrollable(container)

    def _add_misc_int(self, form, key, label, minimum, maximum):
        spin = self._spin(minimum, maximum)
        spin.valueChanged.connect(partial(self._on_misc_int_changed, key))
        form.addRow(label, spin)
        self._misc_spins[key] = spin

    def _add_misc_rate(self, form, key, label):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(100 / 255)
        spin.valueChanged.connect(partial(self._on_misc_rate_changed, key))
        form.addRow(label, spin)
        self._misc_spins[key] = spin

    # ── Tab: Defense ─────────────────────────────────────────────────────

    def _build_defense_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)

        elem_group = QGroupBox("Elemental resistance % (higher = more resistant)")
        elem_form = QFormLayout(elem_group)
        for elem in self.game_data.magic_data_json['magic_type']:
            spin = self._spin(AIData.ELEM_DEF_MIN_VAL, AIData.ELEM_DEF_MAX_VAL, step=10)
            spin.setToolTip("100 = neutral, >100 resist/absorb, <100 weak")
            spin.valueChanged.connect(partial(self._on_elem_changed, elem['id']))
            elem_form.addRow(elem['name'], spin)
            self._elem_spins.append(spin)
        layout.addWidget(elem_group)

        status_group = QGroupBox("Status resistance % (155 = immune)")
        status_form = QFormLayout(status_group)
        for status in self.game_data.status_data_json['status']:
            spin = self._spin(AIData.STATUS_DEF_MIN_VAL, AIData.STATUS_DEF_MAX_VAL, step=5)
            spin.valueChanged.connect(partial(self._on_status_changed, status['id']))
            status_form.addRow(status['name'], spin)
            self._status_spins.append(spin)
        layout.addWidget(status_group)
        layout.addStretch(1)
        return self._scrollable(container)

    # ── Tab: Flags ───────────────────────────────────────────────────────

    def _build_flags_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._build_flag_group('byte_flag_1', "Byte flag 1",
                                                AIData.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE))
        layout.addWidget(self._build_flag_group('byte_flag_2', "Byte flag 2 (surprise / escape / card)",
                                                AIData.SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE))
        note = QLabel("Note: byte flag 0 and 3 are the Camera and Devour categories, "
                      "editable as integers in the Stats tab.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return self._scrollable(container)

    def _build_flag_group(self, flag_key, title, bit_names) -> QGroupBox:
        group = QGroupBox(title)
        form = QVBoxLayout(group)
        self._flag_checks[flag_key] = {}
        for bit_name in bit_names:
            check = QCheckBox(bit_name)
            check.toggled.connect(partial(self._on_flag_toggled, flag_key, bit_name))
            form.addWidget(check)
            self._flag_checks[flag_key][bit_name] = check
        return group

    # ── Tab: Loot ────────────────────────────────────────────────────────

    def _build_loot_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        top = QHBoxLayout()
        # Card
        card_group = QGroupBox("Card")
        card_form = QFormLayout(card_group)
        for label in ('Drop', 'Mod', 'Rare mod'):
            combo = self._combo_from_json(self.game_data.card_data_json['card_info'])
            index = len(self._card_combos)
            combo.activated.connect(partial(self._on_card_changed, index))
            card_form.addRow(label, combo)
            self._card_combos.append(combo)
        top.addWidget(card_group)

        # Devour
        devour_group = QGroupBox("Devour effect")
        devour_form = QFormLayout(devour_group)
        for label in ('Low', 'Medium', 'High'):
            combo = self._combo_from_json(self.game_data.devour_data_json['devour'])
            index = len(self._devour_combos)
            combo.activated.connect(partial(self._on_devour_changed, index))
            devour_form.addRow(label, combo)
            self._devour_combos.append(combo)
        top.addWidget(devour_group)
        top.addStretch(1)
        layout.addLayout(top)

        # Draw / Mug / Drop
        layout.addWidget(self._build_loot_group(
            "Draw (magic)", ['low_lvl_mag', 'med_lvl_mag', 'high_lvl_mag'],
            self.game_data.magic_data_json['magic'], value_label="Qty (unused for draw)"))
        layout.addWidget(self._build_loot_group(
            "Mug (item)", ['low_lvl_mug', 'med_lvl_mug', 'high_lvl_mug'],
            self.game_data.item_data_json['items'], value_label="Qty"))
        layout.addWidget(self._build_loot_group(
            "Drop (item)", ['low_lvl_drop', 'med_lvl_drop', 'high_lvl_drop'],
            self.game_data.item_data_json['items'], value_label="Qty"))
        layout.addStretch(1)
        return self._scrollable(container)

    def _build_loot_group(self, title, keys, json_list, value_label) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        for col, (key, tier) in enumerate(zip(keys, ('Low', 'Med', 'High'))):
            grid.addWidget(QLabel(f"<b>{tier}</b>"), 0, col * 2, 1, 2, Qt.AlignmentFlag.AlignCenter)
            self._loot_widgets[key] = []
            for row in range(4):
                combo = self._combo_from_json(json_list)
                combo.activated.connect(partial(self._on_loot_id_changed, key, row))
                value_spin = self._spin(0, 255)
                value_spin.setToolTip(value_label)
                value_spin.valueChanged.connect(partial(self._on_loot_value_changed, key, row))
                grid.addWidget(combo, row + 1, col * 2)
                grid.addWidget(value_spin, row + 1, col * 2 + 1)
                self._loot_widgets[key].append((combo, value_spin))
        return group

    # ── Tab: Abilities ───────────────────────────────────────────────────

    def _build_abilities_tab(self) -> QWidget:
        inner_tabs = QTabWidget()
        for key, title in zip(AIData.ABILITIES_HIGHNESS_ORDER, ("Low level", "Med level", "High level")):
            inner_tabs.addTab(self._build_ability_level(key), title)
        return inner_tabs

    def _build_ability_level(self, key) -> QWidget:
        container = QWidget()
        grid = QGridLayout(container)
        grid.addWidget(QLabel("<b>#</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Type</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Ability</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Anim seq</b>"), 0, 3)
        self._ability_widgets[key] = []
        for row in range(16):
            type_combo = self._combo_from_json(self.game_data.enemy_abilities_data_json['abilities_type'])
            id_combo = QComboBox()
            anim_spin = self._spin(0, 255)

            type_combo.activated.connect(partial(self._on_ability_type_changed, key, row))
            id_combo.activated.connect(partial(self._on_ability_id_changed, key, row))
            anim_spin.valueChanged.connect(partial(self._on_ability_anim_changed, key, row))

            grid.addWidget(QLabel(str(row)), row + 1, 0)
            grid.addWidget(type_combo, row + 1, 1)
            grid.addWidget(id_combo, row + 1, 2)
            grid.addWidget(anim_spin, row + 1, 3)
            self._ability_widgets[key].append((type_combo, id_combo, anim_spin))
        return self._scrollable(container)

    def _populate_ability_id_combo(self, id_combo, type_id, id_value):
        id_combo.blockSignals(True)
        id_combo.clear()
        for el in self._ability_id_json(type_id):
            id_combo.addItem(f"{el['id']}: {el['name']}", el['id'])
        self._set_combo_id(id_combo, id_value)
        id_combo.blockSignals(False)

    # ── Tab: Renzokuken ──────────────────────────────────────────────────

    def _build_renzokuken_tab(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.addRow(QLabel("Renzokuken finisher special actions (8 slots)"))
        for i in range(8):
            combo = self._combo_from_json(self.game_data.special_action_data_json['special_action'])
            combo.activated.connect(partial(self._on_renzokuken_changed, i))
            form.addRow(f"Value {i + 1}", combo)
            self._renzokuken_combos.append(combo)
        return self._scrollable(container)

    # ── Loading ──────────────────────────────────────────────────────────

    def load_data(self):
        """Re-read the current enemy's info_stat_data and refresh every widget."""
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None or not enemy.info_stat_data:
            return
        self._data = enemy.info_stat_data
        data = self._data
        self._loading = True
        try:
            # Name
            name = data.get('monster_name')
            self._name_edit.setText(name.get_str() if name is not None else "")

            # Stats
            for stat_name, spins in self._stat_spins.items():
                values = data.get(stat_name, [])
                for i, spin in enumerate(spins):
                    spin.setValue(values[i] if i < len(values) else 0)

            # Misc
            for key, spin in self._misc_spins.items():
                value = data.get(key, 0)
                if isinstance(spin, QDoubleSpinBox):
                    spin.setValue(float(value))
                else:
                    spin.setValue(int(value))

            # Categories (stored as bit dicts)
            self._camera_spin.setValue(self._flag_dict_to_int(data.get('byte_flag_0', {})))
            self._devour_cat_spin.setValue(self._flag_dict_to_int(data.get('byte_flag_3', {})))

            # Elemental / status defense
            for i, spin in enumerate(self._elem_spins):
                elem = data.get('elem_def', [])
                spin.setValue(elem[i] if i < len(elem) else 100)
            for i, spin in enumerate(self._status_spins):
                status = data.get('status_def', [])
                spin.setValue(status[i] if i < len(status) else 0)

            # Bit flags
            for flag_key, checks in self._flag_checks.items():
                flag_data = data.get(flag_key, {})
                for bit_name, check in checks.items():
                    check.setChecked(bool(flag_data.get(bit_name, 0)))

            # Card / Devour
            card = data.get('card', [0, 0, 0])
            for i, combo in enumerate(self._card_combos):
                self._set_combo_id(combo, card[i] if i < len(card) else 0)
            devour = data.get('devour', [0, 0, 0])
            for i, combo in enumerate(self._devour_combos):
                self._set_combo_id(combo, devour[i] if i < len(devour) else 0)

            # Draw / Mug / Drop
            for key, rows in self._loot_widgets.items():
                entries = data.get(key, [])
                for row, (combo, value_spin) in enumerate(rows):
                    entry = entries[row] if row < len(entries) else {'ID': 0, 'value': 0}
                    self._set_combo_id(combo, entry.get('ID', 0))
                    value_spin.setValue(entry.get('value', 0))

            # Abilities
            for key, rows in self._ability_widgets.items():
                entries = data.get(key, [])
                for row, (type_combo, id_combo, anim_spin) in enumerate(rows):
                    entry = entries[row] if row < len(entries) else {'type': 0, 'animation': 0, 'id': 0}
                    self._set_combo_id(type_combo, entry.get('type', 0))
                    self._populate_ability_id_combo(id_combo, entry.get('type', 0), entry.get('id', 0))
                    anim_spin.setValue(entry.get('animation', 0))

            # Renzokuken
            renzokuken = data.get('renzokuken', [])
            for i, combo in enumerate(self._renzokuken_combos):
                self._set_combo_id(combo, renzokuken[i] if i < len(renzokuken) else 0)
        finally:
            self._loading = False

    # ── Byte-flag <-> int conversion ─────────────────────────────────────

    @staticmethod
    def _flag_dict_to_int(flag_dict) -> int:
        value = 0
        for i, bit in enumerate(flag_dict.values()):
            value |= (int(bit) << i)
        return value

    @staticmethod
    def _int_to_flag_dict(value, bit_names) -> dict:
        return {name: (value >> i) & 1 for i, name in enumerate(bit_names)}

    # ── Write-back handlers ──────────────────────────────────────────────

    def _on_name_edited(self, text):
        if self._loading or self._data is None:
            return
        self._data['monster_name'].set_str(text)

    def _on_stat_changed(self, stat_name, index, value):
        if self._loading or self._data is None:
            return
        self._data[stat_name][index] = value

    def _on_misc_int_changed(self, key, value):
        if self._loading or self._data is None:
            return
        self._data[key] = value

    def _on_misc_rate_changed(self, key, value):
        if self._loading or self._data is None:
            return
        self._data[key] = value

    def _on_category_changed(self, flag_key, value):
        if self._loading or self._data is None:
            return
        if flag_key == 'byte_flag_0':
            names = AIData.SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE
        else:
            names = AIData.SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE
        self._data[flag_key] = self._int_to_flag_dict(value, names)

    def _on_elem_changed(self, index, value):
        if self._loading or self._data is None:
            return
        self._data['elem_def'][index] = value

    def _on_status_changed(self, index, value):
        if self._loading or self._data is None:
            return
        self._data['status_def'][index] = value

    def _on_flag_toggled(self, flag_key, bit_name, checked):
        if self._loading or self._data is None:
            return
        self._data[flag_key][bit_name] = int(checked)

    def _on_card_changed(self, index, _combo_index):
        if self._loading or self._data is None:
            return
        self._data['card'][index] = self._card_combos[index].currentData()

    def _on_devour_changed(self, index, _combo_index):
        if self._loading or self._data is None:
            return
        self._data['devour'][index] = self._devour_combos[index].currentData()

    def _on_loot_id_changed(self, key, row, _combo_index):
        if self._loading or self._data is None:
            return
        combo, _ = self._loot_widgets[key][row]
        self._data[key][row]['ID'] = combo.currentData()

    def _on_loot_value_changed(self, key, row, value):
        if self._loading or self._data is None:
            return
        self._data[key][row]['value'] = value

    def _on_ability_type_changed(self, key, row, _combo_index):
        if self._loading or self._data is None:
            return
        type_combo, id_combo, _ = self._ability_widgets[key][row]
        type_id = type_combo.currentData()
        self._data[key][row]['type'] = type_id
        # Repopulate the ability list for the new type, keeping the id if valid.
        current_id = id_combo.currentData()
        self._populate_ability_id_combo(id_combo, type_id, current_id if current_id is not None else 0)
        self._data[key][row]['id'] = id_combo.currentData()

    def _on_ability_id_changed(self, key, row, _combo_index):
        if self._loading or self._data is None:
            return
        _, id_combo, _ = self._ability_widgets[key][row]
        self._data[key][row]['id'] = id_combo.currentData()

    def _on_ability_anim_changed(self, key, row, value):
        if self._loading or self._data is None:
            return
        self._data[key][row]['animation'] = value

    def _on_renzokuken_changed(self, index, _combo_index):
        if self._loading or self._data is None:
            return
        self._data['renzokuken'][index] = self._renzokuken_combos[index].currentData()
