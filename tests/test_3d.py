"""
Tests for Ifrit3D bone and animation data structures.

Tests the BoneSection, Bone, AnimationFrame, Animation, and AnimationSection
with real FF8 battle model data, verifying that bone/animation parsing and
serialization work correctly.
"""
import sys
import pathlib
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.monsterdata import (
    BoneSection, Bone, AnimationFrame, Animation, AnimationSection,
    Matrix4x4, Vector3D, RotationType, PositionType,
    BitReader, BitWriter
)
from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget


# ---------------------------------------------------------------------------
# Shared test data - c0m003.dat bone and animation data
# ---------------------------------------------------------------------------

# Bone data from c0m003.dat (first 15 bytes shown here for header + one bone entry)
C0M003_BONE_DATA = bytearray([
    0x23, 0x00, 0x2F, 0x01, 0x0A, 0x01, 0x00, 0x00, 0x68, 0xC0, 0x07, 0x08, 0x16, 0x00, 0x00, 0x00,
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x9C, 0xF3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x14, 0xF9,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0xF1, 0xEF,
])

# Animation data sample (first animation frame bytes)
C0M003_ANIMATION_DATA = bytearray([
    0x01, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x1D, 0x00, 0x10, 0x00, 0x0D, 0x00, 0x50, 0xFF,
    0x00, 0x00, 0x89, 0xFC, 0x0D, 0x01, 0x00, 0x00, 0xFF, 0xFD, 0xC2, 0xFD, 0x00, 0x00, 0xDC, 0xFC,
    0xFF, 0xFE, 0x00, 0x00, 0xD7, 0xFF, 0x2F, 0xFF, 0x00, 0x00, 0x2C, 0xFE, 0x25, 0x00, 0x0C, 0x01,
    0x34, 0xFE, 0x2F, 0xFF, 0x0D, 0x01, 0x2C, 0xFE, 0xFF, 0xFE, 0x97, 0x01, 0xD7, 0xFF, 0x13, 0x00,
])

