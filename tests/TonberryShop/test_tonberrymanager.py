"""
Tests for TonberryShop (shop file editor).

The shop file is a flat array of NB_SHOP (20) shops, each holding
NB_ITEM_PER_SHOP (16) two-byte entries:
    - byte 0: item id (resolved to a name through Resources/item.txt)
    - byte 1: 0xFF => normal item, 0x00 => rare item

A small synthetic shop file is built with known entries so the tests don't need
the original game files.
"""
import pathlib

import pytest

from TonberryShop.tonberrymanager import Shop, TonberryManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
RESOURCE_FOLDER = str(PROJECT_ROOT / "Resources")

NB_SHOP = TonberryManager.NB_SHOP
NB_ITEM = Shop.NB_ITEM_PER_SHOP
SHOP_FILE_SIZE = NB_SHOP * NB_ITEM * TonberryManager.NB_BYTE_PER_ITEM


@pytest.fixture
def manager():
    return TonberryManager(resource_folder=RESOURCE_FOLDER)


@pytest.fixture
def shop_file(tmp_path):
    """A full-size shop file, all slots = item 0 / normal, with a few known overrides."""
    data = bytearray(SHOP_FILE_SIZE)
    # Every second byte is the rarity flag; default 0x00 in a zeroed buffer would mean
    # "rare", so initialise the whole file to normal (0xFF) first.
    for i in range(1, SHOP_FILE_SIZE, 2):
        data[i] = 0xFF
    # Shop 0, item 0: Potion (id 1), normal
    data[0] = 0x01
    data[1] = 0xFF
    # Shop 0, item 1: Phoenix Down (id 7), rare
    data[2] = 0x07
    data[3] = 0x00
    file_path = tmp_path / "shop.bin"
    file_path.write_bytes(data)
    return file_path


class TestTonberryManager:
    def test_item_data_loaded(self, manager):
        assert manager.item_values[0x00] == "Nothing"
        assert manager.item_values[0x01] == "Potion"
        assert manager.item_values[0x07] == "Phoenix Down"

    def test_shop_names_count_matches(self, manager):
        assert len(manager.SHOP_NAME_LIST) == NB_SHOP

    def test_read_and_analyze(self, manager, shop_file):
        manager.read_shop_file(str(shop_file))
        manager.analyze_shop_file()

        assert len(manager.shop_info) == NB_SHOP
        shop0 = manager.shop_info[0]
        assert shop0.item[0] == "Potion"
        assert shop0.rare[0] is False
        assert shop0.item[1] == "Phoenix Down"
        assert shop0.rare[1] is True
        # untouched slot
        assert shop0.item[2] == "Nothing"
        assert shop0.rare[2] is False

    def test_write_without_modification_is_identical(self, manager, shop_file, tmp_path):
        manager.read_shop_file(str(shop_file))
        manager.analyze_shop_file()
        saved = tmp_path / "saved_shop.bin"
        manager.write_shop_file(str(saved))
        assert saved.read_bytes() == shop_file.read_bytes()

    def test_modify_item_and_rarity(self, manager, shop_file, tmp_path):
        manager.read_shop_file(str(shop_file))
        manager.analyze_shop_file()
        manager.shop_info[0].item[0] = "Hi-Potion"  # id 3
        manager.shop_info[0].rare[0] = True
        saved = tmp_path / "saved_shop.bin"
        manager.write_shop_file(str(saved))

        data = saved.read_bytes()
        assert data[0] == 0x03
        assert data[1] == 0x00  # now rare
        # neighbouring entry untouched (Phoenix Down, rare)
        assert data[2] == 0x07
        assert data[3] == 0x00

    def test_write_defaults_to_loaded_path(self, manager, shop_file):
        manager.read_shop_file(str(shop_file))
        manager.analyze_shop_file()
        manager.shop_info[0].item[0] = "Nothing"
        manager.write_shop_file()
        assert shop_file.read_bytes()[0] == 0x00

    def test_reload_roundtrip(self, manager, shop_file):
        manager.read_shop_file(str(shop_file))
        manager.analyze_shop_file()
        manager.shop_info[NB_SHOP - 1].item[NB_ITEM - 1] = "Hi-Potion"
        manager.shop_info[NB_SHOP - 1].rare[NB_ITEM - 1] = True
        manager.write_shop_file()

        reloaded = TonberryManager(resource_folder=RESOURCE_FOLDER)
        reloaded.read_shop_file(str(shop_file))
        reloaded.analyze_shop_file()
        last = reloaded.shop_info[NB_SHOP - 1]
        assert last.item[NB_ITEM - 1] == "Hi-Potion"
        assert last.rare[NB_ITEM - 1] is True
