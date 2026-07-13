"""Load a .glb (glTF binary) back into the battle-stage viewer / for saving.

Parses geometry + embedded textures into the same monsterdata/BattleStageModel
structures the Ifrit3D viewer renders, so a stage exported with Alexander's
"Export .glb" (and optionally edited in Blender) can be previewed and saved.

Two glb layouts are understood:
- Alexander's own export (stageexport): one node/mesh per group, named
  group0/group1/group2/sky_group3, materials named ff8tex_<tex_key>, no
  skinning. Group membership and the stable texture index are recovered, so the
  sky (group 3) and the CLUT mapping survive an edit -> save round-trip.
- The shared Ifrit exporter's skinned glb (a single flattened mesh): handled as
  a fallback - the exact viewer position is recovered from the skin's inverse
  bind matrices, and every object is treated as group 0.
"""

import io
import re
from typing import List, Optional

from PIL import Image

from FF8GameData.monsterdata import (
    Bone, ObjectData, VerticesData, GeometryTriangle,
    AnimationSection, Animation, AnimationFrame,
    PositionType, RotationType, Matrix4x4, UV,
)
from FF8GameData.battlestage.battlestageanalyser import BattleStageModel
from FF8GameData.gltf.glbbuilder import read_glb, bufferview_bytes, read_accessor

_GROUP_NAME_RE = re.compile(r"group\s*([0-3])|sky_group\s*([0-3])", re.IGNORECASE)
_MATERIAL_KEY_RE = re.compile(r"ff8tex_(\d+)")
FLIP = (1.0, -1.0, -1.0)


class ImportedVertex:
    """Vertex whose viewer coordinates are already known (get_list() is drawn)."""
    __slots__ = ("_p",)

    def __init__(self, p):
        self._p = p

    def get_list(self):
        return self._p


class ImportedUV(UV):
    """UV already normalised to 0..1 (glTF texture coordinates)."""

    def __init__(self, u, v):
        super().__init__()
        self._uf = u
        self._vf = v

    def get_u_norm(self):
        return self._uf

    def get_v_norm(self):
        return self._vf


def _load_images(gltf, binary) -> List[Optional[Image.Image]]:
    images = []
    for img in gltf.get("images", []):
        if "bufferView" in img:
            png = bufferview_bytes(gltf, binary, img["bufferView"])
            images.append(Image.open(io.BytesIO(png)).convert("RGBA"))
        else:
            images.append(None)
    return images


def _material_info(gltf, material_index):
    """Return (image_source_index, tex_key_from_name) for a material."""
    if material_index is None:
        return None, None
    mat = gltf["materials"][material_index]
    src = None
    tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if tex:
        src = gltf["textures"][tex["index"]].get("source")
    key = None
    m = _MATERIAL_KEY_RE.search(mat.get("name", ""))
    if m:
        key = int(m.group(1))
    return src, key


def _node_group(name: str) -> int:
    m = _GROUP_NAME_RE.search(name or "")
    if m:
        return int(m.group(1) if m.group(1) is not None else m.group(2))
    return 0


def _joint_translations(gltf, binary):
    """Per-joint bind-pose world translation from the skin's inverse-bind
    matrices (T = -IBM[12:15] for the rigid, unrotated stage bones)."""
    skins = gltf.get("skins")
    if not skins or "inverseBindMatrices" not in skins[0]:
        return None
    ibms = read_accessor(gltf, binary, skins[0]["inverseBindMatrices"])
    return [(-m[12], -m[13], -m[14]) for m in ibms]


