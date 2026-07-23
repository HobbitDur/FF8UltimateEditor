"""Tests for the multi-character composite model (Watts/compositemodel.py)."""
from Watts.compositemodel import (CompositeVictoryModel, party_slot_offsets,
                                  _build_texture_atlas)


class _FakeGeometry:
    """Same signatures as the real GeometryData, `include_hidden` included: the composite passes
    it straight down, so a fake without it would hide a break rather than catch one."""

    def __init__(self, verts, tris, quads):
        self._verts, self._tris, self._quads = verts, tris, quads

    def get_vertices(self):
        return self._verts

    def get_triangles(self, include_hidden=False):
        return self._tris

    def get_quads(self, include_hidden=False):
        return self._quads

    def get_triangles_with_uv(self, include_hidden=False):
        return []

    def get_quads_with_uv(self, include_hidden=False):
        return []

    def get_triangles_hidden_mask(self, include_hidden=False):
        return [False] * len(self._tris)

    def get_quads_hidden_mask(self, include_hidden=False):
        return [False] * len(self._quads)


class _FakeAnim:
    def __init__(self, nb_frames):
        self.frames = [object() for _ in range(nb_frames)]  # real (non-None) frame objects


class _FakeAnimData:
    def __init__(self, nb_frames):
        self.nb_animations = 1
        self.animations = [_FakeAnim(nb_frames)]


class _FakeEnemy:
    def __init__(self, geometry, nb_frames):
        self.geometry_data = geometry
        self.animation_data = _FakeAnimData(nb_frames)
        self.bone_data = "bones"          # delegated attribute
        self.entity_type = "CHARACTER"


class _FakeManager:
    def __init__(self, verts, tris, nb_frames=2):
        self.game_data = "gd"
        self.enemy = _FakeEnemy(_FakeGeometry(verts, tris, []), nb_frames)
        self.texture_data = []
        self._verts = verts

    def get_animated_vertices(self, anim_id, frame_id, next_frame_id=None, step=0.0):
        # a trivial "animation": shift every vertex by +frame_id in x
        return [(x + frame_id, y, z) for (x, y, z) in self._verts]


def test_party_slot_offsets_centred_row():
    assert party_slot_offsets(1, 7.0) == [(0.0, 0.0, 0.0)]
    assert party_slot_offsets(2, 7.0) == [(-3.5, 0.0, 0.0), (3.5, 0.0, 0.0)]
    assert party_slot_offsets(3, 7.0) == [(-7.0, 0.0, 0.0), (0.0, 0.0, 0.0), (7.0, 0.0, 0.0)]
    assert party_slot_offsets(0, 7.0) == []


def _entry(manager, offset, frames=2):
    return {"manager": manager, "win_pose_id": 0, "offset": offset,
            "frame_count": frames, "real_frame_count": frames}


def test_composite_merges_geometry_with_rebased_indices_and_offsets():
    a = _FakeManager([(0, 0, 0), (1, 0, 0)], [(0, 1, 0)])
    b = _FakeManager([(0, 0, 0), (2, 0, 0), (3, 0, 0)], [(0, 1, 2)])
    comp = CompositeVictoryModel([_entry(a, (-10.0, 0.0, 0.0)), _entry(b, (10.0, 0.0, 0.0))])

    verts = comp.enemy.geometry_data.get_vertices()
    assert len(verts) == 5                     # 2 + 3
    assert verts[0] == (-10, 0, 0)             # a's vertices shifted by a's offset
    assert verts[2] == (10, 0, 0)              # b's vertices shifted by b's offset

    tris = comp.enemy.geometry_data.get_triangles()
    assert tris == [(0, 1, 0), (2, 3, 4)]      # b's (0,1,2) rebased by len(a.verts)=2

    assert comp.enemy.animation_data.nb_animations == 1
    assert comp.enemy.bone_data == "bones"     # delegated to first manager's enemy


class _TexDesc:
    def __init__(self, image):
        self.texture_image = image


class _UVGeometry:
    def __init__(self, tri_uv, quad_uv):
        self._tri_uv, self._quad_uv = tri_uv, quad_uv

    def get_triangles_with_uv(self, include_hidden=False):
        return self._tri_uv

    def get_quads_with_uv(self, include_hidden=False):
        return self._quad_uv


class _UVManager:
    def __init__(self, tri_uv, quad_uv, textures):
        self.enemy = type("E", (), {"geometry_data": _UVGeometry(tri_uv, quad_uv)})()
        self.texture_data = textures


def test_texture_atlas_flattens_and_rebases_ids():
    # model 0 uses raw tex-ids {0, 64} with two textures; model 1 uses {0} with one
    m0 = _UVManager([((0, 1, 2), (), 0, 0), ((3, 4, 5), (), 64, 0)], [],
                    [_TexDesc("a"), _TexDesc("b")])
    m1 = _UVManager([((0, 1, 2), (), 0, 0)], [], [_TexDesc("c")])
    textures, remap = _build_texture_atlas([(m0, 0, (0, 0, 0)), (m1, 0, (0, 0, 0))])
    # each character's textures stacked in order; ids contiguous per (model, raw-id)
    assert [t.texture_image for t in textures] == ["a", "b", "c"]
    assert remap == {(0, 0): 0, (0, 64): 1, (1, 0): 2}


def test_composite_animated_vertices_offset_and_clamped():
    a = _FakeManager([(0, 0, 0)], [])
    b = _FakeManager([(0, 0, 0)], [])
    comp = CompositeVictoryModel([_entry(a, (-10.0, 0.0, 0.0), frames=2),
                                  _entry(b, (10.0, 0.0, 0.0), frames=2)])
    frame1 = comp.get_animated_vertices(0, 1)
    assert frame1 == [(-9, 0, 0), (11, 0, 0)]  # +1 (frame) then +/-10 (party offset)
    # frame beyond a model's count clamps to its last frame (2 frames -> max index 1)
    assert comp.get_animated_vertices(0, 5) == [(-9, 0, 0), (11, 0, 0)]


def test_the_composite_answers_every_call_the_real_geometry_does():
    """The composite stands in for a GeometryData in front of Ifrit3DWidget, and the viewer calls
    it with the same arguments it uses on a real model. When the real class grew `include_hidden`
    and the hidden-face masks, the composite did not follow, and the whole multi-character preview
    fell back to "3D preview unavailable" - a TypeError swallowed into a placeholder, which no
    unit test noticed because the fakes had drifted too.

    So the signatures are checked against the real class rather than against a fake."""
    import inspect

    from FF8GameData.monsterdata import GeometrySection
    from Watts.compositemodel import _CompositeGeometry

    for name in ("get_vertices", "get_triangles", "get_quads", "get_triangles_with_uv",
                 "get_quads_with_uv", "get_triangles_hidden_mask", "get_quads_hidden_mask",
                 "get_colored_triangles_with_color", "get_colored_quads_with_color"):
        real = getattr(GeometrySection, name, None)
        assert real is not None, f"the real geometry no longer has {name}"
        composite = getattr(_CompositeGeometry, name, None)
        assert composite is not None, f"the composite is missing {name}"
        assert (list(inspect.signature(composite).parameters)
                == list(inspect.signature(real).parameters)), f"{name} signatures have drifted"


def test_the_composite_animation_answers_get_nb_frame():
    """Same drift, on the animation side: the viewer asks every frame, and a composite without it
    took the preview down the same silent fallback."""
    from Watts.compositemodel import _CompositeAnimationData

    animation = _CompositeAnimationData([object(), object(), object()]).animations[0]
    assert animation.get_nb_frame() == 3
