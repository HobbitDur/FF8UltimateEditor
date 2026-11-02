"""Instruction insertion/removal in field scripts (CCGroup/jsmedit.py) and the Cronos turn clock of
the NPC card players (CCGroup/jsmcardgame.py), on hand-built scripts and on every real field script
of extracted_files (the real-file part is skipped in CI, copyright)."""
import pathlib
import struct

import pytest

from CCGroup import jsmedit
from CCGroup.jsmcardgame import (JsmCardGameFile, CardGameFolderManager, CARDGAME_DWORD, OPCODE_PSHN_L,
                                 OPCODE_POPM_W, OPCODE_POPM_B, VAR_CRONOS_CLOCK_SECONDS,
                                 VAR_CRONOS_CLOCK_INCREMENT, PARAM_DECK_ID, clock_block_words, clock_text)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD_DIR = PROJECT_ROOT / "extracted_files" / "field"

OPCODE_LBL, OPCODE_RET, OPCODE_JMP, OPCODE_JPF = 0x05, 0x06, 0x02, 0x03
RET_WORD = 0x00000006


def build_jsm(scripts):
    """A one-entity .jsm from lists of instruction words (each script starts with its LBL)."""
    nb_scripts = len(scripts)
    offset_section1 = 8 + 2  # header + 1 entity entry
    offset_script = offset_section1 + 2 * (nb_scripts + 1)
    data = bytearray([0, 0, 0, 1])  # 1 "other" entity
    data += struct.pack("<HH", offset_section1, offset_script)
    data += struct.pack("<H", (nb_scripts - 1) | (0 << 7))
    position = 0
    for script in scripts:
        data += struct.pack("<H", position)
        position += len(script)
    data += struct.pack("<H", position)  # end of the data
    for script in scripts:
        for word in script:
            data += struct.pack("<I", word)
    return bytes(data)


def card_game_script(index, deck=7):
    return [jsmedit.encode(OPCODE_LBL, index),
            jsmedit.encode(OPCODE_PSHN_L, 1), jsmedit.encode(OPCODE_JPF, 10),  # 2: if 1: the match, else RET
            jsmedit.encode(OPCODE_PSHN_L, deck), jsmedit.encode(OPCODE_PSHN_L, 1), jsmedit.encode(OPCODE_PSHN_L, 1),
            jsmedit.encode(OPCODE_PSHN_L, 50), jsmedit.encode(OPCODE_PSHN_L, 3), jsmedit.encode(OPCODE_PSHN_L, 2),
            jsmedit.encode(OPCODE_PSHN_L, 3), CARDGAME_DWORD,
            jsmedit.encode(OPCODE_JMP, -8),  # 11: back to the first push (3), a jump onto the call's pushes
            RET_WORD]  # 12


def decode(data):
    """(entry positions, instruction words)"""
    offset_section1, offset_script = struct.unpack_from("<HH", data, 4)
    entries = [struct.unpack_from("<H", data, offset)[0] for offset in range(offset_section1, offset_script, 2)]
    return entries, jsmedit.instruction_words(data)


def jump_targets(words):
    return {index: index + jsmedit._sign_extend_24(word & 0xFFFFFF) for index, word in enumerate(words)
            if word >> 24 in jsmedit.RELATIVE_JUMP_OPCODES}


class TestJsmEdit:

    def test_insert_shifts_later_scripts_and_reaims_jumps(self):
        data = build_jsm([card_game_script(0), card_game_script(1, deck=9)])
        entries, words = decode(data)
        inserted = jsmedit.insert_instructions(data, 3, [0x07000001, 0x07000002])
        new_entries, new_words = decode(inserted)
        assert new_entries == [entries[0], entries[1] + 2, entries[2] + 2]
        assert new_words[3:5] == [0x07000001, 0x07000002]
        targets = jump_targets(new_words)
        assert targets[2] == 14  # JPF still skips the whole match (now 2 longer) to the RET
        assert new_words[targets[2]] == words[12] == RET_WORD
        assert targets[13] == 3  # the JMP onto the pushes lands on the inserted code
        # the second script is untouched apart from its position
        assert new_words[15:] == words[13:]

    def test_remove_is_the_exact_inverse(self):
        data = build_jsm([card_game_script(0), card_game_script(1)])
        inserted = jsmedit.insert_instructions(data, 16, [0x07000005] * 4)
        assert jsmedit.remove_instructions(inserted, 16, 4) == data

    def test_refusals(self):
        data = build_jsm([card_game_script(0), card_game_script(1)])
        with pytest.raises(ValueError):
            jsmedit.insert_instructions(data, 13, [0])  # the second script's LBL
        with pytest.raises(ValueError):
            jsmedit.remove_instructions(data, 12, 2)  # holds a script start
        with pytest.raises(ValueError):
            jsmedit.remove_instructions(data, 10, 2)  # holds a jump


