"""Load a .glb (glTF binary) back into the battle-stage viewer.

View-only: parses geometry + embedded textures into the same
monsterdata/BattleStageModel structures the Ifrit3D viewer renders, so a stage
exported with the "Export glTF" button (and optionally edited in Blender) can be
previewed again in Alexander. It does not write anything back to the .x file.

Only what the viewer needs is read: POSITION, TEXCOORD_0, indices and the
base-colour texture of each primitive. Skinning/animation is ignored - the glb
stores the mesh already in its posed (bind) position, which is displayed static.
"""

import io
import json
import struct
from typing import List, Optional

from PIL import Image

from FF8GameData.monsterdata import (
    BoneSection, Bone, GeometrySection, ObjectData, VerticesData,
    GeometryTriangle, AnimationSection, Animation, AnimationFrame,
    PositionType, RotationType, Matrix4x4, UV,
)
from FF8GameData.battlestage.battlestageanalyser import BattleStageModel

_COMPONENT = {
    5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
    5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4),
}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class ImportedVertex:
    """Vertex whose viewer coordinates are already known (get_list() is what the
    viewer draws). Duck-types monsterdata.Vertex for the render path."""

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


# --------------------------------------------------------------------- glb read

def _read_glb(path: str):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"glTF":
        raise ValueError("Not a .glb file (bad magic)")
    length = struct.unpack_from("<I", data, 8)[0]
    pos = 12
    json_chunk = None
    bin_chunk = b""
    while pos < length:
        clen, ctype = struct.unpack_from("<II", data, pos)
        pos += 8
        chunk = data[pos:pos + clen]
        pos += clen
        if ctype == 0x4E4F534A:      # 'JSON'
            json_chunk = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:    # 'BIN\0'
            bin_chunk = chunk
    if json_chunk is None:
        raise ValueError("glb has no JSON chunk")
    return json_chunk, bin_chunk


