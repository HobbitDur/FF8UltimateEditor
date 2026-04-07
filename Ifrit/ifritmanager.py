import os
import pathlib
import re
import shutil
import subprocess
from typing import List, Tuple

from PIL import Image
from PIL.ImageQt import QPixmap
from PyQt6.QtGui import QColor
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData, Matrix4x4
from IfritAI.AICompiler.AICompiler import AICompiler
from IfritAI.AICompiler.AIDecompiler import AIDecompiler
from IfritXlsx import xlsxmanager
from IfritXlsx.xlsxmanager import DatToXlsx, XlsxToDat


class MetaData:
    def __init__(self, meta_file_path: pathlib.Path = None):
        self.meta_file_path = meta_file_path
        self.meta_data_str = ""
        self.depth=8
        self.imageX=0
        self.imageY=0
        self.paletteX=0
        self.paletteY=0
        if meta_file_path:
            self.extract_data_from_str(meta_file_path.read_text(encoding="utf-8"))

    def __str__(self):
        return f"MetaData(Depth:{self.depth}, imageX:{self.imageX}, imageY:{self.imageY}, paletteX:{self.paletteX}, paletteY:{self.paletteY})"

    def __repr__(self):
        return self.__str__()

    def extract_data_from_str(self, str_data: str):
        self.meta_data_str = str_data
        values = str_data.split("\n")
        self.depth = int(values[0].split("=")[1])
        self.imageX = int(values[1].split("=")[1])
        self.imageY = int(values[2].split("=")[1])
        self.paletteX = int(values[3].split("=")[1])
        self.paletteY = int(values[4].split("=")[1])


class TextureData:
    def __init__(self, meta:MetaData=None, texture_path: pathlib.Path=None, palette_path:pathlib.Path=None):
        if meta:
            self.meta = meta
        else:
            self.meta = self._create_dummy_meta()
        if texture_path:
            self.texture_image = QPixmap(str(texture_path))
        else:
            self.texture_image = None
        if palette_path:
            self.palette_image = QPixmap(str(palette_path))
        else:
            self.palette_image = None
    @staticmethod
    def _create_dummy_meta():
        new_meta = MetaData()
        new_meta.depth = 8
        new_meta.imageX = 0
        new_meta.imageY = 0
        new_meta.paletteX = 0
        new_meta.paletteY = 0
        return new_meta
    def create_dummy_images(self):
        self.texture_image = self._create_dummy_image(width=128, height=128)
        self.palette_image = self._create_dummy_image(width=256, height=1)
    @staticmethod
    def _create_dummy_image(color=QColor(0, 255, 0), width=128, height=128):
        pix = QPixmap(width, height)
        pix.fill(color)
        return pix



