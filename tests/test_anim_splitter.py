"""
Tests for splitting an animation that is too long for the file format.

The frame count of an animation is one byte, so adding interpolated frames for 30/60 fps
can push it over 255. Such an animation is cut in parts chained by the sequences, which
means rewriting the sequence byte-code: the inserted animation ids move every following
op code, so the relative jumps have to be recomputed.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.dat.animloopdetector import (get_animation_kind_dict, is_looping,
                                              get_slowable_animation_id_set)
from FF8GameData.dat.sequencecommand import read_sequence_command_list, get_jump_target
from FF8GameData.dat import animsplitter as splitter

splitter_slowable = get_slowable_animation_id_set

BATTLE_PATH = pathlib.Path(__file__).parent.parent / "extracted_files" / "battle"


@pytest.fixture(scope="session")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent
    game_data = GameData(str(project_root / "FF8GameData"))
    game_data.load_all()
    return game_data


def _seq_data(sequence_list):
    return {'seq_animation_data': [{'id': index + 1, 'data': bytearray(data)}
                                   for index, data in enumerate(sequence_list)]}


class _FakeAnimationSection:
    def __init__(self, nb_animations):
        self.nb_animations = nb_animations
        self.animations = []


class TestSlowSafeLimit:
    """Slow status makes the engine compute 2 * nb_frame - 1 in a byte, so an animation
    it can reach must stay under 128 frames (FF8_EN.exe @0x509482 "shl cl, 1 / dec cl").
    """

    def test_an_animation_slow_can_reach_is_capped(self):
        assert splitter.get_max_frame_for_animation(True) == splitter.MAX_SLOW_SAFE_ANIMATION_FRAME
        assert splitter.get_max_frame_for_animation(True) == 128

    def test_the_others_use_the_whole_format_limit(self):
        assert splitter.get_max_frame_for_animation(False) == splitter.MAX_ANIMATION_FRAME

    def test_a_format_without_the_slow_behaviour_is_not_capped(self):
        """A field model is not played by the battle engine."""
        assert splitter.get_max_frame_for_animation(True, 500, slow_doubles_frame_count=False) == 500

    def test_the_cap_never_raises_a_lower_format_limit(self):
        assert splitter.get_max_frame_for_animation(True, 100) == 100

    def test_the_doubled_count_of_a_capped_animation_fits_a_byte(self):
        assert 2 * splitter.MAX_SLOW_SAFE_ANIMATION_FRAME - 1 == 255

    def test_only_a_base_sequence_animation_can_be_slowed(self, game_data):
        """A3 marks the sequence as the base one: only what it plays can be slowed."""
        seq_animation_data = _seq_data([[0xA3, 0x00, 0xE6, 0xFF],   # base sequence: idle 0
                                        [0x04, 0xA0, 0x05, 0xA2]])  # attack: not the base one
        assert splitter_slowable(game_data, seq_animation_data) == {0}

    def test_an_animation_looped_outside_the_base_sequence_is_not_slowable(self, game_data):
        seq_animation_data = _seq_data([[0xA0, 0x09, 0xA2]])  # loops 9, but no A3
        assert splitter_slowable(game_data, seq_animation_data) == set()


class TestPartCount:

    def test_an_animation_that_fits_needs_no_part(self):
        assert splitter.get_nb_part_needed(30, 4, True) == 1
        assert splitter.get_nb_part_needed(64, 4, False) == 1

    def test_two_parts_are_enough_for_a_medium_animation(self):
        # 72 frames one-shot at 60 fps -> 285 frames, over the 255 limit
        assert splitter.get_converted_frame_count(72, 4, False) == 285
        assert splitter.get_nb_part_needed(72, 4, False) == 2

    def test_a_very_long_animation_needs_three_parts(self):
        """Elvoret's animation 27: 140 frames. Half of it is still too long at 60 fps."""
        assert splitter.get_converted_frame_count(140, 4, False) == 557
        assert splitter.get_nb_part_needed(140, 4, False) == 3

    def test_every_part_fits_once_converted(self):
        for nb_frame in (65, 70, 88, 100, 116, 128, 140):
            for smooth_loop in (False, True):
                nb_converted = splitter.get_converted_frame_count(nb_frame, 4, smooth_loop)
                for nb_part_frame in splitter.get_part_frame_count_list(nb_converted):
                    assert nb_part_frame <= splitter.MAX_ANIMATION_FRAME


