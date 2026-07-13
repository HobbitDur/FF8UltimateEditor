"""
Tests for the Ifrit3D glTF exporter/importer maths (Ifrit/Ifrit3D/gltfexporter.py
and gltfimporter.py).

These cover the pure geometry helpers the .glb round-trip relies on — matrix
multiply/inverse, rotation/scale decomposition, quaternion extraction and the
FF8 vertex/UV (de)swizzling — none of which need the original game files.
"""
import math

import pytest

from Ifrit.Ifrit3D.gltfexporter import (
    _transform_point, _mat_mul, _mat4_inverse, _rigid_inverse,
    _decompose_rotation_scale, _quat_from_matrix,
)
from Ifrit.Ifrit3D.gltfimporter import GltfImporter, _clamp_i16

IDENTITY = [[1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _almost_equal_matrix(a, b, tol=1e-9):
    return all(abs(a[r][c] - b[r][c]) <= tol for r in range(4) for c in range(4))


def _rotation_z(theta, tx=0.0, ty=0.0, tz=0.0):
    c, s = math.cos(theta), math.sin(theta)
    return [[c, -s, 0.0, tx],
            [s, c, 0.0, ty],
            [0.0, 0.0, 1.0, tz],
            [0.0, 0.0, 0.0, 1.0]]


class TestMatrixHelpers:
    def test_identity_multiply(self):
        assert _mat_mul(IDENTITY, IDENTITY) == IDENTITY

    def test_transform_point_identity(self):
        assert _transform_point(IDENTITY, (1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)

    def test_transform_point_translation(self):
        m = _rotation_z(0.0, tx=5.0, ty=-2.0, tz=1.0)
        assert _transform_point(m, (1.0, 1.0, 1.0)) == (6.0, -1.0, 2.0)

    def test_transform_point_rotation(self):
        m = _rotation_z(math.pi / 2)   # 90° about Z: (1,0,0) -> (0,1,0)
        x, y, z = _transform_point(m, (1.0, 0.0, 0.0))
        assert abs(x) < 1e-9 and abs(y - 1.0) < 1e-9 and abs(z) < 1e-9

    def test_mat4_inverse_is_true_inverse(self):
        m = _rotation_z(0.7, tx=5.0, ty=6.0, tz=7.0)
        inv = _mat4_inverse(m)
        assert _almost_equal_matrix(_mat_mul(inv, m), IDENTITY)
        assert _almost_equal_matrix(_mat_mul(m, inv), IDENTITY)

    def test_mat4_inverse_handles_scale(self):
        """Unlike a rigid inverse, the full inverse must invert a scaled matrix."""
        m = [[2.0, 0.0, 0.0, 1.0],
             [0.0, 3.0, 0.0, 2.0],
             [0.0, 0.0, 4.0, 3.0],
             [0.0, 0.0, 0.0, 1.0]]
        inv = _mat4_inverse(m)
        assert _almost_equal_matrix(_mat_mul(inv, m), IDENTITY)

    def test_mat4_inverse_singular_falls_back_to_rigid(self):
        singular = [[0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0]]
        # must not raise: it falls back to the rigid inverse
        assert _mat4_inverse(singular) == _rigid_inverse(singular)

    def test_rigid_inverse_matches_full_inverse_for_rigid(self):
        m = _rotation_z(1.1, tx=-3.0, ty=4.0, tz=5.0)
        assert _almost_equal_matrix(_rigid_inverse(m), _mat4_inverse(m))


class TestQuaternion:
    def test_identity_is_unit_w(self):
        x, y, z, w = _quat_from_matrix(IDENTITY)
        assert (round(x, 9), round(y, 9), round(z, 9), round(w, 9)) == (0.0, 0.0, 0.0, 1.0)

    def test_90deg_about_z(self):
        x, y, z, w = _quat_from_matrix(_rotation_z(math.pi / 2))
        half = math.sqrt(2) / 2
        assert abs(x) < 1e-9 and abs(y) < 1e-9
        assert abs(z - half) < 1e-9 and abs(w - half) < 1e-9

    def test_quaternion_is_normalised(self):
        for theta in (0.3, 1.2, 2.5, 3.0):
            x, y, z, w = _quat_from_matrix(_rotation_z(theta))
            assert abs(math.sqrt(x * x + y * y + z * z + w * w) - 1.0) < 1e-9


class TestDecomposeRotationScale:
    def test_pure_rotation_has_unit_scale(self):
        _rot, scale = _decompose_rotation_scale(_rotation_z(0.9))
        assert all(abs(s - 1.0) < 1e-9 for s in scale)

    def test_extracts_uniform_and_nonuniform_scale(self):
        m = [[2.0, 0.0, 0.0, 0.0],
             [0.0, 3.0, 0.0, 0.0],
             [0.0, 0.0, 4.0, 0.0],
             [0.0, 0.0, 0.0, 1.0]]
        rot, scale = _decompose_rotation_scale(m)
        assert (round(scale[0], 6), round(scale[1], 6), round(scale[2], 6)) == (2.0, 3.0, 4.0)
        # no rotation component -> identity quaternion
        assert (round(rot[0], 6), round(rot[1], 6), round(rot[2], 6), round(rot[3], 6)) == (0.0, 0.0, 0.0, 1.0)

    def test_reflection_folded_into_negative_x_scale(self):
        # negative determinant (mirror on X) must stay a proper rotation
        m = [[-1.0, 0.0, 0.0, 0.0],
             [0.0, 1.0, 0.0, 0.0],
             [0.0, 0.0, 1.0, 0.0],
             [0.0, 0.0, 0.0, 1.0]]
        _rot, scale = _decompose_rotation_scale(m)
        assert scale[0] < 0


class TestClampI16:
    def test_within_range_unchanged(self):
        assert _clamp_i16(5) == 5
        assert _clamp_i16(-5) == -5

    def test_clamps_bounds(self):
        assert _clamp_i16(40000) == 32767
        assert _clamp_i16(-40000) == -32768
        assert _clamp_i16(32767) == 32767
        assert _clamp_i16(-32768) == -32768


class TestUvSwizzle:
    def test_make_uv_scales_and_masks(self):
        uv = GltfImporter._make_uv((0.5, 0.25))
        assert uv._u == 64   # round(0.5 * 128)
        assert uv._v == 32   # round(0.25 * 128)

    def test_make_uv_wraps_to_byte(self):
        uv = GltfImporter._make_uv((2.0, 3.0))   # 256, 384 -> & 0xFF
        assert uv._u == 0
        assert uv._v == 128


class TestVertexSwizzleRoundtrip:
    """The importer must invert the exporter's raw->world vertex placement."""

    @pytest.mark.parametrize("raw", [(0, 0, 0), (10, -20, 30), (32000, -32000, 1)])
    def test_unskinned_roundtrip(self, raw):
        # Exporter's Vertex.get_list() swizzle: (-_x/2048, _z/2048, -_y/2048)
        world = (-raw[0] / 2048.0, raw[2] / 2048.0, -raw[1] / 2048.0)
        recovered = GltfImporter._world_to_raw(world[0], world[1], world[2], 0, None)
        assert recovered == raw


class TestMaterialTexId:
    def test_recovers_id_from_exporter_material_name(self):
        gltf = {"materials": [{"name": "ff8_texture_7"}]}
        assert GltfImporter._material_tex_id(gltf, 0, {}) == 7

    def test_no_material_index_returns_zero(self):
        assert GltfImporter._material_tex_id({"materials": []}, None, {}) == 0

    def test_unnamed_material_gets_stable_sequential_fallback(self):
        gltf = {"materials": [{"name": "blob"}, {"name": "blob2"}]}
        fallback = {}
        first = GltfImporter._material_tex_id(gltf, 0, fallback)
        second = GltfImporter._material_tex_id(gltf, 1, fallback)
        # same material index keeps its assigned id
        assert GltfImporter._material_tex_id(gltf, 0, fallback) == first
        assert first == 0 and second == 1