def build_model_from_glb(path: str) -> BattleStageModel:
    gltf, binary = read_glb(path)
    images = _load_images(gltf, binary)
    joint_t = _joint_translations(gltf, binary)
    fx, fy, fz = FLIP

    model = BattleStageModel()
    model.name = "imported.glb"
    root = Bone()
    root.parent_id = 0xFFFF
    root.set_size_raw(0)
    model.bone_data.bones = [root]
    model.bone_data.nb_bone = 1
    model.textures = []
    src_to_key = {}       # glb image source index -> our tex_key
    object_data_all = []
    group_of_object = []

    # mesh index -> group index, from the node that references the mesh
    mesh_group = {}
    for node in gltf.get("nodes", []):
        if "mesh" in node:
            mesh_group[node["mesh"]] = _node_group(node.get("name", ""))

    for mesh_index, mesh in enumerate(gltf.get("meshes", [])):
        group = mesh_group.get(mesh_index, 0)
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            if "POSITION" not in attrs:
                continue
            positions = read_accessor(gltf, binary, attrs["POSITION"])
            uvs = (read_accessor(gltf, binary, attrs["TEXCOORD_0"])
                   if "TEXCOORD_0" in attrs else [(0.0, 0.0)] * len(positions))
            joints = (read_accessor(gltf, binary, attrs["JOINTS_0"])
                      if joint_t is not None and "JOINTS_0" in attrs else None)
            indices = ([t[0] for t in read_accessor(gltf, binary, prim["indices"])]
                       if "indices" in prim else list(range(len(positions))))

            src, name_key = _material_info(gltf, prim.get("material"))
            # tex_key: prefer the stable index encoded in the material name
            # (Alexander export); otherwise assign sequentially by image.
            if name_key is not None:
                tex_key = name_key
                if src is not None and name_key not in {v for v in src_to_key.values()} \
                        and name_key >= len(model.textures):
                    # grow textures list so index name_key holds this image
                    while len(model.textures) <= name_key:
                        model.textures.append(None)
                    if src < len(images):
                        model.textures[name_key] = images[src]
            elif src is not None:
                if src not in src_to_key:
                    src_to_key[src] = len(model.textures)
                    model.textures.append(images[src] if src < len(images) else None)
                tex_key = src_to_key[src]
            else:
                tex_key = 0

            obj = ObjectData()
            vd = VerticesData()
            vd.bone_id = 0
            for vi, (x, y, z) in enumerate(positions):
                if joints is not None:
                    j = joints[vi][0]
                    tx, ty, tz = joint_t[j] if j < len(joint_t) else (0.0, 0.0, 0.0)
                    vd.vertices.append(ImportedVertex((x, 2.0 * ty - y, 2.0 * tz - z)))
                else:
                    vd.vertices.append(ImportedVertex((x * fx, y * fy, z * fz)))
            vd.nb_vertices = len(vd.vertices)
            obj.vertices_data.append(vd)
            obj.nb_vertices_data = 1

            for i in range(0, len(indices) - 2, 3):
                a, b, c = indices[i], indices[i + 1], indices[i + 2]
                tri = GeometryTriangle()
                tri.vertex_indexes = [b, c, a]   # get_triangles_with_uv -> (C,A,B)=idx[2,0,1]
                tri.vta = ImportedUV(*uvs[a][:2])
                tri.vtb = ImportedUV(*uvs[b][:2])
                tri.vtc = ImportedUV(*uvs[c][:2])
                tri.tex_id_1 = tri.tex_id_2 = tri.tex_key = tex_key
                obj.triangles.append(tri)
            obj.nb_triangle = len(obj.triangles)
            obj.nb_quad = 0
            object_data_all.append(obj)
            group_of_object.append(group)

    # any texture slots left None (unused index gaps) -> transparent 1x1
    model.textures = [img if img is not None else Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                      for img in model.textures]

    model.geometry_data.object_data = object_data_all
    model.geometry_data.nb_object = len(object_data_all)
    model.group_of_object = group_of_object

    frame = AnimationFrame(1)
    frame.position = [PositionType(), PositionType(), PositionType()]
    frame.rotation_vector_data = [[RotationType(True, 0, 0) for _ in range(3)]]
    frame.bone_matrices = [Matrix4x4()]
    anim = Animation()
    anim.frames = [frame]
    model.animation_data.animations = [anim]
    model.animation_data.nb_animations = 1
    return model
