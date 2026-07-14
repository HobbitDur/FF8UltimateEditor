"""Real-file round-trip test for TonberryShop (menu/shop.bin editor).

Loads the original game shop.bin from extracted_files/ and checks the read/analyze/write
cycle is stable (idempotent). shop.bin stores item names via an id->name table, so a
name that maps back to a different id can shift bytes on the first save; what must hold
is that a second identical round-trip produces exactly the same bytes.

Needs the real file, skipped otherwise (ff8data marker).
"""
import pathlib

import pytest

from TonberryShop.tonberrymanager import TonberryManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
SHOP_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "shop.bin"
RESOURCE_FOLDER = str(PROJECT_ROOT / "Resources")


def _read_analyze_write(dest):
    manager = TonberryManager(resource_folder=RESOURCE_FOLDER)
    manager.read_shop_file(str(SHOP_BIN) if dest is None else str(dest))
    manager.analyze_shop_file()
    return manager


@pytest.mark.ff8data("extracted_files/menu/shop.bin")
def test_real_shop_bin_roundtrip_is_idempotent(tmp_path):
    first = _read_analyze_write(None)
    out1 = tmp_path / "shop1.bin"
    first.write_shop_file(str(out1))

    second = TonberryManager(resource_folder=RESOURCE_FOLDER)
    second.read_shop_file(str(out1))
    second.analyze_shop_file()
    out2 = tmp_path / "shop2.bin"
    second.write_shop_file(str(out2))

    assert out1.read_bytes() == out2.read_bytes()
    # Same size as the original (write patches in place, never grows the file)
    assert len(out1.read_bytes()) == len(SHOP_BIN.read_bytes())


@pytest.mark.ff8data("extracted_files/menu/shop.bin")
def test_real_shop_parsed_shops_survive_reload(tmp_path):
    first = _read_analyze_write(None)
    parsed = [(shop.item[:], shop.rare[:]) for shop in first.shop_info]

    out = tmp_path / "shop.bin"
    first.write_shop_file(str(out))

    reloaded = TonberryManager(resource_folder=RESOURCE_FOLDER)
    reloaded.read_shop_file(str(out))
    reloaded.analyze_shop_file()
    reparsed = [(shop.item[:], shop.rare[:]) for shop in reloaded.shop_info]
    assert parsed == reparsed
