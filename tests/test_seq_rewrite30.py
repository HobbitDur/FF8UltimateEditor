"""Tests for the 30 fps sequence rewriter (FF8GameData/dat/seqrewrite30.py) and the relinker
it shares with the animation splitter (FF8GameData/dat/sequencerelink.py).

Every rule is checked twice: on the bytes it must produce, and by running the original at
15 Hz against the rewrite at 30 Hz in the sequence interpreter (tests/dat30_verifier.py):
same wall time, same events in the same order. The corpus test does the same for every
sequence of every vanilla battle model and pins the numbers, so a regression shows.
"""
import collections
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.sequencevm import entity_sequence_vm
from FF8GameData.dat.sequencerelink import (parse_node_list, assemble_node_list,
                                            insert_and_fix_jump, SequenceRelinkError)
from FF8GameData.dat import seqrewrite30 as rw
from tests.dat30_verifier import (verify_sequence, read_sequence_dict, read_frame_count_list,
                                  bake, compare)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"
needs_corpus = pytest.mark.skipif(not (BATTLE_PATH / "c0m001.dat").exists(),
                                  reason="extracted battle files not available")


@pytest.fixture(scope="module")
def vm():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_anim_sequence_data()
    return entity_sequence_vm(data)


def _rewrite(vm, hex_text):
    data = bytes.fromhex(hex_text.replace(" ", ""))
    new_data, report = rw.rewrite_sequence(vm, data, 1)
    return data, new_data, report


def _verify(vm, original, rewritten, frames, seq_id=1, **kwargs):
    """The rewrite at 30 Hz matches the original at 15 Hz (empty list = match)."""
    sequence_15 = original if isinstance(original, dict) else {seq_id: original}
    sequence_30 = rewritten if isinstance(rewritten, dict) else {seq_id: rewritten}
    return verify_sequence(vm, sequence_15, sequence_30, seq_id, frames,
                           [2 * n for n in frames], **kwargs)


# ------------------------------------------------------------------------ relinker
class TestRelink:

    def test_parse_assemble_is_the_identity(self, vm):
        data = bytes.fromhex("C10FE57FA000A1C37FC5FFE57FE7F7A2")
        node_list, end = parse_node_list(vm, data)
        assert bytes(assemble_node_list(node_list, end)) == data

    def test_insertion_keeps_every_jump_on_its_command(self, vm):
        # 0: 05 (anim) / 1: E6 FF -> 0 ; insert 2 parts after the anim
        data = bytes.fromhex("05E6FF")
        new_data = insert_and_fix_jump(vm, data, {1: bytes([0x20, 0x21])})
        assert bytes(new_data) == bytes.fromhex("052021E6FD")

    def test_a_short_jump_out_of_reach_is_promoted(self, vm):
        data = bytes.fromhex("A1E6FF")   # A1 / JMP -> A1
        node_list, end = parse_node_list(vm, data)
        filler = [n for n in parse_node_list(vm, bytes([0xA1]) * 200)[0]]
        node_list = node_list[:1] + filler + node_list[1:]
        with pytest.raises(SequenceRelinkError):
            assemble_node_list(node_list, end, promote_jump=False)
        new_data = assemble_node_list(node_list, end, promote_jump=True)
        assert new_data[-3] == 0xED      # E6 became ED (int16)
        assert int.from_bytes(new_data[-2:], "little", signed=True) == -201

    def test_a_jump_into_a_parameter_is_refused(self, vm):
        with pytest.raises(SequenceRelinkError):
            parse_node_list(vm, bytes.fromhex("C10FE6FF"))   # jumps into C1's parameter


