"""Parser for FF8 battle stage files (a0stgXXX.x).

A battle stage has no file header: the camera and geometry section offsets are
hardcoded per stage in FF8_EN.exe. The geometry section (found here by scanning,
so the parser also works on loose/extracted files) holds up to 4 object groups,
each a mini model in the same skeleton/geometry format as the monster .dat and
field .mch files, plus one 8bpp TIM texture shared through PSX VRAM pages/CLUTs.

This module reverse-engineers that layout (traced from BS_ReadGeometry @0x500EA0,
RenderGeometry @0x5099D0, ParsePolygons @0x50FDF0 in FF8_EN.exe) and produces the
same FieldModel/monsterdata structures the Ifrit3D viewer already renders. All
retail stage bones have identity rotation, so the skeleton is a pure translation
hierarchy baked into a single static animation frame.

Texture resolution mirrors summontexture.py: each polygon carries a CLUT id
(tex_id_1) and a texture-page id (tex_id_2); one RGBA image is built per unique
(page, clut) pair from the stage TIM.
"""

import struct
from typing import List, Optional, Tuple

from PIL import Image

from FF8GameData.monsterdata import (
    BoneSection, Bone, GeometrySection, ObjectData, VerticesData, Vertex,
    GeometryTriangle, GeometryQuad, UV, AnimationSection, Animation,
    AnimationFrame, PositionType, RotationType, Matrix4x4,
)
from FF8GameData.dat.summontexture import RawTim, SummonTextureError

# Vertex scale: stage coords reach ~16000; 1/2048 matches monster/field models.
VERTEX_SCALE = 1.0 / 2048.0
PAGE_WIDTH_HW = 64          # a PSX texture page is 64 VRAM halfwords wide
PAGE_HEIGHT = 256

# Per-stage geometry section offset, hardcoded in FF8_EN.exe (extracted from the
# 163 BS_StageXXX handlers). Used when the stage id is known; loose files fall
# back to find_geometry_offset scanning.
STAGE_GEOMETRY_OFFSET = {
    0: 4064, 1: 2308, 2: 5472, 3: 1760, 4: 2224, 5: 2364, 6: 4988, 7: 3784,
    8: 4552, 9: 4524, 10: 2852, 11: 2444, 12: 4372, 13: 3228, 14: 4252, 15: 4280,
    16: 3124, 17: 2812, 18: 3180, 19: 3304, 20: 3800, 21: 3052, 22: 3160, 23: 4928,
    24: 4588, 25: 3400, 26: 3112, 27: 3148, 28: 3136, 29: 1720, 30: 4820, 31: 2812,
    32: 3060, 33: 3196, 34: 3160, 35: 2976, 36: 2980, 37: 6756, 38: 4988, 39: 3144,
    40: 5512, 41: 4408, 42: 1772, 43: 4796, 44: 5364, 45: 5496, 46: 4160, 47: 3716,
    48: 4324, 49: 3312, 50: 3052, 51: 3068, 52: 3192, 53: 2812, 54: 2968, 55: 1768,
    56: 2980, 57: 5508, 58: 4304, 59: 2968, 60: 4988, 61: 2068, 62: 3088, 63: 4228,
    64: 4584, 65: 2628, 66: 4436, 67: 4184, 68: 1836, 69: 3168, 70: 5720, 71: 5588,
    72: 6048, 73: 4276, 74: 2576, 75: 2572, 76: 2596, 77: 4224, 78: 2952, 79: 3072,
    80: 2936, 81: 3044, 82: 2008, 83: 1912, 84: 1772, 85: 2980, 86: 3024, 87: 3012,
    88: 3220, 89: 2772, 90: 2760, 91: 3728, 92: 5600, 93: 2836, 94: 4360, 95: 2612,
    96: 4328, 97: 2812, 98: 5744, 99: 7292, 100: 1740, 101: 10768, 102: 5364, 103: 6872,
    104: 5608, 105: 15440, 106: 2992, 107: 6944, 108: 4192, 109: 4152, 110: 3964, 111: 10196,
    112: 5376, 113: 4140, 114: 5704, 115: 4364, 116: 4988, 117: 4620, 118: 3440, 119: 4312,
    120: 2920, 121: 3492, 122: 3500, 123: 7344, 124: 3280, 125: 3220, 126: 7380, 127: 3188,
    128: 10576, 129: 5676, 130: 5236, 131: 4152, 132: 2920, 133: 2716, 134: 4988, 135: 4052,
    136: 2944, 137: 4336, 138: 2704, 139: 3168, 140: 2932, 141: 5704, 142: 6528, 143: 3088,
    144: 2824, 145: 2824, 146: 4056, 147: 4528, 148: 3132, 149: 3124, 150: 2872, 151: 4068,
    152: 2288, 153: 2912, 154: 3028, 155: 2924, 156: 3064, 157: 2948, 158: 2752, 159: 3008,
    160: 4984, 161: 4548, 162: 2776,
}


