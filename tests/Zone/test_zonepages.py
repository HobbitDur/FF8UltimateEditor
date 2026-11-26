"""Zone adds a new book's pages at the end of mmag.bin, and removes only the added ones."""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.menu.magpage import MagPageEntry
from Zone.zonemanager import ZoneManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture
def mmag_path(tmp_path):
    """A vanilla-sized mmag.bin (69 pages), page 5 with a recognisable window."""
    entries = [MagPageEntry(index) for index in range(ZoneManager.VANILLA_ENTRY_COUNT)]
    entries[5].window_x = 24
    entries[5].window_width = 336
    entries[5].texture_category = 0
    entries[5].texture_page = 2
    path = tmp_path / "mmag.bin"
    path.write_bytes(b"".join(bytes(entry.to_bytes()) for entry in entries))
    return path


@pytest.fixture
def manager(mmag_path):
    manager = ZoneManager(GameData(str(PROJECT_ROOT / "FF8GameData")))
    manager.load_file(str(mmag_path))
    return manager


def test_added_page_copies_the_selected_one_and_is_saved(manager, mmag_path):
    index = manager.add_entry(copy_of=5)
    assert index == ZoneManager.VANILLA_ENTRY_COUNT
    manager.entries[index].window_y = 9
    manager.save_file()

    reloaded = ZoneManager(manager.game_data)
    reloaded.load_file(str(mmag_path))
    assert len(reloaded.entries) == ZoneManager.VANILLA_ENTRY_COUNT + 1
    page = reloaded.entries[index]
    assert (page.window_x, page.window_width, page.window_y) == (24, 336, 9)
    assert reloaded.entries[5].window_y == 0  # the copy is its own page
    assert reloaded.entry_name(index) == "Added page"


def test_only_added_pages_can_be_removed(manager):
    assert not manager.can_remove_entry()
    assert manager.remove_last_entry() is False
    manager.add_entry()
    assert manager.remove_last_entry() is True
    assert len(manager.entries) == ZoneManager.VANILLA_ENTRY_COUNT


def test_no_more_than_256_pages(manager):
    while manager.add_entry() is not None:
        pass
    assert len(manager.entries) == ZoneManager.MAX_ENTRY_COUNT


def test_picture_file_the_pc_game_shows(manager):
    assert manager.pc_picture_file(manager.entries[5]) == "mag02.TEX"  # Weapons Monthly base 28 + 2
    direct = MagPageEntry()
    direct.texture_category = 7
    direct.texture_page = 206
    assert manager.pc_picture_file(direct) is None


def test_widget_buttons_add_and_remove_pages(mmag_path):
    QApplication.instance() or QApplication(sys.argv)
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(mmag_path))
    zone.select_entry(5)
    assert not zone.remove_page_button.isEnabled()

    zone.add_page_button.click()
    assert zone.entry_list.count() == ZoneManager.VANILLA_ENTRY_COUNT + 1
    assert zone.current_entry_index == ZoneManager.VANILLA_ENTRY_COUNT
    assert zone.window_w.value() == 336
    assert zone.remove_page_button.isEnabled()

    zone.remove_page_button.click()
    assert zone.entry_list.count() == ZoneManager.VANILLA_ENTRY_COUNT
    assert len(zone.manager.entries) == ZoneManager.VANILLA_ENTRY_COUNT
    zone.save_file()  # the removed page's form must not be written anywhere
    assert mmag_path.stat().st_size == ZoneManager.VANILLA_ENTRY_COUNT * MagPageEntry.SIZE
