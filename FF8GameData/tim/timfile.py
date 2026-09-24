"""Shared PSX TIM texture decoder.

Decodes standard PlayStation TIM textures (4/8-bit paletted, 16-bit direct)
into PIL RGBA images, preserving PSX per-texel semi-transparency:

  16-bit color value (bits: STP RRRRR GGGGG BBBBB, little-endian BGR555)
    0x0000              -> fully transparent (never drawn)
    bit 15 (0x8000) set -> semi-transparent when the primitive enables ABE;
                           PSX blend mode 0 (0.5*back + 0.5*front) maps to a
                           straight 50% alpha here
    otherwise           -> opaque

Encoding semi-transparency as an alpha value lets a normal alpha-blending
renderer reproduce the look. Whether a given face actually blends its STP
texels is a per-face property (the primitive's ABE bit); callers that need
that gate keep an opaque copy (alpha 128 -> 255) for non-ABE faces.

Used by the Seed field-model viewer (mch/chara.one) and available to any
tool that has raw TIM bytes.
"""
import struct
from typing import List, Optional, Tuple

from PIL import Image

# PSX blend mode 0 (0.5*back + 0.5*front) as a straight alpha.
SEMI_TRANSPARENT_ALPHA = 128


def _u32(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], byteorder='little')


def _u16(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder='little')


def texel_alpha(color: int) -> int:
    """Alpha for a 16-bit PSX texel/CLUT value (see module docstring)."""
    if color == 0:
        return 0
    if color & 0x8000:
        return SEMI_TRANSPARENT_ALPHA
    return 255


def force_opaque(image: Image.Image) -> Image.Image:
    """Return a copy where semi-transparent texels are made opaque (alpha
    128 -> 255); fully transparent texels stay transparent. Used for faces
    that do not enable ABE, where STP texels render opaque."""
    red, green, blue, alpha = image.split()
    alpha = alpha.point(lambda v: 255 if v > 0 else 0)
    return Image.merge('RGBA', (red, green, blue, alpha))


class TimImage:
    """A decoded TIM texture: a PIL RGBA image plus its VRAM placement."""

    def __init__(self, image: Image.Image, bpp: int, image_x: int, image_y: int):
        self.image = image
        self.bpp = bpp          # 0: 4bpp, 1: 8bpp, 2: 16bpp
        self.image_x = image_x  # VRAM x of the image block
        self.image_y = image_y  # VRAM y of the image block

    def __repr__(self):
        return (f"TimImage({self.image.width}x{self.image.height}, bpp:{self.bpp}, "
                f"vram:({self.image_x},{self.image_y}))")