# ------------------------------------------------------------------------ rules
class TestStraightLineRules:

    def test_b9_doubles(self, vm):
        _, new_data, report = _rewrite(vm, "B9 05 A2")
        assert new_data == bytes.fromhex("B90AA2")
        assert rw.RULE_B9 in report.rule_set

    def test_b9_128_becomes_b9_0(self, vm):
        _, new_data, _ = _rewrite(vm, "B9 80 A2")
        assert new_data == bytes.fromhex("B900A2")    # B9 00 waits 256 ticks

    def test_b9_over_255_is_split(self, vm):
        original, new_data, report = _rewrite(vm, "B9 C8 A2")   # 200 -> 400 = 255 + 145
        assert new_data == bytes.fromhex("B9FFB991A2")
        assert rw.RULE_B9_SPLIT in report.rule_set
        assert _verify(vm, original, new_data, [4]) == []

    def test_ba_is_doubled(self, vm):
        _, new_data, _ = _rewrite(vm, "BA A2")
        assert new_data == bytes.fromhex("BABAA2")

    def test_straight_a1_is_doubled(self, vm):
        original, new_data, report = _rewrite(vm, "B5 00 00 A1 B5 01 00 A2")
        assert new_data == bytes.fromhex("B50000A1A1B50100A2")
        assert rw.RULE_STRAIGHT_A1 in report.rule_set
        assert _verify(vm, original, new_data, [4]) == []

    def test_task_durations_double(self, vm):
        _, new_data, _ = _rewrite(vm, "84 0A 9E 01 18 AD 05 00 10 18 AE 01 02 00 10 19 A2")
        assert new_data == bytes.fromhex("8414 9E0130 AD05001030 AE0102001032 A2".replace(" ", ""))

    def test_9f_stamps_double(self, vm):
        _, new_data, _ = _rewrite(vm, "9F 03 07 FF A2")
        assert new_data == bytes.fromhex("9F060EFFA2")

    def test_15hz_task_parameters_are_left_alone(self, vm):
        """96, 99/B1, A6, 81: hardcoded 15-tick tasks FFNx keeps at 15 Hz."""
        text = "96 64 00 05 99 13 06 0A FF B1 14 04 09 FF A6 07 00 00 E0 FC F4 01 00 FD 81 02 A2"
        original, new_data, _ = _rewrite(vm, text)
        assert new_data == original

    def test_the_ab_list_is_left_alone(self, vm):
        """AB consumes its animation list up to its A1: neither the ids nor that A1 change
        (FFNx handles the Renzokuken timing)."""
        original, new_data, report = _rewrite(vm, "AB 00 21 23 27 A0 29 24 A1 A2")
        assert new_data == original
        assert report.status == rw.STATUS_UNCHANGED

    def test_a_frame_counted_sequence_needs_nothing(self, vm):
        # 0F: anim 15 (waits), A0 10 / C3 0A E5 7F / loop: d * 09 / 0A -> z ; A1 ; 7F-- ; back
        text = ("0F A0 10 C3 0A E5 7F C3 02 CF 09 E5 FE C3 FE D3 0A E5 0F A1 "
                "C3 7F C5 FF E5 7F E7 EF A2")
        original, new_data, report = _rewrite(vm, text)
        assert new_data == original
        assert rw.RULE_FRAME_LOOP in report.rule_set
        assert _verify(vm, original, new_data, [0] * 15 + [8, 12]) == []


