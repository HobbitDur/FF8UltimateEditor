"""
Table view of the NPC card players tab: every card player on one sortable row, and bulk edits
applied to the selected rows (or every visible row when nothing is selected).

The operations themselves are in cardgamebulk.py; this widget only picks them and shows the
result. Double-clicking a row opens that player in the editor view.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QLineEdit, QCheckBox, QComboBox,
                             QSpinBox, QPushButton, QLabel, QGroupBox, QStackedWidget)

from CCGroup import cardgamebulk as bulk
from CCGroup.jsmcardgame import (GAME_RULE_BITS, TRADE_RULE_NAMES, AI_STRATEGY_NAMES,
                                 PARAM_DECK_ID, PARAM_GAME_RULES, PARAM_TRADE_RULES, PARAM_RARE_CHANCE,
                                 PARAM_AI_SEARCH, PARAM_AI_STRATEGY, PARAM_LEVEL_MASK)
from CCGroup import cardlocation

TEST_MAP_PREFIX = "test"
MODIFIED_COLOR = QColor(255, 170, 60)

# (header, params shown in the column (to flag modified cells), tooltip)
COLUMNS = [
    ("Map", [], "Field map (.jsm file)"),
    ("NPC", [], "Entity that starts the match"),
    ("Script", [], "Script of the entity holding the CARDGAME call"),
    ("Variant", [], "When the script holds several CARDGAME calls: which one, and its odds or condition"),
    ("Deck ID", [PARAM_DECK_ID], "Rare card location (see the editor's Deck ID picker)"),
    ("Rare card", [PARAM_DECK_ID], "Rare card that starts the game at this Deck ID"),
    ("Rare %", [PARAM_RARE_CHANCE], "Rare card chance"),
    ("Rules", [PARAM_GAME_RULES], "Game rules ('region' = the rules spread by the Queen of Cards)"),
    ("Trade", [PARAM_TRADE_RULES], "Trade rule ('region' = the region's trade rule)"),
    ("AI depth", [PARAM_AI_SEARCH], "AI search depth 0-7 (higher = reads more moves ahead)"),
    ("Guesses hand", [PARAM_AI_SEARCH], "Whether the AI invents a hidden hand for you"),
    ("AI strategy", [PARAM_AI_STRATEGY], "AI strategy profile"),
    ("Levels", [PARAM_LEVEL_MASK], "Card levels the normal cards are drawn from"),
    ("Modified", [], "Changed since the file was loaded (saved with the header's Save)"),
]


class NumericItem(QTableWidgetItem):
    """Sorts by its number (Qt sorts text otherwise: 10 < 9); text-only cells sort after numbers."""

    def __init__(self, text: str, number=None):
        QTableWidgetItem.__init__(self, text)
        self.number = number

    def __lt__(self, other):
        if isinstance(other, NumericItem):
            if self.number is None or other.number is None:
                return (self.number is None, self.text()) < (other.number is None, other.text())
            return self.number < other.number
        return QTableWidgetItem.__lt__(self, other)


class ValueEditor(QStackedWidget):
    """The value input of the bulk bar: a number, a choice, or a set of bits (rules / levels)."""

    def __init__(self):
        QStackedWidget.__init__(self)
        self.spinbox = QSpinBox()
        self.spinbox.wheelEvent = lambda event: None
        self.combobox = QComboBox()
        self.combobox.wheelEvent = lambda event: None
        self.bits_widget = QWidget()
        self.bits_layout = QHBoxLayout()
        self.bits_layout.setContentsMargins(0, 0, 0, 0)
        self.bits_widget.setLayout(self.bits_layout)
        self.bit_checkboxes = []
        self.none_widget = QLabel("")
        for widget in (self.spinbox, self.combobox, self.bits_widget, self.none_widget):
            self.addWidget(widget)

    def show_number(self, minimum, maximum, value, suffix=""):
        self.spinbox.setRange(minimum, maximum)
        self.spinbox.setValue(value)
        self.spinbox.setSuffix(suffix)
        self.setCurrentWidget(self.spinbox)

    def show_choices(self, names):
        self.combobox.clear()
        self.combobox.addItems(names)
        self.setCurrentWidget(self.combobox)

    def show_bits(self, bits):
        while self.bits_layout.count():
            self.bits_layout.takeAt(0).widget().deleteLater()
        self.bit_checkboxes = []
        for bit, name in bits:
            checkbox = QCheckBox(name)
            self.bits_layout.addWidget(checkbox)
            self.bit_checkboxes.append((bit, checkbox))
        self.setCurrentWidget(self.bits_widget)

    def show_nothing(self):
        self.setCurrentWidget(self.none_widget)

    def value(self):
        current = self.currentWidget()
        if current is self.spinbox:
            return self.spinbox.value()
        if current is self.combobox:
            return self.combobox.currentIndex()
        if current is self.bits_widget:
            return sum(bit for bit, checkbox in self.bit_checkboxes if checkbox.isChecked())
        return None


LEVEL_BITS = [(1 << level, f"Lv{level + 1}") for level in range(cardlocation.NB_LEVELS)]

# Bulk operations per parameter: (operation label, function, value input kind, input config)
BULK_OPERATIONS = {
    "Rare card chance": [
        ("Set to", bulk.set_rare_chance, "number", (0, 100, 50, " %")),
        ("Add", bulk.add_rare_chance, "number", (-100, 100, 10, " %")),
        ("Multiply by", bulk.multiply_rare_chance, "number", (0, 1000, 200, " % of current")),
    ],
    "AI search depth": [
        ("Set to", bulk.set_ai_depth, "number", (0, 7, 7, "")),
        ("Add", bulk.add_ai_depth, "number", (-7, 7, 1, "")),
    ],
    "AI guesses your hand": [
        ("Stop guessing (bit 0x10 set)", bulk.set_ai_no_guess, "fixed", True),
        ("Guess (bit 0x10 clear)", bulk.set_ai_no_guess, "fixed", False),
    ],
    "AI strategy": [
        ("Set to", bulk.set_ai_strategy, "choices", AI_STRATEGY_NAMES),
    ],
    "Card levels": [
        ("Shift all levels by", bulk.shift_levels, "number", (-6, 6, 1, " level(s)")),
        ("Add levels", bulk.add_levels, "bits", LEVEL_BITS),
        ("Remove levels", bulk.remove_levels, "bits", LEVEL_BITS),
        ("Set to exactly", bulk.set_levels, "bits", LEVEL_BITS),
    ],
    "Game rules": [
        ("Add rules", bulk.add_game_rules, "bits", GAME_RULE_BITS),
        ("Remove rules", bulk.remove_game_rules, "bits", GAME_RULE_BITS),
        ("Set to fixed rules", bulk.set_game_rules, "bits", GAME_RULE_BITS),
        ("Follow the region rules (var 292)", bulk.use_region_rules, "none", None),
    ],
    "Trade rule": [
        ("Set to fixed rule", bulk.set_trade_rule, "choices", TRADE_RULE_NAMES),
        ("Follow the region rule (var 293)", bulk.use_region_trade_rule, "none", None),
    ],
    "Deck ID": [
        ("Set to", bulk.set_deck_id, "number", (0, 255, 0, "")),
    ],
    "Everything": [
        ("Restore the original values", bulk.restore_original, "none", None),
    ],
}


class NpcCardTableWidget(QWidget):
    """Every card player on one row, with a bulk-edit bar."""

    players_changed = pyqtSignal(list)  # the players a bulk edit changed
    open_player = pyqtSignal(object)  # double-click: show this player in the editor view

    def __init__(self, card_names: list):
        QWidget.__init__(self)
        self.card_names = card_names
        self.manager = None
        self.__rows = []  # (jsm_file, player) per table row, in load order
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        filter_layout = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter rows (any column: map, NPC, rare card, rules...)")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(lambda _: self.apply_filter())
        self.hide_test_checkbox = QCheckBox("Hide debug maps (test*)")
        self.hide_test_checkbox.setChecked(True)
        self.hide_test_checkbox.setToolTip("The test* maps are developer debug rooms, never reached in the game.")
        self.hide_test_checkbox.toggled.connect(lambda _: self.apply_filter())
        self.modified_only_checkbox = QCheckBox("Modified only")
        self.modified_only_checkbox.toggled.connect(lambda _: self.apply_filter())
        self.count_label = QLabel()
        filter_layout.addWidget(self.filter_edit, 1)
        filter_layout.addWidget(self.hide_test_checkbox)
        filter_layout.addWidget(self.modified_only_checkbox)
        filter_layout.addWidget(self.count_label)
        main_layout.addLayout(filter_layout)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([header for header, _, _ in COLUMNS])
        for column, (_, _, tooltip) in enumerate(COLUMNS):
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(self.table.fontMetrics().height() + 6)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.__update_target_label)
        self.table.cellDoubleClicked.connect(self.__row_double_clicked)
        main_layout.addWidget(self.table, 1)

        bulk_group = QGroupBox("Bulk edit")
        bulk_layout = QHBoxLayout()
        bulk_group.setLayout(bulk_layout)
        self.parameter_combobox = QComboBox()
        self.parameter_combobox.addItems(list(BULK_OPERATIONS))
        self.parameter_combobox.currentIndexChanged.connect(self.__parameter_changed)
        self.operation_combobox = QComboBox()
        self.operation_combobox.currentIndexChanged.connect(self.__operation_changed)
        self.value_editor = ValueEditor()
        self.override_checkbox = QCheckBox("Also replace game-state values")
        self.override_checkbox.setToolTip(
            "Off: players whose value follows the game state (the region rules, levels the script rolls\n"
            "at random) keep it. On: 'Set' operations replace it with the fixed value too.")
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_bulk)
        self.target_label = QLabel()
        self.result_label = QLabel()
        for widget in (QLabel("Parameter:"), self.parameter_combobox, self.operation_combobox, self.value_editor):
            bulk_layout.addWidget(widget)
        bulk_layout.addWidget(self.override_checkbox)
        bulk_layout.addStretch(1)
        bulk_layout.addWidget(self.target_label)
        bulk_layout.addWidget(self.apply_button)
        main_layout.addWidget(bulk_group)
        main_layout.addWidget(self.result_label)
        self.__parameter_changed(0)

    # ------------------------------------------------------------------ content

    def set_manager(self, manager):
        self.manager = manager
        self.__rows = [(jsm_file, player) for jsm_file in manager.jsm_files for player in jsm_file.players]
        self.refresh()
        self.table.resizeColumnsToContents()

    def refresh(self):
        """Rebuild every row from the current parameter values (keeps sort, selection, scroll)."""
        selected = set(id(player) for player in self.selected_players())
        sort_column = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        scroll = self.table.verticalScrollBar().value()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.__rows))
        for row, (jsm_file, player) in enumerate(self.__rows):
            self.__fill_row(row, jsm_file, player)
        self.table.setSortingEnabled(True)
        self.table.sortItems(sort_column, sort_order)
        self.table.clearSelection()
        selection_model = self.table.selectionModel()
        flags = selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows
        for row in range(self.table.rowCount()):
            if id(self.__player_at(row)) in selected:
                selection_model.select(self.table.model().index(row, 0), flags)
        self.apply_filter()
        self.table.verticalScrollBar().setValue(scroll)

    def __fill_row(self, row, jsm_file, player):
        params = player.params
        search = params[PARAM_AI_SEARCH]
        variant = player.variant
        if variant is not None and variant.is_variant():
            chance = variant.random_chance()
            variant_text = f"{variant.index + 1}/{len(variant.siblings)}" + (
                f" ({chance:.0f}%)" if chance is not None
                else " (" + " and ".join(condition.text() for condition in variant.conditions) + ")")
        else:
            variant_text = ""
        values = [
            NumericItem(jsm_file.map_name),
            NumericItem(player.entity_name),
            NumericItem(player.script_name),
            NumericItem(variant_text),
            NumericItem(bulk.deck_text(player, self.card_names),
                        params[PARAM_DECK_ID].value if params[PARAM_DECK_ID].is_literal() else None),
            NumericItem(bulk.rare_card_text(player, self.card_names)),
            NumericItem(bulk.param_text(params[PARAM_RARE_CHANCE], lambda value: f"{value}%"),
                        params[PARAM_RARE_CHANCE].value if params[PARAM_RARE_CHANCE].is_literal() else None),
            NumericItem(bulk.game_rules_text(player)),
            NumericItem(bulk.trade_rule_text(player)),
            NumericItem(bulk.param_text(search, lambda value: str(value & 0x07)),
                        search.value & 0x07 if search.is_literal() else None),
            NumericItem(bulk.param_text(search, lambda value: "no" if value & 0x10 else "yes")),
            NumericItem(bulk.param_text(params[PARAM_AI_STRATEGY],
                                        lambda value: AI_STRATEGY_NAMES[value & 0x07].split(" (")[0])),
            NumericItem(bulk.levels_text(player)),
            NumericItem("*" if player.is_modified() else ""),
        ]
        values[0].setData(Qt.ItemDataRole.UserRole, player)
        values[0].setToolTip(jsm_file.jsm_path)
        bold = QFont()
        bold.setBold(True)
        for column, item in enumerate(values):
            if player.is_modified():
                item.setFont(bold)
            if any(params[index].is_modified() for index in COLUMNS[column][1]):
                item.setForeground(QBrush(MODIFIED_COLOR))
            self.table.setItem(row, column, item)

    def __player_at(self, row):
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def apply_filter(self):
        text = self.filter_edit.text().strip().lower()
        nb_visible = 0
        for row in range(self.table.rowCount()):
            player = self.__player_at(row)
            map_name = self.table.item(row, 0).text()
            hidden = (self.hide_test_checkbox.isChecked() and map_name.startswith(TEST_MAP_PREFIX)) or (
                self.modified_only_checkbox.isChecked() and not player.is_modified())
            if not hidden and text:
                hidden = not any(text in self.table.item(row, column).text().lower()
                                 for column in range(self.table.columnCount()))
            self.table.setRowHidden(row, hidden)
            nb_visible += not hidden
        self.count_label.setText(f"{nb_visible} / {self.table.rowCount()} rows")
        self.__update_target_label()

    def selected_players(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.__player_at(row) for row in rows if not self.table.isRowHidden(row)]

    def target_players(self):
        """The selected rows, or every visible row when nothing is selected."""
        selected = self.selected_players()
        if selected:
            return selected
        return [self.__player_at(row) for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def __update_target_label(self):
        nb_selected = len(self.selected_players())
        if nb_selected:
            self.target_label.setText(f"to the {nb_selected} selected row(s)")
        else:
            self.target_label.setText("to every visible row (nothing selected)")

    # ------------------------------------------------------------------ bulk edit

    def __current_operation(self):
        operations = BULK_OPERATIONS[self.parameter_combobox.currentText()]
        index = self.operation_combobox.currentIndex()
        return operations[index] if 0 <= index < len(operations) else operations[0]

    def __parameter_changed(self, _index):
        self.operation_combobox.blockSignals(True)
        self.operation_combobox.clear()
        self.operation_combobox.addItems([label for label, _, _, _ in
                                          BULK_OPERATIONS[self.parameter_combobox.currentText()]])
        self.operation_combobox.blockSignals(False)
        self.__operation_changed(0)

    def __operation_changed(self, _index):
        label, function, kind, config = self.__current_operation()
        if kind == "number":
            self.value_editor.show_number(*config)
        elif kind == "choices":
            self.value_editor.show_choices(config)
        elif kind == "bits":
            self.value_editor.show_bits(config)
        else:
            self.value_editor.show_nothing()
        # Only the "set to a fixed value" operations can replace a game-state value
        self.override_checkbox.setVisible(function in (bulk.set_rare_chance, bulk.set_levels, bulk.set_game_rules,
                                                       bulk.set_trade_rule, bulk.set_deck_id))

    def apply_bulk(self):
        label, function, kind, config = self.__current_operation()
        value = config if kind == "fixed" else self.value_editor.value()
        players = self.target_players()
        changed_players = [player for player in players
                           if function(player, value, self.override_checkbox.isChecked())]
        nb_unchanged = len(players) - len(changed_players)
        self.result_label.setText(
            f"{self.parameter_combobox.currentText()} - {label}: {len(changed_players)} player(s) changed,"
            f" {nb_unchanged} unchanged (already at that value, or following the game state)."
            f" Save with the header's Save button.")
        self.refresh()
        if changed_players:
            self.players_changed.emit(changed_players)

    def __row_double_clicked(self, row, _column):
        player = self.__player_at(row)
        if player is not None:
            self.open_player.emit(player)
