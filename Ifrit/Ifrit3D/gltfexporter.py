"""
glTF 2.0 exporter for the FF8 model currently loaded in the 3D viewer (Ifrit3D).

Why glTF and not FBX?
- Blender only imports *binary* FBX, which is a proprietary and undocumented format.
  Writing it by hand is unreliable (an ASCII FBX file is simply rejected by Blender).
- glTF 2.0 is the current open standard for 3D asset exchange. Blender imports it
  natively (File > Import > glTF 2.0), and the whole model fits in a single .glb file.

What is exported (everything in one .glb file):
- The mesh, with per-face UVs, split into one primitive per FF8 texture.
- The textures (PNG extracted by VincentTim), embedded in the file.
- The skeleton, one joint per FF8 bone.
- The skinning: each FF8 vertex follows exactly one bone (weight = 1.0).
- Every animation of the .dat file, one glTF animation (a Blender "action") each.

How the FF8 data is mapped to glTF:
- The viewer already computes, for every animation frame, a world matrix per bone
  (AnimationFrame.bone_matrices). We reuse those matrices instead of re-deriving the
  FF8 rotation conventions, so the export matches the viewer exactly.
- IfritManager._transform_vertex shows how a vertex is placed in the world:
      world = M * (x, -y, -z) + (M41, M42, M43)
  so the "standard" 4x4 world matrix of a bone is:
      | M11 M12 M13 M41 |
      | M21 M22 M23 M42 |        (column-vector convention)
      | M31 M32 M33 M43 |
      |  0   0   0   1  |
  and the vertex must be swizzled to (x, -y, -z) before applying it.
- The bind pose (the rest position of the mesh in Blender) is animation 0, frame 0:
  the same pose the viewer shows when a file is loaded.
- The per-frame local transform of a joint (what glTF animates) is:
      local = inverse(parent_world) * child_world
  decomposed into a translation and a rotation quaternion.
- The whole-model translation of each frame (frame.position, applied by the viewer
  with glTranslate) is baked into the world matrices, so it ends up in the root joint.
"""

import math
import struct

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImage

# Shared, Qt-free glTF binary core (also used by the Alexander battle-stage tool).
from FF8GameData.gltf.glbbuilder import (
    GlbBuilder as _GlbBuilder, write_glb as _write_glb,
    COMPONENT_FLOAT, COMPONENT_UNSIGNED_SHORT,
    TARGET_ARRAY_BUFFER, FILTER_NEAREST, WRAP_REPEAT,
)