class TestPartBoundary:
    """The animation is interpolated first and cut after, so the parts are contiguous
    slices of the converted stream: nothing is repeated, nothing is inserted."""

    def test_the_parts_add_up_to_the_converted_animation(self):
        for nb_converted in (256, 279, 280, 557, 1000):
            assert sum(splitter.get_part_frame_count_list(nb_converted)) == nb_converted

    def test_an_animation_that_fits_is_one_part(self):
        assert splitter.get_part_frame_count_list(255) == [255]

    def test_elvoret_at_30fps_is_cut_in_two_without_a_repeated_frame(self):
        """140 frames one-shot -> 279 converted -> 140 + 139, and 140 + 139 == 279."""
        assert splitter.get_converted_frame_count(140, 2, False) == 279
        assert splitter.get_part_frame_count_list(279) == [140, 139]

    def test_the_parts_are_balanced(self):
        assert splitter.get_part_frame_count_list(557) == [186, 186, 185]
        assert splitter.get_part_frame_count_list(280, 128) == [94, 93, 93]


class TestSequenceRewrite:

    def test_bare_op_code_plays_the_parts_in_a_row(self, game_data):
        seq_animation_data = _seq_data([[0x05, 0xA2]])  # play animation 5, end
        nb = splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 5, [7])
        assert nb == 1
        assert bytes(seq_animation_data['seq_animation_data'][0]['data']) == bytes([0x05, 0x07, 0xA2])

    def test_backward_jump_is_fixed_so_the_loop_still_works(self, game_data):
        """A3 / 00 / E6 FF is the idle pattern: E6 FF jumps -1 back onto the animation."""
        seq_animation_data = _seq_data([[0xA3, 0x00, 0xE6, 0xFF]])
        splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 0, [12])
        data = bytes(seq_animation_data['seq_animation_data'][0]['data'])
        assert data == bytes([0xA3, 0x00, 0x0C, 0xE6, 0xFE])
        # the jump must still land on the op code playing the first part
        command_list = read_sequence_command_list(game_data, data)
        jump = [(a, o, p) for a, o, p in command_list if o == 0xE6][0]
        assert get_jump_target(*jump) == 1
        assert data[1] == 0x00 and data[2] == 0x0C  # part 1 then part 2, looped

    def test_three_parts_are_all_inserted(self, game_data):
        seq_animation_data = _seq_data([[0x01, 0xA2]])
        splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 1, [9, 10])
        assert bytes(seq_animation_data['seq_animation_data'][0]['data']) == bytes([0x01, 0x09, 0x0A, 0xA2])

    def test_a_forward_jump_over_the_insert_is_fixed(self, game_data):
        # E9 04: if current_value == 0 jump +4 from the op code -> lands on A2 at offset 4
        seq_animation_data = _seq_data([[0xE9, 0x04, 0x03, 0xA1, 0xA2]])
        splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 3, [8])
        data = bytes(seq_animation_data['seq_animation_data'][0]['data'])
        assert data == bytes([0xE9, 0x05, 0x03, 0x08, 0xA1, 0xA2])
        command_list = read_sequence_command_list(game_data, data)
        jump = [(a, o, p) for a, o, p in command_list if o == 0xE9][0]
        assert get_jump_target(*jump) == 5  # still the A2, now one byte further
        assert data[5] == 0xA2

    def test_a_sequence_not_playing_the_animation_is_untouched(self, game_data):
        seq_animation_data = _seq_data([[0x05, 0xA2], [0x06, 0xA2]])
        splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 5, [7])
        assert bytes(seq_animation_data['seq_animation_data'][1]['data']) == bytes([0x06, 0xA2])

    def test_the_parameter_of_a0_is_not_taken_for_an_animation_op_code(self, game_data):
        """A0 05: the 05 is a parameter, rewriting it would corrupt the sequence."""
        seq_animation_data = _seq_data([[0xA0, 0x05, 0xA2]])
        nb = splitter.rewrite_sequence_list_for_split(game_data, seq_animation_data, 5, [7])
        assert nb == 0
        assert bytes(seq_animation_data['seq_animation_data'][0]['data']) == bytes([0xA0, 0x05, 0xA2])


