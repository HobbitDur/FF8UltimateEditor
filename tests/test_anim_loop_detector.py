"""
Tests for the animation loop detector.

Whether an animation loops is not written in the animation data: it depends on how the
animation sequence section (section 5) plays it. These tests cover the three patterns
the engine uses, on hand-written sequences and on real c0m .dat files.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.monsterdata import EntityType
from FF8GameData.dat.animloopdetector import (get_animation_kind_dict, is_looping,
                                              find_character_weapon_file_list,
                                              get_animation_kind_dict_from_weapon_file,
                                              ANIM_LOOP, ANIM_ONE_SHOT, ANIM_BOTH, ANIM_UNUSED)

BATTLE_PATH = pathlib.Path(__file__).parent.parent / "extracted_files" / "battle"


@pytest.fixture(scope="session")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent
    game_data = GameData(str(project_root / "FF8GameData"))
    game_data.load_all()
    return game_data


def _kind_dict(game_data, sequence_list, nb_animation):
    seq_animation_data = {'seq_animation_data': [{'id': index + 1, 'data': bytearray(data)}
                                                 for index, data in enumerate(sequence_list)]}
    return get_animation_kind_dict(game_data, seq_animation_data, nb_animation)


class TestAnimationKindDetection:

    def test_bare_op_code_is_played_once(self, game_data):
        # 00: play animation 0 and wait for it to end, A2: end of sequence
        assert _kind_dict(game_data, [[0x00, 0xA2]], 1) == {0: ANIM_ONE_SHOT}

    def test_a0_op_code_loops(self, game_data):
        # A0 00: play animation 0 without pausing, the engine re-queues it when it ends
        assert _kind_dict(game_data, [[0xA0, 0x00, 0xA2]], 1) == {0: ANIM_LOOP}

    def test_bare_op_code_in_a_backward_jump_loops(self, game_data):
        # A3 / 00 / E6 FF: the idle stance pattern, E6 FF jumps -1 byte back onto the
        # "play animation 0" op code (real sequence 1 of c0m001).
        assert _kind_dict(game_data, [[0xA3, 0x00, 0xE6, 0xFF]], 1) == {0: ANIM_LOOP}

    def test_animation_after_a_backward_jump_is_played_once(self, game_data):
        # Only what the jump goes back over is repeated: animation 1 sits after it.
        # A3 / 00 / E6 FF / 01 / A2
        kind_dict = _kind_dict(game_data, [[0xA3, 0x00, 0xE6, 0xFF, 0x01, 0xA2]], 2)
        assert kind_dict == {0: ANIM_LOOP, 1: ANIM_ONE_SHOT}

    def test_animation_looped_and_played_once_is_both(self, game_data):
        kind_dict = _kind_dict(game_data, [[0xA3, 0x00, 0xE6, 0xFF], [0x00, 0xA2]], 1)
        assert kind_dict == {0: ANIM_BOTH}

    def test_animation_never_referenced_is_unused(self, game_data):
        assert _kind_dict(game_data, [[0x00, 0xA2]], 2) == {0: ANIM_ONE_SHOT, 1: ANIM_UNUSED}

    def test_jump_target_is_not_read_as_an_op_code(self, game_data):
        # A0 05: the 05 is the parameter of A0, not a "play animation 5" op code, so
        # animation 5 loops and is never reported as played once.
        kind_dict = _kind_dict(game_data, [[0xA0, 0x05, 0xA2]], 6)
        assert kind_dict[5] == ANIM_LOOP

    def test_no_sequence_section_returns_empty(self, game_data):
        assert get_animation_kind_dict(game_data, {'seq_animation_data': []}, 5) == {}
        assert get_animation_kind_dict(game_data, None, 5) == {}

    def test_section_playing_animations_that_do_not_exist_is_rejected(self, game_data):
        """Not a sequence section (e.g. d7c016 read with the wrong section layout).

        Answering from it would smooth the wrong animations, so nothing is returned and
        the caller falls back on asking.
        """
        sequence = [[0x05, 0xA2]]  # plays animation 5
        assert _kind_dict(game_data, sequence, 2) == {}  # only 2 animations exist
        assert _kind_dict(game_data, sequence, 6)[5] == ANIM_ONE_SHOT  # 6 exist: fine


class TestIsLooping:

    def test_loop_and_both_are_smoothed(self):
        assert is_looping(ANIM_LOOP)
        assert is_looping(ANIM_BOTH)

    def test_one_shot_and_unused_are_not_smoothed(self):
        assert not is_looping(ANIM_ONE_SHOT)
        assert not is_looping(ANIM_UNUSED)


@pytest.mark.skipif(not (BATTLE_PATH / "c0m001.dat").exists(),
                    reason="extracted battle files not available")
class TestRealFile:

    @pytest.fixture(scope="class")
    def gim52a_kind_dict(self, game_data):
        monster = MonsterAnalyser(game_data)
        monster.load_file_data(str(BATTLE_PATH / "c0m001.dat"), game_data)
        monster.analyse_loaded_data(game_data)
        return get_animation_kind_dict(game_data, monster.seq_animation_data,
                                       monster.animation_data.nb_animations)

    def test_every_animation_is_classified(self, gim52a_kind_dict):
        assert len(gim52a_kind_dict) == 20

    def test_idle_animation_loops(self, gim52a_kind_dict):
        # Animation 0 is the idle stance: looped by the base sequence (A3 / 00 / E6 FF)
        # and also played once by sequence 14.
        assert gim52a_kind_dict[0] == ANIM_BOTH
        assert is_looping(gim52a_kind_dict[0])

    def test_short_loops_are_detected(self, gim52a_kind_dict):
        assert gim52a_kind_dict[16] == ANIM_LOOP
        assert gim52a_kind_dict[18] == ANIM_LOOP

    def test_attack_animations_are_played_once(self, gim52a_kind_dict):
        for anim_id in (1, 2, 3, 4, 5):
            assert gim52a_kind_dict[anim_id] == ANIM_ONE_SHOT
            assert not is_looping(gim52a_kind_dict[anim_id])

    def test_no_animation_id_out_of_range(self, game_data):
        """A desynced byte-code walker would reference animations that do not exist."""
        for file_name in ("c0m000.dat", "c0m001.dat", "c0m020.dat", "c0m050.dat"):
            monster = MonsterAnalyser(game_data)
            monster.load_file_data(str(BATTLE_PATH / file_name), game_data)
            monster.analyse_loaded_data(game_data)
            kind_dict = get_animation_kind_dict(game_data, monster.seq_animation_data,
                                               monster.animation_data.nb_animations)
            assert set(kind_dict) == set(range(monster.animation_data.nb_animations))


@pytest.mark.skipif(not (BATTLE_PATH / "d0c000.dat").exists(),
                    reason="extracted battle files not available")
class TestCharacterWeapon:
    """A character body has no sequences: they live in its weapon file."""

    SQUALL_NB_ANIMATION = 42  # d0c000 / d0c001

    def test_weapon_files_are_found_next_to_the_body(self):
        weapon_list = find_character_weapon_file_list(BATTLE_PATH / "d0c000.dat")
        assert [w.name for w in weapon_list] == [f"d0w00{i}.dat" for i in range(8)]

    def test_only_the_weapons_of_that_character_are_returned(self):
        weapon_list = find_character_weapon_file_list(BATTLE_PATH / "d2c006.dat")
        assert [w.name for w in weapon_list] == ["d2w013.dat", "d2w014.dat",
                                                 "d2w015.dat", "d2w016.dat"]

    def test_a_file_that_is_not_a_character_has_no_weapon(self):
        assert find_character_weapon_file_list(BATTLE_PATH / "c0m001.dat") == []
        assert find_character_weapon_file_list(BATTLE_PATH / "d0w000.dat") == []

    def test_character_animations_are_classified_from_its_weapon(self, game_data):
        kind_dict = get_animation_kind_dict_from_weapon_file(
            game_data, BATTLE_PATH / "d0w000.dat", self.SQUALL_NB_ANIMATION)
        assert len(kind_dict) == self.SQUALL_NB_ANIMATION
        assert is_looping(kind_dict[0])  # idle stance
        # A weapon plays exactly the animations of its body, no unused one
        assert ANIM_UNUSED not in kind_dict.values()

    def test_every_weapon_of_a_character_gives_the_same_answer(self, game_data):
        """Vanilla weapons of one character share a byte-identical sequence section."""
        reference = get_animation_kind_dict_from_weapon_file(
            game_data, BATTLE_PATH / "d0w000.dat", self.SQUALL_NB_ANIMATION)
        for weapon_id in range(1, 7):  # d0w007 is a garbage file
            kind_dict = get_animation_kind_dict_from_weapon_file(
                game_data, BATTLE_PATH / f"d0w00{weapon_id}.dat", self.SQUALL_NB_ANIMATION)
            assert kind_dict == reference

    def test_unarmed_character_weapon_is_readable(self, game_data):
        """Zell's weapon has no model at all (6 sections) but still carries the program."""
        kind_dict = get_animation_kind_dict_from_weapon_file(
            game_data, BATTLE_PATH / "d1w008.dat", 38)
        assert len(kind_dict) == 38
        assert is_looping(kind_dict[0])


