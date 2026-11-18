"""The high-resolution game font (FF8GameData/font/hiresfont.py): synthetic Latin (sysfld00/01) and
Japanese (sysevn/sysodd 00-03) tiles, and the real English sysfld00/01 (ff8data)."""
import pathlib

import pytest

from FF8GameData.font.hiresfont import CELL, HiresFont
from FF8GameData.tex.texfile import TexFile

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
HIRES_DIR = PROJECT_ROOT / "extracted_files" / "menu" / "hires"


def make_tile(path, palettes, entries, fill=0):
    palette = bytes(b for p in range(palettes) for i in range(entries) for b in (i, i, p, 255 if i else 0))
    TexFile(bytes(240), palette, bytearray([fill] * 256 * 256), palettes, entries, 8, 256, 256).write(str(path))


def make_latin(folder):
    for name in ("sysfld00.TEX", "sysfld01.tex"):  # the case differs between game versions
        make_tile(folder / name, 8, 256)


def make_japanese(folder):
    for kind in ("evn", "odd"):
        for i in range(4):
            make_tile(folder / f"sys{kind}{i:02d}.TEX", 16, 16)


def test_latin_page_spans_two_tiles(tmp_path):
    make_latin(tmp_path)
    font = HiresFont.from_path(str(tmp_path / "sysfld01.tex"))  # any tile finds the others
    assert not font.japanese and len(font.paths) == 2
    assert font.has_letter(209) and not font.has_letter(210)  # 21 x 10 cells of 24 px in 256 rows
    font.set_level(10, 20, 0, 200)  # glyph 10: x 240-263, so its pixel 20 is in the second tile
    font.set_level(10, 3, 0, 1)
    font.write()
    left, right = (TexFile.read(str(tmp_path / name)) for name in ("sysfld00.TEX", "sysfld01.tex"))
    assert left.pixels[243] == 1 and right.pixels[260 - 256] == 200
    assert HiresFont.from_path(str(tmp_path / "sysfld00.TEX")).level(10, 20, 0) == 200
    assert font.level_color(7, 10, 200) == (7, 200, 200, 255)  # palette = text colour, entry = value (B,G,R,A on disk)


def test_japanese_even_and_odd_glyphs_are_in_their_own_page_and_bits(tmp_path):
    make_japanese(tmp_path)
    font = HiresFont.from_path(str(tmp_path / "sysodd02.TEX"))
    assert font.japanese and len(font.paths) == 8 and font.level_values == [0, 1, 2, 3]
    # 記 at 1a c8 = glyph 616 (even, sysevn) and 1b a1 = glyph 801 (odd, sysodd): both at row/col 14/14
    # and 1/19 of their page, 24 px cells
    font.set_level(616, 0, 0, 3)
    font.set_level(801, 0, 0, 2)
    font.write()
    evn = TexFile.read(str(tmp_path / "sysevn03.TEX"))  # (336, 336): bottom-right tile
    odd = TexFile.read(str(tmp_path / "sysodd02.TEX"))  # (24, 456): bottom-left tile
    assert evn.pixels[(336 - 256) * 256 + 336 - 256] == 3
    assert odd.pixels[(456 - 256) * 256 + 24] == 2 << 2
    assert not font.has_letter(882)


@pytest.mark.ff8data("extracted_files/menu/hires/sysfld00.TEX", "extracted_files/menu/hires/sysfld01.TEX")
def test_real_latin_hires_font_reads_and_saves_unchanged(tmp_path):
    import shutil
    for name in ("sysfld00.TEX", "sysfld01.TEX"):
        shutil.copy(HIRES_DIR / name, tmp_path / name)
    font = HiresFont.from_path(str(tmp_path / "sysfld00.TEX"))
    assert any(font.levels(0x21 - 0x20))  # "0" has pixels
    font.write()
    for name in ("sysfld00.TEX", "sysfld01.TEX"):
        assert (tmp_path / name).read_bytes() == (HIRES_DIR / name).read_bytes()