class TestLoopRules:

    def test_literal_counter_doubles(self, vm):
        # C1 0F E5 7F / 4: A0 00 / A1 / 7F-- / E7 -> 4
        original, new_data, report = _rewrite(vm, "C1 0F E5 7F A0 00 A1 C3 7F C5 FF E5 7F E7 F7 A2")
        assert new_data == bytes.fromhex("C11EE57FA000A1C37FC5FFE57FE7F7A2")
        assert rw.RULE_LITERAL_COUNTER in report.rule_set
        assert _verify(vm, original, new_data, [6]) == []

    def test_per_tick_increment_halves(self, vm):
        # C1 0A E5 7F / 4: z += 300 / A1 / 7F-- / E7 -> 4
        text = "C1 0A E5 7F C3 0F C4 2C 01 E5 0F A1 C3 7F C5 FF E5 7F E7 F2 A2"
        original, new_data, report = _rewrite(vm, text)
        assert new_data == bytes.fromhex("C114E57FC30FC49600E50FA1C37FC5FFE57FE7F2A2")
        assert rw.RULE_STEP_HALF in report.rule_set
        assert report.odd_step_list == []
        assert _verify(vm, original, new_data, [4]) == []

    def test_an_odd_step_is_rounded_and_reported(self, vm):
        text = "C1 0A E5 7F C3 0F C5 15 E5 0F A1 C3 7F C5 FF E5 7F E7 F3 A2"   # z += 21
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("C50B") in new_data                             # 11 per 30 Hz tick
        assert report.odd_step_list == [(6, 21, 11)]
        assert rw.RULE_ODD_STEP in report.rule_set
        assert _verify(vm, original, new_data, [4], drift_per_tick=1) == []

    def test_ratio_loop(self, vm):
        """z = (11 - counter) * 100 / 10: k within one of the start N keeps the +1 offset
        (k + N), the divisor doubles."""
        text = "C1 0A E5 7F C1 0B CB 7F CC 64 00 D1 0A E5 0F A1 C3 7F C5 FF E5 7F E7 EE A2"
        original, new_data, report = _rewrite(vm, text)
        assert new_data == bytes.fromhex("C114E57FC115CB7FCC6400D114E50FA1C37FC5FFE57FE7EEA2")
        assert rw.RULE_COUNTER_CONSTANT in report.rule_set
        assert _verify(vm, original, new_data, [4]) == []

    def test_a_counter_compared_with_a_literal_doubles_it(self, vm):
        """up-counter from 0, leaves when it reaches 30 (c0m061 sequence 13 shape)."""
        # 0: var0 = 0 / 4: A0 00 / 6: if var0 - 30 == 0 -> 21 / A1 / var0 += 1 / JMP 4 / 21: A2
        text = "C1 00 E5 00 A0 00 C3 00 C9 1E E9 0B A1 C3 00 C5 01 E5 00 E6 F1 A2"
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("C93C") in new_data      # 30 -> 60
        assert _verify(vm, original, new_data, [6]) == []

    def test_events_in_a_smooth_loop_are_gated_on_counter_parity(self, vm):
        # C1 05 E5 7F / 4: B5 00 00 / A1 / 7F-- / E7 -> 4
        original, new_data, report = _rewrite(vm, "C1 05 E5 7F B5 00 00 A1 C3 7F C5 FF E5 7F E7 F6 A2")
        assert rw.RULE_EVENT_GATE in report.rule_set
        # counter 10 (even) at the first tick: fires when even, skips (EA) when odd
        assert new_data.startswith(bytes.fromhex("C10AE57FC37FD601EA05B50000A1"))
        assert _verify(vm, original, new_data, [4]) == []
        result = bake(vm, {1: new_data}, 1, [8], {}, 100)
        assert sum(1 for f in result.frame_list for c in f.command_list if c.op_code == 0xB5) == 5

    def test_counter_modulo_keeps_every_nth_tick(self, vm):
        """`counter % 5 == 0` -> `counter % 10 == 0` (c0m025 sequence 12 shape)."""
        text = ("C1 1A E5 7F C3 7F E1 05 E5 7E C1 00 CB 7E EA 05 B5 00 00 A1 "
                "C3 7F C5 FF E5 7F E7 EA A2")
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("E10A") in new_data
        assert _verify(vm, original, new_data, [6]) == []

    def test_unknown_counter_origin_falls_back_to_15hz_cadence(self, vm):
        # counter = random % 5 / 6: A1 / 7F-- / E7 -> 6
        original, new_data, report = _rewrite(vm, "C3 0C E1 05 E5 7F A1 C3 7F C5 FF E5 7F E7 F9 A2")
        assert new_data == bytes.fromhex("C30CE105E57FA1A1C37FC5FFE57FE7F8A2")
        assert report.status == rw.STATUS_FALLBACK
        assert report.fallback_list
        assert _verify(vm, original, new_data, [4]) == []

    def test_an_endless_loop_firing_every_tick_falls_back(self, vm):
        original, new_data, report = _rewrite(vm, "A0 00 80 02 A1 E6 FD")
        assert new_data == bytes.fromhex("A0008002A1A1E6FC")
        assert report.status == rw.STATUS_FALLBACK
        assert _verify(vm, original, new_data, [4]) == []

    def test_an_external_flag_poll_is_left_alone(self, vm):
        # effect handshake: wait for bit 0x10 of the state flags
        text = "C3 08 D5 10 E5 7F C1 10 CB 7F E9 03 A1 E6 F3 A2"
        original, new_data, report = _rewrite(vm, text)
        assert new_data == original
        assert rw.RULE_POLL in report.rule_set


