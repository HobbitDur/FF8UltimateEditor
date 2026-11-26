"""The magazine and tutorial page pictures, and the files the PC game really shows them from.

A page's picture is a mngrp.bin raw file (MagPageManager.texture_raw_file), a 256x192 8bpp TIM
placed at VRAM (896, 0) with one 256-colour CLUT at (512, 218). That is the PSX picture: the PC
port never uploads it. Menu_RegisterTexUpload (0x4B3C00) queues the slot number only for a fixed
list of slots, and Menu_images (0x4B3D00) turns each one into a standalone texture of the menu
folder through a hard-coded switch - slot 28 is menu/mag00.TEX, slot 24 menu/mag07.TEX... So:

* a page can only show one of the PC_PICTURE_FILES pictures in game: a slot outside the list
  (an empty mngrp slot included) is never uploaded, and its page shows no picture;
* a new picture for a new book replaces one of those files (and the mngrp copy, which the editor
  previews and the PSX path reads);
* or, with FFNx's AddMorePictures, it is a new one: a page on slot 185-255 shows
  menu/magNNN.TEX (NNN = the slot) when the mod provides that file. The slot must hold a TIM in
  mngrp.bin too: the game takes the picture's VRAM placement from its header. The tools add them
  after the last slot mngrp.bin uses (206 in the game's), so the slots before keep their places.

The .TEX copy is 256x256: the picture, then 64 rows of index 0. Index 0 of both palettes is
transparent black, the other 255 colours are opaque - the layout every vanilla picture has, and
the one encode_picture writes.
"""
import os
from typing import List, Optional, Tuple

from PIL import Image

from FF8GameData.tex.texfile import TexFile
from FF8GameData.tim.timfile import PalettedTim, decode_tim

PICTURE_WIDTH = 256
PICTURE_HEIGHT = 192
NB_COLOR = 256

# mngrp slot -> the menu texture the PC game shows for it (Menu_images, 0x4B3D00). Only the page
# pictures: the switch also has the faces, the start screen and the pad pictures.
PC_PICTURE_FILES = {
    28: "mag00", 29: "mag01", 30: "mag02", 31: "mag03", 32: "mag04", 33: "mag05", 34: "mag06",
    24: "mag07", 44: "mag08", 45: "mag09",
    48: "mc00", 49: "mc01", 50: "mc02", 51: "mc03", 52: "mc04",
    53: "mc05", 54: "mc06", 55: "mc07", 56: "mc08", 57: "mc09",
    71: "mag10", 72: "mag11", 73: "mag12", 74: "mag13", 75: "mag14",
    180: "mag15", 181: "mag16", 182: "mag17", 183: "mag18", 184: "mag19",
}

# FFNx's AddMorePictures: slots past the game's switches show menu/magNNN.TEX
ADDED_FIRST_SLOT = 185
ADDED_LAST_SLOT = 255

# A carrier slot whose TIM header places a picture like every page picture (VRAM (896, 0), CLUT
# (512, 218)): an added picture's TIM is built on it.
TEMPLATE_SLOT = 28

# The header of a page picture .TEX (mag00.TEX's, the two runtime pointers it keeps at 0x60 and
# 0xD8 zeroed): 1 palette of 256 colours, 8 bpp, 256x256, colour key on, placed like the TIM.
DEFAULT_TEX_HEADER = bytes.fromhex(
    "020000000000000001000000000000000700000004000000080000000000000008000000080000002000000000000000"
    "010000000001000008000000000100000001000000000000000000000100000008000000000000000001000000010000"
    "000000000800000001000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000ff00000004000000000000000000000000000000000000000000000000020000da0000008003000000000000")

Color = Tuple[int, int, int]


def is_added_slot(raw_file: int) -> bool:
    """A slot number an added picture may take (185-255). Being in that range is not enough to be
    one: the game's own mngrp.bin uses 188-205 for other data; see is_page_picture_tim."""
    return ADDED_FIRST_SLOT <= raw_file <= ADDED_LAST_SLOT


def is_page_picture_tim(data) -> bool:
    """Whether a mngrp slot holds a page picture: an 8bpp TIM of 256x192 texels (what Add new
    picture writes). Slots 188-205 of the game hold other data, which this keeps out."""
    tim = PalettedTim.parse(bytes(data)) if data else None
    return tim is not None and tim.bpp == 1 and (tim.width, tim.height) == (256, 192)


