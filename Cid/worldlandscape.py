"""Read-only terrain metadata and low-resolution world textures from wmset.

Format references: FF8ModdingWiki worldmap-wmsetxx-file-format and Deling's
WmxFile/MapPoly; low-resolution page placement verified against FFNx's
ff8_wm_texl_palette_upload_vram. Live previews decode the loaded game files;
the bundled default map is a rendered reference image.
"""
import struct

from FF8GameData.tim.timfile import PalettedTim


GROUND_NAMES = {
    0: 'Forest', 1: 'Frosted forest', 2: 'Grandidi forest', 3: 'Forest',
    4: 'Balamb forest', 5: 'Trabia forest', 6: 'Grassland', 7: 'Dirt / badlands',
    8: 'Desert', 9: 'Snow', 10: 'Beach / shallows', 12: 'Esthar streets',
    14: 'Plateau', 15: 'Grassland mountain edge', 16: 'Mountain edge',
    17: 'Snowy mountain edge', 18: 'Tundra', 23: 'Tundra mountain edge',
    24: 'Balamb mountain edge', 25: 'Esthar border terrain', 27: 'Railway',
    28: 'Road / town', 29: 'Inaccessible terrain', 31: 'Lake',
    32: 'Coastal water', 33: 'Offshore water', 34: 'Sea',
}
REGION_NAMES = {
    0: 'Balamb', 1: 'Dollet', 2: 'Timber', 3: 'Galbadia Garden area',
    4: 'Deling City area', 6: 'Winhill', 7: 'Centra', 8: 'Trabia',
    9: 'Shumi Village area', 10: 'Esthar', 11: 'North Esthar',
    12: 'Esthar southern island', 13: 'South Esthar', 14: 'Cactuar Island',
    15: 'Island Closest to Hell', 17: 'Winter Island',
    18: 'Island Closest to Heaven', 19: 'Central / NW Galbadia', 255: 'Sea',
}


def section_bytes(data, index):
    if len(data) < 192 or not 0 <= index < 47:
        raise ValueError('Truncated wmset header')
    start, end = struct.unpack_from('<II', data, index * 4)
    if not 192 <= start < end <= len(data):
        raise ValueError(f'Invalid wmset section {index}')
    return bytes(data[start:end])


class WorldLandscape:
    def __init__(self, data, game_data):
        self.names = {item['id']: item['name'] for item in game_data.field_data_json['field']}
        self.regions, self.locations = b'', b''
        for index, attribute in ((1, 'regions'), (18, 'locations')):
            try:
                grid = section_bytes(data, index)
                if len(grid) >= 768:
                    setattr(self, attribute, grid[:768])
            except ValueError:
                pass
        self.textures, self.texture_error = None, ''
        try:
            self.textures = WorldTextures(data)
        except (ValueError, IndexError, struct.error) as error:
            self.texture_error = str(error)

    def location_at(self, x, y):
        if not (0 <= x < 128 and 0 <= y < 96):
            return {}
        index = int(y) // 4 * 32 + int(x) // 4
        region = self.regions[index] if self.regions else None
        location = self.locations[index] if self.locations else None
        return dict(region=region, region_name=REGION_NAMES.get(region, 'Unknown region'),
                    location=location, location_name=self.names.get(location, '') if location else '')


