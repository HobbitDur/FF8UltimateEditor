import math
import pathlib
from typing import Tuple, List

from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData


class Ifrit3DManager:
    def __init__(self, monster_file:str, game_data_folder="FF8GameData"):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.monster_data = MonsterAnalyser(self.game_data)
        self.monster_data.load_file_data(monster_file, self.game_data)
        self.monster_data.analyse_loaded_data(self.game_data)

    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0):
        """Draw skeleton with correct hierarchical accumulation and scale"""
        anim_section = self.monster_data.animation_data
        bone_section = self.monster_data.bone_data

        if anim_id >= len(anim_section.animations):
            return []

        frame = anim_section.animations[anim_id].frames[frame_id]
        bones = bone_section.bones

        # Scale factor to make bones visible on screen
        SCALE = 1.0 / 2048.0

        # First, calculate world positions for all bones
        world_positions = {}

        # Bone 0 (root) at origin
        world_positions[0] = (0.0, 0.0, 0.0)

        # Process bones in order
        for k in range(len(bones)):
            if k == 0:
                continue

            bone = bones[k]
            if bone.parent_id != 0xFFFF and bone.parent_id in world_positions:
                mat = frame.bone_matrices[k]
                parent_mat = frame.bone_matrices[bone.parent_id]

                # Get local offset from parent
                local_offset = (mat.M41 - parent_mat.M41,
                                mat.M42 - parent_mat.M42,
                                mat.M43 - parent_mat.M43)

                # Apply rotation (y, -x, z) to local offset
                world_offset = (local_offset[1], -local_offset[0], local_offset[2])

                # Scale down for visibility
                world_offset_scaled = (world_offset[0] * SCALE,
                                       world_offset[1] * SCALE,
                                       world_offset[2] * SCALE)

                # Get parent world position
                parent_pos = world_positions[bone.parent_id]

                # Child world position = parent world position + offset
                child_pos = (parent_pos[0] + world_offset_scaled[0],
                             parent_pos[1] + world_offset_scaled[1],
                             parent_pos[2] + world_offset_scaled[2])

                world_positions[k] = child_pos

        # Draw lines from parent to child
        lines = []
        for k, bone in enumerate(bones):
            if bone.parent_id != 0xFFFF and k in world_positions and bone.parent_id in world_positions:
                parent_pos = world_positions[bone.parent_id]
                child_pos = world_positions[k]

                # Debug print for key bones
                if k == 1 or k == 3 or k == 8:
                    print(f"\nBone {k} (parent={bone.parent_id}):")
                    print(f"  Parent pos: ({parent_pos[0]:.4f}, {parent_pos[1]:.4f}, {parent_pos[2]:.4f})")
                    print(f"  Child pos:  ({child_pos[0]:.4f}, {child_pos[1]:.4f}, {child_pos[2]:.4f})")

                lines.append((parent_pos, child_pos))

        return lines
    # def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0):
    #     """Draw Bone 1->Bone 3 with different rotation orders"""
    #     anim_section = self.monster_data.animation_data
    #     bone_section = self.monster_data.bone_data
    #
    #     if anim_id >= len(anim_section.animations):
    #         return []
    #
    #     frame = anim_section.animations[anim_id].frames[frame_id]
    #
    #     SCALE = 1.0 / 2048.0
    #
    #     mat_bone1 = frame.bone_matrices[1]
    #     mat_bone3 = frame.bone_matrices[3]
    #
    #     # Local offset from Bone 1 to Bone 3 (already scaled)
    #     local_offset = (mat_bone3.M41 - mat_bone1.M41,
    #                     mat_bone3.M42 - mat_bone1.M42,
    #                     mat_bone3.M43 - mat_bone1.M43)
    #
    #     print(f"Local offset: ({local_offset[0]:.1f}, {local_offset[1]:.1f}, {local_offset[2]:.1f})")
    #
    #     # Try different axis mappings to make it point upward
    #     # We want the line to point mostly in +Y or +Z direction
    #
    #     tests = [
    #         ("(x, y, z) - original", (local_offset[0], local_offset[1], local_offset[2])),
    #         ("(x, z, y)", (local_offset[0], local_offset[2], local_offset[1])),
    #         ("(y, x, z)", (local_offset[1], local_offset[0], local_offset[2])),
    #         ("(y, z, x)", (local_offset[1], local_offset[2], local_offset[0])),
    #         ("(z, x, y)", (local_offset[2], local_offset[0], local_offset[1])),
    #         ("(z, y, x)", (local_offset[2], local_offset[1], local_offset[0])),
    #     ]
    #
    #     print("\n=== ORIENTATION TESTS ===")
    #     for name, vec in tests:
    #         # Scale for visibility
    #         scaled = (vec[0] * SCALE, vec[1] * SCALE, vec[2] * SCALE)
    #
    #         # Calculate angle from vertical (assuming Y is up)
    #         vertical_angle = math.degrees(math.atan2(math.sqrt(scaled[0] ** 2 + scaled[2] ** 2), abs(scaled[1])))
    #
    #         print(f"{name}: ({scaled[0]:.3f}, {scaled[1]:.3f}, {scaled[2]:.3f}) angle from vertical: {vertical_angle:.1f}°")
    #
    #         # Draw the best one (most vertical)
    #         if vertical_angle < 30:  # Within 30 degrees of vertical
    #             print(f"✓ Using this orientation!")
    #             lines = [((0, 0, 0), scaled)]
    #             return lines
    #
    #     # If none is vertical, use the one with smallest angle
    #     best_angle = 90
    #     best_vec = None
    #     for name, vec in tests:
    #         scaled = (vec[0] * SCALE, vec[1] * SCALE, vec[2] * SCALE)
    #         vertical_angle = math.degrees(math.atan2(math.sqrt(scaled[0] ** 2 + scaled[2] ** 2), abs(scaled[1])))
    #         if vertical_angle < best_angle:
    #             best_angle = vertical_angle
    #             best_vec = scaled
    #
    #     print(f"\nBest orientation (angle: {best_angle:.1f}°): ({best_vec[0]:.3f}, {best_vec[1]:.3f}, {best_vec[2]:.3f})")
    #     lines = [((0, 0, 0), best_vec)]
    #     return lines
    def debug_bone_positions(self, anim_id=0, frame_id=0):
        """Debug bone positions to verify they're being calculated"""
        anim_section = self.monster_data.animation_data
        bone_section = self.monster_data.bone_data

        if anim_id >= len(anim_section.animations):
            print("No animation found")
            return

        frame = anim_section.animations[anim_id].frames[frame_id]
        bones = bone_section.bones

        print(f"\n=== BONE POSITIONS (Frame {frame_id}) ===")
        for k, bone in enumerate(bones[:10]):  # First 10 bones
            mat = frame.bone_matrices[k]
            print(f"Bone {k}: parent={bone.parent_id}, pos=({mat.M41:.2f}, {mat.M42:.2f}, {mat.M43:.2f})")

        # Also print first few skeleton lines
        lines = []
        for k, bone in enumerate(bones):
            if bone.parent_id != 0xFFFF:
                mat = frame.bone_matrices[k]
                parent_mat = frame.bone_matrices[bone.parent_id]
                lines.append(((parent_mat.M41, parent_mat.M42, parent_mat.M43),
                              (mat.M41, mat.M42, mat.M43)))

        print(f"\n=== SKELETON LINES (First 5) ===")
        for i, (start, end) in enumerate(lines[:5]):
            print(f"Line {i}: ({start[0]:.2f}, {start[1]:.2f}, {start[2]:.2f}) -> ({end[0]:.2f}, {end[1]:.2f}, {end[2]:.2f})")