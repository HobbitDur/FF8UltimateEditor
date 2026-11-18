"""The high-resolution game font (menu/hires/*.TEX): the 24x24 glyphs FF8 PC draws in high-res mode.

The exe loads them instead of menu/sysfnt.TEX when its high-res font option is on (FFNx's
``ff8_high_res_font``; its default turns it on for FF8 Steam). The widths still come from sysfnt.tdw.
The glyphs are in the tdw's order and grid, twice as big (24 px cells, 21 per row), on a page split
into 256x256 tiles:

- **Latin** (English, French...): ``sysfld00.TEX`` + ``sysfld01.TEX`` side by side, a 512x256 page.
  8 bits per pixel; each of the 8 palettes (one per text colour) maps the 256 values to a shade, so a
  pixel's value is its brightness level (0 transparent, 1 the brightest, up to 254).
- **Japanese**: two 504x504 pages, ``sysevn00-03.TEX`` for the even glyphs and ``sysodd00-03.TEX``
  for the odd ones (tiles 00 top-left, 01 top-right, 02 bottom-left, 03 bottom-right). Glyph ``n`` is
  at cell ``n // 2`` of its page, in the low 2 bits of each pixel (sysevn) or the high 2 bits (sysodd),
  so each glyph has 4 levels; palette ``c`` (0-7) shows text colour ``c``. menu/sysfnt_even.TEX and
  sysfnt_odd.TEX are the same at 12 px.

Saving rewrites only the pixels, so unchanged tiles save back identical.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from PIL import Image

from FF8GameData.tex.texfile import TexFile

CELL = 24
COLUMNS = 21
TILE = 256
LATIN_LEVELS = [0, 1] + list(range(17, 255, 16)) + [254]  # a sample of the 255 shades, to paint with

_LATIN = re.compile(r"sysfld0[01]\.tex$", re.IGNORECASE)
_JAPANESE = re.compile(r"sys(evn|odd)0[0-3]\.tex$", re.IGNORECASE)


def _find(folder: str, name: str) -> str:
    """The file of that name in folder, whatever its case (sysfld00.tex / sysfld00.TEX)."""
    for entry in os.listdir(folder):
        if entry.lower() == name.lower():
            return os.path.join(folder, entry)
    raise FileNotFoundError(f"{name} is not next to the other hi-res font textures in {folder}")


class HiresFont:
    def __init__(self, pages: Dict[str, List[Tuple[str, TexFile]]], japanese: bool):
        self.pages = pages          # page name -> [(path, TexFile)] tiles, row by row, 2 per row
        self.japanese = japanese

    @staticmethod
    def is_hires_font(path: str) -> bool:
        name = os.path.basename(path)
        return bool(_LATIN.match(name) or _JAPANESE.match(name))

    @classmethod
    def from_path(cls, path: str) -> "HiresFont":
        """Any one of the tiles: the others are found next to it."""
        folder, name = os.path.split(os.path.abspath(path))
        if _LATIN.match(name):
            names = {"page": ["sysfld00.TEX", "sysfld01.TEX"]}
        elif _JAPANESE.match(name):
            names = {kind: [f"sys{kind}{i:02d}.TEX" for i in range(4)] for kind in ("evn", "odd")}
        else:
            raise ValueError(f"{name} is not a hi-res font texture (sysfld00/01, sysevn00-03, sysodd00-03)")
        pages = {}
        for page, tile_names in names.items():
            tiles = []
            for tile_name in tile_names:
                tile_path = _find(folder, tile_name)
                tex = TexFile.read(tile_path)
                if (tex.width, tex.height) != (TILE, TILE):
                    raise ValueError(f"{tile_name} is {tex.width}x{tex.height}, 256x256 expected")
                tiles.append((tile_path, tex))
            pages[page] = tiles
        return cls(pages, japanese=_JAPANESE.match(name) is not None)

    @property
    def paths(self) -> List[str]:
        return [path for tiles in self.pages.values() for path, _tex in tiles]

    def write(self):
        for tiles in self.pages.values():
            for path, tex in tiles:
                tex.write(path)

    # -- glyph addressing --------------------------------------------------------------------------
    def _page(self, glyph: int):
        if self.japanese:
            return self.pages["evn" if glyph % 2 == 0 else "odd"], glyph // 2, 2 * (glyph % 2)
        return self.pages["page"], glyph, 0

    def _pixel(self, glyph: int, x: int, y: int):
        tiles, cell, shift = self._page(glyph)
        px, py = (cell % COLUMNS) * CELL + x, (cell // COLUMNS) * CELL + y
        tile = (py // TILE) * 2 + px // TILE
        if tile >= len(tiles):
            return None
        tex = tiles[tile][1]
        return tex, (py % TILE) * TILE + px % TILE, shift

    def has_letter(self, glyph: int) -> bool:
        return self._pixel(glyph, CELL - 1, CELL - 1) is not None

    @property
    def level_values(self) -> List[int]:
        """The levels offered to paint with (any value can still be picked from a pixel)."""
        return [0, 1, 2, 3] if self.japanese else LATIN_LEVELS

    def level(self, glyph: int, x: int, y: int) -> int:
        tex, offset, shift = self._pixel(glyph, x, y)
        value = tex.pixels[offset]
        return (value >> shift) & 3 if self.japanese else value

    def set_level(self, glyph: int, x: int, y: int, level: int):
        tex, offset, shift = self._pixel(glyph, x, y)
        if self.japanese:
            mask = 3 << shift
            tex.pixels[offset] = (tex.pixels[offset] & ~mask & 0xFF) | ((level & 3) << shift)
        else:
            tex.pixels[offset] = level & 0xFF

    def set_levels(self, glyph: int, levels: List[int]):
        for i, level in enumerate(levels):
            self.set_level(glyph, i % CELL, i // CELL, level)

    def _palette(self, color: int, glyph: int):
        """The colour of each level of that glyph in that text colour (palettes don't change: cached)."""
        tiles, _cell, shift = self._page(glyph)
        key = (id(tiles), color % 8)
        cache = self.__dict__.setdefault("_palettes", {})
        if key not in cache:
            palette = tiles[0][1].palette(color % 8)
            cache[key] = [palette[level << shift] for level in range(4)] if self.japanese else palette
        return cache[key]

    def level_color(self, color: int, glyph: int, level: int):
        return self._palette(color, glyph)[level]

    def level_colors(self, color: int, glyph: int = 0) -> List[tuple]:
        return [self.level_color(color, glyph, level) for level in self.level_values]

    def levels(self, glyph: int) -> List[int]:
        if not self.has_letter(glyph):
            return [0] * (CELL * CELL)
        tiles, cell, shift = self._page(glyph)
        x0, y0 = (cell % COLUMNS) * CELL, (cell // COLUMNS) * CELL
        out = []
        for y in range(y0, y0 + CELL):
            row_tiles = tiles[(y // TILE) * 2:(y // TILE) * 2 + 2]
            for x in range(x0, x0 + CELL):
                value = row_tiles[x // TILE][1].pixels[(y % TILE) * TILE + x % TILE]
                out.append((value >> shift) & 3 if self.japanese else value)
        return out

    def letter_image(self, glyph: int, color: int = 7) -> Image.Image:
        image = Image.new("RGBA", (CELL, CELL))
        if self.has_letter(glyph):
            palette = self._palette(color, glyph)
            image.putdata([palette[level] for level in self.levels(glyph)])
        return image
