"""Shiva's "Magazine pictures" tab: a picture replaced from a PNG lands in both copies at Save - the
.TEX the PC game shows and the TIM inside mngrp.bin - and nothing else moves.

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
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from FF8GameData.tex.texfile import TexFile
from FF8GameData.tim.timfile import decode_tim

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"
SLOT = 28  # mag00, Weapons Monthly

pytestmark = pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/mag00.TEX")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _load(game_data, folder):
    manager = MngrpManager(game_data)
    manager.load_file(str(folder / "mngrphd.bin"), str(folder / "mngrp.bin"))
    return manager


def test_replaced_picture_is_written_to_the_tex_and_the_mngrp(qapp, game_data, tmp_path):
    from Shiva.ShivaMagazinePicture.shivamagazinepicturewidget import ShivaMagazinePictureWidget
    for name in ("mngrp.bin", "mngrphd.bin", "mag00.TEX"):
        shutil.copy(MENU / name, tmp_path / name)
    png = tmp_path / "new.png"
    Image.new("RGBA", (256, 192), (200, 40, 40, 255)).save(png)

    manager = _load(game_data, tmp_path)
    before = [bytes(section.get_data_hex()) for section in manager.mngrp.get_section_list()]
    tab = ShivaMagazinePictureWidget()
    tab.load_from_mngrp(manager)
    assert tab.replace_from_file(SLOT, str(png))
    tab.save_to_mngrp(manager)
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))

    tex_image = tex_to_image(TexFile.read(str(tmp_path / "mag00.TEX")))
    r, g, b, a = tex_image.getpixel((128, 96))
    assert a == 255 and abs(r - 200) < 9 and abs(g - 40) < 9 and abs(b - 40) < 9

    reloaded = _load(game_data, tmp_path)
    after = [bytes(section.get_data_hex()) for section in reloaded.mngrp.get_section_list()]
    tim = decode_tim(after[SLOT])
    assert tim.image_x == 896 and tim.image_y == 0
    r, g, b, a = tim.image.getpixel((128, 96))
    assert a == 255 and abs(r - 200) < 9 and abs(g - 40) < 9
    changed = [slot for slot, (old, new) in enumerate(zip(before, after)) if old != new]
    assert changed == [SLOT]


def test_wrong_size_is_refused_and_nothing_is_queued(qapp, game_data, tmp_path, monkeypatch):
    from Shiva.ShivaMagazinePicture import shivamagazinepicturewidget as module
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args, **kwargs: None)
    for name in ("mngrp.bin", "mngrphd.bin"):
        shutil.copy(MENU / name, tmp_path / name)
    png = tmp_path / "wrong.png"
    Image.new("RGBA", (320, 240)).save(png)
    tab = module.ShivaMagazinePictureWidget()
    tab.load_from_mngrp(_load(game_data, tmp_path))

    assert tab.replace_from_file(SLOT, str(png)) is False
    assert tab._pending == {}


def test_a_new_picture_takes_the_first_free_slot_and_is_saved(qapp, game_data, tmp_path):
    """Add new picture: slot 206 (after every slot mngrp.bin uses), its TIM in mngrp.bin and its
    mag206.TEX written at Save; the other sections stay as they were."""
    from Shiva.ShivaMagazinePicture.shivamagazinepicturewidget import ShivaMagazinePictureWidget
    for name in ("mngrp.bin", "mngrphd.bin", "mag00.TEX"):
        shutil.copy(MENU / name, tmp_path / name)
    png = tmp_path / "new.png"
    Image.new("RGBA", (256, 192), (40, 200, 40, 255)).save(png)

    manager = _load(game_data, tmp_path)
    before = [bytes(section.get_data_hex()) for section in manager.mngrp.get_section_list()]
    tab = ShivaMagazinePictureWidget()
    tab.load_from_mngrp(manager)
    assert tab.free_slots()[0] == 206
    assert tab.add_from_file(str(png)) == 206
    assert tab._current_slot() == 206
    tab.save_to_mngrp(manager)
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))

    reloaded = _load(game_data, tmp_path)
    sections = [bytes(section.get_data_hex()) for section in reloaded.mngrp.get_section_list()]
    assert sections[:206] == before[:206]
    tim = decode_tim(sections[206])
    assert tim is not None and tim.image.size == (256, 192)
    assert (tmp_path / "mag206.TEX").exists()
    assert tex_to_image(TexFile.read(str(tmp_path / "mag206.TEX"))).convert("RGB").getpixel((5, 5)) == (40, 200, 40)
    # Loaded again, the tab lists it after the game's 30
    tab.load_from_mngrp(reloaded)
    assert tab._picture_slots()[-1] == 206


def test_the_sprites_tab_shows_the_sprites_over_a_picture(qapp, game_data):
    """Shiva's Sprites tab: the same view as Zone's picker; a click selects the sprite in the editor."""
    from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget
    manager = _load(game_data, MENU)
    tab = ShivaSpriteWidget()
    tab.load_from_mngrp(manager)
    assert tab.picture_combo.currentData() == 28
    assert tab.canvas._pixmap is not None and tab.canvas.sprites
    tab._canvas_picked(8)
    assert tab.sp2_editor.sprite_list.currentRow() == 8 and tab.canvas.selected_id == 8


def test_the_games_other_data_past_185_is_not_listed_as_an_added_picture(qapp, game_data):
    """Slots 188-205 of the game's mngrp.bin hold other data: neither Shiva tab lists them."""
    from Shiva.ShivaMagazinePicture.shivamagazinepicturewidget import ShivaMagazinePictureWidget
    from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget
    manager = _load(game_data, MENU)
    pictures = ShivaMagazinePictureWidget()
    pictures.load_from_mngrp(manager)
    assert max(pictures._picture_slots()) == 184 and len(pictures._picture_slots()) == 30
    sprites = ShivaSpriteWidget()
    sprites.load_from_mngrp(manager)
    assert len(sprites._picture_slots()) == 30


