from typing import List, Tuple

from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData, Matrix4x4
from IfritAI.AICompiler.AICompiler import AICompiler
from IfritAI.AICompiler.AIDecompiler import AIDecompiler


class IfritManager:
    def __init__(self, game_data_folder="FF8GameData"):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.enemy = MonsterAnalyser(self.game_data)
        self.compiler = AICompiler(self.game_data, self.enemy.battle_script_data['battle_text'], self.enemy.info_stat_data)
        self.decompiler = AIDecompiler(self.game_data, self.enemy.battle_script_data['battle_text'], self.enemy.info_stat_data)

    def init_from_file(self, file_path):
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
        if frame_id >= anim.nb_frames:
            print(f"[WARN] frame_id {frame_id} >= nb_frames {anim.nb_frames}, clamping to 0")
            frame_id = 0

        frame = anim.frames[frame_id]

        # Check if matrices exist
        if not hasattr(frame, 'bone_matrices') or frame.bone_matrices is None:
            print("[ERROR] No pre‑computed bone_matrices found in frame!")

        matrices = frame.bone_matrices
        return matrices
    # ------------------------------------------------------------------
    # Public: get skeleton lines for the OpenGL widget
    # ------------------------------------------------------------------
    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0) -> List[Tuple]:
        """
        Returns list of (start_pos, end_pos) tuples in viewer space.
        Each pos is (x, y, z).

        We apply the same axis flip that your Vertex.get_list() uses:
            viewer_x = -raw_x * SCALE
            viewer_z = -raw_y * SCALE   (note: file Y -> viewer Z)
            viewer_y = -raw_z * SCALE   (note: file Z -> viewer Y)

        The bone matrices use the raw/unflipped space, so we flip at the end.
        """
        world_matrices = self._get_bone_matrices(anim_id, frame_id)
        if not world_matrices:
            return []

        bones = self.enemy.bone_data.bones

        # --- Build line segments (parent -> child pivot) ---
        lines = []
        for k, bone in enumerate(bones):
            if bone.parent_id == 0xFFFF:
                continue
            if k >= len(world_matrices) or bone.parent_id >= len(world_matrices):
                continue

            parent_mat = world_matrices[bone.parent_id]
            child_mat  = world_matrices[k]
            if parent_mat is None or child_mat is None:
                continue


            def to_viewer(mat: Matrix4x4):
                return mat.M41, mat.M42, mat.M43

            parent_pos = to_viewer(parent_mat)
            child_pos  = to_viewer(child_mat)

            lines.append((parent_pos, child_pos))

        return lines

    def get_animated_vertices(self, anim_id: int, frame_id: int, next_frame_id: int = None, step: float = 0.0) -> List[Tuple[float, float, float]]:
        """
        Get animated vertices for current frame.
        If next_frame_id is provided, interpolate between frames using step (0.0-1.0).
        """
        anim = self.enemy.animation_data.animations[anim_id]
        frame = anim.frames[frame_id]
        matrices = frame.bone_matrices  # already built!

        if next_frame_id is not None:
            next_frame = anim.frames[next_frame_id]
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

