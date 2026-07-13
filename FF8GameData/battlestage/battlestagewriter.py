"""Serialize a battle stage back to an a0stgXXX.x file.

The parser (battlestageanalyser) decodes geometry into monsterdata structures
for viewing/editing; this module keeps a byte-faithful decomposition of the
same file so it can be rebuilt. Sections that are not edited (camera, skeleton,
animation, texture-animation block, TIM, and any untouched object) are copied
back verbatim, so an unedited load->save round-trips byte-for-byte. Edited or
imported objects are re-encoded (as textured "colour" triangles).

Coordinate/φtexture conventions match battlestageanalyser: vertices are
(x, y_vertical, z_ground) s16 at object offsets 0/2/4, and a face's texture is a
(texpage, clut) pair. get_list() reversal and the (rank -> page/clut/size)
texture layout captured at parse time make the geometry re-encodable.
"""

import struct
from typing import List, Optional

VERTEX_SCALE = 1.0 / 2048.0


def _u16(d, o):
    return int.from_bytes(d[o:o + 2], "little")


def _u32(d, o):
    return int.from_bytes(d[o:o + 4], "little")


def _align4(n):
    return (n + 3) & ~3


class _Group:
    __slots__ = ("unk", "header_gap", "skeleton", "objlist_raw", "bone_count_raw",
                 "animation", "objects_raw", "_table_end_rel", "_offs")


class BattleStageRaw:
    """Byte-faithful decomposition of one stage file, for reserialization."""

    def __init__(self):
        self.data = b""
        self.geo = 0
        self.pre = b""            # everything before the geometry section (camera etc.)
        self.count = 6
        self.groups: List[Optional[_Group]] = [None, None, None, None]
        self.texanim = b""        # end-of-groups .. tim_off
        self.tim_prefix = b""     # tim_off .. aligned tim
        self.tim = b""


def parse_raw(data: bytes, geo: int) -> BattleStageRaw:
    raw = BattleStageRaw()
    raw.data = bytes(data)
    raw.geo = geo
    raw.pre = bytes(data[:geo])
    count, g0, g1, g2, g3, end_groups, tim_off, size = struct.unpack_from("<8I", data, geo)
    raw.count = count
    group_offs = [g0, g1, g2, g3, end_groups]

    for i in range(4):
        if group_offs[i + 1] == group_offs[i]:
            continue
        gstart = geo + group_offs[i]
        gend = geo + group_offs[i + 1]
        unk, skel_off, objlist_off, anim_off = struct.unpack_from("<4I", data, gstart)
        grp = _Group()
        grp.unk = unk
        grp.header_gap = bytes(data[gstart + 16: gstart + skel_off])
        grp.skeleton = bytes(data[gstart + skel_off: gstart + objlist_off])
        grp.bone_count_raw = bytes(data[gstart + anim_off - 4: gstart + anim_off])
        grp.animation = bytes(data[gstart + anim_off: gend])

        ol = gstart + objlist_off
        nb_obj = _u32(data, ol)
        offs = list(struct.unpack_from(f"<{nb_obj}i", data, ol + 4)) if nb_obj else []
        table_end = ol + 4 + 4 * nb_obj
        # object list bytes = everything from table start to bone_count (exclusive)
        grp.objlist_raw = bytes(data[ol: gstart + anim_off - 4])
        # split into per-object raw slices (sorted by offset; keep any leading gap)
        sorted_offs = sorted(offs)
        grp.objects_raw = []
        obj_region_end = gstart + anim_off - 4
        for k, o in enumerate(offs):
            start = ol + o
            nxt = sorted_offs.index(o) + 1
            end = ol + sorted_offs[nxt] if nxt < len(sorted_offs) else obj_region_end
            grp.objects_raw.append(bytes(data[start:end]))
        grp._table_end_rel = table_end - ol           # objlist gap detection
        grp._offs = offs
        raw.groups[i] = grp

    raw.texanim = bytes(data[geo + end_groups: geo + tim_off])
    tim_ptr = _align4(geo + tim_off)
    raw.tim_prefix = bytes(data[geo + tim_off: tim_ptr])
    raw.tim = bytes(data[tim_ptr:])
    return raw


def _build_objlist(objects_raw: List[bytes], objlist_raw: bytes, offs: List[int]) -> bytes:
    """Rebuild a group's object-list block from (possibly new) object byte blobs,
    preserving the original leading gap between the offset table and the objects."""
    nb = len(objects_raw)
    table = bytearray(struct.pack("<i", nb))
    table += b"\x00" * (4 * nb)
    # leading gap: bytes in the original objlist between table end and first object
    table_end = 4 + 4 * nb
    first_obj_rel = min(offs) if offs else table_end
    gap = objlist_raw[table_end:first_obj_rel] if first_obj_rel > table_end else b""
    table += gap
    obj_offsets = []
    for blob in objects_raw:
        obj_offsets.append(len(table))
        table += blob
    struct.pack_into(f"<{nb}i", table, 4, *obj_offsets)
    return bytes(table)


