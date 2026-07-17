"""
Tests for converting several .dat files to 30/60 fps in one go.

The delicate part is the character files: a body (dXcYYY) and its weapons (dXwYYY) are
animated by the SAME animation ids, each reading its own file, so their animations must
keep matching frame counts. Only the weapon carries the sequences.
"""
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from Ifrit.ifritmanager import IfritManager

BATTLE_PATH = pathlib.Path(__file__).parent.parent / "extracted_files" / "battle"
pytestmark = pytest.mark.skipif(not (BATTLE_PATH / "c0m001.dat").exists(),
                                reason="extracted battle files not available")


@pytest.fixture(scope="session")
def manager():
    return IfritManager(str(pathlib.Path(__file__).parent.parent / "FF8GameData"))


@pytest.fixture(scope="session")
def game_data(manager):
    return manager.game_data


def _copy(tmp_path, *name_list):
    """Never convert the real extracted files: work on copies."""
    path_list = []
    for name in name_list:
        target = tmp_path / name
        shutil.copy(BATTLE_PATH / name, target)
        path_list.append(str(target))
    return path_list


def _frame_count_list(game_data, path):
    monster = MonsterAnalyser(game_data)
    monster.load_file_data(str(path), game_data)
    monster.analyse_loaded_data(game_data)
    return [len(anim.frames) for anim in monster.animation_data.animations]


class TestFileFamily:

    def test_a_monster_is_alone(self):
        family = IfritManager.get_file_family_list(BATTLE_PATH / "c0m001.dat")
        assert [pathlib.Path(f).name for f in family] == ["c0m001.dat"]

    def test_a_character_body_pulls_its_weapons(self):
        family = IfritManager.get_file_family_list(BATTLE_PATH / "d0c000.dat")
        name_list = [pathlib.Path(f).name for f in family]
        assert "d0c000.dat" in name_list and "d0w000.dat" in name_list
        assert all(n.startswith("d0") for n in name_list)

    def test_a_weapon_pulls_its_body(self):
        family = IfritManager.get_file_family_list(BATTLE_PATH / "d2w013.dat")
        assert "d2c006.dat" in [pathlib.Path(f).name for f in family]

    def test_character_files_are_recognised(self):
        assert IfritManager.is_character_family_file("d0c000.dat")
        assert IfritManager.is_character_family_file("d0w000.dat")
        assert not IfritManager.is_character_family_file("c0m001.dat")


