"""Tests for the timeline view (FF8GameData/dat/sequencetimeline.py).

The timeline is what makes a baked sequence readable: it folds one record per battle frame
into "these commands ran on frame 45" and "frames 1 to 44 only waited". What is pinned here
is that fold - that it never invents or loses a frame, that it does not let a background
sequence turn every frame into its own row - plus the two things the rendered pane must
always say out loud: where the sequence loops, and which values were assumed.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.sequencebake import bake_sequence, BattleContext
from FF8GameData.dat.sequencetimeline import (build_timeline, format_timeline_html,
                                              assumption_list)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="session")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


def _bake(game_data, sequence_list, frame_count=None, **kwargs):
    sequence_by_id = {index + 1: bytes(data) for index, data in enumerate(sequence_list)}
    return bake_sequence(game_data, sequence_by_id, 1, frame_count or {}, **kwargs)


class TestTheFold:

    def test_every_frame_of_the_bake_lands_in_exactly_one_row(self, game_data):
        # The fold is a partition of the frames: rows must be contiguous, in order, and
        # cover the whole bake. Anything else means the timeline lies about the timing.
        result = _bake(game_data, [[0x00, 0xB5, 0x01, 0x00, 0x01, 0xA9]], {0: 7, 1: 5})
        row_list = build_timeline(result)
        assert row_list[0].first_frame == 0
        assert row_list[-1].last_frame == result.frame_list[-1].index
        for previous, row in zip(row_list, row_list[1:]):
            assert row.first_frame == previous.last_frame + 1

    def test_a_frame_that_ran_commands_gets_its_own_row(self, game_data):
        # 00 (play a 5 frame animation) then A9: two rows that ran something (frame 0 and
        # frame 5) with one wait row between them.
        result = _bake(game_data, [[0x00, 0xA9]], {0: 5})
        row_list = build_timeline(result)
        assert [row.frame_text() for row in row_list] == ["0", "1-4", "5"]
        assert [row.is_wait for row in row_list] == [False, True, False]

    def test_a_wait_row_says_what_it_is_waiting_for(self, game_data):
        result = _bake(game_data, [[0x00, 0xA9]], {0: 5})
        wait_row = build_timeline(result)[1]
        assert wait_row.nb_frame == 4
        assert "waiting for the animation" in wait_row.wait_text()
        assert wait_row.animation_text() == "anim 0 [1-4/5]"

    def test_a_wait_row_splits_when_the_animation_changes(self, game_data):
        # Two animations back to back: their wait rows cannot be merged into one.
        result = _bake(game_data, [[0x00, 0x01, 0xA9]], {0: 4, 1: 4})
        anim_id_list = [row.anim_id for row in build_timeline(result) if row.is_wait]
        assert anim_id_list == [0, 1]

    def test_frames_running_the_same_commands_merge_into_one_row(self, game_data):
        # The per-frame poll: A0 00 (keep the animation running) / C3 08 (read the battle
        # flag) / EA 05 (leave once it is set) / A1 (yield) / E6 F9 (back to the top). It
        # runs the same block every frame; printing it once per frame would bury whatever
        # comes after. c0m001 sequence 13 does exactly this for 10 frames.
        sequence = [[0xA0, 0x00, 0xC3, 0x08, 0xEA, 0x05, 0xA1, 0xE6, 0xF9, 0xA9]]
        result = _bake(game_data, sequence, {0: 4})
        poll_row = [row for row in build_timeline(result) if row.is_repeat]
        assert len(poll_row) == 1
        assert poll_row[0].nb_frame > 1
        assert "ran on each of these" in poll_row[0].repeat_text()

    def test_a_row_the_animation_wraps_inside_does_not_read_backwards(self, game_data):
        # A0 loops its animation, so a merged row can start on frame 1 and end on frame 0.
        sequence = [[0xA0, 0x00, 0xC3, 0x08, 0xEA, 0x05, 0xA1, 0xE6, 0xF9, 0xA9]]
        row = [row for row in build_timeline(_bake(game_data, sequence, {0: 4}))
               if row.is_repeat][0]
        assert row.animation_text() == "anim 0 [looping, 4 frames]"

    def test_a_background_sequence_does_not_flood_the_timeline(self, game_data):
        # Sequence 2 runs every frame (9A 02). Kept, it would give every frame a command
        # and turn all 5 frames into their own row, burying the sequence being read.
        sequence = [[0x9A, 0x02, 0x00, 0xA9], [0xC1, 0x07, 0xA1]]
        result = _bake(game_data, sequence, {0: 5})
        assert [row.frame_text() for row in build_timeline(result)] == ["0", "1-4", "5"]
        # Kept, they leave no frame idle: the wait row becomes a "same commands every
        # frame" one instead, which is true but says nothing about the sequence being read.
        with_background = build_timeline(result, include_background=True)
        assert not any(row.is_wait for row in with_background)
        assert any(row.is_repeat for row in with_background)


class TestTheRenderedPane:

    def test_it_names_the_frame_the_sequence_loops_back_to(self, game_data):
        # The idle pattern: A3 / 00 / E6 FF.
        result = _bake(game_data, [[0xA3, 0x00, 0xE6, 0xFF]], {0: 6})
        html = format_timeline_html(result)
        assert "loops forever" in html
        assert "&#8635;" in html, "the loop point must be marked in the frame column"

    def test_it_warns_about_a_hang_in_red(self, game_data):
        result = _bake(game_data, [[0xE4, 0xA9]])
        html = format_timeline_html(result)
        assert "HANGS" in html
        assert "#bf616a" in html

    def test_it_lists_what_was_assumed_from_the_battle(self, game_data):
        # C3 18 (target slot) and C3 22 (back attack) are battle values, not file values:
        # a reader has to be told the branch rests on them.
        result = _bake(game_data, [[0xC3, 0x18, 0xC3, 0x22, 0xA9]],
                       context=BattleContext(target_slot=2))
        assert assumption_list(result) == [("target slot", 2), ("back attack / preemptive", 0)]
        assert "Assumed from the battle" in format_timeline_html(result)

    def test_the_random_value_is_not_shown_as_a_fixed_assumption(self, game_data):
        # It is seeded so the timeline is reproducible, but calling it "random value = 8123"
        # would read as if the engine used that number.
        result = _bake(game_data, [[0xC3, 0x0C, 0xA9]])
        assert assumption_list(result) == [("random value", "seeded, changes on re-roll")]

    def test_it_names_the_background_sequence_running_underneath(self, game_data):
        result = _bake(game_data, [[0x9A, 0x02, 0x00, 0xA9], [0xC1, 0x07, 0xA1]], {0: 3})
        assert result.background_seq_id_list == [2]
        assert "Sequence 2 runs" in format_timeline_html(result)

    def test_a_description_cannot_inject_markup(self, game_data):
        # The pane is HTML, and part of what it prints comes from the json descriptions.
        html = format_timeline_html(_bake(game_data, [[0x00, 0xA9]], {0: 2}))
        assert "<script" not in html
        assert html.count("<table") == 1

    def test_an_empty_bake_says_why_instead_of_rendering_nothing(self, game_data):
        result = bake_sequence(game_data, {1: b"\xA9"}, 9, {})  # no sequence 9
        assert not result.frame_list
        assert "no sequence 9" in format_timeline_html(result)
