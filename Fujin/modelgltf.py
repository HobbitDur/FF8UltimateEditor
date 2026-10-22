"""An effect's embedded battle model (.dat sections 1-3 inside a MAG) to .glb and back.

Export is Ifrit's (skinned mesh + every animation). The MAG keeps its size, so import only
MOVES VERTICES: the .glb's triangles are matched, corner for corner and per material, to the
triangles Ifrit's exporter wrote, and each vertex goes back to its bone's own coordinates
through the file's inverse bind matrices (Ifrit's importer maths). Faces, UVs, bones and
animations stay as they are in the MAG.
"""
import struct

from FF8GameData.gltf.glbbuilder import read_glb
from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Ifrit.Ifrit3D.gltfimporter import GltfImporter


def export_model(loader, object_id, path):
    """Write the model `object_id` of a CreatureLoader's containers as a .glb."""
    loader(object_id)                                   # parses it: the loader's IfritManager holds it
    manager = loader._ifrit_manager()
    GltfExporter(manager).export(path)
    return manager


def vertex_offsets(data, geometry_start):
    """Absolute offset of every vertex of a geometry section (objects, then bone groups, then
    vertices: the global order Ifrit's faces use). A vertex is s16 x, z, y."""
    count = struct.unpack_from("<I", data, geometry_start)[0]
    result = []
    for index in range(count):
        at = geometry_start + struct.unpack_from("<I", data, geometry_start + 4 + 4 * index)[0]
        groups = struct.unpack_from("<H", data, at)[0]
        at += 2
        for _group in range(groups):
            _bone, vertices = struct.unpack_from("<HH", data, at)
            at += 4
            result += [at + 6 * k for k in range(vertices)]
            at += 6 * vertices
    return result


def _expected_triangles(manager):
    """Ifrit's export order: per texture id (sorted), its triangles as global vertex indices."""
    groups = {}
    for indices, _uvs, tex_id in GltfExporter(manager)._collect_triangulated_faces():
        groups.setdefault(tex_id, []).append(tuple(indices))
    return groups


def import_positions(manager, path):
    """{global vertex index: (x, y, z) raw} from an edited .glb of the model `manager` holds."""
    importer = GltfImporter(getattr(manager, "vertex_axis_signs", (1.0, -1.0, -1.0)))
    gltf, binary = read_glb(path)
    ibms = importer._read_inverse_bind_matrices(gltf, binary)
    _bones, corner_pos, _uvs, triangles = importer._collect_corners(gltf, binary, ibms)
    # Ifrit writes one primitive per texture id, in id order (an untextured model: all on one
    # "flat" material); Blender keeps that triangle order when nothing is added or removed
    theirs = [(a, b, c) for a, b, c, _ua, _ub, _uc, _tex_id in triangles]
    ours = _expected_triangles(manager)
    ours = [triangle for tex_id in sorted(ours) for triangle in ours[tex_id]]
    if len(theirs) != len(ours):
        raise ValueError(f"the model has {len(ours)} triangles, the file {len(theirs)}: only moving vertices "
                         "is possible, the MAG keeps its size")
    result = {}
    for mine, other in zip(ours, theirs):
        for original, corner in zip(mine, other):
            point = corner_pos[corner]
            if original not in result:
                result[original] = point
            elif max(abs(p - q) for p, q in zip(result[original], point)) > 2:
                raise ValueError("the faces changed order or a vertex was split: keep the topology "
                                 "(move vertices only)")
    return result


def vertex_patches(data, geometry_start, positions):
    """[(offset, bytes)] writing the raw positions (x, y, z) of the vertices that moved."""
    patches = []
    for index, at in enumerate(vertex_offsets(data, geometry_start)):
        if index not in positions:
            continue
        x, y, z = positions[index]
        raw = struct.pack("<3h", x, z, y)
        if bytes(data[at:at + 6]) != raw:
            patches.append((at, raw))
    return patches
