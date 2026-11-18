"""FF8 font files (.tdw) (FF8GameData/font/tdwfile.py).

Synthetic fonts cover both layouts (Latin: 8 palettes, 16 levels; Japanese: 16+ palettes, two glyphs
per cell, 2 bits each); the real sysfnt.tdw / sysfnt.TEX checks are ff8data."""
import pathlib
import struct

import pytest

from FF8GameData.font.tdwfile import TABLE_SIZE, TdwFile

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


def make_tdw(width_bytes: bytes, palettes: int, height: int, clut_rows_in_header: int = None) -> bytes:
    """A tdw: width block + 4bpp 256-px TIM. Palette p, entry i = grey level 8*i + p (so each entry
    is distinct); the CLUT row count in its header can be wrong, as in the Japanese game file."""
    clut = b"".join(struct.pack("<H", (min(31, i + p) << 10) | (i << 5) | p if i else 0)
                    for p in range(palettes) for i in range(16))
    tim = struct.pack("<II", 0x10, 0x08)
    tim += struct.pack("<IHHHH", 12 + len(clut), 0, 480, 16, clut_rows_in_header or palettes) + clut
    pixels = bytes(256 * height // 2)
    tim += struct.pack("<IHHHH", 12 + len(pixels), 0, 0, 64, height) + pixels
    return struct.pack("<II", 8, 8 + len(width_bytes)) + width_bytes + tim


def test_latin_widths_and_levels_round_trip():
    data = make_tdw(bytes([0x58, 0x07]) + bytes(98), palettes=8, height=120)
    tdw = TdwFile(data)
    assert (tdw.table_count, tdw.char_count(0), tdw.optimized, tdw.level_count) == (1, 200, False, 16)
    assert [tdw.char_width(0, i) for i in range(3)] == [8, 5, 7]
    assert tdw.to_bytes() == data  # unchanged file saves back identical

    tdw.set_char_width(0, 1, 12)
    tdw.set_level(22, 3, 4, 13)  # glyph 22: column 1, row 1 -> pixel (12+3, 12+4)
    assert tdw.letter_origin(22) == (12, 12)
    assert tdw.char_width(0, 0) == 8 and tdw.char_width(0, 1) == 12
    saved = TdwFile(tdw.to_bytes())
    assert saved.char_width(0, 1) == 12 and saved.level(22, 3, 4) == 13
    assert saved.pixels[(12 + 4) * 256 + 12 + 3] == 13


def test_japanese_glyphs_share_cells_two_bits_each():
    width_bytes = bytes(3 * 112 + 108)  # tables of 224, 224, 224, 216 glyphs
    data = make_tdw(width_bytes, palettes=32, height=252, clut_rows_in_header=16)
    tdw = TdwFile(data)
    assert tdw.optimized and tdw.level_count == 4
    assert [tdw.char_count(t) for t in range(4)] == [224, 224, 224, 216]
    ki_field, ki_menu = tdw.glyph_id(2, 0xc8 - 0x20), tdw.glyph_id(3, 0xa1 - 0x20)  # 記 at 1a c8 and 1b a1
    assert (ki_field, ki_menu) == (616, 801)
    assert tdw.letter_origin(616) == (14 * 12, 14 * 12)  # cell 308: column 14, row 14
    assert tdw.letter_origin(617) == tdw.letter_origin(616)  # its odd neighbour shares the cell

    tdw.set_level(616, 0, 0, 3)
    tdw.set_level(617, 0, 0, 2)
    assert tdw.level(616, 0, 0) == 3 and tdw.level(617, 0, 0) == 2
    assert tdw.pixels[14 * 12 * 256 + 14 * 12] == 3 | 2 << 2
    # a level is shown with the colour of its own bits: palette 2*colour (even) or 2*colour + 1 (odd)
    assert tdw.level_colors(7, 616)[3] == tdw.palette(14)[3]
    assert tdw.level_colors(7, 617)[2] == tdw.palette(15)[2 << 2]
    assert TdwFile(tdw.to_bytes()).levels(616) == tdw.levels(616)


@pytest.mark.ff8data("extracted_files/menu/sysfnt.tdw", "extracted_files/menu/sysfnt.TEX")
def test_real_sysfnt_round_trips_and_matches_its_texture():
    data = (MENU_DIR / "sysfnt.tdw").read_bytes()
    tdw = TdwFile(data)
    assert tdw.to_bytes() == data
    assert (tdw.table_count, tdw.char_count(0), tdw.width, tdw.height) == (1, 200, 256, 120)
    from FF8GameData.font.lowresfont import LowresFont
    lowres = LowresFont(japanese=False)
    lowres.attach(str(MENU_DIR / "sysfnt.TEX"))
    # sysfnt.TEX (what the PC game draws) has the tdw's glyphs, plus 5 the tdw lacks in the English
    # game (codes cc-d0: glyphs 172-176)
    different = [glyph for glyph in range(200) if lowres.levels(glyph) != tdw.levels(glyph)]
    assert set(different) <= set(range(172, 177))
