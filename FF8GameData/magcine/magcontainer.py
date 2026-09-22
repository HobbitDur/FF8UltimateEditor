"""Resource half of a GF cinematic mag file (MAGxxx_B.00 / .01 and the packed battle/magxxx_b.0k).

Every packed file starts with the same 0x30-byte header of u32 offsets:
  0x04 script (root program, .00 only)      0x08 CLUT table (= end of the texture table)
  0x0C object table: u32 count + u32 ofs[count] relative to the table start, 0 = not in this file
  0x10 sound-effect table (.00 only)        0x14 texture table (always 0x30)
  0x18 music-stream table                   0x1C end of the tables (.01: the engine's RAM area)
  0x20 stage camera animation (unused)      0x24 voice bank (.00 only)
Resource tables are GLOBAL-index tables shared by all the GF's files: resource i has an entry only
in the file that holds it (the exe's per-GF descriptor says which file slot that is).

Objects are polymorphic - the opcode that uses an id decides what it is:
 - mesh: 0x30-byte header (flags, prim list at +0x08, vertices +0x14/+0x18, normals +0x1C/+0x20),
   8-byte vertices (s16 x, y, z, pad), a primitive list of {u16 type, u16 count} groups ending at
   count 0xFFFF; vertex fields are byte offsets into the vertex array. flags bit0 clear = vertex
   only morph target;
 - embedded battle model (the creature): 7 u32 {size, skeleton (.dat section 1), geometry
   (section 2), animation (section 3), 0, 0, size-4};
 - sprite frame list: 8-byte entries {s32 frame offset from the object table, s16 duration,
   s8 code (0 next, 1 end, 2 loop)}.
Decoded from FF8_EN.exe (GfCinematic_GetObjectPtr 0xB657E0, GF_201Ifrit_DrawMeshObject 0xB27440).
"""
import struct
from dataclasses import dataclass, field

PRIM_SIZE = [12, 16, 20, 24, 16, 20, 12, 20, 20, 28, 16, 20, 28, 32, 20, 28, 12, 24, 24, 36]
PRIM_NAME = {2: "G3 lit", 6: "F3", 7: "G3", 8: "FT3", 9: "GT3", 12: "G4 lit", 16: "F4", 17: "G4",
             18: "FT4", 19: "GT4"}
# byte offsets of the vertex fields in each primitive record
PRIM_VERTEX_FIELDS = {2: (14, 16, 18), 6: (4, 6, 8), 7: (12, 14, 16), 8: (10, 12, 14), 9: (18, 20, 22),
                      12: (20, 22, 24, 26), 16: (4, 6, 8, 10), 17: (16, 18, 20, 22),
                      18: (12, 14, 16, 18), 19: (24, 26, 28, 30)}
TEXTURED = {8, 9, 18, 19}

HEADER_FIELDS = [
    (0x04, "script (root program)"), (0x08, "CLUT table"), (0x0C, "object table"),
    (0x10, "sound-effect table"), (0x14, "texture table"), (0x18, "music-stream table"),
    (0x1C, "end of tables / RAM area"), (0x20, "stage camera animation"), (0x24, "voice bank"),
]


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


@dataclass
class CineMesh:
    flags: int
    vertices: list                                # (x, y, z)
    faces: list = field(default_factory=list)     # (prim type, [vertex indices], rgb)
    prim_counts: dict = field(default_factory=dict)
    normal_count: int = 0

    @property
    def is_morph_target(self):
        return not self.flags & 1


@dataclass
class CineObject:
    index: int
    offset: int          # absolute offset in the file
    kind: str            # mesh / model / sprite
    size: int = 0        # bytes up to the next object (or the table end)
    mesh: CineMesh = None
    info: dict = field(default_factory=dict)
    error: str = ""


