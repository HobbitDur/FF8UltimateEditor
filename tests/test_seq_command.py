"""Tests for the sequence command model (FF8GameData/dat/sequencecommand.py).

The model is what lets IfritSeq stop being a hex box: a command is an object with an op
code, typed parameters and a jump target, instead of a slice the user has to count out by
hand. Everything else planned on top of it (rows with dropdowns, jump labels, a preview)
is only as trustworthy as two properties tested here:

- the walk finds the same command boundaries the engine does, on real data;
- read -> write is the identity, so opening a file and saving it cannot corrupt it.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.dat.sequencecommand import (SequenceCommand, read_sequence, write_sequence,
                                             read_sequence_command_list, get_op_code_info,
                                             normalize_parameters, default_parameters)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


def _corpus_file_list():
    """Monster/character/weapon files. mag*.dat excluded: MonsterAnalyser does not
    terminate on them (they are magic effect files, not entity models)."""
    return sorted(path for path in BATTLE_PATH.glob("*.dat")
                  if not path.name.startswith("mag"))


def _iter_real_sequence(game_data):
    import contextlib
    import io
    for path in _corpus_file_list():
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                monster = MonsterAnalyser(game_data)
                monster.load_file_data(str(path), game_data)
                monster.analyse_loaded_data(game_data)
        except Exception:
            continue
        section = getattr(monster, "seq_animation_data", None) or {}
        for sequence in section.get("seq_animation_data", []):
            if sequence["data"]:
                yield path.name, sequence["id"], bytes(sequence["data"])


class TestReadWrite:
    """The model's core promise: nothing is lost between bytes and commands."""

    def test_a_bare_op_code_is_an_animation_played_once(self, game_data):
        command_list = read_sequence(game_data, bytes([0x00, 0x05, 0x7F]))
        assert [c.op_code for c in command_list] == [0x00, 0x05, 0x7F]
        assert all(c.is_animation() for c in command_list)
        assert [c.get_animation_id() for c in command_list] == [0x00, 0x05, 0x7F]
        assert all(c.get_size() == 1 for c in command_list)

    def test_a0_carries_the_animation_id_as_a_parameter(self, game_data):
        command, = read_sequence(game_data, bytes([0xA0, 0x12]))
        assert not command.is_animation(), "A0 is not itself an animation op code"
        assert command.get_animation_id() == 0x12, "but it does play animation 0x12"
        assert command.get_size() == 2

    def test_an_op_code_playing_no_animation_has_no_animation_id(self, game_data):
        command, = read_sequence(game_data, bytes([0xA3]))
        assert command.get_animation_id() is None

    def test_addresses_are_where_each_command_starts(self, game_data):
        # A3 (0 param) / 00 (anim) / A0 12 (2 bytes) / E6 FF (2 bytes)
        command_list = read_sequence(game_data, bytes([0xA3, 0x00, 0xA0, 0x12, 0xE6, 0xFF]))
        assert [c.address for c in command_list] == [0, 1, 2, 4]

    def test_write_sequence_rebuilds_the_bytes(self, game_data):
        data = bytes([0xA3, 0x00, 0xA0, 0x12, 0xE6, 0xFF])
        assert write_sequence(read_sequence(game_data, data)) == data

    def test_write_sequence_recomputes_addresses(self, game_data):
        """An edited list must not keep the addresses it was read with."""
        command_list = read_sequence(game_data, bytes([0xA3, 0x00, 0xE6, 0xFF]))
        command_list.insert(1, SequenceCommand(game_data, 0xA0, b"\x07"))
        write_sequence(command_list)
        assert [c.address for c in command_list] == [0, 1, 3, 4]

    def test_an_empty_sequence_reads_to_nothing(self, game_data):
        assert read_sequence(game_data, b"") == []
        assert write_sequence([]) == bytearray()


