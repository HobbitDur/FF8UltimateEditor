"""CARDGAME variants: which call of a script plays, from the real field scripts."""
import pathlib
import shutil

import pytest

from CCGroup.jsmcardgame import JsmCardGameFile

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata"
BGMON = FIELD / "bg" / "bgmon_4"
BGHOKE = FIELD / "bg" / "bghoke_1"

pytestmark = pytest.mark.ff8data("extracted_files/field/mapdata/bg/bgmon_4/bgmon_4.jsm",
                                 "extracted_files/field/mapdata/bg/bgmon_4/bgmon_4.sym",
                                 "extracted_files/field/mapdata/bg/bghoke_1/bghoke_1.jsm",
                                 "extracted_files/field/mapdata/bg/bghoke_1/bghoke_1.sym")


@pytest.fixture
def joker_file(tmp_path):
    for extension in (".jsm", ".sym"):
        shutil.copy(BGMON / f"bgmon_4{extension}", tmp_path / f"bgmon_4{extension}")
    return JsmCardGameFile(str(tmp_path / "bgmon_4.jsm"), str(tmp_path / "bgmon_4.sym"))


def test_joker_picks_one_of_three_calls_on_a_random_roll(joker_file):
    variants = [player.variant for player in joker_file.players]
    assert [variant.index for variant in variants] == [0, 1, 2]
    assert all(len(variant.siblings) == 3 for variant in variants)
    assert [variant.random_ranges_text() for variant in variants] == [
        "random 0-84", "random 85-169", "random 170-255"]
    assert sum(variant.random_chance() for variant in variants) == pytest.approx(100)
    # The "answered yes" branch every call goes through is not a variant condition
    assert all("I[0]" not in condition.text() for variant in variants for condition in variant.conditions)


def test_kadowaki_picks_on_two_story_bits():
    jsm_file = JsmCardGameFile(str(BGHOKE / "bghoke_1.jsm"), str(BGHOKE / "bghoke_1.sym"))
    texts = [[condition.text() for condition in player.variant.conditions] for player in jsm_file.players]
    assert texts == [["(var 475 & 1) == 0", "(var 475 & 2) == 0"],
                     ["(var 475 & 1) == 0", "(var 475 & 2) != 0"],
                     ["(var 475 & 1) != 0", "(var 475 & 2) == 0"],
                     ["(var 475 & 1) != 0", "(var 475 & 2) != 0"]]
    assert all(player.variant.random_chance() is None for player in jsm_file.players)


def test_edited_threshold_is_saved_and_changes_the_odds(joker_file):
    threshold = joker_file.players[0].variant.literals()[0]
    assert threshold.value == 85
    original = bytes(joker_file.data)
    threshold.value = 128
    assert joker_file.players[0].variant.random_chance() == pytest.approx(50)
    assert joker_file.is_modified()
    joker_file.save()

    patched = pathlib.Path(joker_file.jsm_path).read_bytes()
    diff = [index for index in range(len(original)) if patched[index] != original[index]]
    assert diff and all(threshold.file_offset <= index < threshold.file_offset + 3 for index in diff)
    reloaded = JsmCardGameFile(joker_file.jsm_path, joker_file.sym_path)
    assert reloaded.players[0].variant.random_ranges_text() == "random 0-127"
    assert not reloaded.is_modified()