class GltfExporter:
    # The viewer plays the animations at 15 frames per second.
    FPS = 15.0

    def __init__(self, ifrit_manager):
        self.ifrit_manager = ifrit_manager

    def export(self, filepath: str, first_animation_id: int = None):
        """
        Export the currently loaded model to a .glb file.
        first_animation_id: animation to write first in the file. Most glTF players
        auto-play the first animation, so passing the animation currently selected
        in the viewer makes the exported file play the same thing.
        """
        enemy = self.ifrit_manager.enemy
        bones = enemy.bone_data.bones
        all_animations = enemy.animation_data.animations
        # Without animation data there is no bind pose to skin against, so weapons
        # without animation (and any file without bones) are exported as a static mesh.
        skinned = bool(bones) and any(anim.frames for anim in all_animations)

        builder = _GlbBuilder()
        gltf = {
            "asset": {"version": "2.0", "generator": "FF8UltimateEditor - Ifrit3D"},
            "scene": 0,
        }

        # --- Mesh vertices ---
        raw_positions, vertex_bone_ids = self._collect_vertices()
        if skinned:
            bind_animation = next(anim for anim in all_animations if anim.frames)
            bind_globals = self._global_bone_matrices(bind_animation.frames[0])
            # Store the mesh in its bind pose: the pose the viewer shows on load.
            world_positions = []
            for (x, y, z), bone_id in zip(raw_positions, vertex_bone_ids):
                world_positions.append(_transform_point(bind_globals[bone_id], (x, -y, -z)))
        else:
            world_positions = raw_positions

        # --- Materials, textures and mesh primitives ---
        material_of_tex_id = self._build_materials(builder, gltf)
        primitives = self._build_primitives(builder, world_positions, vertex_bone_ids,
                                            skinned, material_of_tex_id)
        gltf["meshes"] = [{"name": self.model_name(), "primitives": primitives}]

        mesh_node = {"name": self.model_name(), "mesh": 0}
        nodes = [mesh_node]
        scene_root_nodes = [0]

        # --- Skeleton, skin and animations ---
        if skinned:
            first_joint_node = len(nodes)
            bind_locals = self._local_bone_transforms(bind_globals, bones)
            for bone_id, (translation, rotation) in enumerate(bind_locals):
                nodes.append({
                    "name": f"bone_{bone_id:02d}",
                    "translation": list(translation),
                    "rotation": list(rotation),
                })
            for bone_id, bone in enumerate(bones):
                if bone.parent_id != 0xFFFF:
                    parent_node = nodes[first_joint_node + bone.parent_id]
                    parent_node.setdefault("children", []).append(first_joint_node + bone_id)
            root_joint_nodes = [first_joint_node + bone_id
                                for bone_id, bone in enumerate(bones) if bone.parent_id == 0xFFFF]
            scene_root_nodes.extend(root_joint_nodes)

            # The inverse bind matrices bring a mesh vertex back into bone space.
            ibm_flat = []
            for bone_global in bind_globals:
                inverse = _rigid_inverse(bone_global)
                # glTF matrices are stored column by column
                ibm_flat.extend(inverse[row][col] for col in range(4) for row in range(4))
            gltf["skins"] = [{
                "joints": [first_joint_node + bone_id for bone_id in range(len(bones))],
                "inverseBindMatrices": builder.add_accessor(ibm_flat, COMPONENT_FLOAT, "MAT4"),
                "skeleton": root_joint_nodes[0],
            }]
            mesh_node["skin"] = 0

            gltf["animations"] = self._build_animations(builder, bones, all_animations,
                                                        first_joint_node, first_animation_id)

        gltf["nodes"] = nodes
        gltf["scenes"] = [{"nodes": scene_root_nodes}]
        gltf["bufferViews"] = builder.buffer_views
        gltf["accessors"] = builder.accessors
        gltf["buffers"] = [{"byteLength": len(builder.binary_data)}]

        _write_glb(filepath, gltf, builder.binary_data)

    # ------------------------------------------------------------------
    # Mesh
    # ------------------------------------------------------------------

    def _collect_vertices(self):
        """
        Return (positions, bone_ids) for every vertex of the model.
        The order matches the global indices used by GeometrySection.get_triangles_with_uv()
        and get_quads_with_uv() (objects, then vertex groups, then vertices).
        """
        positions = []
        bone_ids = []
        for obj in self.ifrit_manager.enemy.geometry_data.object_data:
            for vertices_data in obj.vertices_data:
                for vertex in vertices_data.vertices:
                    positions.append(vertex.get_list())
                    bone_ids.append(vertices_data.bone_id)
        return positions, bone_ids

    def _collect_triangulated_faces(self):
        """
        Return every face of the model as a triangle: (vertex_indices, uvs, tex_id).
        Quads are split into two triangles exactly like the OpenGL viewer does
        (A,B,D then A,C,D).
        """
        geometry = self.ifrit_manager.enemy.geometry_data
        faces = list(geometry.get_triangles_with_uv())
        for (a, b, c, d), (uv_a, uv_b, uv_c, uv_d), tex_id in geometry.get_quads_with_uv():
            faces.append(((a, b, d), (uv_a, uv_b, uv_d), tex_id))
            faces.append(((a, c, d), (uv_a, uv_c, uv_d), tex_id))
        return faces

    def _build_primitives(self, builder, world_positions, vertex_bone_ids, skinned,
                          material_of_tex_id):
        """
        Build one glTF primitive per texture id.
        FF8 UVs belong to face corners (not to vertices), so vertices are not shared:
        each triangle gets its own three vertices. Simple, and Blender can always
        merge them back with "Merge by distance".
        """
        faces_by_tex_id = {}
        for face in self._collect_triangulated_faces():
            faces_by_tex_id.setdefault(face[2], []).append(face)

        primitives = []
        for tex_id, faces in sorted(faces_by_tex_id.items()):
            positions = []
            uvs = []
            joints = []
            for vertex_indices, face_uvs, _ in faces:
                for corner in range(3):
                    vertex_index = vertex_indices[corner]
                    positions.append(world_positions[vertex_index])
                    uvs.append(face_uvs[corner])
                    joints.append(vertex_bone_ids[vertex_index])

            attributes = {
                "POSITION": builder.add_accessor(
                    [coord for position in positions for coord in position],
                    COMPONENT_FLOAT, "VEC3", target=TARGET_ARRAY_BUFFER, with_min_max=True),
                "TEXCOORD_0": builder.add_accessor(
                    [coord for uv in uvs for coord in uv],
                    COMPONENT_FLOAT, "VEC2", target=TARGET_ARRAY_BUFFER),
            }
            if skinned:
                # Each vertex follows exactly one bone: joint = bone id, weight = 1.
                joints_flat = []
                weights_flat = []
                for bone_id in joints:
                    joints_flat.extend((bone_id, 0, 0, 0))
                    weights_flat.extend((1.0, 0.0, 0.0, 0.0))
                attributes["JOINTS_0"] = builder.add_accessor(
                    joints_flat, COMPONENT_UNSIGNED_SHORT, "VEC4", target=TARGET_ARRAY_BUFFER)
                attributes["WEIGHTS_0"] = builder.add_accessor(
                    weights_flat, COMPONENT_FLOAT, "VEC4", target=TARGET_ARRAY_BUFFER)

            primitives.append({
                "attributes": attributes,
                "material": material_of_tex_id[tex_id],
            })
        return primitives

    # ------------------------------------------------------------------
    # Materials and textures
    # ------------------------------------------------------------------

    def _build_materials(self, builder, gltf):
        """
        Create one material per texture id used by the faces, and embed the texture
        PNGs in the binary buffer. Returns {tex_id: material_index}.
        """
        used_tex_ids = sorted({tex_id for _, _, tex_id in self._collect_triangulated_faces()})
        pixmaps = [texture.texture_image for texture in self.ifrit_manager.texture_data
                   if texture.texture_image is not None]

        if not pixmaps:
            # No texture extracted: single flat material, same color as the viewer.
            gltf["materials"] = [{
                "name": "ff8_flat",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.45, 0.65, 0.95, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
                "doubleSided": True,
            }]
            return {tex_id: 0 for tex_id in used_tex_ids}

        # Pixel-art look: nearest filtering and repeat wrapping, like the viewer.
        gltf["samplers"] = [{
            "magFilter": FILTER_NEAREST,
            "minFilter": FILTER_NEAREST,
            "wrapS": WRAP_REPEAT,
            "wrapT": WRAP_REPEAT,
        }]
        gltf["images"] = []
        gltf["textures"] = []
        for image_index, pixmap in enumerate(pixmaps):
            png_bytes = _pixmap_to_png_bytes(pixmap)
            gltf["images"].append({
                "name": f"texture_{image_index}",
                "mimeType": "image/png",
                "bufferView": builder.add_buffer_view(png_bytes),
            })
            gltf["textures"].append({"sampler": 0, "source": image_index})

        # Map raw tex_ids to textures with the same rule as the viewer
        # (FF8OpenGLWidget.set_texture_pixmaps): sorted unique ids, clamped to
        # the number of available textures.
        gltf["materials"] = []
        material_of_tex_id = {}
        for rank, tex_id in enumerate(used_tex_ids):
            texture_index = min(rank, len(pixmaps) - 1)
            gltf["materials"].append({
                "name": f"ff8_texture_{tex_id}",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": texture_index},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
                # Cut out the transparent (originally black) texels, like the viewer
                "alphaMode": "MASK",
                "alphaCutoff": 0.5,
                "doubleSided": True,
            })
            material_of_tex_id[tex_id] = rank
        return material_of_tex_id

    # ------------------------------------------------------------------
    # Skeleton and animations
    # ------------------------------------------------------------------

    @staticmethod
    def _global_bone_matrices(frame):
        """
        Standard 4x4 world matrix of every bone for one animation frame, including
        the whole-model translation of the frame (see the module docstring).
        """
        if len(frame.position) >= 3:
            tx = frame.position[0].get_pos_world()
            ty = frame.position[1].get_pos_world()
            tz = frame.position[2].get_pos_world()
        else:
            tx = ty = tz = 0.0

        matrices = []
        for m in frame.bone_matrices:
            matrices.append([
                [m.M11, m.M12, m.M13, m.M41 + tx],
                [m.M21, m.M22, m.M23, m.M42 + ty],
                [m.M31, m.M32, m.M33, m.M43 + tz],
                [0.0, 0.0, 0.0, 1.0],
            ])
        return matrices

    @staticmethod
    def _local_bone_transforms(global_matrices, bones):
        """
        Local transform of every bone relative to its parent, as
        (translation, rotation quaternion) tuples. Root bones are relative to the scene.
        """
        local_transforms = []
        for bone_id, bone in enumerate(bones):
            bone_global = global_matrices[bone_id]
            if bone.parent_id == 0xFFFF:
                local = bone_global
            else:
                local = _mat_mul(_rigid_inverse(global_matrices[bone.parent_id]), bone_global)
            translation = (local[0][3], local[1][3], local[2][3])
            rotation = _quat_from_matrix(local)
            local_transforms.append((translation, rotation))
        return local_transforms

    def _build_animations(self, builder, bones, all_animations, first_joint_node,
                          first_animation_id=None):
        """
        One glTF animation per FF8 animation, with a keyframe on every frame for the
        translation and rotation of every joint.
        Animations are named "anim_<FF8 id>_<frame count>f" (e.g. "anim_3_45f"), and
        the one selected in the viewer is written first so that glTF players auto-play it.
        """
        anim_ids = list(range(len(all_animations)))
        if first_animation_id is not None and first_animation_id in anim_ids:
            anim_ids.remove(first_animation_id)
            anim_ids.insert(0, first_animation_id)

        gltf_animations = []
        for anim_id in anim_ids:
            anim = all_animations[anim_id]
            if not anim.frames:
                continue

            # translations[bone_id][frame] = (x, y, z) ; rotations[bone_id][frame] = (x, y, z, w)
            translations = [[] for _ in bones]
            rotations = [[] for _ in bones]
            for frame in anim.frames:
                frame_globals = self._global_bone_matrices(frame)
                frame_locals = self._local_bone_transforms(frame_globals, bones)
                for bone_id, (translation, rotation) in enumerate(frame_locals):
                    # Keep quaternions on the same hemisphere as the previous frame,
                    # otherwise the interpolation takes the "long way around".
                    if rotations[bone_id]:
                        previous = rotations[bone_id][-1]
                        if sum(p * r for p, r in zip(previous, rotation)) < 0:
                            rotation = tuple(-component for component in rotation)
                    translations[bone_id].append(translation)
                    rotations[bone_id].append(rotation)

            times = [frame_id / self.FPS for frame_id in range(len(anim.frames))]
            input_accessor = builder.add_accessor(times, COMPONENT_FLOAT, "SCALAR",
                                                  with_min_max=True)

            samplers = []
            channels = []
            for bone_id in range(len(bones)):
                samplers.append({
                    "input": input_accessor,
                    "interpolation": "LINEAR",
                    "output": builder.add_accessor(
                        [coord for translation in translations[bone_id] for coord in translation],
                        COMPONENT_FLOAT, "VEC3"),
                })
                channels.append({
                    "sampler": len(samplers) - 1,
                    "target": {"node": first_joint_node + bone_id, "path": "translation"},
                })
                samplers.append({
                    "input": input_accessor,
                    "interpolation": "LINEAR",
                    "output": builder.add_accessor(
                        [coord for rotation in rotations[bone_id] for coord in rotation],
                        COMPONENT_FLOAT, "VEC4"),
                })
                channels.append({
                    "sampler": len(samplers) - 1,
                    "target": {"node": first_joint_node + bone_id, "path": "rotation"},
                })

            gltf_animations.append({
                "name": f"anim_{anim_id}_{len(anim.frames)}f",
                "samplers": samplers,
                "channels": channels,
            })
        return gltf_animations

    def model_name(self):
        """Monster name usable as a file/object name."""
        name = str(self.ifrit_manager.enemy.info_stat_data.get("monster_name", ""))
        name = "".join(char for char in name if char.isalnum() or char in " _-").strip()
        return name or "ff8_model"


