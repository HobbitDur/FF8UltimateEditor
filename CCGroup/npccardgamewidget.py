"""
"NPC card players" tab of the CCGroup tool.

Loads a folder, scans every .jsm/.sym field script inside it for CARDGAME (0x13A)
calls, and shows an editor for the 7 parameters of each NPC card player found.

The game/trade rules and the card levels can either be a fixed value or follow the
game state (savemap variables, e.g. the regional rules spread by the Queen of Cards):
a named checkbox switches between the two modes.

Below the parameters, the editor shows what they mean in play: the variant (when the script
picks among several CARDGAME calls), the rare cards tied to the Deck ID (and the other NPCs
sharing it) and a preview of the deck the NPC deals. A third column shows where the NPC stands
on the field background and its 3D model.

All values and descriptions come from the FF8ModdingWiki page 13A_CARDGAME.
"""
import os
import random
from collections import Counter

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QPixmap, QBrush, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
                             QLabel, QComboBox, QCheckBox, QPushButton, QFileDialog,
                             QSpinBox, QGroupBox, QMessageBox, QSplitter, QLineEdit,
                             QTreeWidget, QTreeWidgetItem, QTabWidget, QHeaderView, QPlainTextEdit)

from CCGroup import cardlocation
from CCGroup import cardplayersfile
from CCGroup import jsmnpc as jsm_npc
from CCGroup.addcardgamedialog import AddCardGameDialog
from CCGroup.npccardtablewidget import NpcCardTableWidget
from CCGroup.npcfieldview import NpcFieldView
from Common.fieldfolder import MAPDATA, VANILLA_MIN_MAPS, check_field_folder
from Common.fileregistry import busy_cursor
from CCGroup.jsmcardgame import (CardGameFolderManager, OPCODE_PSHN_L, CardGamePlayer, CardGameParam,
                                 GAME_RULE_BITS, TRADE_RULE_NAMES, AI_STRATEGY_NAMES,
                                 AI_SEARCH_DEPTH_NAMES, AI_SEARCH_NO_GUESS_BIT,
                                 VAR_CURRENT_REGION_GAME_RULES, VAR_CURRENT_REGION_TRADE_RULE,
                                 PARAM_DECK_ID, PARAM_GAME_RULES, PARAM_TRADE_RULES,
                                 PARAM_RARE_CHANCE, PARAM_AI_SEARCH, PARAM_AI_STRATEGY,
                                 PARAM_LEVEL_MASK, CLOCK_MAX_SECONDS, CLOCK_MAX_INCREMENT,
                                 VAR_CRONOS_CLOCK_SECONDS, VAR_CRONOS_CLOCK_INCREMENT, clock_text)

TOOLTIP_DECK_ID = (
    "<b>Deck ID (rare card location)</b><br/>"
    "The NPC's pocket for <b>rare cards</b> (IDs 77-109): a rare card can be played by this NPC<br/>"
    "only while its location in the savegame equals this Deck ID. It has <b>no effect on the<br/>"
    "normal cards</b>, which come from the allowed card levels only.<br/><br/>"
    "The cards you pick for the match are moved to this Deck ID and come back only if you keep<br/>"
    "or win them: a rare card you lose stays here, and every NPC sharing this Deck ID can play it.<br/><br/>"
    "<b>0</b> = no rare cards, <b>1</b> = Queen of Cards, <b>200-232</b> = starting owner of rare card<br/>"
    "Deck ID - 123 (e.g. 213 = Leviathan, Joker's card), <b>240</b> = the player's own cards.")

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
    "The rare cards (IDs 77-109) currently located at this NPC's Deck ID are tested in card order.<br/>"
    "The first one joins the NPC's hand with this % chance; once one has joined, every<br/>"
    "following one is tested at <b>half</b> this chance (not halved again), up to 5 cards.<br/>"
    "At 100 the first rare is guaranteed and each further one has 50%.<br/>"
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

TOOLTIP_SCRIPT_LEVELS = (
    "<b>Levels set by the script</b><br/>"
    "Checked: the script pushes a savemap variable that its own map script sets right before<br/>"
    "the match, usually from a <b>random roll</b> (e.g. the Balamb Garden hall students pick one of<br/>"
    "Lv1-3, Lv1-2+4, Lv1+3-4, Lv2-4, Lv1-4; Joker always has Lv2, Lv3, Lv5 plus random levels).<br/>"
    "The deck preview lists what the script can set.<br/>"
    "Unchecked: this NPC always draws from the fixed levels you check here.<br/><br/>"
    "<i>These variables (1024 and up) are scratch variables of the map: another map does not set<br/>"
    "them, which is why only NPCs that already use one offer this option.</i>")


TOOLTIP_CRONOS_OPTIONS = (
    "<b>Cronos options</b><br/>"
    "Shows the settings that only work with the Cronos mod's DLLs (e.g. the Triple Triad turn clock,<br/>"
    "TripleTriadClock.dll). A value set here is saved into the field script like any other, but the<br/>"
    "vanilla game ignores it.")

TOOLTIP_CLOCK = (
    "<b>Turn clock</b> (Cronos, TripleTriadClock.dll) - a chess clock for the human player.<br/>"
    "<b>Starting time</b>: the player's time bank at the start of the match. It runs down only during<br/>"
    "the player's own turns (not during card flips, not while the Select rules box is open) and shows<br/>"
    "on screen as M:SS (red from 0:10). Each number stays a full second: the player <b>loses</b> once<br/>"
    "0:00 has shown for one second. A Sudden Death rematch refills it. <b>0 = no clock</b>.<br/>"
    "<b>Increment</b>: seconds added to the bank each time the player places a card.<br/><br/>"
    f"Saved as 4 instructions right before the CARDGAME pushes: savemap var {VAR_CRONOS_CLOCK_SECONDS} (word)<br/>"
    f"= starting time, var {VAR_CRONOS_CLOCK_INCREMENT} (byte) = increment; the DLL reads and clears them.")


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
        self.on_change = None  # called after every edit of the param (the editor refreshes its previews)
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
        if self.on_change is not None:
            self.on_change()

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


class DeckIdParamRow(SpinParamRow):
    """Deck ID: the spinbox plus a picker of the meaningful locations (no rare, Queen, the 33
    rare-card starting owners, the player) and a line saying what the current value means."""

    def __init__(self, param: CardGameParam, card_names: list):
        SpinParamRow.__init__(self, param, "Deck ID", TOOLTIP_DECK_ID, 0, 255)
        self.card_names = card_names
        self.picker = QComboBox()
        self.picker.setToolTip(TOOLTIP_DECK_ID)
        self.picker.wheelEvent = lambda event: None
        self.picker_values = [None, cardlocation.LOCATION_NO_RARE, cardlocation.LOCATION_QUEEN]
        self.picker.addItems(["", "0 - No rare cards", "1 - Queen of Cards"])
        for card_id in range(cardlocation.RARE_CARD_FIRST_ID, cardlocation.RARE_CARD_LAST_ID + 1):
            location = cardlocation.starting_location(card_id)
            self.picker_values.append(location)
            self.picker.addItem(f"{location} - {card_names[card_id]} (starting owner)")
        self.picker_values.append(cardlocation.LOCATION_PLAYER)
        self.picker.addItem(f"{cardlocation.LOCATION_PLAYER} - The player's own cards")
        self.__sync_picker()
        self.picker.activated.connect(self.__picked)
        self.spinbox.valueChanged.connect(lambda _: self.__sync_picker())

    def editor_widgets(self):
        return [self.spinbox, self.picker]

    def layout(self):
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.spinbox)
        editor_layout.addWidget(self.picker)
        return editor_layout

    def __picked(self, index: int):
        if self.picker_values[index] is not None:
            self.spinbox.setValue(self.picker_values[index])

    def __sync_picker(self):
        # Item 0 describes a value that is not in the list; a listed value shows its own item instead
        value = self.spinbox.value()
        if value in self.picker_values:
            self.picker.setItemText(0, "Other value (type it in the box)")
        else:
            self.picker.setItemText(0, f"{value} - " + cardlocation.location_label(value, self.card_names))
        self.picker.setCurrentIndex(self.picker_values.index(value) if value in self.picker_values else 0)


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


