"""
Field background renderer: rebuilds a field's picture from its .mim (palettes + texture
pages) and .map (16x16 tile list) files.

Reference: FF8ModdingWiki, Field File Format / FileFormat_MIM and FileFormat_MAP.

.mim, no header, two fixed sizes:
  type 1 (438272 bytes): 24 palettes (0x3000 bytes) + a 1664x256 byte image (13 pages of 128)
  type 2 (401408 bytes): 16 palettes (0x2000 bytes) + a 1536x256 byte image (12 pages)
Palettes are 256 PSX colors (R5G5B5 + STP bit); the tiles use palette (id + 8).

.map, 16 bytes per tile, ends with x = 0x7FFF:
  type 1: x i16, y i16, z u16, tex u16, pal u16, src_x u8, src_y u8, layer u8, blend u8,
          anim_id u8, anim_state u8
  type 2: x i16, y i16, src_x u16, src_y u16, z u16, tex u16, pal u16, anim_id u8, anim_state u8
tex: bits 0-3 texture page, bit 4 draw, bits 5-6 blend, bits 7-8 texel depth (0 = 4-bit,
1 = 8-bit, 2 = 16-bit direct color). pal: bits 6-9 palette.
Tiles are drawn from the highest Z (farthest) to the lowest.
"""
import os
import struct

import numpy as np
from PIL import Image

TILE_SIZE = 16
PAGE_WIDTH = 128  # bytes per texture page row
IMAGE_HEIGHT = 256
PALETTE_SIZE = 512  # 256 colors x 2 bytes
PALETTE_ID_OFFSET = 8
MAP_END_X = 0x7FFF
BLEND_NONE = 4
NO_ANIMATION = 0xFF

MIM_TYPES = {  # file size: (palette bytes, image width)
    0x3000 + 0x68000: (0x3000, 1664),
    0x2000 + 0x60000: (0x2000, 1536),
}


class FieldTile:
    def __init__(self, x, y, z, texture_page, depth, palette_id, src_x, src_y, blend, anim_id, anim_state):
        self.x = x
        self.y = y
        self.z = z
        self.texture_page = texture_page
        self.depth = depth  # 0 = 4-bit, 1 = 8-bit, 2 = 16-bit
        self.palette_id = palette_id
        self.src_x = src_x
        self.src_y = src_y
        self.blend = blend
        self.anim_id = anim_id
        self.anim_state = anim_state


def psx_colors_to_rgba(colors: np.ndarray):
    """uint16 PSX colors -> (n, 4) uint8 RGBA; color 0x0000 is transparent."""
    red = (colors & 0x1F) << 3
    green = ((colors >> 5) & 0x1F) << 3
    blue = ((colors >> 10) & 0x1F) << 3
    alpha = np.where(colors == 0, 0, 255)
    return np.stack([red, green, blue, alpha], axis=-1).astype(np.uint8)


def parse_map(map_data: bytes, is_type2: bool):
    tiles = []
    for offset in range(0, len(map_data) - 15, 16):
        if is_type2:
            x, y, src_x, src_y, z, tex, pal, anim_id, anim_state = struct.unpack_from("<hhHHHHHBB", map_data, offset)
            blend = BLEND_NONE
        else:
            x, y, z, tex, pal, src_x, src_y, _layer, blend, anim_id, anim_state = struct.unpack_from(
                "<hhHHHBBBBBB", map_data, offset)
        if x == MAP_END_X:
            break
        tiles.append(FieldTile(x, y, z, tex & 0x0F, (tex >> 7) & 0x03, (pal >> 6) & 0x0F, src_x, src_y,
                               blend, anim_id, anim_state))
    return tiles


