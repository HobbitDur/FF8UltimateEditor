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
from typing import Optional

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