class TestRenzokuken:
    """AB is why the two walks had to become one: the json says size -1, which the old
    SequenceAnalyser turned into one parameter byte, but FF8_EN.exe
    AnimSeq_DispatchActionOpcode @0x504bb0 case 0xAB does ptr += 2 before resuming. One
    byte out means every following op code is read from the wrong place."""

    def test_ab_takes_two_parameter_bytes(self, game_data):
        # The real byte string from d0w000 seq 13: AB 00 21, then anim 23 follows
        command_list = read_sequence(game_data, bytes([0xAB, 0x00, 0x21, 0x23]))
        assert command_list[0].op_code == 0xAB
        assert command_list[0].parameters == bytearray([0x00, 0x21])
        assert command_list[0].get_size() == 3
        assert command_list[1].op_code == 0x23, \
            "the command after AB starts two bytes later, not one"

    @pytest.mark.skipif(not (BATTLE_PATH / "d0w000.dat").is_file(),
                        reason="extracted battle files not available")
    def test_squall_renzokuken_reads_the_slashes_that_follow(self, game_data):
        """Reading AB one byte short shifts the whole rest of Squall's Renzokuken."""
        name_id_data = [x for x in _iter_real_sequence(game_data)
                        if x[0] == "d0w000.dat" and x[1] == 13]
        assert name_id_data, "d0w000 sequence 13 not found"
        _name, _seq_id, data = name_id_data[0]
        command_list = read_sequence(game_data, data)
        ab_index = next(i for i, c in enumerate(command_list) if c.op_code == 0xAB)
        assert command_list[ab_index].get_size() == 3
        # What follows the AB is the chain of slash animations (bare op codes and A0 XX,
        # d0w000 seq 13 has 23 27 28 then A0 29), ending on A1
        following = command_list[ab_index + 1:ab_index + 5]
        assert all(c.get_animation_id() is not None for c in following), \
            f"expected animation-playing commands after AB, got {following}"


class TestJump:
    def test_a_backward_jump_target_is_relative_to_the_op_code(self, game_data):
        # E6 FF at address 1 jumps -1 -> back onto address 0. The real idle stance shape.
        command_list = read_sequence(game_data, bytes([0x00, 0xE6, 0xFF]))
        jump = command_list[1]
        assert jump.is_jump()
        assert jump.get_jump_target() == 0

    def test_set_jump_target_writes_the_offset_back(self, game_data):
        command_list = read_sequence(game_data, bytes([0x00, 0x00, 0xE6, 0xFF]))
        jump = command_list[2]
        jump.set_jump_target(0)
        assert jump.get_jump_target() == 0
        assert jump.parameters == bytearray([0xFE]), "-2 as a signed byte"

    def test_setting_a_jump_target_on_a_non_jump_is_refused(self, game_data):
        command, = read_sequence(game_data, bytes([0xA3]))
        with pytest.raises(ValueError):
            command.set_jump_target(0)


class TestUnknownOpCode:
    """Op codes the json does not describe, handled exactly like the engine does."""

    def test_an_undescribed_action_op_code_is_an_engine_no_op(self, game_data):
        """0x87-0x8F and 0xB3 hit AnimSeq_DispatchActionOpcode @0x504bb0's default case:
        no parameter is consumed and the next byte is the next op code."""
        for op_code in (0x87, 0x8F, 0xB3):
            assert get_op_code_info(game_data, op_code) is None, \
                f"0x{op_code:02X} grew a json entry, this test needs another op code"
            data = bytes([op_code, 0xA0, 0x12])
            command_list = read_sequence(game_data, data)
            assert [c.op_code for c in command_list] == [op_code, 0xA0]
            assert command_list[0].get_size() == 1
            assert write_sequence(command_list) == data

    def test_an_unknown_vm_op_code_keeps_the_rest_of_the_sequence(self, game_data):
        """0xF4+ hits computeAnimationSequence @0x50db40's default case without advancing:
        the engine hangs on it, there is no defined size. The walk stops - but the bytes
        must survive a save."""
        unknown = 0xFF  # not in op_code_info
        assert get_op_code_info(game_data, unknown) is None, "0xFF must stay unknown"
        data = bytes([0x00, unknown, 0x11, 0x22])
        command_list = read_sequence(game_data, data)
        assert command_list[-1].is_unknown()
        assert write_sequence(command_list) == data, \
            "an unreadable tail must round trip, not be dropped on save"


