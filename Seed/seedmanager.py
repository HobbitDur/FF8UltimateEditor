import pathlib
from typing import List, Tuple

import numpy as np
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QPixmap

from FF8GameData.mch.mchanalyser import (CharaOne, CharaOneEntry, MchFile, FieldModel,
                                         compute_frame_matrices, mch_texture_group,
                                         mch_texture_is_semi)
from FF8GameData.monsterdata import Matrix4x4, Animation


class SeedTextureData:
    """Duck-types Ifrit's TextureData: the 3D widget only reads texture_image."""

    def __init__(self, pil_image):
        self.texture_image = QPixmap.fromImage(ImageQt(pil_image.convert("RGBA")))
        self.palette_image = None


class SeedManager:
    """Field model manager for the Seed tool.

    Exposes the same surface as IfritManager (enemy, texture_data,
    get_animated_vertices, get_skeleton_lines, bone setters) so the
    Ifrit3DWidget viewer works on chara.one / .mch models unchanged.
    """

    # chara.one stores animation frame counts as uint16 (battle .dat files
    # only have one byte, hence the viewer's default limit of 255).
    max_animation_frames = 65535
    # Field animations play at 30 fps in game (battle .dat animations: 15).
    anim_native_fps = 30
    # TIM decoding provides real alpha (0x0000 transparent, 0x8000 opaque
    # black): the viewer must not key pure black to transparent.
    texture_black_is_transparent = False

    def __init__(self):
        self.enemy = FieldModel()
        self.texture_data: List[SeedTextureData] = []
        self.chara_one: CharaOne = None
        self.chara_one_path: pathlib.Path = None
        self.main_chr_folder: pathlib.Path = None
        self.current_entry_index = None  # entry of the loaded model (None: standalone mch)
        # Models already built for the open chara.one, by entry index. Kept
        # so edits (60 fps conversions, bone tweaks) survive switching models
        # and are all written together on save.
        self.models = {}

    # ------------------------------------------------------------------ loading

    def load_chara_one(self, path) -> List[CharaOneEntry]:
        self.chara_one_path = pathlib.Path(path)
        self.chara_one = CharaOne(self.chara_one_path.read_bytes())
        self.models = {}
        self.current_entry_index = None
        if self.main_chr_folder is None:
            self.main_chr_folder = self._find_main_chr_folder()
        return self.chara_one.entries

    def _find_main_chr_folder(self):
        """Guess .../field/model/main_chr from a .../field/mapdata/xx/room/chara.one path."""
        for parent in self.chara_one_path.parents:
            candidate = parent / "model" / "main_chr"
            if candidate.is_dir():
                return candidate
        return None

    def load_entry(self, index: int):
        if index in self.models:  # keep edits made on a previously viewed model
            self._set_model(self.models[index])
            self.current_entry_index = index
            return
        entry = self.chara_one.entries[index]
        if entry.is_main:
            if self.main_chr_folder is None:
                raise FileNotFoundError(
                    f"{entry.name} is a main character: its model is in main_chr "
                    f"({entry.name}.mch), please select the main_chr folder.")
            mch_path = self.main_chr_folder / f"{entry.name}.mch"
            if not mch_path.is_file():
                raise FileNotFoundError(f"{mch_path} not found")
            mch_data = mch_path.read_bytes()
            if len(mch_data) < 0x100:
                raise ValueError(f"{mch_path.name} is a stub file without model data")
            model = self.chara_one.build_main_model(entry, mch_data)
        else:
            model = self.chara_one.build_npc_model(entry)
        self._set_model(model)
        self.models[index] = model
        self.current_entry_index = index

    def modified_entry_names(self) -> List[str]:
        """Names of the viewed models whose animations differ from the file."""
        if self.chara_one is None or self.chara_one.headerless:
            return []
        return [self.chara_one.entries[index].name
                for index in self.chara_one.changed_entries(self.models)]

    def save_chara_one(self, dest_path) -> List[str]:
        """Write the chara.one back with the animations of every model
        modified in this session (60 fps conversions, bone edits...). Other
        entries are copied verbatim. Returns the modified model names."""
        if self.chara_one is None:
            raise ValueError("No chara.one loaded")
        modified = self.modified_entry_names()
        data = self.chara_one.rebuild_with_models(self.models)
        pathlib.Path(dest_path).write_bytes(data)
        return modified

    def load_mch(self, path):
        """Load a standalone d0xx.mch (only its internal rest pose is available)."""
        path = pathlib.Path(path)
        data = path.read_bytes()
        if len(data) < 0x100:
            raise ValueError(f"{path.name} is a stub file without model data")
        model = MchFile(data).build_model()
        model.name = path.stem
        self._set_model(model)
        self.current_entry_index = None

    def _set_model(self, model: FieldModel):
        self.enemy = model
        self.texture_data = self._build_texture_data(model)

    @staticmethod
    def _force_opaque(image: Image.Image) -> Image.Image:
        """STP texels decode to 50% alpha; on non-ABE faces they are opaque."""
        red, green, blue, alpha = image.split()
        alpha = alpha.point(lambda v: 255 if v > 0 else 0)
        return Image.merge('RGBA', (red, green, blue, alpha))

    def _build_texture_data(self, model: FieldModel) -> List[SeedTextureData]:
        """One texture per distinct face tex id, ordered to match the sorted
        unique ids (the viewer maps ids to this list by rank). Even ids keep
        the semi-transparent TIM, odd ids get an opaque copy — see
        mchanalyser.mch_texture_id()."""
        used_ids = set()
        for obj in model.geometry_data.object_data:
            for triangle in obj.triangles:
                used_ids.add(triangle.tex_id_1 & 0xFF)
            for quad in obj.quads:
                used_ids.add(quad.tex_id_1 & 0xFF)

        opaque_cache = {}
        texture_data = []
        for tex_id in sorted(used_ids):
            group = mch_texture_group(tex_id)
            if group >= len(model.tim_images) or model.tim_images[group] is None:
                texture_data.append(SeedTextureData(Image.new('RGBA', (2, 2), (0, 255, 0, 255))))
                continue
            image = model.tim_images[group].image
            if not mch_texture_is_semi(tex_id):
                if group not in opaque_cache:
                    opaque_cache[group] = self._force_opaque(image)
                image = opaque_cache[group]
            texture_data.append(SeedTextureData(image))
        return texture_data

    # ---------------------------------------------------- viewer support
    # Same math as IfritManager: transforms bone-local vertices with the
    # pre-computed frame matrices.

    def _get_bone_matrices(self, anim_id: int, frame_id: int) -> List[Matrix4x4]:
        anim_section = self.enemy.animation_data
        if not anim_section or not anim_section.nb_animations:
            if self.enemy.bone_data:
                return [Matrix4x4() for _ in range(len(self.enemy.bone_data.bones))]
            return []
        if anim_id >= len(anim_section.animations):
            return []
        anim = anim_section.animations[anim_id]
        if frame_id >= anim.get_nb_frame():
            frame_id = 0
        return anim.frames[frame_id].bone_matrices

    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0) -> tuple:
        world_matrices = self._get_bone_matrices(anim_id, frame_id)
        bones = self.enemy.bone_data.bones
        if not world_matrices:
            return [None] * len(bones), []
        lines = [None] * len(bones)
        parents = [bone.parent_id for bone in bones]
        for k, bone in enumerate(bones):
            if bone.parent_id == 0xFFFF:
                continue
            if k >= len(world_matrices) or bone.parent_id >= len(world_matrices):
                continue
            parent_mat = world_matrices[bone.parent_id]
            child_mat = world_matrices[k]
            if parent_mat is None or child_mat is None:
                continue
            lines[k] = ((parent_mat.M41, parent_mat.M42, parent_mat.M43),
                        (child_mat.M41, child_mat.M42, child_mat.M43))
        return lines, parents

    def get_animated_vertices(self, anim_id: int, frame_id: int, next_frame_id: int = None,
                              step: float = 0.0) -> List[Tuple[float, float, float]]:
        anim = self.enemy.animation_data.animations[anim_id]
        matrices = anim.frames[frame_id].bone_matrices
        next_matrices = anim.frames[next_frame_id].bone_matrices if next_frame_id is not None else None

        all_vertices = []
        for obj in self.enemy.geometry_data.object_data:
            for vert_data in obj.vertices_data:
                bone_id = vert_data.bone_id
                mat = matrices[bone_id]
                next_mat = next_matrices[bone_id] if next_matrices is not None else None
                for vertex in vert_data.vertices:
                    transformed = self._transform_vertex(vertex.get_list(), mat)
                    if next_mat is not None:
                        next_transformed = self._transform_vertex(vertex.get_list(), next_mat)
                        transformed = (
                            transformed[0] * (1 - step) + next_transformed[0] * step,
                            transformed[1] * (1 - step) + next_transformed[1] * step,
                            transformed[2] * (1 - step) + next_transformed[2] * step,
                        )
                    all_vertices.append(transformed)
        return all_vertices

    @staticmethod
    def _transform_vertex(vertex: Tuple[float, float, float], matrix: Matrix4x4) -> Tuple[float, float, float]:
        # Field matrices are plain rotation+translation (unlike the battle
        # .dat pipeline, which flips y/z here): v' = R * v + t.
        x, y, z = vertex
        return (
            matrix.M11 * x + matrix.M12 * y + matrix.M13 * z + matrix.M41,
            matrix.M21 * x + matrix.M22 * y + matrix.M23 * z + matrix.M42,
            matrix.M31 * x + matrix.M32 * y + matrix.M33 * z + matrix.M43,
        )

    # ---------------------------------------------------- bone editor support

    def set_bone_length(self, bone_idx: int, length: float):
        self.enemy.bone_data.bones[bone_idx].set_size(length)
        self._recompute_all_animation_matrices()

    def set_bone_parent(self, bone_idx: int, parent_idx: int):
        self.enemy.bone_data.bones[bone_idx].parent_id = parent_idx
        self._recompute_all_animation_matrices()

    def set_animation_frame_bone_rotation(self, anim_id: int, frame_id: int, bone_idx: int,
                                          rot_x_deg: float, rot_y_deg: float, rot_z_deg: float):
        anim: Animation = self.enemy.animation_data.animations[anim_id]
        if frame_id >= len(anim.frames):
            return
        frame = anim.frames[frame_id]
        frame.rotation_vector_data[bone_idx][0].rotate_deg(rot_x_deg)
        frame.rotation_vector_data[bone_idx][1].rotate_deg(rot_y_deg)
        frame.rotation_vector_data[bone_idx][2].rotate_deg(rot_z_deg)
        self._recompute_frame_matrices(anim, frame_id, bone_idx)

    def get_bone_rotation_gizmo(self, anim_id: int, frame_id: int, bone_id: int):
        """Geometry for the viewer's rotation gizmo: (center, axes).

        Field-model counterpart of IfritManager.get_bone_rotation_gizmo. center
        is the bone's joint position; axes are 3 model-space unit vectors, one
        per Euler channel, giving the axis a +degrees turn of that channel spins
        the bone at its current pose. They are measured by finite differences on
        the bone's world rotation (the 3x3 of bone_matrices, which is the pure
        rotation chain here since compute_frame_matrices only writes translation
        into M41-M43), so they stay correct in any pose, gimbal included."""
        anim_section = self.enemy.animation_data
        if not self.enemy.bone_data or not anim_section or not anim_section.nb_animations:
            return None
        anims = anim_section.animations
        if anim_id >= len(anims) or frame_id >= len(anims[anim_id].frames):
            return None
        frame = anims[anim_id].frames[frame_id]
        bones = self.enemy.bone_data.bones
        if bone_id >= len(bones) or bone_id >= len(frame.rotation_vector_data):
            return None
        if len(frame.rotation_vector_data[bone_id]) < 3:
            return None

        world = frame.bone_matrices[bone_id]
        center = (world.M41, world.M42, world.M43)

        def rot3x3():
            c = frame.bone_matrices[bone_id]
            return np.array([[c.M11, c.M12, c.M13],
                             [c.M21, c.M22, c.M23],
                             [c.M31, c.M32, c.M33]], dtype=np.float64)

        delta_raw = 64  # ~5.6 deg: clean finite difference, well above rounding
        m0 = rot3x3()
        axes = []
        for axis in range(3):
            rot = frame.rotation_vector_data[bone_id][axis]
            saved = int(rot.get_rotate_raw())
            rot.rotate_raw(saved + delta_raw)
            compute_frame_matrices(frame, bones)
            m1 = rot3x3()
            rot.rotate_raw(saved)
            compute_frame_matrices(frame, bones)

            rel = m1 @ m0.T
            # For a rotation R about unit axis a: R - R^T = 2 sin(angle) [a]x
            v = np.array([rel[2, 1] - rel[1, 2],
                          rel[0, 2] - rel[2, 0],
                          rel[1, 0] - rel[0, 1]])
            norm = np.linalg.norm(v)
            axes.append(tuple(v / norm) if norm > 1e-9 else (1.0, 0.0, 0.0))

        return center, axes

    def _recompute_all_animation_matrices(self):
        for anim in self.enemy.animation_data.animations:
            for frame_id in range(anim.get_nb_frame()):
                self._recompute_frame_matrices(anim, frame_id, None)

    def _recompute_frame_matrices(self, anim, frame_id, changed_bone_idx=None):
        # Field bone matrices are cheap to build; recompute the whole frame so
        # every descendant of an edited bone stays consistent.
        compute_frame_matrices(anim.frames[frame_id], self.enemy.bone_data.bones)
