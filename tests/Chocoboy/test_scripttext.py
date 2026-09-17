"""Tests for writing a script section out as text and reading it back.

The point of the format is that a jump survives editing: it is written as a label, so inserting
or deleting instructions anywhere cannot send it to the wrong place the way a raw byte offset
does. Most of these tests are about that.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Chocoboy.chocoboymanager import ChocoboyManager, SECTION_NAME
from Chocoboy.scripttext import section_to_text, text_to_section
from Chocoboy.wmsetscript import ScriptSection

from tests.Chocoboy.test_chocoboymanager import build_script_section

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
WMSET_REL = "extracted_files/world/dat/wmsetus.obj"
WMSET = PROJECT_ROOT / WMSET_REL


@pytest.fixture
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_sysfnt_data()
    return data


def a_section():
    """Two scripts, the first jumping into the second."""
    return ScriptSection(36, build_script_section(
        [0, 3],
        [(0xFF0E, 24, 0), (0xFF36,), (0xFF16,), (0xFF36,), (0xFF16,)]))


def import_into(section, text):
    result = text_to_section(text)
    if result.ok:
        section.replace_scripts(result.scripts, result.names, result.trailing_comments)
    return result


def script_lines(text, entry):
    """The lines of one script, stripped, without its marker."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.startswith(f"=== Script #{entry} "))
    out = []
    for line in lines[start + 1:]:
        if line.startswith("=== Script #"):
            break
        if line.strip():
            out.append(line.strip())
    return out


# --- what the text looks like -----------------------------------------------------------------

def test_a_jump_is_written_as_a_label_not_an_offset():
    text = section_to_text(a_section(), "Global event scripts")
    assert script_lines(text, 0) == ["GOTO label_1", "CONSUME_INPUT", "RETURN"]
    assert script_lines(text, 1) == ["label_1:", "CONSUME_INPUT", "RETURN"]


def test_a_word_parameter_is_written_as_the_one_value_the_game_reads():
    section = ScriptSection(36, build_script_section(
        [0], [(0xFF25, 14, 0), (0xFF27, 61, 1), (0xFF16,)]))
    text = section_to_text(section, "Global event scripts")
    # CHECK_WORLD_MAP_STATE takes a uint16, CHECK_BIT_FLAG takes two separate bytes
    assert script_lines(text, 0) == ["CHECK_WORLD_MAP_STATE 14", "CHECK_BIT_FLAG 61, 1", "RETURN"]


def test_a_script_name_and_its_comments_come_back():
    section = a_section()
    text = """=== Script #0 (Closes the Obel Lake window) ===
; the interesting part
GOTO label_1   ; and away
RETURN
; trailing thought

=== Script #1 ===
label_1:
RETURN
"""
    assert import_into(section, text).ok
    assert section.script_names[0] == "Closes the Obel Lake window"
    assert section.instructions[0].comments == ["; the interesting part"]
    assert section.instructions[0].trailing == "; and away"
    assert section.script_trailing_comments[0] == ["; trailing thought"]
    assert "=== Script #0 (Closes the Obel Lake window) ===" in section_to_text(section, "x")


# --- what the labels are for --------------------------------------------------------------------

def test_inserting_an_instruction_before_a_label_moves_the_jump_with_it():
    section = a_section()
    text = """=== Script #0 ===
GOTO label_1
RETURN

=== Script #1 ===
CONSUME_INPUT
CONSUME_INPUT
label_1:
RETURN
"""
    assert import_into(section, text).ok
    target = section.index_at_offset(section.instructions[0].word)
    assert section.instructions[target].name == "RETURN"
    assert section.dangling_gotos() == []


def test_a_jump_into_a_script_that_lost_its_first_lines_still_lands_right():
    section = a_section()
    text = """=== Script #0 ===
GOTO label_1
RETURN

=== Script #1 ===
label_1:
RETURN
"""
    assert import_into(section, text).ok
    assert section.entry_offsets == [12, 20]
    assert section.instructions[section.index_at_offset(section.instructions[0].word)].name == "RETURN"


def test_a_script_can_be_added_which_moves_every_offset():
    section = a_section()
    text = """=== Script #0 ===
GOTO label_1
RETURN

=== Script #1 ===
label_1:
RETURN

=== Script #2 (brand new) ===
CONSUME_INPUT
RETURN
"""
    assert import_into(section, text).ok
    assert len(section.entry_offsets) == 3
    assert section.table_size == 16  # three offsets plus the sentinel: every script moved 4 bytes
    assert section.entry_offsets[0] == 16
    assert section.instructions[section.index_at_offset(section.instructions[0].word)].name == "RETURN"
    assert section.to_bytes()[:4] == b"\x10\x00\x00\x00"


