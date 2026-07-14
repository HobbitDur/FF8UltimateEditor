"""Real-file round-trip tests for Moomba (menu/mmag2.bin, Chocobo World screen pages).

Loads the original game mmag2.bin from extracted_files/ and checks that load + save is
byte-for-byte lossless, that the documented retail values are parsed, and that the text
overlay strings resolve against mngrp.bin raw file 90. Needs the real files, skipped
otherwise (ff8data marker).
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Moomba.moombamanager import MoombaManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MMAG2_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mmag2.bin"
MMAG_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mmag.bin"
MNGRP_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mngrp.bin"
MNGRPHD_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mngrphd.bin"


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


@pytest.mark.ff8data("extracted_files/menu/mmag2.bin")
def test_real_mmag2_bin_roundtrip_is_lossless(game_data, tmp_path):
    manager = MoombaManager(game_data)
    manager.load_file(str(MMAG2_BIN))
    assert len(manager.entries) == MoombaManager.NB_ENTRIES

    out = tmp_path / "mmag2.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == MMAG2_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mmag.bin")
def test_real_mmag_bin_roundtrip_is_lossless_too(game_data, tmp_path):
    """mmag.bin shares the 68-byte entry format (69 entries in the EN release)."""
    manager = MoombaManager(game_data)
    manager.load_file(str(MMAG_BIN))
    assert len(manager.entries) == 69

    out = tmp_path / "mmag.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == MMAG_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mmag2.bin")
def test_real_mmag2_bin_documented_values(game_data):
    manager = MoombaManager(game_data)
    manager.load_file(str(MMAG2_BIN))
    for entry in manager.entries:
        # All Chocobo World pages use texture category 6 (raw file 180 + page)
        assert entry.texture_category == MoombaManager.TEXTURE_CATEGORY
        # Story slides (0-2) use page 0 (raw 180), the manual (3-11) page 1 (raw 181)
    for entry in manager.entries[:3]:
        assert entry.texture_page == 0
    for entry in manager.entries[3:]:
        assert entry.texture_page == 1
    # The retail picture overlay sprite ids all belong to the documented 58-76 SP2 range
    sprite_ids = [slot.id for entry in manager.entries
                  for slot in entry.picture_overlays if not slot.unused]
    assert sprite_ids
    assert all(MoombaManager.SP2_SPRITE_FIRST <= sprite_id <= MoombaManager.SP2_SPRITE_LAST
               for sprite_id in sprite_ids)
    # Text overlay ids cover story strings 0-4 and manual strings 5-14 of raw file 90
    text_ids = sorted({slot.id for entry in manager.entries
                       for slot in entry.text_overlays if not slot.unused})
    assert text_ids == list(range(15))


@pytest.mark.ff8data("extracted_files/menu/mmag2.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_raw90_text_preview(game_data):
    manager = MoombaManager(game_data)
    manager.load_file(str(MMAG2_BIN))
    nb_strings = manager.load_mngrp(str(MNGRP_BIN), str(MNGRPHD_BIN))
    assert nb_strings == 15
    # Story slide 1 text
    assert "treasure hunting" in manager.get_overlay_text(0)
    # Manual page 1/8 title
    assert "What is Solo-RPG" in manager.get_overlay_text(5)
    # Every text overlay of the retail file resolves to a non-empty string
    for entry in manager.entries:
        for slot in entry.text_overlays:
            if not slot.unused:
                text = manager.get_overlay_text(slot.id)
                assert text and "not found" not in text


@pytest.mark.ff8data("extracted_files/menu/mmag2.bin")
def test_real_mmag2_bin_edit_persists(game_data, tmp_path):
    manager = MoombaManager(game_data)
    manager.load_file(str(MMAG2_BIN))

    manager.entries[0].picture_overlays[0].id = 60
    manager.entries[0].text_overlays[0].x = 100
    out = tmp_path / "mmag2.bin"
    manager.save_file(str(out))

    reloaded = MoombaManager(game_data)
    reloaded.load_file(str(out))
    assert reloaded.entries[0].picture_overlays[0].id == 60
    assert reloaded.entries[0].text_overlays[0].x == 100
    # Only those two bytes differ from the original (sprite id 58->60 at 0x27,
    # text overlay X 147->100 low byte at 0x34; the high byte stays 0)
    original = MMAG2_BIN.read_bytes()
    rebuilt = out.read_bytes()
    diff_offsets = [i for i in range(len(original)) if original[i] != rebuilt[i]]
    assert diff_offsets == [0x27, 0x34]