class TestFrameRules:

    def test_frame_index_equality(self, vm):
        """`C3 09 == 8` fires at 30 Hz when C3 09 == 15 (2c - 1), the same instant."""
        text = ("A0 00 C3 0A E5 7F C3 09 E5 7E C1 08 CB 7E EA 05 B5 00 00 A1 "
                "C3 7F C5 FF E5 7F E7 EC A2")
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("C10FCB7E") in new_data
        assert rw.RULE_FRAME_INDEX in report.rule_set
        assert _verify(vm, original, new_data, [20]) == []

    def test_frame_parity(self, vm):
        """Soldier family (c0m064 sequence 13): `C3 09 & 1 == 1` -> `C3 09 & 3 == 1`, and the
        guarded event is not gated again."""
        text = ("A0 00 C1 14 E5 7F C3 09 D5 01 E5 7E C1 01 CB 7E EA 05 B5 00 00 A1 "
                "C3 7F C5 FF E5 7F E7 EA A2")
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("C128E57FC309D503E57EC101CB7E") in new_data
        assert rw.RULE_FRAME_PARITY in report.rule_set
        assert rw.RULE_EVENT_GATE not in report.rule_set
        assert _verify(vm, original, new_data, [37]) == []

    def test_frame_window_offset(self, vm):
        """`total/2 - 3 < C3 09 < total/2 + 3` (c0m010 sequence 12): the offsets carry the
        -1 of the index rule (3 -> 7 and 5)."""
        text = ("A0 00 C3 0A E5 7F "
                "C3 09 E5 7E C3 0A D1 02 C9 03 CB 7E E8 13 "            # 6: lower bound
                "C3 09 E5 7E C3 0A D1 02 C5 03 CB 7E EB 05 B5 00 00 "   # 20: upper bound
                "A1 C3 7F C5 FF E5 7F E7 DA A2")
        original, new_data, report = _rewrite(vm, text)
        assert bytes.fromhex("C907CB7E") in new_data and bytes.fromhex("C505CB7E") in new_data
        assert _verify(vm, original, new_data, [20]) == []


class TestBackgroundSequence:

    def test_a_background_sequence_is_gated_to_15hz(self, vm):
        sequence = {1: bytes.fromhex("9A02A1E6FF"), 2: bytes.fromhex("8001A1")}
        new, section_report = rw.rewrite_sequence_dict(vm, sequence)
        assert section_report.background_id_set == {2}
        assert section_report.toggle_var == 0x78
        assert new[2] == bytes.fromhex("C378DD01E578E9048001A1")
        assert section_report.sequence_report[2].status == rw.STATUS_REWRITTEN
        assert verify_sequence(vm, sequence, new, 2, [4], [8], as_background=True) == []
        assert verify_sequence(vm, sequence, new, 1, [4], [8]) == []
        # and the check does catch an ungated one: twice the texture steps
        assert verify_sequence(vm, sequence, sequence, 2, [4], [8], as_background=True)

    def test_a_background_body_that_is_not_straight_is_a_manual_decision(self, vm):
        sequence = {1: bytes.fromhex("9A02A1E6FF"), 2: bytes.fromhex("8001E6FE")}
        new, section_report = rw.rewrite_sequence_dict(vm, sequence)
        assert section_report.sequence_report[2].status == rw.STATUS_MANUAL
        assert new[2] == sequence[2]

    def test_the_toggle_variable_is_one_no_sequence_uses(self, vm):
        sequence = {1: bytes.fromhex("C301E578C301E5799A03A1E6FF"), 3: bytes.fromhex("8001A1")}
        _, section_report = rw.rewrite_sequence_dict(vm, sequence)
        assert section_report.toggle_var == 0x7A


