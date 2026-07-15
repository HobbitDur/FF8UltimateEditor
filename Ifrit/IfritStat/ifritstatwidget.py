"""Local editor for section 7 (Informations & stats) of a monster c0mxxx.dat file.

Unlike the Excel round-trip tab (StatExcel), this tab edits the already-parsed
``ifrit_manager.enemy.info_stat_data`` dictionary in place, so every change is
immediately reflected in the loaded monster and written out by the shared Save
button. It mirrors the exact analyse/prepare logic of ``MonsterAnalyser`` so the
values shown here match what gets serialized back to the .dat file.
"""
from functools import partial
from math import floor

from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QComboBox, QCheckBox, QGroupBox,
    QTabWidget, QScrollArea, QPlainTextEdit, QSizePolicy, QToolButton,
)

from FF8GameData.monsterdata import AIData
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from SmallWidget.nowheel import NoWheelComboBox, NoWheelSpinBox


# Tooltips describing the four raw stat bytes and how the engine turns them into
# the value shown in-game at a given level L.
STAT_TOOLTIPS = {
    'hp': "HP curve, 4 raw bytes (0-255).\nHP = floor(b0*(L*L/20+L)) + 10*b1 + b2*100*L + 1000*b3  (L = level)",
    'str': "STR curve, 4 raw bytes (0-255).\nSTR = floor(L*b0/40) + floor(L/(4*b1)) + floor(b2/4) + floor(L*L/(8*b3))",
    'mag': "MAG curve, 4 raw bytes (0-255).\nMAG = floor(L*b0/40) + floor(L/(4*b1)) + floor(b2/4) + floor(L*L/(8*b3))",
    'vit': "VIT curve, 4 raw bytes (0-255).\nVIT = L*b0 + floor(L/b1) + b2 - floor(L/b3)",
    'spr': "SPR curve, 4 raw bytes (0-255).\nSPR = L*b0 + floor(L/b1) + b2 - floor(L/b3)",
    'spd': "SPD curve, 4 raw bytes (0-255).\nSPD = L*b0 + floor(L/b1) + b2 - floor(L/b3)",
    'eva': "EVA curve, 4 raw bytes (0-255).\nEVA = L*b0 + floor(L/b1) + b2 - floor(L/b3)",
}

# Per-stat curve colours used by the live plot / legend.
STAT_COLORS = {
    'hp': '#e0564b', 'str': '#e08a3c', 'vit': '#c9b03a', 'mag': '#4b8fe0',
    'spr': '#9a6fd0', 'spd': '#3cc0c0', 'eva': '#d05fb0',
}

# Placeholder bit names in AIData mapped to their real wiki meaning for display.
# (The canonical dict keys are kept unchanged for round-trip compatibility.)
FLAG_DISPLAY_NAMES = {
    'byte1_zz1': 'unused (bit 0x04 - no effect)',
    'Immune NVPlus_Moins': 'LvUp-Down Immunity',
    'Hidden HP': 'HP Hidden',
    'byte2_unused_6': 'unused',
    'Diablos-missed': 'Gravity Immunity',
}

# Flag bits the loader never reads — shown but not editable.
UNUSED_FLAG_BITS = {'byte1_zz1', 'byte2_unused_6'}


