"""Tests for the Chocoboy manager and the world-map script bytecode it reads.

The synthetic tests build a tiny wmsetxx.obj in memory - a 48-offset header and 48 sections,
only the script and text ones filled in - so the offset fix-ups can be checked without the game
file. The real-file tests load ``extracted_files/world/dat/wmsetus.obj`` and are skipped when it
is missing (see the ff8data marker in the project-root conftest.py).
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from Chocoboy.chocoboymanager import ChocoboyManager, HEADER_SIZE, NB_SECTION
from Chocoboy.wmsetscript import Instruction, ScriptSection, to_pseudo_code

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
WMSET_REL = "extracted_files/world/dat/wmsetus.obj"
WMSET = PROJECT_ROOT / WMSET_REL


def build_script_section(entry_indices, instruction_list):
    """A script section whose entry points are given as instruction indices, not byte offsets."""
    table_size = 4 * (len(entry_indices) + 1)
    data = b"".join(struct.pack("<I", table_size + index * 4) for index in entry_indices)
    data += b"\x00\x00\x00\x00"
    return data + b"".join(Instruction(*values).to_bytes() for values in instruction_list)


def pseudo_code_lines(section, entry):
    """The pseudo-code without its offset column, which is what the shape assertions are about."""
    return [line[7:] for line in to_pseudo_code(section, entry).splitlines()]


def build_wmset(section_by_index):
    """A minimal but well-formed wmsetxx.obj: 48 offsets, a zero word, then the sections."""
    sections = [section_by_index.get(index, b"") for index in range(NB_SECTION)]
    header = bytearray()
    offset = HEADER_SIZE + 4  # the zero word closing the header, as the real file has
    for section in sections:
        header += struct.pack("<I", offset)
        offset += len(section)
    return bytes(header) + b"\x00\x00\x00\x00" + b"".join(sections)


@pytest.fixture
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_sysfnt_data()
    return data


# --- the bytecode container ------------------------------------------------------------------

def test_script_range_stops_at_the_return_not_at_the_next_entry():
    # Two entries, the second pointing at the RETURN the first script ends on
    section = ScriptSection(36, build_script_section(
        [0, 2],
        [(0xFF01,), (0xFF27, 5, 1), (0xFF16,), (0xFF16,)]))
    assert section.script_range(0) == (0, 3)  # entry 0 runs to its own RETURN
    assert section.script_range(1) == (2, 3)  # entry 1 shares that RETURN


def test_script_range_falls_back_to_the_next_entry_without_a_return():
    # Section 9 spawn lists end on END, not on RETURN
    section = ScriptSection(9, build_script_section(
        [0, 2],
        [(0xFF13, 1, 0), (0xFF05,), (0xFF13, 2, 0), (0xFF05,)]))
    assert section.script_range(0) == (0, 2)
    assert section.script_range(1) == (2, 4)


def test_insert_moves_the_entry_points_and_the_gotos_that_follow():
    # Script 0 jumps forward into script 1, script 1 jumps backwards into script 0
    section = ScriptSection(36, build_script_section(
        [0, 2],
        [(0xFF0E, 20, 0), (0xFF16,), (0xFF0E, 12, 0), (0xFF16,)]))
    assert section.entry_offsets == [12, 20]
    section.insert_instruction(2, Instruction(0xFF36))  # at the top of script 1

    # Script 1 still starts where it did, so the new instruction is the one it now starts on
    assert section.entry_offsets == [12, 20]
    assert section.script_range(1) == (2, 5)
    assert section.instructions[2].code == 0xFF36
    # Same for the jump into script 1. The jump backwards is before the change and never moves.
    assert section.instructions[0].word == 20
    assert section.instructions[3].word == 12


def test_insert_inside_a_script_pushes_everything_after_it_along():
    section = ScriptSection(36, build_script_section(
        [0, 3],
        [(0xFF0E, 24, 0), (0xFF36,), (0xFF16,), (0xFF16,)]))
    assert section.entry_offsets == [12, 24]
    section.insert_instruction(1, Instruction(0xFF36))  # inside script 0

    assert section.entry_offsets == [12, 28]  # script 1 moved 4 bytes further into the section
    assert section.instructions[0].word == 28  # and so did the jump aiming at it


def test_delete_moves_the_entry_points_and_the_gotos_that_follow():
    section = ScriptSection(36, build_script_section(
        [0, 2],
        [(0xFF0E, 24, 0), (0xFF16,), (0xFF36,), (0xFF0E, 12, 0), (0xFF16,)]))
    assert section.entry_offsets == [12, 20]
    section.delete_instruction(2)  # the first instruction of script 1

    assert section.entry_offsets == [12, 20]  # script 1 now starts on what followed it
    assert section.instructions[0].word == 20
    assert section.instructions[2].word == 12


def test_an_edit_never_leaves_a_dangling_goto():
    section = ScriptSection(36, build_script_section(
        [0], [(0xFF0E, 16, 0), (0xFF36,), (0xFF16,)]))
    assert section.dangling_gotos() == []
    section.insert_instruction(1, Instruction(0xFF36))
    assert section.dangling_gotos() == []
    assert section.instructions[0].word == 20  # still aiming at the same RETURN


def test_unknown_bytes_are_kept_as_they_are():
    section = ScriptSection(36, build_script_section([0], [(0x1234, 9, 8), (0xFF16,)]))
    assert section.instructions[0].name == "RAW_1234"
    assert section.to_bytes()[8:12] == struct.pack("<HBB", 0x1234, 9, 8)


def test_pseudo_code_nests_the_if_then_else_chain():
    """The script's own condition list reads "require" / "do", not "if" / "then".

    A failed condition there ends the script; a failed one inside an IF_BLOCK only picks the
    next branch. Printing both as "if" would hide the one difference that matters.
    """
    section = ScriptSection(36, build_script_section(
        [0],
        [(0xFF01,), (0xFF27, 5, 1), (0xFF04,), (0xFF0A,), (0xFF20, 64, 0), (0xFF0B,),
         (0xFF28, 5, 0), (0xFF05,), (0xFF0D,), (0xFF28, 5, 1), (0xFF05,), (0xFF05,), (0xFF16,)]))
    assert pseudo_code_lines(section, 0) == [
        "require",
        "    CHECK_BIT_FLAG 5, 1",
        "do",
        "    if",
        "        CHECK_BUTTON_INPUT 64",
        "    then",
        "        SET_BIT_FLAG 5, 0",
        "    end",
        "    else",
        "        SET_BIT_FLAG 5, 1",
        "    end",
        "end",
        "RETURN",
    ]


# --- the file --------------------------------------------------------------------------------

def test_synthetic_roundtrip_is_byte_exact(game_data, tmp_path):
    file_data = build_wmset({
        7: build_script_section([0], [(0xFF01,), (0xFF16,)]),
        9: build_script_section([0], [(0xFF13, 1, 0), (0xFF05,)]),
        11: build_script_section([0], [(0xFF15, 1, 0), (0xFF16,)]),
        36: build_script_section([0], [(0xFF1F, 0, 0), (0xFF16,)]),
        13: b"\x08\x00\x00\x00\x00\x00\x00\x00" + b"\x45\x67\x00\x00",
        31: b"\x08\x00\x00\x00\x00\x00\x00\x00" + b"\x45\x67\x00\x00",
        20: b"whatever raw bytes",
    })
    source = tmp_path / "wmsetus.obj"
    source.write_bytes(file_data)

    manager = ChocoboyManager(game_data)
    manager.load_file(str(source))
    destination = tmp_path / "out.obj"
    manager.save_file(str(destination))

    assert destination.read_bytes() == file_data


def test_adding_an_instruction_grows_the_file_and_moves_the_later_sections(game_data, tmp_path):
    file_data = build_wmset({
        7: build_script_section([0], [(0xFF01,), (0xFF16,)]),
        36: build_script_section([0], [(0xFF1F, 0, 0), (0xFF16,)]),
        37: b"a later section",
    })
    source = tmp_path / "wmsetus.obj"
    source.write_bytes(file_data)

    manager = ChocoboyManager(game_data)
    manager.load_file(str(source))
    manager.script_sections[7].insert_instruction(0, Instruction(0xFF36))
    destination = tmp_path / "out.obj"
    manager.save_file(str(destination))

    written = destination.read_bytes()
    assert len(written) == len(file_data) + 4
    offsets = [struct.unpack_from("<I", written, index * 4)[0] for index in range(NB_SECTION)]
    assert written[offsets[37]:offsets[37] + len(b"a later section")] == b"a later section"

    reloaded = ChocoboyManager(game_data)
    reloaded.load_file(str(destination))
    assert reloaded.script_sections[7].entry_offsets == [8]
    assert reloaded.script_sections[7].instructions[0].code == 0xFF36


def test_a_file_that_is_not_a_wmset_is_refused(game_data, tmp_path):
    bad = tmp_path / "not_a_wmset.obj"
    bad.write_bytes(b"\x00" * HEADER_SIZE)
    with pytest.raises(ValueError):
        ChocoboyManager(game_data).load_file(str(bad))


# --- the real game file ----------------------------------------------------------------------

@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_roundtrip_is_byte_exact(game_data, tmp_path):
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    destination = tmp_path / "out.obj"
    manager.save_file(str(destination))
    assert destination.read_bytes() == WMSET.read_bytes()


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_scripts_are_well_formed(game_data):
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))

    for index, section in manager.script_sections.items():
        assert section.entry_offsets, f"section {index} has no script"
        assert section.dangling_gotos() == [], f"section {index} has a GOTO pointing nowhere"
        for entry in range(len(section.entry_offsets)):
            start, end = section.script_range(entry)
            assert start < end, f"section {index} script #{entry} is empty"

    # Sections 7, 11 and 36 are walked until RETURN, section 9 is a plain action list
    for index in (7, 11, 36):
        section = manager.script_sections[index]
        for entry in range(len(section.entry_offsets)):
            _start, end = section.script_range(entry)
            assert section.instructions[end - 1].code == 0xFF16


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_stores_two_section_36_scripts_out_of_table_order(game_data):
    """Why a script has to be read up to its RETURN and not up to the next table offset: section
    36 stores two of its scripts earlier in the file than the script listed before them."""
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    offsets = manager.script_sections[36].entry_offsets

    out_of_order = [entry for entry in range(len(offsets) - 1) if offsets[entry] > offsets[entry + 1]]
    assert out_of_order, "expected a script stored before the one listed ahead of it"
    for entry in out_of_order:
        start, end = manager.script_sections[36].script_range(entry)
        assert start < end, "reading up to the next table offset would give a negative length here"


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_dialogs_are_reachable_from_the_scripts(game_data):
    manager = ChocoboyManager(game_data)
    manager.load_file(str(WMSET))
    lookup = manager.dialog_lookup()
    assert len(lookup) > 100
    assert manager.find_text_users(61), "dialog 61 (the Obel Lake shadow) should be opened by a script"


# --- the structure check -----------------------------------------------------------------------

def test_the_check_passes_a_well_formed_if_else_chain():
    section = ScriptSection(36, build_script_section(
        [0],
        [(0xFF01,), (0xFF27, 5, 1), (0xFF04,), (0xFF0A,), (0xFF20, 64, 0), (0xFF0B,),
         (0xFF28, 5, 0), (0xFF05,), (0xFF0D,), (0xFF28, 5, 1), (0xFF05,), (0xFF05,), (0xFF16,)]))
    assert section.problems(must_return=True) == []


def test_the_check_catches_a_script_that_does_not_end_on_return():
    section = ScriptSection(36, build_script_section([0], [(0xFF36,), (0xFF05,)]))
    problems = section.problems(must_return=True)
    assert len(problems) == 1
    assert "instead of RETURN" in problems[0][2]
    assert section.problems(must_return=False) == []  # section 9's lists end on END on purpose


def test_the_check_catches_a_branch_with_no_actions():
    """An IF_BLOCK whose conditions can pass but that has no THEN: the interpreter never gets to
    return an action pointer for it, so the branch silently does nothing."""
    section = ScriptSection(36, build_script_section(
        [0], [(0xFF0A,), (0xFF20, 64, 0), (0xFF05,), (0xFF16,)]))
    problems = section.problems(must_return=True)
    assert len(problems) == 1
    assert "no THEN" in problems[0][2]


def test_the_check_catches_an_else_with_no_chain_to_continue():
    section = ScriptSection(36, build_script_section([0], [(0xFF0D,), (0xFF36,), (0xFF16,)]))
    problems = section.problems(must_return=True)
    assert any("no IF_BLOCK chain" in message for _entry, _offset, message in problems)


def test_the_check_catches_a_jump_to_nowhere():
    section = ScriptSection(36, build_script_section([0], [(0xFF0E, 200, 0), (0xFF16,)]))
    problems = section.problems(must_return=True)
    assert len(problems) == 1
    assert "not the start of an instruction" in problems[0][2]


def test_an_end_closing_the_scripts_own_do_block_is_not_a_problem():
    """Not every END belongs to an IF_BLOCK: the outermost one closes the DO block, and some
    scripts have it while others just run into their RETURN."""
    section = ScriptSection(36, build_script_section(
        [0], [(0xFF01,), (0xFF27, 5, 1), (0xFF04,), (0xFF36,), (0xFF05,), (0xFF16,)]))
    assert section.problems(must_return=True) == []


# --- snapshots ---------------------------------------------------------------------------------

def test_a_snapshot_brings_back_the_names_and_comments_too():
    """They have nowhere to live in the .obj, so a snapshot of the bytes alone would lose them
    the first time an edit was undone past a text import."""
    section = ScriptSection(36, build_script_section([0], [(0xFF36,), (0xFF16,)]))
    section.script_names[0] = "The UFO"
    section.instructions[0].comments = ["; eats the button press"]
    section.instructions[0].trailing = "; here"
    section.script_trailing_comments[0] = ["; end of it"]
    snapshot = section.snapshot()

    section.script_names.clear()
    section.instructions[0].comments = []
    section.instructions[0].trailing = ""
    section.script_trailing_comments.clear()
    section.delete_instruction(0)

    section.restore_snapshot(snapshot)
    assert len(section.instructions) == 2
    assert section.script_names == {0: "The UFO"}
    assert section.instructions[0].comments == ["; eats the button press"]
    assert section.instructions[0].trailing == "; here"
    assert section.script_trailing_comments == {0: ["; end of it"]}


# --- whole scripts -----------------------------------------------------------------------------

def jumps_as_places(section):
    """Every jump as (script it is in, line in that script, script it lands in, line there).

    Byte offsets all move when a script is added, removed or reordered; what must not move is
    which instruction each jump lands on, and this is the shape of that.
    """
    ranges = [section.script_range(entry) for entry in range(len(section.entry_offsets))]
    places = []
    for entry, (start, end) in enumerate(ranges):
        for index in range(start, end):
            instruction = section.instructions[index]
            if instruction.code != 0xFF0E:
                continue
            target = section.index_at_offset(instruction.word)
            owner = next((other for other, (first, last) in enumerate(ranges)
                          if first <= target < last), None)
            places.append((entry, index - start, owner,
                           None if owner is None else target - ranges[owner][0]))
    return places


def a_jumping_section():
    """Three scripts; the middle one jumps to its own last line.

    The table holds 3 offsets plus the sentinel, so the instructions start at byte 16 and the
    jump's target, instruction 5, sits at byte 36.
    """
    return ScriptSection(36, build_script_section(
        [0, 2, 6],
        [(0xFF36,), (0xFF16,),
         (0xFF0E, 36, 0), (0xFF36,), (0xFF36,), (0xFF16,),
         (0xFF36,), (0xFF16,)]))


def test_adding_a_script_moves_every_other_one_and_keeps_the_jumps():
    section = a_jumping_section()
    before = jumps_as_places(section)
    section.add_script(0, [Instruction(0xFF01), Instruction(0xFF1E), Instruction(0xFF16)])

    assert len(section.entry_offsets) == 4
    assert section.table_size == 20  # one more offset: every script moved 4 bytes further on
    # The jump was in script 1 and is now in script 2, still landing on the same line of it
    assert [(entry - 1, line, owner - 1, target)
            for entry, line, owner, target in jumps_as_places(section)] == before
    assert section.dangling_gotos() == []


def test_a_duplicated_script_jumps_inside_itself_not_into_the_original():
    section = a_jumping_section()
    section.duplicate_script(1)

    assert len(section.entry_offsets) == 4
    places = jumps_as_places(section)
    assert (1, 0, 1, 3) in places, "the original still jumps to its own last line"
    assert (2, 0, 2, 3) in places, "and so does the copy, into the copy"


def test_removing_a_script_renumbers_the_rest_and_keeps_the_jumps():
    section = a_jumping_section()
    section.remove_script(0)

    assert len(section.entry_offsets) == 2
    assert jumps_as_places(section) == [(0, 0, 0, 3)]
    assert section.dangling_gotos() == []


def test_moving_a_script_changes_which_one_answers_first():
    """The order of the table is what decides which script runs in sections 7 and 11, so moving
    one is a real edit, not a cosmetic one."""
    section = a_jumping_section()
    section.move_script(2, 0)

    assert len(section.entry_offsets) == 3
    assert jumps_as_places(section) == [(2, 0, 2, 3)]  # the jumping script is now the last
    assert section.dangling_gotos() == []


def test_the_names_follow_their_scripts_when_one_moves():
    section = a_jumping_section()
    section.script_names = {0: "first", 1: "jumper", 2: "last"}
    section.move_script(0, 2)
    assert section.script_names == {2: "first", 0: "jumper", 1: "last"}


def test_a_section_whose_scripts_leave_a_gap_says_so():
    """Rebuilding from a list of scripts would drop instructions belonging to none of them."""
    section = ScriptSection(36, build_script_section(
        [0], [(0xFF16,), (0xFF36,), (0xFF16,)]))  # the last two lines belong to no script
    assert not section.scripts_cover_everything()
    assert a_jumping_section().scripts_cover_everything()
