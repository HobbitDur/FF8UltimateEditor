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

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QPixmap, QBrush, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
                             QLabel, QComboBox, QCheckBox, QPushButton, QFileDialog,
                             QSpinBox, QGroupBox, QMessageBox, QSplitter, QLineEdit,
                             QTreeWidget, QTreeWidgetItem, QTabWidget)

from CCGroup import cardlocation
from CCGroup.npccardtablewidget import NpcCardTableWidget
from CCGroup.npcfieldview import NpcFieldView
from CCGroup.jsmcardgame import (CardGameFolderManager, OPCODE_PSHN_L, CardGamePlayer, CardGameParam,
                                 GAME_RULE_BITS, TRADE_RULE_NAMES, AI_STRATEGY_NAMES,
                                 AI_SEARCH_DEPTH_NAMES, AI_SEARCH_NO_GUESS_BIT,
                                 VAR_CURRENT_REGION_GAME_RULES, VAR_CURRENT_REGION_TRADE_RULE,
                                 PARAM_DECK_ID, PARAM_GAME_RULES, PARAM_TRADE_RULES,
                                 PARAM_RARE_CHANCE, PARAM_AI_SEARCH, PARAM_AI_STRATEGY,
                                 PARAM_LEVEL_MASK)

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
        # Item 0 describes a value that is not in the list (and invites to pick one)
        value = self.spinbox.value()
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
MODIFIED_FOLDER_COLOR = QColor(40, 110, 210)  # maps read from the modified folder


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


