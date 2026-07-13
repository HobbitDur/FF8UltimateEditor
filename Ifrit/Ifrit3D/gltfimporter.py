"""glTF 2.0 importer for FF8 monster/character/weapon .dat models (Ifrit3D).

This is the inverse of :mod:`Ifrit.Ifrit3D.gltfexporter`. It reads a ``.glb``
produced by that exporter (optionally edited in Blender) and rebuilds an FF8
geometry section (section 2) so the model can be previewed in the viewer and
written back into a ``.dat`` with ``MonsterAnalyser.write_data_to_file``.

Scope and fidelity
-------------------
Only the **mesh** is reconstructed faithfully. The skeleton and the animations
are *not* rebuilt from the glb, because the export is not losslessly invertible
for them: the exporter bakes the bind pose into world-space vertex positions and
decomposes every bone/animation rotation into a float quaternion, and there is
no unique way back to FF8's raw-int rotation encoding (bone rotation vs frame-0
animation rotation are ambiguous once combined). The intended round trip is
therefore:

    load original .dat  ->  export .glb  ->  (edit mesh in Blender)  ->
    import .glb into the SAME enemy (keeps its bones/anim/all other sections)
    ->  save .dat

``import_into_enemy`` follows exactly that: it swaps *only* ``geometry_data`` and
refreshes the raw bytes of section 2, leaving every other section untouched.

What the mesh rebuild recovers vs. loses
----------------------------------------
Recovered: vertex positions (exact, via the skin's inverse-bind matrices),
per-vertex bone assignment (JOINTS_0), UVs, the low-byte texture id (from the
``ff8_texture_<id>`` material name), and face connectivity.

Lost (inherent to the glTF export): quads become triangle pairs; per-corner
vertices are merged back by (bone, position); the texture-id upper bits
(CLUT/TPage) and ``tex_id_2``; per-face depth bias; hidden/colored faces (the
exporter never writes them). A saved model therefore renders correctly in the
viewer but is not byte-identical to the original section 2.
"""

import re

from FF8GameData.monsterdata import (
    GeometrySection, ObjectData, VerticesData, Vertex, UV, GeometryTriangle,
)
from FF8GameData.gltf.glbbuilder import read_glb, read_accessor

_MATERIAL_NAME_RE = re.compile(r"ff8_texture_(\d+)")
_VERTEX_SCALE = 2048.0            # Vertex.SCALE == 1/2048
_UV_SCALE = 128.0                 # UV.get_u_norm() == (_u & 0xFF) / 128
_MAX_OBJECT_VERTICES = 0x1000     # 12-bit face indices


class GltfImportError(Exception):
    pass


