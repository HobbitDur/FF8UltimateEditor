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
KERNEL_PATH = PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"
MWEPON_PATH = PROJECT_ROOT / "extracted_files" / "menu" / "mwepon.bin"


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
        assert (entry.picture_tint_r, entry.picture_tint_g, entry.picture_tint_b) == (115, 35, 7)
        assert (entry.paper_e1, entry.paper_e2) == (0x12, 0xC0)
        assert entry.text_file_index == 2
        assert (entry.texture_category, entry.texture_page) == (5, 3)
        assert entry.weapon_index == 6
        assert entry.weapon_line_spacing == 16
        assert entry.duel_move_id == 4
        assert entry.angelo_move_id == 5
        assert (entry.weapon_list_x, entry.weapon_list_y) == (169, 102)
        assert entry.weapon_quantity_column_x == 160
        assert (entry.duel_combo_x, entry.duel_combo_y) == (150, 126)
        assert entry.footer_flag == 1
        assert not entry.picture_overlays[0].unused
        assert (entry.picture_overlays[0].x, entry.picture_overlays[0].y,
                entry.picture_overlays[0].id) == (25, 84, 9)
        assert all(slot.unused for slot in entry.picture_overlays[1:])
        assert [slot.id for slot in entry.text_overlays] == [1, 2, 0xFF, 0xFF]

    def test_save_without_modification_is_identical(self, manager, mmag_file, tmp_path):
        manager.load_file(str(mmag_file))
        saved = tmp_path / "saved_mmag.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == mmag_file.read_bytes()

    def test_modify_and_reload(self, manager, game_data, mmag_file):
        manager.load_file(str(mmag_file))
        manager.entries[0].weapon_index = 23  # Shooting Star
        manager.entries[0].text_overlays[2].x = 100
        manager.entries[0].text_overlays[2].y = 50
        manager.entries[0].text_overlays[2].id = 7
        manager.save_file()

        reloaded = ZoneManager(game_data)
        reloaded.load_file(str(mmag_file))
        assert reloaded.entries[0].weapon_index == 23
        overlay = reloaded.entries[0].text_overlays[2]
        assert (overlay.x, overlay.y, overlay.id) == (100, 50, 7)

    def test_raw_file_resolution(self, manager, mmag_file):
        manager.load_file(str(mmag_file))
        entry = manager.entries[0]
        # text file 2 -> raw 89, texture category 5 (base 71) page 3 -> raw 74
        assert manager.book_text_raw_file(entry) == BOOK_TEXT_FIRST_RAW_FILE + 2
        assert manager.texture_raw_file(entry) == TEXTURE_CATEGORIES[5][1] + 3
        # A category outside the table uses the page directly
        entry.texture_category = 200
        entry.texture_page = 42
        assert manager.texture_raw_file(entry) == 42

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
        ultimate_pages = [manager.get_weapon_name(manager.entries[i].weapon_index)
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
            assert (entry.weapon_index, entry.duel_move_id, entry.angelo_move_id) == \
                (0xFF, 0xFF, 0xFF)
        # Battle tutorial pages read text file 1 (raw 88), card rules file 2 (raw 89)
        assert manager.book_text_raw_file(manager.entries[43]) == 88
        assert manager.book_text_raw_file(manager.entries[51]) == 89


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/main/kernel.bin",
                     "extracted_files/menu/mwepon.bin")
class TestZoneManagerUnlockSources:
    """The unlock block draws from kernel.bin (Duel combos) and mwepon.bin (remodel lists)."""

    def test_unloaded_sources_are_empty_not_an_error(self, manager):
        manager.load_file(str(MMAG_PATH))
        assert manager.kernel_loaded is False and manager.mwepon_loaded is False
        assert manager.duel_sequence(4) == []
        assert manager.weapon_items(6) == []

    def test_duel_sequences_match_the_retail_combos(self, manager):
        manager.load_file(str(MMAG_PATH))
        manager.load_kernel(str(KERNEL_PATH))
        assert manager.kernel_loaded is True
        # 10 moves, each a 0xFFFF-terminated run of at most 5 buttons
        assert all(0 < len(manager.duel_sequence(move)) <= 5 for move in range(10))
        assert 0xFFFF not in manager.duel_sequence(9)
        # Punch Rush is the 2-button starter, My Final Heaven the 5-button finisher
        assert len(manager.duel_sequence(0)) == 2
        assert len(manager.duel_sequence(9)) == 5
        # Combat King 001 teaches Dolphin Blow, a 4-button combo
        assert len(manager.duel_sequence(manager.entries[28].duel_move_id)) == 4

    def test_load_kernel_rejects_a_non_kernel_file(self, manager, tmp_path):
        bad = tmp_path / "bad.bin"
        bad.write_bytes(bytes(256))
        with pytest.raises(ValueError):
            manager.load_kernel(str(bad))

    def test_weapon_items_are_the_real_remodel_recipes(self, manager):
        manager.load_file(str(MMAG_PATH))
        manager.load_mwepon(str(MWEPON_PATH))
        assert manager.mwepon_loaded is True
        # Weapons Monthly 1st issue page 1 is the Lion Heart page
        items = manager.weapon_items(manager.entries[0].weapon_index)
        assert [(manager.get_item_name(i), q) for i, q in items] == \
            [("Adamantine", 1), ("Dragon Fang", 4), ("Pulse Ammo", 12)]
        # Empty slots are dropped, so every row drawn has an item
        assert all(item_id for item_id, _ in manager.weapon_items(1))

    def test_item_names_are_ff8_encodable(self, manager):
        """item.json spells these with a backtick, which has no FF8 character code."""
        manager.load_file(str(MMAG_PATH))
        name = manager.get_item_name(159)
        assert name == "Chef's Knife"
        manager.game_data.translate_str_to_hex(name)  # must not raise


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
                  for overlay in entry.text_overlays if not overlay.unused]
        assert any("Weapons Monthly" in title for title in titles)
        # Unused slots resolve to an empty string
        assert manager.get_overlay_text(entry, entry.text_overlays[3]) == ""
