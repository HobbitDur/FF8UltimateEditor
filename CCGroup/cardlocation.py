"""
Triple Triad card locations and deck building, as the FF8 engine does them.

A CARDGAME "Deck ID" is a location code: the NPC's pocket for rare cards. It only
decides which rare cards (IDs 77-109) the NPC can play; the NPC's normal cards come
from the allowed-level mask alone. On a new game rare card N starts at location
N + 123 (200-232), the Deck ID of the NPC that holds it at the start.

Reference: FF8ModdingWiki, Field Opcodes 13A_CARDGAME (BuildOpponentDeck @0x537640,
Savemap_InitTripleTriadNewGame @0x8DFF20 in FF8_EN.exe).
"""
import random

NB_CARDS = 110
RARE_CARD_FIRST_ID = 77
RARE_CARD_LAST_ID = 109
NB_LEVELS = 7
NB_CARDS_PER_LEVEL = 11
NB_CARDS_IN_HAND = 5
# The opponent deck builder re-rolls this card (PuPu), so no NPC ever deals it.
CARD_NEVER_DEALT = 47

RARE_START_LOCATION_OFFSET = 123
LOCATION_NO_RARE = 0
LOCATION_QUEEN = 1
LOCATION_PLAYER = 240


def is_rare_card(card_id: int):
    return RARE_CARD_FIRST_ID <= card_id <= RARE_CARD_LAST_ID


def starting_location(rare_card_id: int):
    """Location of a rare card on a new game."""
    return rare_card_id + RARE_START_LOCATION_OFFSET


def starting_rare_card(location: int):
    """The rare card that starts the game at this location, or None."""
    card_id = location - RARE_START_LOCATION_OFFSET
    return card_id if is_rare_card(card_id) else None


def effective_level_mask(level_mask: int):
    """The engine reads one byte, uses bits 0-6 and falls back to level 1 when the byte is 0."""
    level_mask &= 0xFF
    return level_mask if level_mask else 1


def enabled_levels(level_mask: int):
    """Level indexes (0 = Lv1) the normal cards are drawn from."""
    mask = effective_level_mask(level_mask)
    return [level for level in range(NB_LEVELS) if mask & (1 << level)]


def levels_text(level_mask: int):
    """Readable level list of a mask, e.g. 'Lv1-3' or 'Lv2, Lv3, Lv5'."""
    levels = [level + 1 for level in enabled_levels(level_mask)]
    if len(levels) > 2 and levels == list(range(levels[0], levels[-1] + 1)):
        return f"Lv{levels[0]}-{levels[-1]}"
    return ", ".join(f"Lv{level}" for level in levels)


def level_cards(level: int):
    first = level * NB_CARDS_PER_LEVEL
    return list(range(first, first + NB_CARDS_PER_LEVEL))


def normal_card_pool(level_mask: int):
    """Every normal card the NPC can be dealt (card 47 excluded)."""
    return [card_id for level in enabled_levels(level_mask) for card_id in level_cards(level)
            if card_id != CARD_NEVER_DEALT]


def rare_pick_chances(nb_candidates: int, rare_chance: int):
    """Chance (%) each rare candidate is tested with, assuming the previous ones were all picked:
    the first at the full chance, every later one at half the original chance (not halved again)."""
    rare_chance &= 0xFF
    return [rare_chance if index == 0 else rare_chance >> 1
            for index in range(min(nb_candidates, NB_CARDS_IN_HAND))]


def roll_opponent_hand(level_mask: int, rare_chance: int, rare_candidates, rng: random.Random = None):
    """Deal a hand the way BuildOpponentDeck does. rare_candidates = the rare cards currently at
    the NPC's Deck ID. Returns the list of 5 card ids (rare cards first)."""
    rng = rng or random.Random()
    rare_chance &= 0xFF
    hand = []
    pick_chance = rare_chance
    for card_id in sorted(rare_candidates):
        if rng.randrange(100) < pick_chance:
            hand.append(card_id)
            pick_chance = rare_chance >> 1
            if len(hand) >= NB_CARDS_IN_HAND:
                break
    levels = enabled_levels(level_mask)
    while len(hand) < NB_CARDS_IN_HAND:
        card_id = levels[rng.randrange(len(levels))] * NB_CARDS_PER_LEVEL + rng.randrange(NB_CARDS_PER_LEVEL)
        if card_id == CARD_NEVER_DEALT or card_id in hand:
            continue
        hand.append(card_id)
    return hand


def location_label(location: int, card_names):
    """Short description of a location code for the UI."""
    if location == LOCATION_NO_RARE:
        return "no rare cards"
    if location == LOCATION_QUEEN:
        return "Queen of Cards"
    if location == LOCATION_PLAYER:
        return "the player's own cards"
    card_id = starting_rare_card(location)
    if card_id is not None:
        return f"starting owner of {card_names[card_id]}"
    return "NPC pocket (no rare card at the start)"