def _bufferview_bytes(gltf, binary, view_index):
    view = gltf["bufferViews"][view_index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def _read_accessor(gltf, binary, accessor_index):
    acc = gltf["accessors"][accessor_index]
    fmt_char, comp_size = _COMPONENT[acc["componentType"]]
    ncomp = _NCOMP[acc["type"]]
    count = acc["count"]
    view = gltf["bufferViews"][acc["bufferView"]]
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", comp_size * ncomp)
    out = []
    for i in range(count):
        off = base + i * stride
        out.append(struct.unpack_from("<" + fmt_char * ncomp, binary, off))
    return out


def _load_images(gltf, binary) -> List[Optional[Image.Image]]:
    images = []
    for img in gltf.get("images", []):
        if "bufferView" in img:
            png = _bufferview_bytes(gltf, binary, img["bufferView"])
            images.append(Image.open(io.BytesIO(png)).convert("RGBA"))
        else:
            images.append(None)  # external uri not supported
    return images


def _material_image_index(gltf, material_index) -> Optional[int]:
    if material_index is None:
        return None
    mat = gltf["materials"][material_index]
    tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if not tex:
        return None
    texture = gltf["textures"][tex["index"]]
    return texture.get("source")


# --------------------------------------------------------------- model building

def _joint_translations(gltf, binary):
    """Per-joint bind-pose world translation, from the skin's inverse-bind
    matrices (IBM = [R | -R.T] column-major; for the rigid, unrotated stage
    bones T = -IBM[12:15]). Returns None when the glb is not skinned."""
    skins = gltf.get("skins")
    if not skins or "inverseBindMatrices" not in skins[0]:
        return None
    ibms = _read_accessor(gltf, binary, skins[0]["inverseBindMatrices"])
    return [(-m[12], -m[13], -m[14]) for m in ibms]


def build_model_from_glb(path: str, flip=(1.0, -1.0, -1.0)) -> BattleStageModel:
    """Build a viewer-ready model from a .glb.

    The exporter stored world = bind * (x, -y, -z); with per-vertex bone
    translation T recovered from the skin, the exact viewer position is
    (glb.x, 2*T.y - glb.y, 2*T.z - glb.z). Un-skinned glb (e.g. some Blender
    re-exports) fall back to the plain `flip` handedness inverse."""
    gltf, binary = _read_glb(path)
    images = _load_images(gltf, binary)
    joint_t = _joint_translations(gltf, binary)

    model = BattleStageModel()
    model.name = "imported.glb"

    # one bone (identity) so the viewer's skeleton/animation paths are happy
    root = Bone()
    root.parent_id = 0xFFFF
    root.set_size_raw(0)
    model.bone_data.bones = [root]
    model.bone_data.nb_bone = 1

    fx, fy, fz = flip
    used_images = {}        # source image index -> tex_key
    model.textures = []
    object_data_all = []

    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            if "POSITION" not in attrs:
                continue
            positions = _read_accessor(gltf, binary, attrs["POSITION"])
            uvs = (_read_accessor(gltf, binary, attrs["TEXCOORD_0"])
                   if "TEXCOORD_0" in attrs else [(0.0, 0.0)] * len(positions))
            joints = (_read_accessor(gltf, binary, attrs["JOINTS_0"])
                      if joint_t is not None and "JOINTS_0" in attrs else None)
            if "indices" in prim:
                indices = [t[0] for t in _read_accessor(gltf, binary, prim["indices"])]
            else:
                indices = list(range(len(positions)))

            src = _material_image_index(gltf, prim.get("material"))
            if src is not None and src not in used_images:
                img = images[src] if src < len(images) else None
                if img is not None:
                    used_images[src] = len(model.textures)
                    model.textures.append(img)
            tex_key = used_images.get(src, 0)

            obj = ObjectData()
            vd = VerticesData()
            vd.bone_id = 0
            # glb positions are already in the viewer's world units (the exporter
            # applied VERTEX_SCALE); recover the exact viewer position per vertex.
            for vi, (x, y, z) in enumerate(positions):
                if joints is not None:
                    j = joints[vi][0]
                    tx, ty, tz = (joint_t[j] if j < len(joint_t) else (0.0, 0.0, 0.0))
                    vd.vertices.append(ImportedVertex((x, 2.0 * ty - y, 2.0 * tz - z)))
                else:
                    vd.vertices.append(ImportedVertex((x * fx, y * fy, z * fz)))
            vd.nb_vertices = len(vd.vertices)
            obj.vertices_data.append(vd)
            obj.nb_vertices_data = 1

            for i in range(0, len(indices) - 2, 3):
                a, b, c = indices[i], indices[i + 1], indices[i + 2]
                tri = GeometryTriangle()
                tri.vertex_indexes = [b, c, a]   # get_triangles_with_uv reads (C,A,B) = idx[2],[0],[1]
                tri.vta = ImportedUV(*uvs[a])
                tri.vtb = ImportedUV(*uvs[b])
                tri.vtc = ImportedUV(*uvs[c])
                tri.tex_id_1 = tex_key
                tri.tex_id_2 = tex_key
                tri.tex_key = tex_key
                obj.triangles.append(tri)
            obj.nb_triangle = len(obj.triangles)
            obj.nb_quad = 0
            object_data_all.append(obj)

    model.geometry_data.object_data = object_data_all
    model.geometry_data.nb_object = len(object_data_all)
    model.group_of_object = [0] * len(object_data_all)   # no sky group

    # single static identity frame so get_animated_vertices works
    frame = AnimationFrame(1)
    frame.position = [PositionType(), PositionType(), PositionType()]
    frame.rotation_vector_data = [[RotationType(True, 0, 0) for _ in range(3)]]
    frame.bone_matrices = [Matrix4x4()]
    anim = Animation()
    anim.frames = [frame]
    model.animation_data.animations = [anim]
    model.animation_data.nb_animations = 1
    return model
