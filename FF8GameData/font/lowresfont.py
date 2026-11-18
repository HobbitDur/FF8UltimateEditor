"""The low-resolution game font texture (menu/sysfnt.TEX...): the 12x12 glyphs FF8 PC draws when its
high-res font option is off. (sysfnt.tdw holds the same picture, from the PlayStation version, but the
PC game reads only the widths from it.)

Same grid and glyph order as the tdw: 21 cells of 12 px per row.

- **Latin** ``sysfnt.TEX`` (256x128): one glyph per cell, its 16 levels in the low 4 bits of each pixel;
  palette ``c`` (0-7) shows text colour ``c``.
- **Japanese** ``sysfnt.TEX`` (256x256): two glyphs per cell, glyph ``n`` at cell ``n // 2``, an even
  glyph in the low 2 bits and an odd one in the high 2 bits (4 levels each); palette ``2c`` shows the
  even glyphs in colour ``c``, ``2c + 1`` the odd ones.
- **Japanese** ``sysfnt_even.TEX`` / ``sysfnt_odd.TEX``: the even glyphs (low 2 bits) and the odd ones
  (high 2 bits) on their own, palette ``c`` = colour ``c``; their other 2 bits are left alone.

Any of these files can be attached; an edit goes to every attached file holding that glyph.
"""
from __future__ import annotations

import os
from typing import List, Tuple

from PIL import Image

from FF8GameData.tex.texfile import TexFile

CELL = 12
COLUMNS = 21
_NAMES = {"sysfnt": "all", "sysfnt_even": "even", "sysfnt_odd": "odd"}


class LowresFont:
    def __init__(self, japanese: bool):
        self.japanese = japanese
        self.textures: List[Tuple[str, TexFile, str]] = []   # (path, texture, "all" / "even" / "odd")

    @staticmethod
    def kind_of(path: str) -> str:
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        if stem not in _NAMES or not path.lower().endswith(".tex"):
            raise ValueError(f"{os.path.basename(path)} is not a low-resolution font texture "
                             "(sysfnt.TEX, sysfnt_even.TEX, sysfnt_odd.TEX)")
        return _NAMES[stem]

    def attach(self, path: str):
        """Add a texture; sysfnt_even / sysfnt_odd bring their other half when it is next to them."""
        kind = self.kind_of(path)
        if kind != "all" and not self.japanese:
            raise ValueError("sysfnt_even / sysfnt_odd are Japanese font textures, this font is not")
        paths = [path]
        if kind != "all":
            other = "sysfnt_odd" if kind == "even" else "sysfnt_even"
            folder = os.path.dirname(os.path.abspath(path))
            paths += [os.path.join(folder, entry) for entry in os.listdir(folder)
                      if entry.lower() == other + ".tex"]
        loaded = []
        for texture_path in paths:
            tex = TexFile.read(texture_path)
            needed = (256, 252) if self.japanese else (256, 120)
            if tex.width != needed[0] or tex.height < needed[1]:
                raise ValueError(f"{os.path.basename(texture_path)} is {tex.width}x{tex.height}, "
                                 f"this font needs {needed[0]}x{needed[1]}")
            loaded.append((texture_path, tex, self.kind_of(texture_path)))
        known = {os.path.abspath(p) for p, _t, _k in self.textures}
        self.textures += [t for t in loaded if os.path.abspath(t[0]) not in known]

    @property
    def paths(self) -> List[str]:
        return [path for path, _tex, _kind in self.textures]

    def write(self):
        for path, tex, _kind in self.textures:
            tex.write(path)

    # -- glyph addressing --------------------------------------------------------------------------
    def _holders(self, glyph: int):
        """(texture, palette for colour 0, shift) of every attached file holding that glyph, the
        combined sysfnt.TEX first."""
        odd = glyph % 2
        holders = []
        for _path, tex, kind in sorted(self.textures, key=lambda t: t[2] != "all"):
            if not self.japanese:
                holders.append((tex, 0, 0, 1))
            elif kind == "all":
                holders.append((tex, odd, 2 * odd, 2))
            elif kind == ("odd" if odd else "even"):
                holders.append((tex, 0, 2 * odd, 1))
        return holders

    def _offset(self, glyph: int, x: int, y: int) -> int:
        cell = glyph // 2 if self.japanese else glyph
        return ((cell // COLUMNS) * CELL + y) * 256 + (cell % COLUMNS) * CELL + x

    def has_letter(self, glyph: int) -> bool:
        holders = self._holders(glyph)
        return bool(holders) and self._offset(glyph, CELL - 1, CELL - 1) < len(holders[0][0].pixels)

    @property
    def level_values(self) -> List[int]:
        return [0, 1, 2, 3] if self.japanese else list(range(16))

    @property
    def _mask(self) -> int:
        return 3 if self.japanese else 15

    def level(self, glyph: int, x: int, y: int) -> int:
        tex, _palette, shift, _step = self._holders(glyph)[0]
        return (tex.pixels[self._offset(glyph, x, y)] >> shift) & self._mask

    def set_level(self, glyph: int, x: int, y: int, level: int):
        offset = self._offset(glyph, x, y)
        for tex, _palette, shift, _step in self._holders(glyph):
            mask = self._mask << shift
            tex.pixels[offset] = (tex.pixels[offset] & ~mask & 0xFF) | ((level << shift) & mask)

    def levels(self, glyph: int) -> List[int]:
        if not self.has_letter(glyph):
            return [0] * (CELL * CELL)
        tex, _palette, shift, _step = self._holders(glyph)[0]
        start, mask, pixels = self._offset(glyph, 0, 0), self._mask, tex.pixels
        return [(pixels[start + y * 256 + x] >> shift) & mask for y in range(CELL) for x in range(CELL)]

    def set_levels(self, glyph: int, levels: List[int]):
        for i, level in enumerate(levels):
            self.set_level(glyph, i % CELL, i // CELL, level)

    def _palette(self, color: int, glyph: int):
        """The colour of each level of that glyph in that text colour (palettes don't change: cached)."""
        tex, palette, shift, step = self._holders(glyph)[0]
        index = ((color % 8) * step + palette) % tex.num_palettes
        key = (id(tex), index, shift)
        cache = self.__dict__.setdefault("_palettes", {})
        if key not in cache:
            colors = tex.palette(index)
            cache[key] = [colors[level << shift] for level in self.level_values]
        return cache[key]

    def level_color(self, color: int, glyph: int, level: int):
        return self._palette(color, glyph)[level]

    def level_colors(self, color: int, glyph: int = 0):
        return list(self._palette(color, glyph))

    def letter_image(self, glyph: int, color: int = 7) -> Image.Image:
        image = Image.new("RGBA", (CELL, CELL))
        if self.has_letter(glyph):
            palette = self._palette(color, glyph)
            image.putdata([palette[level] for level in self.levels(glyph)])
        return image
