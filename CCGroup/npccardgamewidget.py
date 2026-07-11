"""
"NPC card players" tab of the CCGroup tool.

Loads a folder, scans every .jsm/.sym field script inside it for CARDGAME (0x13A)
calls, and shows an editor for the 7 parameters of each NPC card player found.

The game/trade rules and the card levels can either be a fixed value or follow the
game state (savemap variables, e.g. the regional rules spread by the Queen of Cards):
a named checkbox switches between the two modes.

All values and descriptions come from the FF8ModdingWiki page 13A_CARDGAME.
"""
import os

from PyQt6.QtCore import QSize, Qt, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
                             QFileDialog, QPushButton, QLabel, QComboBox, QCheckBox,
                             QSpinBox, QGroupBox, QMessageBox, QSplitter, QLineEdit,
                             QTreeWidget, QTreeWidgetItem)

from CCGroup.jsmcardgame import (CardGameFolderManager, CardGamePlayer, CardGameParam,
                                 GAME_RULE_BITS, TRADE_RULE_NAMES, AI_STRATEGY_NAMES,
                                 AI_SEARCH_DEPTH_NAMES, AI_SEARCH_NO_GUESS_BIT,
                                 VAR_CURRENT_REGION_GAME_RULES, VAR_CURRENT_REGION_TRADE_RULE,
                                 ESCALATING_LEVEL_MASK_VARS,
                                 PARAM_DECK_ID, PARAM_GAME_RULES, PARAM_TRADE_RULES,
                                 PARAM_RARE_CHANCE, PARAM_AI_SEARCH, PARAM_AI_STRATEGY,
                                 PARAM_LEVEL_MASK)

TOOLTIP_DECK_ID = (
    "<b>Deck ID (owner location)</b><br/>"
    "The deck the AI opponent draws its non-rare cards from, and the location code used<br/>"
    "to decide which <b>rare cards</b> (IDs 77-109) may appear: a rare card is eligible only if<br/>"
    "its current owner-location in the savegame equals this Deck ID.<br/>"
    "Special value <b>240 (0xF0)</b> = the player's own cards.")

TOOLTIP_GAME_RULES = (
    "<b>Game rules</b> (bitfield)<br/>"
    "<b>Open</b>: both hands visible (the AI also stops guessing your hidden hand)<br/>"
    "<b>Same / Plus / Same Wall</b>: capture combo rules (Same Wall only works if Same is on)<br/>"
    "<b>Random</b>: your hand becomes 5 random cards from your collection<br/>"
    "<b>Sudden Death</b>: a draw restarts the game with the captured cards<br/>"
    "<b>Elemental</b>: elemental tiles give +1/-1 to cards placed on them")

TOOLTIP_TRADE_RULES = (
    "<b>Trade rules</b> - how cards change hands at the end of the match:<br/>"
    "<b>None</b> (0): no trade, everyone keeps their cards (also the fallback on a draw)<br/>"
    "<b>One</b> (1): winner takes 1 card<br/>"
    "<b>Difference</b> (2): winner takes the score difference in cards<br/>"
    "<b>Direct</b> (3): each player keeps every card captured on the board<br/>"
    "<b>All</b> (4): winner takes all 5")

TOOLTIP_RARE_CHANCE = (
    "<b>Rare card chance</b> (0-100)<br/>"
    "Each rare card (IDs 77-109) currently located at this NPC's Deck ID has this % chance<br/>"
    "of being added to the NPC's deck (up to 5). The chance is <b>halved</b> after each<br/>"
    "successful pick: at 100 the first rare is guaranteed, the next is 50%, then 25%...<br/>"
    "0 = the NPC never plays rare cards.")

TOOLTIP_AI_SEARCH = (
    "<b>AI search profile</b> - how hard the AI thinks.<br/>"
    "The depth (0-7) selects how many moves ahead the minimax search reads: profile 0 plays<br/>"
    "almost greedily (~1 move), profile 7 reads 3-4 moves deep in the mid-game.<br/>"
    "The search is shallow while hands are full and deepens toward the endgame.<br/><br/>"
    "<b>Doesn't guess your hand</b> (bit 0x10): when unchecked the AI invents a plausible<br/>"
    "hidden hand for you and plays around it; when checked (or with the Open rule) it only<br/>"
    "reasons about cards it can actually see.")