def _u16(d, o):
    return int.from_bytes(d[o:o + 2], 'little')


def _s16(d, o):
    return int.from_bytes(d[o:o + 2], 'little', signed=True)


def _u32(d, o):
    return int.from_bytes(d[o:o + 4], 'little')


def _align4(n):
    return (n + 3) & ~3


class StageUV(UV):
    """UV whose normalisation divides by the owning page image size (set per
    poly), so page-local 0..255 texel coords map to 0..1 for any image size."""

    def __init__(self, u: int, v: int, width: float = 256.0, height: float = 256.0):
        super().__init__()
        self._u = u
        self._v = v
        self._nw = width
        self._nh = height

    def get_u_norm(self):
        return self._u / self._nw

    def get_v_norm(self):
        return self._v / self._nh


class BattleStageModel:
    """A parsed battle stage exposed as the sections the Ifrit3D viewer reads."""

    def __init__(self):
        self.name = ""
        self.bone_data = BoneSection()
        self.geometry_data = GeometrySection()
        self.animation_data = AnimationSection()
        self.tim_images = []            # kept for parity with FieldModel
        self.textures: List[Image.Image] = []   # one per (page, clut) pair
        self.geometry_offset = 0
        self.sky_group_index = 3
        self.group_of_object: List[int] = []    # group index (0-3) of each object_data
        self.raw = None                         # BattleStageRaw, for saving
        # tex_key -> (texpage, clut, width, height); lets an edited/imported
        # mesh be re-encoded against this stage's TIM layout.
        self.tex_layout: dict = {}

    @property
    def info_stat_data(self):
        # the glTF exporter reads enemy.info_stat_data["monster_name"] for the name
        return {"monster_name": self.name or "battle_stage"}


# --------------------------------------------------------------------- scanning

def find_geometry_offset(data: bytes) -> int:
    """Locate the geometry section: header is [u32 count=6, u32 g0=32, ...]
    with a valid TIM at its tim offset. Returns the file offset."""
    limit = len(data) - 32
    o = 0
    while o < limit:
        if _u32(data, o) == 6 and _u32(data, o + 4) == 32:
            _, g0, g1, g2, g3, end_groups, tim_off, size = struct.unpack_from("<8I", data, o)
            offs = [g0, g1, g2, g3, end_groups]
            tim_at = o + ((tim_off + 3) & ~3)
            if (all(offs[i] <= offs[i + 1] for i in range(4))
                    and end_groups <= tim_off
                    and tim_at + 8 <= len(data)
                    and _u32(data, tim_at) == 0x10
                    and (_u32(data, tim_at + 4) & 0x7) in (0, 1, 2)):
                return o
        o += 4
    raise ValueError("No battle stage geometry section found in file")


# ------------------------------------------------------------------ geometry

