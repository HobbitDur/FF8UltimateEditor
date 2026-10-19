"""The Scan screen's text, drawn where the game draws it on its 320x240 screen.

MAG_040_SCAN_Viewer_State0_SpawnTextPager (0x84F8D0) opens two text layers:
  * layer 2, the monster name: rect (170, 30) 136x28;
  * layer 0, the scan text:    rect (170, 52) 136x128.
setTextPosition (0x4A07A0) draws a layer's text 6 px inside its rect, one line every 16 px,
(height - 12) / 16 lines per page - 7 lines for the scan text, the TextPager turning pages.
"""
from PIL import Image, ImageDraw

from FF8GameData.font.textlayout import layout_text, FontMetrics

SCREEN_SIZE = (320, 240)
NAME_RECT = (170, 30, 136, 28)
TEXT_RECT = (170, 52, 136, 128)
TEXT_PADDING = 6
LINE_HEIGHT = 16


def lines_per_page(rect=TEXT_RECT) -> int:
    return max(1, (rect[3] - 12) // LINE_HEIGHT)


class ScanHud:
    """Renders the name + one page of scan text as a transparent 320x240 overlay."""

    def __init__(self, game_data):
        self.game_data = game_data
        self.atlas = None
        self.metrics = FontMetrics(widths=None)

    def set_font_folder(self, folder):
        """Use sysfnt.TEX/.tdw from this menu folder (None = fallback font)."""
        from FF8GameData.font.atlas import FontAtlas
        self.atlas = FontAtlas.from_folder(folder) if folder else None
        self.metrics = FontMetrics.from_folder(folder)

    def layout(self, text):
        return layout_text(text, self.game_data, self.metrics, line_height=LINE_HEIGHT)

    def page_count(self, text) -> int:
        layout = self.layout(text)
        return max(1, -(-layout.line_count // lines_per_page()))

    def too_wide_lines(self, text) -> list:
        """1-based line numbers wider than the text box."""
        width = TEXT_RECT[2] - 2 * TEXT_PADDING
        return [index + 1 for index, line_width in enumerate(self.layout(text).line_widths)
                if line_width > width]

    def render(self, name, text, page=0) -> Image.Image:
        image = Image.new("RGBA", SCREEN_SIZE, (0, 0, 0, 0))
        self._draw(image, name, NAME_RECT, 0)
        self._draw(image, text, TEXT_RECT, page)
        return image

    def _draw(self, image, text, rect, page):
        if not text:
            return
        layout = self.layout(text)
        per_page = lines_per_page(rect)
        first, last = page * per_page * LINE_HEIGHT, (page + 1) * per_page * LINE_HEIGHT
        x0, y0 = rect[0] + TEXT_PADDING, rect[1] + TEXT_PADDING - first
        draw = None
        for glyph in layout.glyphs:
            if not first <= glyph.y < last:
                continue
            cell = self.atlas.glyph(glyph.code, glyph.color) if self.atlas is not None else None
            if cell is not None:
                image.alpha_composite(cell, (x0 + glyph.x, y0 + glyph.y))
            else:  # No game font open: a plain stand-in at the same place
                draw = draw or ImageDraw.Draw(image)
                draw.text((x0 + glyph.x, y0 + glyph.y), glyph.char, fill=(255, 255, 255, 255))