TOOLTIP_AI_STRATEGY = (
    "<b>AI strategy profile</b> - what the AI wants (the board scoring weights):<br/>"
    "<b>0, 6, 7 - Territory</b>: counts controlled tiles only, ignores card strength. Weakest.<br/>"
    "<b>1 - Hoarder</b>: hoards its strong cards, opens with junk. Defensive.<br/>"
    "<b>2 - Power-hungry</b>: wants strong cards on the board, fights for power tiles. Aggressive.<br/>"
    "<b>3 - Territory + randomness</b>: unpredictable, sometimes misplays.<br/>"
    "<b>4 / 5 - Greedy / Very greedy</b>: overvalues captures made on its own turn.<br/><br/>"
    "The strongest opponents combine a high search depth with strategy 2 or 5.")

TOOLTIP_LEVEL_MASK = (
    "<b>Allowed card levels</b><br/>"
    "The non-rare part of the NPC's deck is drawn only from the checked levels<br/>"
    "(each level is a group of 11 cards: Lv1 = IDs 0-10, Lv2 = 11-21, ... Lv7 = 66-76).<br/>"
    "If nothing is checked the game falls back to level 1 only.")

TOOLTIP_REGION_GAME_RULES = (
    "<b>Current region rules</b><br/>"
    f"Checked: the match uses the ruleset of the current region (savemap variable {VAR_CURRENT_REGION_GAME_RULES},<br/>"
    "prepared by the cardgamemaster script), so it evolves as the Queen of Cards spreads or<br/>"
    "abolishes rules - this is the original behavior of most NPCs.<br/>"
    "Unchecked: this NPC always plays with the fixed rules you pick here.")

TOOLTIP_REGION_TRADE_RULE = (
    "<b>Current region rule</b><br/>"
    f"Checked: the trade rule follows the current region (savemap variable {VAR_CURRENT_REGION_TRADE_RULE},<br/>"
    "prepared by the cardgamemaster script) - this is the original behavior of most NPCs.<br/>"
    "Unchecked: this NPC always uses the fixed trade rule you pick here.")

TOOLTIP_ESCALATING_LEVELS = (
    "<b>Escalating levels</b><br/>"
    "Checked: the deck levels come from a savemap variable that the field scripts raise<br/>"
    "each time you challenge the NPC, so the deck grows stronger as you keep playing<br/>"
    "(e.g. the Balamb Garden hall students go from Lv1-3 to more and more Lv4).<br/>"
    "The variable is shared between the NPCs that use it: progress against one<br/>"
    "strengthens the others.<br/><br/>"
    "Only 4 such variables exist in the game, pick which progression to follow:<br/>"
    "<b>1041</b>: Balamb Garden hall students (seito8/seito10, bghall_1)<br/>"
    "<b>1040</b>: Balamb Garden hall SeeDs (seed01/seed02, bghall1b)<br/>"
    "<b>1024</b>: Joker in the training center (bgmon_4)<br/>"
    "<b>1025</b>: Joker on the Ragnarok (rgroad11)<br/><br/>"
    "Unchecked: this NPC always draws from the fixed levels you check here.<br/><br/>"
    "<i>Note: the variable is only raised by the scripts of those maps; on a fresh game<br/>"
    "it starts at the value their init scripts give it.</i>")

TOOLTIP_GAME_STATE_GENERIC = (
    "<b>Value from the game state</b><br/>"
    "Checked: the script pushes a savemap variable instead of a fixed number, so the value<br/>"
    "is decided at runtime (original behavior).<br/>"
    "Unchecked: replace it with the fixed value you pick here.")