# --------------------------------------------------------------- re-encoding

def _clamp_u8(v):
    return 0 if v < 0 else 255 if v > 255 else int(round(v))


def group_bone0_size(group_skeleton: bytes) -> int:
    """boneSize of a group's first (root) bone - its world offset along the
    vertical axis. Vertices collapsed onto bone 0 must have this subtracted so
    the engine's re-application of the bone matrix cancels out on reload."""
    return struct.unpack_from("<h", group_skeleton, 18)[0] if len(group_skeleton) >= 20 else 0


def encode_object(obj, tex_layout, default_color=0x00808080, y_bias=0) -> bytes:
    """Encode an (edited/imported) ObjectData into stage object bytes: all faces
    become 20-byte textured "colour" triangles. Quads are split A,B,C / A,C,D.

    tex_layout maps a face's tex_key (rank) to (texpage, clut, width, height) so
    page-local UVs and the CLUT/page ids of the source stage are restored.
    y_bias (raw file units) is subtracted from the vertical coordinate to cancel
    the target group's bone-0 offset (see group_bone0_size)."""
    out = bytearray()
    out += struct.pack("<H", len(obj.vertices_data))
    for vd in obj.vertices_data:
        out += struct.pack("<HH", vd.bone_id, len(vd.vertices))
        for v in vd.vertices:
            vx, vy, vz = v.get_list()
            fx = int(round(-vx / VERTEX_SCALE))
            fy = int(round(vy / VERTEX_SCALE)) - y_bias   # vertical, bone-0 corrected
            fz = int(round(-vz / VERTEX_SCALE))           # ground
            out += struct.pack("<hhh", _clamp_s16(fx), _clamp_s16(fy), _clamp_s16(fz))
    while len(out) % 4:
        out += b"\x00"

    tris = []
    for t in obj.triangles:
        tris.append((t.vertex_indexes, (t.vta, t.vtb, t.vtc), _tex_key(t)))
    for q in obj.quads:
        a, b, c, d = q.vertex_indexes
        tris.append(([a, b, c], (q.vta, q.vtb, q.vtc), _tex_key(q)))
        tris.append(([a, c, d], (q.vta, q.vtc, q.vtd), _tex_key(q)))

    out += struct.pack("<4H", 0, 0, len(tris), 0)   # n1,n2,n3(=colour tris),n4
    out += struct.pack("<I", 0)                     # unknown dword

    for indices, uvs, key in tris:
        page, clut, w, h = tex_layout.get(key, (0, 0, 256, 256))
        idx0, idx1, idx2 = indices[0] & 0xFFF, indices[1], indices[2]
        w0 = idx0 | (8 << 12)                        # zbias 0 -> (0+8)<<12
        uc, vc = _uv_texel(uvs[0], w, h)
        ua, va = _uv_texel(uvs[1], w, h)
        ub, vb = _uv_texel(uvs[2], w, h)
        out += struct.pack("<HHH", w0, idx1, idx2)
        out += struct.pack("<4B", uc, vc, ua, va)
        out += struct.pack("<H2BH", clut, ub, vb, page)
        out += struct.pack("<I", default_color)
    return bytes(out)


def _clamp_s16(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def _tex_key(face):
    return getattr(face, "tex_key", getattr(face, "tex_id_1", 0))


def _uv_texel(uv, w, h):
    return _clamp_u8(uv.get_u_norm() * w), _clamp_u8(uv.get_v_norm() * h)


def serialize(raw: BattleStageRaw,
              group_objects: Optional[dict] = None) -> bytes:
    """Rebuild the .x bytes. group_objects optionally maps group index ->
    list of object byte blobs to write instead of the original objects (used
    for edited geometry). Sections not overridden are copied verbatim."""
    out = bytearray(raw.pre)
    header_pos = len(out)
    out += b"\x00" * 32           # geometry header placeholder

    group_offs = []
    for i in range(4):
        group_offs.append(len(out) - header_pos)
        grp = raw.groups[i]
        if grp is None:
            continue
        gstart = len(out)
        out += b"\x00" * 16        # group header placeholder
        header_off = len(out) - gstart
        out += grp.header_gap
        skel_off = len(out) - gstart
        out += grp.skeleton
        objlist_off = len(out) - gstart
        if group_objects and i in group_objects:
            out += _build_objlist(group_objects[i], grp.objlist_raw, grp._offs)
        else:
            out += grp.objlist_raw
        out += grp.bone_count_raw
        anim_off = len(out) - gstart
        out += grp.animation
        struct.pack_into("<4I", out, gstart, grp.unk, skel_off, objlist_off, anim_off)

    end_groups = len(out) - header_pos
    out += raw.texanim
    tim_off = len(out) - header_pos
    out += raw.tim_prefix
    out += raw.tim
    section_size = len(out) - header_pos
    struct.pack_into("<8I", out, header_pos, raw.count, *group_offs,
                     end_groups, tim_off, section_size)
    return bytes(out)