CARD_THUMBNAIL_SIZE = 48
MODIFIED_FOLDER_COLOR = QColor(40, 110, 210)  # maps read from the folder you edit (with vanilla open)
NO_CARD_MASTER_COLOR = QColor(215, 120, 0)  # the note on maps without a cardgamemaster entity
NO_CARD_MASTER_TEXT = "no card master"
TOOLTIP_NO_CARD_MASTER = ("No card master in this map: a card game added here uses the region rules directly,\n"
                          "without the Queen of Cards rule spreading.")
DEFAULT_EXPORT_NAME = "card_players.cardplayers.json"
TOOLTIP_EXPORT = (
    "<b>Export card players</b> (*.cardplayers.json)<br/>"
    "Every card player of the opened folders in one readable file: its 7 values, Cronos clock, variant<br/>"
    "conditions and texts, unsaved edits included. Keep it (it diffs well in git), share it, or apply it<br/>"
    "onto another field folder. With the vanilla reference open, each player is also marked as changed<br/>"
    "from vanilla or not, and the card games given to an NPC are marked as added.")
TOOLTIP_APPLY = (
    "<b>Apply card players file</b><br/>"
    "Set every card player of the file on the opened folders (found by map, NPC and script), and give the<br/>"
    "card games marked as added to their NPC. Nothing is written: review, then Save. A report lists what<br/>"
    "changed and what could not be applied (map or NPC missing, script changed by a mod...).")
NO_CARD_GAME_COLOR = QColor(150, 150, 150)  # NPCs that do not play cards
ADD_BUTTON_COLOR = QColor(40, 150, 60)
ADD_CARD_GAME_TEXT = "+ Add card game"
NPC_ROLE = Qt.ItemDataRole.UserRole + 1  # tree item data of an NPC without a card game: (jsm_file, NpcEntity)
MAP_ROLE = Qt.ItemDataRole.UserRole + 2  # tree item data of a map row: its JsmCardGameFile


class CardImages:
    """Card names and thumbnails from the shared card data (card.json + the card sheet)."""

    def __init__(self, game_data):
        self.card_info = game_data.card_data_json["card_info"]
        self.names = [card["name"] for card in self.card_info]
        self.__pixmaps = {}

    def pixmap(self, card_id: int, size: int = CARD_THUMBNAIL_SIZE):
        key = (card_id, size)
        if key not in self.__pixmaps:
            image = self.card_info[card_id]["img"].resize((size, size))
            self.__pixmaps[key] = QPixmap.fromImage(ImageQt(image))
        return self.__pixmaps[key]

    def label(self, card_id: int, size: int = CARD_THUMBNAIL_SIZE, dimmed: bool = False):
        """A QLabel showing the card, with its name and id as tooltip."""
        label = QLabel()
        label.setPixmap(self.pixmap(card_id, size))
        label.setFixedSize(size, size)
        tooltip = f"{self.names[card_id]} (card {card_id})"
        if dimmed:
            label.setEnabled(False)
            tooltip += " - never dealt: the deck builder re-rolls this card"
        label.setToolTip(tooltip)
        return label


def wrapped_label(text: str):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


TOOLTIP_VARIANT = (
    "<b>Variants</b><br/>"
    "This NPC's script holds several CARDGAME calls, each with its own deck, rules and AI,<br/>"
    "and branches to one of them before the match: on a <b>random roll</b> (RND, 0-255) or on<br/>"
    "the <b>game state</b> (story progress, flags...). The conditions below are the branches<br/>"
    "that lead to this call; the values in boxes are the numbers the script compares with,<br/>"
    "and can be edited in place (e.g. change 85 to 128 to make the first variant 50%).")


def variant_text(player: CardGamePlayer):
    """Short description of how a variant is picked: its random chance, or its conditions."""
    variant = player.variant
    chance = variant.random_chance()
    conditions = " and ".join(condition.text() for condition in variant.conditions) or "always"
    if chance is not None:
        return f"{chance:.0f}% ({variant.random_ranges_text()} of 0-255)"
    return conditions


class VariantGroup(QGroupBox):
    """Which of the script's CARDGAME calls this is, and the editable conditions that pick it."""

    def __init__(self, player: CardGamePlayer, changed_callback, select_player_callback):
        variant = player.variant
        QGroupBox.__init__(self, f"Variant {variant.index + 1} of {len(variant.siblings)}"
                                 f" ({player.entity_name}::{player.script_name})")
        self.setToolTip(TOOLTIP_VARIANT)
        self.player = player
        self.changed_callback = changed_callback
        self.select_player_callback = select_player_callback
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(wrapped_label(
            f"The script of {player.entity_name} holds {len(variant.siblings)} CARDGAME calls and branches to"
            f" one of them before the match. This one plays when:"))
        if not variant.conditions:
            layout.addWidget(QLabel("<i>(no branch found before this call)</i>"))
        for condition in variant.conditions:
            row = QHBoxLayout()
            row.addWidget(QLabel("\u2022"))
            for token in condition.tokens():
                if isinstance(token, str):
                    row.addWidget(QLabel(token))
                else:
                    row.addWidget(self.__literal_spinbox(token))
            row.addStretch(1)
            layout.addLayout(row)
        self.chance_label = QLabel()
        layout.addWidget(self.chance_label)
        layout.addWidget(QLabel("All the variants of this script:"))
        self.siblings_label = QLabel()
        self.siblings_label.setWordWrap(True)
        self.siblings_label.linkActivated.connect(self.__link_activated)
        layout.addWidget(self.siblings_label)
        self.refresh()

    def __literal_spinbox(self, literal):
        spinbox = QSpinBox()
        spinbox.setRange(-0x800000, 0x7FFFFF)
        spinbox.setValue(literal.value)
        spinbox.wheelEvent = lambda event: None
        spinbox.setToolTip(f"Number the script compares with (PSHN_L at file offset 0x{literal.file_offset:X}),"
                           f" original value {literal.original_value}. Shared by every variant that tests it.")

        def value_changed(value):
            literal.value = value
            self.refresh()
            self.changed_callback(self.player)

        spinbox.valueChanged.connect(value_changed)
        return spinbox

    def refresh(self):
        variant = self.player.variant
        chance = variant.random_chance()
        self.chance_label.setText(f"<b>Chance: {chance:.1f}%</b> of the random rolls pick this variant."
                                  if chance is not None else "")
        self.chance_label.setVisible(chance is not None)
        lines = []
        for index, sibling in enumerate(variant.siblings):
            text = f"{index + 1}. {variant_text(sibling)}"
            if sibling is self.player:
                lines.append(f"<b>{text} (this one)</b>")
            else:
                lines.append(f'<a href="{index}">{text}</a>')
        self.siblings_label.setText("<br/>".join(lines))

    def __link_activated(self, link: str):
        self.select_player_callback(self.player.variant.siblings[int(link)])