def render_background(mim_data: bytes, map_data: bytes, all_animation_states: bool = False):
    """The field background as a PIL RGBA image, plus the (x, y) of the field origin inside it.
    Animated tiles only show their first state unless all_animation_states is set."""
    if len(mim_data) not in MIM_TYPES:
        raise ValueError(f"Unknown .mim size {len(mim_data)}")
    palette_bytes, image_width = MIM_TYPES[len(mim_data)]
    is_type2 = palette_bytes == 0x2000
    palettes = np.frombuffer(mim_data, dtype="<u2", count=palette_bytes // 2).reshape(-1, 256)
    palettes_rgba = psx_colors_to_rgba(palettes.astype(np.uint32))
    image = np.frombuffer(mim_data, dtype=np.uint8, offset=palette_bytes).reshape(IMAGE_HEIGHT, image_width)

    tiles = parse_map(map_data, is_type2)
    if not all_animation_states:
        tiles = [tile for tile in tiles if tile.anim_id == NO_ANIMATION or tile.anim_state == 0]
    if not tiles:
        return Image.new("RGBA", (TILE_SIZE, TILE_SIZE)), (0, 0)
    min_x = min(tile.x for tile in tiles)
    min_y = min(tile.y for tile in tiles)
    width = max(tile.x for tile in tiles) - min_x + TILE_SIZE
    height = max(tile.y for tile in tiles) - min_y + TILE_SIZE
    canvas = np.zeros((height, width, 4), dtype=np.float32)

    for tile in sorted(tiles, key=lambda tile: -tile.z):
        palette_index = min(tile.palette_id + PALETTE_ID_OFFSET, len(palettes_rgba) - 1)
        page_x = tile.texture_page * PAGE_WIDTH
        rows = image[tile.src_y:tile.src_y + TILE_SIZE]
        if rows.shape[0] < TILE_SIZE:
            continue
        if tile.depth == 2:  # 16-bit direct colors
            byte_x = page_x + tile.src_x * 2
            raw = np.ascontiguousarray(rows[:, byte_x:byte_x + TILE_SIZE * 2])
            if raw.shape != (TILE_SIZE, TILE_SIZE * 2):
                continue
            texels = psx_colors_to_rgba(raw.view("<u2").astype(np.uint32)).astype(np.float32)
        else:
            if tile.depth == 1:
                indexes = rows[:, page_x + tile.src_x:page_x + tile.src_x + TILE_SIZE]
            else:
                byte_x = page_x + tile.src_x // 2
                packed = rows[:, byte_x:byte_x + TILE_SIZE // 2]
                indexes = np.empty((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
                if packed.shape == (TILE_SIZE, TILE_SIZE // 2):
                    indexes[:, 0::2] = packed & 0x0F
                    indexes[:, 1::2] = packed >> 4
                else:
                    indexes = packed
            if indexes.shape != (TILE_SIZE, TILE_SIZE):
                continue
            texels = palettes_rgba[palette_index][indexes].astype(np.float32)
        x, y = tile.x - min_x, tile.y - min_y
        target = canvas[y:y + TILE_SIZE, x:x + TILE_SIZE]
        opaque = texels[..., 3] > 0
        if tile.blend == 1:  # additive
            target[..., :3] = np.where(opaque[..., None], np.minimum(target[..., :3] + texels[..., :3], 255),
                                       target[..., :3])
        elif tile.blend == 2:  # subtractive
            target[..., :3] = np.where(opaque[..., None], np.maximum(target[..., :3] - texels[..., :3], 0),
                                       target[..., :3])
        elif tile.blend == 3:  # background + 25% of the tile
            target[..., :3] = np.where(opaque[..., None],
                                       np.minimum(target[..., :3] + texels[..., :3] / 4, 255), target[..., :3])
        else:
            target[opaque] = texels[opaque]
            continue
        target[..., 3] = np.where(opaque, 255, target[..., 3])
    return Image.fromarray(canvas.astype(np.uint8), "RGBA"), (-min_x, -min_y)


def render_field_folder(folder: str, map_name: str = ""):
    """Render <folder>/<map_name>.mim + .map (map_name defaults to the folder name)."""
    map_name = map_name or os.path.basename(os.path.normpath(folder))
    with open(os.path.join(folder, map_name + ".mim"), "rb") as mim_file:
        mim_data = mim_file.read()
    with open(os.path.join(folder, map_name + ".map"), "rb") as map_file:
        map_data = map_file.read()
    return render_background(mim_data, map_data)