@pytest.mark.skipif(not (BATTLE_PATH / "d7c016.dat").exists(),
                    reason="extracted battle files not available")
class TestEdea:
    """Edea (d7c016) has no weapon file: her body carries the sequences itself.

    Her 11-section layout is a character one plus the sections a weapon usually holds
    (animation sequences, sounds, sound bank), so her sequences are in section 6 while
    section 5 is the camera sequence.
    """

    @pytest.fixture(scope="class")
    def edea(self, game_data):
        monster = MonsterAnalyser(game_data)
        monster.load_file_data(str(BATTLE_PATH / "d7c016.dat"), game_data)
        monster.analyse_loaded_data(game_data)
        return monster

    def test_entity_type_is_detected(self, edea):
        assert edea.entity_type == EntityType.CHARACTER_NO_WEAPON

    def test_sequences_are_read_from_section_6(self, edea):
        assert len(edea.seq_animation_data['seq_animation_data']) == 30

    def test_animations_are_classified(self, game_data, edea):
        kind_dict = get_animation_kind_dict(game_data, edea.seq_animation_data,
                                            edea.animation_data.nb_animations)
        assert len(kind_dict) == 30
        assert is_looping(kind_dict[0])  # idle stance
        assert ANIM_UNUSED not in kind_dict.values()  # a character uses all its animations

    def test_she_has_no_weapon_file(self):
        assert find_character_weapon_file_list(BATTLE_PATH / "d7c016.dat") == []

    def test_save_keeps_every_section_but_the_animation_padding(self, game_data, edea, tmp_path):
        """Only the alignment bits at the end of each animation bit-stream may change.

        See tests/Ifrit/test_realfile_monster.py: the game never reads them.
        """
        saved_path = tmp_path / "d7c016.dat"
        edea.write_data_to_file(game_data, str(saved_path))
        original = (BATTLE_PATH / "d7c016.dat").read_bytes()
        saved = saved_path.read_bytes()
        assert len(saved) == len(original)

        position = edea.header_data['section_pos']
        nb_section = edea.header_data['nb_section']
        for section in range(nb_section):
            if section == 3:  # animation section: padding may differ
                continue
            end = position[section + 1] if section + 1 < nb_section else len(original)
            assert original[position[section]:end] == saved[position[section]:end], \
                f"section {section} changed on save"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