def _parse_object(data: bytes, off: int, bone_base: int,
                  bone_of_local) -> Tuple[ObjectData, int]:
    """Parse one stage object into an ObjectData (vertices + 4 polygon lists)."""
    obj = ObjectData()
    nb_groups = _u16(data, off)
    p = off + 2
    for _ in range(nb_groups):
        local_bone = _u16(data, p)
        nb_verts = _u16(data, p + 2)
        p += 4
        vd = VerticesData()
        vd.bone_id = bone_base + local_bone
        vd.nb_vertices = nb_verts
        for _ in range(nb_verts):
            x = _s16(data, p)
            y_vert = _s16(data, p + 2)   # file's vertical axis (small extent; sky >> floor)
            z_ground = _s16(data, p + 4)  # file's ground-plane axis (large extent)
            p += 6
            v = Vertex()
            # Vertex.get_list() == (-_x, _z, -_y) * SCALE: the shared monster/mch
            # convention feeds the FILE's vertical component into the "_z" slot
            # (so it comes out unnegated as viewer Y, i.e. "up") and the ground
            # component into "_y" (so it comes out as -viewerZ). Confirmed
            # empirically: sky-dome vertices average y_vert far above floor
            # vertices (e.g. stage 0: sky 15795 vs floor 1468), while x and
            # z_ground average ~0 for the sky (it is centered horizontally).
            v._x, v._y, v._z = x, z_ground, y_vert
            vd.vertices.append(v)
        obj.vertices_data.append(vd)
    obj.nb_vertices_data = len(obj.vertices_data)

    p = _align4(p)
    n1, n2, n3, n4 = struct.unpack_from("<4H", data, p)
    p += 12  # counts (8) + unknown u32

    for _ in range(n1):
        obj.triangles.append(_read_triangle(data, p, with_color=False))
        p += 16
    for _ in range(n2):
        obj.quads.append(_read_quad(data, p, with_color=False))
        p += 20
    for _ in range(n3):
        obj.triangles.append(_read_triangle(data, p, with_color=True))
        p += 20
    for _ in range(n4):
        obj.quads.append(_read_quad(data, p, with_color=True))
        p += 24

    obj.nb_triangle = len(obj.triangles)
    obj.nb_quad = len(obj.quads)
    return obj, p


def _read_triangle(data, o, with_color):
    w0, b, c = struct.unpack_from("<HHH", data, o)
    uc, vc, ua, va = struct.unpack_from("<4B", data, o + 6)
    clut, ub, vb, texpage = struct.unpack_from("<H2BH", data, o + 10)
    t = GeometryTriangle()
    t.vertex_indexes = [w0 & 0xFFF, b, c]
    # get_triangles_with_uv pairs vta->C, vtb->A, vtc->B
    t.vta = StageUV(uc, vc)
    t.vtb = StageUV(ua, va)
    t.vtc = StageUV(ub, vb)
    t.tex_id_1 = clut
    t.tex_id_2 = texpage
    return t


def _read_quad(data, o, with_color):
    w0, b, c, d = struct.unpack_from("<4H", data, o)
    ua, va = struct.unpack_from("<2B", data, o + 8)
    clut, ub, vb, texpage = struct.unpack_from("<H2BH", data, o + 10)
    uc, vc, ud, vd = struct.unpack_from("<4B", data, o + 16)
    q = GeometryQuad()
    q.vertex_indexes = [w0 & 0xFFF, b, c, d]
    q.vta = StageUV(ua, va)
    q.vtb = StageUV(ub, vb)
    q.vtc = StageUV(uc, vc)
    q.vtd = StageUV(ud, vd)
    q.tex_id_1 = clut
    q.tex_id_2 = texpage
    return q