class TextsGroup(QGroupBox):
    """The texts of a card player's script (question, 'not enough cards', other lines), editable in
    the map's .msd. A message several script lines show is changed for all of them."""

    def __init__(self, player: CardGamePlayer, jsm_file, manager, changed_callback=None):
        QGroupBox.__init__(self, "Texts")
        self.player = player
        self.changed_callback = changed_callback
        layout = QGridLayout()
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)
        self.editors = {}  # message id -> QPlainTextEdit
        msd_file = manager.msd(jsm_file)
        if msd_file is None:
            label = QLabel(f"No {jsm_file.map_name}.msd in the opened folders: the texts cannot be shown. A mod's field"
                           f" folder holds only the files it changes: open the vanilla field folder (Import"
                           f" complementary) to read them from it.")
            label.setWordWrap(True)
            layout.addWidget(label, 0, 0, 1, 2)
            return
        uses_in_file = Counter()
        instructions = jsm_file.instructions()
        for index, (opcode, _) in enumerate(instructions):
            nb_values = jsm_npc.MESSAGE_OPCODES.get(opcode)
            if nb_values is not None and index >= nb_values and instructions[index - nb_values + 1][0] == OPCODE_PSHN_L:
                uses_in_file[instructions[index - nb_values + 1][1]] += 1
        row = 0
        for use in jsm_npc.player_messages(jsm_file, player):
            if use.message_id in self.editors or not 0 <= use.message_id < len(msd_file):
                continue
            role = QLabel(f"{use.role}:")
            role.setToolTip(f"Message {use.message_id} of {jsm_file.map_name}.msd")
            editor = QPlainTextEdit(msd_file.text(use.message_id))
            editor.setFixedHeight(editor.fontMetrics().height() * (msd_file.text(use.message_id).count("\n") + 1) + 14)
            tooltip = f"Message {use.message_id} of {jsm_file.map_name}.msd."
            if uses_in_file[use.message_id] > 1:
                tooltip += f" Shown by {uses_in_file[use.message_id]} script lines of this map: editing changes them all."
            if msd_file.encode(msd_file.text(use.message_id)) != msd_file.messages[use.message_id]:
                editor.setReadOnly(True)
                tooltip += (" Read-only: it holds codes this tool cannot re-encode exactly (edit it with"
                            " ShumiTranslator).")
            editor.setToolTip(tooltip)
            editor.textChanged.connect(lambda message_id=use.message_id, text_editor=editor, msd=msd_file:
                                       self.__text_changed(msd, message_id, text_editor))
            layout.addWidget(role, row, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(editor, row, 1)
            self.editors[use.message_id] = editor
            row += 1
        if not self.editors:
            layout.addWidget(QLabel("No text found in this script."), 0, 0, 1, 2)

    def __text_changed(self, msd_file, message_id, editor):
        msd_file.set_text(message_id, editor.toPlainText())
        if self.changed_callback is not None:
            self.changed_callback(self.player)


class RareCardsGroup(QGroupBox):
    """What the Deck ID means for rare cards: the card that starts there, the cards scripts move
    there, and the other card players sharing the same pocket (links select them)."""

    def __init__(self, card_images: CardImages, manager: CardGameFolderManager, select_player_callback):
        QGroupBox.__init__(self, "Rare cards (Deck ID)")
        self.card_images = card_images
        self.manager = manager
        self.select_player_callback = select_player_callback
        self.shared_players = []
        self.__layout = QVBoxLayout()
        self.setLayout(self.__layout)

    def refresh(self, player: CardGamePlayer):
        clear_layout(self.__layout)
        self.shared_players = []
        deck_param = player.params[PARAM_DECK_ID]
        if not deck_param.is_literal():
            self.__layout.addWidget(QLabel("The Deck ID is decided at runtime, the rare cards cannot be known."))
            return
        deck_id = deck_param.value
        if deck_id == cardlocation.LOCATION_NO_RARE:
            self.__layout.addWidget(QLabel("Deck ID 0: this NPC never plays rare cards."))
            return
        if deck_id == cardlocation.LOCATION_PLAYER:
            self.__layout.addWidget(wrapped_label("Deck ID 240 is the player's own collection: the rare cards the"
                                           " player owns are the ones this NPC can play."))

        start_card = cardlocation.starting_rare_card(deck_id)
        if start_card is not None:
            row = QHBoxLayout()
            row.addWidget(self.card_images.label(start_card))
            row.addWidget(wrapped_label(f"<b>{self.card_images.names[start_card]}</b> starts the game here"
                                        f" (rare card {start_card} starts at location {start_card} + 123 = {deck_id})."
                                        f"<br/>The NPC keeps it until the player wins it."), 1)
            self.__layout.addLayout(row)
        elif deck_id != cardlocation.LOCATION_PLAYER:
            self.__layout.addWidget(QLabel("No rare card starts the game at this Deck ID."))

        seen_moves = set()
        move_rows = []
        for move in self.manager.moves_to_location(deck_id):
            key = (move.card_id, move.map_name, move.entity_name)
            if cardlocation.is_rare_card(move.card_id) and key not in seen_moves:
                seen_moves.add(key)
                move_rows.append(move)
        if move_rows:
            self.__layout.addWidget(QLabel("Rare cards the field scripts can move here (SETCARD):"))
            for move in move_rows:
                row = QHBoxLayout()
                row.addWidget(self.card_images.label(move.card_id, 32))
                row.addWidget(QLabel(f"{self.card_images.names[move.card_id]} - by"
                                     f" {move.entity_name}::{move.script_name} in {move.map_name}"))
                row.addStretch(1)
                self.__layout.addLayout(row)

        self.shared_players = [(jsm_file, other) for jsm_file, other in self.manager.players_with_deck_id(deck_id)
                               if other is not player]
        if self.shared_players:
            # An NPC with several CARDGAME calls (story variants) is listed once, with its call count
            link_names = {}
            for index, (jsm_file, other) in enumerate(self.shared_players):
                key = (jsm_file.map_name, other.entity_name)
                if key not in link_names:
                    link_names[key] = [index, 0]
                link_names[key][1] += 1
            links = ", ".join(f'<a href="{index}">{entity_name} ({map_name})</a>' + (f" x{count}" if count > 1 else "")
                              for (map_name, entity_name), (index, count) in link_names.items())
            shared_label = QLabel(f"Also used by: {links}<br/><i>They share this pocket: a rare card"
                                  f" lost to one of them can be played by all of them.</i>")
            shared_label.setWordWrap(True)
            shared_label.linkActivated.connect(self.__link_activated)
            self.__layout.addWidget(shared_label)
        else:
            self.__layout.addWidget(QLabel("No other card player uses this Deck ID."))

    def __link_activated(self, link: str):
        _, other = self.shared_players[int(link)]
        self.select_player_callback(other)


class DeckPreviewGroup(QGroupBox):
    """The cards the NPC can deal: rare candidates with their chance, the normal card pool of the
    allowed levels, and a sample hand dealt with the game's algorithm."""

    def __init__(self, card_images: CardImages, level_options=()):
        QGroupBox.__init__(self, "Deck preview")
        self.card_images = card_images
        self.level_options = list(level_options)  # how the map script sets a variable level mask
        self.__player = None
        self.hand = []
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        self.__info_layout = QVBoxLayout()
        main_layout.addLayout(self.__info_layout)

        self.level_option_combobox = QComboBox()
        self.level_option_combobox.wheelEvent = lambda event: None
        self.level_option_combobox.setToolTip("How the map script sets the level variable right before the"
                                              " match. 'Any' deals like the game: a random option each time.")
        if len(self.level_options) > 1:
            self.level_option_combobox.addItem("Any of them (rolled like the script)")
        for option in self.level_options:
            if option.is_random():
                self.level_option_combobox.addItem(
                    f"Always {cardlocation.levels_text(option.always_bits)} + random among"
                    f" {cardlocation.levels_text(option.random_bits & ~option.always_bits)}")
            else:
                self.level_option_combobox.addItem(
                    f"{option.always_bits} = {cardlocation.levels_text(option.always_bits)}")
        self.level_option_combobox.currentIndexChanged.connect(self.__level_option_changed)
        self.__level_option_row = QWidget()
        option_layout = QHBoxLayout()
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.addWidget(QLabel("Levels the script can set:"))
        option_layout.addWidget(self.level_option_combobox)
        option_layout.addStretch(1)
        self.__level_option_row.setLayout(option_layout)
        main_layout.addWidget(self.__level_option_row)
        main_layout.addWidget(wrapped_label("<b>Normal cards</b> the NPC can deal (one random allowed level,"
                                     " then one random card of it, no duplicates):"))
        self.__pool_layout = QGridLayout()
        self.__pool_layout.setHorizontalSpacing(2)
        self.__pool_layout.setVerticalSpacing(2)
        pool_row = QHBoxLayout()
        pool_row.addLayout(self.__pool_layout)
        pool_row.addStretch(1)
        main_layout.addLayout(pool_row)

        hand_title = QHBoxLayout()
        hand_title.addWidget(QLabel("<b>Sample hand</b> (dealt like the game does, with the rare cards"
                                    " at their new-game locations):"))
        self.deal_button = QPushButton("Deal another")
        self.deal_button.setToolTip("Deal a new random hand with the current parameters")
        self.deal_button.clicked.connect(self.deal)
        hand_title.addWidget(self.deal_button)
        hand_title.addStretch(1)
        main_layout.addLayout(hand_title)
        self.__hand_layout = QHBoxLayout()
        main_layout.addLayout(self.__hand_layout)

    def refresh(self, player: CardGamePlayer):
        self.__player = player
        clear_layout(self.__info_layout)
        clear_layout(self.__pool_layout)
        level_mask = self.__level_mask()
        level_param = player.params[PARAM_LEVEL_MASK]
        uses_script_levels = not level_param.is_literal() and bool(self.level_options)
        self.__level_option_row.setVisible(uses_script_levels)
        if uses_script_levels:
            self.__info_layout.addWidget(wrapped_label(f"The card levels come from variable {level_param.value},"
                                                       f" set by this map's script right before the match."))
        elif not level_param.is_literal():
            self.__info_layout.addWidget(wrapped_label(f"<i>The card levels come from savemap variable"
                                                       f" {level_param.value} at runtime and no script of this map"
                                                       f" sets it in a known way; the preview shows the level 1"
                                                       f" fallback.</i>"))
        elif level_mask & 0xFF == 0:
            self.__info_layout.addWidget(QLabel("<i>No level checked: the game falls back to level 1.</i>"))

        rare_candidates = self.__rare_candidates()
        rare_param = player.params[PARAM_RARE_CHANCE]
        if rare_candidates:
            if rare_param.is_literal():
                chances = cardlocation.rare_pick_chances(len(rare_candidates), rare_param.value)
                text = ", ".join(f"{self.card_images.names[card_id]} {chance}%"
                                 for card_id, chance in zip(rare_candidates, chances))
                self.__info_layout.addWidget(wrapped_label(f"<b>Rare cards</b> at the start: {text}"))
            else:
                self.__info_layout.addWidget(QLabel("Rare card chance decided at runtime."))

        for row, level in enumerate(cardlocation.enabled_levels(level_mask)):
            self.__pool_layout.addWidget(QLabel(f"Lv{level + 1}"), row, 0)
            for column, card_id in enumerate(cardlocation.level_cards(level)):
                self.__pool_layout.addWidget(
                    self.card_images.label(card_id, 40, dimmed=card_id == cardlocation.CARD_NEVER_DEALT),
                    row, column + 1)
        self.deal()

    def __level_option_changed(self, _index: int):
        if self.__player is not None:
            self.refresh(self.__player)

    def __selected_level_options(self):
        """The script options the preview follows: the selected one, or all of them for 'Any'."""
        index = self.level_option_combobox.currentIndex()
        if len(self.level_options) > 1:
            if index <= 0:
                return self.level_options
            index -= 1
        return [self.level_options[max(index, 0)]]

    def __level_mask(self):
        """Every level the NPC can use: the literal mask, or for a script variable the union of the
        levels the selected script options can set (0 = the game's level 1 fallback)."""
        level_param = self.__player.params[PARAM_LEVEL_MASK]
        if level_param.is_literal():
            return level_param.value
        mask = 0
        if self.level_options:
            for option in self.__selected_level_options():
                mask |= option.union_mask()
        return mask

    def __rolled_level_mask(self, rng):
        """The level mask of one match: a script variable is rolled like the script does."""
        level_param = self.__player.params[PARAM_LEVEL_MASK]
        if level_param.is_literal() or not self.level_options:
            return self.__level_mask()
        options = self.__selected_level_options()
        return options[rng.randrange(len(options))].roll(rng)

    def __rare_candidates(self):
        deck_param = self.__player.params[PARAM_DECK_ID]
        if not deck_param.is_literal():
            return []
        start_card = cardlocation.starting_rare_card(deck_param.value)
        return [] if start_card is None else [start_card]

    def deal(self):
        if self.__player is None:
            return
        clear_layout(self.__hand_layout)
        rare_param = self.__player.params[PARAM_RARE_CHANCE]
        rng = random.Random()
        self.hand = cardlocation.roll_opponent_hand(self.__rolled_level_mask(rng),
                                                    rare_param.value if rare_param.is_literal() else 0,
                                                    self.__rare_candidates(), rng)
        for card_id in self.hand:
            self.__hand_layout.addWidget(self.card_images.label(card_id, 64))
        self.__hand_layout.addStretch(1)


class ClockGroup(QGroupBox):
    """Cronos turn clock of one card player: starting time and increment."""

    def __init__(self, player: CardGamePlayer, changed_callback):
        QGroupBox.__init__(self, "Cronos: turn clock")
        self.setToolTip(TOOLTIP_CLOCK)
        self.player = player
        self.changed_callback = changed_callback
        self.seconds_spinbox = QSpinBox()
        self.seconds_spinbox.setRange(0, CLOCK_MAX_SECONDS)
        self.seconds_spinbox.setSuffix(" s")
        self.seconds_spinbox.setSpecialValueText("No clock")
        self.seconds_spinbox.setValue(player.clock_seconds)
        self.increment_spinbox = QSpinBox()
        self.increment_spinbox.setRange(0, CLOCK_MAX_INCREMENT)
        self.increment_spinbox.setSuffix(" s per card placed")
        self.increment_spinbox.setValue(player.clock_increment)
        self.summary_label = QLabel()
        for spinbox in (self.seconds_spinbox, self.increment_spinbox):
            spinbox.setToolTip(TOOLTIP_CLOCK)
            spinbox.wheelEvent = lambda event: None
            spinbox.valueChanged.connect(lambda _: self.__changed())
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Starting time:"))
        layout.addWidget(self.seconds_spinbox)
        layout.addWidget(QLabel("Increment:"))
        layout.addWidget(self.increment_spinbox)
        layout.addWidget(self.summary_label)
        layout.addStretch(1)
        self.setLayout(layout)
        self.__refresh()

    def __changed(self):
        self.player.set_clock(self.seconds_spinbox.value(), self.increment_spinbox.value())
        self.__refresh()
        self.changed_callback()

    def __refresh(self):
        has_clock = self.player.clock_seconds > 0
        self.increment_spinbox.setEnabled(has_clock)
        self.summary_label.setText(f"= {clock_text(*self.player.clock())}" if has_clock else "")


class CardPlayerWidget(QWidget):
    """Editor of the 7 CARDGAME parameters of one NPC, with the rare cards and deck preview."""

    def __init__(self, player: CardGamePlayer, card_images: CardImages, manager: CardGameFolderManager,
                 changed_callback=None, select_player_callback=None, cronos_options=False):
        QWidget.__init__(self)
        self.player = player
        self.changed_callback = changed_callback
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        params_group = QGroupBox(f"{player.entity_name}  ({player.script_name})")
        params_group.setToolTip(f"CARDGAME call at file offset 0x{player.cardgame_file_offset:X},"
                                f" script {player.entity_name}::{player.script_name}")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        params_group.setLayout(grid)
        main_layout.addWidget(params_group)

        self.rows = [
            DeckIdParamRow(player.params[PARAM_DECK_ID], card_images.names),
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
                            variable_option=self.__script_levels_option(player.params[PARAM_LEVEL_MASK])),
        ]
        for row_index, row in enumerate(self.rows):
            row.add_to_grid(grid, row_index, row.layout())
            row.on_change = self.__param_changed
        self.clock_group = None
        if cronos_options:
            self.clock_group = ClockGroup(player, self.__param_changed)
            main_layout.addWidget(self.clock_group)

        select_player_callback = select_player_callback or (lambda _: None)
        jsm_file = manager.file_of(player)
        if jsm_file is not None:
            main_layout.addWidget(TextsGroup(player, jsm_file, manager, changed_callback))
        if player.variant is not None and player.variant.is_variant():
            main_layout.addWidget(VariantGroup(player, self.__variant_changed, select_player_callback))
        self.rare_cards_group = RareCardsGroup(card_images, manager, select_player_callback)
        main_layout.addWidget(self.rare_cards_group)
        jsm_file = manager.file_of(player)
        level_param = player.params[PARAM_LEVEL_MASK]
        level_options = []
        if jsm_file is not None and level_param.original_opcode != OPCODE_PSHN_L:
            level_options = jsm_file.level_mask_options(level_param.original_value)
        self.deck_preview_group = DeckPreviewGroup(card_images, level_options)
        main_layout.addWidget(self.deck_preview_group)
        self.__refresh_previews()

    @staticmethod
    def __script_levels_option(level_param: CardGameParam):
        if not level_param.is_variable():
            return None
        variable = level_param.original_value
        return f"Set by the script (var {variable})", [(variable, "")], TOOLTIP_SCRIPT_LEVELS

    def __refresh_previews(self):
        self.rare_cards_group.refresh(self.player)
        self.deck_preview_group.refresh(self.player)

    def __variant_changed(self, _player):
        if self.changed_callback is not None:
            for sibling in self.player.variant.siblings:  # a shared literal changes their odds too
                self.changed_callback(sibling)

    def __param_changed(self):
        self.__refresh_previews()
        if self.changed_callback is not None:
            self.changed_callback(self.player)


