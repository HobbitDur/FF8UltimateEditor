"""Real-file round-trip test for Kadowaki (menu/mitem.bin item-menu editor).

Loads the original game mitem.bin from extracted_files/ and checks that load + save
is byte-for-byte lossless. Needs the real file, skipped otherwise (ff8data marker).
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Kadowaki.kadowakimanager import KadowakiManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MITEM_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mitem.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_item_data()
    gd.load_mitem_data()
    gd.load_gforce_data()
    return gd


@pytest.mark.ff8data("extracted_files/menu/mitem.bin")
def test_real_mitem_bin_roundtrip_is_lossless(game_data, tmp_path):
    manager = KadowakiManager(game_data)
    manager.load_file(str(MITEM_BIN))
    assert manager.menu_items, "no menu items parsed from the real file"

    out = tmp_path / "mitem.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == MITEM_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mitem.bin")
def test_real_mitem_bin_edit_persists(game_data, tmp_path):
    manager = KadowakiManager(game_data)
    manager.load_file(str(MITEM_BIN))
    original = [(m.type_id, m.flags, m.param1, m.param2) for m in manager.menu_items]

    manager.menu_items[3].param1 = 0x7F
    out = tmp_path / "mitem.bin"
    manager.save_file(str(out))

    reloaded = KadowakiManager(game_data)
    reloaded.load_file(str(out))
    assert reloaded.menu_items[3].param1 == 0x7F
    for index, values in enumerate(original):
        if index == 3:
            continue
        item = reloaded.menu_items[index]
        assert (item.type_id, item.flags, item.param1, item.param2) == values
