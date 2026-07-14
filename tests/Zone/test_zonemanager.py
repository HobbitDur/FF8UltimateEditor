"""
Tests for Zone (mmag.bin magazine page editor).

mmag.bin is a headerless array of 68-byte page entries (69 in the English PC
release) sharing the MagPageEntry format with mmag2.bin (Moomba): window rect,
page picture quad, paper background, book text file, page texture, unlock block
and 4 picture + 4 text overlay slots.

A synthetic file with known entries covers the field mapping without the
original game files; the ff8data tests check the real file round-trips
byte-exactly and that the magazine map/name lookups match the retail content.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Zone.zonemanager import ZoneManager, TEXTURE_CATEGORIES, BOOK_TEXT_FIRST_RAW_FILE

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MMAG_PATH = PROJECT_ROOT / "extracted_files" / "menu" / "mmag.bin"
MNGRP_PATH = PROJECT_ROOT / "extracted_files" / "menu" / "mngrp.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_sysfnt_data()
    return gd


@pytest.fixture
def manager(game_data):
    return ZoneManager(game_data)


def _synthetic_entry():
    """One 68-byte entry with distinct, recognizable values in every field."""
    data = bytearray(68)
    data[0x00:0x02] = (24).to_bytes(2, "little")     # window x
    data[0x02:0x04] = (8).to_bytes(2, "little")      # window y
    data[0x04:0x06] = (336).to_bytes(2, "little")    # window width
    data[0x06:0x08] = (184).to_bytes(2, "little")    # window height
    data[0x08:0x0A] = (13).to_bytes(2, "little")     # picture x
    data[0x0A:0x0C] = (84).to_bytes(2, "little")     # picture y
    data[0x0C:0x0E] = (152).to_bytes(2, "little")    # picture width
    data[0x0E:0x10] = (96).to_bytes(2, "little")     # picture height
    data[0x10] = 115                                 # scale x
    data[0x11] = 35                                  # scale y
    data[0x12] = 7                                   # scale z
    data[0x13] = 0x12                                # paper E1
    data[0x14] = 0xC0                                # paper E2
    data[0x15] = 2                                   # text file index
    data[0x16] = 5                                   # texture category
    data[0x17] = 3                                   # texture page
    data[0x18] = 6                                   # weapon index (Lion Heart)
    data[0x19] = 16                                  # weapon line spacing
    data[0x1A] = 4                                   # duel move (Dolphin Blow)
    data[0x1B] = 5                                   # angelo move (Angelo Strike)
    data[0x1C:0x1E] = (169).to_bytes(2, "little")    # weapon list x
    data[0x1E] = 102                                 # weapon list y
    data[0x1F] = 160                                 # weapon quantity column x
    data[0x20:0x22] = (150).to_bytes(2, "little")    # duel combo x
    data[0x22] = 126                                 # duel combo y
    data[0x23] = 1                                   # footer flag
    # Picture overlay slot 0 used, others unused
    data[0x24:0x28] = (25).to_bytes(2, "little") + bytes([84, 9])
    data[0x28:0x34] = bytes([0, 0, 0, 0xFF]) * 3
    # Text overlay slots 0-1 used, others unused
    data[0x34:0x38] = (13).to_bytes(2, "little") + bytes([6, 1])
    data[0x38:0x3C] = (13).to_bytes(2, "little") + bytes([22, 2])
    data[0x3C:0x44] = bytes([0, 0, 0, 0xFF]) * 2
    return bytes(data)


@pytest.fixture
def mmag_file(tmp_path):
    """A 2-entry synthetic mmag.bin (the synthetic entry + an all-0xFF-unlock blank)."""
    data = _synthetic_entry() + bytes(0x18) + bytes([0xFF] * 4) + bytes(0x08) + bytes([0xFF, 0, 0, 0xFF] * 8)
    file_path = tmp_path / "mmag.bin"
    file_path.write_bytes(data)
    return file_path


class TestZoneManagerSynthetic:
    def test_load_rejects_bad_size(self, manager, tmp_path):
        bad = tmp_path / "bad.bin"
        bad.write_bytes(bytes(67))
        with pytest.raises(ValueError):
            manager.load_file(str(bad))

    def test_field_mapping(self, manager, mmag_file):
        manager.load_file(str(mmag_file))
        entry = manager.entries[0]
        assert (entry.window_x, entry.window_y) == (24, 8)
        assert (entry.window_width, entry.window_height) == (336, 184)
        assert (entry.picture_x, entry.picture_y) == (13, 84)
        assert (entry.picture_width, entry.picture_height) == (152, 96)
        assert (entry.picture_scale_x, entry.picture_scale_y, entry.picture_scale_z) == (115, 35, 7)
        assert (entry.paper_e1, entry.paper_e2) == (0x12, 0xC0)
        assert entry.text_file_index == 2
        assert (entry.texture_category, entry.texture_page) == (5, 3)
        assert entry.weapon_id == 6
        assert entry.weapon_line_spacing == 16
        assert entry.duel_move_id == 4
        assert entry.angelo_move_id == 5
        assert (entry.weapon_list_x, entry.weapon_list_y) == (169, 102)
        assert entry.weapon_quantity_x_offset == 160
        assert (entry.duel_combo_x, entry.duel_combo_y) == (150, 126)
        assert entry.footer_flag == 1
        assert entry.picture_overlays[0].used
        assert (entry.picture_overlays[0].x, entry.picture_overlays[0].y,
                entry.picture_overlays[0].id) == (25, 84, 9)
        assert all(not slot.used for slot in entry.picture_overlays[1:])
        assert [slot.id for slot in entry.text_overlays] == [1, 2, 0xFF, 0xFF]

    def test_save_without_modification_is_identical(self, manager, mmag_file, tmp_path):
        manager.load_file(str(mmag_file))
        saved = tmp_path / "saved_mmag.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == mmag_file.read_bytes()

    def test_modify_and_reload(self, manager, game_data, mmag_file):
        manager.load_file(str(mmag_file))
        manager.entries[0].weapon_id = 23  # Shooting Star
        manager.entries[0].text_overlays[2].x = 100
        manager.entries[0].text_overlays[2].y = 50
        manager.entries[0].text_overlays[2].id = 7
        manager.save_file()

        reloaded = ZoneManager(game_data)
        reloaded.load_file(str(mmag_file))
        assert reloaded.entries[0].weapon_id == 23
        overlay = reloaded.entries[0].text_overlays[2]
        assert (overlay.x, overlay.y, overlay.id) == (100, 50, 7)

    def test_raw_file_resolution(self, manager, mmag_file):
        manager.load_file(str(mmag_file))
        entry = manager.entries[0]
        # text file 2 -> raw 89, texture category 5 (base 71) page 3 -> raw 74
        assert entry.book_text_raw_file == BOOK_TEXT_FIRST_RAW_FILE + 2
        assert entry.texture_raw_file == TEXTURE_CATEGORIES[5][1] + 3
        # A category outside the table uses the page directly
        entry.texture_category = 200
        entry.texture_page = 42
        assert entry.texture_raw_file == 42

    def test_name_lookups(self, manager):
        assert manager.get_weapon_name(6) == "Lion Heart"
        assert manager.get_weapon_name(0xFF) == "None"
        assert manager.get_duel_move_name(4) == "Dolphin Blow"
        assert manager.get_angelo_move_name(5) == "Angelo Strike"
        assert manager.get_texture_category_name(1) == "Combat King"

    def test_magazine_map(self, manager):
        assert manager.entry_name(0) == "Weapons Monthly 1st Issue 1/4"
        assert manager.entry_name(27) == "Weapons Monthly August Issue 4/4"
        assert manager.entry_name(28) == "Combat King 001"
        assert manager.entry_name(32) == "Combat King 005"
        assert manager.entry_name(33) == "Pet Pals Vol.1"
        assert manager.entry_name(39) == "Occult Fan I"
        assert manager.entry_name(43) == "Battle tutorial 1/8"
        assert manager.entry_name(51) == "Card rules 1/13"
        assert manager.entry_name(64) == "Card icon explanation 1/4"
        assert manager.entry_name(68) == "Empty terminator"


@pytest.mark.ff8data("extracted_files/menu/mmag.bin")
class TestZoneManagerRealFile:
    def test_roundtrip_byte_exact(self, manager, tmp_path):
        manager.load_file(str(MMAG_PATH))
        assert len(manager.entries) == 69
        saved = tmp_path / "mmag_out.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == MMAG_PATH.read_bytes()

    def test_retail_content_matches_magazine_map(self, manager):
        manager.load_file(str(MMAG_PATH))
        # Weapons Monthly 1st Issue: the four ultimate weapons, one per page
        ultimate_pages = [manager.get_weapon_name(manager.entries[i].weapon_id)
                          for i in range(4)]
        assert ultimate_pages == ["Lion Heart", "Shooting Star", "Exeter", "Strange Vision"]
        # Combat King 001-005 teach the five learnable Duel moves
        duel_moves = [manager.get_duel_move_name(manager.entries[i].duel_move_id)
                      for i in range(28, 33)]
        assert duel_moves == ["Dolphin Blow", "Meteor Strike", "Meteor Barret",
                              "Different Beat", "My Final Heaven"]
        # Pet Pals Vol.1 teaches Angelo Strike
        assert manager.get_angelo_move_name(manager.entries[33].angelo_move_id) == "Angelo Strike"
        # The tutorial books never use the unlock block
        for index in range(43, 68):
            entry = manager.entries[index]
            assert (entry.weapon_id, entry.duel_move_id, entry.angelo_move_id) == \
                (0xFF, 0xFF, 0xFF)
        # Battle tutorial pages read text file 1 (raw 88), card rules file 2 (raw 89)
        assert manager.entries[43].book_text_raw_file == 88
        assert manager.entries[51].book_text_raw_file == 89


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
class TestZoneManagerMngrpPreview:
    def test_overlay_text_resolution(self, manager):
        manager.load_file(str(MMAG_PATH))
        assert not manager.mngrp_loaded
        manager.load_mngrp(str(MNGRP_PATH))
        assert manager.mngrp_loaded
        entry = manager.entries[0]
        titles = [manager.get_overlay_text(entry, overlay)
                  for overlay in entry.text_overlays if overlay.used]
        assert any("Weapons Monthly" in title for title in titles)
        # Unused slots resolve to an empty string
        assert manager.get_overlay_text(entry, entry.text_overlays[3]) == ""