class TestBatchConversion:

    def test_a_monster_is_converted(self, manager, game_data, tmp_path):
        path = _copy(tmp_path, "c0m001.dat")[0]
        before = _frame_count_list(game_data, path)
        report = manager.convert_file_list_to_fps([path], 30)[0]
        after = _frame_count_list(game_data, path)
        assert report['error'] == ""
        assert report['nb_converted'] > 0
        assert report['skipped_list'] == []
        # a one-shot animation of n frames becomes 2n-1, a looping one 2n
        assert after[1] == before[1] * 2 - 1
        assert after[0] == before[0] * 2  # animation 0 is the idle loop

    def test_an_animation_too_long_is_split(self, manager, game_data, tmp_path):
        path = _copy(tmp_path, "c0m091.dat")[0]  # Elvoret: animation 27 is 140 frames
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['split_list'], "animation 27 does not fit at 30 fps and must be split"
        anim_id, nb_frame, nb_part, new_id_list = report['split_list'][0]
        assert (anim_id, nb_frame, nb_part) == (27, 140, 2)
        after = _frame_count_list(game_data, path)
        # the parts add up to the unsplit conversion, without a repeated frame
        assert after[27] + after[new_id_list[0]] == 140 * 2 - 1

    def test_a_garbage_file_is_reported_not_crashed(self, manager, tmp_path):
        path = _copy(tmp_path, "c0m127.dat")[0]
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['error']
        assert report['nb_converted'] == 0

    def test_nothing_is_split_when_the_option_is_off(self, manager, tmp_path):
        path = _copy(tmp_path, "c0m091.dat")[0]
        report = manager.convert_file_list_to_fps([path], 30, split_when_too_long=False)[0]
        assert report['split_list'] == []
        assert any(anim_id == 27 for anim_id, _ in report['skipped_list'])

    def test_a_file_is_converted_whole_or_not_at_all(self, manager, tmp_path):
        """The frame count IS the duration: one animation still at 15 fps in a file
        converted to 60 fps would play four times too fast. Geezard's animation 15 is
        played with A0 and cannot be split, so the file must be left untouched."""
        path = _copy(tmp_path, "c0m004.dat")[0]
        before = pathlib.Path(path).read_bytes()
        report = manager.convert_file_list_to_fps([path], 60)[0]
        assert report['skipped_list'], "animation 15 cannot make it to 60 fps"
        assert report['nb_converted'] == 0
        assert pathlib.Path(path).read_bytes() == before, "the file must not be modified at all"

    def test_what_60fps_refuses_converts_at_30fps(self, manager, game_data, tmp_path):
        path = _copy(tmp_path, "c0m004.dat")[0]
        assert manager.convert_file_list_to_fps([path], 60)[0]['skipped_list']
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['skipped_list'] == []
        assert report['nb_converted'] > 0

    def test_a_file_that_fully_fits_is_converted(self, manager, tmp_path):
        path = _copy(tmp_path, "c0m034.dat")[0]  # Gerogero: everything splits fine at 60 fps
        before = pathlib.Path(path).read_bytes()
        report = manager.convert_file_list_to_fps([path], 60)[0]
        assert report['skipped_list'] == []
        assert report['split_list']
        assert pathlib.Path(path).read_bytes() != before

    def test_the_progress_callback_can_cancel(self, manager, tmp_path):
        path_list = _copy(tmp_path, "c0m001.dat", "c0m002.dat", "c0m003.dat")
        report_list = manager.convert_file_list_to_fps(path_list, 30,
                                                       progress_callback=lambda i, n: i < 1)
        assert len(report_list) == 1  # stopped before the second file


class TestCharacterFamily:
    """A body and its weapon must always end up with the same frame counts."""

    def test_body_and_weapon_stay_in_lockstep_at_30fps(self, manager, game_data, tmp_path):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        assert _frame_count_list(game_data, body) == _frame_count_list(game_data, weapon)
        manager.convert_file_list_to_fps([body, weapon], 30)
        assert _frame_count_list(game_data, body) == _frame_count_list(game_data, weapon)

    def test_body_and_weapon_stay_in_lockstep_at_60fps(self, manager, game_data, tmp_path):
        """The weapon could be split (it has the sequences) but the body could not:
        splitting only the weapon would desynchronise the pair. Squall's animation 14 is
        played by the base sequence, so both files are left untouched instead."""
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 60)
        assert _frame_count_list(game_data, body) == _frame_count_list(game_data, weapon)
        for report in report_list:
            assert report['split_list'] == [], "a character family is never split"

    def test_the_body_reads_its_loops_from_the_weapon(self, manager, tmp_path):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        report = manager.convert_file_list_to_fps([body, weapon], 30)[0]
        assert report['file'] == "d0c000.dat"
        assert report['source'] == "d0w000.dat"

    def test_the_same_animation_is_skipped_on_both_at_60fps(self, manager, tmp_path):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 60)
        skipped = [sorted(anim_id for anim_id, _ in r['skipped_list']) for r in report_list]
        assert skipped[0] == skipped[1], "body and weapon must take the same decision"

    def test_the_slow_limit_uses_the_weapon_sequences(self, manager, tmp_path):
        """The body has no sequence of its own: read from the body alone, nothing would be
        slowable and its animation 14 would wrongly get the 255 frame limit (40*4 = 160
        frames, accepted) while the weapon correctly refuses it at 128 — converting the
        body but not its weapon.
        """
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        body_report, weapon_report = manager.convert_file_list_to_fps([body, weapon], 60)
        assert 14 in [anim_id for anim_id, _ in body_report['skipped_list']], \
            "the body must take the 128 frame limit of its weapon's base sequence"
        assert 14 in [anim_id for anim_id, _ in weapon_report['skipped_list']]
        assert body_report['source'] == "d0w000.dat"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