class TestVerifier:

    def test_an_unconverted_wait_is_caught(self, vm):
        original = bytes.fromhex("B91EB50000A2")   # wait 30 ticks, sound
        assert _verify(vm, original, original, [4])

    def test_b9_waits_exactly_n_ticks(self, vm):
        result = bake(vm, {1: bytes.fromhex("B905B50000A2")}, 1, [4], {}, 50)
        tick = next(f.index for f in result.frame_list
                    for c in f.command_list if c.op_code == 0xB5)
        assert tick == 5


# ------------------------------------------------------------------------ corpus
# Pinned over every vanilla c0m/dXc/dXw file (mag* excluded): 3160 sequences.
EXPECTED_COUNT = {rw.STATUS_REWRITTEN: 889, rw.STATUS_UNCHANGED: 2268, rw.STATUS_FALLBACK: 3}
EXPECTED_NOT_AUTOMATIC = {("c0m010.dat", 8), ("c0m060.dat", 3), ("c0m073.dat", 13)}


def _corpus_file_list():
    return [path for path in sorted(BATTLE_PATH.glob("*.dat"))
            if path.name.lower().startswith(("c0m", "d")) and path.stat().st_size >= 8]


def _body_frame_count_list(path):
    for body in sorted(BATTLE_PATH.glob(path.name[:2] + "c*.dat")):
        frame_list = read_frame_count_list(body.read_bytes())
        if frame_list:
            return frame_list
    return []


@needs_corpus
def test_relink_round_trip_on_every_vanilla_sequence(vm):
    nb = 0
    for path in _corpus_file_list():
        for seq_id, data in read_sequence_dict(path.read_bytes()).items():
            if not data:
                continue
            node_list, end = parse_node_list(vm, data)
            assert bytes(assemble_node_list(node_list, end)) == data, (path.name, seq_id)
            nb += 1
    assert nb == 3160


@needs_corpus
def test_corpus_every_rewrite_matches_the_original(vm):
    """Every sequence of every vanilla model: rewritten, then run at 15 Hz (original) vs
    30 Hz (rewrite) in three battle contexts. All must match; the counts are pinned."""
    count = collections.Counter()
    failing, not_automatic = [], set()
    for path in _corpus_file_list():
        data = path.read_bytes()
        sequence = read_sequence_dict(data)
        if not sequence:
            continue
        frames = read_frame_count_list(data) or _body_frame_count_list(path)
        new, section_report = rw.rewrite_sequence_dict(vm, sequence)
        for seq_id, report in section_report.sequence_report.items():
            if not sequence[seq_id]:
                continue
            count[report.status] += 1
            if report.status != rw.STATUS_REWRITTEN and report.status != rw.STATUS_UNCHANGED:
                not_automatic.add((path.name, seq_id))
            problem_list = verify_sequence(vm, sequence, new, seq_id, frames,
                                           [2 * n for n in frames],
                                           as_background=report.is_background,
                                           drift_per_tick=1 if report.odd_step_list else 0)
            if problem_list:
                failing.append((path.name, seq_id, problem_list[:2]))
    print(f"\ncorpus: {dict(count)}, failing {len(failing)}, not fully automatic "
          f"{sorted(not_automatic)}")
    assert failing == []
    assert dict(count) == EXPECTED_COUNT
    assert not_automatic == EXPECTED_NOT_AUTOMATIC