def decode_tim(data, offset: int = 0, palette_index: int = 0) -> Optional[TimImage]:
    """Decode a TIM at `data[offset:]` into a TimImage, or None if it is not a
    valid TIM. `palette_index` selects the CLUT row for paletted images."""
    if offset + 8 > len(data) or _u32(data, offset) != 0x10:
        return None
    flags = _u32(data, offset + 4)
    bpp = flags & 0x3
    has_clut = bool(flags & 0x8)
    pos = offset + 8

    palette = None
    if has_clut:
        clut_size = _u32(data, pos)
        clut_width = _u16(data, pos + 8)      # colors per CLUT row
        clut_height = _u16(data, pos + 10)    # number of CLUT rows
        row = palette_index if 0 <= palette_index < max(clut_height, 1) else 0
        palette = []
        color_pos = pos + 12 + row * clut_width * 2
        for i in range(clut_width):
            color = _u16(data, color_pos + i * 2)
            red = round((color & 0x1F) * 255 / 31)
            green = round(((color >> 5) & 0x1F) * 255 / 31)
            blue = round(((color >> 10) & 0x1F) * 255 / 31)
            palette.append((red, green, blue, texel_alpha(color)))
        pos += clut_size

    image_x = _u16(data, pos + 4)
    image_y = _u16(data, pos + 6)
    width_16bit = _u16(data, pos + 8)
    height = _u16(data, pos + 10)
    pixel_pos = pos + 12

    if bpp == 0:
        width = width_16bit * 4
    elif bpp == 1:
        width = width_16bit * 2
    else:
        width = width_16bit
    if width <= 0 or height <= 0 or width > 2048 or height > 2048:
        return None

    rgba = bytearray(width * height * 4)
    if bpp == 0 and palette:
        for i in range(width * height // 2):
            byte = data[pixel_pos + i]
            for half, index in enumerate((byte & 0x0F, byte >> 4)):
                out = (i * 2 + half) * 4
                rgba[out:out + 4] = bytes(palette[index])
    elif bpp == 1 and palette:
        for i in range(width * height):
            out = i * 4
            rgba[out:out + 4] = bytes(palette[data[pixel_pos + i] % len(palette)])
    elif bpp == 2:
        for i in range(width * height):
            color = _u16(data, pixel_pos + i * 2)
            out = i * 4
            rgba[out] = round((color & 0x1F) * 255 / 31)
            rgba[out + 1] = round(((color >> 5) & 0x1F) * 255 / 31)
            rgba[out + 2] = round(((color >> 10) & 0x1F) * 255 / 31)
            rgba[out + 3] = texel_alpha(color)
    else:
        return None

    return TimImage(Image.frombytes('RGBA', (width, height), bytes(rgba)), bpp, image_x, image_y)


def word_to_rgba(color: int) -> Tuple[int, int, int, int]:
    """8-bit RGBA of a 16-bit PSX CLUT word, same expansion as decode_tim."""
    return (round((color & 0x1F) * 255 / 31), round(((color >> 5) & 0x1F) * 255 / 31),
            round(((color >> 10) & 0x1F) * 255 / 31), texel_alpha(color))


class PalettedTim:
    """A 4/8bpp TIM kept as raw CLUT words + per-texel palette indices, so an edit can be
    written back without re-quantizing texels that did not change (see encode_indices)."""

    def __init__(self, bpp: int, clut_x: int, clut_y: int, clut_rows: List[List[int]],
                 image_x: int, image_y: int, width: int, height: int, indices: bytes):
        self.bpp = bpp                # 0: 4bpp, 1: 8bpp
        self.clut_x = clut_x
        self.clut_y = clut_y
        self.clut_rows = clut_rows    # rows of 16-bit words
        self.image_x = image_x        # VRAM halfword x
        self.image_y = image_y
        self.width = width            # texels
        self.height = height
        self.indices = indices        # one byte per texel, row-major

    @classmethod
    def parse(cls, data) -> Optional['PalettedTim']:
        """None when `data` is not a 4/8bpp TIM with a CLUT."""
        if len(data) < 20 or _u32(data, 0) != 0x10:
            return None
        flags = _u32(data, 4)
        bpp = flags & 0x3
        if bpp not in (0, 1) or not flags & 0x8:
            return None
        clut_size = _u32(data, 8)
        clut_x, clut_y = _u16(data, 12), _u16(data, 14)
        clut_w, clut_h = _u16(data, 16), _u16(data, 18)
        clut_rows = [[_u16(data, 20 + (r * clut_w + i) * 2) for i in range(clut_w)]
                     for r in range(clut_h)]
        pos = 8 + clut_size
        image_x, image_y = _u16(data, pos + 4), _u16(data, pos + 6)
        width = _u16(data, pos + 8) * (4 if bpp == 0 else 2)
        height = _u16(data, pos + 10)
        raw = bytes(data[pos + 12: pos + 12 + width * height // (2 if bpp == 0 else 1)])
        if bpp == 0:
            indices = bytes(v for b in raw for v in (b & 0x0F, b >> 4))
        else:
            indices = raw
        if len(indices) != width * height:
            return None
        return cls(bpp, clut_x, clut_y, clut_rows, image_x, image_y, width, height, indices)

    def to_bytes(self) -> bytes:
        clut_w = len(self.clut_rows[0])
        clut = b''.join(w.to_bytes(2, 'little') for row in self.clut_rows for w in row)
        if self.bpp == 0:
            pixels = bytes((self.indices[i] & 0x0F) | ((self.indices[i + 1] & 0x0F) << 4)
                           for i in range(0, len(self.indices), 2))
            width_hw = self.width // 4
        else:
            pixels = bytes(self.indices)
            width_hw = self.width // 2
        out = bytearray(b"\x10\x00\x00\x00")
        out += (0x08 | self.bpp).to_bytes(4, 'little')
        out += struct.pack("<IHHHH", 12 + len(clut), self.clut_x, self.clut_y, clut_w, len(self.clut_rows))
        out += clut
        out += struct.pack("<IHHHH", 12 + len(pixels), self.image_x, self.image_y, width_hw, self.height)
        out += pixels
        return bytes(out)


def _to5(rgb):
    """8-bit channel(s) -> 5-bit, inverse of the round(v*255/31) expansion."""
    import numpy as np
    return np.rint(np.asarray(rgb, dtype=np.float64) * 31 / 255).astype(np.int32)


def encode_clut(rgba_rows, source_rows: Optional[List[List[int]]] = None) -> List[List[int]]:
    """CLUT words from an (rows, colors, 4) RGBA array. A color whose 5-bit RGB and
    transparency class match the source word at the same slot keeps that word verbatim
    (preserves its STP bit); a changed one gets alpha 0 -> 0x0000 (transparent), otherwise
    BGR555 with the source STP bit, and pure black is written 0x8000 so it stays opaque."""
    import numpy as np
    rgba_rows = np.asarray(rgba_rows)
    rows = []
    for r in range(rgba_rows.shape[0]):
        row = []
        for i in range(rgba_rows.shape[1]):
            red, green, blue = (int(v) for v in _to5(rgba_rows[r, i, :3]))
            transparent = rgba_rows[r, i, 3] == 0
            src = None
            if source_rows and r < len(source_rows) and i < len(source_rows[r]):
                src = source_rows[r][i]
            if src is not None:
                s = word_to_rgba(src)
                if (s[3] == 0) == transparent and (transparent or tuple(_to5(s[:3])) == (red, green, blue)):
                    row.append(src)
                    continue
            if transparent:
                row.append(0)
                continue
            word = red | (green << 5) | (blue << 10) | ((src or 0) & 0x8000)
            row.append(word or 0x8000)
        rows.append(row)
    return rows


def encode_indices(rgba, clut_row: List[int], source: Optional[PalettedTim] = None) -> bytes:
    """Per-texel palette indices for an (H, W, 4) RGBA image against `clut_row`.

    A texel still showing exactly what `source` rendered there (its old index through its old
    palette) keeps that index, so a palette-only edit (or an untouched texel) never moves to
    another slot - which matters when several slots share a color but not a role (palette
    swaps recolor by slot). Every other texel takes the first slot holding its 5-bit color in
    the source palette, then in `clut_row`, else the nearest color of `clut_row`; transparent
    texels take a 0x0000 slot when there is one."""
    import numpy as np
    rgba = np.asarray(rgba)
    h, w = rgba.shape[:2]
    px5 = _to5(rgba[:, :, :3]).reshape(-1, 3)
    px_transparent = (rgba[:, :, 3] == 0).reshape(-1)
    result = np.full(h * w, -1, dtype=np.int32)

    if source is not None and (source.width, source.height) == (w, h):
        old = np.frombuffer(source.indices, dtype=np.uint8).astype(np.int32)
        old_row = source.clut_rows[0]
        old_rgba = np.array([word_to_rgba(old_row[k]) if k < len(old_row) else (0, 0, 0, 0)
                             for k in range(256)])
        old_px = old_rgba[old]
        same = (px_transparent == (old_px[:, 3] == 0)) & (
            px_transparent | np.all(_to5(old_px[:, :3]) == px5, axis=1))
        result[same] = old[same]

        # An edited texel painted in a color of the source palette (the texture view shows the
        # source colors) takes that slot, so editing texture and palette together still works
        old_opaque = [k for k in range(len(old_row)) if old_rgba[k, 3] != 0]
        first_slot = {}
        for k in old_opaque:
            first_slot.setdefault(tuple(_to5(old_rgba[k, :3])), k)
        todo = np.nonzero((result < 0) & ~px_transparent)[0]
        if todo.size and first_slot:
            for colour, where in _group_rows(px5[todo], todo):
                slot = first_slot.get(tuple(int(v) for v in colour))
                if slot is not None:
                    result[where] = slot

    pal = np.array([word_to_rgba(word) for word in clut_row])
    pal5 = _to5(pal[:, :3])
    pal_transparent = pal[:, 3] == 0
    transparent_slots = np.nonzero(pal_transparent)[0]
    if transparent_slots.size:
        result[(result < 0) & px_transparent] = transparent_slots[0]
    todo = np.nonzero(result < 0)[0]
    if todo.size:
        opaque_slots = np.nonzero(~pal_transparent)[0]
        if not opaque_slots.size:
            opaque_slots = np.arange(len(clut_row))
        for colour, where in _group_rows(px5[todo], todo):
            dist = ((pal5[opaque_slots] - colour) ** 2).sum(axis=1)
            result[where] = opaque_slots[int(np.argmin(dist))]   # argmin = first exact match
    return result.astype(np.uint8).tobytes()


def _group_rows(values, positions):
    """Yield (row value, positions having it) for each distinct row of `values`."""
    import numpy as np
    uniq, inverse = np.unique(values, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    for k in range(len(uniq)):
        yield uniq[k], positions[inverse == k]


def render_palette_rows(rgba, palette_rgba, source: Optional[PalettedTim] = None) -> list:
    """The (H, W, 4) texture redrawn with each row of an (rows, colors, 4) palette, as a list of
    RGBA arrays (one per row). Texels are mapped to slots exactly as a save would (see
    encode_indices, row 0 = the colors the texture is shown in); STP texels come out opaque,
    only 0x0000 is transparent, like the texture view."""
    import numpy as np
    rgba = np.asarray(rgba)
    clut_rows = encode_clut(palette_rgba, source.clut_rows if source else None)
    indices = np.frombuffer(encode_indices(rgba, clut_rows[0], source), dtype=np.uint8)
    images = []
    for row in clut_rows:
        lut = np.array([(r, g, b, 255 if a else 0) for r, g, b, a in map(word_to_rgba, row)],
                       dtype=np.uint8)
        images.append(lut[np.minimum(indices, len(row) - 1)].reshape(rgba.shape[0], rgba.shape[1], 4))
    return images
