"""The Scan screen's text, drawn where the game draws it on its 320x240 screen.

MAG_040_SCAN_Viewer_State0_SpawnTextPager (0x84F8D0) opens the text layers:
  * layer 2, the monster name: rect (170, 30) 136x28;
  * layer 0, the scan text:    rect (170, 52) 136x128.
setTextPosition (0x4A07A0) draws a layer's text 6 px inside its rect, one line every 16 px, with
room for (height - 12) / 16 lines - 7 for the scan text. The scan text is never paged: only its
first 7 lines fit and Text_RenderGlyphs stops at a page break. The TextPager pages the one-line
info bar (layer 1: level/HP, element affinities, the AI's setScanText line), not the scan text:
  * layer 1, the info bar:     rect (16, 180) 296x28 (one line, see Xu.xuinfobar).

The info bar is a battle text, drawn by Text_RenderGlyphs (0x4A1570): a byte >= 0x20 is a glyph,
0x05 + code an icon.sp1 sprite (the element names are icons), which advances the pen by the
sprite's width (Menu_GetSp1IconSize: max of quad dx + width) + 1, 0x06 + colour sets the colour,
0x03-0x0F carry one parameter byte, 0x10-0x18 none, 0x19-0x1F lead a 2-byte glyph.
"""
import os

from PIL import Image, ImageDraw

from FF8GameData.font.textlayout import layout_text, FontMetrics, DEFAULT_COLOR
from Xu.xuinfobar import icon_sprite_id

SCREEN_SIZE = (320, 240)
NAME_RECT = (170, 30, 136, 28)
TEXT_RECT = (170, 52, 136, 128)
INFO_RECT = (16, 180, 296, 28)
ICON_FALLBACK_ADVANCE = 12     # an icon this preview cannot draw: a box of about an icon's size
TEXT_PADDING = 6
LINE_HEIGHT = 16