class CardGameParamRow:
    """Base helper: one labeled parameter row.

    ``variable_option`` = (checkbox_text, var_choices, tooltip) describes the
    game-state alternative of the parameter: a named checkbox that is always shown.
    Checked, the instruction pushes a savemap variable; unchecked, it pushes the
    fixed value built from the editor widgets. ``var_choices`` is a list of
    (variable, label): when there is more than one, a selector lets the user pick
    which variable to follow. Parameters without a known game-state variable still
    get a generic checkbox when the script happens to use one."""

    def __init__(self, param: CardGameParam, label_text: str, tooltip: str, variable_option=None):
        self.param = param
        self.label = QLabel(label_text + ":")
        self.label.setToolTip(tooltip)
        self.variable_checkbox = None
        self.variable_combobox = None
        self.not_editable_label = None
        self.variable_opcode = None
        self.variable_values = []
        if variable_option is None and param.is_variable():
            variable_option = (f"Value from game state (var {param.original_value})",
                               [(param.original_value, f"var {param.original_value}")],
                               TOOLTIP_GAME_STATE_GENERIC)
        if not param.is_editable():
            self.not_editable_label = QLabel("computed at runtime (not editable)")
            self.not_editable_label.setToolTip("The pushed value is not a literal nor a savemap"
                                               " variable, so this tool cannot edit it safely.")
        elif variable_option is not None:
            checkbox_text, var_choices, variable_tooltip = variable_option
            if param.is_variable():
                # Keep the exact original push opcode when re-checked
                self.variable_opcode = param.original_opcode
                if param.original_value not in [variable for variable, _ in var_choices]:
                    var_choices = [(param.original_value,
                                    f"var {param.original_value} (original)")] + list(var_choices)
            self.variable_values = [variable for variable, _ in var_choices]
            if len(var_choices) > 1:
                self.variable_combobox = QComboBox()
                self.variable_combobox.addItems([label for _, label in var_choices])
                self.variable_combobox.setToolTip(variable_tooltip)
                self.variable_combobox.wheelEvent = lambda event: None
                if param.is_variable():
                    self.variable_combobox.setCurrentIndex(
                        self.variable_values.index(param.original_value))
                self.variable_combobox.currentIndexChanged.connect(lambda _: self.apply_to_param())
            self.variable_checkbox = QCheckBox(checkbox_text)
            self.variable_checkbox.setToolTip(variable_tooltip)
            self.variable_checkbox.setChecked(param.is_variable())
            self.variable_checkbox.toggled.connect(self.__variable_toggled)

    def editor_widgets(self):
        """Widgets holding the fixed value (disabled while the variable mode is checked)."""
        return []

    def value_from_editors(self):
        """Current fixed value built from the editor widgets."""
        return 0

    def set_editors_enabled(self, enabled: bool):
        for widget in self.editor_widgets():
            widget.setEnabled(enabled)

    def selected_variable(self):
        if self.variable_combobox is not None:
            return self.variable_values[self.variable_combobox.currentIndex()]
        return self.variable_values[0]

    def apply_to_param(self):
        if not self.param.is_editable():
            return
        if self.variable_checkbox is not None and self.variable_checkbox.isChecked():
            if self.variable_opcode is not None:
                self.param.set_variable(self.selected_variable(), self.variable_opcode)
            else:
                self.param.set_variable(self.selected_variable())
        else:
            self.param.set_literal(self.value_from_editors())

    def __variable_toggled(self, checked: bool):
        self.set_editors_enabled(not checked)
        if self.variable_combobox is not None:
            self.variable_combobox.setEnabled(checked)
        self.apply_to_param()

    def add_to_grid(self, grid: QGridLayout, row: int, editor_layout):
        grid.addWidget(self.label, row, 0, Qt.AlignmentFlag.AlignTop)
        line_layout = QHBoxLayout()
        if self.not_editable_label is not None:
            line_layout.addWidget(self.not_editable_label)
        if self.variable_checkbox is not None:
            line_layout.addWidget(self.variable_checkbox)
        if self.variable_combobox is not None:
            line_layout.addWidget(self.variable_combobox)
        if editor_layout is not None:
            line_layout.addLayout(editor_layout)
        line_layout.addStretch(1)
        grid.addLayout(line_layout, row, 1)
        if not self.param.is_editable():
            self.set_editors_enabled(False)
        elif self.variable_checkbox is not None:
            checked = self.variable_checkbox.isChecked()
            self.set_editors_enabled(not checked)
            if self.variable_combobox is not None:
                self.variable_combobox.setEnabled(checked)


class SpinParamRow(CardGameParamRow):
    """A parameter edited with a single spinbox (Deck ID, rare chance)."""

    def __init__(self, param: CardGameParam, label_text: str, tooltip: str,
                 minimum: int, maximum: int, suffix: str = "", variable_option=None):
        CardGameParamRow.__init__(self, param, label_text, tooltip, variable_option)
        self.spinbox = QSpinBox()
        self.spinbox.setRange(minimum, maximum)
        self.spinbox.setValue(min(max(param.value if param.is_literal() else 0, minimum), maximum))
        if suffix:
            self.spinbox.setSuffix(suffix)
        self.spinbox.setToolTip(tooltip)
        self.spinbox.wheelEvent = lambda event: None
        self.spinbox.valueChanged.connect(lambda _: self.apply_to_param())

    def editor_widgets(self):
        return [self.spinbox]

    def value_from_editors(self):
        return self.spinbox.value()

    def layout(self):
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.spinbox)
        return editor_layout