class MagContainer:
    def __init__(self, data: bytes):
        self.data = bytes(data)
        self.packed = len(self.data) >= 0x30 and _u32(self.data, 0x14) == 0x30 and _u32(self.data, 0x08) > 0x30
        self.header = struct.unpack_from("<12I", self.data, 0) if len(self.data) >= 0x30 else ()
        self.objects = []
        if self.packed:
            self._read_objects()

    @property
    def texture_count(self):
        return (self.header[2] - self.header[5]) // 4

    @property
    def clut_count(self):
        return (self.header[6] - self.header[2]) // 4

    def texture_entries(self):
        """(global texture id, absolute offset) for the textures stored in this file."""
        return [(i, self.header[5] + (entry & 0xFFFFFF)) for i in range(self.texture_count)
                if (entry := _u32(self.data, self.header[5] + 4 * i))]

    def clut_entries(self):
        return [(i, self.header[2] + (entry & 0xFFFFFF)) for i in range(self.clut_count)
                if (entry := _u32(self.data, self.header[2] + 4 * i))]

    def _read_objects(self):
        table = self.header[3]
        if not table or table + 4 > len(self.data):
            return
        count = _u32(self.data, table)
        offsets = []
        for index in range(min(count, 1024)):
            relative = _u32(self.data, table + 4 + 4 * index)
            if relative:
                offsets.append((index, table + relative))
        ends = sorted({offset for _i, offset in offsets} | {len(self.data)})
        for index, offset in offsets:
            end = next(e for e in ends if e > offset)
            obj = CineObject(index, offset, self._classify(offset), end - offset)
            try:
                if obj.kind == "mesh":
                    obj.mesh = self._parse_mesh(offset)
                elif obj.kind == "model":
                    obj.info = self._parse_model(offset)
                else:
                    obj.info = self._parse_sprite_list(table, offset)
            except (struct.error, ValueError, IndexError) as error:
                obj.error = str(error)
            self.objects.append(obj)

    def _classify(self, offset):
        words = struct.unpack_from("<4I", self.data, offset)
        if words[1] == 1 and words[2] == 0x30:
            return "mesh"
        if words[1] == 0x1C and words[2] > 0x1C and words[3] > words[2]:
            return "model"
        return "sprite"

    def _parse_mesh(self, offset):
        data = self.data
        header = struct.unpack_from("<12I", data, offset)
        flags, vertex_offset, vertex_count, normal_count = header[0], header[5], header[6], header[8]
        vertices = [struct.unpack_from("<3h", data, offset + vertex_offset + 8 * i) for i in range(vertex_count)]
        mesh = CineMesh(flags, vertices, normal_count=normal_count)
        if not flags & 1:
            return mesh  # morph target: vertices only
        cursor = offset + header[2]
        for _guard in range(4096):
            prim_type, count = _u16(data, cursor), _u16(data, cursor + 2)
            if count == 0xFFFF:
                break
            if prim_type >= len(PRIM_SIZE):
                raise ValueError(f"bad primitive type {prim_type} at 0x{cursor:X}")
            cursor += 4
            size = PRIM_SIZE[prim_type]
            fields = PRIM_VERTEX_FIELDS.get(prim_type)
            mesh.prim_counts[prim_type] = mesh.prim_counts.get(prim_type, 0) + count
            for k in range(count):
                record = cursor + k * size
                if fields is None:
                    continue
                indices = [_u16(data, record + f) // 8 for f in fields]
                if any(i >= vertex_count for i in indices):
                    raise ValueError(f"vertex index out of range at 0x{record:X}")
                rgb = _u32(data, record) & 0xFFFFFF
                mesh.faces.append((prim_type, indices, rgb))
            cursor += count * size
        return mesh

    def _parse_model(self, offset):
        size, skeleton, geometry, animation = struct.unpack_from("<4I", self.data, offset)
        return {"size": size, "bones": _u16(self.data, offset + skeleton),
                "geometry objects": _u32(self.data, offset + geometry),
                "animations": _u32(self.data, offset + animation),
                "sections": (offset + skeleton, offset + geometry, offset + animation)}

    def _parse_sprite_list(self, table, offset, limit=64):
        frames = []
        for k in range(limit):
            entry = offset + 8 * k
            if entry + 8 > len(self.data):
                break
            frame, duration, code = struct.unpack_from("<ihb", self.data, entry)
            quads = None
            if code != 1 and 0 <= table + frame < len(self.data) - 4:
                quads = _u32(self.data, table + frame)
            frames.append({"frame": frame, "duration": duration, "code": code, "quads": quads})
            if code in (1, 2):
                break
        return {"frames": frames}