def _parse_group(data, gstart, gend, bone_base):
    """Return (bones, world_offsets, objects) for one group.

    bones: list[Bone] (parent ids already offset to the combined skeleton).
    world_offsets: list[(x,y,z)] raw translation of each bone (identity rots).
    """
    unk, skel_off, objlist_off, anim_off = struct.unpack_from("<4I", data, gstart)
    skel = gstart + skel_off
    nb_bones = _u16(data, skel)

    bones, offsets = [], []
    for i in range(nb_bones):
        bo = skel + 16 + 48 * i
        parent = _s16(data, bo)
        bone_size = _s16(data, bo + 2)
        b = Bone()
        b.parent_id = 0xFFFF if parent < 0 else bone_base + parent
        b.set_size_raw(bone_size)
        bones.append(b)
        base = list(offsets[parent]) if 0 <= parent < len(offsets) else [0, 0, 0]
        base[2] += bone_size   # translation runs along Z (identity rotation)
        offsets.append((base[0], base[1], base[2]))

    ol = gstart + objlist_off
    nb_obj = _u32(data, ol)
    obj_offs = struct.unpack_from(f"<{nb_obj}i", data, ol + 4) if nb_obj else ()
    bone_of_local = None
    objects = []
    for oo in obj_offs:
        obj, _ = _parse_object(data, ol + oo, bone_base, bone_of_local)
        objects.append(obj)
    return bones, offsets, objects


# ------------------------------------------------------------------- textures

