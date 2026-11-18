"""FF8 font file ``.tdw``: glyph widths + the 12x12 glyph image (a PSX TIM).

Ported from Deling's TdwFile (myst6re, GPL-3.0). Used for the game font ``main/sysfnt.tdw``
(``menu/sysfnt.tdw`` holds the same file) and the per-field additional fonts ``field/.../xxx.tdw``.
The PC game reads only the widths from sysfnt.tdw (readFilesKernelNamedicIconSysfnt copies its width
block); the glyphs it draws are the textures (FF8GameData.font.lowresfont / hiresfont). The image here
is the PlayStation one, the same glyphs as menu/sysfnt.TEX.

Layout::

    0x00  u32 width block offset (always 8)
    0x04  u32 TIM offset
    0x08  width block: one byte per 2 glyphs (low nibble = even glyph, high nibble = odd glyph),
          112 bytes per table of 224 glyphs. The last table may be shorter.
    TIM   4bpp, 256 px wide, 21 glyph columns of 12x12 px.

Two image kinds exist:

- **Latin** (8 palettes, one per text colour): 16 colour levels, glyph ``n`` at column ``n % 21``, row
  ``n // 21``.
- **Japanese** ("optimized", 16 or 32 palettes): two glyphs share each cell. Glyph ``n`` sits at cell
  ``n // 2``; an even glyph uses the low 2 bits of each pixel and an odd glyph the high 2 bits, so
  each glyph has 4 levels. Palette ``2 * colour`` shows the even glyphs, ``2 * colour + 1`` the odd
  ones.

A glyph is addressed by its absolute id ``224 * table + (byte - 0x20)``: table 0 is the single-byte
codes, tables 1-3 the Japanese lead bytes 0x19/0x1a/0x1b (the game's menu_draw_text uses the same id).

The file is kept as raw bytes and saving patches only the widths and the pixels, so an unchanged
file saves back identical. The Japanese sysfnt.tdw's TIM block sizes are wrong (it really holds 32
palettes and 252 rows), so the CLUT size comes from its block length and the pixel size from the
image dimensions, as the game reads it.
"""
from __future__ import annotations

import struct
from typing import List, Optional, Tuple

from PIL import Image

from FF8GameData.tim.timfile import word_to_rgba

LETTER_SIZE = 12
COLUMNS = 21
TABLE_SIZE = 224
WIDTH_BYTES_PER_TABLE = TABLE_SIZE // 2
COLORS = ("Dark grey", "Grey", "Yellow", "Red", "Green", "Blue", "Purple", "White")
WHITE = 7
MAX_WIDTH = 15

Rgba = Tuple[int, int, int, int]


