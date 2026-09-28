"""0x0a context values are named only in the screen that fills them.

The same slot means different things per screen: 0x0a26 is the SeeD rank in the SeeD test
(Menu_SeedTest_ParseCursorStops 0x4D4A80), a spell in the battle rewards
(BattleText_FormatRewardMessage 0x4A3260) and the Magic menu (Menu_Magic_FormatMessage 0x4EFF40),
and the new weapon in the Junk Shop, so a name given everywhere mislabels most of them.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_sysfnt_data()
    return game_data


@pytest.mark.parametrize("section_name, context", [
    ("Test seed general", "seed_test"),
    ("Test seed 12", "seed_test"),
    ("Misc text section", "battle_reward"),
    ("tkmnmes3.bin - subsection n°9", "item_menu_message"),
    ("tkmnmes2.bin - subsection n°8", "magic_menu"),
    ("tkmnmes3.bin - subsection n°3", "junk_shop"),
    ("tkmnmes3.bin - subsection n°11", "junction_menu"),
    ("tkmnmes2.bin - subsection n°13", "card_album"),
    ("tkmnmes3.bin - subsection n°13", "seed_test"),
    ("tkmnmes3.bin - subsection n°4", None),
    ("tkmnmes3.bin - subsection n°90", None),
    ("Book text", None),
])
def test_context_of_a_section(game_data, section_name, context):
    assert game_data.special_value_context_for_section(section_name) == context


def test_same_slot_decodes_per_screen(game_data):
    rank_slot = [0x0a, 0x26]
    assert game_data.translate_hex_to_str(rank_slot, special_value_context="seed_test") == "{SeedRank}"
    assert game_data.translate_hex_to_str(rank_slot, special_value_context="battle_reward") == "{RewardMagic}"
    assert game_data.translate_hex_to_str(rank_slot, special_value_context="junk_shop") == "{JunkShopWeapon}"
    assert game_data.translate_hex_to_str(rank_slot) == "{x0a26}"


def test_every_name_encodes_back_to_its_slot(game_data):
    for context, special_values in game_data.sysfnt_data_json["SpecialValues"].items():
        for code, name in special_values.items():
            code_bytes = [0x0a, int(code[-2:], 16)]
            assert game_data.translate_str_to_hex("{" + name + "}") == code_bytes
            assert game_data.translate_hex_to_str(code_bytes, special_value_context=context) == "{" + name + "}"


def test_names_are_unique_across_screens(game_data):
    """Encoding has no context, so a name must point to one slot only."""
    name_list = [name for special_values in game_data.sysfnt_data_json["SpecialValues"].values()
                 for name in special_values.values()]
    name_list += list(game_data.sysfnt_data_json["SpecialValueLegacyNames"])
    assert len(name_list) == len(set(name_list))


@pytest.mark.parametrize("legacy_name, code_bytes", [("CurrentSeedTestLevel", [0x0a, 0x20]),
                                                     ("CardReceived", [0x0a, 0x23])])
def test_legacy_names_still_import(game_data, legacy_name, code_bytes):
    """CSVs exported before the names moved per screen still hold these names."""
    assert game_data.translate_str_to_hex("{" + legacy_name + "}") == code_bytes