class ComboParamRow(CardGameParamRow):
    """A parameter edited with a combobox over its low 3 bits (trade rule, AI strategy),
    preserving any unknown high bits of the original literal."""

    def __init__(self, param: CardGameParam, label_text: str, tooltip: str,
                 item_names: list, kept_bits_mask: int, variable_option=None):
        CardGameParamRow.__init__(self, param, label_text, tooltip, variable_option)
        self.kept_bits_mask = kept_bits_mask
        self.combobox = QComboBox()
        self.combobox.addItems(item_names)
        self.combobox.setToolTip(tooltip)
        self.combobox.wheelEvent = lambda event: None
        initial = param.value if param.is_literal() else 0
        self.high_bits = initial & kept_bits_mask
        selectable = initial & ~kept_bits_mask
        if selectable >= len(item_names):
            self.combobox.addItem(f"Unknown ({selectable})")
            self.combobox.setCurrentIndex(self.combobox.count() - 1)
            self.unknown_value = selectable
        else:
            self.combobox.setCurrentIndex(selectable)
            self.unknown_value = None
        self.combobox.currentIndexChanged.connect(lambda _: self.apply_to_param())

    def editor_widgets(self):
        return [self.combobox]

    def value_from_editors(self):
        index = self.combobox.currentIndex()
        if self.unknown_value is not None and index == self.combobox.count() - 1:
            return self.unknown_value | self.high_bits
        return index | self.high_bits

    def layout(self):
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.combobox)
        return editor_layout


class BitmaskParamRow(CardGameParamRow):
    """A parameter edited with one checkbox per bit (game rules, allowed levels)."""

    def __init__(self, param: CardGameParam, label_text: str, tooltip: str, bits: list,
                 variable_option=None):
        CardGameParamRow.__init__(self, param, label_text, tooltip, variable_option)
        self.checkboxes = []
        initial = param.value if param.is_literal() else 0
        known_mask = 0
        for bit_value, bit_name in bits:
            checkbox = QCheckBox(bit_name)
            checkbox.setToolTip(tooltip)
            checkbox.setChecked(bool(initial & bit_value))
            checkbox.toggled.connect(lambda _: self.apply_to_param())
            self.checkboxes.append((bit_value, checkbox))
            known_mask |= bit_value
        self.high_bits = initial & ~known_mask

    def editor_widgets(self):
        return [checkbox for _, checkbox in self.checkboxes]

    def value_from_editors(self):
        value = self.high_bits
        for bit_value, checkbox in self.checkboxes:
            if checkbox.isChecked():
                value |= bit_value
        return value

    def layout(self):
        editor_layout = QHBoxLayout()
        for _, checkbox in self.checkboxes:
            editor_layout.addWidget(checkbox)
        return editor_layout


class AiSearchParamRow(CardGameParamRow):
    """AI search profile: depth combobox (bits 0-2) + 'doesn't guess your hand' checkbox (0x10)."""

    def __init__(self, param: CardGameParam):
        CardGameParamRow.__init__(self, param, "AI search", TOOLTIP_AI_SEARCH)
        self.combobox = QComboBox()
        self.combobox.addItems(AI_SEARCH_DEPTH_NAMES)
        self.combobox.setToolTip(TOOLTIP_AI_SEARCH)
        self.combobox.wheelEvent = lambda event: None
        self.no_guess_checkbox = QCheckBox("Doesn't guess your hand")
        self.no_guess_checkbox.setToolTip(TOOLTIP_AI_SEARCH)
        initial = param.value if param.is_literal() else 0
        self.combobox.setCurrentIndex(initial & 7)
        self.no_guess_checkbox.setChecked(bool(initial & AI_SEARCH_NO_GUESS_BIT))
        self.high_bits = initial & ~(7 | AI_SEARCH_NO_GUESS_BIT)
        self.combobox.currentIndexChanged.connect(lambda _: self.apply_to_param())
        self.no_guess_checkbox.toggled.connect(lambda _: self.apply_to_param())

    def editor_widgets(self):
        return [self.combobox, self.no_guess_checkbox]

    def value_from_editors(self):
        value = (self.combobox.currentIndex() & 7) | self.high_bits
        if self.no_guess_checkbox.isChecked():
            value |= AI_SEARCH_NO_GUESS_BIT
        return value

    def layout(self):
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.combobox)
        editor_layout.addWidget(self.no_guess_checkbox)
        return editor_layout