def pc_picture_name(raw_file: int) -> Optional[str]:
    """The menu texture ("mag00"...) the PC game shows for a page picture slot: one of the game's
    30, or magNNN for a slot 185-255 (with FFNx's AddMorePictures). None for a slot it never
    uploads."""
    if is_added_slot(raw_file):
        return f"mag{raw_file:03d}"
    return PC_PICTURE_FILES.get(raw_file)


def default_tex_template() -> TexFile:
    """An empty page picture .TEX, for a picture written where no vanilla .TEX sits to copy."""
    palette = bytes(NB_COLOR * 4)
    return TexFile(DEFAULT_TEX_HEADER, palette, bytearray(PICTURE_WIDTH * PICTURE_WIDTH), 1, NB_COLOR, 8,
                   PICTURE_WIDTH, PICTURE_WIDTH)


def pc_picture_file_name(raw_file: int) -> Optional[str]:
    name = pc_picture_name(raw_file)
    return f"{name}.TEX" if name else None


def tex_to_image(tex: TexFile) -> Image.Image:
    """The picture of a page .TEX (8bpp, one 256-colour palette), cropped to the 256x192 the page
    uses. TexFile.to_image reads 4bpp font atlases, so it only looks at the low nibble."""
    palette = tex.palette(0)
    lut = [(r, g, b, 255 if a else 0) for r, g, b, a in palette]
    lut += [(0, 0, 0, 0)] * (NB_COLOR - len(lut))
    height = min(tex.height, PICTURE_HEIGHT)
    image = Image.new("RGBA", (tex.width, height))
    image.putdata([lut[index] for index in tex.pixels[:tex.width * height]])
    return image


def prepare_picture(image: Image.Image) -> Image.Image:
    """The image as the page picture: 256x192 RGBA. A 256x256 one (a .TEX export) is cropped to its
    top 192 rows; any other size is refused, as the page sprites crop fixed rectangles out of it."""
    if image.size == (PICTURE_WIDTH, PICTURE_WIDTH):
        image = image.crop((0, 0, PICTURE_WIDTH, PICTURE_HEIGHT))
    if image.size != (PICTURE_WIDTH, PICTURE_HEIGHT):
        raise ValueError(f"A page picture is {PICTURE_WIDTH}x{PICTURE_HEIGHT} pixels, this image is "
                         f"{image.size[0]}x{image.size[1]}")
    return image.convert("RGBA")


def quantize_picture(image: Image.Image) -> Tuple[List[Color], bytes]:
    """(palette, indices) of a 256x192 image: index 0 is transparent black and takes every pixel
    whose alpha is under 128, the 255 others are the opaque colours. A colour too dark to tell from
    black is lifted a little, so neither format reads it as transparent (a 0x0000 TIM word, the
    .TEX colour key)."""
    image = prepare_picture(image)
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    quantized = rgb.quantize(colors=NB_COLOR - 1, method=Image.Quantize.MEDIANCUT)
    flat = quantized.getpalette()[:3 * (NB_COLOR - 1)]
    flat += [0] * (3 * (NB_COLOR - 1) - len(flat))
    palette: List[Color] = [(0, 0, 0)]
    for i in range(NB_COLOR - 1):
        r, g, b = flat[3 * i:3 * i + 3]
        if max(r, g, b) < 8:
            r, g, b = 8, 8, 8
        palette.append((r, g, b))
    indices = bytes(0 if a < 128 else index + 1
                    for index, a in zip(quantized.tobytes(), alpha.tobytes()))
    return palette, indices


def _bgr555(color: Color) -> int:
    r, g, b = (round(channel * 31 / 255) for channel in color)
    return r | (g << 5) | (b << 10)


def encode_picture_tim(palette: List[Color], indices: bytes, template: bytes) -> bytes:
    """The mngrp TIM of a picture, placed in VRAM (CLUT and image) exactly like `template`, the
    picture it replaces."""
    source = PalettedTim.parse(template)
    if source is None or source.bpp != 1:
        raise ValueError("The picture to replace is not an 8bpp TIM")
    clut = [0] + [_bgr555(color) or 0x8000 for color in palette[1:]]
    tim = PalettedTim(1, source.clut_x, source.clut_y, [clut], source.image_x, source.image_y,
                      PICTURE_WIDTH, PICTURE_HEIGHT, indices)
    return tim.to_bytes()


