"""
Tests for Quezacotl (init.out new-game default editor).

init.out is a single binary buffer holding GF records, character records, a config
block, a misc block and the starting item table. The manager keeps the whole buffer
in memory and exposes thin views over it, so regions it never decodes must survive a
load/save round-trip byte-for-byte.

The tests build a zero-initialised buffer of the right size (the manager grows the
vanilla file up to FULL_FILE_SIZE on load) rather than needing the original game file.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Quezacotl.quezacotlmanager import (
    QuezacotlManager, FULL_FILE_SIZE, NB_GF, NB_CHARACTERS, NB_ITEMS,
    GF_DATA_OFFSET, GF_ENTRY_SIZE, ITEMS_DATA_OFFSET, ITEM_ENTRY_SIZE,
    GF_COMPATIBILITY_MIN,
)


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    gd = GameData(str(project_root / "FF8GameData"))
    return gd


@pytest.fixture
def manager(game_data):
    return QuezacotlManager(game_data)


@pytest.fixture
def init_file(tmp_path):
    """A full-size, zero-initialised init.out."""
    file_path = tmp_path / "init.out"
    file_path.write_bytes(bytes(FULL_FILE_SIZE))
    return file_path


class TestLoad:
    def test_parses_all_entry_tables(self, manager, init_file):
        manager.load_file(str(init_file))
        assert len(manager.gf_entries) == NB_GF
        assert len(manager.character_entries) == NB_CHARACTERS
        assert len(manager.item_entries) == NB_ITEMS
        assert manager.config is not None
        assert manager.misc is not None

    def test_grows_short_vanilla_file(self, manager, tmp_path):
        """A vanilla init.out only reserves 4 item slots; the manager grows it so every
        item slot becomes editable and the buffer reaches FULL_FILE_SIZE."""
        short = tmp_path / "vanilla_init.out"
        short.write_bytes(bytes(ITEMS_DATA_OFFSET + 4 * ITEM_ENTRY_SIZE))
        manager.load_file(str(short))
        assert len(manager.buffer) == FULL_FILE_SIZE
        assert len(manager.item_entries) == NB_ITEMS

    def test_gf_names_from_gforce_json(self, manager, init_file):
        manager.load_file(str(init_file))
        assert manager.gf_entries[0].gf_name == "Quezacotl"


class TestSaveRoundtrip:
    def test_save_without_modification_is_identical(self, manager, init_file, tmp_path):
        manager.load_file(str(init_file))
        saved = tmp_path / "saved_init.out"
        manager.save_file(str(saved))
        assert saved.read_bytes() == init_file.read_bytes()

    def test_save_defaults_to_loaded_path(self, manager, init_file):
        manager.load_file(str(init_file))
        manager.item_entries[0].item_id = 5
        manager.save_file()
        assert init_file.read_bytes()[ITEMS_DATA_OFFSET] == 5


class TestGfEntry:
    def test_name_roundtrip(self, manager, game_data, init_file):
        manager.load_file(str(init_file))
        manager.gf_entries[0].name = "Quetzal"
        manager.gf_entries[0].exp = 123456
        manager.gf_entries[0].available = True
        manager.gf_entries[0].current_hp = 999
        manager.save_file()

        reloaded = QuezacotlManager(game_data)
        reloaded.load_file(str(init_file))
        gf = reloaded.gf_entries[0]
        assert gf.name == "Quetzal"
        assert gf.exp == 123456
        assert gf.available is True
        assert gf.current_hp == 999

    def test_ability_bitfield(self, manager, init_file):
        manager.load_file(str(init_file))
        gf = manager.gf_entries[0]
        assert gf.has_ability(10) is False
        gf.set_ability(10, True)
        assert gf.has_ability(10) is True
        # a different ability in the same byte is unaffected
        assert gf.has_ability(11) is False
        gf.set_ability(10, False)
        assert gf.has_ability(10) is False

    def test_name_is_clamped_to_twelve_bytes(self, manager, init_file):
        """Setting a name must never spill into the next GF entry's 68-byte record."""
        manager.load_file(str(init_file))
        manager.gf_entries[0].name = "ABCDEFGHIJKLMNOP"  # 16 chars, longer than the 12-byte field
        # the first byte of GF entry 1 (right after entry 0) stays zero
        assert manager.buffer[GF_DATA_OFFSET + GF_ENTRY_SIZE] == 0


class TestCharacterEntry:
    def test_stat_roundtrip(self, manager, game_data, init_file):
        manager.load_file(str(init_file))
        squall = manager.character_entries[0]
        assert squall.name == "Squall"
        squall.current_hp = 1234
        squall.exp = 654321
        squall.str_stat = 42
        squall.spd = 17
        squall.luck = 99
        manager.save_file()

        reloaded = QuezacotlManager(game_data)
        reloaded.load_file(str(init_file))
        squall = reloaded.character_entries[0]
        assert squall.current_hp == 1234
        assert squall.exp == 654321
        assert squall.str_stat == 42
        assert squall.spd == 17
        assert squall.luck == 99

    def test_gf_compatibility_roundtrip(self, manager, game_data, init_file):
        manager.load_file(str(init_file))
        squall = manager.character_entries[0]
        squall.set_gf_compatibility(0, GF_COMPATIBILITY_MIN + 500)
        manager.save_file()

        reloaded = QuezacotlManager(game_data)
        reloaded.load_file(str(init_file))
        assert reloaded.character_entries[0].get_gf_compatibility(0) == GF_COMPATIBILITY_MIN + 500

    def test_magic_slots_are_independent(self, manager, init_file):
        manager.load_file(str(init_file))
        squall = manager.character_entries[0]
        assert len(squall.magics) == 32
        squall.magics[0].magic_id = 5
        squall.magics[0].quantity = 100
        assert squall.magics[1].magic_id == 0
        assert squall.magics[1].quantity == 0


class TestItemEntry:
    def test_item_roundtrip_and_name(self, manager, game_data, init_file):
        manager.load_file(str(init_file))
        manager.item_entries[0].item_id = 1  # Potion
        manager.item_entries[0].quantity = 50
        assert manager.item_entries[0].name == "Potion"
        manager.save_file()

        reloaded = QuezacotlManager(game_data)
        reloaded.load_file(str(init_file))
        assert reloaded.item_entries[0].item_id == 1
        assert reloaded.item_entries[0].quantity == 50

    def test_unknown_item_id_falls_back(self, manager, init_file):
        manager.load_file(str(init_file))
        manager.item_entries[0].item_id = 254
        assert manager.item_entries[0].name == "Item 254"
