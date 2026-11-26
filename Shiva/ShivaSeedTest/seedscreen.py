"""The SeeD written test screen as the game draws it, into a PIL image (no Qt here).

Everything below comes from the PC exe:

* Menu_SeedTest_Draw (sub_4D58A0, 0x4D58A0) draws three menu windows: a title bar at (24, 6)
  244x22, the question window at (24, 29) 336x167 and a help bar at (24, 196) 336x20. The
  question text starts at (34, 35) and is clipped to the draw area (28, 33) 328x159 (set with
  BattleUI_EmitDrawAreaRelativeToDrawEnv just before it): what passes x 356 or y 192 is cut off.
* Menu_SeedTest_ParseCursorStops (0x4D4A80) walks the text after expanding its values, adds 16
  per line break, and records each cursor stop (code 0x0B) at the pen position; the choice is the
  stop's order. Menu_SeedTest_Update queues the hand at (stop + (34, 35)), and
  Menu_QueueCursorHand draws it 26 px left of that and 3 px lower.
* The values {SeedTestLevelOrScore} {NextSeedTestLevel} {SeedRank} (code 0x0A 0x20/0x22/0x26) are
  digits (the rank: digits, or "A") filled in when the screen opens; the preview puts sample
  values in, so the line widths and the cursor stops after them are where the game puts them.

* The windows and the hand come from icon.sp1 / icon.TEX (MenuIcons): Menu_DrawWindowFrame's
  border is the 24x24 bevel at (16, 0) of icon.TEX (palette 0, CLUT 0x3810) cut in 8 px corners and
  edges, and the queued hand is drawn by sub_4BDA00 as icon.sp1 sprite 0. Without those files a
  plain outline and a drawn hand stand in.

* The window fill (BattleUI_DrawWindowBorder 0x4B6A80, called with texture origin 8) is textured too:
  128 px wide strips from icon.TEX's page with palette 1 (CLUT 0x3850), the first one starting at
  u = 8, under the texture window 0xE20303D0 (table 0xB87CD0) that keeps u in 0-127 and v in 48-63.
  So the fill is the 128x16 band at (0, 48) of icon.TEX, a left-dark right-light grey gradient,
  repeated across and down. The game tints it with the player's Config > Window colour; the preview
  shows it untinted (the default).

The title and help bars' own text comes from another file (the menu strings), so they are drawn
empty.
"""
import os

from PIL import Image, ImageDraw

from FF8GameData.font.atlas import GLYPH_SIZE
from FF8GameData.font.textlayout import FontMetrics
from Shiva.ShivaSeedTest.seedfont import layout_text

TITLE_WINDOW = (24, 6, 244, 22)
QUESTION_WINDOW = (24, 29, 336, 167)
HELP_WINDOW = (24, 196, 336, 20)
TEXT_X, TEXT_Y = 34, 35
TEXT_CLIP = (28, 33, 328, 159)  # x, y, width, height
HAND_DX, HAND_DY = -26, 3

CLIP_RIGHT = TEXT_CLIP[0] + TEXT_CLIP[2]   # 356: first column cut off
CLIP_BOTTOM = TEXT_CLIP[1] + TEXT_CLIP[3]  # 192: first row cut off
MAX_TEXT_WIDTH = CLIP_RIGHT - TEXT_X       # 322 px of ink from the text start
MAX_LINES = (CLIP_BOTTOM - TEXT_Y - GLYPH_SIZE) // 16 + 1  # 10 lines of 16 px fit

# The part of the 384x240 menu screen the preview shows: the three windows and a small margin.
CROP = (16, 0, 368, 222)

# Sample values for the codes the screen fills in (name in the editor's text -> digits).
SAMPLE_VALUES = {"SeedTestLevelOrScore": "7", "NextSeedTestLevel": "8", "SeedRank": "15"}

HAND_ICON = 0         # the icon.sp1 sprite sub_4BDA00 draws for a queued hand
FRAME_BOX = (16, 0, 40, 24)  # the window bevel in icon.TEX (palette 0)
FRAME_CORNER = 8
FILL_BOX = (0, 48, 128, 64)  # the window fill band in icon.TEX (palette 1), see the module docstring
FILL_PALETTE = 1
FILL_FIRST_U = 8             # the first strip starts 8 texels into the band