def encode_picture_tex(palette: List[Color], indices: bytes, template: TexFile) -> TexFile:
    """The PC .TEX of a picture, with `template`'s header (the file it replaces): its 256x256
    canvas, the picture in the top 192 rows and index 0 below, and the template's opaque alpha."""
    if template.palette_entries != NB_COLOR or template.num_palettes < 1 or template.width != PICTURE_WIDTH \
            or template.height < PICTURE_HEIGHT:
        raise ValueError("The .TEX to replace is not a 256-colour page picture")
    opaque_alpha = max(a for _r, _g, _b, a in template.palette(0)) or 255
    raw_palette = bytearray()
    for index, (r, g, b) in enumerate(palette):
        raw_palette.extend((b, g, r, 0 if index == 0 else opaque_alpha))
    # Any extra palette of the template keeps its bytes (no vanilla picture has one)
    raw_palette.extend(template.raw_palette[len(raw_palette):])
    pixels = bytearray(indices) + bytearray(template.width * template.height - len(indices))
    return TexFile(template.raw_header, raw_palette, pixels, template.num_palettes,
                   template.palette_entries, template.bpp, template.width, template.height)


def picture_from_indices(palette: List[Color], indices: bytes) -> Image.Image:
    """The 256x192 RGBA picture of quantize_picture's (palette, indices)."""
    lut = [(0, 0, 0, 0)] + [(r, g, b, 255) for r, g, b in palette[1:]]
    image = Image.new("RGBA", (PICTURE_WIDTH, PICTURE_HEIGHT))
    image.putdata([lut[index] for index in indices])
    return image


def tex_path(menu_folder: str, raw_file: int) -> str:
    """Where the PC texture of a picture slot sits: next to mngrp.bin, in the menu folder."""
    return os.path.join(menu_folder, pc_picture_file_name(raw_file))


def tex_template(menu_folder: str, raw_file: int) -> TexFile:
    """The .TEX a picture of slot `raw_file` takes its header from: the slot's own one, else any
    other page picture of the folder (they all share the same header), else the default one."""
    if not menu_folder:
        return default_tex_template()
    candidates = [tex_path(menu_folder, raw_file)] + [os.path.join(menu_folder, f"{name}.TEX")
                                                      for name in PC_PICTURE_FILES.values()]
    for path in candidates:
        if os.path.exists(path):
            try:
                return TexFile.read(path)
            except (OSError, ValueError):
                continue
    return default_tex_template()


def write_picture_tex(menu_folder: str, raw_file: int, palette: List[Color], indices: bytes) -> bool:
    """Write the .TEX the PC game shows for slot `raw_file` into the menu folder. False without a
    folder (nothing written)."""
    if not menu_folder:
        return False
    template = tex_template(menu_folder, raw_file)
    encode_picture_tex(palette, indices, template).write(tex_path(menu_folder, raw_file))
    return True


def replace_picture_tim(mngrp_manager, raw_file: int, palette: List[Color], indices: bytes) -> bytes:
    """Put the picture's TIM in slot `raw_file` of a loaded MngrpManager, placed in VRAM like the
    one it replaces. Returns the TIM bytes."""
    section = mngrp_manager.mngrp.get_section_list()[raw_file]
    data = encode_picture_tim(palette, indices, bytes(section.get_data_hex()))
    mngrp_manager.mngrp.set_section_by_id_and_bytearray(section.id, bytearray(data))
    return data


def slot_picture(menu_folder: str, raw_file: int, tim_bytes: bytes = b"") -> Tuple[Optional[Image.Image], str]:
    """(image, where it comes from) of a picture slot as the PC game shows it: its .TEX in the menu
    folder, else the mngrp copy `tim_bytes`."""
    path = tex_path(menu_folder, raw_file) if pc_picture_name(raw_file) and menu_folder else ""
    if path and os.path.exists(path):
        try:
            return tex_to_image(TexFile.read(path)), f"menu/{os.path.basename(path)}"
        except (OSError, ValueError):
            pass
    tim = decode_tim(tim_bytes) if tim_bytes else None
    if tim is not None:
        return tim.image, "mngrp copy (no .TEX found next to mngrp.bin)"
    return None, ""
