"""Alexander's own battle-stage glTF (.glb) exporter.

Unlike the shared Ifrit3D model exporter (which flattens the whole model), this
keeps the stage's group structure: each of the 4 battle-stage groups becomes a
separate glTF node/mesh, named group0/group1/group2/sky_group3. The importer
(glbimport) reads those names back, so an edit->save round-trip can put geometry
back into the right group - in particular the sky must stay in group 3 for the
engine to rotate it.

Qt-free: builds on FF8GameData.gltf.glbbuilder and encodes textures from PIL
images directly, so it can run from the (Qt-free) manager.

Conventions (kept in sync with glbimport.build_model_from_glb):
- Vertices are exported in viewer world space (bind pose baked via the model's
  bone matrices) with a handedness flip FLIP; the import applies the same flip,
  which is its own inverse, so the round-trip is exact. No skinning is written.
- One primitive per (group, texture); material name "ff8tex_<tex_key>" carries
  the stable texture index so the importer can map UVs back to the right CLUT.
"""

import io
from typing import List

from FF8GameData.gltf.glbbuilder import (
    GlbBuilder, write_glb, COMPONENT_FLOAT, TARGET_ARRAY_BUFFER,
    FILTER_NEAREST, WRAP_REPEAT,
)

# glTF axis flip applied to viewer world coordinates (self-inverse per axis).
FLIP = (1.0, -1.0, -1.0)
GROUP_NODE_NAMES = ["group0", "group1", "group2", "sky_group3"]


def _png_bytes(pil_image) -> bytes:
    buf = io.BytesIO()
    pil_image.convert("RGBA").save(buf, "PNG")
    return buf.getvalue()


def _obj_world_vertices(obj, mats):
    verts = []
    for vd in obj.vertices_data:
        m = mats[vd.bone_id] if vd.bone_id < len(mats) else None
        for v in vd.vertices:
            gx, gy, gz = v.get_list()
            if m is None:
                verts.append((gx, gy, gz))
            else:
                verts.append((
                    m.M11 * gx + m.M12 * gy + m.M13 * gz + m.M41,
                    m.M21 * gx + m.M22 * gy + m.M23 * gz + m.M42,
                    m.M31 * gx + m.M32 * gy + m.M33 * gz + m.M43,
                ))
    return verts


def export_stage_glb(model, path: str):
    """Export a full BattleStageModel (all 4 groups) to a group-tagged .glb."""
    builder = GlbBuilder()
    gltf = {"asset": {"version": "2.0", "generator": "FF8UltimateEditor - Alexander"},
            "scene": 0}
    fx, fy, fz = FLIP

    mats = model.animation_data.animations[0].frames[0].bone_matrices
    group_of_object = getattr(model, "group_of_object", [0] * len(model.geometry_data.object_data))

    # --- materials / textures: one per used tex_key, name carries the tex_key ---
    used_keys = set()
    for obj in model.geometry_data.object_data:
        for f in list(obj.triangles) + list(obj.quads):
            used_keys.add(getattr(f, "tex_key", 0))
    used_keys = sorted(k for k in used_keys if k < len(model.textures))

    gltf["samplers"] = [{"magFilter": FILTER_NEAREST, "minFilter": FILTER_NEAREST,
                         "wrapS": WRAP_REPEAT, "wrapT": WRAP_REPEAT}]
    gltf["images"] = []
    gltf["textures"] = []
    gltf["materials"] = []
    material_of_key = {}
    for key in used_keys:
        img_index = len(gltf["images"])
        gltf["images"].append({
            "name": f"tex_{key}", "mimeType": "image/png",
            "bufferView": builder.add_buffer_view(_png_bytes(model.textures[key])),
        })
        gltf["textures"].append({"sampler": 0, "source": img_index})
        material_of_key[key] = len(gltf["materials"])
        gltf["materials"].append({
            "name": f"ff8tex_{key}",       # importer parses the tex_key from here
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": img_index},
                "metallicFactor": 0.0, "roughnessFactor": 1.0},
            "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": True,
        })
    if not gltf["materials"]:
        gltf["materials"].append({"name": "ff8_flat", "doubleSided": True,
                                  "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.6, 0.7, 1.0]}})

    # --- meshes: one mesh (and node) per non-empty group ---
    meshes = []
    nodes = []
    scene_nodes = []
    for gi in range(4):
        faces_by_key = {}
        for oi, obj in enumerate(model.geometry_data.object_data):
            if group_of_object[oi] != gi:
                continue
            world = _obj_world_vertices(obj, mats)
            for indices, uvs, key in _obj_triangles(obj):
                faces_by_key.setdefault(key, []).append((indices, uvs, world))
        if not faces_by_key:
            continue
        primitives = []
        for key, faces in sorted(faces_by_key.items()):
            positions = []
            uvs = []
            for indices, face_uvs, world in faces:
                for corner in range(3):
                    vx, vy, vz = world[indices[corner]]
                    positions.append((vx * fx, vy * fy, vz * fz))
                    uvs.append(face_uvs[corner])
            attributes = {
                "POSITION": builder.add_accessor(
                    [c for p in positions for c in p], COMPONENT_FLOAT, "VEC3",
                    target=TARGET_ARRAY_BUFFER, with_min_max=True),
                "TEXCOORD_0": builder.add_accessor(
                    [c for uv in uvs for c in uv], COMPONENT_FLOAT, "VEC2",
                    target=TARGET_ARRAY_BUFFER),
            }
            primitives.append({"attributes": attributes,
                               "material": material_of_key.get(key, 0)})
        mesh_index = len(meshes)
        meshes.append({"name": GROUP_NODE_NAMES[gi], "primitives": primitives})
        node_index = len(nodes)
        nodes.append({"name": GROUP_NODE_NAMES[gi], "mesh": mesh_index})
        scene_nodes.append(node_index)

    gltf["meshes"] = meshes
    gltf["nodes"] = nodes
    gltf["scenes"] = [{"nodes": scene_nodes}]
    gltf["bufferViews"] = builder.buffer_views
    gltf["accessors"] = builder.accessors
    gltf["buffers"] = [{"byteLength": len(builder.binary_data)}]
    write_glb(path, gltf, builder.binary_data)


def _obj_triangles(obj):
    """Per-object faces as triangles with object-local vertex indices, in the
    (C,A,B) corner order used by GeometrySection.get_triangles_with_uv (quads
    split A,B,C / A,C,D)."""
    out = []
    for t in obj.triangles:
        a, b, c = t.vertex_indexes[0], t.vertex_indexes[1], t.vertex_indexes[2]
        out.append(((c, a, b),
                    ((t.vta.get_u_norm(), t.vta.get_v_norm()),
                     (t.vtb.get_u_norm(), t.vtb.get_v_norm()),
                     (t.vtc.get_u_norm(), t.vtc.get_v_norm())),
                    getattr(t, "tex_key", getattr(t, "tex_id_1", 0))))
    for q in obj.quads:
        a, b, c, d = q.vertex_indexes
        ua = (q.vta.get_u_norm(), q.vta.get_v_norm())
        ub = (q.vtb.get_u_norm(), q.vtb.get_v_norm())
        uc = (q.vtc.get_u_norm(), q.vtc.get_v_norm())
        ud = (q.vtd.get_u_norm(), q.vtd.get_v_norm())
        key = getattr(q, "tex_key", getattr(q, "tex_id_1", 0))
        out.append(((a, b, c), (ua, ub, uc), key))
        out.append(((a, c, d), (ua, uc, ud), key))
    return out
