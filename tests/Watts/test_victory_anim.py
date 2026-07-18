"""The victory animation the non-r0win characters play via weapon sequence 18.

Guards both the extraction mechanism (read sequence 18, take its animation command) and
the vanilla ids the Watts widget falls back to when no weapon file is next to the body.
"""
import glob
import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE = PROJECT_ROOT / "extracted_files" / "battle"

# com_id -> expected body animation id played by that character's weapon sequence 18
EXPECTED = {0: 30, 1: 30, 6: 26, 8: 28, 10: 26}  # Squall, Zell, Seifer, Laguna, Ward


def _seq18_anim_id(game_data, path):
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    from FF8GameData.dat.sequencecommand import read_sequence
    analyser = MonsterAnalyser(game_data)
    analyser.load_file_data(str(path), game_data)
    analyser.analyse_loaded_data(game_data)
    sequences = {s["id"]: bytes(s["data"])
                 for s in analyser.seq_animation_data["seq_animation_data"]}
    data = sequences.get(18)
    if not data:
        return None
    for command in read_sequence(game_data, data):
        if command.is_animation():
            return command.get_animation_id()
    return None


def test_widget_fallback_matches_module_constant():
    from Watts.wattswidget import WattsWidget
    assert WattsWidget._OWN_VICTORY_ANIM == EXPECTED


@pytest.mark.ff8data("extracted_files/battle/r0win.dat")
@pytest.mark.parametrize("com_id, expected", sorted(EXPECTED.items()))
def test_weapon_sequence_18_victory_anim(com_id, expected):
    from FF8GameData.gamedata import GameData
    weapons = sorted(glob.glob(str(BATTLE / f"d{com_id:x}w*.dat")))
    if not weapons:
        pytest.skip(f"no weapon files for com_id {com_id}")
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    # The first readable weapon should report the expected victory animation; garbage
    # weapons (e.g. Squall's d0w007) raise and are skipped, like the widget does.
    found = None
    for weapon in weapons:
        try:
            found = _seq18_anim_id(game_data, weapon)
        except Exception:
            continue
        if found is not None:
            break
    assert found == expected
