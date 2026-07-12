import pathlib
from typing import List, Tuple

from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QPixmap

from FF8GameData.mch.mchanalyser import CharaOne, CharaOneEntry, MchFile, FieldModel, compute_frame_matrices
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

    def __init__(self):
        self.enemy = FieldModel()
        self.texture_data: List[SeedTextureData] = []
        self.chara_one: CharaOne = None
        self.chara_one_path: pathlib.Path = None
        self.main_chr_folder: pathlib.Path = None
        self.current_entry_index = None  # entry of the loaded model (None: standalone mch)

    # ------------------------------------------------------------------ loading

    def load_chara_one(self, path) -> List[CharaOneEntry]:
        self.chara_one_path = pathlib.Path(path)
        self.chara_one = CharaOne(self.chara_one_path.read_bytes())
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
        self.current_entry_index = index

    def save_chara_one(self, dest_path):
        """Write the chara.one back with the current model's animations
        (edited frames, 60 fps conversions...). Other entries are copied
        verbatim from the original file."""
        if self.chara_one is None:
            raise ValueError("No chara.one loaded")
        if self.current_entry_index is None:
            raise ValueError("The current model was not loaded from this chara.one")
        data = self.chara_one.rebuild_with_animations(self.current_entry_index, self.enemy)
        pathlib.Path(dest_path).write_bytes(data)

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
        self.texture_data = [SeedTextureData(tim.image) for tim in model.tim_images]

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

    def _recompute_all_animation_matrices(self):
        for anim in self.enemy.animation_data.animations:
            for frame_id in range(anim.get_nb_frame()):
                self._recompute_frame_matrices(anim, frame_id, None)

    def _recompute_frame_matrices(self, anim, frame_id, changed_bone_idx=None):
        # Field bone matrices are cheap to build; recompute the whole frame so
        # every descendant of an edited bone stays consistent.
        compute_frame_matrices(anim.frames[frame_id], self.enemy.bone_data.bones)
