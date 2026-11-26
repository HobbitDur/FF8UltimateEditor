"""SeeD-test text layout: the common FF8 pen walk (FF8GameData.font.textlayout)
pinned to the SeeD test's own line height. The screen it is drawn on, and what
the game cuts off, is in seedscreen.py.

Menu_SeedTest_ParseCursorStops (0x4D4A80) adds 16 per line break where the
generic menu_draw_text adds 13, so the SeeD preview must lay out with 16.
"""
from FF8GameData.font.textlayout import (FontMetrics, SEED_TEST_LINE_HEIGHT,
                                         layout_text as _layout_text)

LINE_HEIGHT = SEED_TEST_LINE_HEIGHT  # The SeeD test parser adds 16 on every line break

SeedFontMetrics = FontMetrics  # The widths are the common ones, only the walk differs


def layout_text(text_str, game_data, metrics):
    """Lay out one question's text the way the SeeD test screen does.

    The answer byte is not part of the text (the engine reads it separately), so
    only the FF8 text is walked, starting at pen (0, 0)."""
    return _layout_text(text_str, game_data, metrics, line_height=LINE_HEIGHT)