BACKDROP = (0, 0, 0, 255)
WINDOW_LEFT = (65, 60, 58)   # without icon.TEX: the band's gradient, left to right
WINDOW_RIGHT = (98, 96, 95)
WINDOW_EDGE = (160, 160, 160, 255)  # without icon.TEX: a plain outline
WINDOW_SHADOW = (40, 40, 40, 255)
BOX_FILL = (210, 210, 210, 170)  # a glyph without sysfnt.TEX: a box of its true width
HAND_COLOR = (250, 240, 200, 255)
EXPECTED_HAND_COLOR = (110, 230, 130, 255)
HAND_OUTLINE = (40, 30, 20, 255)


class MenuIcons:
    """icon.sp1 and the icon.TEX beside it: the menu's cursor hand and window bevel."""

    def __init__(self, sp1_path):
        from FF8GameData.tex.texfile import TexFile
        from Minimog.minimogmanager import MinimogManager
        tex_path = os.path.join(os.path.dirname(sp1_path), "icon.TEX")
        if not os.path.exists(tex_path):
            raise FileNotFoundError(f"icon.TEX holds the pixels icon.sp1 points at, not found at: {tex_path}")
        self.sprites = MinimogManager()
        self.sprites.load_file(sp1_path)
        texture = TexFile.read(tex_path)
        self.frame = texture.to_image(0).convert("RGBA").crop(FRAME_BOX)
        self.fill_band = texture.to_image(FILL_PALETTE).convert("RGBA").crop(FILL_BOX)
        icon = self.sprites.icons[HAND_ICON] if HAND_ICON < len(self.sprites.icons) else None
        image = self.sprites.render_icon(HAND_ICON, texture) if icon is not None else None
        # (image, where its top-left sits from the draw position)
        self.hand = None if image is None else (image.convert("RGBA"), *icon.bounding_box()[:2])


def fill_values(text, values=None):
    """The text with the screen's values put in (sample ones by default), as the game shows it."""
    for name, value in (values or SAMPLE_VALUES).items():
        text = text.replace("{" + name + "}", str(value))
    return text


class SeedScreen:
    """One question drawn: `image` (the CROP part of the screen, 1 game pixel = 1 pixel), the
    `layout` (pen positions from the text start), and what the game cuts off."""

    def __init__(self, image, layout, ink_right, cut_columns, cut_lines):
        self.image = image
        self.layout = layout
        self.ink_right = ink_right      # px of ink from the text start, on the widest line
        self.cut_columns = cut_columns  # px of ink past the clip on the right (0: none)
        self.cut_lines = cut_lines      # lines past the clip at the bottom (0: none)

    @property
    def cut(self):
        return bool(self.cut_columns or self.cut_lines)


def _window_fill(width, height, icons):
    """The window fill: icon.TEX's 128x16 band repeated across (the first strip from u = 8) and down;
    without icon.TEX, the band's gradient drawn plain."""
    if icons is not None:
        band = icons.fill_band
    else:
        band = Image.new("RGBA", (FILL_BOX[2] - FILL_BOX[0], FILL_BOX[3] - FILL_BOX[1]))
        draw = ImageDraw.Draw(band)
        for column in range(band.width):
            t = column / (band.width - 1)
            draw.line((column, 0, column, band.height),
                      fill=tuple(round(a + (b - a) * t) for a, b in zip(WINDOW_LEFT, WINDOW_RIGHT)) + (255,))
    fill = Image.new("RGBA", (width, height))
    x = -FILL_FIRST_U
    while x < width:
        for y in range(0, height, band.height):
            fill.paste(band, (x, y))
        x += band.width
    return fill


def _draw_window(screen, box, icons):
    """The window fill (see _window_fill), then its border: icon.TEX's bevel cut in 8 px corners
    and edges when icons are loaded, else a plain outline."""
    x, y, width, height = box
    screen.alpha_composite(_window_fill(width, height, icons), (x, y))
    if icons is None:
        draw = ImageDraw.Draw(screen)
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=WINDOW_EDGE)
        draw.rectangle((x + 1, y + 1, x + width - 2, y + height - 2), outline=WINDOW_SHADOW)
        return
    frame, c = icons.frame, FRAME_CORNER
    size = frame.width
    right, bottom = x + width - c, y + height - c
    for tile_x in range(x + c, right, c):  # top and bottom edges, the bevel's middle 8 px repeated
        w = min(c, right - tile_x)
        screen.alpha_composite(frame.crop((c, 0, c + w, c)), (tile_x, y))
        screen.alpha_composite(frame.crop((c, size - c, c + w, size)), (tile_x, bottom))
    for tile_y in range(y + c, bottom, c):  # left and right edges
        h = min(c, bottom - tile_y)
        screen.alpha_composite(frame.crop((0, c, c, c + h)), (x, tile_y))
        screen.alpha_composite(frame.crop((size - c, c, size, c + h)), (right, tile_y))
    for (u, v), position in (((0, 0), (x, y)), ((size - c, 0), (right, y)),
                             ((0, size - c), (x, bottom)), ((size - c, size - c), (right, bottom))):
        screen.alpha_composite(frame.crop((u, v, u + c, v + c)), position)


