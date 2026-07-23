"""Tests for the sequence baker (FF8GameData/dat/sequencebake.py).

The baker is what turns "these bytes mean X" into "this is what happens, and when". A
preview built on it is only worth having if the timing is right, so what is pinned here is
mostly frame counts: an animation occupies exactly its frame count, B9 waits what it says,
a yield costs one frame. The rest covers the outcomes a modder must be warned about -
an infinite loop, a hang, a jump out of the sequence - and a sweep over every vanilla
sequence to make sure no real data makes the interpreter throw.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.dat.sequencebake import (bake_sequence, sequence_dict_from_section,
                                          background_sequence_id_set, BattleContext,
                                          STOP_END, STOP_LOOP, STOP_HANG, STOP_ERROR,
                                          STOP_MAX_FRAMES, EVENT_SOUND)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"


def _entity_file_list():
    """The battle files that hold an entity model: monsters (c0m*), character bodies
    (dXc*) and weapons (dXw*). The other .dat of the folder are containers - b0wave.dat and
    the mag* effect files - which MonsterAnalyser does not terminate on, so they are named
    in rather than filtered out."""
    path_list = []
    for pattern in ("c0m*.dat", "d[0-9]c*.dat", "d[0-9]w*.dat"):
        path_list.extend(BATTLE_PATH.glob(pattern))
    return sorted(path_list)


@pytest.fixture(scope="session")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


def _bake(game_data, sequence_list, frame_count=None, **kwargs):
    """Bake sequence 1 of a hand-written file. sequence_list[0] is sequence 1."""
    sequence_by_id = {index + 1: bytes(data) for index, data in enumerate(sequence_list)}
    return bake_sequence(game_data, sequence_by_id, 1, frame_count or {}, **kwargs)


class TestTiming:
    """How many frames things take - the whole point of a preview."""

    def test_animation_occupies_exactly_its_frame_count(self, game_data):
        # 00 (play animation 0, wait for it) then A9 (hard stop). Animation 0 is 10 frames,
        # so it draws frames 0..9 on battle frames 0..9 and the interpreter resumes on
        # battle frame 10 - the completion tick, which does not draw (Battle_ReadAnimation
        # @0x508F90 returns early). That is the timing animsplitter relies on to chain the
        # parts of a split animation.
        result = _bake(game_data, [[0x00, 0xA9]], {0: 10})
        assert result.stop_reason == STOP_END
        assert result.nb_frame == 11
        assert [frame.anim_frame for frame in result.frame_list[:10]] == list(range(10))

    def test_two_animations_chain_without_a_gap(self, game_data):
        # 00 01 A9 with a 10 and a 4 frame animation: 14 frames of animation, then the
        # frame A9 runs on. No frame is lost or repeated between the two.
        result = _bake(game_data, [[0x00, 0x01, 0xA9]], {0: 10, 1: 4})
        assert result.nb_frame == 15
        assert result.frame_list[10].anim_id == 1
        assert result.frame_list[10].anim_frame == 0

    def test_yield_costs_one_frame(self, game_data):
        # A1 A1 A1 A9: three yields, then the stop on the fourth frame.
        result = _bake(game_data, [[0xA1, 0xA1, 0xA1, 0xA9]])
        assert result.nb_frame == 4

    def test_b9_waits_its_parameter_minus_one_frames(self, game_data):
        # B9 05 A9: the next op code runs 4 frames later, so A9 lands on frame 4.
        result = _bake(game_data, [[0xB9, 0x05, 0xA9]])
        assert result.nb_frame == 5
        assert result.frame_list[4].command_list[0].op_code == 0xA9

    def test_b9_always_pauses_at_least_the_current_frame(self, game_data):
        # B9 01 would be "wait 0 frames", but the op code pauses the interpreter, so the
        # next op code cannot run on the same frame.
        result = _bake(game_data, [[0xB9, 0x01, 0xA9]])
        assert result.nb_frame == 2

    def test_a0_does_not_pause_the_sequence(self, game_data):
        # A0 00 queues animation 0 and keeps going, so A9 runs on the very first frame.
        result = _bake(game_data, [[0xA0, 0x00, 0xA9]], {0: 10})
        assert result.nb_frame == 1
        assert result.frame_list[0].anim_id == 0

    def test_a0_animation_loops(self, game_data):
        # A0 00 then a yield jumped back onto forever (E6 FF at address 3 targets the A1 at
        # 2): the sequence never queues anything again, and the engine re-queues the
        # animation from frame 0 when it ends. The bake stops once the whole state repeats,
        # which here is one animation cycle plus the frame proving it wrapped.
        result = _bake(game_data, [[0xA0, 0x00, 0xA1, 0xE6, 0xFF]], {0: 3})
        assert result.stop_reason == STOP_LOOP
        assert [frame.anim_frame for frame in result.frame_list] == [0, 1, 2, 0]


class TestControlFlow:

    def test_idle_stance_is_detected_as_an_endless_loop(self, game_data):
        # A3 / 00 / E6 FF - the idle pattern (c0m001 sequence 1): E6 FF jumps one byte
        # back onto the "play animation 0" op code, forever.
        result = _bake(game_data, [[0xA3, 0x00, 0xE6, 0xFF]], {0: 6})
        assert result.stop_reason == STOP_LOOP
        assert result.is_endless()
        assert result.loop_from is not None
        assert "loops forever" in result.summary()

    def test_conditional_jump_not_taken(self, game_data):
        # C1 05 (current_value = 5), E9 04 (jump if == 0, not taken), A9.
        result = _bake(game_data, [[0xC1, 0x05, 0xE9, 0x04, 0xA9]])
        assert result.stop_reason == STOP_END
        assert result.frame_list[0].current_value == 5
        assert [command.op_code for command in result.frame_list[0].command_list] == \
               [0xC1, 0xE9, 0xA9]

    def test_conditional_jump_taken(self, game_data):
        # C1 00 (current_value = 0), E9 04 at address 2 jumps to address 6, skipping the
        # A1 at 4 (which would have cost a frame) and landing on the A9.
        result = _bake(game_data, [[0xC1, 0x00, 0xE9, 0x04, 0xA1, 0xA1, 0xA9]])
        assert result.nb_frame == 1
        assert [command.op_code for command in result.frame_list[0].command_list] == \
               [0xC1, 0xE9, 0xA9]

    def test_arithmetic_is_evaluated(self, game_data):
        # C1 0A (=10), C5 05 (+5), CD 02 (*2), D1 03 (/3) -> 10
        result = _bake(game_data, [[0xC1, 0x0A, 0xC5, 0x05, 0xCD, 0x02, 0xD1, 0x03, 0xA9]])
        assert result.frame_list[0].current_value == 10

    def test_division_truncates_toward_zero_like_c(self, game_data):
        # C1 F9 (= -7), D1 02 (/2) -> -3 in C, -4 with Python's floor division.
        result = _bake(game_data, [[0xC1, 0xF9, 0xD1, 0x02, 0xA9]])
        assert result.frame_list[0].current_value == -3

    def test_a7_jumps_to_another_sequence(self, game_data):
        # Sequence 1: A7 02 (goto sequence 2). Sequence 2: 00 A9.
        result = _bake(game_data, [[0xA7, 0x02], [0x00, 0xA9]], {0: 3})
        assert result.stop_reason == STOP_END
        assert result.frame_list[0].seq_id == 2
        assert result.nb_frame == 4

    def test_a2_continues_into_the_idle_sequence(self, game_data):
        # Sequence 1 ends with A2 and nothing is queued, so the entity falls back to its
        # base sequence - sequence 1 itself here, since nothing set another one.
        result = _bake(game_data, [[0x00, 0xA2]], {0: 2})
        assert result.stop_reason == STOP_LOOP

    def test_a2_stops_the_bake_when_the_chain_is_not_followed(self, game_data):
        result = _bake(game_data, [[0x00, 0xA2]], {0: 2}, follow_chain=False)
        assert result.stop_reason == STOP_END
        assert result.nb_frame == 3


class TestWhatMustBeWarnedAbout:

    def test_e4_is_reported_as_a_hang(self, game_data):
        # E4 sets current_value = 0 without advancing the pointer: the engine spins on it.
        result = _bake(game_data, [[0xE4, 0xA9]])
        assert result.stop_reason == STOP_HANG
        assert "E4" in result.stop_detail

    def test_unknown_high_op_code_is_reported_as_a_hang(self, game_data):
        # F4-FF are not in the json and computeAnimationSequence @0x50DB40 hits
        # 'default: continue' without advancing: same hang.
        result = _bake(game_data, [[0xFE, 0xA9]])
        assert result.stop_reason == STOP_HANG

    def test_jump_outside_the_sequence_is_an_error(self, game_data):
        # E6 40: jump 64 bytes forward, well past the end of a 2 byte sequence.
        result = _bake(game_data, [[0xE6, 0x40]])
        assert result.stop_reason == STOP_ERROR
        assert "outside" in result.stop_detail

    def test_goto_a_missing_sequence_is_an_error(self, game_data):
        result = _bake(game_data, [[0xA7, 0x09]])
        assert result.stop_reason == STOP_ERROR

    def test_running_past_the_end_is_an_error(self, game_data):
        # No terminator: the engine would read whatever byte follows in the file.
        result = _bake(game_data, [[0xA1]])
        assert result.stop_reason == STOP_ERROR

    def test_a_sequence_that_never_ends_hits_the_frame_cap(self, game_data):
        # A0 00 then an unconditional backward jump over a yield: it runs forever, but the
        # random value read each frame keeps the state from ever repeating, so the loop
        # detector cannot fire and the cap is what stops it.
        result = _bake(game_data, [[0xA0, 0x00, 0xC3, 0x0C, 0xA1, 0xE6, 0xFB]], {0: 4},
                       max_frame=50)
        assert result.stop_reason == STOP_MAX_FRAMES
        assert result.nb_frame == 50


class TestBattleContext:

    def test_a_battle_context_read_is_recorded_as_an_assumption(self, game_data):
        # C3 18 reads the target slot - a battle value, not a file value.
        result = _bake(game_data, [[0xC3, 0x18, 0xA9]],
                       context=BattleContext(target_slot=3))
        assert result.frame_list[0].current_value == 3
        assert [(parameter, value) for _frame, parameter, _what, value
                in result.assumption_list] == [(0x18, 3)]

    def test_the_context_decides_which_branch_is_taken(self, game_data):
        # C3 22 (back attack), E9 04 (jump if == 0 to the A9 at 6, skipping two yields).
        sequence = [[0xC3, 0x22, 0xE9, 0x04, 0xA1, 0xA1, 0xA9]]
        assert _bake(game_data, sequence, context=BattleContext(back_attack=0)).nb_frame == 1
        assert _bake(game_data, sequence, context=BattleContext(back_attack=1)).nb_frame == 3

    def test_the_random_value_is_seeded_so_a_bake_is_reproducible(self, game_data):
        sequence = [[0xC3, 0x0C, 0xA9]]
        first = _bake(game_data, sequence, context=BattleContext(seed=7))
        second = _bake(game_data, sequence, context=BattleContext(seed=7))
        other = _bake(game_data, sequence, context=BattleContext(seed=8))
        assert first.frame_list[0].current_value == second.frame_list[0].current_value
        assert first.frame_list[0].current_value != other.frame_list[0].current_value


class TestStateAndEvents:

    def test_e5_writes_the_position_and_c3_reads_it_back(self, game_data):
        # C0 E8 03 (current_value = 1000), E5 0E (write position X), then read it back
        # into current_value with C3 0E.
        result = _bake(game_data, [[0xC0, 0xE8, 0x03, 0xE5, 0x0E, 0xC3, 0x0E, 0xA9]])
        assert result.frame_list[0].position[0] == 1000
        assert result.frame_list[0].current_value == 1000

    def test_95_resets_x_and_z_but_not_y(self, game_data):
        # Write X, Y, Z, then 95 (reset position X and Z).
        result = _bake(game_data, [[0xC1, 0x0A, 0xE5, 0x0E, 0xE5, 0x0F, 0xE5, 0x0D,
                                    0x95, 0xA9]])
        assert result.frame_list[0].position == (0, 10, 0)

    def test_a_sound_is_an_event_on_the_frame_it_plays(self, game_data):
        # A1 (yield) then B5 03 00 (play sound 3): the sound lands on frame 1.
        result = _bake(game_data, [[0xA1, 0xB5, 0x03, 0x00, 0xA9]])
        event_list = list(result.iter_event())
        sound_list = [(index, command) for index, command in event_list
                      if command.kind == EVENT_SOUND]
        assert len(sound_list) == 1
        assert sound_list[0][0] == 1

    def test_the_background_sequence_runs_every_frame(self, game_data):
        # Sequence 1 sets sequence 2 as its background (9A 02) then waits 4 frames.
        # Sequence 2 (C1 07 A1) then runs from its start on every LATER frame - frame 0 is
        # the one 9A itself runs on, and the driver reads the background id before the
        # main sequence, so it only takes effect from the next frame.
        result = _bake(game_data, [[0x9A, 0x02, 0xB9, 0x05, 0xA9], [0xC1, 0x07, 0xA1]])
        assert not any(command.is_background
                       for command in result.frame_list[0].command_list)
        assert all(any(command.is_background for command in frame.command_list)
                   for frame in result.frame_list[1:])
        assert result.frame_list[2].current_value == 7

    def test_a_background_sequence_is_found_by_the_9a_naming_it(self, game_data):
        # Sequence 1 sets sequence 2 as its background; sequence 3 is a normal one.
        sequence_by_id = {1: bytes([0x9A, 0x02, 0xA9]), 2: bytes([0x80, 0x01, 0xA1]),
                          3: bytes([0x00, 0xA2])}
        assert background_sequence_id_set(game_data, sequence_by_id) == {2}

    def test_a_background_sequence_previewed_as_a_main_one_runs_off_its_end(self, game_data):
        # "80 01 A1" (step texture animation 1, yield) is the vanilla background shape
        # (c0m123 sequence 12). It has no terminator, so resuming after the A1 walks out
        # of the sequence - and the message has to point at the real cause.
        sequence_by_id = {1: bytes([0x9A, 0x01]), 2: bytes([0x80, 0x01, 0xA1])}
        result = bake_sequence(game_data, sequence_by_id, 2, {})
        assert result.stop_reason == STOP_ERROR
        assert "background sequence" not in result.stop_detail  # no 9A names sequence 2

        sequence_by_id[1] = bytes([0x9A, 0x02])  # now one does
        result = bake_sequence(game_data, sequence_by_id, 2, {})
        assert result.stop_reason == STOP_ERROR
        assert "as_background" in result.stop_detail

    def test_a_background_sequence_restarts_every_frame(self, game_data):
        # Baked the way 9A runs it, it never falls off its end: each frame starts at 0.
        sequence_by_id = {1: bytes([0x9A, 0x02]), 2: bytes([0x80, 0x01, 0xA1])}
        result = bake_sequence(game_data, sequence_by_id, 2, {}, as_background=True,
                               max_frame=10)
        assert result.stop_reason != STOP_ERROR
        assert result.frame_list[0].command_list[0].op_code == 0x80

    def test_the_animations_played_are_listed_in_order(self, game_data):
        result = _bake(game_data, [[0x02, 0x00, 0x02, 0xA9]], {0: 2, 2: 2})
        assert result.animation_id_list() == [2, 0]


class TestVanillaData:
    """Every sequence of every vanilla battle file must bake, and must END SOMEWHERE.

    Shipped data works, so nothing in it may come out as a hang or as an error: it either
    ends, loops forever (an idle stance, the common case), or is still going at the frame
    cap. Anything else means the interpreter is wrong, not the data - which is exactly how
    the two mistakes worth catching show up (a chain the baker follows when the engine
    would not, a pause the baker misses so the sequence runs away).

    The one shape that does need telling apart is the background sequence: the ten vanilla
    ones (c0m123 sequence 12 and friends) have no terminator because 9A restarts them
    every frame, so they are baked the way they are run.
    """

    @pytest.mark.skipif(not BATTLE_PATH.is_dir(), reason="no extracted battle files")
    def test_every_vanilla_sequence_bakes(self, game_data):
        nb_baked = 0
        for path in _entity_file_list():
            monster = MonsterAnalyser(game_data)
            try:
                monster.load_file_data(str(path), game_data)
                monster.analyse_loaded_data(game_data)
            except Exception:
                continue  # not a readable entity file: the analyser tests cover that
            sequence_by_id = sequence_dict_from_section(
                getattr(monster, 'seq_animation_data', None))
            if not sequence_by_id:
                continue
            frame_count = [len(animation.frames)
                           for animation in monster.animation_data.animations]
            background_id_set = background_sequence_id_set(game_data, sequence_by_id)
            for seq_id, data in sequence_by_id.items():
                if not data:
                    continue
                result = bake_sequence(game_data, sequence_by_id, seq_id, frame_count,
                                       max_frame=300,
                                       as_background=seq_id in background_id_set)
                assert result.stop_reason in (STOP_END, STOP_LOOP, STOP_MAX_FRAMES), \
                    (f"{path.name} sequence {seq_id} ({data.hex(' ')}): "
                     f"{result.stop_reason} - {result.stop_detail}")
                assert len(result.frame_list) <= 300
                nb_baked += 1
        assert nb_baked > 1000, "the corpus should hold far more sequences than that"