class TdwFile:
    def __init__(self, data: bytes):
        if len(data) <= 8:
            raise ValueError("tdw too short")
        self._data = bytearray(data)
        width_offset, self._tim_offset = struct.unpack_from("<II", data, 0)
        if width_offset != 8 or self._tim_offset > len(data):
            raise ValueError(f"not a tdw file (width offset {width_offset}, TIM offset {self._tim_offset})")
        width_size = self._tim_offset - 8
        self._table_count = width_size // WIDTH_BYTES_PER_TABLE + int(width_size % WIDTH_BYTES_PER_TABLE != 0)
        self._char_counts = [min((width_size - t * WIDTH_BYTES_PER_TABLE) * 2, TABLE_SIZE)
                             for t in range(self._table_count)]
        self._parse_tim()

    def _parse_tim(self):
        tim = self._tim_offset
        tag, flags = struct.unpack_from("<II", self._data, tim)
        if tag != 0x10 or flags & 0x7 != 0 or not flags & 0x8:
            raise ValueError("tdw image is not a 4bpp TIM with palettes")
        clut_length, _x, _y, clut_width, _h = struct.unpack_from("<IHHHH", self._data, tim + 8)
        clut_words = (clut_length - 12) // 2
        self._palettes: List[List[Rgba]] = []
        for row in range(clut_words // clut_width):
            words = struct.unpack_from(f"<{clut_width}H", self._data, tim + 20 + row * clut_width * 2)
            self._palettes.append([word_to_rgba(word) for word in words])
        if len(self._palettes) not in (8, 16, 32):
            raise ValueError(f"tdw image has {len(self._palettes)} palettes (8, 16 or 32 expected)")
        image = tim + 8 + clut_length
        _length, _x, _y, width_halfwords, height = struct.unpack_from("<IHHHH", self._data, image)
        self.width = width_halfwords * 4
        self.height = height
        self._pixel_offset = image + 12
        packed = self._data[self._pixel_offset:self._pixel_offset + self.width * height // 2]
        if len(packed) != self.width * height // 2:
            raise ValueError("tdw image is truncated")
        self.pixels = bytearray(v for byte in packed for v in (byte & 0x0F, byte >> 4))

    @classmethod
    def read(cls, path: str) -> "TdwFile":
        with open(path, "rb") as f:
            return cls(f.read())

    @property
    def width_data(self) -> bytes:
        """The width tables as stored (a copy, to compare or put back)."""
        return bytes(self._data[8:self._tim_offset])

    @width_data.setter
    def width_data(self, data: bytes):
        if len(data) != self._tim_offset - 8:
            raise ValueError("width data of another size")
        self._data[8:self._tim_offset] = data

    def to_bytes(self) -> bytes:
        data = bytearray(self._data)
        packed = bytes((self.pixels[i] & 0x0F) | ((self.pixels[i + 1] & 0x0F) << 4)
                       for i in range(0, len(self.pixels), 2))
        data[self._pixel_offset:self._pixel_offset + len(packed)] = packed
        return bytes(data)

    def write(self, path: str):
        with open(path, "wb") as f:
            f.write(self.to_bytes())

    def copy(self) -> "TdwFile":
        return TdwFile(self.to_bytes())

    # -- tables and widths ------------------------------------------------------------------------
    @property
    def table_count(self) -> int:
        return self._table_count

    def char_count(self, table: int = 0) -> int:
        return self._char_counts[table] if 0 <= table < self._table_count else 0

    @property
    def optimized(self) -> bool:
        """Japanese layout: two glyphs per cell, 4 levels each (see the module docstring)."""
        return len(self._palettes) >= 16

    @property
    def level_count(self) -> int:
        return 4 if self.optimized else 16

    def _width_position(self, table: int, char: int) -> Optional[int]:
        if not 0 <= char < self.char_count(table):
            return None
        position = 8 + table * WIDTH_BYTES_PER_TABLE + char // 2
        return position if position < self._tim_offset else None

    def char_width(self, table: int, char: int) -> int:
        position = self._width_position(table, char)
        if position is None:
            return 0
        return (self._data[position] >> (4 * (char % 2))) & 0x0F

    def set_char_width(self, table: int, char: int, width: int):
        position = self._width_position(table, char)
        if position is None:
            raise IndexError(f"no width for glyph {char} of table {table}")
        shift = 4 * (char % 2)
        self._data[position] = (self._data[position] & ~(0x0F << shift) & 0xFF) | ((width & 0x0F) << shift)

    # -- glyphs ------------------------------------------------------------------------------------
    @staticmethod
    def glyph_id(table: int, char: int) -> int:
        return table * TABLE_SIZE + char

    def palette_index(self, color: int, glyph: int) -> int:
        if self.optimized:
            return (color % 8) * 2 + glyph % 2
        return color % 8

    def palette(self, index: int) -> List[Rgba]:
        return self._palettes[index]

    def letter_origin(self, glyph: int) -> Tuple[int, int]:
        cell = glyph // 2 if self.optimized else glyph
        return (cell % COLUMNS) * LETTER_SIZE, (cell // COLUMNS) * LETTER_SIZE

    def has_letter(self, glyph: int) -> bool:
        x, y = self.letter_origin(glyph)
        return y + LETTER_SIZE <= self.height

    def _shift(self, glyph: int) -> int:
        return 2 * (glyph % 2) if self.optimized else 0

    def level(self, glyph: int, x: int, y: int) -> int:
        """The colour level of one pixel of a glyph: 0..3 (Japanese) or 0..15 (Latin)."""
        ox, oy = self.letter_origin(glyph)
        value = self.pixels[(oy + y) * self.width + ox + x]
        return (value >> self._shift(glyph)) & (self.level_count - 1)

    def set_level(self, glyph: int, x: int, y: int, level: int):
        ox, oy = self.letter_origin(glyph)
        offset = (oy + y) * self.width + ox + x
        mask = (self.level_count - 1) << self._shift(glyph)
        self.pixels[offset] = (self.pixels[offset] & ~mask & 0x0F) | ((level << self._shift(glyph)) & mask)

    def levels(self, glyph: int) -> List[int]:
        """The 144 pixel levels of a glyph, row by row."""
        if not self.has_letter(glyph):
            return [0] * (LETTER_SIZE * LETTER_SIZE)
        return [self.level(glyph, x, y) for y in range(LETTER_SIZE) for x in range(LETTER_SIZE)]

    def set_levels(self, glyph: int, levels: List[int]):
        for i, level in enumerate(levels):
            self.set_level(glyph, i % LETTER_SIZE, i // LETTER_SIZE, level)

    @property
    def level_values(self) -> List[int]:
        return list(range(self.level_count))

    def level_color(self, color: int, glyph: int, level: int) -> Rgba:
        return self.palette(self.palette_index(color, glyph))[level << self._shift(glyph)]

    def level_colors(self, color: int, glyph: int = 0) -> List[Rgba]:
        """What each level looks like in a text colour (index = level)."""
        palette = self.palette(self.palette_index(color, glyph))
        return [palette[level << self._shift(glyph)] for level in range(self.level_count)]

    def letter_image(self, glyph: int, color: int = WHITE) -> Image.Image:
        image = Image.new("RGBA", (LETTER_SIZE, LETTER_SIZE))
        if not self.has_letter(glyph):
            return image
        colors = self.level_colors(color, glyph)
        image.putdata([colors[level] for level in self.levels(glyph)])
        return image

    def image(self, color: int = WHITE) -> Image.Image:
        """The whole glyph image in one text colour (as the game's palette shows it, even glyphs'
        palette for the Japanese layout)."""
        palette = self.palette(self.palette_index(color, 0))
        image = Image.new("RGBA", (self.width, self.height))
        image.putdata([palette[value] for value in self.pixels])
        return image

    def set_letter_image(self, glyph: int, image: Image.Image, color: int = WHITE):
        """Draw a 12x12 image into a glyph: each pixel takes the level whose colour is nearest."""
        image = image.convert("RGBA").resize((LETTER_SIZE, LETTER_SIZE), Image.Resampling.NEAREST)
        colors = self.level_colors(color, glyph)

        def nearest(pixel):
            if pixel[3] < 64:
                return 0
            return min(range(1, len(colors)), key=lambda i: sum((a - b) ** 2 for a, b in zip(pixel[:3], colors[i][:3])))

        self.set_levels(glyph, [nearest(pixel) for pixel in image.getdata()])
