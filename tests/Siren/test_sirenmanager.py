"""
Tests for Siren (price.bin shop-price editor).

price.bin is a flat array of 4-byte entries indexed by item id:
    - uint16 buy_price / 10
    - byte   sell multiplier
    - byte   unused padding (preserved byte-perfect)

A small synthetic price.bin is built with known entries so the tests don't need
the original game files.
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from Siren.sirenmanager import PriceEntry, SirenManager


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    gd = GameData(str(project_root / "FF8GameData"))
    gd.load_item_data()
    return gd


@pytest.fixture
def manager(game_data):
    return SirenManager(game_data)


@pytest.fixture
def price_file(tmp_path):
    """price.bin with 3 known entries."""
    entries = [
        # item 0 (Nothing): dummy zero entry
        (0, 0, 0),
        # item 1 (Potion): buy 100 G -> stored 10, sell mult 5, padding preserved
        (10, 5, 0),
        # item 2: buy 2000 G -> stored 200, sell mult 2, non-zero padding to prove it survives
        (200, 2, 0x7F),
    ]
    data = bytearray()
    for price_div10, sell_mult, padding in entries:
        data += struct.pack("<HBB", price_div10, sell_mult, padding)
    file_path = tmp_path / "price.bin"
    file_path.write_bytes(data)
    return file_path, entries


class TestPriceEntry:
    def test_buy_price_is_stored_value_times_ten(self):
        entry = PriceEntry(1, "Potion", price_div10=10, sell_mult=5)
        assert entry.buy_price == 100

    def test_buy_price_setter_divides_by_ten(self):
        entry = PriceEntry(1, "Potion")
        entry.buy_price = 2500
        assert entry.price_div10 == 250
        assert entry.buy_price == 2500

    def test_sell_price_formula(self):
        # sell = round((buy / 10 / 2) * sell_mult) = round((1000/10/2)*3) = round(50*3) = 150
        entry = PriceEntry(1, "X", price_div10=100, sell_mult=3)
        assert entry.buy_price == 1000
        assert entry.sell_price == 150

    def test_to_bytes_is_four_bytes_little_endian(self):
        entry = PriceEntry(1, "X", price_div10=0x1234, sell_mult=0x56, padding=0x78)
        assert entry.to_bytes() == bytes([0x34, 0x12, 0x56, 0x78])


class TestSirenManager:
    def test_load_file(self, manager, price_file):
        file_path, entries = price_file
        manager.load_file(str(file_path))
        assert len(manager.price_entries) == len(entries)

        potion = manager.price_entries[1]
        assert potion.item_id == 1
        assert potion.name == "Potion"
        assert potion.price_div10 == 10
        assert potion.buy_price == 100
        assert potion.sell_mult == 5

    def test_item_names_come_from_item_json(self, manager, price_file):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        assert manager.price_entries[0].name == "Nothing"

    def test_save_without_modification_is_identical(self, manager, price_file, tmp_path):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        saved = tmp_path / "saved_price.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == file_path.read_bytes()

    def test_padding_preserved_byte_perfect(self, manager, price_file, tmp_path):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        assert manager.price_entries[2].padding == 0x7F
        saved = tmp_path / "saved_price.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes()[8:12] == bytes([200, 0, 2, 0x7F])

    def test_modify_and_save(self, manager, price_file, tmp_path):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        manager.price_entries[1].buy_price = 3000  # stored as 300
        manager.price_entries[1].sell_mult = 4
        saved = tmp_path / "saved_price.bin"
        manager.save_file(str(saved))

        data = saved.read_bytes()
        assert data[4:8] == bytes([300 & 0xFF, 300 >> 8, 4, 0])
        # untouched neighbours survive
        assert data[0:4] == bytes([0, 0, 0, 0])
        assert data[8:12] == bytes([200, 0, 2, 0x7F])

    def test_save_defaults_to_loaded_path(self, manager, price_file):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        manager.price_entries[0].sell_mult = 9
        manager.save_file()
        assert file_path.read_bytes()[2] == 9

    def test_reload_roundtrip(self, manager, game_data, price_file, tmp_path):
        file_path, _ = price_file
        manager.load_file(str(file_path))
        manager.price_entries[2].buy_price = 12340
        manager.save_file()

        reloaded = SirenManager(game_data)
        reloaded.load_file(str(file_path))
        assert reloaded.price_entries[2].buy_price == 12340
        assert reloaded.price_entries[2].padding == 0x7F