class CardPlayerWidget(QWidget):
    """Editor of the 7 CARDGAME parameters of one NPC, with the rare cards and deck preview."""

    def __init__(self, player: CardGamePlayer, card_images: CardImages, manager: CardGameFolderManager,
                 changed_callback=None, select_player_callback=None):
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

        select_player_callback = select_player_callback or (lambda _: None)
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

    Left: a filterable map/NPC tree of every card player found in the loaded folder.
    Right: the parameter editor of the selected player (built on demand - a full game
    dump contains hundreds of players, so only one editor exists at a time)."""

    NO_FOLDER_TEXT = ("Use the header's Open-folder button on your vanilla 'field' folder (.jsm/.sym "
                      "scripts, e.g. extracted with Deling) to list the NPC card players.")
    NO_MODIFIED_FOLDER_TEXT = "none - saves are written in place, into the vanilla folder"
    TOOLTIP_MODIFIED_FOLDER = (
        "<b>Modified field folder</b> (e.g. a mod's ...\\FieldRework\\field)<br/>"
        "Holds only the maps the mod changes, at the same paths as the vanilla folder. A map is read<br/>"
        "from it when it has it (the mod's own changes are kept), else from vanilla.<br/><br/>"
        "<b>Save</b> writes only into this folder, and only the maps whose script differs from vanilla<br/>"
        "(a map edited back to vanilla is not written, and you are offered to delete it from the folder).<br/>"
        "The vanilla folder is never written to.")

    def __init__(self, icon_path='Resources', settings: QSettings = None, game_data=None):
        QWidget.__init__(self)
        if game_data is None:  # Used alone: load the card names and images itself
            from FF8GameData.gamedata import GameData
            game_data = GameData()
        if getattr(game_data, "card_data_json", None) is None:
            game_data.load_card_data()
        self.card_images = CardImages(game_data)
        self.__player_items = {}  # id(player) -> its tree item
        self.manager = CardGameFolderManager()
        self.folder_loaded = ""
        self.settings = settings

        self.__main_layout = QVBoxLayout()
        self.setLayout(self.__main_layout)

        # Opening the folder and saving the patched .jsm files both run from the shared header
        # toolbar (Open-folder -> load_folder, Save -> save_folder); this tab keeps only its list.
        self.__info_label = QLabel(self.NO_FOLDER_TEXT)

        self.__layout_top = QHBoxLayout()
        self.__layout_top.addWidget(self.__info_label)
        self.__layout_top.addStretch(1)
        self.__main_layout.addLayout(self.__layout_top)

        # Second layer: a modified field folder on top of vanilla (opened after it, saved into)
        self.modified_folder = ""
        self.__modified_label = QLabel(self.NO_MODIFIED_FOLDER_TEXT)
        self.__modified_label.setToolTip(self.TOOLTIP_MODIFIED_FOLDER)
        self.__modified_button = QPushButton("Open modified folder...")
        self.__modified_button.setToolTip(self.TOOLTIP_MODIFIED_FOLDER)
        self.__modified_button.setEnabled(False)
        self.__modified_button.clicked.connect(self.__pick_modified_folder)
        self.__remove_modified_button = QPushButton("Remove")
        self.__remove_modified_button.setToolTip("Stop using the modified folder (back to vanilla only).")
        self.__remove_modified_button.setVisible(False)
        self.__remove_modified_button.clicked.connect(self.close_modified_folder)
        modified_layout = QHBoxLayout()
        modified_title = QLabel("<b>Modified field folder:</b>")
        modified_title.setToolTip(self.TOOLTIP_MODIFIED_FOLDER)
        modified_layout.addWidget(modified_title)
        modified_layout.addWidget(self.__modified_label, 1)
        modified_layout.addWidget(self.__modified_button)
        modified_layout.addWidget(self.__remove_modified_button)
        self.__main_layout.addLayout(modified_layout)

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

        # Right pane: where the NPC stands (field background) and its 3D model
        self.field_view = NpcFieldView()

        self.__splitter = QSplitter(Qt.Orientation.Horizontal)
        self.__splitter.addWidget(left_widget)
        self.__splitter.addWidget(self.__editor_scroll)
        self.__splitter.addWidget(self.field_view)
        self.__splitter.setStretchFactor(0, 1)
        self.__splitter.setStretchFactor(1, 2)
        self.__splitter.setStretchFactor(2, 2)
        self.__splitter.setSizes([260, 700, 520])

        # Two views of the same players: one at a time (Editor) or all in a table (bulk edits)
        self.table_widget = NpcCardTableWidget(self.card_images.names)
        self.table_widget.players_changed.connect(self.__players_bulk_changed)
        self.table_widget.open_player.connect(self.__open_from_table)
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.__splitter, "Editor")
        self.view_tabs.addTab(self.table_widget, "Table (bulk edit)")
        self.view_tabs.currentChanged.connect(self.__view_changed)
        self.__main_layout.addWidget(self.view_tabs, 1)

    def load_folder(self, folder_path: str):
        """The vanilla field folder (the header's Open-folder button). A modified folder already
        opened stays on top of it."""
        if not self.__confirm_discard():
            return
        self.folder_loaded = folder_path
        if self.settings is not None:
            self.settings.setValue("ccgroup/npc_last_folder", folder_path)
        self.__reload()

    def load_modified_folder(self, folder_path: str):
        """Put a modified field folder on top of the vanilla one (see TOOLTIP_MODIFIED_FOLDER)."""
        if not self.folder_loaded:
            QMessageBox.information(self, "CC Group", "Open the vanilla field folder first (header's"
                                                      " Open-folder button), then the modified one.")
            return
        if os.path.normcase(os.path.abspath(folder_path)) == os.path.normcase(os.path.abspath(self.folder_loaded)):
            QMessageBox.warning(self, "CC Group", "The modified folder must be another folder than the vanilla one.")
            return
        if not self.__confirm_discard():
            return
        self.modified_folder = folder_path
        if self.settings is not None:
            self.settings.setValue("ccgroup/npc_modified_folder", folder_path)
        self.__reload()

    def close_modified_folder(self):
        if not self.modified_folder or not self.__confirm_discard():
            return
        self.modified_folder = ""
        self.__reload()

    def __pick_modified_folder(self):
        start = self.settings.value("ccgroup/npc_modified_folder", "") if self.settings is not None else ""
        folder = QFileDialog.getExistingDirectory(
            self, "Modified field folder (the mod's 'field' folder, holding only the changed maps)", start)
        if folder:
            self.load_modified_folder(folder)

    def __confirm_discard(self):
        """Reloading drops unsaved edits: ask first when there are some."""
        if not any(jsm_file.is_modified() for jsm_file in self.manager.jsm_files):
            return True
        answer = QMessageBox.question(self, "CC Group", "Unsaved card player changes will be lost. Continue?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def __reload(self):
        self.manager.load_folder(self.folder_loaded, self.modified_folder)
        self.field_view.set_field_folders(self.folder_loaded, self.modified_folder)
        self.__rebuild_tree()
        self.table_widget.set_manager(self.manager)
        self.__modified_button.setEnabled(bool(self.folder_loaded))
        self.__remove_modified_button.setVisible(bool(self.modified_folder))
        self.__update_labels()

    def __update_labels(self):
        nb_players = self.manager.nb_players()
        if not self.folder_loaded:
            self.__info_label.setText(self.NO_FOLDER_TEXT)
        elif nb_players == 0:
            self.__info_label.setText(f"No card player found in {self.folder_loaded}")
        else:
            self.__info_label.setText(f"{nb_players} card player(s) in {len(self.manager.jsm_files)} map(s)"
                                      f" - vanilla: {self.folder_loaded}")
        if self.modified_folder:
            self.__modified_label.setText(f"{self.modified_folder} ({self.manager.nb_from_modified_folder()}"
                                          f" card-player map(s) read from it; Save writes here only)")
        else:
            self.__modified_label.setText(self.NO_MODIFIED_FOLDER_TEXT)

    def close_folder(self):
        """Forget the loaded folders and their card players (unsaved patches included)."""
        self.folder_loaded = ""
        self.modified_folder = ""
        self.manager = CardGameFolderManager()
        self.field_view.set_field_folders("", "")
        self.__rebuild_tree()
        self.table_widget.set_manager(self.manager)
        self.__modified_button.setEnabled(False)
        self.__remove_modified_button.setVisible(False)
        self.__update_labels()

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

    def __rebuild_tree(self):
        self.__tree.clear()
        self.__player_items = {}
        self.__show_editor(None)
        for jsm_file in self.manager.jsm_files:
            source = "  [modified]" if jsm_file.modified_path else ""
            map_item = QTreeWidgetItem([f"{jsm_file.map_name}  ({len(jsm_file.players)}){source}"])
            map_item.setToolTip(0, jsm_file.jsm_path)
            if jsm_file.modified_path:
                map_item.setForeground(0, QBrush(MODIFIED_FOLDER_COLOR))
            for player in jsm_file.players:
                player_item = QTreeWidgetItem([self.player_label(player)])
                player_item.setData(0, Qt.ItemDataRole.UserRole, player)
                self.__player_items[id(player)] = player_item
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
            self.field_view.clear()
        else:
            jsm_file = self.manager.file_of(player)
            if jsm_file is not None:
                self.field_view.show_player(jsm_file, player)
            editor_widget = QWidget()
            editor_layout = QVBoxLayout()
            editor_layout.addWidget(CardPlayerWidget(player, self.card_images, self.manager,
                                                     changed_callback=self.__player_changed,
                                                     select_player_callback=self.select_player))
            editor_layout.addStretch(1)
            editor_widget.setLayout(editor_layout)
            self.__editor_scroll.setWidget(editor_widget)

    def save_folder(self):
        """Save the patched maps (the shared header Save button calls this): in place without a
        modified folder, else into the modified folder, only the maps that differ from vanilla."""
        report = self.manager.save_all_report()
        lines = []
        if report.written:
            target = self.modified_folder or "in place"
            lines.append(f"{len(report.written)} map(s) saved ({target}):")
            lines += [f"  - {jsm_file.rel_path}" for jsm_file in report.written[:30]]
            if len(report.written) > 30:
                lines.append(f"  ... and {len(report.written) - 30} more")
        if report.identical_to_vanilla:
            names = "\n".join(f"  - {jsm_file.rel_path}" for jsm_file in report.identical_to_vanilla)
            answer = QMessageBox.question(
                self, "CC Group", f"These maps of the modified folder are now identical to vanilla:\n{names}\n\n"
                                  f"Delete them from the modified folder (the game then uses vanilla)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                for jsm_file in report.identical_to_vanilla:
                    self.manager.delete_from_modified_folder(jsm_file)
                lines.append(f"{len(report.identical_to_vanilla)} map(s) identical to vanilla removed from the"
                             f" modified folder.")
        if not lines:
            lines.append("No modification to save.")
        if report.written or report.identical_to_vanilla:
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