class TestCanSplit:

    def test_an_animation_played_by_a0_is_refused(self, game_data):
        section = _FakeAnimationSection(10)
        can, reason = splitter.can_split_animation(game_data, _seq_data([[0xA0, 0x05, 0xA2]]),
                                                   section, 5, 2)
        assert not can
        assert "A0" in reason

    def test_a_bare_op_code_is_accepted(self, game_data):
        section = _FakeAnimationSection(10)
        can, reason = splitter.can_split_animation(game_data, _seq_data([[0x05, 0xA2]]),
                                                   section, 5, 2)
        assert can, reason

    def test_too_many_animations_is_refused(self, game_data):
        """A bare op code IS the animation id, so ids stop at 0x7F."""
        section = _FakeAnimationSection(0x80)
        can, reason = splitter.can_split_animation(game_data, _seq_data([[0x05, 0xA2]]),
                                                   section, 5, 2)
        assert not can
        assert "127" in reason

    def test_a_jump_leaving_the_sequence_is_refused(self, game_data):
        """Some vanilla sequences fall through into the next one (c0m005, c0m060)."""
        section = _FakeAnimationSection(10)
        seq_animation_data = _seq_data([[0x05, 0xE6, 0x05]])  # jumps past its own end
        can, reason = splitter.can_split_animation(game_data, seq_animation_data, section, 5, 2)
        assert not can
        assert "outside" in reason

    def test_no_sequence_section_is_refused(self, game_data):
        section = _FakeAnimationSection(10)
        can, reason = splitter.can_split_animation(game_data, {'seq_animation_data': []},
                                                   section, 5, 2)
        assert not can


@pytest.mark.skipif(not (BATTLE_PATH / "c0m029.dat").exists(),
                    reason="extracted battle files not available")