class TestClockModel:

    @pytest.fixture
    def jsm(self, tmp_path):
        path = tmp_path / "test.jsm"
        path.write_bytes(build_jsm([card_game_script(0), card_game_script(1, deck=9)]))
        return JsmCardGameFile(str(path))

    def test_add_change_remove(self, jsm, tmp_path):
        first, second = jsm.players
        assert first.clock() == (0, 0) and not first.is_modified()
        second.set_clock(90, 5)
        assert second.is_modified() and second.is_clock_modified()
        out = tmp_path / "out.jsm"
        jsm.save(str(out))
        assert not jsm.is_modified()
        reloaded = JsmCardGameFile(str(out))
        assert [player.clock() for player in reloaded.players] == [(0, 0), (90, 5)]
        assert [player.params[PARAM_DECK_ID].value for player in reloaded.players] == [7, 9]
        _, words = decode(out.read_bytes())
        block = reloaded.players[1].clock_block_offset
        assert words[(block - reloaded.offset_script) // 4:][:4] == [
            jsmedit.encode(OPCODE_PSHN_L, 90), jsmedit.encode(OPCODE_POPM_W, VAR_CRONOS_CLOCK_SECONDS),
            jsmedit.encode(OPCODE_PSHN_L, 5), jsmedit.encode(OPCODE_POPM_B, VAR_CRONOS_CLOCK_INCREMENT)]

        # change in place, then remove: back to the original bytes
        reloaded.players[1].set_clock(600, 0)
        changed = tmp_path / "changed.jsm"
        reloaded.save(str(changed))
        assert len(changed.read_bytes()) == len(out.read_bytes())
        again = JsmCardGameFile(str(changed))
        assert again.players[1].clock() == (600, 0)
        again.players[1].set_clock(0, 9)
        assert again.players[1].clock() == (0, 0)
        removed = tmp_path / "removed.jsm"
        again.save(str(removed))
        assert removed.read_bytes() == (tmp_path / "test.jsm").read_bytes()

    def test_saving_twice_writes_the_same_file(self, jsm, tmp_path):
        jsm.players[0].set_clock(30, 2)
        jsm.save(str(tmp_path / "a.jsm"))
        jsm.players[1].params[PARAM_DECK_ID].set_literal(12)
        jsm.save(str(tmp_path / "b.jsm"))
        reloaded = JsmCardGameFile(str(tmp_path / "b.jsm"))
        assert [player.clock() for player in reloaded.players] == [(30, 2), (0, 0)]
        assert reloaded.players[1].params[PARAM_DECK_ID].value == 12

    def test_restore_original(self, jsm):
        jsm.players[0].set_clock(30, 2)
        jsm.players[0].restore_original()
        assert not jsm.players[0].is_modified()

    def test_clock_text(self):
        assert clock_text(0, 5) == ""
        assert clock_text(90, 0) == "1:30"
        assert clock_text(3725, 12) == "62:05 +12s"


@pytest.mark.ff8data("extracted_files/field")
class TestRealFiles:

    def test_clock_on_every_card_player_round_trips(self, tmp_path):
        """A clock on every card player of every map: jumps still reach the same instructions (or the
        new block, for those aimed at the pushes), the scripts keep their starts, every player reads
        its clock back, and removing the clocks gives the original file byte for byte."""
        manager = CardGameFolderManager()
        manager.load_folder(str(FIELD_DIR))
        assert manager.nb_players() > 250
        nb_maps = 0
        for jsm_file in manager.jsm_files:
            original = bytes(jsm_file.data)
            entries, words = decode(original)
            for index, player in enumerate(jsm_file.players):
                player.set_clock(60 + index, index % 4)
            out = tmp_path / "clock.jsm"
            out.write_bytes(jsm_file.output_data())
            clocked = JsmCardGameFile(str(out))
            assert [player.clock() for player in clocked.players] == \
                   [(60 + index, index % 4) for index in range(len(jsm_file.players))], jsm_file.rel_path
            assert [[param.to_dword() for param in player.params] for player in clocked.players] == \
                   [[param.to_dword() for param in player.params] for player in jsm_file.players]

            # every original instruction moved by the number of blocks before it
            first_pushes = sorted((player.params[PARAM_DECK_ID].file_offset - jsm_file.offset_script) // 4
                                  for player in jsm_file.players)

            def moved(position):
                return position + 4 * sum(1 for push in first_pushes if push <= position)

            new_entries, new_words = decode(out.read_bytes())
            assert [entry & 0x7FFF for entry in new_entries] == [moved(entry & 0x7FFF) for entry in entries]
            new_targets = jump_targets(new_words)
            for source, target in jump_targets(words).items():
                want = moved(target) - 4 if target in first_pushes else moved(target)
                assert new_targets[moved(source)] == want, (jsm_file.rel_path, source)

            for player in clocked.players:
                player.set_clock(0, 0)
            assert clocked.output_data() == original, jsm_file.rel_path
            nb_maps += 1
        assert nb_maps == len(manager.jsm_files)