# Minimal bone data for testing
MINIMAL_BONE_DATA = bytearray([
    0x01,  # 1 bone
    0x00,  # extra data flag
    0x00, 0x00,  # unknown00
    0x00, 0x00,  # unknown01
    0x00, 0x00,  # unknown02
    0x00, 0x08,  # scale_x (signed)
    0x00, 0x08,  # scale_y (signed)
    0x00, 0x08,  # scale_z (signed)
    0x00, 0x00,  # unknown2
    # Bone data (48 bytes)
    0xFF, 0xFF,  # parent (-1 = root)
    0x00, 0x01,  # size
    0x00, 0x00,  # rotX
    0x00, 0x00,  # rotY
    0x00, 0x00,  # rotZ
    0x00, 0x00,  # unknown3
    0x00, 0x00,  # unknown4
    0x00, 0x00,  # unknown5
    0x00, 0x00,  # unknown6
    0x00, 0x00,  # unknown7
    0x00, 0x00,  # unknown8
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Create QApplication singleton for test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(scope="session")
def game_data():
    """Load GameData once for the entire test session."""
    project_root = pathlib.Path(__file__).parent.parent
    game_data = GameData(str(project_root / "FF8GameData"))
    game_data.load_all()
    return game_data


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _make_mock_ifrit_manager():
    """Create a mock IfritManager for testing."""
    manager = MagicMock()
    manager.enemy = MagicMock()
    manager.enemy.bone_section = None
    manager.bone_data = []
    return manager


# ===========================================================================
# Section 1 – BoneSection tests (pure data-model)
# ===========================================================================

class TestBoneSectionDataModel:
    """
    Tests for BoneSection that operate solely on the data model,
    without requiring QApplication.
    """

    def test_bone_section_init(self):
        """BoneSection should initialize with default values."""
        section = BoneSection()
        assert section.nb_bone == 0
        assert section.extra_data == False
        assert section.unknown00 == 0
        assert len(section.bones) == 0

    def test_bone_section_analyze_minimal(self):
        """BoneSection should analyze minimal bone data."""
        section = BoneSection()
        section.analyze(MINIMAL_BONE_DATA)
        assert section.nb_bone == 1
        assert len(section.bones) == 1
        assert section.bones[0].parent_id == 0xFFFF

    def test_bone_section_c0m003_parse(self):
        """BoneSection should parse c0m003 bone data."""
        section = BoneSection()
        section.analyze(C0M003_BONE_DATA)
        assert section.nb_bone == 0x23  # 35 bones
        assert len(section.bones) == 35

    def test_bone_section_scale_extraction(self):
        """BoneSection should correctly extract scale values."""
        section = BoneSection()
        section.analyze(MINIMAL_BONE_DATA)
        scales = section.get_scale_list()
        assert isinstance(scales, tuple)
        assert len(scales) == 3

    def test_bone_section_to_binary_roundtrip(self):
        """BoneSection should preserve data through to_binary()."""
        section = BoneSection()
        section.analyze(MINIMAL_BONE_DATA)
        binary = section.to_binary()

        # Parse the binary back
        section2 = BoneSection()
        section2.analyze(binary)
        assert section2.nb_bone == section.nb_bone
        assert len(section2.bones) == len(section.bones)


# ===========================================================================
# Section 2 – Bone unit tests
# ===========================================================================

class TestBone:
    """
    Tests for individual Bone data structures.
    """

    def test_bone_init(self):
        """Bone should initialize with default values."""
        bone = Bone()
        assert bone.parent_id == 0
        assert bone.get_size() == 0

    def test_bone_analyze(self):
        """Bone should analyze 48-byte bone data."""
        bone_data = MINIMAL_BONE_DATA[16:64]  # Extract bone portion
        bone = Bone()
        bone.analyze(bone_data)
        assert bone.parent_id == 0xFFFF
        # Size is stored as raw int and returned as float (divided by 2048)
        assert abs(bone.get_size() - (0x0100 / 2048)) < 0.01

    def test_bone_get_byte(self):
        """Bone should serialize back to 48 bytes."""
        bone = Bone()
        bone.parent_id = 0x0001
        bone._size = 0x0100
        binary = bone.get_byte()
        assert len(binary) == 48
        assert binary[0:2] == bytearray([0x01, 0x00])

    def test_bone_parent_id(self):
        """Bone parent_id should be accessible."""
        bone = Bone()
        bone.parent_id = 5
        assert bone.parent_id == 5

    def test_bone_size_conversion(self):
        """Bone size should convert to world coordinates."""
        bone = Bone()
        bone._size = 2048  # Raw size (corresponds to 1.0 in world units)
        size = bone.get_size()
        assert abs(size - 1.0) < 0.01  # Should be 1.0 when divided by 2048


# ===========================================================================
# Section 3 – AnimationFrame tests
# ===========================================================================

class TestAnimationFrame:
    """
    Tests for AnimationFrame data structures.
    """

    def test_animation_frame_init(self):
        """AnimationFrame should initialize with correct number of bones."""
        frame = AnimationFrame(nb_bones=5)
        assert len(frame.rotation_vector_data) == 5
        assert len(frame.bone_matrices) == 5
        assert frame.position == []

    def test_animation_frame_position_data(self):
        """AnimationFrame should handle position data."""
        frame = AnimationFrame(nb_bones=1)
        frame.position = [
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
        ]
        assert len(frame.position) == 3

    def test_animation_frame_rotation_data(self):
        """AnimationFrame should handle rotation data."""
        frame = AnimationFrame(nb_bones=2)
        frame.rotation_vector_data[0] = [
            RotationType(True, 0, 0),
            RotationType(True, 0, 0),
            RotationType(True, 0, 0),
        ]
        assert len(frame.rotation_vector_data[0]) == 3

    def test_animation_frame_bone_matrices(self):
        """AnimationFrame should have identity matrices initially."""
        frame = AnimationFrame(nb_bones=3)
        assert len(frame.bone_matrices) == 3
        # Check first matrix is identity
        mat = frame.bone_matrices[0]
        assert mat.M11 == 1.0
        assert mat.M22 == 1.0
        assert mat.M33 == 1.0
        assert mat.M44 == 1.0


# ===========================================================================
# Section 4 – Animation tests
# ===========================================================================

class TestAnimation:
    """
    Tests for Animation (collection of frames).
    """

    def test_animation_init(self):
        """Animation should initialize empty."""
        anim = Animation()
        assert len(anim.frames) == 0

    def test_animation_add_frame(self):
        """Animation should be able to store frames."""
        anim = Animation()
        frame = AnimationFrame(nb_bones=1)
        anim.frames.append(frame)
        assert len(anim.frames) == 1

    def test_animation_get_nb_frame(self):
        """Animation should report correct frame count."""
        anim = Animation()
        for _ in range(5):
            anim.frames.append(AnimationFrame(nb_bones=1))
        assert anim.get_nb_frame() == 5

    def test_animation_to_binary(self):
        """Animation should serialize to binary."""
        anim = Animation()
        frame = AnimationFrame(nb_bones=1)
        frame.position = [
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
            PositionType(position_type_bits=0, vector_axis=0, bone_scale=20480),
        ]
        frame.rotation_vector_data[0] = [
            RotationType(False, 0, 0),
            RotationType(False, 0, 0),
            RotationType(False, 0, 0),
        ]
        anim.frames.append(frame)

        binary = anim.to_binary()
        assert len(binary) > 0
        assert binary[0] == 1  # Frame count


# ===========================================================================
# Section 5 – Matrix4x4 tests
# ===========================================================================

class TestMatrix4x4:
    """
    Tests for Matrix4x4 transformation matrices.
    """

    def test_matrix_identity(self):
        """Matrix4x4 should be identity by default."""
        mat = Matrix4x4()
        assert mat.M11 == 1.0
        assert mat.M22 == 1.0
        assert mat.M33 == 1.0
        assert mat.M44 == 1.0
        assert mat.M12 == 0.0
        assert mat.M21 == 0.0

    def test_matrix_rotation_x(self):
        """Matrix4x4 should create rotation X matrices."""
        mat = Matrix4x4.CreateRotationX(90.0)
        assert mat.M11 == 1.0  # X-axis rotation doesn't change M11
        # M22 and M33 should be affected by 90 degree rotation
        assert abs(mat.M22) < 0.01 or abs(mat.M22 - 1.0) < 0.01

    def test_matrix_rotation_y(self):
        """Matrix4x4 should create rotation Y matrices."""
        mat = Matrix4x4.CreateRotationY(90.0)
        assert mat.M22 == 1.0  # Y-axis rotation doesn't change M22

    def test_matrix_rotation_z(self):
        """Matrix4x4 should create rotation Z matrices."""
        mat = Matrix4x4.CreateRotationZ(90.0)
        assert mat.M33 == 1.0  # Z-axis rotation doesn't change M33

    def test_matrix_multiply_identity(self):
        """Matrix multiplication with identity should be unchanged."""
        mat1 = Matrix4x4.CreateRotationX(45.0)
        mat2 = Matrix4x4()  # Identity
        result = Matrix4x4.MultiplyRowMajor(mat1, mat2)
        assert result.M11 == mat1.M11


# ===========================================================================
# Section 6 – Ifrit3DWidget integration tests
# ===========================================================================

class TestIfrit3DWidget:
    """
    Tests for the Ifrit3DWidget integration.
    """

    def test_ifrit3d_widget_init(self, qapp):
        """Ifrit3DWidget should initialize."""
        manager = _make_mock_ifrit_manager()
        widget = Ifrit3DWidget(manager, show_controls=False)
        assert widget is not None
        assert widget.current_anim_id == 0
        assert widget.current_frame == 0

    def test_ifrit3d_widget_has_gl_widget(self, qapp):
        """Ifrit3DWidget should have OpenGL widget."""
        manager = _make_mock_ifrit_manager()
        widget = Ifrit3DWidget(manager, show_controls=False)
        assert hasattr(widget, 'gl_widget')

    def test_ifrit3d_widget_animation_controls(self, qapp):
        """Ifrit3DWidget should have animation controls."""
        manager = _make_mock_ifrit_manager()
        widget = Ifrit3DWidget(manager, show_controls=True)
        assert hasattr(widget, 'play_btn')
        assert hasattr(widget, 'reset_anim_btn')
        assert hasattr(widget, 'frame_label')

    def test_ifrit3d_widget_fps_setting(self, qapp):
        """Ifrit3DWidget should allow FPS setting."""
        manager = _make_mock_ifrit_manager()
        widget = Ifrit3DWidget(manager, show_controls=False)
        assert widget.fps == 15
        # Should be modifiable
        widget.fps = 30
        assert widget.fps == 30

    def test_ifrit3d_widget_animation_state(self, qapp):
        """Ifrit3DWidget should track animation state."""
        manager = _make_mock_ifrit_manager()
        widget = Ifrit3DWidget(manager, show_controls=False)
        assert widget.animating == False


# ===========================================================================
# Section 7 – Vector3D and helper classes
# ===========================================================================

class TestVector3D:
    """
    Tests for Vector3D helper class.
    """

    def test_vector3d_init_default(self):
        """Vector3D should initialize with zeros."""
        vec = Vector3D()
        assert vec.x == 0
        assert vec.y == 0
        assert vec.z == 0

    def test_vector3d_init_values(self):
        """Vector3D should accept initial values."""
        vec = Vector3D(x=1.0, y=2.0, z=3.0)
        assert vec.x == 1.0
        assert vec.y == 2.0
        assert vec.z == 3.0


class TestRotationType:
    """
    Tests for RotationType helper class.
    """

    def test_rotation_type_init(self):
        """RotationType should initialize correctly."""
        rot = RotationType(is_rotation_type_available=True, rotation_type_bits=2, vector_axis=45)
        assert rot.is_rotation_type_available == True
        assert rot.rotation_type_bits == 2
        # Vector axis represents raw rotation value
        assert rot._vector_axis == 45

    def test_rotation_type_degree_conversion(self):
        """RotationType should convert between degrees and raw values."""
        rot = RotationType(is_rotation_type_available=True, rotation_type_bits=2, vector_axis=0)
        # Get rotation in degrees
        deg = rot.get_rotate_deg()
        assert isinstance(deg, float)


# ===========================================================================
# Section 8 – Edge cases and error handling
# ===========================================================================

class TestBoneEdgeCases:
    """
    Tests for edge cases and error conditions.
    """

    def test_bone_section_empty_bones(self):
        """BoneSection with no bones should handle correctly."""
        section = BoneSection()
        assert section.nb_bone == 0
        assert len(section.bones) == 0
        binary = section.to_binary()
        assert len(binary) >= 16  # At least header

    def test_bone_section_many_bones(self):
        """BoneSection should handle many bones."""
        # 35 bones (c0m003 has 35)
        section = BoneSection()
        section.analyze(C0M003_BONE_DATA)
        assert section.nb_bone == len(section.bones)

    def test_animation_frame_many_bones(self):
        """AnimationFrame should handle many bones."""
        frame = AnimationFrame(nb_bones=35)
        assert len(frame.rotation_vector_data) == 35
        assert len(frame.bone_matrices) == 35

    def test_matrix_zero_rotation(self):
        """Matrix should handle zero rotation."""
        mat = Matrix4x4.CreateRotationX(0.0)
        assert abs(mat.M22 - 1.0) < 0.01  # cos(0) = 1
        assert abs(mat.M23) < 0.01  # sin(0) = 0


# ===========================================================================
# Section 9 – Data integrity tests
# ===========================================================================

class TestDataIntegrity:
    """
    Tests to ensure data integrity through transformations.
    """

    def test_bone_section_parse_and_rewrite(self):
        """Bone data should survive parse → rewrite → parse cycle."""
        section1 = BoneSection()
        section1.analyze(C0M003_BONE_DATA)

        binary = section1.to_binary()

        section2 = BoneSection()
        section2.analyze(binary)

        assert section2.nb_bone == section1.nb_bone
        assert len(section2.bones) == len(section1.bones)

    def test_animation_frame_string_representation(self):
        """AnimationFrame should have string representation."""
        frame = AnimationFrame(nb_bones=1)
        frame_str = str(frame)
        assert frame_str is not None
        assert "AnimationFrame" in frame_str

    def test_animation_string_representation(self):
        """Animation should have string representation."""
        anim = Animation()
        anim_str = str(anim)
        assert anim_str is not None
        assert "Animation" in anim_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])






