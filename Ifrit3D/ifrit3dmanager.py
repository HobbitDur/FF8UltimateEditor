import math
from typing import Tuple, List

from FF8GameData.gamedata import GameData, Matrix4x4, AnimationSection, BoneSection


class Ifrit3DManager:
    def __init__(self, monster_file: str, game_data_folder="FF8GameData"):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()

        from FF8GameData.dat.monsteranalyser import MonsterAnalyser
        self.monster_data = MonsterAnalyser(self.game_data)
        self.monster_data.load_file_data(monster_file, self.game_data)
        self.monster_data.analyse_loaded_data(self.game_data)

    # ------------------------------------------------------------------
    # Core: build world-space bone matrices for a given anim/frame
    # This is a direct Python port of the C# ReadSection3 matrix loop,
    # with the translation bug fixed.
    # ------------------------------------------------------------------
    def _build_bone_matrices(self, anim_id: int, frame_id: int,
                             debug: bool = True) -> List[Matrix4x4]:
        """
        Returns a list of world-space Matrix4x4 for every bone.
        Translation (M41, M42, M43) = world position of the bone's pivot.

        KEY FIX vs original AnimationSection code:
          The original code did:
              MatrixZ = Multiply(prevBone, MatrixZ)   # world rotation OK
              MatrixZ.M41 = 0; M42 = 0; M43 = bone_len  # local offset
              temp_m41 = MatrixZ.M41   # <-- BUG: saves 0, not world-space yet
              MatrixZ.M41 = prevBone.M11*temp_m41 + ... + prevBone.M41

          Because M41/M42/M43 were just set to (0, 0, bone_len),
          temp_m41/m42/m43 = (0, 0, bone_len), and the formula becomes:
              new_M41 = prevBone.M13 * bone_len + prevBone.M41   -- CORRECT
          ... which is actually right! The temp_ variables don't help or hurt
          when the values are (0, 0, bone_len).

          So the C# code IS correct. The bug must be elsewhere.
          This version is a clean, explicit reimplementation to be sure.
        """
        anim_section: AnimationSection = self.monster_data.animation_data
        bone_section: BoneSection = self.monster_data.bone_data

        if anim_id >= len(anim_section.animations):
            print(f"[ERROR] anim_id {anim_id} out of range (max {len(anim_section.animations)-1})")
            return []

        anim = anim_section.animations[anim_id]
        if frame_id >= anim.nb_frames:
            print(f"[WARN] frame_id {frame_id} >= nb_frames {anim.nb_frames}, clamping to 0")
            frame_id = 0

        frame = anim.frames[frame_id]
        bones = bone_section.bones
        nb_bones = len(bones)

        world_matrices: List[Matrix4x4] = [None] * nb_bones

        if debug:
            print(f"\n{'='*60}")
            print(f"BUILD MATRICES: anim={anim_id}  frame={frame_id}")
            print(f"{'='*60}")
            print(f"Root position from animation: {frame.position}")
        for k in range(nb_bones):
            deg = frame.bone_rot_deg[k]
            xRot = Matrix4x4.CreateRotationX(-deg[0])
            yRot = Matrix4x4.CreateRotationY(-deg[1])
            zRot = Matrix4x4.CreateRotationZ(-deg[2])

            local = Matrix4x4.MultiplyColumnMajor(yRot, xRot)
            local = Matrix4x4.MultiplyColumnMajor(zRot, local)

            parent_id = bones[k].parent_id
            if parent_id != 0xFFFF:
                parent_mat = world_matrices[parent_id]
                world = Matrix4x4.MultiplyRowMajor(parent_mat, local)
                parent_length = bones[parent_id].size
                world.M41 = parent_mat.M13 * parent_length + parent_mat.M41
                world.M42 = parent_mat.M23 * parent_length + parent_mat.M42
                world.M43 = parent_mat.M33 * parent_length + parent_mat.M43
                world_matrices[k] = world
            else:
                local.M41 = 0.0
                local.M42 = 0.0
                local.M43 = 0.0
                world_matrices[k] = local

            if debug and k == 16:  # adjust bone index as needed
                print(f"\n=== Bone {k} (ID {k}) World Matrix ===")
                # Row-major axes (X, Y, Z as rows)
                print(f"X axis: ({world.M11:.6f}, {world.M12:.6f}, {world.M13:.6f})")
                print(f"Y axis: ({world.M21:.6f}, {world.M22:.6f}, {world.M23:.6f})")
                print(f"Z axis: ({world.M31:.6f}, {world.M32:.6f}, {world.M33:.6f})")
                print(f"Position: ({world.M41:.6f}, {world.M42:.6f}, {world.M43:.6f})")


        return world_matrices

    # ------------------------------------------------------------------
    # Public: get skeleton lines for the OpenGL widget
    # ------------------------------------------------------------------
    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0,
                           debug: bool = True) -> List[Tuple]:
        """
        Returns list of (start_pos, end_pos) tuples in viewer space.
        Each pos is (x, y, z).

        We apply the same axis flip that your Vertex.get_list() uses:
            viewer_x = -raw_x * SCALE
            viewer_z = -raw_y * SCALE   (note: file Y -> viewer Z)
            viewer_y = -raw_z * SCALE   (note: file Z -> viewer Y)

        The bone matrices use the raw/unflipped space, so we flip at the end.
        """
        world_matrices = self._build_bone_matrices(anim_id, frame_id, debug=debug)
        if not world_matrices:
            return []

        bones = self.monster_data.bone_data.bones

        # --- Debug: compare frame 0 vs frame 1 to check drift ---
        if debug and frame_id == 0 and anim_id == 0:
            print(f"\n{'='*60}")
            print("FRAME 0 vs FRAME 1 position comparison (bone 6, 7):")
            mats_f1 = self._build_bone_matrices(anim_id, 1)
            for bone_idx in [6, 7, 11, 12]:
                if bone_idx < len(world_matrices) and bone_idx < len(mats_f1):
                    m0 = world_matrices[bone_idx]
                    m1 = mats_f1[bone_idx]
                    dx = m1.M41 - m0.M41
                    dy = m1.M42 - m0.M42
                    dz = m1.M43 - m0.M43
                    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                    print(f"  Bone {bone_idx:2d}: frame0=({m0.M41:.4f},{m0.M42:.4f},{m0.M43:.4f})  "
                          f"frame1=({m1.M41:.4f},{m1.M42:.4f},{m1.M43:.4f})  delta_dist={dist:.4f}")
            print()

        # --- Compare with Noesis SMD frame 0 for key bones ---
        if debug and frame_id == 0 and anim_id == 0:
            print(f"\n{'='*60}")
            print("SMD COMPARISON (frame 0, raw matrix space):")
            # From your SMD file (document 4), frame 0 positions (raw, not scaled):
            # bone 0:  pos (-120, -14445, 2100)   <- root
            # bone 6:  pos (0, 0.000244, -2853)   <- relative? or world?
            # The SMD stores world positions in raw units (not /2048).
            # Let's print our world positions * 2048 to compare:
            UNSCALE = 2048.0
            print(f"  (Showing world_pos * 2048 to match SMD raw units)")
            for k in range(min(12, len(world_matrices))):
                m = world_matrices[k]
                if m:
                    print(f"  Bone {k:2d}: ({m.M41*UNSCALE:10.3f}, {m.M42*UNSCALE:10.3f}, {m.M43*UNSCALE:10.3f})")

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

        if debug:
            print(f"\nTotal skeleton line segments: {len(lines)}")
            for i, (s, e) in enumerate(lines[:6]):
                print(f"  Line {i}: {s} -> {e}")

        return lines

    def get_animated_vertices(self, anim_id: int, frame_id: int, next_frame_id: int = None, step: float = 0.0) -> List[Tuple[float, float, float]]:
        """
        Get animated vertices for current frame.
        If next_frame_id is provided, interpolate between frames using step (0.0-1.0).
        """
        anim = self.monster_data.animation_data.animations[anim_id]
        frame = anim.frames[frame_id]
        matrices = frame.bone_matrices  # already built!

        if next_frame_id is not None:
            next_frame = anim.frames[next_frame_id]
            next_matrices = next_frame.bone_matrices
        else:
            next_matrices = None

        # Get static vertices with bone assignments
        geometry = self.monster_data.geometry_data
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
        result_x = (matrix.M11 * x +
                    matrix.M12 * -z +  # Note: file Y -> viewer Z, so we use -z
                    matrix.M13 * -y +  # file Z -> viewer Y, so we use -y
                    matrix.M41)

        result_y = (matrix.M21 * x +
                    matrix.M22 * -z +
                    matrix.M23 * -y +
                    matrix.M42)

        result_z = (matrix.M31 * x +
                    matrix.M32 * -z +
                    matrix.M33 * -y +
                    matrix.M43)

        return (result_x, result_y, result_z)