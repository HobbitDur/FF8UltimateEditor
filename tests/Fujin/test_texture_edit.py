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
from Fujin.texturepictureview import TimTexture, palette_from_image, palette_grid, tim_blocks

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


@pytest.mark.ff8data(ATLAS)
def test_video_memory_position(tmp_path):
    manager = document(tmp_path, ATLAS)
    tim = texture(manager)
    vram = tim.vram()
    assert vram["picture"][2:] == (256, 256) and vram["palette"][2:] == (256, 2)   # 512 texels = 256 units
    tim.set_vram("picture", 640, 0)
    tim.set_vram("palette", 512, 480)
    assert tim.vram()["picture"][:2] == (640, 0) and tim.vram()["palette"][:2] == (512, 480)
    assert tim.picture(0).shape == (256, 512, 4)               # the picture itself does not move
    with pytest.raises(ValueError, match="multiple of 16"):
        tim.set_vram("palette", 520, 0)
    with pytest.raises(ValueError, match="leaves"):
        tim.set_vram("picture", 800, 0)
    manager.undo()
    manager.undo()
    assert tim.vram() == vram and not manager.modified


@pytest.mark.ff8data(ATLAS)
def test_semi_transparency(tmp_path):
    manager = document(tmp_path, ATLAS)
    tim = texture(manager)
    rows = tim.palette_rows()
    # Cure's sprites are blended: every visible colour of its atlas is semi-transparent
    index = next(i for i, word in enumerate(rows[0]) if word & 0x7FFF)
    assert tim.semi_transparent(0, index) and tim.palette_image()[0, index, 3] == 128
    tim.set_semi_transparent(0, index, False)
    assert not tim.semi_transparent(0, index) and tim.palette_image()[0, index, 3] == 255
    tim.set_semi_transparent(0, index, True)
    assert not manager.modified
    if 0x8000 in rows[0]:
        with pytest.raises(ValueError, match="black"):
            tim.set_semi_transparent(0, rows[0].index(0x8000), False)
    if 0 in rows[0]:
        with pytest.raises(ValueError, match="fully transparent"):
            tim.set_semi_transparent(0, rows[0].index(0), True)
    # PNG alpha carries it: 128 = semi-transparent, 255 = opaque
    palette = tim.palette_image()
    palette[0, index, 3] = 255
    tim.set_palette(palette)
    assert not tim.semi_transparent(0, index)
    palette[0, index, 3] = 128
    tim.set_palette(palette)
    assert not manager.modified


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
    picture[0, 1] = (255, 0, 0, 128)                  # alpha 128: semi-transparent texel
    tim.set_picture(picture)
    assert tim.picture()[0, 1, 3] == 128


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
    assert fujin.textures.display.widget(0) is fujin.textures.panel   # the pictures first, then the sections
    card = fujin.textures.panel.cards[0]
    picture_png, palette_png = card.export_pngs(str(tmp_path), "atlas")
    # the palette PNG is laid out like the swatches: 16 colours per line, 2 rows of 256 = 32 lines
    assert Image.open(picture_png).size == (512, 256) and Image.open(palette_png).size == (16, 32)
    palette = palette_from_image(np.asarray(Image.open(palette_png).convert("RGBA")), 256)
    pixels = np.asarray(Image.open(picture_png).convert("RGBA")).copy()
    pixels[:2, :2] = next(colour for colour in palette[0] if colour[3] and tuple(colour) != tuple(pixels[0, 0]))
    Image.fromarray(pixels, "RGBA").save(tmp_path / "edited.png")
    assert card.import_picture(str(tmp_path / "edited.png"))
    assert fujin.can_save_folder() and fujin.modified_effects() and "modified" in fujin.textures.panel.cards[0].info.text()
    assert card.import_palette(palette_png)                   # its own export back: nothing moves
    card._pick_colour(1 + 3 * 12 + 2, 1 + 1 * 12 + 2)          # palette row 0, line 1, column 3
    assert card.colour == (0, 19) and "Row 0, colour 19" in card.colour_info.text()
    card._pick_colour(1 + 3 * 12 + 2, 1 + (16 * 12 + 4) + 2)    # second row block
    assert card.colour == (1, 3)
    card.vram_boxes["picture", 0].setValue(640)
    assert card.texture.vram()["picture"][:2][0] == 640
    card.texture.manager.undo()
    assert fujin.save_files()                                  # Save writes the .tim in place and says so
    assert path.read_bytes() != (ROOT / ATLAS).read_bytes() and not fujin.can_save_folder()
    assert "saved mag000-049.tim" in fujin.context.text() and str(path) in fujin.context.toolTip()
    fujin.textures.activate()
    assert "modified" not in fujin.textures.panel.cards[0].info.text()


def test_palette_png_layouts():
    palette = np.arange(2 * 256 * 4, dtype=np.uint32).astype(np.uint8).reshape(2, 256, 4)
    grid = palette_grid(palette)
    assert grid.shape == (32, 16, 4) and (grid[16] == palette[1, :16]).all()
    assert (palette_from_image(grid, 256) == palette).all()          # the on-screen layout
    assert (palette_from_image(palette, 256) == palette).all()       # one row per line (older exports)
    assert palette_grid(palette[:, :16]).shape == (2, 16, 4)         # 4-bit: a row is one line
    with pytest.raises(ValueError, match="16 pixels wide"):
        palette_from_image(grid[:20], 256)
