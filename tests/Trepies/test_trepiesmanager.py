"""TrepiesManager tests against the real mngrp.bin/mngrphd.bin.

The manager patches raw mngrphd slots in place, so unlike the ShumiTranslator
save path a load/save round-trip must be BYTE-exact, not just semantically
identical. Needs the real files, skipped otherwise (ff8data marker).
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from Trepies.trepiesmanager import (TrepiesManager, DemoScriptOp, SCRIPT_SLOTS, MOCK_CHAR_SLOTS,
                                    MOCK_GF_SLOTS, DEMO_INFO, SECTOR_SIZE,
                                    NB_CHARACTER_RECORDS, NB_GF_RECORDS,
                                    CHARACTER_RECORD_SIZE, GF_RECORD_SIZE)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"
MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"

pytestmark = pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


@pytest.fixture()
def manager(game_data):
    trepies_manager = TrepiesManager(game_data)
    trepies_manager.load_file(str(MNGRPHD), str(MNGRP))
    return trepies_manager


def _read_raw_sections(mngrphd_bytes, mngrp_bytes):
    """raw slot -> section bytes, read like the exe (independent of the manager)."""
    sections = {}
    for raw_slot in range(len(mngrphd_bytes) // 8):
        seek, size = struct.unpack_from("<II", mngrphd_bytes, raw_slot * 8)
        if size == 0 or seek in (0, 0xFFFFFFFF):
            continue
        sections[raw_slot] = mngrp_bytes[seek - 1:seek - 1 + size]
    return sections


def test_load_parses_known_vanilla_values(manager):
    assert sorted(manager.scripts) == sorted(SCRIPT_SLOTS)
    # Start of the Junction demo script (wiki example, verified in game files)
    junction_ops = manager.scripts[168].ops
    assert [str(op) for op in junction_ops[:6]] == \
        ["SET_TEXT_X 192", "SET_TEXT_Y 104", "SET_TEXT_INDEX 0", "WAIT 60", "SHOW_TEXT", "WAIT_WINDOW_READY"]
    assert junction_ops[-1].opcode == 0xF  # END
    for slot in SCRIPT_SLOTS:
        assert manager.scripts[slot].ops[-1].opcode == 0xF
        assert not any(manager.scripts[slot].tail), "tail after END should be zero padding"

    for slot in MOCK_CHAR_SLOTS:
        records = manager.mock_char_files[slot].records
        assert len(records) == NB_CHARACTER_RECORDS
        squall = records[0]
        assert squall.name == "Squall"
        assert squall.current_hp == 9999
        assert squall.exists == 1

    for slot in MOCK_GF_SLOTS:
        records = manager.mock_gf_files[slot].records
        assert len(records) == NB_GF_RECORDS
        assert records[0].hp == 9999
    # The development misspelling left in the file ("Quetcoatl"), overridden
    # by the real save's name in game
    assert manager.mock_gf_files[177].records[0].name == "Quetcoatl"

    # Caption preview resolves through the paired string section
    captions = manager.get_captions(168)
    assert captions and captions[0] == "Junction Tutorial"


def test_unmodified_save_is_byte_exact(manager, tmp_path):
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))
    assert out_mngrp.read_bytes() == MNGRP.read_bytes()
    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()


def test_script_text_roundtrip_is_byte_exact(manager):
    for slot in SCRIPT_SLOTS:
        script = manager.scripts[slot]
        before = script.to_bytes()
        script.set_ops_from_text(script.to_text(manager.get_captions(slot)))
        assert script.to_bytes() == before, f"script raw {slot} changed through text round-trip"


def test_json_roundtrip_is_byte_exact(manager, game_data, tmp_path):
    exported = manager.to_dict()
    other = TrepiesManager(game_data)
    other.load_file(str(MNGRPHD), str(MNGRP))
    other.from_dict(exported)
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    other.save_file(str(out_mngrp), str(out_mngrphd))
    assert out_mngrp.read_bytes() == MNGRP.read_bytes()
    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()


def test_same_size_edit_only_touches_its_slot(manager, game_data, tmp_path):
    script = manager.scripts[173]
    wait_op = next(op for op in script.ops if op.name == "WAIT")
    wait_op.operand = 120
    squall = manager.mock_char_files[176].records[0]
    squall.stat_str = 99
    gf = manager.mock_gf_files[177].records[2]
    gf.exp = 123456

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    # Header untouched, and only the three edited sections differ
    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()
    original_sections = _read_raw_sections(MNGRPHD.read_bytes(), MNGRP.read_bytes())
    new_sections = _read_raw_sections(out_mngrphd.read_bytes(), out_mngrp.read_bytes())
    assert sorted(original_sections) == sorted(new_sections)
    changed = [slot for slot in original_sections if original_sections[slot] != new_sections[slot]]
    assert sorted(changed) == [173, 176, 177]

    # And the edits read back
    reloaded = TrepiesManager(game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    assert next(op for op in reloaded.scripts[173].ops if op.name == "WAIT").operand == 120
    assert reloaded.mock_char_files[176].records[0].stat_str == 99
    assert reloaded.mock_gf_files[177].records[2].exp == 123456


def test_script_growth_relayouts_and_preserves_other_sections(manager, game_data, tmp_path):
    script = manager.scripts[174]
    end_op = script.ops.pop()
    # Grow well past the current sector so the section needs one more sector
    grow_count = (SECTOR_SIZE - len(script.to_bytes())) // 2 + 8
    script.ops.extend(DemoScriptOp(0x9, 1) for _ in range(grow_count))
    script.ops.append(end_op)
    expected_ops = [op.word for op in script.ops]

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    original_sections = _read_raw_sections(MNGRPHD.read_bytes(), MNGRP.read_bytes())
    new_sections = _read_raw_sections(out_mngrphd.read_bytes(), out_mngrp.read_bytes())
    assert sorted(original_sections) == sorted(new_sections), "valid raw slots changed"
    for slot in original_sections:
        if slot == 174:
            continue
        assert new_sections[slot] == original_sections[slot], f"raw slot {slot} content changed"
    assert len(new_sections[174]) == len(original_sections[174]) + SECTOR_SIZE

    # Layout stays game-loadable: 0x800-aligned, contiguous, in-bounds
    new_header = out_mngrphd.read_bytes()
    expected_offset = 0
    entries = sorted(((struct.unpack_from("<II", new_header, raw_slot * 8), raw_slot)
                      for raw_slot in range(len(new_header) // 8)
                      if struct.unpack_from("<II", new_header, raw_slot * 8)[1]
                      and struct.unpack_from("<II", new_header, raw_slot * 8)[0] not in (0, 0xFFFFFFFF)),
                     key=lambda entry: entry[0][0])
    for (seek, size), raw_slot in entries:
        assert seek & 1, f"raw slot {raw_slot}: uncompressed flag lost"
        assert seek - 1 == expected_offset, f"raw slot {raw_slot}: gap or overlap"
        assert size % SECTOR_SIZE == 0
        expected_offset = seek - 1 + size
    assert expected_offset == len(out_mngrp.read_bytes())

    # Invalid placeholder entries preserved byte-exactly
    original_header = MNGRPHD.read_bytes()
    original_valid = _read_raw_sections(original_header, MNGRP.read_bytes())
    for raw_slot in range(len(original_header) // 8):
        if raw_slot not in original_valid:
            assert new_header[raw_slot * 8:raw_slot * 8 + 8] == original_header[raw_slot * 8:raw_slot * 8 + 8]

    reloaded = TrepiesManager(game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    assert [op.word for op in reloaded.scripts[174].ops] == expected_ops


def test_gf_name_encode_roundtrip(manager, game_data, tmp_path):
    gf = manager.mock_gf_files[179].records[1]
    gf.name = "Shivette"
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))
    reloaded = TrepiesManager(game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    assert reloaded.mock_gf_files[179].records[1].name == "Shivette"
    with pytest.raises(ValueError):
        gf.name = "WayTooLongGFName"


def test_record_field_coverage_rebuilds_from_dict(manager, game_data):
    """to_dict/from_dict cover every byte of the records: applying a record's
    dict onto the SAME slot of the other variant makes the bytes identical."""
    char_a = manager.mock_char_files[176].records[3]
    char_b = manager.mock_char_files[178].records[3]
    assert char_a.to_bytes() != char_b.to_bytes()
    char_b.from_dict(char_a.to_dict())
    assert char_b.to_bytes() == char_a.to_bytes()

    gf_a = manager.mock_gf_files[177].records[5]
    gf_b = manager.mock_gf_files[179].records[5]
    gf_b.from_dict(gf_a.to_dict())
    assert gf_b.to_bytes() == gf_a.to_bytes()


def test_demo_info_pairs_are_present(manager):
    for script_slot, (name, caption_slot, char_slot, gf_slot) in DEMO_INFO.items():
        assert script_slot in manager.scripts
        assert char_slot in manager.mock_char_files
        assert gf_slot in manager.mock_gf_files
        assert manager.get_captions(script_slot), f"no captions decoded for {name} (raw {caption_slot})"
