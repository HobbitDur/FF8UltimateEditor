"""A MAG cinematic mesh (or morph target) to .glb and back, for editing its shape in Blender.

The file keeps its size, so only the vertex POSITIONS come back: the vertex and face counts, the
face colours and the texture coordinates stay as they are in the MAG. Blender writes the vertices
in its own order, so they are matched through the faces: the exported triangles come back in the
same order, corner for corner, as long as no face is added or removed.

Coordinates: the engine's s16 units / SCALE, Y and Z negated (glTF is Y up, the PSX Y down).
"""
import struct

from FF8GameData.gltf.glbbuilder import (COMPONENT_FLOAT, COMPONENT_UNSIGNED_INT, TARGET_ARRAY_BUFFER,
                                         TARGET_ELEMENT_ARRAY_BUFFER, GlbBuilder, read_accessor, read_glb,
                                         write_glb)

SCALE = 1000.0
SIGNS = (1.0, -1.0, -1.0)
EXTRAS_KEY = "ff8_mag_mesh"


def triangles(mesh):
    """Triangles over the mesh's vertex indices, faces in file order (quads stored 0-1-3-2)."""
    result = []
    for _prim, indices, _rgb, _texture in mesh.faces:
        if len(indices) == 3:
            result.append(tuple(indices))
        else:
            a, b, c, d = indices
            result += [(a, b, c), (b, d, c)]
    return result


def export_mesh(mesh, path, name="MAG mesh"):
    """Write `mesh` (a CineMesh) as a .glb: one primitive, triangles, or points for a morph target."""
    builder = GlbBuilder()
    flat = [value * sign / SCALE for vertex in mesh.vertices for value, sign in zip(vertex, SIGNS)]
    position = builder.add_accessor(flat, COMPONENT_FLOAT, "VEC3", TARGET_ARRAY_BUFFER, with_min_max=True)
    primitive = {"attributes": {"POSITION": position}}
    tris = triangles(mesh)
    if tris:
        primitive["indices"] = builder.add_accessor([i for tri in tris for i in tri], COMPONENT_UNSIGNED_INT,
                                                    "SCALAR", TARGET_ELEMENT_ARRAY_BUFFER)
    else:
        primitive["mode"] = 0                                   # POINTS: a morph target has no faces
    gltf = {"asset": {"version": "2.0", "generator": "FF8UltimateEditor - Fujin"}, "scene": 0,
            "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": [primitive],
                        "extras": {EXTRAS_KEY: {"vertices": len(mesh.vertices), "triangles": len(tris)}}}],
            "buffers": [{"byteLength": len(builder.binary_data)}],
            "bufferViews": builder.buffer_views, "accessors": builder.accessors}
    write_glb(path, gltf, builder.binary_data)


def _to_engine(point):
    values = [round(value * SCALE * sign) for value, sign in zip(point, SIGNS)]
    if any(not -32768 <= v <= 32767 for v in values):
        raise ValueError("a vertex is too far from the centre (beyond the 16-bit range)")
    return tuple(values)


def import_positions(mesh, path):
    """The mesh's vertices, in its own order, as positioned in the .glb at `path`."""
    gltf, binary = read_glb(path)
    primitives = [p for m in gltf.get("meshes", []) for p in m.get("primitives", []) if "POSITION" in p["attributes"]]
    if len(primitives) != 1:
        raise ValueError(f"the file holds {len(primitives)} mesh parts; keep the exported one only (one object, "
                         "one material)")
    primitive = primitives[0]
    points = [tuple(p) for p in read_accessor(gltf, binary, primitive["attributes"]["POSITION"])]
    count = len(mesh.vertices)
    ours = triangles(mesh)
    if not ours:                                               # a morph target: points in order
        if len(points) != count:
            raise ValueError(f"the morph target has {count} vertices, the file {len(points)}")
        return [_to_engine(p) for p in points]
    indices = [i[0] for i in read_accessor(gltf, binary, primitive["indices"])] if "indices" in primitive \
        else list(range(len(points)))
    theirs = [tuple(indices[k:k + 3]) for k in range(0, len(indices) - 2, 3)]
    if len(theirs) != len(ours):
        raise ValueError(f"the mesh has {len(ours)} triangles, the file {len(theirs)}: only moving vertices is "
                         "possible (the MAG keeps its size)")
    result = [None] * count
    for mine, other in zip(ours, theirs):
        for original, new in zip(mine, other):
            point = _to_engine(points[new])
            if result[original] is None:
                result[original] = point
            elif max(abs(a - b) for a, b in zip(result[original], point)) > 1:
                raise ValueError("the faces changed order or a vertex was split: keep the mesh's topology "
                                 "(move vertices only)")
    for index, point in enumerate(result):
        if point is None:
            result[index] = tuple(mesh.vertices[index])        # not used by a face: unchanged
    return result


def vertex_bytes(data, mesh_offset, positions):
    """(offset, bytes) of the mesh's vertex array holding `positions` (each vertex's 4th word kept)."""
    vertex_offset = struct.unpack_from("<I", data, mesh_offset + 0x14)[0]
    start = mesh_offset + vertex_offset
    raw = bytearray(data[start:start + 8 * len(positions)])
    for index, (x, y, z) in enumerate(positions):
        struct.pack_into("<3h", raw, 8 * index, x, y, z)
    return start, bytes(raw)
