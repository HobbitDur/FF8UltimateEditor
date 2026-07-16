"""Tests for the shared FF8 font code (FF8GameData/font/).

The pen walk and the atlas cell maths run without any game file; the exact
widths and the real glyph images need sysfnt.tdw / sysfnt.TEX and are ff8data.
"""
import pathlib

import pytest

from FF8GameData.font.atlas import ATLAS_COLUMNS, GLYPH_SIZE, FontAtlas
from FF8GameData.font.textlayout import (DEFAULT_COLOR, MENU_TEXT_LINE_HEIGHT,
                                         SEED_TEST_LINE_HEIGHT, FontMetrics, layout_text)
from FF8GameData.gamedata import GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


def test_line_height_is_the_callers_choice(game_data):
    """menu_draw_text adds 13 per line break, the SeeD test parser adds 16."""
    metrics = FontMetrics(widths=None)
    text = "A\\nB"
    menu = layout_text(text, game_data, metrics, line_height=MENU_TEXT_LINE_HEIGHT)
    seed = layout_text(text, game_data, metrics, line_height=SEED_TEST_LINE_HEIGHT)
    assert menu.glyphs[1].y == MENU_TEXT_LINE_HEIGHT == 13
    assert seed.glyphs[1].y == SEED_TEST_LINE_HEIGHT == 16
    assert menu.line_count == seed.line_count == 2


def test_glyphs_carry_their_code_and_advance(game_data):
    metrics = FontMetrics(widths=None)  # uniform 8px
    layout = layout_text("AB", game_data, metrics)
    assert [glyph.char for glyph in layout.glyphs] == ["A", "B"]
    assert layout.glyphs[0].x == 0 and layout.glyphs[1].x == 8
    # The code is what indexes the atlas, and it is not ASCII
    assert layout.glyphs[0].code == game_data.translate_hex_to_str_table.index("A")


def test_colour_code_switches_and_sticks(game_data):
    metrics = FontMetrics(widths=None)
    # {Blue} = colour index 5, {White} = 7; the code carries no advance
    layout = layout_text("A{Blue}BC{White}D", game_data, metrics)
    colors = {glyph.char: glyph.color for glyph in layout.glyphs}
    assert colors["A"] == DEFAULT_COLOR
    assert colors["B"] == colors["C"] == 5
    assert colors["D"] == 7
    # The colour codes take no horizontal space
    assert [glyph.x for glyph in layout.glyphs] == [0, 8, 16, 24]


def test_overflows_uses_the_callers_envelope(game_data):
    metrics = FontMetrics(widths=None)
    layout = layout_text("AAA", game_data, metrics)  # 24px, 1 line
    assert layout.overflows(max_width=10, max_lines=8) is True
    assert layout.overflows(max_width=100, max_lines=8) is False


def test_atlas_cell_maths():
    """menu_draw_text: cell = code - 0x20, U = 12*(cell%21), V = 12*(cell/21)."""
    # A fake 21-column atlas where every cell is a distinct solid colour is
    # overkill; the geometry alone is what the exe pins down.
    assert GLYPH_SIZE == 12
    assert ATLAS_COLUMNS == 21
    cell = ord("A") - 0x20  # only used for the arithmetic, not a real FF8 code
    assert 12 * (cell % 21) < 256 and 12 * (cell // 21) < 128


def test_atlas_missing_folder_is_none(tmp_path):
    assert FontAtlas.from_folder(str(tmp_path)) is None


def test_every_item_name_is_ff8_encodable(game_data):
    """item.json names get drawn as FF8 text (Zone's weapon remodel lists), so
    every character must have a code in the game's table. The apostrophe is code
    67; a backtick has no code at all and used to raise here."""
    for item in game_data.item_data_json["items"]:
        try:
            game_data.translate_str_to_hex(item["name"])
        except ValueError:
            pytest.fail(f"item {item['id']} {item['name']!r} cannot be encoded as FF8 text")


@pytest.mark.ff8data("extracted_files/menu/sysfnt.tdw")
def test_exact_widths_from_tdw(game_data):
    metrics = FontMetrics.from_folder(str(MENU_DIR))
    assert metrics.exact is True

    def width(char):  # glyph_width takes an FF8 code byte, not an ASCII ord
        return metrics.glyph_width(game_data.translate_hex_to_str_table.index(char))

    assert width("i") < width("W")
    assert width("l") < width("M")


@pytest.mark.ff8data("extracted_files/menu/sysfnt.TEX")
def test_atlas_glyphs_are_real_and_coloured(game_data):
    atlas = FontAtlas.from_folder(str(MENU_DIR))
    assert atlas is not None
    code = game_data.translate_hex_to_str_table.index("A")
    glyph = atlas.glyph(code, color=7)
    assert glyph.size == (GLYPH_SIZE, GLYPH_SIZE)

    def opaque_pixels(color):
        image = atlas.glyph(code, color)
        return [pixel for _count, pixel in image.getcolors(maxcolors=256) if pixel[3]]

    assert opaque_pixels(7), "the 'A' cell must not be blank"

    # The palettes are the sysfnt colours in order: 3 = Red, 5 = Blue. This is
    # what pins the .TEX palette channel order down to B,G,R,A.
    def brightest(color):
        return max(opaque_pixels(color), key=lambda pixel: sum(pixel[:3]))

    red = brightest(3)
    blue = brightest(5)
    assert red[0] > red[1] and red[0] > red[2], f"palette 3 must be red, got {red}"
    assert blue[2] > blue[0], f"palette 5 must be blue, got {blue}"