class NpcCardGameWidget(QWidget):
    """The 'NPC card players' tab.

    Two field folders, opened from the header in any order (see CCGroupWidget):
    - the edited one (Import): what Save writes to - a mod's field folder holding only the maps it
      changes, or a whole copy of the game's;
    - the vanilla reference (Import complementary, read-only): the whole game, so every NPC is
      listed and a map is read from the edited folder only when it has it.

    Left: a filterable map/NPC tree of every card player found. Right: the parameter editor of the
    selected player (built on demand - a full game dump contains hundreds of players, so only one
    editor exists at a time)."""

    folders_changed = pyqtSignal()  # the edited or the reference folder was set, changed or closed

    EDITED_TITLE = "Field folder you edit"
    REFERENCE_TITLE = "Vanilla field folder (reference)"
    NO_EDITED_TEXT = "none - Import > " + EDITED_TITLE
    NO_REFERENCE_TEXT = "none - Import complementary > " + REFERENCE_TITLE
    NO_FOLDER_TEXT = ("Open a field folder from the header: Import > " + EDITED_TITLE + " (a mod's field folder,"
                      " or a whole extracted one), and Import complementary > " + REFERENCE_TITLE + ".")
    TOOLTIP_FOLDERS = (
        "<b>Field folder you edit</b> (Import, e.g. a mod's ...\\FieldRework\\field)<br/>"
        "What Save writes to. A mod's folder holds only the maps it changes, at the same paths as<br/>"
        "vanilla: a map is read from it when it has it (the mod's own changes are kept), else from vanilla.<br/><br/>"
        "<b>Vanilla field folder</b> (Import complementary, read-only)<br/>"
        "The whole game's field folder: every NPC is listed from it, and with it Save writes only the<br/>"
        "maps whose script differs from vanilla (a map edited back to vanilla is not written, and you<br/>"
        "are offered to delete it from the edited folder). It is never written to.<br/><br/>"
        "Only the vanilla folder open: Save asks where to create the mod's field folder.<br/>"
        "Only the edited folder open: Save writes the edited maps in place.")

    def __init__(self, icon_path='Resources', settings: QSettings = None, game_data=None):
        QWidget.__init__(self)
        if game_data is None:  # Used alone: load the card names and images itself
            from FF8GameData.gamedata import GameData
            game_data = GameData()
        if getattr(game_data, "card_data_json", None) is None:
            game_data.load_card_data()
        self.card_images = CardImages(game_data)
        self.game_data = game_data
        self.__player_items = {}  # id(player) -> its tree item
        self.manager = CardGameFolderManager(game_data)
        self.working_folder = ""    # the field folder Save writes to
        self.reference_folder = ""  # the vanilla field folder (read-only)
        self.settings = settings

        self.__main_layout = QVBoxLayout()
        self.setLayout(self.__main_layout)

        # Opening the folders and saving the patched .jsm files all run from the shared header
        # toolbar (see CCGroupWidget.import_entries / save_folder); this tab keeps only its list.
        self.__info_label = QLabel(self.NO_FOLDER_TEXT)
        self.__info_label.setWordWrap(True)
        self.cronos_options_checkbox = QCheckBox("Cronos options")
        self.cronos_options_checkbox.setToolTip(TOOLTIP_CRONOS_OPTIONS)
        if settings is not None:
            self.cronos_options_checkbox.setChecked(settings.value("ccgroup/cronos_options", False, type=bool))
        self.cronos_options_checkbox.toggled.connect(self.__cronos_options_toggled)

        # Where the card players come from and where Save writes, at a glance
        self.__sources_label = QLabel()
        self.__sources_label.setToolTip(self.TOOLTIP_FOLDERS)
        self.__sources_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sources_layout = QVBoxLayout()
        sources_layout.setSpacing(2)
        sources_layout.addWidget(self.__sources_label)
        sources_layout.addWidget(self.__info_label)

        # The card players file: every card player in one readable file, to keep or apply elsewhere
        self.export_button = QPushButton("Export card players...")
        self.export_button.setToolTip(TOOLTIP_EXPORT)
        self.export_button.clicked.connect(self.export_card_players)
        self.apply_button = QPushButton("Apply card players file...")
        self.apply_button.setToolTip(TOOLTIP_APPLY)
        self.apply_button.clicked.connect(self.apply_card_players)
        file_layout = QVBoxLayout()
        file_layout.setSpacing(2)
        file_layout.addWidget(self.export_button)
        file_layout.addWidget(self.apply_button)

        self.__layout_top = QHBoxLayout()
        self.__layout_top.addLayout(file_layout)
        self.__layout_top.addWidget(self.cronos_options_checkbox, 0, Qt.AlignmentFlag.AlignTop)
        self.__layout_top.addLayout(sources_layout, 1)
        self.__main_layout.addLayout(self.__layout_top)

        # Left pane: filter + tree of maps/players
        self.__filter_edit = QLineEdit()
        self.__filter_edit.setPlaceholderText("Filter by map or NPC name...")
        self.__filter_edit.setClearButtonEnabled(True)
        self.__filter_edit.textChanged.connect(self.__filter_changed)
        self.__show_all_checkbox = QCheckBox("Show the NPCs without a card game")
        self.__show_all_checkbox.setChecked(True)
        self.__show_all_checkbox.setToolTip("Also list every NPC that does not play cards (greyed), with a button to give\n"
                                            "them a card game. Main characters (party members met as NPCs) are marked.")
        self.__show_all_checkbox.toggled.connect(lambda _: self.__rebuild_tree_keeping_selection())
        self.__tree = QTreeWidget()
        self.__tree.setColumnCount(2)
        self.__tree.setHeaderHidden(True)
        self.__tree.header().setStretchLastSection(False)
        self.__tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.__tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.__tree.currentItemChanged.connect(self.__selection_changed)
        self.__tree.itemClicked.connect(self.__item_clicked)
        self.__legend = QLabel()  # follows which folders are open (see __update_labels)
        self.__legend.setWordWrap(True)
        legend = self.__legend
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.__filter_edit)
        left_layout.addWidget(self.__show_all_checkbox)
        left_layout.addWidget(self.__tree)
        left_layout.addWidget(legend)
        left_widget.setLayout(left_layout)

        # Right pane: editor of the selected player
        self.__editor_scroll = QScrollArea()
        self.__editor_scroll.setWidgetResizable(True)
        self.__editor_scroll.setWidget(QLabel("Select a card player in the list."))

        # Right pane: where the NPC stands (field background) and its 3D model
        self.field_view = NpcFieldView()

        self.__splitter = QSplitter(Qt.Orientation.Horizontal)
        self.__splitter.addWidget(left_widget)
        self.__splitter.addWidget(self.__editor_scroll)
        self.__splitter.addWidget(self.field_view)
        self.__splitter.setStretchFactor(0, 1)
        self.__splitter.setStretchFactor(1, 2)
        self.__splitter.setStretchFactor(2, 2)
        self.__splitter.setSizes([360, 680, 480])

        # Two views of the same players: one at a time (Editor) or all in a table (bulk edits)
        self.table_widget = NpcCardTableWidget(self.card_images.names)
        self.table_widget.set_cronos_options(self.cronos_options_checkbox.isChecked())
        self.table_widget.players_changed.connect(self.__players_bulk_changed)
        self.table_widget.open_player.connect(self.__open_from_table)
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.__splitter, "Editor")
        self.view_tabs.addTab(self.table_widget, "Table (bulk edit)")
        self.view_tabs.currentChanged.connect(self.__view_changed)
        self.__main_layout.addWidget(self.view_tabs, 1)
        self.__update_labels()

    @staticmethod
    def __same_folder(first: str, second: str):
        return bool(first and second) and \
            os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))

    def set_working_folder(self, folder_path: str):
        """The field folder you edit (see the class doc). A checked field folder (Common.fieldfolder).
        Returns whether it is now used."""
        if self.__same_folder(folder_path, self.reference_folder):
            QMessageBox.warning(self, "CC Group", f"This folder is already open as the vanilla reference:\n"
                                                  f"{folder_path}\n\nThe folder you edit must be another one.")
            return False
        if not self.__confirm_discard():
            return False
        self.working_folder = folder_path
        self.__reload()
        return True

    def set_reference_folder(self, folder_path: str):
        """The vanilla field folder, read-only (see the class doc). A checked complete field folder
        (Common.fieldfolder). Returns whether it is now used."""
        if self.__same_folder(folder_path, self.working_folder):
            QMessageBox.warning(self, "CC Group", f"This folder is already open as the folder you edit:\n"
                                                  f"{folder_path}\n\nThe vanilla reference must be another one.")
            return False
        if not self.__confirm_discard():
            return False
        self.reference_folder = folder_path
        self.__reload()
        return True

    def __cronos_options_toggled(self, checked: bool):
        if self.settings is not None:
            self.settings.setValue("ccgroup/cronos_options", checked)
        self.table_widget.set_cronos_options(checked)
        for player, item in ((item.data(0, Qt.ItemDataRole.UserRole), item) for item in self.__player_items.values()):
            item.setText(0, self.player_label(player))
        current = self.__tree.currentItem()
        player = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        if player is not None:
            self.__show_editor(player)

    def __confirm_discard(self):
        """Reloading drops unsaved edits: ask first when there are some."""
        if not self.manager.has_modifications():
            return True
        answer = QMessageBox.question(self, "CC Group", "Unsaved card player changes will be lost. Continue?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def __base_and_overlay(self):
        """The manager's (vanilla, modified) pair: the reference under the edited folder when both
        are open, else the one folder open alone (edited in place, or browsed until Save)."""
        if self.reference_folder:
            return self.reference_folder, self.working_folder
        return self.working_folder, ""

    def __reload(self):
        base, overlay = self.__base_and_overlay()
        if base:
            with busy_cursor():  # ~880 scripts for a whole game: a couple of seconds
                self.manager.load_folder(base, overlay)
        else:
            self.manager = CardGameFolderManager(self.game_data)
        self.field_view.set_field_folders(base, overlay, reference_open=bool(self.reference_folder))
        self.__rebuild_tree()
        self.table_widget.set_manager(self.manager)
        self.__update_labels()
        self.folders_changed.emit()

    def __update_labels(self):
        edited = self.working_folder or f"<i>{self.NO_EDITED_TEXT}</i>"
        reference = self.reference_folder or f"<i>{self.NO_REFERENCE_TEXT}</i>"
        self.__sources_label.setText(f"<b>{self.EDITED_TITLE}:</b> {edited}<br/>"
                                     f"<b>{self.REFERENCE_TITLE}:</b> {reference}")
        self.__legend.setText(self.__legend_text())
        players_loaded = self.manager.nb_players() > 0
        self.export_button.setEnabled(players_loaded)
        self.apply_button.setEnabled(players_loaded)
        nb_players = self.manager.nb_players()
        if not self.working_folder and not self.reference_folder:
            self.__info_label.setText(self.NO_FOLDER_TEXT)
            return
        text = (f"{nb_players} card player(s) in {len(self.manager.jsm_files)} map(s)" if nb_players
                else "No card player found")
        if self.working_folder and self.reference_folder:
            text += (f" ({self.manager.nb_from_modified_folder()} map(s) read from the folder you edit). Save writes"
                     f" only into the folder you edit, only the maps that differ from vanilla.")
        elif self.reference_folder:
            text += ". Save asks where to create the mod's field folder: vanilla is never written to."
        else:
            text += ". Save writes the edited maps in place."
            if len(self.manager.all_files) < VANILLA_MIN_MAPS:
                text += (f" <span style='color:{NO_CARD_MASTER_COLOR.name()}'>Only {len(self.manager.all_files)}"
                         f" map(s) here: also open the vanilla field folder (Import complementary) to list every"
                         f" NPC of the game.</span>")
        self.__info_label.setText(text)

    def __file_dialog_folder(self):
        folder = self.settings.value("ccgroup/cardplayers_folder", "", type=str) if self.settings is not None else ""
        return folder or os.path.dirname(self.working_folder or self.reference_folder)

    def __remember_file_folder(self, path):
        if self.settings is not None:
            self.settings.setValue("ccgroup/cardplayers_folder", os.path.dirname(path))

    def export_card_players(self, path: str = ""):
        """Write every card player to a card players file (asks where when no path is given)."""
        if not path:
            path = QFileDialog.getSaveFileName(
                self, "Export every card player", os.path.join(self.__file_dialog_folder(), DEFAULT_EXPORT_NAME),
                cardplayersfile.FILE_FILTER)[0]
            if not path:
                return None
            if not path.lower().endswith(".json"):
                path += ".cardplayers.json"
        self.__remember_file_folder(path)
        compare = bool(self.working_folder and self.reference_folder)
        with busy_cursor():
            content = cardplayersfile.export_players(self.manager, compare)
        try:
            cardplayersfile.write_file(path, content)
        except OSError as error:
            QMessageBox.warning(self, "CC Group", f"Could not write {path}:\n{error}")
            return None
        players = content["players"]
        text = f"{len(players)} card player(s) exported to:\n{path}"
        if compare:
            changed = sum(1 for record in players if record.get("changed"))
            added = sum(1 for record in players if "added" in record)
            text += f"\n\n{changed} differ from vanilla, {added} of them added to an NPC."
        else:
            text += ("\n\nOpen both the folder you edit and the vanilla reference to also mark what differs from"
                     " vanilla and which card games were added (then applying the file adds them).")
        QMessageBox.information(self, "CC Group", text)
        return content

    def apply_card_players(self, path: str = ""):
        """Apply a card players file onto the opened folders, as unsaved edits (Save writes them)."""
        if not path:
            path = QFileDialog.getOpenFileName(self, "Apply a card players file", self.__file_dialog_folder(),
                                               cardplayersfile.FILE_FILTER)[0]
            if not path:
                return None
        self.__remember_file_folder(path)
        try:
            content = cardplayersfile.read_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "CC Group", f"Could not apply {path}:\n{error}")
            return None
        with busy_cursor():
            report = cardplayersfile.apply_players(self.manager, content)
        self.__rebuild_tree_keeping_selection()
        lines = [f"{len(report.changed)} card player(s) changed, {len(report.added)} card game(s) added to an NPC,"
                 f" {report.unchanged} already as in the file."]
        for title, items in (("Changed", report.changed), ("Added", report.added),
                             ("Not applied", report.not_found), ("Partly applied", report.problems)):
            if items:
                lines.append(f"\n{title}:\n" + "\n".join(f"  - {item}" for item in items[:20])
                             + (f"\n  ... and {len(items) - 20} more" if len(items) > 20 else ""))
        if report.changed or report.added:
            lines.append("\nNothing is written yet: review the changes (bold maps), then Save.")
        QMessageBox.information(self, "CC Group", "\n".join(lines))
        return report

    def __legend_text(self):
        """What the tree's marks mean, for the folders open now."""
        if self.working_folder and self.reference_folder:
            source = (f'<span style="color:{MODIFIED_FOLDER_COLOR.name()}"><b>Blue map</b> [mod]</span>: read from the'
                      f' folder you edit (the mod changes it); the others come from vanilla.')
        elif self.working_folder:
            source = "Every map is read from the folder you edit."
        elif self.reference_folder:
            source = "Every map is read from vanilla (never written to)."
        else:
            return ""
        return (f"{source} <b>* Bold map</b>: unsaved changes."
                f' <span style="color:{NO_CARD_MASTER_COLOR.name()}">{NO_CARD_MASTER_TEXT}</span>: a card game added'
                f" there uses the region rules directly (no Queen of Cards rule spreading)."
                f' <span style="color:{NO_CARD_GAME_COLOR.name()}">Grey</span>: NPC without a card game.')

    def close_working_folder(self):
        """Stop using the folder you edit (unsaved patches dropped); the reference stays open."""
        self.working_folder = ""
        self.__reload()

    def close_reference_folder(self):
        """Stop using the vanilla reference (unsaved patches dropped); the edited folder stays open."""
        self.reference_folder = ""
        self.__reload()

    def close_folder(self):
        """Forget both folders and their card players (unsaved patches included)."""
        self.working_folder = ""
        self.reference_folder = ""
        self.__reload()

    def player_label(self, player: CardGamePlayer):
        """Tree text of a card player: its names, plus the rare card that starts at its Deck ID."""
        text = f"{player.entity_name}  ({player.script_name})"
        deck_param = player.params[PARAM_DECK_ID]
        if deck_param.is_literal():
            start_card = cardlocation.starting_rare_card(deck_param.value)
            if start_card is not None:
                text += f"  - {self.card_images.names[start_card]}"
            elif deck_param.value == cardlocation.LOCATION_QUEEN:
                text += "  - Queen of Cards"
        variant = player.variant
        if variant is not None and variant.is_variant():
            text += f"  [variant {variant.index + 1}/{len(variant.siblings)}"
            chance = variant.random_chance()
            text += f", {chance:.0f}%]" if chance is not None else "]"
        if self.cronos_options_checkbox.isChecked() and player.clock_seconds:
            text += f"  - clock {clock_text(*player.clock())}"
        return text

    def select_player(self, player: CardGamePlayer):
        """Select a card player in the tree (clears the filter if it hides it)."""
        item = self.__player_items.get(id(player))
        if item is None:
            return
        if item.isHidden() or item.parent().isHidden():
            self.__filter_edit.clear()
        self.__tree.setCurrentItem(item)
        self.__tree.scrollToItem(item)

    def __players_bulk_changed(self, players: list):
        """A bulk edit of the table changed these players: refresh their tree labels and the editor."""
        for player in players:
            self.__player_changed(player)
        current = self.__tree.currentItem()
        current_player = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        if current_player is not None and current_player in players:
            self.__show_editor(current_player)

    def __open_from_table(self, player: CardGamePlayer):
        self.view_tabs.setCurrentIndex(0)
        self.select_player(player)

    def __view_changed(self, index: int):
        if self.view_tabs.widget(index) is self.table_widget:
            self.table_widget.refresh()  # edits made in the editor since the last look

    def __player_changed(self, player: CardGamePlayer):
        item = self.__player_items.get(id(player))
        if item is not None:
            item.setText(0, self.player_label(player))
            self.__refresh_map_item(item.parent())

    def __refresh_map_item(self, map_item):
        """Map row text: name, card players, [mod] when read from the folder you edit, bold + '*'
        while it has unsaved changes."""
        jsm_file = map_item.data(0, MAP_ROLE) if map_item is not None else None
        if jsm_file is None:
            return
        unsaved = self.manager.has_unsaved_changes(jsm_file)
        source = "  [mod]" if jsm_file.modified_path else ""
        map_item.setText(0, f"{'* ' if unsaved else ''}{jsm_file.map_name}  ({len(jsm_file.players)}){source}")
        font = map_item.font(0)
        font.setBold(unsaved)
        map_item.setFont(0, font)

    def __rebuild_tree(self):
        self.__tree.clear()
        self.__player_items = {}
        self.__show_editor(None)
        show_all = self.__show_all_checkbox.isChecked()
        files = self.manager.all_files if show_all else self.manager.jsm_files
        for jsm_file in files:
            npcs_without_cards = [npc for npc in self.manager.npcs(jsm_file) if not npc.plays_cards()] \
                if show_all else []
            if not jsm_file.players and not npcs_without_cards:
                continue
            map_item = QTreeWidgetItem(["", ""])
            map_item.setData(0, MAP_ROLE, jsm_file)
            self.__refresh_map_item(map_item)
            tooltip = jsm_file.jsm_path
            if jsm_file.modified_path and self.reference_folder:
                map_item.setForeground(0, QBrush(MODIFIED_FOLDER_COLOR))
                tooltip += "\nRead from the folder you edit (the mod changes this map), not from vanilla."
            if not jsm_npc.has_card_master(jsm_file):
                map_item.setText(1, NO_CARD_MASTER_TEXT)
                map_item.setForeground(1, QBrush(NO_CARD_MASTER_COLOR))
                map_item.setToolTip(1, TOOLTIP_NO_CARD_MASTER)
            map_item.setToolTip(0, tooltip)
            for player in jsm_file.players:
                player_item = QTreeWidgetItem([self.player_label(player), ""])
                player_item.setData(0, Qt.ItemDataRole.UserRole, player)
                self.__player_items[id(player)] = player_item
                map_item.addChild(player_item)
            for npc in npcs_without_cards:
                main = "  - main character" if npc.is_main_character else ""
                npc_item = QTreeWidgetItem([f"{npc.entity_name}  (talk){main}", ADD_CARD_GAME_TEXT])
                npc_item.setData(0, NPC_ROLE, (jsm_file, npc))
                npc_item.setForeground(0, QBrush(NO_CARD_GAME_COLOR))
                npc_item.setForeground(1, QBrush(ADD_BUTTON_COLOR))
                npc_item.setToolTip(1, "Give this NPC a card game (talk to it -> 'Will you play cards with me?')")
                map_item.addChild(npc_item)
            self.__tree.addTopLevelItem(map_item)
        self.__tree.expandAll()
        self.__filter_changed(self.__filter_edit.text())

    def __item_clicked(self, item: QTreeWidgetItem, column: int):
        if column == 1 and item.data(0, NPC_ROLE) is not None:
            jsm_file, npc = item.data(0, NPC_ROLE)
            self.add_card_game_dialog(jsm_file, npc)

    def add_card_game_dialog(self, jsm_file, npc):
        """The '+ Add card game' button: ask the texts/options, add, select the new card player."""
        calls = jsm_npc.card_master_calls(jsm_file) if jsm_npc.has_card_master(jsm_file) else None
        dialog = AddCardGameDialog(self, jsm_file.map_name, npc.entity_name, jsm_npc.has_card_master(jsm_file),
                                   calls["region"] if calls else "", self.manager.region_guess(jsm_file),
                                   self.manager.free_deck_id(), self.manager.deck_id_users)
        if dialog.exec() != AddCardGameDialog.DialogCode.Accepted:
            return
        self.add_card_game(jsm_file, npc, dialog.question_text(), dialog.not_enough_text(), dialog.region(),
                           dialog.on_no(), dialog.deck_id())

    def add_card_game(self, jsm_file, npc, question_text, not_enough_text, region=0, on_no=jsm_npc.ON_NO_NOTHING,
                      deck_id=None):
        try:
            player = self.manager.add_card_game(jsm_file, npc, question_text, not_enough_text, region, on_no,
                                                deck_id)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "CC Group", f"Could not add a card game to {npc.entity_name}:\n{error}")
            return None
        self.__rebuild_tree()
        self.table_widget.set_manager(self.manager)
        self.__update_labels()
        self.select_player(player)
        return player

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
        npc_data = current.data(0, NPC_ROLE) if current is not None else None
        if npc_data is not None:
            self.__show_npc_without_cards(*npc_data)
            return
        player = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        self.__show_editor(player)

    def __show_npc_without_cards(self, jsm_file, npc):
        old_widget = self.__editor_scroll.takeWidget()
        if old_widget is not None:
            old_widget.deleteLater()
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        text = f"<b>{npc.entity_name}</b> ({jsm_file.map_name}) does not play cards."
        if not jsm_npc.has_card_master(jsm_file):
            text += ("<br/>This map has <b>no card master</b>: a card game added here uses the region rules"
                     " directly, without the Queen of Cards rule spreading.")
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        button = QPushButton(ADD_CARD_GAME_TEXT)
        button.clicked.connect(lambda: self.add_card_game_dialog(jsm_file, npc))
        layout.addWidget(button)
        layout.addStretch(1)
        self.__editor_scroll.setWidget(panel)
        self.field_view.show_entity(jsm_file, npc.entity_name)

    def __show_editor(self, player):
        old_widget = self.__editor_scroll.takeWidget()
        if old_widget is not None:
            old_widget.deleteLater()
        if player is None:
            self.__editor_scroll.setWidget(QLabel("Select a card player in the list."))
            self.field_view.clear()
        else:
            jsm_file = self.manager.file_of(player)
            if jsm_file is not None:
                self.field_view.show_player(jsm_file, player)
            editor_widget = QWidget()
            editor_layout = QVBoxLayout()
            editor_layout.addWidget(CardPlayerWidget(player, self.card_images, self.manager,
                                                     changed_callback=self.__player_changed,
                                                     select_player_callback=self.select_player,
                                                     cronos_options=self.cronos_options_checkbox.isChecked()))
            editor_layout.addStretch(1)
            editor_widget.setLayout(editor_layout)
            self.__editor_scroll.setWidget(editor_widget)

    def save_folder(self):
        """Save the patched maps (the shared header Save button calls this): into the folder you
        edit - with the vanilla reference, only the maps that differ from vanilla; alone, in place.
        With only the vanilla reference open, first ask where to create the mod's field folder."""
        if not self.working_folder:
            if self.reference_folder and self.manager.has_modifications():
                self.__save_into_new_folder()
            else:
                QMessageBox.information(self, "CC Group", "No modification to save.")
            return
        self.__save_report()

    def __save_into_new_folder(self):
        """Only vanilla is open: pick (or create) the mod's field folder, write the patched maps
        there, then keep it open as the folder you edit."""
        folder = QFileDialog.getExistingDirectory(
            self, "Save into: pick or create the mod's 'field' folder (vanilla is never written to)",
            os.path.dirname(self.reference_folder))
        if not folder:
            return
        problem = self.__new_folder_problem(folder)
        if problem:
            QMessageBox.warning(self, "CC Group - cannot save there", problem)
            return
        if not os.path.isdir(os.path.join(folder, MAPDATA)) and os.listdir(folder):
            answer = QMessageBox.question(
                self, "CC Group", f"This folder is not empty and holds no 'mapdata' folder:\n{folder}\n\n"
                                  f"Save creates mapdata\\<area>\\<map>\\ in it, as a mod's field folder. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.working_folder = folder
        self.manager.modified_folder = folder  # write there; the reload below then reads it back
        self.__save_report()
        self.__reload()

    def __new_folder_problem(self, folder: str):
        """Why the patched maps can't be written into this new folder ("" when they can)."""
        if self.__same_folder(folder, self.reference_folder) or \
                os.path.normcase(os.path.abspath(folder)).startswith(
                    os.path.normcase(os.path.abspath(self.reference_folder)) + os.sep):
            return "This is the vanilla reference (or a folder inside it): vanilla is never written to."
        if os.path.isdir(os.path.join(folder, "field", MAPDATA)):
            return f"This folder holds a 'field' folder: pick that one instead:\n{os.path.join(folder, 'field')}"
        if not os.path.isdir(os.path.join(folder, MAPDATA)):
            return ""
        check = check_field_folder(folder)
        if check.misplaced or (not check.ok and check.maps):
            return check.error
        # An existing mod folder: writing a map it already has would lose the mod's own changes.
        edited = [jsm_file.rel_path for jsm_file in self.manager.all_files or self.manager.jsm_files
                  if jsm_file.is_modified()]
        clashes = [rel_path for rel_path in edited if os.path.isfile(os.path.join(folder, rel_path))]
        if clashes:
            listed = "\n".join(f"    {rel_path}" for rel_path in clashes[:5])
            return (f"This mod folder already has its own version of map(s) you edited:\n{listed}\n\n"
                    f"Saving would replace them and lose the mod's own changes. Open it with Import > "
                    f"{self.EDITED_TITLE} first (its changes are kept, yours are made on top), or pick another folder.")
        return ""

    def __save_report(self):
        report = self.manager.save_all_report()
        lines = []
        if report.written:
            target = self.working_folder if self.reference_folder else "in place"
            lines.append(f"{len(report.written)} map(s) saved ({target}):")
            lines += [f"  - {jsm_file.rel_path}" for jsm_file in report.written[:30]]
            if len(report.written) > 30:
                lines.append(f"  ... and {len(report.written) - 30} more")
        if report.written_texts:
            lines.append(f"{len(report.written_texts)} dialogue file(s) saved:")
            lines += [f"  - {path}" for path in report.written_texts]
        if report.identical_to_vanilla:
            names = "\n".join(f"  - {jsm_file.rel_path}" for jsm_file in report.identical_to_vanilla)
            answer = QMessageBox.question(
                self, "CC Group", f"These maps of the folder you edit are now identical to vanilla:\n{names}\n\n"
                                  f"Delete them from the folder you edit (the game then uses vanilla)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                for jsm_file in report.identical_to_vanilla:
                    self.manager.delete_from_modified_folder(jsm_file)
                lines.append(f"{len(report.identical_to_vanilla)} map(s) identical to vanilla removed from the"
                             f" folder you edit.")
        if not lines:
            lines.append("No modification to save.")
        if report.written or report.identical_to_vanilla or report.written_texts:
            self.__rebuild_tree_keeping_selection()
        QMessageBox.information(self, "CC Group", "\n".join(lines))

    def __rebuild_tree_keeping_selection(self):
        current = self.__tree.currentItem()
        player = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        self.__rebuild_tree()
        self.table_widget.refresh()
        self.__update_labels()
        if player is not None:
            self.select_player(player)

    def can_save_folder(self):
        """Whether a folder of card players is loaded, so there is something the Save button can do."""
        return self.manager.nb_players() > 0
