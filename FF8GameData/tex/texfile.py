"""FF8 PC ``.TEX`` texture reader/writer.

This is the FF7/FF8 PC texture container (distinct from the PSX ``TIM`` handled
by :mod:`FF8GameData.tim.timfile`). On-disk layout::

    0x000  240-byte header. Meaningful uint32 LE fields used here:
              0x00 version         (2 for FF8)
              0x08 color_key flag
              0x30 num_palettes
              0x34 palette_entries (colours per palette, 16 for the fonts)
              0x38 bpp             (4 for the fonts, but see below)
              0x3C width
              0x40 height
    0x0F0  palette block : num_palettes * palette_entries * 4 bytes.
           Each colour is 4 bytes; for the fonts the observed order is R,G,B,A
           with A in 0..254 (0 = transparent).
    ...    pixel block   : width * height bytes, one byte per pixel. Even though
           the header advertises 4bpp, the pixels are stored unpacked (one byte
           per pixel) and only the low nibble is a palette index.

Only the numeric fields above are interpreted; the rest of the 240-byte header
is preserved verbatim so a read -> write round-trip is byte-exact.
"""
from __future__ import annotations

import struct
from typing import List, Optional, Tuple

from PIL import Image

HEADER_SIZE = 240

# Header field offsets (uint32 LE).
_OFF_VERSION = 0x00
_OFF_COLOR_KEY = 0x08
_OFF_NUM_PALETTES = 0x30
_OFF_PALETTE_ENTRIES = 0x34
_OFF_BPP = 0x38
_OFF_WIDTH = 0x3C
_OFF_HEIGHT = 0x40

Color = Tuple[int, int, int, int]  # (r, g, b, a)


class TexFile:
    """A decoded FF8 PC ``.TEX`` texture.

    Attributes:
        num_palettes / palette_entries / bpp / width / height: header values.
        raw_header: the original 240-byte header (patched on write).
        raw_palette: the palette block bytes (kept verbatim for lossless write).
        pixels: ``bytearray`` of ``width * height`` palette indices.
    """

    def __init__(self, raw_header: bytes, raw_palette: bytes, pixels: bytearray,
                 num_palettes: int, palette_entries: int, bpp: int,
                 width: int, height: int):
        self.raw_header = bytearray(raw_header)
        self.raw_palette = bytearray(raw_palette)
        self.pixels = pixels
        self.num_palettes = num_palettes
        self.palette_entries = palette_entries
        self.bpp = bpp
        self.width = width
        self.height = height

    # ------------------------------------------------------------------ read
    @classmethod
    def from_bytes(cls, data: bytes) -> "TexFile":
        if len(data) < HEADER_SIZE:
            raise ValueError(f"TEX too small ({len(data)} bytes)")
        num_palettes = struct.unpack_from("<I", data, _OFF_NUM_PALETTES)[0]
        palette_entries = struct.unpack_from("<I", data, _OFF_PALETTE_ENTRIES)[0]
        bpp = struct.unpack_from("<I", data, _OFF_BPP)[0]
        width = struct.unpack_from("<I", data, _OFF_WIDTH)[0]
        height = struct.unpack_from("<I", data, _OFF_HEIGHT)[0]

        palette_size = num_palettes * palette_entries * 4
        pixel_offset = HEADER_SIZE + palette_size
        pixel_size = width * height
        expected = pixel_offset + pixel_size
        if expected != len(data):
            raise ValueError(
                f"TEX size mismatch: header implies {expected} bytes "
                f"({width}x{height}, {num_palettes} palettes) but file is {len(data)}")

        raw_header = data[:HEADER_SIZE]
        raw_palette = data[HEADER_SIZE:pixel_offset]
        pixels = bytearray(data[pixel_offset:pixel_offset + pixel_size])
        return cls(raw_header, raw_palette, pixels, num_palettes,
                   palette_entries, bpp, width, height)

    @classmethod
    def read(cls, path: str) -> "TexFile":
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())

    # ----------------------------------------------------------------- write
    def to_bytes(self) -> bytes:
        header = bytearray(self.raw_header)
        # Patch the numeric fields that a rebuilt atlas may have changed.
        struct.pack_into("<I", header, _OFF_NUM_PALETTES, self.num_palettes)
        struct.pack_into("<I", header, _OFF_PALETTE_ENTRIES, self.palette_entries)
        struct.pack_into("<I", header, _OFF_WIDTH, self.width)
        struct.pack_into("<I", header, _OFF_HEIGHT, self.height)
        if len(self.pixels) != self.width * self.height:
            raise ValueError("pixel buffer does not match width*height")
        if len(self.raw_palette) != self.num_palettes * self.palette_entries * 4:
            raise ValueError("palette buffer does not match palette dimensions")
        return bytes(header) + bytes(self.raw_palette) + bytes(self.pixels)

    def write(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.to_bytes())

    # --------------------------------------------------------------- palettes
    def palette(self, index: int = 0) -> List[Color]:
        """Return palette ``index`` as a list of ``(r, g, b, a)`` tuples."""
        if not 0 <= index < self.num_palettes:
            raise IndexError(f"palette {index} out of range (0..{self.num_palettes - 1})")
        base = index * self.palette_entries * 4
        out: List[Color] = []
        for i in range(self.palette_entries):
            r, g, b, a = self.raw_palette[base + i * 4: base + i * 4 + 4]
            out.append((r, g, b, a))
        return out

    def to_image(self, palette_index: int = 0) -> Image.Image:
        """Render the texture to a PIL RGBA image using the given palette.

        Alpha 0 stays transparent; any non-zero source alpha becomes opaque
        (the font's 0/254 alpha is effectively a 1-bit mask)."""
        pal = self.palette(palette_index)
        rgba = bytearray(self.width * self.height * 4)
        for i, px in enumerate(self.pixels):
            r, g, b, a = pal[px & 0x0F] if (px & 0x0F) < len(pal) else (0, 0, 0, 0)
            o = i * 4
            rgba[o:o + 4] = bytes((r, g, b, 255 if a else 0))
        return Image.frombytes("RGBA", (self.width, self.height), bytes(rgba))