class GltfImporter:
    def __init__(self):
        self.stats = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def import_into_enemy(self, glb_path: str, enemy) -> dict:
        """Rebuild the mesh of ``enemy`` from ``glb_path`` in place.

        Replaces ``enemy.geometry_data`` and the raw bytes of section 2 so a
        subsequent ``write_data_to_file`` writes the imported mesh. Everything
        else (skeleton, animations, textures, stats, AI, ...) is preserved.
        """
        original_end = enemy.geometry_data.end if enemy.geometry_data else 0
        geometry = self.import_geometry(glb_path, original_end=original_end)
        enemy.geometry_data = geometry
        # Section 2 is written from section_raw_data on save (it is not
        # re-serialized from geometry_data), so refresh it here.
        if len(enemy.section_raw_data) > 2:
            enemy.section_raw_data[2] = geometry.get_byte()
        return self.stats

    def import_geometry(self, glb_path: str, original_end: int = None) -> GeometrySection:
        """Read ``glb_path`` and return a rebuilt :class:`GeometrySection`.

        ``original_end`` is written verbatim into the section trailer (its exact
        meaning is unknown; preserving the source value keeps the file valid).
        """
        gltf, binary = read_glb(glb_path)
        ibms = self._read_inverse_bind_matrices(gltf, binary)
        corner_bone, corner_pos, corner_uv, triangles = self._collect_corners(
            gltf, binary, ibms)

        # --- Merge corners back into per-bone vertex lists ---
        # FF8 groups vertices by bone (VerticesData) inside an object; face
        # indices address the object's concatenated vertex list. We keep a
        # single object (monster meshes are well under 4096 vertices).
        bones_used = sorted({corner_bone[i] for i in range(len(corner_bone))})
        per_bone_vertices = {b: [] for b in bones_used}   # bone -> [ (rawx,rawy,rawz) ]
        per_bone_index = {b: {} for b in bones_used}      # bone -> { coord -> local rank }
        global_index = {}                                 # corner id -> object-global index

        # First pass: merge duplicate corners into a per-bone vertex list.
        for corner in range(len(corner_bone)):
            bone = corner_bone[corner]
            coord = corner_pos[corner]
            table = per_bone_index[bone]
            if coord not in table:
                table[coord] = len(per_bone_vertices[bone])
                per_bone_vertices[bone].append(coord)

        # Second pass: assign object-global indices in bone order (VerticesData
        # are emitted in that same order below, so the layout matches).
        base_for_bone = {}
        running = 0
        for bone in bones_used:
            base_for_bone[bone] = running
            running += len(per_bone_vertices[bone])
        total_vertices = running
        if total_vertices > _MAX_OBJECT_VERTICES:
            raise GltfImportError(
                f"{total_vertices} vertices exceed the {_MAX_OBJECT_VERTICES} "
                f"limit of 12-bit face indices; multi-object rebuild not supported")

        for corner in range(len(corner_bone)):
            bone = corner_bone[corner]
            local = per_bone_index[bone][corner_pos[corner]]
            global_index[corner] = base_for_bone[bone] + local

        # --- Build the single object ---
        obj = ObjectData()
        obj.nb_vertices_data = len(bones_used)
        for bone in bones_used:
            vd = VerticesData()
            vd.bone_id = bone
            for (rx, ry, rz) in per_bone_vertices[bone]:
                v = Vertex()
                v._x, v._y, v._z = rx, ry, rz
                vd.vertices.append(v)
            vd.nb_vertices = len(vd.vertices)
            obj.vertices_data.append(vd)

        for (c0, c1, c2, uv0, uv1, uv2, tex_id) in triangles:
            # Exporter emitted glb corners in (C, A, B) order (see
            # GeometrySection.get_triangles_with_uv). Rebuild so that method
            # returns the same (C, A, B) with matching UVs:
            #   vertex_indexes = [A, B, C]; vta/vtb/vtc = uv(C), uv(A), uv(B)
            tri = GeometryTriangle()
            tri.vertex_indexes = [global_index[c1], global_index[c2], global_index[c0]]
            tri.vta = self._make_uv(uv0)   # C
            tri.vtb = self._make_uv(uv1)   # A
            tri.vtc = self._make_uv(uv2)   # B
            tri.tex_id_1 = tex_id & 0xFF
            tri.tex_id_2 = 0               # visible (upper CLUT/TPage bits lost)
            obj.triangles.append(tri)
        obj.nb_triangle = len(obj.triangles)
        obj.nb_quad = obj.nb_colored_triangle = obj.nb_colored_quad = 0

        geometry = GeometrySection()
        geometry.nb_object = 1
        geometry.object_data = [obj]
        geometry.offset = [4 + 4 * geometry.nb_object]   # header: nb_object + offset table
        geometry.end = original_end if original_end is not None else total_vertices

        self.stats = {
            "vertices": total_vertices,
            "triangles": len(obj.triangles),
            "bones_used": len(bones_used),
            "textures": len({t[6] for t in triangles}),
        }
        return geometry

    # ------------------------------------------------------------------
    # glb parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _read_inverse_bind_matrices(gltf, binary):
        """Per-joint inverse bind matrix as a column-major 16-tuple, or None if
        the glb is not skinned (static mesh export)."""
        skins = gltf.get("skins")
        if not skins or "inverseBindMatrices" not in skins[0]:
            return None
        return read_accessor(gltf, binary, skins[0]["inverseBindMatrices"])

    def _collect_corners(self, gltf, binary, ibms):
        """Flatten every primitive into per-corner arrays and a triangle list.

        Returns (corner_bone, corner_pos, corner_uv, triangles) where triangles
        is a list of (c0, c1, c2, uv0, uv1, uv2, tex_id); cN are corner ids and
        uvN are (u, v) floats. corner_pos holds integer FF8 raw (x, y, z).
        """
        corner_bone = []
        corner_pos = []
        corner_uv = []
        triangles = []
        fallback_tex_for_material = {}

        for mesh in gltf.get("meshes", []):
            for prim in mesh.get("primitives", []):
                attrs = prim.get("attributes", {})
                if "POSITION" not in attrs:
                    continue
                positions = read_accessor(gltf, binary, attrs["POSITION"])
                uvs = (read_accessor(gltf, binary, attrs["TEXCOORD_0"])
                       if "TEXCOORD_0" in attrs else [(0.0, 0.0)] * len(positions))
                joints = (read_accessor(gltf, binary, attrs["JOINTS_0"])
                          if "JOINTS_0" in attrs else None)
                indices = ([t[0] for t in read_accessor(gltf, binary, prim["indices"])]
                           if "indices" in prim else list(range(len(positions))))
                tex_id = self._material_tex_id(gltf, prim.get("material"),
                                               fallback_tex_for_material)

                # Map this primitive's local corners to global corner ids.
                local_to_global = {}
                for local_vertex in set(indices):
                    px, py, pz = positions[local_vertex][:3]
                    bone = int(joints[local_vertex][0]) if joints is not None else 0
                    raw = self._world_to_raw(px, py, pz, bone, ibms)
                    corner_id = len(corner_bone)
                    corner_bone.append(bone)
                    corner_pos.append(raw)
                    corner_uv.append(tuple(uvs[local_vertex][:2]))
                    local_to_global[local_vertex] = corner_id

                for i in range(0, len(indices) - 2, 3):
                    a, b, c = indices[i], indices[i + 1], indices[i + 2]
                    ga, gb, gc = local_to_global[a], local_to_global[b], local_to_global[c]
                    triangles.append((ga, gb, gc,
                                      corner_uv[ga], corner_uv[gb], corner_uv[gc],
                                      tex_id))
        return corner_bone, corner_pos, corner_uv, triangles

    @staticmethod
    def _material_tex_id(gltf, material_index, fallback):
        """Recover the FF8 low-byte texture id from the material name written by
        the exporter (``ff8_texture_<id>``); fall back to a stable sequential id."""
        if material_index is None:
            return 0
        name = gltf.get("materials", [])[material_index].get("name", "") \
            if material_index < len(gltf.get("materials", [])) else ""
        m = _MATERIAL_NAME_RE.search(name)
        if m:
            return int(m.group(1))
        if material_index not in fallback:
            fallback[material_index] = len(fallback)
        return fallback[material_index]

    @staticmethod
    def _world_to_raw(px, py, pz, bone, ibms):
        """Invert the exporter's vertex placement to FF8 raw integer (x, y, z).

        Exporter: world = bind_global[bone] @ (x, -y, -z) with
        (x, y, z) = Vertex.get_list() = (-_x/2048, _z/2048, -_y/2048).
        So IBM[bone] @ world = (x, -y, -z), and we undo the swizzle + scale.
        For a static (unskinned) export, world already holds get_list() values.
        """
        if ibms is not None and bone < len(ibms):
            f = ibms[bone]     # column-major: element [row][col] == f[col*4 + row]
            s0 = f[0] * px + f[4] * py + f[8] * pz + f[12]
            s1 = f[1] * px + f[5] * py + f[9] * pz + f[13]
            s2 = f[2] * px + f[6] * py + f[10] * pz + f[14]
            vx, vy, vz = s0, -s1, -s2
        else:
            vx, vy, vz = px, py, pz
        raw_x = int(round(-vx * _VERTEX_SCALE))
        raw_z = int(round(vy * _VERTEX_SCALE))
        raw_y = int(round(-vz * _VERTEX_SCALE))
        return (_clamp_i16(raw_x), _clamp_i16(raw_y), _clamp_i16(raw_z))

    @staticmethod
    def _make_uv(uv_float):
        u, v = uv_float
        uv = UV()
        uv._u = int(round(u * _UV_SCALE)) & 0xFF
        uv._v = int(round(v * _UV_SCALE)) & 0xFF
        return uv


def _clamp_i16(value: int) -> int:
    return max(-32768, min(32767, value))