class StatCurvePlot(QWidget):
    """Lightweight QPainter plot of each stat's value across levels 1-100."""

    LEVELS = list(range(1, 101))

    def __init__(self, stat_names):
        super().__init__()
        self._stat_names = stat_names
        self._series = {}   # name -> [display y per level]
        self._labels = {}   # name -> legend label
        self.setMinimumSize(360, 300)
        self.setToolTip("Resulting stat value per level (1-100) for the current bytes.\n"
                        "HP is drawn divided by 100 so every curve stays visible.")

    def set_data(self, stats):
        self._series, self._labels = {}, {}
        for name in self._stat_names:
            byte_values = stats.get(name)
            if not byte_values or len(byte_values) < 4:
                continue
            ys = [self._stat_value(name, byte_values, level) for level in self.LEVELS]
            if name == 'hp':
                ys = [y / 100 for y in ys]
                self._labels[name] = 'HP/100'
            else:
                self._labels[name] = name.upper()
            self._series[name] = ys
        self.update()

    @staticmethod
    def _stat_value(name, b, level):
        b0, b1, b2, b3 = b[0], b[1], b[2], b[3]
        if name == 'hp':
            return floor(b0 * (level * level / 20 + level)) + 10 * b1 + b2 * 100 * level + 1000 * b3
        if name in ('str', 'mag'):
            return (floor(level * b0 / 40) + (floor(level / (4 * b1)) if b1 else 0)
                    + floor(b2 / 4) + (floor(level * level / (8 * b3)) if b3 else 0))
        # vit / spr / spd / eva
        return level * b0 + (floor(level / b1) if b1 else 0) + b2 - (floor(level / b3) if b3 else 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        left, right, top, bottom = 48, 12, 12, 26
        x0, y0 = left, height - bottom            # bottom-left origin
        x1, y1 = width - right, top               # top-right corner
        painter.fillRect(self.rect(), QColor('#20232a'))

        max_y = 1.0
        for ys in self._series.values():
            if ys:
                max_y = max(max_y, max(ys))

        painter.setFont(QFont('', 7))
        # Horizontal gridlines + Y labels
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            yy = int(y0 - frac * (y0 - y1))
            painter.setPen(QPen(QColor('#333842')))
            painter.drawLine(x0, yy, x1, yy)
            painter.setPen(QPen(QColor('#9aa0aa')))
            painter.drawText(2, yy + 3, f"{max_y * frac:.0f}")
        # Axes
        painter.setPen(QPen(QColor('#8a8f99')))
        painter.drawLine(x0, y0, x1, y0)
        painter.drawLine(x0, y0, x0, y1)
        for level in (1, 25, 50, 75, 100):
            xx = int(x0 + (level - 1) / 99 * (x1 - x0))
            painter.drawText(xx - 6, y0 + 14, str(level))

        # Curves
        for name, ys in self._series.items():
            painter.setPen(QPen(QColor(STAT_COLORS.get(name, '#ffffff')), 1.6))
            poly = QPolygonF()
            for i, level in enumerate(self.LEVELS):
                xx = x0 + (level - 1) / 99 * (x1 - x0)
                yy = y0 - (ys[i] / max_y) * (y0 - y1)
                poly.append(QPointF(xx, yy))
            painter.drawPolyline(poly)

        # Legend (top-left inside the plot)
        lx, ly = x0 + 6, y1 + 4
        for name in self._series:
            painter.fillRect(lx, ly, 9, 9, QColor(STAT_COLORS.get(name, '#ffffff')))
            painter.setPen(QColor('#d0d0d0'))
            painter.drawText(lx + 12, ly + 8, self._labels[name])
            ly += 12
        painter.end()


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
        self._stat_plot = None       # StatCurvePlot
        self._formula_popup = None   # IfritFormulaPopup, created lazily, reused per stat
        self._elem_spins = []        # [8 QSpinBox]
        self._status_spins = []      # [20 QSpinBox]
        self._flag_checks = {}       # byte_flag_name -> {bit_name: QCheckBox}
        self._camera_combo = None    # byte_flag_0 (camera category)
        self._devour_cat_combo = None  # byte_flag_3 (devour category)
        self._misc_spins = {}        # misc name -> QSpinBox
        self._card_combos = []       # [3 QComboBox]
        self._devour_combos = []     # [3 QComboBox]
        self._loot_widgets = {}      # loot key -> [(id_combo, value_spin) x4]
        self._ability_widgets = {}   # ability key -> [(type_combo, id_combo, anim_spin) x16]
        self._ability_seq_view = {}  # ability key -> QPlainTextEdit (read-only anim seq viewer)
        self._anim_spin_level = {}   # QSpinBox -> ability key (for focus tracking)
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
    def _spin(minimum, maximum, step=1, tooltip="", compact=False) -> QSpinBox:
        spin = NoWheelSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        if compact:  # don't let the layout stretch it past what its digits need
            spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if tooltip:
            spin.setToolTip(tooltip)
        return spin

    def _new_combo(self, tooltip="", max_chars=None, compact=False) -> QComboBox:
        """Empty combo. max_chars caps the box width to N chars regardless of the
        longest item (long text just elides — full text is always in the hover);
        compact stops the layout from stretching it wider than that."""
        combo = NoWheelComboBox()
        if max_chars is not None:
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(max_chars)
        if compact:
            combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        combo.setProperty('_base_tip', tooltip)
        combo.currentIndexChanged.connect(lambda _, c=combo: IfritStatWidget._refresh_combo_tooltip(c))
        return combo

    def _combo_from_json(self, json_list, tooltip="", max_chars=None, compact=False) -> QComboBox:
        combo = self._new_combo(tooltip, max_chars, compact)
        for index, el in enumerate(json_list):
            combo.addItem(f"{el['id']}: {el['name']}", el['id'])
            if el.get('desc'):  # per-entry hover text when the list provides one
                combo.setItemData(index, el['desc'], Qt.ItemDataRole.ToolTipRole)
        self._refresh_combo_tooltip(combo)
        return combo

    @staticmethod
    def _refresh_combo_tooltip(combo: QComboBox):
        """Keep the box's own hover text showing the full current selection —
        needed once max_chars starts eliding the visible text."""
        base = combo.property('_base_tip') or ""
        current = combo.currentText()
        if current and base:
            combo.setToolTip(f"{current}\n\n{base}")
        else:
            combo.setToolTip(current or base)

    @staticmethod
    def _set_combo_id(combo: QComboBox, id_value):
        index = combo.findData(id_value)
        if index < 0:  # unknown id, keep it so we don't lose data
            combo.addItem(f"{id_value}: (unknown)", id_value)
            index = combo.findData(id_value)
        combo.setCurrentIndex(index)
        IfritStatWidget._refresh_combo_tooltip(combo)

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
        self._name_edit.setToolTip("Monster name, max 24 bytes in the FF8 text encoding.")
        self._name_edit.textEdited.connect(self._on_name_edited)
        name_layout.addWidget(self._name_edit)
        layout.addWidget(name_group)

        # Base stats (each is 4 raw bytes) + live plot of the resulting values.
        stat_group = QGroupBox("Base stats (4 raw bytes each, feed the per-level formula)")
        stat_group_layout = QVBoxLayout(stat_group)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.addWidget(QLabel("Stat"), 0, 0, Qt.AlignmentFlag.AlignRight)
        for i in range(4):
            grid.addWidget(QLabel(f"Byte {i}"), 0, i + 1)
        # Keep the stat name + 4 byte columns + f(x) button tight together; push slack to col 6.
        grid.setColumnStretch(6, 1)
        for row, stat in enumerate(self.game_data.stat_data_json['stat']):
            name = stat['name']
            tooltip = STAT_TOOLTIPS.get(name, f"{name.upper()} curve, 4 raw bytes (0-255).")
            label = QLabel(stat['name'].upper())
            label.setToolTip(tooltip)
            grid.addWidget(label, row + 1, 0, Qt.AlignmentFlag.AlignRight)
            self._stat_spins[name] = []
            for i in range(4):
                spin = self._spin(AIData.STAT_MIN_VAL, AIData.STAT_MAX_VAL, tooltip=tooltip)
                spin.valueChanged.connect(partial(self._on_stat_changed, name, i))
                grid.addWidget(spin, row + 1, i + 1)
                self._stat_spins[name].append(spin)
            formula_btn = QToolButton()
            formula_btn.setText("ƒ(x)")
            formula_btn.setAutoRaise(True)
            formula_btn.setToolTip(f"View the {name.upper()} formula and evaluate it at any level.")
            formula_btn.clicked.connect(partial(self._open_formula_popup, name))
            grid.addWidget(formula_btn, row + 1, 5)
        stat_group_layout.addLayout(grid)

        self._stat_plot = StatCurvePlot([s['name'] for s in self.game_data.stat_data_json['stat']])
        stat_group_layout.addWidget(self._stat_plot)
        layout.addWidget(stat_group)

        # Misc values
        misc_group = QGroupBox("Miscellaneous")
        form = QFormLayout(misc_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self._add_misc_int(form, 'med_lvl', "Med level start", 0, 255,
                           "Monster level at which it switches to the medium stat/ability set (0-255).")
        self._add_misc_int(form, 'high_lvl', "High level start", 0, 255,
                           "Monster level at which it switches to the high stat/ability set (0-255).")
        self._add_misc_int(form, 'extra_xp', "Extra EXP", 0, 65535, "Bonus EXP granted (0-65535).")
        self._add_misc_int(form, 'xp', "EXP", 0, 65535, "Base EXP granted on kill (0-65535).")
        self._add_misc_int(form, 'ap', "AP", 0, 255, "AP granted on kill (0-255).")
        self._add_misc_int(
            form, 'mug_rate', "Mug rate (raw 0-255)", 0, 255,
            "Raw steal-rate byte (0-255), NOT a percent.\n"
            "Engine (getMugObjectIdAndQuantity): 0 = never steal; otherwise the mug\n"
            "succeeds when random(0..255) <= MugRate + attacker_SPD/2.\n"
            "So base chance ≈ (MugRate + 1) / 256  (e.g. 128 ≈ 50.4%, 255 = 100%).")
        self._add_misc_int(
            form, 'drop_rate', "Drop rate (raw 0-255)", 0, 255,
            "Raw drop-rate byte (0-255), NOT a percent.\n"
            "Engine (ComputeProbabilityGetItemMug): the drop succeeds when\n"
            "random(0..255) <= DropRate.\n"
            "So chance ≈ (DropRate + 1) / 256  (e.g. 128 ≈ 50.4%, 255 = 100%, 0 ≈ 0.4%).")
        self._add_misc_int(form, 'padding', "Padding (unused, read-only)", 0, 255,
                           "Unused padding byte (offset 334). Always 0 — shown read-only.",
                           read_only=True)

        # Camera category (byte_flag_0) and Devour category (byte_flag_3) are
        # small integers, not real bitfields, so present them as named combos.
        camera_tip = ("Byte 246 — camera framing class.\n"
                      "Read once at battle start and converted into the entity's cameraDataRelated,\n"
                      "which the battle camera uses as a size/distance class (it is what pulls the\n"
                      "camera back further for large enemies). Vanilla monsters use 0-4.\n"
                      "Hover an entry for what it becomes.")
        self._camera_combo = self._combo_from_json(
            self.game_data.camera_category_data_json['camera_category'],
            tooltip=camera_tip, max_chars=34, compact=True)
        self._camera_combo.activated.connect(partial(self._on_category_changed, 'byte_flag_0'))
        form.addRow(self._info_label("Camera category (byte 246)", camera_tip), self._camera_combo)

        devour_tip = ("Byte 255 — devour classification consumed by the Devour system.\n"
                      "8 = inedible (every boss); it is also the failure code the engine writes on a\n"
                      "missed devour. On PC it only affects the invisible 0-7 phantom devour damage.\n"
                      "Hover an entry for the monsters that use it.")
        self._devour_cat_combo = self._combo_from_json(
            self.game_data.devour_category_data_json['devour_category'],
            tooltip=devour_tip, max_chars=16, compact=True)
        self._devour_cat_combo.activated.connect(partial(self._on_category_changed, 'byte_flag_3'))
        form.addRow(self._info_label("Devour category (byte 255)", devour_tip), self._devour_cat_combo)

        layout.addWidget(misc_group)
        layout.addStretch(1)
        return self._scrollable(container)

    def _open_formula_popup(self, stat_name):
        if self._formula_popup is None:
            from .ifritformulapopup import IfritFormulaPopup
            self._formula_popup = IfritFormulaPopup(self, self)
        self._formula_popup.show_for(stat_name)

    @staticmethod
    def _info_label(text, tooltip) -> QLabel:
        label = QLabel(text)
        label.setToolTip(tooltip)
        return label

    def _add_misc_int(self, form, key, label, minimum, maximum, tooltip="", read_only=False):
        spin = self._spin(minimum, maximum, tooltip=tooltip, compact=True)
        if read_only:
            spin.setReadOnly(True)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        else:
            spin.valueChanged.connect(partial(self._on_misc_int_changed, key))
        form.addRow(self._info_label(label, tooltip) if tooltip else label, spin)
        self._misc_spins[key] = spin

    # ── Tab: Defense ─────────────────────────────────────────────────────

    def _build_defense_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)

        elem_group = QGroupBox("Elemental resistance %")
        elem_form = QFormLayout(elem_group)
        elem_tip = ("Elemental resistance %, range {0}..{1} (step 10 = 1 raw unit).\n"
                    "100 = neutral, >100 = resistant, <100 = weak.\n"
                    "Stored byte = floor((900 - %) / 10)."
                    ).format(AIData.ELEM_DEF_MIN_VAL, AIData.ELEM_DEF_MAX_VAL)
        elem_group.setToolTip(elem_tip)
        for elem in self.game_data.magic_data_json['magic_type']:
            spin = self._spin(AIData.ELEM_DEF_MIN_VAL, AIData.ELEM_DEF_MAX_VAL, step=10, tooltip=elem_tip)
            spin.valueChanged.connect(partial(self._on_elem_changed, elem['id']))
            row_label = QLabel(elem['name'])
            row_label.setToolTip(elem_tip)
            elem_form.addRow(row_label, spin)
            self._elem_spins.append(spin)
        layout.addWidget(elem_group)

        status_group = QGroupBox("Status resistance %")
        status_form = QFormLayout(status_group)
        status_tip = ("Status resistance %, range {0}..{1}.\n"
                      "0 = fully vulnerable, higher = more resistant, 155 = immune.\n"
                      "Stored byte = % + 100."
                      ).format(AIData.STATUS_DEF_MIN_VAL, AIData.STATUS_DEF_MAX_VAL)
        status_group.setToolTip(status_tip)
        for status in self.game_data.status_data_json['status']:
            spin = self._spin(AIData.STATUS_DEF_MIN_VAL, AIData.STATUS_DEF_MAX_VAL, step=5, tooltip=status_tip)
            spin.valueChanged.connect(partial(self._on_status_changed, status['id']))
            row_label = QLabel(status['name'])
            row_label.setToolTip(status_tip)
            status_form.addRow(row_label, spin)
            self._status_spins.append(spin)
        layout.addWidget(status_group)
        layout.addStretch(1)
        return self._scrollable(container)

    # ── Tab: Flags ───────────────────────────────────────────────────────

    def _build_flags_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._build_flag_group(
            'byte_flag_1', "Byte flag 1 (byte 247) — auto-status & behavior",
            AIData.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE,
            "Bitfield at offset 247. Each box is one on/off flag."))
        layout.addWidget(self._build_flag_group(
            'byte_flag_2', "Byte flag 2 (byte 254) — surprise / escape / card",
            AIData.SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE,
            "Bitfield at offset 254. Each box is one on/off flag."))
        note = QLabel("Note: byte flag 0 and 3 are the Camera and Devour categories, "
                      "editable as lists in the Stats tab.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return self._scrollable(container)

    def _build_flag_group(self, flag_key, title, bit_names, tooltip) -> QGroupBox:
        group = QGroupBox(title)
        group.setToolTip(tooltip)
        form = QVBoxLayout(group)
        self._flag_checks[flag_key] = {}
        for bit_index, bit_name in enumerate(bit_names):
            display_name = FLAG_DISPLAY_NAMES.get(bit_name, bit_name)
            check = QCheckBox(f"bit {bit_index} (0x{1 << bit_index:02X}) - {display_name}")
            if bit_name in UNUSED_FLAG_BITS:
                # Read-only: this bit is never read by the loader.
                check.setEnabled(False)
                check.setToolTip(f"Unused bit, never read by the game — read-only.\nCanonical field: '{bit_name}'.")
            else:
                check.setToolTip(f"{tooltip}\nCanonical field: '{bit_name}'.")
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
        card_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        card_tips = {
            'Drop': "Card that can drop on kill (255 = none).",
            'Mod': "Card obtained from card-mod (255 = none).",
            'Rare mod': "Rare card-mod result (255 = none).",
        }
        for label in ('Drop', 'Mod', 'Rare mod'):
            combo = self._combo_from_json(self.game_data.card_data_json['card_info'],
                                          tooltip=card_tips[label], max_chars=18, compact=True)
            index = len(self._card_combos)
            combo.activated.connect(partial(self._on_card_changed, index))
            card_form.addRow(label, combo)
            self._card_combos.append(combo)
        top.addWidget(card_group)

        # Devour
        devour_group = QGroupBox("Devour effect")
        devour_form = QFormLayout(devour_group)
        devour_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        devour_tips = {
            'Low': "Devour effect when monster level < med start.",
            'Medium': "Devour effect for med level tier.",
            'High': "Devour effect for high level tier.",
        }
        for label in ('Low', 'Medium', 'High'):
            combo = self._combo_from_json(self.game_data.devour_data_json['devour'],
                                          tooltip=devour_tips[label], max_chars=18, compact=True)
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
            self.game_data.magic_data_json['magic'],
            id_tip="Magic that can be drawn (per level tier).",
            value_tip="Quantity field (0-255). Unused for draw — the drawn amount is computed at runtime."))
        layout.addWidget(self._build_loot_group(
            "Mug (item)", ['low_lvl_mug', 'med_lvl_mug', 'high_lvl_mug'],
            self.game_data.item_data_json['items'],
            id_tip="Item that can be stolen/mugged (per level tier).",
            value_tip="Quantity stolen (0-255)."))
        layout.addWidget(self._build_loot_group(
            "Drop (item)", ['low_lvl_drop', 'med_lvl_drop', 'high_lvl_drop'],
            self.game_data.item_data_json['items'],
            id_tip="Item that can drop on kill (per level tier).",
            value_tip="Quantity dropped (0-255)."))
        layout.addStretch(1)
        return self._scrollable(container)

    def _build_loot_group(self, title, keys, json_list, id_tip, value_tip) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        for col, (key, tier) in enumerate(zip(keys, ('Low', 'Med', 'High'))):
            grid.addWidget(QLabel(f"<b>{tier}</b>"), 0, col * 2, 1, 2, Qt.AlignmentFlag.AlignCenter)
            self._loot_widgets[key] = []
            for row in range(4):
                combo = self._combo_from_json(json_list, tooltip=id_tip, max_chars=20, compact=True)
                combo.activated.connect(partial(self._on_loot_id_changed, key, row))
                value_spin = self._spin(0, 255, tooltip=value_tip, compact=True)
                value_spin.valueChanged.connect(partial(self._on_loot_value_changed, key, row))
                grid.addWidget(combo, row + 1, col * 2)
                grid.addWidget(value_spin, row + 1, col * 2 + 1)
                self._loot_widgets[key].append((combo, value_spin))
        grid.setColumnStretch(len(keys) * 2, 1)  # trailing spacer soaks leftover width
        return group

    # ── Tab: Abilities ───────────────────────────────────────────────────

    def _build_abilities_tab(self) -> QWidget:
        inner_tabs = QTabWidget()
        for key, title in zip(AIData.ABILITIES_HIGHNESS_ORDER, ("Low level", "Med level", "High level")):
            inner_tabs.addTab(self._build_ability_level(key), title)
        return inner_tabs

    def _build_ability_level(self, key) -> QWidget:
        # Left: the 16 ability rows. Right: read-only anim-sequence viewer.
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)

        rows_container = QWidget()
        grid = QGridLayout(rows_container)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        # Every column sized to its own content; the trailing spacer (col 4)
        # soaks any leftover width instead of stretching the combos.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 0)
        grid.setColumnStretch(4, 1)
        hdr = QLabel("#")
        hdr.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(hdr, 0, 0)
        grid.addWidget(QLabel("<b>Type</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Ability</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Anim seq</b>"), 0, 3)

        self._ability_widgets[key] = []
        for row in range(16):
            type_combo = self._combo_from_json(
                self.game_data.enemy_abilities_data_json['abilities_type'],
                tooltip="Ability category. Changing it reloads the Ability list "
                        "(Magic → magic, Item → item, else → enemy abilities).",
                max_chars=14, compact=True)
            id_combo = self._new_combo(tooltip="The magic / item / enemy ability performed.",
                                       max_chars=26, compact=True)
            anim_spin = self._spin(
                0, 255, compact=True,
                tooltip="Animation Sequence ID → a sequence in Section 5.\n"
                        "Select this cell to preview its hex + translation on the right.")

            type_combo.activated.connect(partial(self._on_ability_type_changed, key, row))
            id_combo.activated.connect(partial(self._on_ability_id_changed, key, row))
            anim_spin.valueChanged.connect(partial(self._on_ability_anim_changed, key, row))
            # Track focus so selecting a row shows its anim sequence on the right.
            anim_spin.installEventFilter(self)
            self._anim_spin_level[anim_spin] = key

            index_label = QLabel(str(row))
            index_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(index_label, row + 1, 0)
            grid.addWidget(type_combo, row + 1, 1)
            grid.addWidget(id_combo, row + 1, 2)
            grid.addWidget(anim_spin, row + 1, 3)
            self._ability_widgets[key].append((type_combo, id_combo, anim_spin))

        # Pin the rows panel to its content width so it never grows beyond what
        # the 16 rows need — all the leftover horizontal space goes to the
        # anim-seq viewer instead. QScrollArea.sizeHint() is internally clamped
        # by Qt to an arbitrary ~36-character width, and a Maximum size policy
        # follows THAT (broken) sizeHint rather than maximumWidth() — so a fixed
        # min==max width, bypassing sizeHint entirely, is the only reliable way
        # to size it from the grid's real content width.
        rows_scroll = self._scrollable(rows_container)
        target_width = (rows_container.sizeHint().width()
                        + rows_scroll.verticalScrollBar().sizeHint().width() + 8)
        rows_scroll.setMinimumWidth(target_width)
        rows_scroll.setMaximumWidth(target_width)
        rows_scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        outer_layout.addWidget(rows_scroll)

        # Read-only anim-sequence viewer (hex + translation of the selected row).
        seq_group = QGroupBox("Anim sequence (read-only)")
        seq_layout = QVBoxLayout(seq_group)
        seq_view = QPlainTextEdit()
        seq_view.setReadOnly(True)
        seq_view.setPlaceholderText("Select an 'Anim seq' cell to preview its Section 5 sequence.")
        seq_layout.addWidget(seq_view)
        self._ability_seq_view[key] = seq_view
        outer_layout.addWidget(seq_group, 1)  # the only stretch-eligible widget: takes all leftover width

        return outer

    def _populate_ability_id_combo(self, id_combo, type_id, id_value):
        id_combo.blockSignals(True)
        id_combo.clear()
        for el in self._ability_id_json(type_id):
            id_combo.addItem(f"{el['id']}: {el['name']}", el['id'])
        self._set_combo_id(id_combo, id_value)
        id_combo.blockSignals(False)

    # ── Anim-sequence read-only preview ──────────────────────────────────

    def _anim_seq_lookup(self):
        """Return {seq_id: bytearray} for the loaded monster's Section 5 sequences."""
        enemy = getattr(self.ifrit_manager, "enemy", None)
        seq_section = getattr(enemy, "seq_animation_data", None) if enemy else None
        if not seq_section:
            return {}
        return {seq['id']: seq['data'] for seq in seq_section.get('seq_animation_data', [])}

    def _render_anim_seq_text(self, anim_id):
        lookup = self._anim_seq_lookup()
        if anim_id not in lookup:
            available = ", ".join(str(k) for k in sorted(lookup)) or "none"
            return f"Anim seq id {anim_id}\n\nNo Section 5 sequence with this id.\nAvailable ids: {available}"
        data = lookup[anim_id]
        hex_str = ' '.join(f"{b:02X}" for b in data) if data else "(empty)"
        try:
            translation = SequenceAnalyser(
                game_data=self.game_data,
                model_anim_data=self.ifrit_manager.enemy.model_animation_data,
                sequence=data).get_text()
        except Exception as exc:  # keep the viewer robust against odd data
            translation = f"(could not translate: {exc})"
        return f"Anim seq id {anim_id}  ({len(data)} bytes)\n\nHex:\n{hex_str}\n\nTranslation:\n{translation}"

    def _update_anim_seq_view(self, level_key, anim_id):
        view = self._ability_seq_view.get(level_key)
        if view is not None:
            view.setPlainText(self._render_anim_seq_text(anim_id))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and obj in self._anim_spin_level:
            self._update_anim_seq_view(self._anim_spin_level[obj], obj.value())
        return super().eventFilter(obj, event)

    # ── Tab: Renzokuken ──────────────────────────────────────────────────

    def _build_renzokuken_tab(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.addRow(QLabel("Renzokuken finisher attack animations (8 slots)"))
        tip = "Attack animation triggered for this Renzokuken finisher slot."
        for i in range(8):
            combo = self._combo_from_json(
                self.game_data.attack_animation_data_json['attack_animation'],
                tooltip=tip, max_chars=26, compact=True)
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

            # Misc — mug_rate / drop_rate are stored as % floats; show the raw byte.
            for key, spin in self._misc_spins.items():
                value = data.get(key, 0)
                if key in ('mug_rate', 'drop_rate'):
                    spin.setValue(self._rate_pct_to_raw(value))
                else:
                    spin.setValue(int(value))

            # Categories (stored as bit dicts, edited as small ints)
            self._set_combo_id(self._camera_combo, self._flag_dict_to_int(data.get('byte_flag_0', {})))
            self._set_combo_id(self._devour_cat_combo, self._flag_dict_to_int(data.get('byte_flag_3', {})))

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

            # Refresh the anim-seq preview for the first row of each level.
            for key, rows in self._ability_widgets.items():
                self._update_anim_seq_view(key, rows[0][2].value() if rows else 0)

            self._refresh_plot()
        finally:
            self._loading = False

    def _refresh_plot(self):
        if self._stat_plot is None:
            return
        stats = {name: [sp.value() for sp in spins] for name, spins in self._stat_spins.items()}
        self._stat_plot.set_data(stats)

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

    # ── Mug/drop rate <-> raw byte conversion ────────────────────────────
    # info_stat_data stores the rate as a % float (raw * 100 / 255); we edit the
    # raw 0-255 byte the engine actually compares against random(0..255).

    @staticmethod
    def _rate_pct_to_raw(pct) -> int:
        return max(0, min(255, round(pct * 255 / 100)))

    @staticmethod
    def _rate_raw_to_pct(raw) -> float:
        return raw * 100 / 255

    # ── Write-back handlers ──────────────────────────────────────────────

    def _on_name_edited(self, text):
        if self._loading or self._data is None:
            return
        self._data['monster_name'].set_str(text)

    def _on_stat_changed(self, stat_name, index, value):
        if self._loading or self._data is None:
            return
        self._data[stat_name][index] = value
        self._refresh_plot()

    def _on_misc_int_changed(self, key, value):
        if self._loading or self._data is None:
            return
        if key in ('mug_rate', 'drop_rate'):
            self._data[key] = self._rate_raw_to_pct(value)
        else:
            self._data[key] = value

    def _on_category_changed(self, flag_key, _combo_index):
        if self._loading or self._data is None:
            return
        if flag_key == 'byte_flag_0':
            combo = self._camera_combo
            names = AIData.SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE
        else:
            combo = self._devour_cat_combo
            names = AIData.SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE
        self._data[flag_key] = self._int_to_flag_dict(combo.currentData(), names)

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
        # Keep the read-only preview in sync with the edited value.
        self._update_anim_seq_view(key, value)

    def _on_renzokuken_changed(self, index, _combo_index):
        if self._loading or self._data is None:
            return
        self._data['renzokuken'][index] = self._renzokuken_combos[index].currentData()
