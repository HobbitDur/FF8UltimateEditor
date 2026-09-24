"""Triple Triad deck rules of the NPC card-player tab (CCGroup/cardlocation.py), checked
against what FF8_EN.exe does (BuildOpponentDeck, Savemap_InitTripleTriadNewGame). No game
file needed."""
import random

from CCGroup import cardlocation
from CCGroup.jsmcardgame import LevelMaskOption


def test_rare_cards_start_at_card_id_plus_123():
    assert cardlocation.starting_location(77) == 200
    assert cardlocation.starting_location(109) == 232
    assert cardlocation.starting_rare_card(213) == 90  # Joker holds Leviathan
    assert cardlocation.starting_rare_card(199) is None
    assert cardlocation.starting_rare_card(233) is None
    assert cardlocation.starting_rare_card(cardlocation.LOCATION_PLAYER) is None


def test_empty_level_mask_falls_back_to_level_1_and_bit_7_is_ignored():
    assert cardlocation.enabled_levels(0) == [0]
    assert cardlocation.enabled_levels(0x80) == []  # a non-zero byte: no fallback, no level either
    assert cardlocation.enabled_levels(0x0A) == [1, 3]
    assert cardlocation.enabled_levels(0x17F) == list(range(7))  # only the low byte is read


def test_card_47_is_never_in_the_pool():
    pool = cardlocation.normal_card_pool(0x7F)
    assert cardlocation.CARD_NEVER_DEALT not in pool
    assert len(pool) == 7 * 11 - 1


def test_later_rare_cards_use_half_the_original_chance():
    assert cardlocation.rare_pick_chances(3, 100) == [100, 50, 50]
    assert cardlocation.rare_pick_chances(7, 60) == [60, 30, 30, 30, 30]


def test_rolled_hand_follows_the_rules():
    rng = random.Random(1)
    for _ in range(200):
        hand = cardlocation.roll_opponent_hand(0x10, 100, [90], rng)
        assert hand[0] == 90  # 100 %: the rare card is always first
        assert len(hand) == 5 and len(set(hand)) == 5
        assert all(44 <= card_id <= 54 and card_id != 47 for card_id in hand[1:])
    assert all(90 not in cardlocation.roll_opponent_hand(0x01, 0, [90], rng) for _ in range(50))


def test_levels_text():
    assert cardlocation.levels_text(7) == "Lv1-3"
    assert cardlocation.levels_text(22) == "Lv2, Lv3, Lv5"
    assert cardlocation.levels_text(0) == "Lv1"


def test_level_mask_option_roll_keeps_the_always_bits():
    option = LevelMaskOption(22, 31)  # Joker before story 750: (random & 31) | 22
    assert option.is_random() and option.union_mask() == 31
    rng = random.Random(2)
    assert all(option.roll(rng) & 22 == 22 and option.roll(rng) & ~31 == 0 for _ in range(100))
    assert not LevelMaskOption(7).is_random()
