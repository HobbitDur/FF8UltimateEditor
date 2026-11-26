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
