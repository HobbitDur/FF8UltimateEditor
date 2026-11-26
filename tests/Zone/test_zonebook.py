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


def test_new_pictures_take_the_slots_after_the_last_used_one(manager, menu):
    """Add new picture: slot 206 then 207 (after mngrp.bin's last section, so nothing moves), the
    TIM in mngrp.bin and menu/magNNN.TEX written with the default header when no vanilla .TEX
    sits in the folder."""
    (menu / "mag00.TEX").unlink()  # like a mod's menu folder: no vanilla picture to copy
    first = manager.add_picture(Image.new("RGBA", (256, 192), (250, 10, 120, 255)))
    second = manager.add_picture(Image.new("RGBA", (256, 192), (0, 0, 255, 255)))
    assert (first, second) == (206, 207)
    assert decode_tim(manager.get_raw_file(first)).image_x == 896  # previewed before the save

    assert manager.save_mngrp() == []
    reloaded = _reloaded(manager, menu)
    assert reloaded.has_slot(206) and reloaded.has_slot(207) and not reloaded.has_slot(208)
    image, origin = reloaded.picture(206)
    assert origin == "menu/mag206.TEX" and image.getpixel((3, 3)) == (250, 10, 120, 255)
    assert reloaded.get_book_texts(0) == manager.get_book_texts(0)  # the sections before did not move


def test_a_file_with_added_slots_loads_in_every_mngrp_tool(manager, menu):
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    manager.add_picture(Image.new("RGBA", (256, 192), (1, 2, 3, 255)))
    manager.save_mngrp()
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    model = MngrpManager(game_data)
    model.load_file(str(menu / "mngrphd.bin"), str(menu / "mngrp.bin"))
    assert model.last_used_slot() == 206
    with pytest.raises(ValueError):
        model.add_raw_section(185, b"\x00")  # before the last used slot: it would move the others


def test_widget_adds_a_picture_and_points_the_page_at_it(menu):
    QApplication.instance() or QApplication(sys.argv)
    from Zone.zonewidget import ZoneWidget, DIRECT_TEXTURE_CATEGORY
    zone = ZoneWidget()
    zone._load_mmag(str(menu / "mmag.bin"))
    zone._apply_mngrp(str(menu / "mngrp.bin"))
    zone.select_entry(0)
    zone.add_page_button.click()
    png = menu / "new.png"
    Image.new("RGBA", (256, 192), (40, 200, 90, 255)).save(png)

    slot = zone.add_picture_from_file(str(png))
    assert slot == 206
    assert zone.texture_category.currentData() == DIRECT_TEXTURE_CATEGORY and zone.texture_page.value() == 206
    assert "mag206.TEX" in zone.texture_label.text()
    zone.save_files()
    reloaded = ZoneManager(zone.manager.game_data)
    reloaded.load_file(str(menu / "mmag.bin"))
    page = reloaded.entries[ZoneManager.VANILLA_ENTRY_COUNT]
    assert (page.texture_category, page.texture_page) == (DIRECT_TEXTURE_CATEGORY, 206)
    assert (menu / "mag206.TEX").exists()


def test_raw_numbers_are_offered_as_named_choices(menu):
    """The text file, the page picture and the overlay ids are picked by name, not typed."""
    QApplication.instance() or QApplication(sys.argv)
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(menu / "mmag.bin"))
    zone._apply_mngrp(str(menu / "mngrp.bin"))
    zone.select_entry(2)  # Weapons Monthly 1st Issue 3/4

    assert zone.text_file.currentText().startswith("0: Book text")
    pages = [zone.texture_page.itemText(i) for i in range(zone.texture_page.count())]
    assert "2: mag02.TEX" in pages  # the category's other issues
    assert zone.texture_page.currentText() == "0: mag00.TEX"  # the 4 pages of the 1st issue share mag00
    _x, _y, sprite_id, _none = zone.pic_overlay_spins[0]
    assert sprite_id.currentText().split(":")[0] == str(sprite_id.value())
    assert "x" in sprite_id.currentText()  # the sprite's size
    _x, _y, line_id, editor = zone.text_overlay_spins[0]
    assert line_id.currentText().startswith(f"{line_id.value()}: Weapons Monthly")

    # Picking another line by its name shows it in the editor
    line_id.setCurrentIndex(line_id.findData(2))
    assert editor.toPlainText().startswith("Of all gunblades")
    # Editing a line renames it in every overlay's list
    editor.setPlainText("Renamed line")
    _x, _y, other_line_id, _editor = zone.text_overlay_spins[1]
    assert other_line_id.itemText(other_line_id.findData(2)) == "2: Renamed line"


def test_the_games_other_data_past_185_is_no_added_picture():
    """has_added_picture: the game's 188-205 are not pictures, so Zone neither lists nor replaces them."""
    import pathlib
    import pytest
    from FF8GameData.gamedata import GameData
    from Zone.zonemanager import ZoneManager
    menu = pathlib.Path(__file__).parent.parent.parent / "extracted_files" / "menu"
    if not (menu / "mngrp.bin").exists():
        pytest.skip("needs extracted_files/menu")
    manager = ZoneManager(GameData(str(pathlib.Path(__file__).parent.parent.parent / "FF8GameData")))
    manager.load_mngrp(str(menu / "mngrp.bin"))
    assert manager.has_slot(188) and not manager.has_added_picture(188)
    assert not manager.can_replace_picture(200)
    assert manager.can_replace_picture(28)
