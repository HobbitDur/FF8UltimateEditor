"""Zone edits a whole book: besides the pages (mmag.bin), the book text lines and the page pictures
of mngrp.bin, written by the shared Save only when they changed.

Needs the real game files, which are not in the repo (copyright), so it is skipped without them.
"""
import pathlib
import shutil
import sys

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.menu.magpicture import tex_to_image
from FF8GameData.tex.texfile import TexFile
from FF8GameData.tim.timfile import decode_tim
from Zone.zonemanager import ZoneManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
FILES = ("mmag.bin", "mngrp.bin", "mngrphd.bin", "mag00.TEX", "sysfnt.TEX", "sysfnt.tdw")

pytestmark = pytest.mark.ff8data(*(f"extracted_files/menu/{name}" for name in FILES))


@pytest.fixture
def menu(tmp_path):
    for name in FILES:
        shutil.copy(MENU_DIR / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def manager(menu):
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_sysfnt_data()
    manager = ZoneManager(game_data)
    manager.load_file(str(menu / "mmag.bin"))
    manager.load_mngrp(str(menu / "mngrp.bin"))
    return manager


def _reloaded(manager, menu):
    other = ZoneManager(manager.game_data)
    other.load_mngrp(str(menu / "mngrp.bin"))
    return other


def test_lines_added_and_edited_keep_their_ids_across_saves(manager, menu):
    count = len(manager.get_book_texts(0))
    first = manager.add_book_text("A new book\nby Zone")
    assert first == count
    assert manager.set_book_text(1, "Edited title")
    assert manager.get_book_texts(0)[first] == "A new book\\nby Zone"  # the game's line break
    manager.save_mngrp()
    second = manager.add_book_text("Page 2")
    assert second == count + 1
    manager.save_mngrp()

    texts = _reloaded(manager, menu).get_book_texts(0)
    assert texts[1] == "Edited title"
    assert texts[first:] == ["A new book\\nby Zone", "Page 2"]


def test_replaced_picture_is_previewed_then_saved_to_both_copies(manager, menu):
    manager.replace_picture(28, Image.new("RGBA", (256, 192), (20, 180, 60, 255)))
    assert decode_tim(manager.get_raw_file(28)).image.getpixel((9, 9))[:3] == (16, 181, 58)  # 5-bit colour
    assert tex_to_image(TexFile.read(str(menu / "mag00.TEX"))).getpixel((9, 9)) != (20, 180, 60, 255)

    assert manager.save_mngrp() == []
    assert tex_to_image(TexFile.read(str(menu / "mag00.TEX"))).getpixel((9, 9)) == (20, 180, 60, 255)
    image, origin = _reloaded(manager, menu).picture(28)
    assert origin == "menu/mag00.TEX" and image.getpixel((9, 9)) == (20, 180, 60, 255)


def test_a_slot_the_pc_never_shows_is_refused(manager):
    with pytest.raises(ValueError):
        manager.replace_picture(206, Image.new("RGBA", (256, 192)))


def test_nothing_edited_writes_nothing(manager, menu):
    stamp = (menu / "mngrp.bin").stat().st_mtime_ns
    assert manager.save_mngrp() == []
    assert (menu / "mngrp.bin").stat().st_mtime_ns == stamp


def test_widget_edits_a_line_in_place_and_saves_both_files(menu):
    QApplication.instance() or QApplication(sys.argv)
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(menu / "mmag.bin"))
    zone._apply_mngrp(str(menu / "mngrp.bin"))
    zone.select_entry(0)
    zone.add_page_button.click()

    _x, _y, id_spin, editor = zone.text_overlay_spins[0]
    old_id = id_spin.value()
    zone.new_line_buttons[0].click()
    new_id = id_spin.value()
    assert new_id != old_id and editor.toPlainText() == "" and not editor.isReadOnly()
    editor.setPlainText("My own magazine\nIssue 1")
    assert zone.manager.get_book_texts(0)[new_id] == "My own magazine\\nIssue 1"
    assert zone.replace_picture_button.isEnabled() == zone.manager.can_replace_picture(zone._picture_slot())

    zone.save_files()
    reloaded = ZoneManager(zone.manager.game_data)
    reloaded.load_file(str(menu / "mmag.bin"))
    reloaded.load_mngrp(str(menu / "mngrp.bin"))
    assert reloaded.entries[ZoneManager.VANILLA_ENTRY_COUNT].text_overlays[0].id == new_id
    assert reloaded.get_book_texts(0)[new_id] == "My own magazine\\nIssue 1"


def test_the_tool_save_writes_the_book_edits(menu):
    """The shared Save goes through ZoneTabsWidget: mngrp.bin, a complementary file, must not be
    skipped there."""
    QApplication.instance() or QApplication(sys.argv)
    from Zone.zonetabswidget import ZoneTabsWidget
    tabs = ZoneTabsWidget()
    zone = tabs.mmag_widget
    zone._load_mmag(str(menu / "mmag.bin"))
    zone._apply_mngrp(str(menu / "mngrp.bin"))
    text_id = zone.manager.add_book_text("Saved through the tool")

    assert tabs.save_files() is True
    assert _reloaded(zone.manager, menu).get_book_texts(0)[text_id] == "Saved through the tool"
