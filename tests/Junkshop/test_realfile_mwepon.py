"""Real-file round-trip test for Junkshop (menu/mwepon.bin weapon-upgrade editor).

Loads the original game mwepon.bin from extracted_files/ and checks that load + save
is byte-for-byte lossless. Needs the real file, skipped otherwise (ff8data marker).
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Junkshop.junkshopmanager import JunkshopManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MWEPON_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mwepon.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_item_data()
    return gd


@pytest.mark.ff8data("extracted_files/menu/mwepon.bin")
def test_real_mwepon_bin_roundtrip_is_lossless(game_data, tmp_path):
    manager = JunkshopManager(game_data)
    manager.load_file(str(MWEPON_BIN))
    assert manager.weapon_upgrades, "no weapon upgrades parsed from the real file"

    out = tmp_path / "mwepon.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == MWEPON_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mwepon.bin")
def test_real_mwepon_bin_edit_persists(game_data, tmp_path):
    manager = JunkshopManager(game_data)
    manager.load_file(str(MWEPON_BIN))
    original_prices = [w.price_div10 for w in manager.weapon_upgrades]

    manager.weapon_upgrades[2].price_div10 = 123
    manager.weapon_upgrades[2].items[0] = [7, 4]
    out = tmp_path / "mwepon.bin"
    manager.save_file(str(out))

    reloaded = JunkshopManager(game_data)
    reloaded.load_file(str(out))
    assert reloaded.weapon_upgrades[2].price_div10 == 123
    assert reloaded.weapon_upgrades[2].items[0] == [7, 4]
    for index, price in enumerate(original_prices):
        if index == 2:
            continue
        assert reloaded.weapon_upgrades[index].price_div10 == price
