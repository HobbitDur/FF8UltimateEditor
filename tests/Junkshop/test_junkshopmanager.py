"""
Tests for Junkshop (mwepon.bin weapon-upgrade editor).

mwepon.bin is a flat array of 12-byte entries indexed by weapon-upgrade id:
    - uint16 name_offset (into mwepon.msg, preserved as-is)
    - byte   padding (unused, preserved as-is)
    - byte   price / 10
    - 4 x (byte item_id, byte quantity)   -> the ingredients consumed on upgrade

A small synthetic mwepon.bin is built with known entries so the tests don't need
the original game files.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Junkshop.junkshopmanager import JunkshopManager, WeaponUpgrade

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
RESOURCE_FOLDER = str(PROJECT_ROOT / "Junkshop" / "Resources")


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_item_data()
    return gd


@pytest.fixture
def manager(game_data):
    return JunkshopManager(game_data, resource_folder=RESOURCE_FOLDER)


def _weapon_bytes(name_offset, padding, price_div10, items):
    data = bytearray(12)
    data[0] = name_offset & 0xFF
    data[1] = (name_offset >> 8) & 0xFF
    data[2] = padding & 0xFF
    data[3] = price_div10 & 0xFF
    for i, (item_id, quantity) in enumerate(items):
        data[4 + i * 2] = item_id
        data[5 + i * 2] = quantity
    return bytes(data)


@pytest.fixture
def mwepon_file(tmp_path):
    """mwepon.bin with 2 known weapon upgrades."""
    entries = [
        # weapon 0: name_offset 0x10, padding 0, price 800 (stored 80),
        #   4 ingredients
        (0x10, 0, 80, [(1, 2), (7, 1), (0, 0), (0, 0)]),
        # weapon 1: non-zero padding, price 1500 (stored 150)
        (0x2A, 0x00, 150, [(9, 3), (0, 0), (0, 0), (0, 0)]),
    ]
    data = bytearray()
    for name_offset, padding, price_div10, items in entries:
        data += _weapon_bytes(name_offset, padding, price_div10, items)
    file_path = tmp_path / "mwepon.bin"
    file_path.write_bytes(data)
    return file_path, entries


class TestWeaponUpgrade:
    def test_price_is_stored_value_times_ten(self):
        upgrade = WeaponUpgrade(0, "Revolver", price_div10=80)
        assert upgrade.price == 800

    def test_price_setter_divides_by_ten(self):
        upgrade = WeaponUpgrade(0, "Revolver")
        upgrade.price = 2500
        assert upgrade.price_div10 == 250
        assert upgrade.price == 2500

    def test_default_items_are_four_empty_pairs(self):
        upgrade = WeaponUpgrade(0, "Revolver")
        assert upgrade.items == [[0, 0], [0, 0], [0, 0], [0, 0]]

    def test_to_bytes_layout(self):
        upgrade = WeaponUpgrade(0, "X", name_offset=0x1234, padding=0x56,
                                price_div10=0x78, items=[[1, 2], [3, 4], [5, 6], [7, 8]])
        assert upgrade.to_bytes() == bytes([0x34, 0x12, 0x56, 0x78, 1, 2, 3, 4, 5, 6, 7, 8])


class TestJunkshopManager:
    def test_weapon_names_loaded(self, manager):
        assert len(manager.weapon_name_list) > 0
        assert manager.get_weapon_name(0) == manager.weapon_name_list[0]
        assert manager.get_weapon_name(9999) == "Weapon 9999"

    def test_load_file(self, manager, mwepon_file):
        file_path, entries = mwepon_file
        manager.load_file(str(file_path))
        assert len(manager.weapon_upgrades) == len(entries)

        first = manager.weapon_upgrades[0]
        assert first.name_offset == 0x10
        assert first.price == 800
        assert first.items[0] == [1, 2]
        assert first.items[1] == [7, 1]

    def test_item_names_come_from_item_json(self, manager, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        assert manager.get_item_name(1) == "Potion"
        assert manager.get_item_name(0) == "Nothing"
        assert manager.get_item_name(9999) == "Item 9999"

    def test_save_without_modification_is_identical(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == file_path.read_bytes()

    def test_name_offset_and_padding_preserved(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[1].price = 9990  # only touch price
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        data = saved.read_bytes()
        # name_offset (bytes 0-1) and padding (byte 2) of weapon 1 are untouched
        assert data[12:14] == bytes([0x2A, 0x00])
        assert data[15] == 999 & 0xFF

    def test_modify_ingredients_and_save(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[0].items[2] = [5, 9]
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        data = saved.read_bytes()
        assert data[8:10] == bytes([5, 9])
        # weapon 1 untouched
        assert data[12:24] == _weapon_bytes(0x2A, 0, 150, [(9, 3), (0, 0), (0, 0), (0, 0)])

    def test_save_defaults_to_loaded_path(self, manager, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[0].items[0] = [42, 1]
        manager.save_file()
        assert file_path.read_bytes()[4] == 42

    def test_reload_roundtrip(self, manager, game_data, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        # price is stored in a single byte as price/10, so the max representable value is 2550
        manager.weapon_upgrades[0].price = 2500
        manager.weapon_upgrades[0].items[3] = [11, 22]
        manager.save_file()

        reloaded = JunkshopManager(game_data, resource_folder=RESOURCE_FOLDER)
        reloaded.load_file(str(file_path))
        assert reloaded.weapon_upgrades[0].price == 2500
        assert reloaded.weapon_upgrades[0].items[3] == [11, 22]