def visible_lines(rect=TEXT_RECT) -> int:
    return max(1, (rect[3] - 12) // LINE_HEIGHT)


class IconSheet:
    """icon.sp1 sprites (Minimog's format) with the icon.TEX next to it."""

    def __init__(self, sp1_path):
        from FF8GameData.tex.texfile import TexFile
        from Minimog.minimogmanager import MinimogManager
        tex_path = os.path.join(os.path.dirname(sp1_path), "icon.TEX")
        if not os.path.exists(tex_path):
            raise FileNotFoundError(f"icon.TEX holds the pixels icon.sp1 points at, not found at: {tex_path}")
        self._sp1 = MinimogManager()
        self._sp1.load_file(sp1_path)
        self._tex = TexFile.read(tex_path)
        self._cache = {}

    def has(self, icon_id) -> bool:
        return icon_id is not None and 0 <= icon_id < len(self._sp1.icons)

    def advance(self, icon_id) -> int:
        """Menu_GetSp1IconSize's width + 1: how far the text pen moves past the icon."""
        quads = self._sp1.icons[icon_id].quads
        return max([0] + [quad.dx + quad.width for quad in quads]) + 1

    def image(self, icon_id):
        """(image, dx, dy) of a sprite (its top-left relative to the pen), None when empty."""
        if icon_id not in self._cache:
            image = self._sp1.render_icon(icon_id, self._tex)
            box = self._sp1.icons[icon_id].bounding_box()
            self._cache[icon_id] = None if image is None else (image, box[0], box[1])
        return self._cache[icon_id]


class ScanHud:
    """Renders the name, the scan text and the info bar as a transparent 320x240 overlay."""

    def __init__(self, game_data):
        self.game_data = game_data
        self.atlas = None
        self.metrics = FontMetrics(widths=None)
        self.icons = None       # IconSheet of an opened icon.sp1
        self.icon_table = {}    # text icon code -> icon.sp1 id, from the opened FF8 exe

    def set_icon_file(self, sp1_path):
        """Draw the text icons with this icon.sp1 (None = boxes in their place)."""
        self.icons = IconSheet(sp1_path) if sp1_path else None

    def set_font_folder(self, folder):
        """Use sysfnt.TEX/.tdw from this menu folder (None = fallback font)."""
        from FF8GameData.font.atlas import FontAtlas
        self.atlas = FontAtlas.from_folder(folder) if folder else None
        self.metrics = FontMetrics.from_folder(folder)

    def layout(self, text):
        """What the game draws: the text up to its first page break."""
        return layout_text(text, self.game_data, self.metrics, line_height=LINE_HEIGHT, first_page_only=True)

    def hidden_lines(self, text) -> int:
        """Lines past the 7 that fit in the text box."""
        return max(0, self.layout(text).line_count - visible_lines())

    def has_page_break(self, text) -> bool:
        """True when a page break hides the rest of the text (the game never shows it)."""
        full = layout_text(text, self.game_data, self.metrics, line_height=LINE_HEIGHT)
        shown = self.layout(text)
        return len(full.glyphs) > len(shown.glyphs)

    def too_wide_lines(self, text) -> list:
        """1-based line numbers wider than the text box."""
        width = TEXT_RECT[2] - 2 * TEXT_PADDING
        return [index + 1 for index, line_width in enumerate(self.layout(text).line_widths)
                if line_width > width]

    def render(self, name, text, info_line=b"") -> Image.Image:
        image = Image.new("RGBA", SCREEN_SIZE, (0, 0, 0, 0))
        self._draw(image, name, NAME_RECT)
        self._draw(image, text, TEXT_RECT)
        self._draw_battle_text(image, info_line, INFO_RECT)
        return image

    # ------------------------------------------------------------- info bar (battle text)
    def battle_text_items(self, data: bytes) -> list:
        """[(kind, value, x, width, colour)] of a one-line battle text, kind 'glyph' (value = FF8
        code) or 'icon' (value = icon.sp1 id, None when unknown), pen starting at 0."""
        items, x, color, i = [], 0, DEFAULT_COLOR, 0
        data = bytes(data or b"")
        while i < len(data):
            code = data[i]
            if code in (0x00, 0x01, 0x02, 0x07):  # end, end of page; the bar is one line
                break
            if code >= 0x20:
                width = self.metrics.glyph_width(code)
                items.append(("glyph", code, x, width, color))
                x += width
                i += 1
            elif code >= 0x19:  # 2-byte glyph of the extended tables, not in the EN atlas
                i += 2
            elif code == 0x05:
                icon_id = icon_sprite_id(data[i + 1], self.icon_table) if i + 1 < len(data) else None
                known = self.icons is not None and self.icons.has(icon_id)
                width = self.icons.advance(icon_id) if known else ICON_FALLBACK_ADVANCE
                items.append(("icon", icon_id if known else None, x, width, color))
                x += width
                i += 2
            elif code == 0x06:
                color = (data[i + 1] & 0x7) if i + 1 < len(data) else color
                i += 2
            elif code <= 0x0F:
                i += 2
            else:
                i += 1
        return items

    def battle_text_width(self, data: bytes) -> int:
        items = self.battle_text_items(data)
        return items[-1][2] + items[-1][3] if items else 0

    def _draw_battle_text(self, image, data, rect):
        if not data:
            return
        x0, y0 = rect[0] + TEXT_PADDING, rect[1] + TEXT_PADDING
        draw = None
        for kind, value, x, width, color in self.battle_text_items(data):
            if kind == "icon":
                sprite = self.icons.image(value) if value is not None else None
                if sprite is not None:
                    picture, dx, dy = sprite
                    image.alpha_composite(picture, (max(0, x0 + x + dx), max(0, y0 + dy)))
                    continue
                if value is None:  # no icon.sp1 or no exe table: a box where the icon goes
                    draw = draw or ImageDraw.Draw(image)
                    draw.rectangle((x0 + x, y0, x0 + x + width - 2, y0 + 11), outline=(255, 255, 255, 160))
                continue
            cell = self.atlas.glyph(value, color) if self.atlas is not None else None
            if cell is not None:
                image.alpha_composite(cell, (x0 + x, y0))
            else:
                draw = draw or ImageDraw.Draw(image)
                char = self.game_data.translate_hex_to_str_table[value] if value < len(
                    self.game_data.translate_hex_to_str_table) else "?"
                draw.text((x0 + x, y0), char if len(char) == 1 else "?", fill=(255, 255, 255, 255))

    def _draw(self, image, text, rect):
        if not text:
            return
        layout = self.layout(text)
        last = visible_lines(rect) * LINE_HEIGHT
        x0, y0 = rect[0] + TEXT_PADDING, rect[1] + TEXT_PADDING
        draw = None
        for glyph in layout.glyphs:
            if glyph.y >= last:
                continue
            cell = self.atlas.glyph(glyph.code, glyph.color) if self.atlas is not None else None
            if cell is not None:
                image.alpha_composite(cell, (x0 + glyph.x, y0 + glyph.y))
            else:  # No game font open: a plain stand-in at the same place
                draw = draw or ImageDraw.Draw(image)
                draw.text((x0 + glyph.x, y0 + glyph.y), glyph.char, fill=(255, 255, 255, 255))
