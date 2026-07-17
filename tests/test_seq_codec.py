"""Tests for the IfritSeq-code language (FF8GameData/dat/sequencecodec.py).

The language's contract: every sequence can be shown as code, and that code parses back
to the exact same bytes. Errors carry the line number and say what is wrong, because the
code view is typed by hand.
"""
import contextlib
import io
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.sequencecodec import (sequence_to_code, code_to_sequence,
                                           SeqCodeError, generate_help_entries,
                                           generate_help_html, code_line_to_command)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


class TestBytesToCode:
    def test_a_small_sequence_reads_naturally(self, game_data):
        data = bytes([0x05, 0xA0, 0x12, 0xB9, 0x0A, 0xE6, 0xFB, 0xA2])
        code = sequence_to_code(game_data, data)
        assert code.splitlines() == [
            "anim(5)",
            "anim_async(18)",
            "wait(10)",
            "jump(-5)",
            "end_seq()",
        ]

    def test_value_ops_show_their_literal(self, game_data):
        # C1 xx = set_i8 signed, C0 xxxx = set_i16, C3 xx = set_var (hex)
        data = bytes([0xC1, 0xFE, 0xC0, 0xE8, 0x03, 0xC3, 0x11])
        code = sequence_to_code(game_data, data)
        assert code.splitlines() == ["set_i8(-2)", "set_i16(1000)", "set_var(0x11)"]

    def test_an_engine_no_op_is_kept_as_raw(self, game_data):
        assert sequence_to_code(game_data, bytes([0x87])) == "raw(0x87)"


class TestCodeToBytes:
    def test_comments_and_blank_lines_are_ignored(self, game_data):
        code = "# the idle stance\n\nanim(5)   # looping part\njump(-5)\n"
        assert code_to_sequence(game_data, code) == bytearray([0x05, 0xE6, 0xFB])

    def test_unknown_command_says_the_line(self, game_data):
        with pytest.raises(SeqCodeError) as error:
            code_to_sequence(game_data, "anim(5)\nfly_away(3)")
        assert error.value.line_number == 2
        assert "fly_away" in str(error.value)

    def test_wrong_argument_count_is_refused(self, game_data):
        with pytest.raises(SeqCodeError) as error:
            code_to_sequence(game_data, "wait(1, 2)")
        assert "1 argument" in str(error.value)

    def test_out_of_range_value_is_refused(self, game_data):
        with pytest.raises(SeqCodeError):
            code_to_sequence(game_data, "anim(200)")  # anim ids stop at 0x7F
        with pytest.raises(SeqCodeError):
            code_to_sequence(game_data, "jump(300)")  # int8 jump

    def test_inconsistent_variable_size_block_is_refused_with_the_expected_size(self, game_data):
        # hit_target flag 0x08 promises a bone byte that is not given
        with pytest.raises(SeqCodeError) as error:
            code_to_sequence(game_data, "hit_target(0x15, 0x08)")
        assert "would consume 3" in str(error.value)

    def test_garbage_line_is_refused(self, game_data):
        with pytest.raises(SeqCodeError) as error:
            code_to_sequence(game_data, "this is not code")
        assert error.value.line_number == 1


@pytest.mark.skipif(not BATTLE_PATH.is_dir(), reason="extracted battle files not available")
class TestCorpusRoundTrip:
    def test_every_real_sequence_round_trips_through_the_language(self, game_data):
        """bytes -> code -> bytes must be the identity on all of vanilla, otherwise the
        code view corrupts a file just by opening and re-saving it."""
        from FF8GameData.dat.monsteranalyser import MonsterAnalyser
        broken = []
        nb = 0
        for path in sorted(BATTLE_PATH.glob("*.dat")):
            if path.name.startswith("mag"):  # MonsterAnalyser does not terminate on these
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    monster = MonsterAnalyser(game_data)
                    monster.load_file_data(str(path), game_data)
                    monster.analyse_loaded_data(game_data)
            except Exception:
                continue
            section = getattr(monster, "seq_animation_data", None) or {}
            for sequence in section.get("seq_animation_data", []):
                data = bytes(sequence["data"])
                if not data:
                    continue
                nb += 1
                code = sequence_to_code(game_data, data)
                if code_to_sequence(game_data, code) != data:
                    broken.append(f"{path.name} seq {sequence['id']}")
        assert nb > 1000, f"corpus looks too small ({nb} sequences)"
        assert not broken, f"{len(broken)} sequences break the language round trip: {broken[:20]}"


class TestHelpPage:
    """The help page is generated from the same json + kind dispatch the parser uses, so
    it cannot claim a syntax the parser does not actually accept."""

    def test_every_entry_signature_is_accepted_by_the_parser(self, game_data):
        """The strongest guarantee: parse each signature's own example call. A raw-kind
        signature (name(0xNN, 0xNN, ...)) is documentation, not literal syntax, and is
        skipped; everything else must be real, parseable IfritSeq-code."""
        skipped = 0
        for entry in generate_help_entries(game_data):
            signature = entry["signature"]
            if "0xNN, 0xNN, ..." in signature:
                skipped += 1
                continue
            name = signature.split("(")[0]
            arg_text = signature[signature.index("(") + 1:signature.rindex(")")]
            if name in ("anim", "anim_async"):
                example = f"{name}(5)"
            elif "0xNN" in signature:
                example = f"{name}(0x11)"
            elif not arg_text:
                example = f"{name}()"
            else:
                nb_args = arg_text.count(",") + 1
                example = f"{name}({', '.join(['1'] * nb_args)})"
            command = code_line_to_command(game_data, example, 1)
            assert command is not None, f"{signature} -> {example} failed to parse"
        assert skipped < len(generate_help_entries(game_data)), \
            "at least some commands must have a concrete, checkable signature"

    def test_every_command_the_parser_accepts_is_documented(self, game_data):
        """The reverse direction: nothing the language understands is left undocumented."""
        from FF8GameData.dat.sequencecodec import _func_name_table
        from FF8GameData.dat.sequencevm import as_sequence_vm
        documented = {entry["signature"].split("(")[0] for entry in
                     generate_help_entries(game_data)}
        for name in _func_name_table(as_sequence_vm(game_data)):
            assert name in documented, f"{name} is accepted by the parser but undocumented"

    def test_help_html_contains_every_signature(self, game_data):
        html_text = generate_help_html(game_data)
        assert html_text.startswith("<h2>")
        for entry in generate_help_entries(game_data):
            assert entry["signature"] in html_text

    def test_help_html_mentions_the_escape_hatch_and_comments(self, game_data):
        html_text = generate_help_html(game_data)
        assert "raw(" in html_text
        assert "#" in html_text