def _draw_hand(screen, x, y, icons, expected):
    """The menu's hand (icon.sp1 sprite 0) at the engine's position; without it, a drawn one. The
    expected answer's hand gets a green mark under it (the game shows no such thing)."""
    draw = ImageDraw.Draw(screen)
    if expected:
        draw.rectangle((x + 2, y + 14, x + 21, y + 15), fill=EXPECTED_HAND_COLOR)
    if icons is not None and icons.hand is not None:
        image, dx, dy = icons.hand
        screen.alpha_composite(image, (x + dx, y + dy))
        return
    color = EXPECTED_HAND_COLOR if expected else HAND_COLOR
    draw.rounded_rectangle((x, y + 2, x + 13, y + 11), radius=3, fill=color, outline=HAND_OUTLINE)
    draw.rectangle((x + 12, y + 3, x + 22, y + 6), fill=color, outline=HAND_OUTLINE)


def _ink_right(glyph, atlas):
    """Where the glyph's ink ends, from the text start (its cell's last opaque column + 1)."""
    image = atlas.glyph(glyph.code, glyph.color) if atlas is not None else None
    if image is not None:
        box = image.getchannel("A").getbbox()
        return glyph.x + (box[2] if box else 0)
    return glyph.x + max(glyph.width - 1, 0)


def render_seed_screen(text, answer, game_data, metrics=None, atlas=None, values=None, icons=None):
    """Draw one SeeD test string (`text` as the editor shows it, `answer` its expected choice)
    on the test screen. `metrics` (sysfnt.tdw) and `atlas` (sysfnt.TEX) are the opened font; without
    them every glyph is as wide as the widest, drawn as a box. `icons` (MenuIcons) gives the real
    window border and hand."""
    metrics = metrics if metrics is not None else FontMetrics(widths=None)
    layout = layout_text(fill_values(text, values), game_data, metrics)

    screen = Image.new("RGBA", (384, 240), BACKDROP)
    for box in (TITLE_WINDOW, QUESTION_WINDOW, HELP_WINDOW):
        _draw_window(screen, box, icons)

    # The text, clipped like the game's draw area
    text_layer = Image.new("RGBA", screen.size, (0, 0, 0, 0))
    if atlas is not None:
        atlas.draw_layout(text_layer, layout, TEXT_X, TEXT_Y)
    else:
        boxes = ImageDraw.Draw(text_layer)
        for glyph in layout.glyphs:
            if glyph.char.strip():
                x, y = TEXT_X + glyph.x, TEXT_Y + glyph.y
                boxes.rectangle((x, y + 1, x + max(glyph.width - 2, 0), y + GLYPH_SIZE - 3), fill=BOX_FILL)
    clip = (TEXT_CLIP[0], TEXT_CLIP[1], CLIP_RIGHT, CLIP_BOTTOM)
    screen.alpha_composite(text_layer.crop(clip), clip[:2])

    for stop in layout.stops:
        _draw_hand(screen, TEXT_X + stop.x + HAND_DX, TEXT_Y + stop.y + HAND_DY, icons, stop.index == answer)

    inked = [glyph for glyph in layout.glyphs if glyph.char.strip()]
    ink_right = max((_ink_right(glyph, atlas) for glyph in inked), default=0)
    cut_columns = max(0, ink_right - MAX_TEXT_WIDTH)
    last_line = max((glyph.y for glyph in inked), default=0) // layout.line_height
    cut_lines = max(0, last_line + 1 - MAX_LINES)
    return SeedScreen(screen.crop(CROP), layout, ink_right, cut_columns, cut_lines)
