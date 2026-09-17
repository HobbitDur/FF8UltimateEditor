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
    section = ScriptSection(36, build_script_section(
        [0],
        [(0xFF01,), (0xFF27, 5, 1), (0xFF04,), (0xFF0A,), (0xFF20, 64, 0), (0xFF0B,),
         (0xFF28, 5, 0), (0xFF05,), (0xFF0D,), (0xFF28, 5, 1), (0xFF05,), (0xFF05,), (0xFF16,)]))
    assert pseudo_code_lines(section, 0) == [
        "if",
        "    CHECK_BIT_FLAG 5, 1",
        "always then",
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