# --- what it refuses to do ----------------------------------------------------------------------

def test_a_jump_to_a_label_that_does_not_exist_changes_nothing():
    section = a_section()
    before = section.to_bytes()
    result = import_into(section, "=== Script #0 ===\nGOTO nowhere\nRETURN\n")
    assert not result.ok
    assert 'no label called "nowhere"' in result.errors[0]
    assert section.to_bytes() == before


def test_an_unknown_instruction_changes_nothing():
    section = a_section()
    before = section.to_bytes()
    result = import_into(section, "=== Script #0 ===\nJUMP_TO_THE_MOON 1\nRETURN\n")
    assert not result.ok
    assert "JUMP_TO_THE_MOON" in result.errors[0]
    assert section.to_bytes() == before


def test_a_file_with_no_markers_changes_nothing():
    section = a_section()
    result = import_into(section, "RETURN\n")
    assert not result.ok
    assert "=== Script #N ===" in result.errors[0]


def test_the_other_editors_dialect_is_refused_rather_than_read_wrong():
    """Its ELSE is this tool's THEN. Reading its files as if they were this tool's would put the
    actions of every branch in the wrong place, silently, so they are turned away instead."""
    section = a_section()
    result = import_into(section, "=== Script #0 ===\nIFBLOCK\nELSE\nRETURN\n")
    assert not result.ok
    assert "IFBLOCK" in result.errors[0]


def test_bytes_this_tool_does_not_know_survive_the_trip():
    section = ScriptSection(36, build_script_section([0], [(0x1234, 9, 8), (0xFF16,)]))
    text = section_to_text(section, "Global event scripts")
    assert "RAW 0x1234 9, 8" in text
    assert import_into(section, text).ok
    assert (section.instructions[0].code, section.instructions[0].param1) == (0x1234, 9)


# --- the real game file ---------------------------------------------------------------------

def _scripts_as_tuples(section):
    """Every script as opcode tuples, with each jump as the (script, line) it lands on.

    Comparing these says whether two layouts of a section mean the same thing, which is the real
    question after a round trip: section 36 stores two scripts out of table order, so writing it
    back out in order moves bytes around without changing a single instruction.
    """
    ranges = [section.script_range(entry) for entry in range(len(section.entry_offsets))]
    out = []
    for start, end in ranges:
        script = []
        for index in range(start, end):
            instruction = section.instructions[index]
            if instruction.code == 0xFF0E:
                target = section.index_at_offset(instruction.word)
                owner = next((entry for entry, (first, last) in enumerate(ranges)
                              if first <= target < last), None)
                script.append(("jump", owner, None if owner is None else target - ranges[owner][0]))
            else:
                script.append((instruction.code, instruction.param1, instruction.param2))
        out.append(script)
    return out


@pytest.mark.ff8data(WMSET_REL)
@pytest.mark.parametrize("index", [7, 9, 11, 36])
def test_every_real_section_survives_a_text_round_trip(game_data, index):
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    section = manager.script_sections[index]
    before = _scripts_as_tuples(section)

    result = text_to_section(section_to_text(section, SECTION_NAME[index]))
    assert result.ok, result.errors
    section.replace_scripts(result.scripts, result.names, result.trailing_comments)

    assert _scripts_as_tuples(section) == before


@pytest.mark.ff8data(WMSET_REL)
def test_a_section_stored_in_table_order_comes_back_byte_for_byte(game_data):
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    for index in (7, 9, 11):  # section 36 is the one stored out of order
        section = manager.script_sections[index]
        before = section.to_bytes()
        result = text_to_section(section_to_text(section, SECTION_NAME[index]))
        assert result.ok, result.errors
        section.replace_scripts(result.scripts, result.names, result.trailing_comments)
        assert section.to_bytes() == before, f"section {index}"


@pytest.mark.ff8data(WMSET_REL)
def test_check_battle_escaped_keeps_its_parameter(game_data):
    """The older notes say this opcode reads no parameter. It does - wm_scriptCheckCondition
    compares it like every other condition - and one script in the shipped file passes 1."""
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    section = manager.script_sections[36]
    with_parameter = [instruction for instruction in section.instructions
                      if instruction.code == 0xFF35 and instruction.word != 0]
    assert with_parameter, "expected a CHECK_BATTLE_ESCAPED with a non-zero parameter"

    result = text_to_section(section_to_text(section, SECTION_NAME[36]))
    assert result.ok, result.errors
    section.replace_scripts(result.scripts, result.names, result.trailing_comments)
    assert [instruction.word for instruction in section.instructions
            if instruction.code == 0xFF35 and instruction.word != 0] == \
           [instruction.word for instruction in with_parameter]
