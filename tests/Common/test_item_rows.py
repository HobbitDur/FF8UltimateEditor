"""mitem.bin (Kadowaki) and price.bin (Siren) rows for the items FFNx's AddMoreItems adds.

Both files are one 4-byte row per item id, 199 rows in the game; AddMoreItems reads them up to id
255. The tools add rows at the end (the next item id), remove only the added ones, and name them
from an opened kernel.bin - the only place the added items have a name.
"""
import pathlib

import pytest
from PyQt6.QtWidgets import QApplication

from Kadowaki.kadowakiwidget import KadowakiWidget
from Siren.sirenwidget import SirenWidget
from tests.addmoreitems_fixture import POTION_NAME, extended_kernel, extended_menu_file

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
GAME_DATA_FOLDER = str(PROJECT_ROOT / "FF8GameData")
MENU = PROJECT_ROOT / "extracted_files" / "menu"
KERNEL = PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


TOOLS = [
    pytest.param(KadowakiWidget, "mitem.bin", "menu_items", bytes([10, 0, 0, 0]), id="kadowaki"),
    pytest.param(SirenWidget, "price.bin", "price_entries", bytes(4), id="siren"),
]


@pytest.mark.ff8data("extracted_files/menu/mitem.bin", "extracted_files/menu/price.bin")
@pytest.mark.parametrize("tool_class, file_name, rows_attr, new_row", TOOLS)
def test_rows_are_added_and_removed_at_the_end(qapp, tmp_path, tool_class, file_name, rows_attr, new_row):
    work = tmp_path / file_name
    work.write_bytes((MENU / file_name).read_bytes())
    tool = tool_class(game_data_folder=GAME_DATA_FOLDER)
    tool.load_file(str(work))
    rows = getattr(tool.manager, rows_attr)
    assert len(rows) == 199
    assert not tool.item_rows.remove_button.isEnabled()

    tool.item_rows.add_button.click()
    tool.item_rows.add_button.click()
    assert len(rows) == 201 and tool.item_list.count() == 201
    assert tool.item_list.currentRow() == 200
    assert tool.item_list.item(199).text() == "199: Item 199"
    tool.save_file()
    data = work.read_bytes()
    assert data[:199 * 4] == (MENU / file_name).read_bytes()
    assert data[199 * 4:] == new_row * 2

    tool.item_rows.remove_button.click()
    tool.item_rows.remove_button.click()
    assert len(rows) == 199 and not tool.item_rows.remove_button.isEnabled()

    while len(rows) < 256:
        tool.item_rows.add_button.click()
    assert not tool.item_rows.add_button.isEnabled()
    tool.save_file()
    assert len(work.read_bytes()) == 1024


@pytest.mark.ff8data("extracted_files/menu/mitem.bin", "extracted_files/menu/price.bin",
                     "extracted_files/main/kernel.bin")
@pytest.mark.parametrize("tool_class, file_name, rows_attr, new_row", TOOLS)
def test_an_extended_file_round_trips_and_takes_the_kernel_names(qapp, tmp_path, tool_class, file_name,
                                                                rows_attr, new_row):
    work = tmp_path / file_name
    work.write_bytes(extended_menu_file((MENU / file_name).read_bytes()))
    kernel = tmp_path / "kernel.bin"
    kernel.write_bytes(extended_kernel(KERNEL.read_bytes()))
    tool = tool_class(game_data_folder=GAME_DATA_FOLDER)
    tool.load_file(str(work))
    assert tool.item_list.count() == 256
    assert tool.item_list.item(255).text() == "255: Item 255"
    tool.kernel_names._load(str(kernel))
    assert tool.item_list.item(255).text() == f"255: {POTION_NAME}"
    assert tool.item_list.item(1).text() == "Potion"
    tool.kernel_names._clear()
    assert tool.item_list.item(255).text() == "255: Item 255"
    tool.save_file()
    assert work.read_bytes() == extended_menu_file((MENU / file_name).read_bytes())
