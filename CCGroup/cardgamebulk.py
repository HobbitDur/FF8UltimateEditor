"""
Bulk edits of NPC card players (the NPC tab's table view), and the text of each table column.

An operation changes one CARDGAME parameter of many players at once. Every operation returns
whether it changed the player; players it cannot apply to are skipped, never forced:
- a value the script computes at runtime (not a literal nor a savemap variable) is never touched;
- a parameter that follows the game state (region rules, a level mask the script rolls) is only
  replaced by a fixed value by the "set" operations, and only when ``override_game_state`` is on.
"""
from CCGroup import cardlocation
from CCGroup.jsmcardgame import (CardGamePlayer, GAME_RULE_BITS, TRADE_RULE_NAMES, AI_STRATEGY_NAMES,
                                 AI_SEARCH_NO_GUESS_BIT, VAR_CURRENT_REGION_GAME_RULES,
                                 VAR_CURRENT_REGION_TRADE_RULE, OPCODE_PSHM_B,
                                 PARAM_DECK_ID, PARAM_GAME_RULES, PARAM_TRADE_RULES, PARAM_RARE_CHANCE,
                                 PARAM_AI_SEARCH, PARAM_AI_STRATEGY, PARAM_LEVEL_MASK)

LEVEL_MASK_ALL = (1 << cardlocation.NB_LEVELS) - 1
AI_DEPTH_MASK = 0x07
MAX_AI_DEPTH = 7
MAX_RARE_CHANCE = 100


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _set_literal(param, value, override_game_state: bool):
    """Write a fixed value. Returns True when the param changed."""
    if not param.is_editable() or (param.is_variable() and not override_game_state):
        return False
    before = (param.opcode, param.value)
    param.set_literal(value)
    return (param.opcode, param.value) != before


def _modify_literal(param, function):
    """Apply function(old value) -> new value to a literal param (variables are skipped)."""
    if not param.is_literal():
        return False
    new_value = function(param.value)
    if new_value == param.value:
        return False
    param.set_literal(new_value)
    return True


def _set_variable(param, variable: int):
    if not param.is_editable():
        return False
    before = (param.opcode, param.value)
    # Keep the script's own push opcode when it already read that variable
    opcode = param.original_opcode if param.original_value == variable and param.original_opcode != 0x07 \
        else OPCODE_PSHM_B
    param.set_variable(variable, opcode)
    return (param.opcode, param.value) != before


# ---------------------------------------------------------------- operations (player, value) -> bool

def set_deck_id(player: CardGamePlayer, deck_id: int, override_game_state=False):
    return _set_literal(player.params[PARAM_DECK_ID], clamp(deck_id, 0, 255), override_game_state)


def set_rare_chance(player, chance: int, override_game_state=False):
    return _set_literal(player.params[PARAM_RARE_CHANCE], clamp(chance, 0, MAX_RARE_CHANCE), override_game_state)


def add_rare_chance(player, delta: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_RARE_CHANCE], lambda value: clamp(value + delta, 0, MAX_RARE_CHANCE))


def multiply_rare_chance(player, percent: int, override_game_state=False):
    """percent = 200 doubles the chance, 50 halves it."""
    return _modify_literal(player.params[PARAM_RARE_CHANCE],
                           lambda value: clamp(round(value * percent / 100), 0, MAX_RARE_CHANCE))


def set_ai_depth(player, depth: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_AI_SEARCH],
                           lambda value: (value & ~AI_DEPTH_MASK) | clamp(depth, 0, MAX_AI_DEPTH))


def add_ai_depth(player, delta: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_AI_SEARCH],
                           lambda value: (value & ~AI_DEPTH_MASK)
                           | clamp((value & AI_DEPTH_MASK) + delta, 0, MAX_AI_DEPTH))


def set_ai_no_guess(player, no_guess: bool, override_game_state=False):
    return _modify_literal(player.params[PARAM_AI_SEARCH],
                           lambda value: value | AI_SEARCH_NO_GUESS_BIT if no_guess
                           else value & ~AI_SEARCH_NO_GUESS_BIT)


def set_ai_strategy(player, strategy: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_AI_STRATEGY],
                           lambda value: (value & ~0x07) | clamp(strategy, 0, len(AI_STRATEGY_NAMES) - 1))


def set_levels(player, mask: int, override_game_state=False):
    return _set_literal(player.params[PARAM_LEVEL_MASK], mask & LEVEL_MASK_ALL, override_game_state)