def _clut_palette(clut_raw: bytes):
    pal = []
    for i in range(len(clut_raw) // 2):
        c = clut_raw[2 * i] | (clut_raw[2 * i + 1] << 8)
        pal.append(((c & 0x1F) << 3, ((c >> 5) & 0x1F) << 3, ((c >> 10) & 0x1F) << 3,
                    0 if c == 0 else 255))
    return pal


def _build_textures(tim_bytes: bytes, model: BattleStageModel):
    """Build one RGBA image per unique (texpage, clut) and rewrite each poly's
    tex_id_1 to the image rank so the viewer maps it directly."""
    try:
        tim = RawTim(tim_bytes)
    except (SummonTextureError, Exception):
        return  # untextured fallback: viewer shows flat shading

    # gather usage + per-pair max uv
    pairs = {}
    faces = []
    for obj in model.geometry_data.object_data:
        for f in list(obj.triangles) + list(obj.quads):
            faces.append(f)
            uvs = [f.vta, f.vtb, f.vtc] + ([f.vtd] if hasattr(f, 'vtd') else [])
            key = (f.tex_id_2, f.tex_id_1)
            mu, mv = pairs.get(key, (0, 0))
            for uv in uvs:
                mu = max(mu, uv._u)
                mv = max(mv, uv._v)
            pairs[key] = (mu, mv)

    ordered = sorted(pairs)
    rank = {key: i for i, key in enumerate(ordered)}
    images = []
    dims = {}
    for key in ordered:
        texpage, clut = key
        mu, mv = pairs[key]
        w, h = mu + 1, mv + 1
        page_x_hw = (texpage & 0xF) * PAGE_WIDTH_HW
        page_y = ((texpage >> 4) & 1) * PAGE_HEIGHT
        img = _decode_page(tim, page_x_hw, page_y, clut, w, h)
        images.append(img)
        dims[key] = (img.width, img.height)
        # remember how to write this texture rank back to file (page/clut/size)
        model.tex_layout[rank[key]] = (texpage, clut, img.width, img.height)

    # rewrite tex ids + fix UV normalisation to the real image size.
    # tex_key is the stable index into model.textures; tex_id_1/2 may later be
    # renumbered per visible set (see AlexanderManager) so the viewer's
    # rank-based tex_id->pixmap mapping stays an identity mapping.
    for f in faces:
        key = (f.tex_id_2, f.tex_id_1)
        w, h = dims[key]
        for uv in ([f.vta, f.vtb, f.vtc] + ([f.vtd] if hasattr(f, 'vtd') else [])):
            uv._nw, uv._nh = float(w), float(h)
        f.tex_key = rank[key]
        f.tex_id_1 = rank[key]
        f.tex_id_2 = rank[key]
    model.textures = images


def _decode_page(tim: RawTim, page_x_hw, page_y, clut, w, h) -> Image.Image:
    """RGBA image of a VRAM region, coloured with `clut`. Out-of-range reads are
    clamped and padded transparent (stages sometimes point a hair past the TIM)."""
    try:
        pal = _clut_palette(tim.clut_row(clut))
    except Exception:
        pal = [(255, 0, 255, 255)] * 256   # magenta = missing clut
    rgba = bytearray(w * h * 4)
    for y in range(h):
        try:
            row = tim.pixel_block(page_x_hw, page_y + y, w, 1)
        except Exception:
            continue  # leave transparent
        for x in range(min(w, len(row))):
            idx = row[x]
            r, g, b, a = pal[idx] if idx < len(pal) else (0, 0, 0, 0)
            o = (y * w + x) * 4
            rgba[o] = r
            rgba[o + 1] = g
            rgba[o + 2] = b
            rgba[o + 3] = a
    return Image.frombytes('RGBA', (w, h), bytes(rgba))


# --------------------------------------------------------------------- build

def build_stage_model(data: bytes, geometry_offset: Optional[int] = None,
                      stage_id: Optional[int] = None, name: str = "") -> BattleStageModel:
    if geometry_offset is None and stage_id is not None:
        geometry_offset = STAGE_GEOMETRY_OFFSET.get(stage_id)
    if geometry_offset is None:
        geometry_offset = find_geometry_offset(data)
    geo = geometry_offset
    count, g0, g1, g2, g3, end_groups, tim_off, size = struct.unpack_from("<8I", data, geo)
    group_offs = [g0, g1, g2, g3, end_groups]

    model = BattleStageModel()
    model.name = name
    model.geometry_offset = geo

    combined_bones: List[Bone] = []
    frame_offsets: List[Tuple[int, int, int]] = []
    object_data_all: List[ObjectData] = []

    for i in range(4):
        if group_offs[i + 1] == group_offs[i]:
            continue
        gstart = geo + group_offs[i]
        gend = geo + group_offs[i + 1]
        bone_base = len(combined_bones)
        bones, offsets, objects = _parse_group(data, gstart, gend, bone_base)
        combined_bones.extend(bones)
        frame_offsets.extend(offsets)
        object_data_all.extend(objects)
        model.group_of_object.extend([i] * len(objects))

    model.bone_data.bones = combined_bones
    model.bone_data.nb_bone = len(combined_bones)
    model.geometry_data.object_data = object_data_all
    model.geometry_data.nb_object = len(object_data_all)
    model.geometry_data.end = sum(sum(vd.nb_vertices for vd in o.vertices_data)
                                  for o in object_data_all)

    # one static frame carrying the translation bind pose. The viewer's bone
    # editor reads rotation_vector_data[bone][axis] even when hidden, so fill
    # identity rotations (all retail stage bones have zero rotation anyway).
    frame = AnimationFrame(len(combined_bones))
    frame.position = [PositionType(), PositionType(), PositionType()]
    frame.rotation_vector_data = [
        [RotationType(True, 0, 0), RotationType(True, 0, 0), RotationType(True, 0, 0)]
        for _ in combined_bones]
    matrices = []
    for (ox, oy, oz) in frame_offsets:
        m = Matrix4x4()   # identity
        m.M41 = -ox * VERTEX_SCALE
        m.M42 = oz * VERTEX_SCALE
        m.M43 = -oy * VERTEX_SCALE
        matrices.append(m)
    frame.bone_matrices = matrices
    anim = Animation()
    anim.frames = [frame]
    model.animation_data.animations = [anim]
    model.animation_data.nb_animations = 1

    tim_bytes = data[geo + ((tim_off + 3) & ~3):]
    _build_textures(tim_bytes, model)

    from FF8GameData.battlestage.battlestagewriter import parse_raw
    model.raw = parse_raw(data, geo)
    return model