class TestNormalizeParameters:
    """normalize_parameters must agree with iter_command: a normalized command, written
    out and re-walked ALONE, reads back as exactly that command with nothing left over.
    That property is what lets the editor rebuild a sequence from edited rows without
    the next command starting inside leftover parameter bytes."""

    def _roundtrip(self, game_data, op_code, parameters):
        block = normalize_parameters(game_data, op_code, parameters)
        command = SequenceCommand(game_data, op_code, block)
        data = bytes(command.to_bytes())
        walked = list(read_sequence(game_data, data))
        assert len(walked) == 1, f"0x{op_code:02X} {block.hex(' ')} split into {walked}"
        assert walked[0].op_code == op_code
        assert walked[0].parameters == block
        return block

    def test_every_op_code_with_arbitrary_junk_parameters(self, game_data):
        """Whatever the starting block, normalizing then walking is coherent."""
        junk_blocks = [b"", b"\x00", b"\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x11\x22\x33"]
        for op_code in range(0x00, 0xF4):
            if get_op_code_info(game_data, op_code) is None and op_code >= 0xC0:
                continue  # undecodable by the engine, nothing to normalize
            for junk in junk_blocks:
                self._roundtrip(game_data, op_code, junk)

    def test_sound_flag_bit1_adds_the_channel_mask_byte(self, game_data):
        assert len(normalize_parameters(game_data, 0xB5, b"\x03\x00")) == 2
        assert len(normalize_parameters(game_data, 0xB5, b"\x03\x02")) == 3
        assert len(normalize_parameters(game_data, 0xB5, b"\x03\x02\x05\x99")) == 3

    def test_hit_effect_flags_drive_the_block_size(self, game_data):
        assert len(normalize_parameters(game_data, 0xB4, b"\x15\x00")) == 2
        assert len(normalize_parameters(game_data, 0xB4, b"\x15\x07")) == 5
        assert len(normalize_parameters(game_data, 0xB4, b"\x15\x08")) == 3
        assert len(normalize_parameters(game_data, 0xB4, b"\x15\x40")) == 8
        assert len(normalize_parameters(game_data, 0xB4, b"\x15\x48")) == 3, \
            "bit3 wins over bit6, exactly like the exe's if/elif"

    def test_ff_list_gets_terminated(self, game_data):
        assert normalize_parameters(game_data, 0x9F, b"\x01\x02") == bytearray(b"\x01\x02\xFF")
        assert normalize_parameters(game_data, 0x99, b"") == bytearray(b"\x00\xFF")

    def test_default_parameters_are_already_normalized(self, game_data):
        for op_code in range(0x00, 0xF4):
            if get_op_code_info(game_data, op_code) is None and op_code >= 0xC0:
                continue
            default = default_parameters(game_data, op_code)
            assert normalize_parameters(game_data, op_code, default) == default, \
                f"0x{op_code:02X}: default {default.hex(' ')} is not stable"


@pytest.mark.skipif(not BATTLE_PATH.is_dir(), reason="extracted battle files not available")
class TestRealFile:
    def test_every_real_sequence_round_trips_byte_for_byte(self, game_data):
        """Read then write every vanilla sequence: opening a file and saving it back
        unchanged must be a no-op at the byte level, or the editor corrupts data."""
        broken = []
        nb = 0
        for name, seq_id, data in _iter_real_sequence(game_data):
            nb += 1
            if write_sequence(read_sequence(game_data, data)) != data:
                broken.append(f"{name} seq {seq_id}")
        assert nb > 1000, f"corpus looks too small ({nb} sequences)"
        assert not broken, f"{len(broken)} sequences do not round trip: {broken[:20]}"

    def test_no_real_sequence_hits_an_unknown_op_code(self, game_data):
        """If this fails, the json lost an op code and every sequence using it is being
        cut short - the model would stop reading right there."""
        unknown = []
        for name, seq_id, data in _iter_real_sequence(game_data):
            for command in read_sequence(game_data, data):
                if command.is_unknown():
                    unknown.append(f"{name} seq {seq_id}: op 0x{command.op_code:02X}")
        assert not unknown, f"unknown op codes in vanilla data: {unknown[:20]}"

    def test_the_model_agrees_with_the_tuple_walk(self, game_data):
        """read_sequence is a wrapper over the walk animloopdetector and animsplitter use;
        if they ever drift apart, a sequence gets described one way and rewritten another."""
        for name, seq_id, data in _iter_real_sequence(game_data):
            tuple_list = read_sequence_command_list(game_data, data)
            model_list = read_sequence(game_data, data)
            assert len(tuple_list) == len(model_list), f"{name} seq {seq_id}"
            for (address, op_code, _parameters), command in zip(tuple_list, model_list):
                assert (address, op_code) == (command.address, command.op_code), \
                    f"{name} seq {seq_id}"
