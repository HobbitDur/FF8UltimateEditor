"""FF8 SeeD-test text layout: reproduce the game's pen walk so the editor can
preview exactly where each character and each choice cursor lands.

The character advances come from the game's own font width file, sysfnt.tdw
(1 nibble per glyph, glyph index = FF8 code - 0x20), the same table the exe
loads into font_char_width_table and reads through get_character_width
(0x4A0CD0). The pen walk mirrors Menu_SeedTest_ParseCursorStops (0x4D4A80):
0x02/0x01 start a new line (+LINE_HEIGHT, x back to 0), 0x0B records the pen
position as a choice cursor stop, the other control codes carry one parameter
byte, and every printable glyph advances x by its width.
"""
import os

LINE_HEIGHT = 16  # The exe adds 16 to the pen y on every line break

# Control codes that consume one parameter byte after the code byte.
_TWO_BYTE_CODES = (0x03, 0x04, 0x05, 0x06, 0x09, 0x0B, 0x0C, 0x0E, 0x19, 0x1A, 0x1B)

# Envelope the vanilla SeeD tests stay within (widest vanilla line = 325 px,
# tallest question = 8 lines). Staying inside it renders like the retail game.
VANILLA_MAX_WIDTH = 325
VANILLA_MAX_LINES = 8

_FALLBACK_WIDTH = 8  # Used per glyph when sysfnt.tdw is not available
_ICON_WIDTH = 12  # Rough advance for an inline {Icon}, only an approximation


class SeedFontMetrics:
    """Character widths for the SeeD-test preview, from sysfnt.tdw when present."""
    TDW_HEADER_SIZE = 8

    def __init__(self, widths=None):
        self._widths = widths  # list[int] indexed by glyph (code - 0x20), or None

    @property
    def exact(self):
        """True when real sysfnt.tdw widths are in use (False = uniform fallback)."""
        return self._widths is not None

    @classmethod
    def from_folder(cls, folder):
        """Load sysfnt.tdw sitting next to mngrp.bin; fall back to uniform widths."""
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


class SeedGlyph:
    __slots__ = ("char", "x", "y", "width")

    def __init__(self, char, x, y, width):
        self.char = char
        self.x = x
        self.y = y
        self.width = width


class SeedStop:
    __slots__ = ("index", "x", "y")

    def __init__(self, index, x, y):
        self.index = index
        self.x = x
        self.y = y


class SeedLayout:
    """Result of walking one question's text: glyph positions, choice stops, extent."""

    def __init__(self, glyphs, stops, line_widths):
        self.glyphs = glyphs  # [SeedGlyph]
        self.stops = stops  # [SeedStop], one per cursor stop, in text order
        self.line_widths = line_widths  # px width of each rendered line

    @property
    def line_count(self):
        return len(self.line_widths)

    @property
    def max_width(self):
        return max(self.line_widths) if self.line_widths else 0

    def overflows(self):
        return self.max_width > VANILLA_MAX_WIDTH or self.line_count > VANILLA_MAX_LINES


def _glyph_char(game_data, code):
    """The display character for a single-byte FF8 code (codes are not ASCII)."""
    table = game_data.translate_hex_to_str_table
    if code < len(table):
        char = table[code]
        if len(char) == 1:  # A real glyph, not a {control} placeholder
            return char
    return "?"


def layout_text(text_str, game_data, metrics: SeedFontMetrics) -> SeedLayout:
    """Lay out a decoded question string exactly as the SeeD test screen would.

    The answer byte is not part of the text (the engine reads it separately), so
    only the FF8 text is walked, starting at pen (0, 0)."""
    text_hex = bytes(game_data.translate_str_to_hex(text_str))
    glyphs = []
    stops = []
    line_widths = []
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
            y += LINE_HEIGHT
            i += 1
        elif code == 0x0B:  # Cursor stop: records the pen position of a choice
            stop_index = text_hex[i + 1] - 0x20 if i + 1 < size else len(stops)
            stops.append(SeedStop(stop_index, x, y))
            i += 2
        elif code == 0x05:  # Inline icon: skips the param, advances by an icon width
            x += _ICON_WIDTH
            i += 2
        elif code in _TWO_BYTE_CODES:  # Color/wait/name/... : carry a param, no advance
            i += 2
        else:  # Printable glyph
            width = metrics.glyph_width(code)
            glyphs.append(SeedGlyph(_glyph_char(game_data, code), x, y, width))
            x += width
            i += 1
    line_widths.append(x)  # The final (or only) line
    return SeedLayout(glyphs, stops, line_widths)
