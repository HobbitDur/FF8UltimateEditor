"""Build a single linear font atlas from the Japanese even/odd ``.TEX`` pair.

The Japanese FF8 font ships as two textures, ``sysfnt_even.TEX`` and
``sysfnt_odd.TEX``, split by glyph-cell parity: even cell indices (0, 2, 4, ...)
live in the *even* texture, odd indices (1, 3, 5, ...) in the *odd* one, each
packed at position ``cell // 2`` in a 21-column, 12x12-pixel grid.

The Japanese executable understands that split; the Western executable (which
the ILP-JP mod keeps, for J8 compatibility) does not — it addresses ONE linear
atlas as ``cell -> (row = cell // 21, col = cell % 21)``. This module
de-interleaves even/odd back into that single linear atlas so the Western
engine can sample Japanese glyphs with no code change.

The two source textures also encode the 4-level antialiasing ramp in different
bit positions (an artefact of the PSX 4bpp CLUT alignment that forced the split
in the first place):

    even pixel: ramp = index & 3        (palette [T, L, M, D] repeated)
    odd  pixel: ramp = index >> 2       (palette [T,T,T,T, L,L,L,L, ...])

Both are normalised to the even scheme (``index & 3``) so a single palette set
(the even texture's) drives the whole atlas — the same 4-level-ramp + colour-
palette layout the Western font already uses.
"""
from __future__ import annotations

from typing import List

from .texfile import TexFile, HEADER_SIZE

# Font grid geometry, shared by every FF8 sysfnt texture.
CELL = 12
COLS = 21
# The four FF8 Japanese font tables (table 0 = single-byte glyphs, tables 1-3
# reached via the 0x19/0x1a/0x1b lead bytes). See FF8GameData/Resources/sysfnt_jp.txt.
JP_GLYPH_COUNT = 224 * 3 + 208  # 880


def _ramp_even(index: int) -> int:
    return index & 0x03


def _ramp_odd(index: int) -> int:
    return (index >> 2) & 0x03


def _glyph_block(tex: TexFile, slot: int, ramp) -> List[List[int]]:
    """Return the 12x12 ramp-normalised pixels of packed slot ``slot``."""
    sx = CELL * (slot % COLS)
    sy = CELL * (slot // COLS)
    block = []
    for y in range(CELL):
        row = []
        base = (sy + y) * tex.width + sx
        for x in range(CELL):
            row.append(ramp(tex.pixels[base + x] & 0x0F))
        block.append(row)
    return block


def build_linear_atlas(even: TexFile, odd: TexFile,
                       glyph_count: int = JP_GLYPH_COUNT,
                       width: int = 256) -> TexFile:
    """De-interleave the even/odd font pair into one linear atlas TexFile.

    The result reuses the even texture's header and palette block (patched to
    the new dimensions); pixels are ramp indices 0-3 laid out so that cell N is
    at ``(12 * (N % 21), 12 * (N // 21))`` — exactly what the Western engine
    samples. Colour is still selected at draw time via palette/CLUT."""
    rows = (glyph_count + COLS - 1) // COLS
    height = rows * CELL
    pixels = bytearray(width * height)  # 0 = transparent everywhere by default

    for cell in range(glyph_count):
        if cell % 2 == 0:
            block = _glyph_block(even, cell // 2, _ramp_even)
        else:
            block = _glyph_block(odd, cell // 2, _ramp_odd)
        dx = CELL * (cell % COLS)
        dy = CELL * (cell // COLS)
        for y in range(CELL):
            base = (dy + y) * width + dx
            pixels[base:base + CELL] = bytes(block[y])

    return TexFile(
        raw_header=even.raw_header,
        raw_palette=even.raw_palette,
        pixels=pixels,
        num_palettes=even.num_palettes,
        palette_entries=even.palette_entries,
        bpp=even.bpp,
        width=width,
        height=height,
    )


def build_linear_atlas_from_files(even_path: str, odd_path: str,
                                  glyph_count: int = JP_GLYPH_COUNT) -> TexFile:
    """Convenience wrapper: read both ``.TEX`` files and build the atlas."""
    return build_linear_atlas(TexFile.read(even_path), TexFile.read(odd_path),
                              glyph_count=glyph_count)