class CardPlayerWidget(QGroupBox):
    """Editor of the 7 CARDGAME parameters of one NPC."""

    def __init__(self, player: CardGamePlayer):
        QGroupBox.__init__(self, f"{player.entity_name}  ({player.script_name})")
        self.player = player
        self.setToolTip(f"CARDGAME call at file offset 0x{player.cardgame_file_offset:X},"
                        f" script {player.entity_name}::{player.script_name}")

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.setLayout(grid)

        self.rows = [
            SpinParamRow(player.params[PARAM_DECK_ID], "Deck ID", TOOLTIP_DECK_ID, 0, 255),
            BitmaskParamRow(player.params[PARAM_GAME_RULES], "Game rules", TOOLTIP_GAME_RULES,
                            GAME_RULE_BITS,
                            variable_option=("Current region rules",
                                             [(VAR_CURRENT_REGION_GAME_RULES, "")],
                                             TOOLTIP_REGION_GAME_RULES)),
            ComboParamRow(player.params[PARAM_TRADE_RULES], "Trade rule", TOOLTIP_TRADE_RULES,
                          TRADE_RULE_NAMES, kept_bits_mask=~0x07 & 0xFFFFFF,
                          variable_option=("Current region rule",
                                           [(VAR_CURRENT_REGION_TRADE_RULE, "")],
                                           TOOLTIP_REGION_TRADE_RULE)),
            SpinParamRow(player.params[PARAM_RARE_CHANCE], "Rare card chance", TOOLTIP_RARE_CHANCE,
                         0, 100, suffix=" %"),
            AiSearchParamRow(player.params[PARAM_AI_SEARCH]),
            ComboParamRow(player.params[PARAM_AI_STRATEGY], "AI strategy", TOOLTIP_AI_STRATEGY,
                          AI_STRATEGY_NAMES, kept_bits_mask=~0x07 & 0xFFFFFF),
            BitmaskParamRow(player.params[PARAM_LEVEL_MASK], "Card levels", TOOLTIP_LEVEL_MASK,
                            [(1 << level, f"Lv{level + 1}") for level in range(7)],
                            variable_option=("Escalating levels", ESCALATING_LEVEL_MASK_VARS,
                                             TOOLTIP_ESCALATING_LEVELS)),
        ]
        for row_index, row in enumerate(self.rows):
            row.add_to_grid(grid, row_index, row.layout())


