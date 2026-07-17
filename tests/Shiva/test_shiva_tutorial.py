"""TutorialManager tests against the real mngrp.bin/mngrphd.bin (migrated from Trepies).

The tutorial editor now works on the shared MngrpManager: Shiva keeps the sections no editor
touches byte for byte (keep_unowned_sections_raw), and the tutorial slots round-trip exactly,
so a no-edit save reproduces both files and a same-size edit touches only its own slots.

Needs the real files, skipped otherwise (ff8data marker).
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from Shiva.mngrpsave import keep_unowned_sections_raw
from Shiva.ShivaTutorial.tutorialmanager import (TutorialManager, SCRIPT_SLOTS, MOCK_CHAR_SLOTS,
                                                 MOCK_GF_SLOTS, NB_CHARACTER_RECORDS, NB_GF_RECORDS)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"
MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"

pytestmark = pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


def _load(game_data):
    mngrp_manager = MngrpManager(game_data)
    mngrp_manager.load_file(str(MNGRPHD), str(MNGRP))
    return mngrp_manager, TutorialManager.from_mngrp(game_data, mngrp_manager.mngrp)


def _save(mngrp_manager, tutorial, out_mngrp, out_mngrphd):
    """Save like Shiva does: freeze the unowned sections, write the tutorial slots, write once."""
    keep_unowned_sections_raw(mngrp_manager.game_data, mngrp_manager.mngrp, tutorial.owned_section_ids())
    tutorial.save_to_mngrp(mngrp_manager.mngrp)
    mngrp_manager.save_file(str(out_mngrp), str(out_mngrphd))


def _read_raw_sections(mngrphd_bytes, mngrp_bytes):
    """raw slot -> section bytes, read like the exe (independent of the manager)."""
    sections = {}
    for raw_slot in range(len(mngrphd_bytes) // 8):
        seek, size = struct.unpack_from("<II", mngrphd_bytes, raw_slot * 8)
        if size == 0 or seek in (0, 0xFFFFFFFF):
            continue
        sections[raw_slot] = mngrp_bytes[seek - 1:seek - 1 + size]
    return sections


def test_load_parses_known_vanilla_values(game_data):
    _, tutorial = _load(game_data)
    assert sorted(tutorial.scripts) == sorted(SCRIPT_SLOTS)
    junction_ops = tutorial.scripts[168].ops
    assert [str(op) for op in junction_ops[:6]] == \
        ["SET_TEXT_X 192", "SET_TEXT_Y 104", "SET_TEXT_INDEX 0", "WAIT 60", "SHOW_TEXT", "WAIT_WINDOW_READY"]
    assert junction_ops[-1].opcode == 0xF  # END
    for slot in SCRIPT_SLOTS:
        assert tutorial.scripts[slot].ops[-1].opcode == 0xF
        assert not any(tutorial.scripts[slot].tail), "tail after END should be zero padding"

    for slot in MOCK_CHAR_SLOTS:
        records = tutorial.mock_char_files[slot].records
        assert len(records) == NB_CHARACTER_RECORDS
        squall = records[0]
        assert squall.name == "Squall"
        assert squall.current_hp == 9999
        assert squall.exists == 1

    for slot in MOCK_GF_SLOTS:
        records = tutorial.mock_gf_files[slot].records
        assert len(records) == NB_GF_RECORDS
        assert records[0].hp == 9999
    assert tutorial.mock_gf_files[177].records[0].name == "Quetcoatl"

    captions = tutorial.get_captions(168)
    assert captions and captions[0] == "Junction Tutorial"


def test_unmodified_save_is_byte_exact(game_data, tmp_path):
    mngrp_manager, tutorial = _load(game_data)
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    _save(mngrp_manager, tutorial, out_mngrp, out_mngrphd)
    assert out_mngrp.read_bytes() == MNGRP.read_bytes()
    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()


def test_script_text_roundtrip_is_byte_exact(game_data):
    _, tutorial = _load(game_data)
    for slot in SCRIPT_SLOTS:
        script = tutorial.scripts[slot]
        before = script.to_bytes()
        script.set_ops_from_text(script.to_text(tutorial.get_captions(slot)))
        assert script.to_bytes() == before, f"script raw {slot} changed through text round-trip"


def test_json_roundtrip_is_byte_exact(game_data, tmp_path):
    _, source = _load(game_data)
    exported = source.to_dict()
    mngrp_manager, other = _load(game_data)
    other.from_dict(exported)
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    _save(mngrp_manager, other, out_mngrp, out_mngrphd)
    assert out_mngrp.read_bytes() == MNGRP.read_bytes()
    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()


def test_same_size_edit_only_touches_its_slot(game_data, tmp_path):
    mngrp_manager, tutorial = _load(game_data)
    script = tutorial.scripts[173]
    wait_op = next(op for op in script.ops if op.name == "WAIT")
    wait_op.operand = 120
    tutorial.mock_char_files[176].records[0].stat_str = 99
    tutorial.mock_gf_files[177].records[2].exp = 123456

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    _save(mngrp_manager, tutorial, out_mngrp, out_mngrphd)

    assert out_mngrphd.read_bytes() == MNGRPHD.read_bytes()  # header untouched (same-size edit)
    original_sections = _read_raw_sections(MNGRPHD.read_bytes(), MNGRP.read_bytes())
    new_sections = _read_raw_sections(out_mngrphd.read_bytes(), out_mngrp.read_bytes())
    changed = [slot for slot in original_sections if original_sections[slot] != new_sections[slot]]
    assert sorted(changed) == [173, 176, 177]

    _, reloaded = _load_from(game_data, out_mngrphd, out_mngrp)
    assert next(op for op in reloaded.scripts[173].ops if op.name == "WAIT").operand == 120
    assert reloaded.mock_char_files[176].records[0].stat_str == 99
    assert reloaded.mock_gf_files[177].records[2].exp == 123456


def _load_from(game_data, mngrphd_path, mngrp_path):
    mngrp_manager = MngrpManager(game_data)
    mngrp_manager.load_file(str(mngrphd_path), str(mngrp_path))
    return mngrp_manager, TutorialManager.from_mngrp(game_data, mngrp_manager.mngrp)