# ----------------------------------------------------------------------
# Small math helpers (plain nested lists, no dependency)
# ----------------------------------------------------------------------

def _transform_point(matrix, point):
    """Apply a 4x4 matrix (column-vector convention) to a 3D point."""
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def _mat_mul(a, b):
    """Multiply two 4x4 matrices: result = a * b."""
    return [[sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)]
            for row in range(4)]


def _rigid_inverse(matrix):
    """
    Inverse of a rotation + translation matrix: transpose the 3x3 rotation part
    and rotate the translation back. Valid because bone matrices contain no scale.
    """
    inverse = [[0.0] * 4 for _ in range(4)]
    for row in range(3):
        for col in range(3):
            inverse[row][col] = matrix[col][row]
    for row in range(3):
        inverse[row][3] = -(inverse[row][0] * matrix[0][3]
                            + inverse[row][1] * matrix[1][3]
                            + inverse[row][2] * matrix[2][3])
    inverse[3][3] = 1.0
    return inverse


def _quat_from_matrix(matrix):
    """
    Rotation quaternion (x, y, z, w) of the 3x3 part of a 4x4 matrix.
    Standard Shepperd's method: pick the most numerically stable branch.
    """
    m00, m01, m02 = matrix[0][0], matrix[0][1], matrix[0][2]
    m10, m11, m12 = matrix[1][0], matrix[1][1], matrix[1][2]
    m20, m21, m22 = matrix[2][0], matrix[2][1], matrix[2][2]

    trace = m00 + m11 + m22
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s

    length = math.sqrt(x * x + y * y + z * z + w * w)
    return (x / length, y / length, z / length, w / length)


# ----------------------------------------------------------------------
# glTF binary (.glb) writing helpers
# ----------------------------------------------------------------------
# _GlbBuilder and _write_glb now live in FF8GameData.gltf.glbbuilder (imported
# at the top of this module) so the Alexander battle-stage tool can share them.


def _pixmap_to_png_bytes(pixmap):
    """
    Encode a QPixmap as PNG bytes (in memory), making pure black pixels transparent.
    FF8 textures use black as the transparency color; the viewer does the same
    conversion before uploading to OpenGL (FF8OpenGLWidget._upload_pending_textures).
    """
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = image.bits()
    ptr.setsize(image.sizeInBytes())
    pixels = bytearray(ptr)
    for i in range(0, len(pixels), 4):
        if pixels[i] == 0 and pixels[i + 1] == 0 and pixels[i + 2] == 0:
            pixels[i + 3] = 0  # black -> fully transparent
    transparent_image = QImage(bytes(pixels), image.width(), image.height(),
                               image.bytesPerLine(), QImage.Format.Format_RGBA8888)

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    transparent_image.save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())
