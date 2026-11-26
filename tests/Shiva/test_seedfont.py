"""Tests for the SeeD-test preview (Shiva/ShivaSeedTest/seedfont.py and seedscreen.py).

The pure layout math (pen walk, cursor stops, line breaks) and the screen geometry run without any
game file. The exact-width checks need the real sysfnt.tdw / sysfnt.TEX and are marked ff8data.
"""
import pathlib
import shutil
import sys

import pytest

from FF8GameData.font.atlas import FontAtlas
from FF8GameData.font.textlayout import FontMetrics
from FF8GameData.gamedata import GameData
from Shiva.ShivaSeedTest.seedfont import SeedFontMetrics, layout_text, LINE_HEIGHT
from Shiva.ShivaSeedTest.seedscreen import (CROP, HAND_DX, MAX_LINES, MAX_TEXT_WIDTH, TEXT_X, TEXT_Y,
                                            fill_values, render_seed_screen)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


def test_fallback_metrics_are_uniform_and_flagged():
    metrics = SeedFontMetrics.from_folder("")  # No folder -> no tdw
    assert metrics.exact is False
    assert metrics.glyph_width(ord("W")) == metrics.glyph_width(ord("i"))  # uniform


def test_layout_counts_stops_and_lines(game_data):
    metrics = SeedFontMetrics(widths=None)  # uniform 8px, enough for structure
    text = "A\\n{Cursor_location_id:0x20}YES     {Cursor_location_id:0x21}NO"
    layout = layout_text(text, game_data, metrics)
    assert layout.line_count == 2  # one line break
    assert [stop.index for stop in layout.stops] == [0, 1]
    # both stops on the second line (y == one line height)
    assert all(stop.y == LINE_HEIGHT for stop in layout.stops)
    # the first stop sits at the start of the second line (x == 0)
    assert layout.stops[0].x == 0


def test_layout_third_choice_and_grid(game_data):
    metrics = SeedFontMetrics(widths=None)
    text = ("{Cursor_location_id:0x20}A  {Cursor_location_id:0x21}B\\n"
            "{Cursor_location_id:0x22}C  {Cursor_location_id:0x23}D")
    layout = layout_text(text, game_data, metrics)
    assert [stop.index for stop in layout.stops] == [0, 1, 2, 3]
    # A and C both start their row -> same x (left column aligned)
    assert layout.stops[0].x == layout.stops[2].x
    # top row y=0, bottom row y=LINE_HEIGHT
    assert layout.stops[0].y == 0 and layout.stops[2].y == LINE_HEIGHT


@pytest.mark.ff8data("extracted_files/menu/sysfnt.tdw")
def test_exact_widths_from_tdw(game_data):
    metrics = SeedFontMetrics.from_folder(str(MENU_DIR))
    assert metrics.exact is True

    def width(char):  # glyph_width takes an FF8 code byte, not an ASCII ord
        return metrics.glyph_width(game_data.translate_hex_to_str_table.index(char))

    # Real FF8 metrics: narrow letters are narrower than wide ones.
    assert width("i") < width("W")
    assert width("l") < width("M")


def test_the_screen_fills_its_values_in():
    text = "Level {SeedTestLevelOrScore}, next {NextSeedTestLevel}, rank {SeedRank}"
    assert fill_values(text) == "Level 7, next 8, rank 15"
    assert fill_values(text, {"SeedTestLevelOrScore": "30"}) == "Level 30, next {NextSeedTestLevel}, rank {SeedRank}"


def test_the_screen_geometry_is_the_exes():
    """Menu_SeedTest_Draw: text at (34, 35) clipped to (28, 33) 328x159, so 322 px and 10 lines."""
    assert (TEXT_X, TEXT_Y) == (34, 35)
    assert (MAX_TEXT_WIDTH, MAX_LINES) == (322, 10)
    assert HAND_DX == -26  # Menu_QueueCursorHand


def test_text_past_the_clip_is_reported_cut(game_data):
    metrics = SeedFontMetrics(widths=None)  # every glyph as wide as the widest
    short = render_seed_screen("A{Cursor_location_id:0x20}YES", 0, game_data, metrics)
    assert not short.cut and short.image.size == (CROP[2] - CROP[0], CROP[3] - CROP[1])
    wide = render_seed_screen("W" * 80, 0, game_data, metrics)
    assert wide.cut_columns > 0 and wide.cut_lines == 0
    tall = render_seed_screen("\\n".join(["A"] * 12), 0, game_data, metrics)
    assert tall.cut_lines == 2 and tall.cut_columns == 0


def test_without_any_font_the_text_is_boxes(game_data):
    screen = render_seed_screen("Hello", -1, game_data)  # no tdw, no TEX: uniform widths, boxes
    assert screen.layout.glyphs and not screen.cut


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin",
                     "extracted_files/menu/sysfnt.tdw", "extracted_files/menu/sysfnt.TEX")
def test_vanilla_questions_stay_in_the_window(game_data):
    """Every vanilla SeeD string stays within the lines the window shows, and within its width but
    for one (Test 3 question 2) whose last 2 px reach past the clip the exe sets."""
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    metrics = FontMetrics.from_tdw_bytes((MENU_DIR / "sysfnt.tdw").read_bytes())
    atlas = FontAtlas.from_file(str(MENU_DIR / "sysfnt.TEX"))
    manager = MngrpManager(game_data)
    manager.load_file(str(MENU_DIR / "mngrphd.bin"), str(MENU_DIR / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)
    for _, test in seed_tests.iter_sections():
        for seed_string in test.strings:
            screen = render_seed_screen(seed_string.get_text(), seed_string.answer, game_data, metrics, atlas)
            assert screen.cut_lines == 0
            assert screen.cut_columns <= 2


SIDE_FILES = ("sysfnt.tdw", "sysfnt.TEX", "icon.sp1", "icon.TEX")


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin",
                     *(f"extracted_files/menu/{name}" for name in SIDE_FILES))
def test_shiva_shares_the_side_files_beside_mngrp_with_the_seed_preview(tmp_path):
    """The font and the menu icons beside mngrp.bin are opened as side files (listed in the toolbar),
    and the SeeD preview draws with them; without them it says what to open."""
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from Shiva.shivawidget import ShivaWidget
    for name in ("mngrp.bin", "mngrphd.bin", *SIDE_FILES):
        shutil.copy(MENU_DIR / name, tmp_path / name)
    shiva = ShivaWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    preview = shiva.seed_test_tab.preview
    assert preview.atlas is None and preview.icons is None
    assert "sysfnt" in preview.font_notice.text() and "icon.sp1" in preview.font_notice.text()
    assert {shiva.font_source.tex_binding, shiva.icon_binding} <= set(shiva.file_bindings())

    shiva.mngrp_binding.open_path(str(tmp_path / "mngrp.bin"))
    assert preview.atlas is not None and preview.metrics is not None
    assert preview.icons is not None and preview.icons.hand is not None
    assert preview.icons.hand[0].size == (24, 16)  # the menu hand, icon.sp1 sprite 0
    assert not preview.font_notice.text()
    assert "Widest line" in preview.status_label.text()
    preview.show_string(shiva.seed_test_tab.seed_tests.general_section.strings[0])  # "...level {Next...} test?"
    preview.value_edits["NextSeedTestLevel"].setText("12")
    assert "level 12 test" in "".join(glyph.char for glyph in preview.screen.layout.glyphs)
