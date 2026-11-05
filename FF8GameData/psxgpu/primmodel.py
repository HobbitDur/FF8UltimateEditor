"""The battle effects' prim models: small meshes in FF8_EN.exe's data (runes, columns, rings, debris...).

Every one is drawn by Effect_RenderPrimModel (0x572200, cloned into many effect modules): the caller
puts the model's address in an 88-byte render header with its tint, fade and flags, the renderer
transforms the vertices through the GTE and emits each primitive list in turn:

    +0  u32  offset of the primitive lists = 8 + 8 x vertex count
    +4  u32  vertex count
    +8  vertices: s16 x, y, z, pad (8 bytes each)
    then 8 lists, each a u32 count and its records, in this order:
      F3  12 bytes: colour (+3 the GPU code 0x20), u16 v0 v1 v2, pad
      F4  12 bytes: colour (0x28), v0 v1 v2 v3
      FT3 20 bytes: colour (0x24), v0 v1 v2, uv2, uv0 + CLUT, uv1 + texture page
      FT4 24 bytes: colour (0x2C), v0 v1 v2 v3, uv0 + CLUT, uv1 + texture page, uv2, uv3
      G3  20 bytes: colour0 (0x30), v0 v1 v2, pad, colour1, colour2
      G4  24 bytes: colour0 (0x38), v0 v1 v2 v3, colour1, colour2, colour3
      GT3 28 bytes: colour0 (0x34), v0 v1 v2, uv2, uv0 + CLUT, uv1 + texture page, colour1, colour2
      GT4 36 bytes: colour0 (0x3C), v0 v1 v2 v3, uv0 + CLUT, uv1 + texture page, uv2, uv3, colour1..3

A vertex index is the vertex's byte offset / 4 (2 per vertex: the renderer adds 4 x index to the vertex
base). The colour words are 0xCCBBGGRR with the GPU code in their top byte (+2 semi-transparent, +1 raw
texture); a CLUT / texture page word is the GPU's (the renderer adds the header's +24 to both). Each
record is kept as its words, so a model encodes back byte for byte.

No Qt here.
"""
import struct
from dataclasses import dataclass, field

IMAGE_BASE = 0x400000
MAX_VERTICES = 4096
MAX_PRIMITIVES = 4096
# name, record size, GPU code (flag bits 0-1 masked), corners, textured, gouraud
KINDS = (("F3", 12, 0x20, 3, False, False), ("F4", 12, 0x28, 4, False, False),
         ("FT3", 20, 0x24, 3, True, False), ("FT4", 24, 0x2C, 4, True, False),
         ("G3", 20, 0x30, 3, False, True), ("G4", 24, 0x38, 4, False, True),
         ("GT3", 28, 0x34, 3, True, True), ("GT4", 36, 0x3C, 4, True, True))
KIND = {k[0]: k for k in KINDS}


