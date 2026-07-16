"""SeeD-test text layout: the common FF8 pen walk (FF8GameData.font.textlayout)
pinned to the SeeD test's own line height, plus the vanilla envelope the preview
flags.

Menu_SeedTest_ParseCursorStops (0x4D4A80) adds 16 per line break where the
generic menu_draw_text adds 13, so the SeeD preview must lay out with 16.
"""
from FF8GameData.font.textlayout import (FontMetrics, SEED_TEST_LINE_HEIGHT,
                                         layout_text as _layout_text)

LINE_HEIGHT = SEED_TEST_LINE_HEIGHT  # The SeeD test parser adds 16 on every line break

# Envelope the vanilla SeeD tests stay within (widest vanilla line = 325 px,
# tallest question = 8 lines). Staying inside it renders like the retail game.
VANILLA_MAX_WIDTH = 325
VANILLA_MAX_LINES = 8

SeedFontMetrics = FontMetrics  # The widths are the common ones, only the walk differs


def layout_text(text_str, game_data, metrics):
    """Lay out one question's text the way the SeeD test screen does.

    The answer byte is not part of the text (the engine reads it separately), so
    only the FF8 text is walked, starting at pen (0, 0)."""
    return _layout_text(text_str, game_data, metrics, line_height=LINE_HEIGHT)


def overflows(layout):
    """True when a laid-out question leaves the vanilla envelope."""
    return layout.overflows(VANILLA_MAX_WIDTH, VANILLA_MAX_LINES)