class IfritManager:
    def __init__(self, game_data_folder="FF8GameData", vincent_tim_path=None):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.enemy = MonsterAnalyser(self.game_data)
        self.compiler = AICompiler(self.game_data, self.enemy.battle_script_data['battle_text'], self.enemy.info_stat_data)
        self.decompiler = AIDecompiler(self.game_data, self.enemy.battle_script_data['battle_text'], self.enemy.info_stat_data)

        self.texture_data = []
        self.temp_path = pathlib.Path(__file__).parent.resolve() / "temp_vincent_tim"

        current_script_dir = pathlib.Path(__file__).parent.resolve()
        if vincent_tim_path is None:
            self.vincent_tim_path = current_script_dir.parent / "ExternalTools" / "VincentTim" / "tim.exe"
        else:
            self.vincent_tim_path = pathlib.Path(vincent_tim_path).resolve()
        self._dat_xlsx_manager = DatToXlsx()
        self._xlsx_to_dat_manager = XlsxToDat()

    def close_xlsx_file(self):
        self._xlsx_to_dat_manager.close_file()
        self._dat_xlsx_manager.close_file()

    def create_xlsx_file(self, xlsx_file):
        self._dat_xlsx_manager.create_file(xlsx_file)

    def load_xlsx_file(self, xlsx_file):
        self._xlsx_to_dat_manager.load_file(xlsx_file)

    def init_from_file(self, file_path):
        self.enemy = MonsterAnalyser(self.game_data)
        self.enemy.load_file_data(file_path, self.game_data)
        self.enemy.analyse_loaded_data(self.game_data, self.decompiler)
        self.compiler.set_battle_text_info_stat(self.enemy.battle_script_data['battle_text'],self.enemy.info_stat_data )
        #self.decompiler.set_battle_text_info_stat(self.enemy.battle_script_data['battle_text'],self.enemy.info_stat_data )


    def save_file(self, file_path):
        self.enemy.write_data_to_file(self.game_data, file_path)

    def update_from_xlsx(self):
        #self.enemy.analyse_loaded_data(self.game_data)
        #self.ai_data = self.enemy.battle_script_data['ai_data']
        self.enemy.analyze_battle_script_section(self.game_data)


    def _get_bone_matrices(self, anim_id: int, frame_id: int) -> List[Matrix4x4]:
        """
        Returns world-space bone matrices for a given animation and frame.
        Now uses pre‑computed matrices from AnimationSection.
        """
        anim_section = self.enemy.animation_data

        # Validate animation ID
        if anim_id >= len(anim_section.animations):
            print(f"[ERROR] anim_id {anim_id} out of range (max {len(anim_section.animations) - 1})")
            return []

        anim = anim_section.animations[anim_id]

        # Validate frame ID
        if frame_id >= anim._nb_frames:
            print(f"[WARN] frame_id {frame_id} >= nb_frames {anim._nb_frames}, clamping to 0")
            frame_id = 0

        frame = anim._frames[frame_id]

        # Check if matrices exist
        if not hasattr(frame, 'bone_matrices') or frame.bone_matrices is None:
            print("[ERROR] No pre‑computed bone_matrices found in frame!")

        matrices = frame.bone_matrices
        return matrices

    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0) -> tuple:
        """
        Returns (lines_list, parents_list)
        lines_list: list of (start_pos, end_pos) or None
        parents_list: list of parent IDs for each bone
        """
        world_matrices = self._get_bone_matrices(anim_id, frame_id)
        if not world_matrices:
            return [None] * len(self.enemy.bone_data.bones), []

        bones = self.enemy.bone_data.bones
        lines = [None] * len(bones)
        parents = [bone.parent_id for bone in bones]

        for k, bone in enumerate(bones):
            if bone.parent_id == 0xFFFF:
                lines[k] = None
                continue

            if k >= len(world_matrices) or bone.parent_id >= len(world_matrices):
                continue

            parent_mat = world_matrices[bone.parent_id]
            child_mat = world_matrices[k]
            if parent_mat is None or child_mat is None:
                continue

            def to_viewer(mat: Matrix4x4):
                return (mat.M41, mat.M42, mat.M43)

            parent_pos = to_viewer(parent_mat)
            child_pos = to_viewer(child_mat)
            lines[k] = (parent_pos, child_pos)

        return lines, parents

    def get_animated_vertices(self, anim_id: int, frame_id: int, next_frame_id: int = None, step: float = 0.0) -> List[Tuple[float, float, float]]:
        """
        Get animated vertices for current frame.
        If next_frame_id is provided, interpolate between frames using step (0.0-1.0).
        """
        anim = self.enemy.animation_data.animations[anim_id]
        frame = anim._frames[frame_id]
        matrices = frame.bone_matrices  # already built!

        if next_frame_id is not None:
            next_frame = anim._frames[next_frame_id]
            next_matrices = next_frame.bone_matrices
        else:
            next_matrices = None

        # Get static vertices with bone assignments
        geometry = self.enemy.geometry_data
        all_vertices = []

        # Process each object
        for obj_idx, obj in enumerate(geometry.object_data):
            # Collect all vertices from this object with their bone IDs
            verts_with_bones = []
            for vert_data in obj.vertices_data:
                bone_id = vert_data.bone_id
                for vertex in vert_data.vertices:
                    verts_with_bones.append((vertex.get_list(), bone_id))

            # Transform each vertex
            for vert_pos, bone_id in verts_with_bones:
                # Get matrix for this bone
                mat = matrices[bone_id]

                # Apply transformation (same as C# CalculateFrame)
                transformed = self._transform_vertex(vert_pos, mat)

                if next_matrices is not None:
                    # Interpolate with next frame
                    next_mat = next_matrices[bone_id]
                    next_transformed = self._transform_vertex(vert_pos, next_mat)

                    # Linear interpolation
                    transformed = (
                        transformed[0] * (1 - step) + next_transformed[0] * step,
                        transformed[1] * (1 - step) + next_transformed[1] * step,
                        transformed[2] * (1 - step) + next_transformed[2] * step
                    )

                all_vertices.append(transformed)

        return all_vertices

    def _transform_vertex(self, vertex: Tuple[float, float, float], matrix: Matrix4x4) -> Tuple[float, float, float]:
        """
        Transform a vertex by a bone matrix.
        Matches C# CalculateFrame logic:
        rootFramePos = new Vector3(
            matrix.M11 * tuple.Item1.X + matrix.M41 + matrix.M12 * -tuple.Item1.Z + matrix.M13 * -tuple.Item1.Y,
            matrix.M21 * tuple.Item1.X + matrix.M42 + matrix.M22 * -tuple.Item1.Z + matrix.M23 * -tuple.Item1.Y,
            matrix.M31 * tuple.Item1.X + matrix.M43 + matrix.M32 * -tuple.Item1.Z + matrix.M33 * -tuple.Item1.Y)
        """
        x, y, z = vertex

        # The vertex is already in viewer space (x, y, z)
        # Apply bone transformation
        result_x = matrix.M11 * x + matrix.M12 * -y + matrix.M13 * -z + matrix.M41
        result_y = matrix.M21 * x + matrix.M22 * -y + matrix.M23 * -z + matrix.M42
        result_z = matrix.M31 * x + matrix.M32 * -y + matrix.M33 * -z + matrix.M43

        return (result_x, result_y, result_z)


    def analyze(self, file_path_to_analyze):
        if not self.vincent_tim_path.exists():
            raise FileNotFoundError(f"Critical Error: 'tim.exe' not found")

        specific_temp = self.temp_path / pathlib.Path(file_path_to_analyze).name
        specific_temp.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run([
                str(self.vincent_tim_path),
                "--export-all",
                "--analysis",
                str(file_path_to_analyze),
                str(specific_temp)
            ], check=True, capture_output=True)

            # --- CRITICAL: Use specific_temp for EVERYTHING below ---

            # 1. Count all .meta files in this specific subfolder
            meta_files = list(specific_temp.glob("*.meta"))
            # 2. Count palette files in this specific subfolder
            palette_files = list(specific_temp.glob("*palette.png"))
            # 3. Count texture files in this specific subfolder
            texture_files = [f for f in specific_temp.glob("*.png") if "palette" not in f.name.lower()]
            texture_png_count = len(texture_files)

            # --- PROCESS PALETTES ---
            for palette_path in palette_files:
                with Image.open(palette_path) as img:
                    if img.height > 1:
                        # Pass specific_temp to your helper if it needs it
                        self._cut_palette_file(img, specific_temp)
                        should_delete = True
                    else:
                        should_delete = False
                if should_delete:
                    palette_path.unlink()

            # --- PROCESS TEXTURES ---
            for texture_path in texture_files:
                match = re.search(r'(\d+)\.png$', texture_path.name)
                if not match:
                    continue

                target_index = int(match.group(1))
                with Image.open(texture_path) as img:
                    if img.width != img.height:
                        self._cut_texture_file(img, target_index, texture_path)

            # --- DUPLICATE METAS ---
            for template_meta in meta_files:
                parts = template_meta.name.split('.')
                for i in range(1, texture_png_count):
                    new_parts = parts.copy()
                    new_parts[-2] = str(i)
                    new_name = ".".join(new_parts)
                    target_path = specific_temp / new_name  # Use subfolder path

                    if not target_path.exists():
                        shutil.copy2(template_meta, target_path)

            # --- FINAL MATCHING (Sorted ensures index alignment) ---
            final_metas = sorted(list(specific_temp.glob("*.meta")))
            final_textures = sorted([f for f in specific_temp.glob("*.png") if "palette" not in f.name.lower()])
            final_palettes = sorted(list(specific_temp.glob("*palette.png")))
            if len(final_metas) == len(final_textures) == len(final_palettes):
                for i in range(len(final_metas)):
                    self.texture_data.append(TextureData(
                        meta=MetaData(final_metas[i]),
                        texture_path=final_textures[i],
                        palette_path=final_palettes[i]
                    ))
            else:
                print(f"Mismatch in {specific_temp.name}: M:{len(final_metas)} T:{len(final_textures)} P:{len(final_palettes)}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        except subprocess.CalledProcessError as e:
            print(f"Error: tim.exe failed with exit code {e.returncode}")


    def _cut_texture_file(self, img: Image.Image, index: int, original_path: pathlib.Path) -> None:
        width, height = img.size

        if height > width:
            # Vertical stacking: Index 0 is top, Index 1 is below it
            square_size = width
            left = 0
            top = index * square_size
            right = width
            bottom = top + square_size
        else:
            # Horizontal stacking: Index 0 is left, Index 1 is right
            square_size = height
            left = index * square_size
            top = 0
            right = left + square_size
            bottom = height

        # Perform the crop
        # Note: If the index is out of bounds for the image size,
        # this might create an empty or error-prone crop.
        # Pillow handles it, but ensure your indices match your image dimensions!
        tile = img.crop((left, top, right, bottom))

        # Save the new square image over the original filename
        # (or a new one, but here we replace the original tall/wide one)
        tile.save(original_path)

    def _cut_palette_file(self, img: Image.Image, temp_path:pathlib.Path) -> None:
        """
        Slices a tall palette image into multiple 1px height images.
        """
        width, height = img.size

        for y in range(height):
            # Define the 1px tall box
            box = (0, y, width, y + 1)
            row = img.crop(box)

            # Save each row
            row_path =  temp_path / f"{ temp_path.stem}_row_{y}_palette.png"
            row.save(row_path)

    def _create_tim_from_texture_data(self):
        if not self.vincent_tim_path.exists():
            raise FileNotFoundError(f"Critical Error: 'tim.exe' not found at {self.vincent_tim_path}")
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # --- COUNTING LOGIC ---
        # 1. Count all .meta files
        meta_files = list(self.temp_path.glob("*.meta"))
        meta_count = len(meta_files)

        # 2. Count files ending exactly in palette.png
        palette_files = list(self.temp_path.glob("*palette.png"))
        palette_count = len(palette_files)

        # 3. Count .png files that DO NOT contain "palette" in the name
        # We filter the list of all PNGs manually for precision
        # This creates a list of Path objects that don't have "palette" in the name
        texture_files = [f for f in self.temp_path.glob("*.png") if "palette" not in f.name.lower()]
        # Now you can get the count easily
        texture_png_count = len(texture_files)

        if meta_count == palette_count == texture_png_count:
            for i in range(meta_count):
                subprocess.run([
                    str(self.vincent_tim_path),
                    "--input-format", "png",
                    "--output-format", "tim",
                    "--palette", "0",
                    "--input-path-palette",palette_files[i],
                    "--input-path-meta", meta_files[i],
                    texture_files[i],
                    str(self.temp_path)
                ], check=True, capture_output=True)

    def _inject_in_com(self):
        tim_list = list(self.temp_path.glob("*.tim"))
        self.enemy.texture_data["nb_texture"] = len(tim_list)
        self.enemy.texture_data["tim_offset"] = []
        self.enemy.texture_data["texture_data"] = []
        base_offset = 4+ len(tim_list*4)+ 4
        self.enemy.texture_data["tim_offset"].append(base_offset)
        for i in range(len(tim_list)-1):
            base_offset = base_offset  + tim_list[i].stat().st_size
            self.enemy.texture_data["tim_offset"].append(base_offset)
        if  self.enemy.texture_data["tim_offset"]:
            self.enemy.texture_data["eof_texture"] =   self.enemy.texture_data["tim_offset"][-1] + tim_list[-1].stat().st_size
        else: # Should not happen, but better safe than sorry
            self.enemy.texture_data["eof_texture"] =  self.enemy.header_data['section_pos'][11]
        for i, tim in enumerate(tim_list):
            self.enemy.texture_data["texture_data"].append({'id':i, 'data': bytearray(tim.read_bytes())})
    def inject(self):
        self._create_tim_from_texture_data()
        self._inject_in_com()

    def set_bone_length(self, bone_idx: int, length: float):
        """Modify static bone length and recompute all animation matrices."""
        bone = self.enemy.bone_data.bones[bone_idx]
        bone.size = length
        self._recompute_all_animation_matrices()

    def set_bone_static_rotation(self, bone_idx: int, rot_x_deg: float, rot_y_deg: float, rot_z_deg: float):
        """Modify static bone rotation (the base pose)."""
        bone = self.enemy.bone_data.bones[bone_idx]
        # Convert degrees to raw ints (4096 = 360°)
        bone._rotX = int(rot_x_deg * 4096 / 360)
        bone._rotY = int(rot_y_deg * 4096 / 360)
        bone._rotZ = int(rot_z_deg * 4096 / 360)
        self._recompute_all_animation_matrices()

    def set_bone_parent(self, bone_idx: int, parent_idx: int):
        """Change parent of a bone."""
        bone = self.enemy.bone_data.bones[bone_idx]
        bone.parent_id = parent_idx
        self._recompute_all_animation_matrices()

    def set_animation_frame_bone_rotation(self, anim_id: int, frame_id: int, bone_idx: int,
                                          rot_x_deg: float, rot_y_deg: float, rot_z_deg: float):
        """Modify the rotation of a bone in a specific animation frame."""
        anim = self.enemy.animation_data.animations[anim_id]
        if frame_id >= len(anim._frames):
            return
        frame = anim._frames[frame_id]

        # Update raw rotation
        frame.bone_rot_raw[bone_idx].x = int(rot_x_deg * 4096 / 360)
        frame.bone_rot_raw[bone_idx].y = int(rot_y_deg * 4096 / 360)
        frame.bone_rot_raw[bone_idx].z = int(rot_z_deg * 4096 / 360)
        frame.bone_rot_deg[bone_idx] = (rot_x_deg, rot_y_deg, rot_z_deg)

        # Recompute matrices for this frame, only updating the changed bone and its children
        self._recompute_frame_matrices(anim, frame_id, bone_idx)

    def _recompute_all_animation_matrices(self):
        """Rebuild bone matrices for every frame of every animation."""
        for anim in self.enemy.animation_data.animations:
            for frame_id in range(anim._nb_frames):
                self._recompute_frame_matrices(anim, frame_id, None)

    def _recompute_frame_matrices(self, anim, frame_id, changed_bone_idx=None):
        """
        Recompute bone matrices for a single frame.
        If changed_bone_idx is provided, only recompute that bone and its children.
        """
        frame = anim._frames[frame_id]
        bones = self.enemy.bone_data.bones
        nb_bones = len(bones)

        # Determine which bones need recomputation
        bones_to_update = []
        if changed_bone_idx is not None:
            # Start with the changed bone
            bones_to_update.append(changed_bone_idx)
            # Add all children recursively
            for i in range(changed_bone_idx + 1, nb_bones):
                if bones[i].parent_id == changed_bone_idx:
                    bones_to_update.append(i)
        else:
            # Update all bones
            bones_to_update = list(range(nb_bones))

        # Sort by index to ensure parents are processed before children
        bones_to_update.sort()

        for k in bones_to_update:
            # Build local matrix from frame rotations (already in degrees)
            deg = frame.bone_rot_deg[k]
            xRot = Matrix4x4.CreateRotationX(-deg[0])
            yRot = Matrix4x4.CreateRotationY(-deg[1])
            zRot = Matrix4x4.CreateRotationZ(-deg[2])
            local = Matrix4x4.MultiplyColumnMajor(yRot, xRot)
            local = Matrix4x4.MultiplyColumnMajor(zRot, local)

            parent_id = bones[k].parent_id
            if parent_id != 0xFFFF:
                parent_mat = frame.bone_matrices[parent_id]
                world = Matrix4x4.MultiplyRowMajor(parent_mat, local)
                # Apply parent length translation
                parent_length = bones[parent_id].size
                world.M41 = parent_mat.M13 * parent_length + parent_mat.M41
                world.M42 = parent_mat.M23 * parent_length + parent_mat.M42
                world.M43 = parent_mat.M33 * parent_length + parent_mat.M43
                frame.bone_matrices[k] = world
            else:
                local.M41 = 0.0
                local.M42 = 0.0
                local.M43 = 0.0
                frame.bone_matrices[k] = local

    def dat_to_xlsx(self, file_list, analyse_ai=False, callback_func=None):
        for monster_file in file_list:
            file_name = os.path.basename(monster_file)
            file_index = int(re.search(r'\d{3}', file_name).group())
            if file_index == 0 or file_index == 127 or file_index > 143:  # Avoid working on garbage file
                continue
            monster = MonsterAnalyser(self.game_data)
            monster.load_file_data(monster_file, self.game_data)
            monster.analyse_loaded_data(self.game_data, self.decompiler)
            if callback_func:
                callback_func(monster)
            self._dat_xlsx_manager.export_to_xlsx(monster, file_name, self.game_data, analyse_ai)

        self._dat_xlsx_manager.create_ref_data(self.game_data)
        self._dat_xlsx_manager.close_file()

    def xlsx_to_dat(self, file_list, monster_id_list:List[int]):
        for sheet in self._xlsx_to_dat_manager.workbook:
            if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE:
                monster_index = int(re.search(r'\d+', sheet.title).group())
                if monster_index not in monster_id_list:  # Only doing the monster asked
                    continue
                else:
                    current_dat_file = [text for text in file_list if int(pathlib.Path(text).name.replace('c0m','').replace('.dat', '')) == monster_index]
                    if current_dat_file:
                        current_dat_file = current_dat_file[0]
                    else:
                        print(f"Monster dat file not found for index: {monster_index}")
                        continue
                enemy = self._xlsx_to_dat_manager.import_from_xlsx(sheet, self.game_data, pathlib.Path(current_dat_file).resolve().parent, self.decompiler)
                if enemy:
                    enemy.write_data_to_file(self.game_data, current_dat_file)

    def set_enemy_info_from_xlsx(self):
        for sheet in self._xlsx_to_dat_manager.workbook:
            if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE:
                monster_index = int(re.search(r'\d+', sheet.title).group())
                if monster_index != self.enemy.id:  # Only doing the monster asked
                    continue
                else:
                    self.enemy.info_stat_data = self._xlsx_to_dat_manager.get_stat_info(sheet, self.game_data)
                    self.enemy.battle_script_data['battle_text'] = self._xlsx_to_dat_manager.get_battle_text(sheet, self.game_data)

    def get_monster_data_from_xlsx(self, load_all_data=False, load_only_first=False, load_monster_id=-1) -> dict:
        monster_list = {}
        for sheet in self._xlsx_to_dat_manager.workbook:
            if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE:

                original_file_name = self._xlsx_to_dat_manager.read_original_file(sheet)
                monster_id = int(re.search(r'\d{3}', original_file_name).group())
                if load_monster_id != -1 and load_monster_id != monster_id:
                    continue
                print(sheet.title)
                current_monster = MonsterAnalyser(self.game_data)
                self._xlsx_to_dat_manager.read_monster_name(self.game_data, sheet, current_monster)
                self._xlsx_to_dat_manager.read_stat(self.game_data, sheet, current_monster)
                self._xlsx_to_dat_manager.read_def(self.game_data, sheet, current_monster)
                if load_all_data:
                    self._xlsx_to_dat_manager.read_item(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_misc(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_ability(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_text(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_card(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_devour(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_byte_flag(self.game_data, sheet, current_monster)
                    self._xlsx_to_dat_manager.read_renzokuken(self.game_data, sheet, current_monster)
                monster_list[original_file_name] =  current_monster
                if load_only_first:
                    break
        self._xlsx_to_dat_manager.close_file()
        return monster_list