def add_levels(player, mask: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_LEVEL_MASK], lambda value: value | (mask & LEVEL_MASK_ALL))


def remove_levels(player, mask: int, override_game_state=False):
    """Never empties the mask (the game would silently fall back to level 1): a player that
    would lose every level is left unchanged."""
    def remove(value):
        remaining = value & ~(mask & LEVEL_MASK_ALL)
        if remaining & LEVEL_MASK_ALL:
            return remaining
        return value  # nothing would be left: leave this player unchanged
    return _modify_literal(player.params[PARAM_LEVEL_MASK], remove)


def shift_levels(player, steps: int, override_game_state=False):
    """Move every allowed level up (steps > 0, stronger deck) or down, stopping at Lv1 / Lv7."""
    def shift(value):
        levels = [level for level in range(cardlocation.NB_LEVELS) if value & (1 << level)]
        if not levels:
            return value
        shifted = {clamp(level + steps, 0, cardlocation.NB_LEVELS - 1) for level in levels}
        return (value & ~LEVEL_MASK_ALL) | sum(1 << level for level in shifted)
    return _modify_literal(player.params[PARAM_LEVEL_MASK], shift)


def set_game_rules(player, rules: int, override_game_state=False):
    return _set_literal(player.params[PARAM_GAME_RULES], rules & 0xFF, override_game_state)


def add_game_rules(player, rules: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_GAME_RULES], lambda value: value | (rules & 0xFF))


def remove_game_rules(player, rules: int, override_game_state=False):
    return _modify_literal(player.params[PARAM_GAME_RULES], lambda value: value & ~(rules & 0xFF))


def use_region_rules(player, _value=None, override_game_state=False):
    return _set_variable(player.params[PARAM_GAME_RULES], VAR_CURRENT_REGION_GAME_RULES)


def set_trade_rule(player, trade_rule: int, override_game_state=False):
    return _set_literal(player.params[PARAM_TRADE_RULES], clamp(trade_rule, 0, len(TRADE_RULE_NAMES) - 1),
                        override_game_state)


def use_region_trade_rule(player, _value=None, override_game_state=False):
    return _set_variable(player.params[PARAM_TRADE_RULES], VAR_CURRENT_REGION_TRADE_RULE)


def restore_original(player, _value=None, override_game_state=False):
    changed = player.is_modified()
    for param in player.params:
        param.restore_original()
    return changed


def apply_to_players(players, operation, value=None, override_game_state=False):
    """Run an operation on every player. Returns (number changed, number left unchanged)."""
    changed = sum(1 for player in players if operation(player, value, override_game_state))
    return changed, len(players) - changed


# ---------------------------------------------------------------- column texts

def rules_text(rules: int):
    names = [name for bit, name in GAME_RULE_BITS if rules & bit]
    return ", ".join(names) if names else "no rule"


def param_text(param, fixed_text):
    """Text of a parameter: its fixed value through fixed_text, or where the game state reads it."""
    if param.is_literal():
        return fixed_text(param.value)
    if param.is_variable():
        return f"var {param.value}"
    return "runtime"


def deck_text(player, card_names):
    return param_text(player.params[PARAM_DECK_ID], lambda value: str(value))


def rare_card_text(player, card_names):
    deck = player.params[PARAM_DECK_ID]
    if not deck.is_literal():
        return ""
    card_id = cardlocation.starting_rare_card(deck.value)
    if card_id is not None:
        return card_names[card_id]
    if deck.value == cardlocation.LOCATION_QUEEN:
        return "(Queen of Cards)"
    if deck.value == cardlocation.LOCATION_PLAYER:
        return "(player's cards)"
    return ""


def game_rules_text(player):
    param = player.params[PARAM_GAME_RULES]
    if param.is_variable() and param.value == VAR_CURRENT_REGION_GAME_RULES:
        return "region"
    return param_text(param, rules_text)


def trade_rule_text(player):
    param = player.params[PARAM_TRADE_RULES]
    if param.is_variable() and param.value == VAR_CURRENT_REGION_TRADE_RULE:
        return "region"
    return param_text(param, lambda value: TRADE_RULE_NAMES[value & 0x07]
                      if value & 0x07 < len(TRADE_RULE_NAMES) else str(value))


def levels_text(player):
    param = player.params[PARAM_LEVEL_MASK]
    if param.is_variable():
        return f"script (var {param.value})"
    return param_text(param, cardlocation.levels_text)