def _tim_entries(data):
    if len(data) < 8:
        raise ValueError('Missing texture archive')
    first = struct.unpack_from('<I', data)[0]
    if not 8 <= first <= len(data) or first % 4 or first > 1024:
        raise ValueError('Invalid texture offset table')
    offsets = []
    for pos in range(0, first, 4):
        offset = struct.unpack_from('<I', data, pos)[0]
        if not offset:
            break
        if not first <= offset < len(data) or (offsets and offset <= offsets[-1]):
            raise ValueError('Invalid texture offset')
        offsets.append(offset)
    offsets.append(len(data))
    result = []
    for start, end in zip(offsets, offsets[1:]):
        raw = data[start:end]
        if len(raw) < 32 or struct.unpack_from('<I', raw)[0] != 0x10:
            raise ValueError('Invalid TIM texture')
        flags, clut_size = struct.unpack_from('<II', raw, 4)
        if (flags & 3) not in (0, 1) or not (flags & 8):
            raise ValueError('Expected a paletted world texture')
        _, _, cw, ch = struct.unpack_from('<HHHH', raw, 12)
        if not cw or not ch or cw * ch > 65536 or clut_size != 12 + cw * ch * 2:
            raise ValueError('Invalid texture palette')
        pixel_pos = 8 + clut_size
        if pixel_pos + 12 > len(raw):
            raise ValueError('Truncated TIM palette')
        size, _, _, width, height = struct.unpack_from('<IHHHH', raw, pixel_pos)
        if not 0 < width <= 1024 or not 0 < height <= 512 or size != 12 + width * height * 2 or pixel_pos + size > len(raw):
            raise ValueError('Truncated TIM pixels')
        tim = PalettedTim.parse(raw)
        if tim is None:
            raise ValueError('Could not decode world texture')
        result.append(tim)
    return result


class WorldTextures:
    def __init__(self, data):
        self.world = _tim_entries(section_bytes(data, 37))
        self.roads = _tim_entries(section_bytes(data, 38))
        if len(self.world) < 24 or len(self.roads) < 1:
            raise ValueError('Missing terrain, sea or road textures')
        for tim in self.world[:8]:
            if tim.bpp != 0 or (tim.width, tim.height) != (256, 128) or sum(map(len, tim.clut_rows)) < 512:
                raise ValueError('Unsupported low-resolution terrain page')

    @staticmethod
    def _rgba(tim, palette=0, count=None):
        import numpy as np
        words = np.asarray([word for row in tim.clut_rows for word in row], dtype=np.uint16)
        count = count or (16 if tim.bpp == 0 else 256)
        words = words[palette * count:(palette + 1) * count]
        indices = np.frombuffer(tim.indices, dtype=np.uint8).reshape(tim.height, tim.width)
        if len(words) != count or int(indices.max()) >= count:
            raise ValueError('Invalid texture palette indices')
        rgba = np.empty((count, 4), dtype=np.uint8)
        for channel in range(3):
            rgba[:, channel] = np.rint(((words >> (channel * 5)) & 31) * (255. / 31))
        # STP is not transparency for these opaque terrain faces. Only zero is clear.
        rgba[:, 3] = np.where(words == 0, 0, 255)
        return rgba[indices]

    def images(self):
        """QImages are safe to create/render in the background worker; no QPixmaps."""
        import numpy as np
        from PyQt6.QtGui import QImage

        def image(rgba):
            rgba = np.ascontiguousarray(rgba)
            return QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.strides[0], QImage.Format.Format_RGBA8888).copy()

        land = {}
        for page in range(16):
            # Two 128x128 pages per TIM: the right half uses CLUTs 16..31.
            # wmx UVs address 256x256 texl pages, so the low-res UV scale is 1/2.
            tim = self.world[(page // 4) * 2 + ((page // 2) & 1)]
            half = page & 1
            for palette in range(16):
                rgba = self._rgba(tim, half * 16 + palette, 16)
                land[page, palette] = image(rgba[:, half * 128:(half + 1) * 128])

        def composite(tims):
            points = [(tim.image_x * (4 if tim.bpp == 0 else 2), tim.image_y) for tim in tims]
            left, top = min(x for x, y in points), min(y for x, y in points)
            width = max(x + tim.width for (x, y), tim in zip(points, tims)) - left
            height = max(y + tim.height for (x, y), tim in zip(points, tims)) - top
            if width > 2048 or height > 1024:
                raise ValueError('Invalid composite texture bounds')
            result = np.zeros((height, width, 4), dtype=np.uint8)
            for (x, y), tim in zip(points, tims):
                result[y - top:y - top + tim.height, x - left:x - left + tim.width] = self._rgba(tim)
            return image(result)

        return land, composite(self.world[16:24]), composite(self.roads)
