"""Tests for the SeeD-test layout preview logic (Shiva/ShivaSeedTest/seedfont.py).

The pure layout math (pen walk, cursor stops, line breaks) runs without any game
file. The exact-width checks need the real sysfnt.tdw and are marked ff8data.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Shiva.ShivaSeedTest.seedfont import (SeedFontMetrics, layout_text, LINE_HEIGHT,
                           VANILLA_MAX_WIDTH, VANILLA_MAX_LINES)

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


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin",
                     "extracted_files/menu/sysfnt.tdw")
def test_all_vanilla_questions_fit_envelope(game_data):
    """Every vanilla SeeD string lays out within the envelope the preview flags."""
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    metrics = SeedFontMetrics.from_folder(str(MENU_DIR))
    manager = MngrpManager(game_data)
    manager.load_file(str(MENU_DIR / "mngrphd.bin"), str(MENU_DIR / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)
    for _, test in seed_tests.iter_sections():
        for seed_string in test.strings:
            layout = layout_text(seed_string.get_text(), game_data, metrics)
            assert layout.max_width <= VANILLA_MAX_WIDTH
            assert layout.line_count <= VANILLA_MAX_LINES
