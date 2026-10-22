"""Fujin's Textures tab: TIM pictures and palettes exported as PNG and replaced by PNG, in place
(same size), undoable, restorable; no raw byte tabs."""
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from Fujin.magdocument import MagDocument
from Fujin.texturepictureview import TimTexture, tim_blocks

ROOT = Path(__file__).resolve().parents[2]
ATLAS = "extracted_files/magic/mag000-049.tim"     # 8-bit, 2 palette rows (Cure's atlas)
FOUR_BIT = "extracted_files/magic/mag176.tim"
CURE = 1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def document(tmp_path, name):
    path = tmp_path / Path(name).name
    shutil.copyfile(ROOT / name, path)
    manager = MagDocument()
    manager.load_file(str(path))
    return manager


def texture(manager, index=0):
    return TimTexture(manager, tim_blocks(manager)[index][0])


@pytest.mark.ff8data(ATLAS, FOUR_BIT)
@pytest.mark.parametrize("name", [ATLAS, FOUR_BIT])
def test_picture_round_trip_and_edit(tmp_path, name):
    manager = document(tmp_path, name)
    tim = texture(manager)
    picture = tim.picture(0)
    tim.set_picture(picture, 0)                       # the same picture back: not a single byte moves
    assert not manager.modified
    edited = picture.copy()
    colour = tim.palette_image()[0][1]                # paint a corner with palette colour 1
    edited[:4, :4] = colour
    size = len(manager.data)
    tim.set_picture(edited, 0)
    assert manager.modified and len(manager.data) == size and tim.is_modified()
    assert (tim.picture(0)[:4, :4] == colour).all() and (tim.picture(0)[8:] == picture[8:]).all()
    manager.undo()
    assert not manager.modified
    tim.set_picture(edited, 0)
    tim.restore()
    assert not manager.modified
    with pytest.raises(ValueError, match="pixels"):
        tim.set_picture(picture[:-1], 0)


@pytest.mark.ff8data(ATLAS)
def test_palette_rows_replace(tmp_path):
    manager = document(tmp_path, ATLAS)
    tim = texture(manager)
    palette = tim.palette_image()
    assert palette.shape[:2] == (2, 256)
    tim.set_palette(palette)                          # unchanged palette: same bytes
    assert not manager.modified
    row = palette[1:2].copy()
    row[0, 5] = (255, 0, 0, 255)
    tim.set_palette(row, start_row=1)                 # one row of two
    after = tim.palette_image()
    assert tuple(after[1, 5][:3]) == (255, 0, 0) and (after[0] == palette[0]).all()   # its STP bit is kept
    with pytest.raises(ValueError, match="colours per row"):
        tim.set_palette(palette[:, :16])


def test_sixteen_bit_picture(tmp_path):
    width, height = 4, 2
    words = [0x7FFF, 0x001F, 0x0000, 0x8000] * 2
    raw = struct.pack("<II", 0x10, 2) + struct.pack("<IHHHH", 12 + 2 * len(words), 0, 0, width, height)
    raw += struct.pack(f"<{len(words)}H", *words)
    path = tmp_path / "direct.tim"
    path.write_bytes(raw)
    manager = MagDocument()
    manager.load_file(str(path))
    tim = texture(manager)
    assert tim.palette_rows() == [] and tim.palette_image() is None
    picture = tim.picture()
    tim.set_picture(picture)
    assert not manager.modified                       # transparent and opaque-black texels kept
    picture[0, 0] = (0, 255, 0, 255)
    tim.set_picture(picture)
    assert tuple(tim.picture()[0, 0]) == (0, 255, 0, 255)


@pytest.mark.ff8data(ATLAS)
def test_textures_tab_exports_and_imports_png(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    path = tmp_path / "mag000-049.tim"
    shutil.copyfile(ROOT / ATLAS, path)
    fujin = FujinWidget()
    assert fujin.tabs.tabText(4) == "Textures"
    fujin.import_paths([str(path)])
    fujin.select_effect(CURE)
    fujin.tabs.setCurrentIndex(4)
    fujin.textures.activate()
    assert fujin.textures.display is fujin.textures.panel       # no raw byte tab here
    card = fujin.textures.panel.cards[0]
    picture_png, palette_png = card.export_pngs(str(tmp_path), "atlas")
    assert Image.open(picture_png).size == (512, 256) and Image.open(palette_png).size == (256, 2)
    pixels = np.asarray(Image.open(picture_png).convert("RGBA")).copy()
    pixels[:2, :2] = next(colour for colour in np.asarray(Image.open(palette_png).convert("RGBA"))[0]
                          if colour[3] and tuple(colour) != tuple(pixels[0, 0]))
    Image.fromarray(pixels, "RGBA").save(tmp_path / "edited.png")
    assert card.import_picture(str(tmp_path / "edited.png"))
    assert fujin.can_save_folder() and fujin.modified_effects() and "modified" in fujin.textures.panel.cards[0].info.text()