class NpcCardGameWidget(QWidget):
    """The 'NPC card players' tab.

    Left: a filterable map/NPC tree of every card player found in the loaded folder.
    Right: the parameter editor of the selected player (built on demand - a full game
    dump contains hundreds of players, so only one editor exists at a time)."""

    def __init__(self, icon_path='Resources', settings: QSettings = None):
        QWidget.__init__(self)
        self.manager = CardGameFolderManager()
        self.folder_loaded = ""
        self.settings = settings

        self.__main_layout = QVBoxLayout()
        self.setLayout(self.__main_layout)

        self.__folder_dialog = QFileDialog()
        self.__folder_button = QPushButton()
        self.__folder_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.__folder_button.setIconSize(QSize(30, 30))
        self.__folder_button.setFixedSize(40, 40)
        self.__folder_button.setToolTip("Open a folder: every .jsm field script inside it (subfolders"
                                        " included) is scanned for NPCs that start a card game")
        self.__folder_button.clicked.connect(self.__load_folder_clicked)

        self.__save_button = QPushButton()
        self.__save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.__save_button.setIconSize(QSize(30, 30))
        self.__save_button.setFixedSize(40, 40)
        self.__save_button.setToolTip("Save the modified .jsm files (patched in place)")
        self.__save_button.clicked.connect(self.__save_clicked)
        self.__save_button.setEnabled(False)

        self.__info_label = QLabel("Open a folder containing .jsm/.sym field scripts"
                                   " (e.g. extracted with Deling) to list the NPC card players.")

        self.__layout_top = QHBoxLayout()
        self.__layout_top.addWidget(self.__folder_button)
        self.__layout_top.addWidget(self.__save_button)
        self.__layout_top.addWidget(self.__info_label)
        self.__layout_top.addStretch(1)
        self.__main_layout.addLayout(self.__layout_top)

        # Left pane: filter + tree of maps/players
        self.__filter_edit = QLineEdit()
        self.__filter_edit.setPlaceholderText("Filter by map or NPC name...")
        self.__filter_edit.setClearButtonEnabled(True)
        self.__filter_edit.textChanged.connect(self.__filter_changed)
        self.__tree = QTreeWidget()
        self.__tree.setHeaderHidden(True)
        self.__tree.currentItemChanged.connect(self.__selection_changed)
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.__filter_edit)
        left_layout.addWidget(self.__tree)
        left_widget.setLayout(left_layout)

        # Right pane: editor of the selected player
        self.__editor_scroll = QScrollArea()
        self.__editor_scroll.setWidgetResizable(True)
        self.__editor_scroll.setWidget(QLabel("Select a card player in the list."))

        self.__splitter = QSplitter(Qt.Orientation.Horizontal)
        self.__splitter.addWidget(left_widget)
        self.__splitter.addWidget(self.__editor_scroll)
        self.__splitter.setStretchFactor(0, 1)
        self.__splitter.setStretchFactor(1, 2)
        self.__splitter.setSizes([300, 800])
        self.__main_layout.addWidget(self.__splitter, 1)

    def __load_folder_clicked(self):
        start_folder = self.folder_loaded
        if not start_folder and self.settings is not None:
            start_folder = self.settings.value("ccgroup/npc_last_folder", defaultValue="", type=str)
        folder = self.__folder_dialog.getExistingDirectory(parent=self, caption="Open field script folder",
                                                           directory=start_folder or os.getcwd())
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder_path: str):
        self.folder_loaded = folder_path
        if self.settings is not None:
            self.settings.setValue("ccgroup/npc_last_folder", folder_path)
        self.manager.load_folder(folder_path)
        self.__rebuild_tree()
        nb_players = self.manager.nb_players()
        if nb_players == 0:
            self.__info_label.setText(f"No card player found in {folder_path}")
        else:
            self.__info_label.setText(f"{nb_players} card player(s) found in {len(self.manager.jsm_files)}"
                                      f" file(s) - {folder_path}")
        self.__save_button.setEnabled(nb_players > 0)

    def __rebuild_tree(self):
        self.__tree.clear()
        self.__show_editor(None)
        for jsm_file in self.manager.jsm_files:
            map_item = QTreeWidgetItem([f"{jsm_file.map_name}  ({len(jsm_file.players)})"])
            map_item.setToolTip(0, jsm_file.jsm_path)
            for player in jsm_file.players:
                player_item = QTreeWidgetItem([f"{player.entity_name}  ({player.script_name})"])
                player_item.setData(0, Qt.ItemDataRole.UserRole, player)
                map_item.addChild(player_item)
            self.__tree.addTopLevelItem(map_item)
        self.__tree.expandAll()
        self.__filter_changed(self.__filter_edit.text())

    def __filter_changed(self, text: str):
        text = text.strip().lower()
        for map_index in range(self.__tree.topLevelItemCount()):
            map_item = self.__tree.topLevelItem(map_index)
            map_match = text in map_item.text(0).lower()
            nb_visible_children = 0
            for child_index in range(map_item.childCount()):
                player_item = map_item.child(child_index)
                player_match = map_match or text in player_item.text(0).lower()
                player_item.setHidden(not player_match)
                if player_match:
                    nb_visible_children += 1
            map_item.setHidden(nb_visible_children == 0)

    def __selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        player = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        self.__show_editor(player)

    def __show_editor(self, player):
        old_widget = self.__editor_scroll.takeWidget()
        if old_widget is not None:
            old_widget.deleteLater()
        if player is None:
            self.__editor_scroll.setWidget(QLabel("Select a card player in the list."))
        else:
            editor_widget = QWidget()
            editor_layout = QVBoxLayout()
            editor_layout.addWidget(CardPlayerWidget(player))
            editor_layout.addStretch(1)
            editor_widget.setLayout(editor_layout)
            self.__editor_scroll.setWidget(editor_widget)

    def __save_clicked(self):
        nb_saved = self.manager.save_all()
        if nb_saved == 0:
            QMessageBox.information(self, "CC Group", "No modification to save.")
        else:
            QMessageBox.information(self, "CC Group", f"{nb_saved} file(s) saved.")
