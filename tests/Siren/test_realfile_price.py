"""Real-file round-trip test for Siren (menu/price.bin editor).

Unlike test_sirenmanager.py (which builds a small synthetic price.bin), this test
loads the *original* game price.bin from extracted_files/ and checks that loading
then saving it is byte-for-byte lossless. It needs the real file and is skipped
otherwise (see the ff8data marker in the project-root conftest.py).
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Siren.sirenmanager import SirenManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
PRICE_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "price.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_item_data()
    return gd


@pytest.mark.ff8data("extracted_files/menu/price.bin")
def test_real_price_bin_roundtrip_is_lossless(game_data, tmp_path):
    """Load the real price.bin, save it, and expect identical bytes."""
    manager = SirenManager(game_data)
    manager.load_file(str(PRICE_BIN))
    assert manager.price_entries, "no price entries parsed from the real file"

    out = tmp_path / "price.bin"
    manager.save_file(str(out))

    assert out.read_bytes() == PRICE_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/price.bin")
def test_real_price_bin_edit_persists(game_data, tmp_path):
    """A single price edit survives save + reload, other entries untouched."""
    manager = SirenManager(game_data)
    manager.load_file(str(PRICE_BIN))
    original = [(e.price_div10, e.sell_mult, e.padding) for e in manager.price_entries]

    manager.price_entries[5].price_div10 = 4242
    out = tmp_path / "price.bin"
    manager.save_file(str(out))

    reloaded = SirenManager(game_data)
    reloaded.load_file(str(out))
    assert reloaded.price_entries[5].price_div10 == 4242
    for index, (price, sell, pad) in enumerate(original):
        if index == 5:
            continue
        entry = reloaded.price_entries[index]
        assert (entry.price_div10, entry.sell_mult, entry.padding) == (price, sell, pad)