class TestRealFile:

    def _load(self, game_data, name):
        monster = MonsterAnalyser(game_data)
        monster.load_file_data(str(BATTLE_PATH / name), game_data)
        monster.analyse_loaded_data(game_data)
        return monster

    @staticmethod
    def _pose_list(animation):
        """One comparable pose per frame: root position + every bone rotation."""
        pose_list = []
        for frame in animation.frames:
            pose_list.append((tuple(p.get_pos_raw() for p in frame.position),
                              tuple((int(r[0].get_rotate_raw()) % 4096,
                                     int(r[1].get_rotate_raw()) % 4096,
                                     int(r[2].get_rotate_raw()) % 4096)
                                    for r in frame.rotation_vector_data)))
        return pose_list

    def test_the_parts_are_exactly_the_unsplit_animation(self, game_data, tmp_path):
        """Chaining the parts must play the converted animation frame for frame.

        No frame repeated at the cut, no interpolated frame missing: the parts are slices
        of the very stream an unsplit conversion would produce.
        """
        anim_id, factor = 17, 4  # Jelleye: 72 frames one-shot, 285 frames at 60 fps
        ideal = self._load(game_data, "c0m029.dat")
        ideal.animation_data.animations[anim_id].create_interpolated_frames(
            ideal.bone_data.bones, factor, False)
        reference = self._pose_list(ideal.animation_data.animations[anim_id])

        monster = self._load(game_data, "c0m029.dat")
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, anim_id, factor, False)
        saved = tmp_path / "c0m029.dat"
        monster.write_data_to_file(game_data, str(saved))

        reloaded = MonsterAnalyser(game_data)
        reloaded.load_file_data(str(saved), game_data)
        reloaded.analyse_loaded_data(game_data)

        chained = []
        for part_id in [anim_id] + result['new_id_list']:
            chained.extend(self._pose_list(reloaded.animation_data.animations[part_id]))
        assert len(chained) == len(reference)
        assert chained == reference

    def test_a_split_loop_is_exactly_the_unsplit_loop(self, game_data):
        """Including the wrap frames back to the first part."""
        anim_id, factor = 0, 4  # Gerogero idle: 70 frames, slow-limited to 128 per part
        ideal = self._load(game_data, "c0m034.dat")
        ideal.animation_data.animations[anim_id].create_interpolated_frames(
            ideal.bone_data.bones, factor, True)
        reference = self._pose_list(ideal.animation_data.animations[anim_id])

        monster = self._load(game_data, "c0m034.dat")
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, anim_id, factor, True,
            splitter.get_max_frame_for_animation(True))
        chained = []
        for part_id in [anim_id] + result['new_id_list']:
            chained.extend(self._pose_list(monster.animation_data.animations[part_id]))
        assert chained == reference

    def test_every_part_fits_the_format(self, game_data, tmp_path):
        anim_id = 27  # Elvoret: 140 frames -> 3 parts
        monster = self._load(game_data, "c0m091.dat")
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, anim_id, 4, False)
        assert result['nb_part'] == 3
        for part_id in [anim_id] + result['new_id_list']:
            assert len(monster.animation_data.animations[part_id].frames) <= splitter.MAX_ANIMATION_FRAME

    def test_the_sequences_still_decode_and_chain_the_parts(self, game_data):
        anim_id = 17
        monster = self._load(game_data, "c0m029.dat")
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, anim_id, 4, False)
        part_id_list = [anim_id] + result['new_id_list']
        chain_found = 0
        for sequence in monster.seq_animation_data['seq_animation_data']:
            command_list = read_sequence_command_list(game_data, bytes(sequence['data']))
            assert all(p is not None for _, _, p in command_list), "sequence no longer decodes"
            op_code_list = [op for _, op, _ in command_list]
            for index in range(len(op_code_list) - len(part_id_list) + 1):
                if op_code_list[index:index + len(part_id_list)] == part_id_list:
                    chain_found += 1
        assert chain_found == result['nb_rewritten'] >= 1

    def test_a_looping_animation_split_keeps_looping(self, game_data):
        """Gerogero's idle (animation 0) is looped by a backward jump around it."""
        monster = self._load(game_data, "c0m034.dat")
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, 0, 4, True)
        kind_dict = get_animation_kind_dict(game_data, monster.seq_animation_data,
                                            monster.animation_data.nb_animations)
        assert is_looping(kind_dict[0])
        for new_id in result['new_id_list']:
            assert is_looping(kind_dict[new_id]), "the new part must loop with the first one"

    def test_only_the_idle_is_slowable_on_a_real_file(self, game_data):
        """GIM52A loops 5 animations but only the idle is played by the base sequence."""
        monster = self._load(game_data, "c0m001.dat")
        assert get_slowable_animation_id_set(game_data, monster.seq_animation_data) == {0}
        kind_dict = get_animation_kind_dict(game_data, monster.seq_animation_data,
                                            monster.animation_data.nb_animations)
        assert len([a for a, k in kind_dict.items() if is_looping(k)]) > 1

    def test_a_slowable_animation_is_split_under_the_slow_limit(self, game_data):
        """Gerogero's idle: 70 frames, 280 at 60 fps. Every part must stay Slow-safe."""
        monster = self._load(game_data, "c0m034.dat")
        assert 0 in get_slowable_animation_id_set(game_data, monster.seq_animation_data)
        limit = splitter.get_max_frame_for_animation(True)
        result = splitter.split_and_convert_animation(
            game_data, monster.animation_data, monster.seq_animation_data,
            monster.bone_data.bones, 0, 4, True, limit)
        for part_id in [0] + result['new_id_list']:
            nb_frame = len(monster.animation_data.animations[part_id].frames)
            assert nb_frame <= splitter.MAX_SLOW_SAFE_ANIMATION_FRAME
            assert 2 * nb_frame - 1 <= 255, "the count Slow computes must fit a byte"

    def test_an_animation_played_by_a0_is_refused_on_a_real_file(self, game_data):
        monster = self._load(game_data, "c0m004.dat")  # Geezard animation 15, looped by A0
        with pytest.raises(ValueError, match="A0"):
            splitter.split_and_convert_animation(
                game_data, monster.animation_data, monster.seq_animation_data,
                monster.bone_data.bones, 15, 4, True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
