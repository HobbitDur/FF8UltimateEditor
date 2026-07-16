"""FF8 text layout: reproduce the engine's pen walk so a tool can place every
character exactly where the game does.

The character advances come from the game's own font width file, sysfnt.tdw
(1 nibble per glyph, glyph index = FF8 code - 0x20), the same table the exe
loads into font_char_width_table and reads through get_character_width
(0x4A0CD0).

The walk mirrors menu_draw_text (0x4BDE30): code 0x02 starts a new line (pen x
back to the left margin, y += line height), code 0x05 draws an inline icon and
advances past it, 0x0B records the pen position (the SeeD test reads those back
as its choice cursor stops), 0x06 switches the text colour, the other control
codes carry one parameter byte, and every printable glyph advances x by its
width.

The line height is a caller decision because the engine has no single value:
menu_draw_text adds 13 per line break, while Menu_SeedTest_ParseCursorStops
(0x4D4A80) adds 16. Pass the one that matches the screen being previewed.
"""
import os

MENU_TEXT_LINE_HEIGHT = 13  # menu_draw_text (0x4BDE30) adds 13 on code 0x02
SEED_TEST_LINE_HEIGHT = 16  # Menu_SeedTest_ParseCursorStops (0x4D4A80) adds 16

DEFAULT_COLOR = 7  # sysfnt colour index 7 = White, the engine's default text colour

# Control codes that consume one parameter byte after the code byte.
_TWO_BYTE_CODES = (0x03, 0x04, 0x05, 0x06, 0x09, 0x0B, 0x0C, 0x0E, 0x19, 0x1A, 0x1B)

_FALLBACK_WIDTH = 8  # Used per glyph when sysfnt.tdw is not available
_ICON_WIDTH = 12  # Rough advance for an inline {Icon}, only an approximation


class FontMetrics:
    """Character widths from sysfnt.tdw, with a uniform fallback when absent."""
    TDW_HEADER_SIZE = 8

    def __init__(self, widths=None):
        self._widths = widths  # list[int] indexed by glyph (code - 0x20), or None

    @property
    def exact(self):
        """True when real sysfnt.tdw widths are in use (False = uniform fallback)."""
        return self._widths is not None

    @classmethod
    def from_folder(cls, folder):
        """Load sysfnt.tdw sitting in the given menu folder; fall back to uniform widths."""
        if folder:
            tdw_path = os.path.join(folder, "sysfnt.tdw")
            if os.path.exists(tdw_path):
                with open(tdw_path, "rb") as tdw_file:
                    return cls.from_tdw_bytes(tdw_file.read())
        return cls(widths=None)

    @classmethod
    def from_tdw_bytes(cls, data):
        packed = data[cls.TDW_HEADER_SIZE:]
        widths = []
        for glyph in range(len(packed) * 2):
            byte = packed[glyph >> 1]
            widths.append((byte >> 4) & 0xF if (glyph & 1) else byte & 0xF)
        return cls(widths=widths)

    def glyph_width(self, code):
        """Advance in pixels of the printable glyph with the given FF8 code byte."""
        glyph = code - 0x20
        if glyph < 0:
            return 0
        if glyph == 173:  # Hardcoded in get_character_width
            return 9
        if glyph == 174:
            return 10
        if self._widths is None:
            return _FALLBACK_WIDTH
        if glyph < len(self._widths):
            return self._widths[glyph]
        return _FALLBACK_WIDTH


class Glyph:
    """One printable character at its pen position.

    `code` is the FF8 code byte (the atlas cell is code - 0x20), `char` the
    display character for tools that draw with a system font instead."""
    __slots__ = ("char", "code", "x", "y", "width", "color")

    def __init__(self, char, code, x, y, width, color=DEFAULT_COLOR):
        self.char = char
        self.code = code
        self.x = x
        self.y = y
        self.width = width
        self.color = color


class CursorStop:
    """A pen position recorded by code 0x0B (the SeeD test's choice cursors)."""
    __slots__ = ("index", "x", "y")

    def __init__(self, index, x, y):
        self.index = index
        self.x = x
        self.y = y


class TextLayout:
    """Result of walking one string: glyph positions, cursor stops, extent."""

    def __init__(self, glyphs, stops, line_widths, line_height):
        self.glyphs = glyphs  # [Glyph]
        self.stops = stops  # [CursorStop], one per cursor stop, in text order
        self.line_widths = line_widths  # px width of each rendered line
        self.line_height = line_height

    @property
    def line_count(self):
        return len(self.line_widths)

    @property
    def max_width(self):
        return max(self.line_widths) if self.line_widths else 0

    @property
    def height(self):
        return self.line_count * self.line_height

    def overflows(self, max_width, max_lines):
        """True when the text leaves the given envelope (see the caller's limits)."""
        return self.max_width > max_width or self.line_count > max_lines


def _glyph_char(game_data, code):
    """The display character for a single-byte FF8 code (codes are not ASCII)."""
    table = game_data.translate_hex_to_str_table
    if code < len(table):
        char = table[code]
        if len(char) == 1:  # A real glyph, not a {control} placeholder
            return char
    return "?"


def layout_text(text_str, game_data, metrics: FontMetrics,
                line_height=MENU_TEXT_LINE_HEIGHT) -> TextLayout:
    """Lay out a decoded FF8 string exactly as the engine would, pen starting at (0, 0)."""
    text_hex = bytes(game_data.translate_str_to_hex(text_str))
    glyphs = []
    stops = []
    line_widths = []
    color = DEFAULT_COLOR
    x = 0
    y = 0
    i = 0
    size = len(text_hex)
    while i < size:
        code = text_hex[i]
        if code == 0x00:
            break
        if code in (0x01, 0x02):  # New page / new line
            line_widths.append(x)
            x = 0
            y += line_height
            i += 1
        elif code == 0x0B:  # Cursor stop: records the pen position of a choice
            stop_index = text_hex[i + 1] - 0x20 if i + 1 < size else len(stops)
            stops.append(CursorStop(stop_index, x, y))
            i += 2
        elif code == 0x05:  # Inline icon: skips the param, advances by an icon width
            x += _ICON_WIDTH
            i += 2
        elif code == 0x06:  # Colour: param 0x20 + index, blink variants reuse the base colour
            if i + 1 < size:
                color = (text_hex[i + 1] - 0x20) & 0x7
            i += 2
        elif code in _TWO_BYTE_CODES:  # Wait/name/... : carry a param, no advance
            i += 2
        else:  # Printable glyph
            width = metrics.glyph_width(code)
            glyphs.append(Glyph(_glyph_char(game_data, code), code, x, y, width, color))
            x += width
            i += 1
    line_widths.append(x)  # The final (or only) line
    return TextLayout(glyphs, stops, line_widths, line_height)
