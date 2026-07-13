"""Shared, Qt-free glTF 2.0 binary (.glb) read/write core.

Both the Ifrit3D model exporter and the Alexander battle-stage exporter/importer
build on this so the low-level glTF machinery lives in one place. It has no
dependency on Qt or on any particular model representation.
"""

import json
import struct

# glTF component / target / sampler constants
COMPONENT_BYTE = 5120
COMPONENT_UNSIGNED_BYTE = 5121
COMPONENT_SHORT = 5122
COMPONENT_UNSIGNED_SHORT = 5123
COMPONENT_UNSIGNED_INT = 5125
COMPONENT_FLOAT = 5126
TARGET_ARRAY_BUFFER = 34962
TARGET_ELEMENT_ARRAY_BUFFER = 34963
FILTER_NEAREST = 9728
WRAP_REPEAT = 10497

_COMPONENT_PACK_FORMAT = {
    COMPONENT_BYTE: "b", COMPONENT_UNSIGNED_BYTE: "B", COMPONENT_SHORT: "h",
    COMPONENT_UNSIGNED_SHORT: "H", COMPONENT_UNSIGNED_INT: "I", COMPONENT_FLOAT: "f",
}
_COMPONENT_SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_NB_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class GlbBuilder:
    """Accumulates the binary buffer of a .glb and the matching
    bufferViews/accessors JSON entries."""

    def __init__(self):
        self.binary_data = bytearray()
        self.buffer_views = []
        self.accessors = []

    def add_buffer_view(self, raw_bytes, target=None):
        while len(self.binary_data) % 4:      # glTF requires 4-byte alignment
            self.binary_data.append(0)
        buffer_view = {
            "buffer": 0,
            "byteOffset": len(self.binary_data),
            "byteLength": len(raw_bytes),
        }
        if target is not None:
            buffer_view["target"] = target
        self.binary_data.extend(raw_bytes)
        self.buffer_views.append(buffer_view)
        return len(self.buffer_views) - 1

    def add_accessor(self, flat_values, component_type, accessor_type, target=None,
                     with_min_max=False):
        nb = _NB_COMPONENTS[accessor_type]
        pack = _COMPONENT_PACK_FORMAT[component_type]
        raw = struct.pack(f"<{len(flat_values)}{pack}", *flat_values)
        accessor = {
            "bufferView": self.add_buffer_view(raw, target),
            "componentType": component_type,
            "count": len(flat_values) // nb,
            "type": accessor_type,
        }
        if with_min_max:
            accessor["min"] = [min(flat_values[i::nb]) for i in range(nb)]
            accessor["max"] = [max(flat_values[i::nb]) for i in range(nb)]
        self.accessors.append(accessor)
        return len(self.accessors) - 1


def write_glb(filepath, gltf, binary_data):
    """Write a .glb file: 12-byte header + JSON chunk + binary chunk."""
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    binary_bytes = bytes(binary_data)
    binary_bytes += b"\x00" * ((4 - len(binary_bytes) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary_bytes)
    with open(filepath, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))     # "glTF", version 2
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))   # "JSON"
        f.write(json_bytes)
        f.write(struct.pack("<II", len(binary_bytes), 0x004E4942))  # "BIN\0"
        f.write(binary_bytes)


# ------------------------------------------------------------------- reading

def read_glb(path):
    """Return (gltf_json_dict, binary_chunk_bytes)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"glTF":
        raise ValueError("Not a .glb file (bad magic)")
    length = struct.unpack_from("<I", data, 8)[0]
    pos = 12
    gltf = None
    binary = b""
    while pos < length:
        clen, ctype = struct.unpack_from("<II", data, pos)
        pos += 8
        chunk = data[pos:pos + clen]
        pos += clen
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
    if gltf is None:
        raise ValueError("glb has no JSON chunk")
    return gltf, binary


def bufferview_bytes(gltf, binary, view_index):
    view = gltf["bufferViews"][view_index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def read_accessor(gltf, binary, accessor_index):
    """Return a list of tuples (one per element) for the accessor."""
    acc = gltf["accessors"][accessor_index]
    comp_size = _COMPONENT_SIZE[acc["componentType"]]
    fmt_char = _COMPONENT_PACK_FORMAT[acc["componentType"]]
    ncomp = _NB_COMPONENTS[acc["type"]]
    count = acc["count"]
    view = gltf["bufferViews"][acc["bufferView"]]
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", comp_size * ncomp)
    out = []
    for i in range(count):
        out.append(struct.unpack_from("<" + fmt_char * ncomp, binary, base + i * stride))
    return out