@dataclass
class Primitive:
    kind: str                       # F3 ... GT4
    raw: bytearray                  # its record, as in the exe

    @property
    def corners(self):
        return KIND[self.kind][3]

    @property
    def indices(self):
        """Its vertices (vertex numbers, not the stored byte offsets / 4)."""
        return [struct.unpack_from("<H", self.raw, 4 + 2 * k)[0] // 2 for k in range(self.corners)]

    def set_index(self, corner, vertex):
        struct.pack_into("<H", self.raw, 4 + 2 * corner, vertex * 2)

    def _colour_offsets(self):
        name = self.kind
        if not KIND[name][5]:
            return [0]
        tail = {"G3": 12, "G4": 12, "GT3": 20, "GT4": 24}[name]
        return [0] + [tail + 4 * k for k in range(self.corners - 1)]

    @property
    def colours(self):
        """(r, g, b) of each corner (one for a flat primitive)."""
        return [tuple(self.raw[at:at + 3]) for at in self._colour_offsets()]

    def set_colour(self, corner, rgb):
        at = self._colour_offsets()[corner]
        self.raw[at:at + 3] = bytes(rgb)

    @property
    def gpu_code(self):
        return self.raw[3]

    @property
    def semi_transparent(self):
        return bool(self.raw[3] & 2)

    def _uv_offsets(self):
        if not KIND[self.kind][4]:
            return []
        return [12, 16, 10] if self.corners == 3 else [12, 16, 20, 22]

    @property
    def uvs(self):
        """(u, v) of each corner (textured primitives)."""
        return [tuple(self.raw[at:at + 2]) for at in self._uv_offsets()]

    def set_uv(self, corner, uv):
        at = self._uv_offsets()[corner]
        self.raw[at:at + 2] = bytes(uv)

    @property
    def clut(self):
        return struct.unpack_from("<H", self.raw, 14)[0] if KIND[self.kind][4] else None

    @property
    def tpage(self):
        return struct.unpack_from("<H", self.raw, 18)[0] if KIND[self.kind][4] else None


@dataclass
class PrimModel:
    address: int                                    # in FF8_EN.exe's memory (0x400000-based)
    vertices: list = field(default_factory=list)    # [x, y, z, pad]
    primitives: list = field(default_factory=list)  # Primitive, in list order (F3 first)
    size: int = 0                                   # bytes, from the header to the last list's end

    def count(self, kind):
        return sum(p.kind == kind for p in self.primitives)


def parse_model(data, offset, address=None):
    """The PrimModel at file offset `offset` of an exe image (or a data block), or None when the bytes there are
    not one: the header's list offset 8 + 8 x vertices, every record's GPU code its list's, every index a vertex."""
    if offset < 0 or offset + 8 > len(data):
        return None
    lists_at, count = struct.unpack_from("<II", data, offset)
    if not 0 < count <= MAX_VERTICES or lists_at != 8 + 8 * count or offset + lists_at > len(data):
        return None
    model = PrimModel(address if address is not None else offset + IMAGE_BASE)
    model.vertices = [list(struct.unpack_from("<4h", data, offset + 8 + 8 * k)) for k in range(count)]
    cur = offset + lists_at
    for name, size, code, corners, _textured, _gouraud in KINDS:
        if cur + 4 > len(data):
            return None
        n = struct.unpack_from("<I", data, cur)[0]
        cur += 4
        if n > MAX_PRIMITIVES or cur + n * size > len(data):
            return None
        for _ in range(n):
            primitive = Primitive(name, bytearray(data[cur:cur + size]))
            if primitive.gpu_code & 0xFC != code:
                return None
            for k in range(corners):
                index = struct.unpack_from("<H", primitive.raw, 4 + 2 * k)[0]
                if index & 1 or index // 2 >= count:
                    return None
            model.primitives.append(primitive)
            cur += size
    model.size = cur - offset
    return model


def encode_model(model):
    """The bytes of a PrimModel (parse_model's inverse): the header, the vertices, then the 8 lists in their order
    (a primitive goes in its kind's list, whatever its place in model.primitives)."""
    count = len(model.vertices)
    out = bytearray(struct.pack("<II", 8 + 8 * count, count))
    for vertex in model.vertices:
        out += struct.pack("<4h", *vertex)
    for name, size, *_ in KINDS:
        records = [p for p in model.primitives if p.kind == name]
        out += struct.pack("<I", len(records))
        for p in records:
            if len(p.raw) != size:
                raise ValueError(f"a {name} record is {size} bytes, not {len(p.raw)}")
            out += bytes(p.raw)
    return bytes(out)


def new_primitive(kind, model):
    """A primitive of a kind on the model's first vertices, white, opaque; textured ones on the model's first textured
    primitive's CLUT and page (else 0)."""
    name, size, code, corners, textured, gouraud = KIND[kind]
    raw = bytearray(size)
    primitive = Primitive(name, raw)
    raw[0:4] = bytes((0x80, 0x80, 0x80, code))
    for at in primitive._colour_offsets()[1:]:
        raw[at:at + 3] = bytes((0x80, 0x80, 0x80))
    for k in range(corners):
        primitive.set_index(k, min(k, len(model.vertices) - 1))
    if textured:
        model_textured = next((p for p in model.primitives if KIND[p.kind][4]), None)
        if model_textured is not None:
            struct.pack_into("<H", raw, 14, model_textured.clut)
            struct.pack_into("<H", raw, 18, model_textured.tpage)
    return primitive


def bounds(model):
    """((min x, min y, min z), (max x, max y, max z)) of its vertices."""
    xs, ys, zs = zip(*((v[0], v[1], v[2]) for v in model.vertices))
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
