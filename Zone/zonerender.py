"""The page renderer now lives in the shared workplace (it renders both mmag.bin
and mmag2.bin): FF8GameData.menu.pagerender. This module re-exports it so the
existing Zone imports keep working."""
from FF8GameData.menu.pagerender import (  # noqa: F401
    BACKDROP_COLOR, BACKGROUND_COLOR, BUTTON_BOX, BUTTON_STYLE_BOXES, BUTTON_STYLE_ICONS,
    BUTTON_STYLES, CANVAS_HEIGHT, CANVAS_WIDTH, DUEL_BUTTON_STEP, PageRenderer)