def test_add_and_remove_pictures_like_sprite_ids(qapp, game_data, tmp_path):
    """Through the buttons under the list: "+ Add new picture" makes the next entry (206, 207...),
    grey until its image is set with Replace; "- Remove selected picture" removes the selected one,
    only an added one, leaving its slot for the next add; removing them all saves mngrp.bin as it was."""
    from Shiva.ShivaMagazinePicture.shivamagazinepicturewidget import ShivaMagazinePictureWidget
    for name in ("mngrp.bin", "mngrphd.bin", "mag00.TEX"):
        shutil.copy(MENU / name, tmp_path / name)
    original = (tmp_path / "mngrp.bin").read_bytes(), (tmp_path / "mngrphd.bin").read_bytes()
    manager = _load(game_data, tmp_path)
    tab = ShivaMagazinePictureWidget()
    tab.load_from_mngrp(manager)
    assert tab._current_slot() == 24 and not tab.remove_button.isEnabled()  # a game picture
    tab.add_button.click()
    tab.add_button.click()
    assert tab._picture_slots()[-2:] == [206, 207] and tab._current_slot() == 207
    assert tab.remove_button.isEnabled()
    png = tmp_path / "set.png"
    Image.new("RGBA", (256, 192), (10, 120, 220, 255)).save(png)
    assert tab.replace_from_file(207, str(png))

    tab._fill_slots(select=206)  # remove the first one: 207 keeps its slot, 206 is free again
    tab.remove_button.click()
    assert tab._picture_slots()[-1] == 207 and 206 not in tab._picture_slots()
    assert tab.free_slots()[0] == 206
    tab.add_button.click()
    assert tab._current_slot() == 206

    for slot in (206, 207):
        tab._fill_slots(select=slot)
        tab.remove_button.click()
    assert tab._picture_slots()[-1] == 184
    tab.save_to_mngrp(manager)
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    assert ((tmp_path / "mngrp.bin").read_bytes(), (tmp_path / "mngrphd.bin").read_bytes()) == original


def test_a_gap_left_by_a_removed_picture_survives_a_save(qapp, game_data, tmp_path):
    """206 removed, 207 kept: after Save and a new load, 207 is still 207 and 206 is free."""
    from Shiva.ShivaMagazinePicture.shivamagazinepicturewidget import ShivaMagazinePictureWidget
    for name in ("mngrp.bin", "mngrphd.bin", "mag00.TEX"):
        shutil.copy(MENU / name, tmp_path / name)
    manager = _load(game_data, tmp_path)
    tab = ShivaMagazinePictureWidget()
    tab.load_from_mngrp(manager)
    tab.add_button.click()
    tab.add_button.click()
    tab._fill_slots(select=206)
    tab.remove_button.click()
    tab.save_to_mngrp(manager)
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))

    reloaded = _load(game_data, tmp_path)
    tab.load_from_mngrp(reloaded)
    assert tab._picture_slots()[-1] == 207 and 206 not in tab._picture_slots()
    assert reloaded.free_slots_after(185)[0] == 206 and reloaded.last_mapped_slot() == 205
