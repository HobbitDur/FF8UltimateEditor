"""Tests for direct skeleton manipulation in the Ifrit3D viewer.

Part 1 - joint picking math (no GL context, no game files): FF8OpenGLWidget
projects joints with the transform snapshot taken in paintGL; here the
snapshot is fabricated (identity model-view-projection over a 400x400
viewport) so a model point (x, y, z) lands on a known pixel.

Part 2 - skeleton edit persistence (real files, marked ff8data):
  * a bone-rotation edit on one frame must persist through save + reload and
    must NOT change any other frame. The file stores frames as deltas from
    the previous frame with per-value bit widths, so this exercises
    _recompute_frame_storage_types being called on edit (a stale "axis
    absent" flag silently drops the edit; a stale bit width truncates it and
    corrupts every following frame).
  * a bone-length edit must actually reach the model and persist
    (set_bone_length used to write a dead `bone.size` attribute instead of
    the real `_size` field).
Part 3 - rotation gizmo: ring geometry/angle math on fabricated transforms,
and on real files that the computed axes match what the manager's rotation
setter actually does to the skeleton.
"""
import copy
import pathlib
import shutil
import sys

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from Ifrit.Ifrit3D.ff8openwidget import FF8OpenGLWidget
from Ifrit.ifritmanager import IfritManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


# ---------------------------------------------------------------------------
# Part 1: picking math
# ---------------------------------------------------------------------------

def _make_widget(qapp):
    """Widget with a fabricated transform snapshot and a 3-bone skeleton.

    Identity MVP over a 400x400 viewport: model (x, y) projects to GL window
    pixel ((x+1)/2*400, (y+1)/2*400), which _project_joint converts to Qt
    (top-left origin, logical pixel) coordinates.
    """
    widget = FF8OpenGLWidget()
    widget._pick_modelview = np.identity(4, dtype=np.float64)
    widget._pick_projection = np.identity(4, dtype=np.float64)
    widget._pick_viewport = np.array([0, 0, 400, 400], dtype=np.int32)
    # Bone 0 = root (no line), bone 1 child of 0, bone 2 child of 1
    widget.skeleton_lines = [
        None,
        ((0.0, 0.0, 0.0), (0.5, 0.5, 0.0)),
        ((0.5, 0.5, 0.0), (-0.5, 0.0, 0.0)),
    ]
    widget.bone_parents = [0xFFFF, 0, 1]
    return widget


def _qt_pos(widget, win_x, win_y):
    """GL window pixel -> Qt logical widget coordinates (y flipped, dpr)."""
    dpr = widget.devicePixelRatioF()
    return win_x / dpr, (400 - win_y) / dpr


def test_pick_joint_selects_bone_at_line_end(qapp):
    widget = _make_widget(qapp)
    # Bone 1's joint is at model (0.5, 0.5, 0) -> GL window (300, 300)
    x, y = _qt_pos(widget, 300, 300)
    assert widget._pick_joint(x, y) == 1
    # Bone 2's joint at model (-0.5, 0, 0) -> GL window (100, 200)
    x, y = _qt_pos(widget, 100, 200)
    assert widget._pick_joint(x, y) == 2


def test_pick_joint_selects_root_from_child_line_start(qapp):
    widget = _make_widget(qapp)
    # Root has no line; its joint is the start of bone 1's line: (0, 0, 0)
    x, y = _qt_pos(widget, 200, 200)
    assert widget._pick_joint(x, y) == 0


def test_pick_joint_tolerates_radius_and_misses_beyond_it(qapp):
    widget = _make_widget(qapp)
    dpr = widget.devicePixelRatioF()
    x, y = _qt_pos(widget, 300, 300)
    inside = widget.PICK_RADIUS_PX - 2
    assert widget._pick_joint(x + inside, y) == 1
    outside = widget.PICK_RADIUS_PX * 2
    assert widget._pick_joint(x + outside, y + outside) == -1
    assert widget._pick_joint(*_qt_pos(widget, 40, 380)) == -1


def test_pick_joint_prefers_closest_to_camera_on_overlap(qapp):
    widget = _make_widget(qapp)
    # Bone 3's joint projects on the same pixel as bone 1's but nearer the
    # camera (smaller GL depth)
    widget.skeleton_lines.append(((0.0, 0.0, 0.0), (0.5, 0.5, -0.8)))
    widget.bone_parents.append(1)
    x, y = _qt_pos(widget, 300, 300)
    assert widget._pick_joint(x, y) == 3


def test_pick_joint_without_snapshot_returns_nothing(qapp):
    widget = _make_widget(qapp)
    widget._pick_modelview = None
    assert widget._pick_joint(200, 200) == -1


def test_length_drag_follows_child_line_not_own_line(qapp):
    """A bone's length places its CHILDREN along its axis, so the drag
    direction must follow the child's line (here bone 2's, pointing screen
    left-down from bone 1's joint), not bone 1's own line (right-up)."""
    widget = _make_widget(qapp)
    widget.selected_bone = 1
    direction = widget._selected_bone_axis_screen_dir()
    assert direction is not None
    dx, dy = direction
    # Child line (0.5, 0.5) -> (-0.5, 0.0) in model space: screen-left and,
    # with Qt's top-left origin, downwards
    assert dx < 0 and dy > 0
    # Bone 1's own line points the opposite way: guard against regressing to it
    own_p0 = widget._project_joint(widget.skeleton_lines[1][0])
    own_p1 = widget._project_joint(widget.skeleton_lines[1][1])
    assert (own_p1[0] - own_p0[0]) > 0  # own line goes screen-right


def test_length_drag_leaf_bone_falls_back_to_own_line(qapp):
    widget = _make_widget(qapp)
    widget.selected_bone = 2  # leaf: no bone has it as parent
    direction = widget._selected_bone_axis_screen_dir()
    assert direction is not None


def test_gizmo_angle_is_ccw_positive_around_axis(qapp):
    """Dragging counter-clockwise around an axis facing the camera must give
    a positive, right-hand-rule angle delta."""
    widget = _make_widget(qapp)
    widget.gizmo_center = (0.0, 0.0, 0.0)
    widget.gizmo_axes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    widget._gizmo_active_axis = 2  # Z, facing the identity camera
    widget._gizmo_use_plane = True
    # Model (0.5, 0) -> GL window (300, 200); model (0, 0.5) -> (200, 300).
    # Going from the first to the second is CCW around +Z.
    a0 = widget._gizmo_angle(*_qt_pos(widget, 300, 200))
    a1 = widget._gizmo_angle(*_qt_pos(widget, 200, 300))
    assert a0 is not None and a1 is not None
    delta = (a1 - a0 + 180.0) % 360.0 - 180.0
    assert delta == pytest.approx(90.0, abs=1.0)


def test_pick_gizmo_axis_finds_the_clicked_ring(qapp):
    widget = _make_widget(qapp)
    widget.resize(400, 400)
    widget.zoom = 2.0  # gives the rings a real on-screen radius
    widget.gizmo_center = (0.0, 0.0, 0.0)
    widget.gizmo_axes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    # A 45-degree point of the Z ring: not shared with the X ring (x=0 plane)
    # nor the Y ring (y=0 plane)
    point = widget._gizmo_ring_points(widget.gizmo_axes[2])[6]
    proj = widget._project_joint(tuple(point))
    assert proj is not None
    assert widget._pick_gizmo_axis(proj[0], proj[1]) == 2
    # Far from every ring: no grab
    assert widget._pick_gizmo_axis(5.0, 5.0) == -1


# ---------------------------------------------------------------------------
# Part 2: skeleton edit persistence on a real monster file
# ---------------------------------------------------------------------------

MONSTER = "c0m001.dat"

pytestmark_realfile = pytest.mark.ff8data(f"extracted_files/battle/{MONSTER}")


@pytest.fixture()
def manager(qapp):
    return IfritManager(str(PROJECT_ROOT / "FF8GameData"))


def _load_work_copy(manager, tmp_path):
    work = tmp_path / "work.dat"
    shutil.copy(BATTLE_DIR / MONSTER, work)
    manager.init_from_file(str(work))
    return work


def _all_rotations_raw(anim):
    return [
        [tuple(int(axis.get_rotate_raw()) for axis in bone_rot)
         for bone_rot in frame.rotation_vector_data]
        for frame in anim.frames
    ]


@pytestmark_realfile
def test_rotation_edit_touches_only_edited_frame_and_survives_save(manager, tmp_path):
    work = _load_work_copy(manager, tmp_path)

    anim_section = manager.enemy.animation_data
    anim_id = next(i for i, a in enumerate(anim_section.animations) if len(a.frames) >= 3)
    anim = anim_section.animations[anim_id]
    frame_id, bone_id = 1, 1

    before = _all_rotations_raw(anim)

    # +90 degrees on X: raw +1024, a delta far larger than the couple of bits
    # the original file reserved for this frame-to-frame step
    rot = anim.frames[frame_id].rotation_vector_data[bone_id]
    manager.set_animation_frame_bone_rotation(
        anim_id, frame_id, bone_id,
        rot[0].get_rotate_deg() + 90.0,
        rot[1].get_rotate_deg(),
        rot[2].get_rotate_deg())

    after = _all_rotations_raw(anim)

    # Only (frame_id, bone_id, axis X) changed in memory: frames store
    # absolute values, so editing one frame does not move the others
    assert (after[frame_id][bone_id][0] - before[frame_id][bone_id][0]) % 4096 == 1024
    for f, (frame_before, frame_after) in enumerate(zip(before, after)):
        for b, (bone_before, bone_after) in enumerate(zip(frame_before, frame_after)):
            if (f, b) != (frame_id, bone_id):
                assert bone_after == bone_before, f"frame {f} bone {b} moved"

    # The delta re-encoding must reproduce the exact same absolute values
    manager.save_file(str(work))
    manager.init_from_file(str(work))
    reloaded = _all_rotations_raw(manager.enemy.animation_data.animations[anim_id])
    assert [[tuple(r % 4096 for r in bone) for bone in frame] for frame in reloaded] == \
           [[tuple(r % 4096 for r in bone) for bone in frame] for frame in after]


@pytestmark_realfile
def test_bone_length_edit_applies_and_survives_save(manager, tmp_path):
    """Mirror the Ctrl+drag flow: per-move previews (only the displayed frame
    is recomputed), then the final set_bone_length on release (every frame),
    then save + reload."""
    work = _load_work_copy(manager, tmp_path)

    bone_id = 1
    old_length = manager.enemy.bone_data.bones[bone_id].get_size()
    new_length = old_length + 0.5

    manager.set_bone_length_preview(bone_id, old_length + 0.25, anim_id=0, frame_id=0)
    manager.set_bone_length_preview(bone_id, new_length, anim_id=0, frame_id=0)
    manager.set_bone_length(bone_id, new_length)

    applied = manager.enemy.bone_data.bones[bone_id].get_size()
    assert applied == pytest.approx(new_length, abs=1.0 / 2048)

    # The final full recompute must leave the previewed frame identical to a
    # from-scratch rebuild (previews must not leave stale matrices behind)
    frame = manager.enemy.animation_data.animations[0].frames[0]
    matrices_after_drag = [copy.deepcopy(m) for m in frame.bone_matrices]
    manager._recompute_all_animation_matrices()
    for before, after in zip(matrices_after_drag, frame.bone_matrices):
        assert before.__dict__ == after.__dict__

    manager.save_file(str(work))
    manager.init_from_file(str(work))
    assert manager.enemy.bone_data.bones[bone_id].get_size() == pytest.approx(applied)


@pytestmark_realfile
def test_gizmo_axes_match_actual_bone_rotation(manager, tmp_path):
    """The gizmo's axes must predict what set_animation_frame_bone_rotation
    really does: +10 degrees on Euler axis i moves a child joint along
    cross(axis_i, r) (right-hand rule), with the chord length of a 10-degree
    arc. This pins down both the finite-difference axis extraction and its
    sign convention."""
    _load_work_copy(manager, tmp_path)
    anim_id, frame_id = 0, 0

    lines, parents = manager.get_skeleton_lines(anim_id, frame_id)
    # A bone with a child line AND a real length: its children's joints sit
    # |size| away from the pivot, so its rotation visibly moves them (the
    # root has size 0 — its direct children's joints ARE the pivot)
    bones = manager.enemy.bone_data.bones
    bone_id = next(b for b in range(len(parents))
                   if abs(bones[b].get_size_raw()) > 200
                   and any(p == b and lines[i] is not None for i, p in enumerate(parents)))
    child = next(i for i, p in enumerate(parents) if p == bone_id and lines[i] is not None)

    center, axes = manager.get_bone_rotation_gizmo(anim_id, frame_id, bone_id)
    frame = manager.enemy.animation_data.animations[anim_id].frames[frame_id]
    start_deg = [frame.rotation_vector_data[bone_id][i].get_rotate_deg() for i in range(3)]

    tested = 0
    for axis_index in range(3):
        axis = np.array(axes[axis_index])
        p_before = np.array(manager.get_skeleton_lines(anim_id, frame_id)[0][child][1])
        radius = p_before - np.array(center)
        tangent = np.cross(axis, radius)
        if np.linalg.norm(radius) < 1e-4 or np.linalg.norm(tangent) < 0.05 * np.linalg.norm(radius):
            continue  # joint sits (almost) on the rotation axis: no motion

        new_deg = list(start_deg)
        new_deg[axis_index] += 10.0
        manager.set_animation_frame_bone_rotation(anim_id, frame_id, bone_id, *new_deg)
        p_after = np.array(manager.get_skeleton_lines(anim_id, frame_id)[0][child][1])
        manager.set_animation_frame_bone_rotation(anim_id, frame_id, bone_id, *start_deg)

        movement = p_after - p_before
        # Direction: along the tangent (cos similarity high despite the chord)
        cos_sim = float(np.dot(movement, tangent) /
                        (np.linalg.norm(movement) * np.linalg.norm(tangent)))
        assert cos_sim > 0.9, f"axis {axis_index}: moved against the gizmo axis"
        # Magnitude: chord of a 10-degree arc of radius |tangent| (= r_perp)
        expected_len = 2.0 * np.sin(np.radians(5.0)) * np.linalg.norm(tangent)
        assert np.linalg.norm(movement) == pytest.approx(expected_len, rel=0.15)
        tested += 1

    assert tested >= 2, "degenerate pose: could not exercise enough axes"


@pytestmark_realfile
def test_incremental_rotation_recompute_covers_grandchildren(manager, tmp_path):
    """Rotating a bone must re-chain its WHOLE subtree, not only its direct
    children: after an incremental edit the matrices must equal a full
    from-scratch rebuild."""
    _load_work_copy(manager, tmp_path)
    bones = manager.enemy.bone_data.bones
    parents = [b.parent_id for b in bones]
    # A bone that has at least a grandchild
    grandchild = next(c for c in range(len(bones))
                      if parents[c] != 0xFFFF and parents[parents[c]] != 0xFFFF)
    bone_id = parents[parents[grandchild]]

    frame = manager.enemy.animation_data.animations[0].frames[0]
    start = [frame.rotation_vector_data[bone_id][i].get_rotate_deg() for i in range(3)]
    manager.set_animation_frame_bone_rotation(0, 0, bone_id,
                                              start[0] + 25.0, start[1] - 10.0, start[2] + 5.0)

    snapshot = [copy.deepcopy(m) for m in frame.bone_matrices]
    manager._recompute_all_animation_matrices()
    for bone_index, (incremental, full) in enumerate(zip(snapshot, frame.bone_matrices)):
        assert incremental.__dict__ == full.__dict__, f"bone {bone_index} left stale"


@pytestmark_realfile
def test_rotation_drag_handler_applies_to_current_frame(manager, tmp_path, qapp):
    """With 'Apply to all following frames' OFF, a ring drag poses only the
    current frame and leaves the following ones alone."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(1)
    widget.bone_editor.propagate_rotation_cb.setChecked(False)

    frame = manager.enemy.animation_data.animations[0].frames[0]
    start_x = frame.rotation_vector_data[1][0].get_rotate_deg()
    other_frame_before = [int(r.get_rotate_raw())
                          for r in manager.enemy.animation_data.animations[0].frames[1].rotation_vector_data[1]]

    widget._on_bone_rotation_dragged(0, 25.0)   # drag the X ring by 25 degrees
    widget._on_bone_rotation_dragged(0, 30.0)   # keep dragging to 30 total
    widget._on_bone_rotation_drag_finished()

    end_x = frame.rotation_vector_data[1][0].get_rotate_deg()
    assert ((end_x - start_x) % 360.0) == pytest.approx(30.0, abs=0.1)
    other_frame_after = [int(r.get_rotate_raw())
                         for r in manager.enemy.animation_data.animations[0].frames[1].rotation_vector_data[1]]
    assert other_frame_after == other_frame_before


@pytestmark_realfile
def test_rotation_propagates_to_following_frames(manager, tmp_path):
    """propagate_to_next_frames shifts every following frame by the same
    turn, so the rest of the animation keeps its shape and moves along."""
    work = _load_work_copy(manager, tmp_path)
    anim_id, frame_id, bone_id = 0, 1, 1
    anim = manager.enemy.animation_data.animations[anim_id]

    before = [[int(axis.get_rotate_raw()) for axis in f.rotation_vector_data[bone_id]]
              for f in anim.frames]
    rot = anim.frames[frame_id].rotation_vector_data[bone_id]
    manager.set_animation_frame_bone_rotation(
        anim_id, frame_id, bone_id,
        rot[0].get_rotate_deg() + 90.0, rot[1].get_rotate_deg(), rot[2].get_rotate_deg(),
        propagate_to_next_frames=True)
    after = [[int(axis.get_rotate_raw()) for axis in f.rotation_vector_data[bone_id]]
             for f in anim.frames]

    # Frames before the edit: untouched
    for f in range(frame_id):
        assert after[f] == before[f]
    # The edited frame and every following one: +90 deg (raw 1024) on X only
    for f in range(frame_id, len(anim.frames)):
        assert (after[f][0] - before[f][0]) % 4096 == 1024, f"frame {f} X"
        assert (after[f][1] - before[f][1]) % 4096 == 0, f"frame {f} Y"
        assert (after[f][2] - before[f][2]) % 4096 == 0, f"frame {f} Z"
    # Propagated values stay inside the editor's spinbox range
    for f in range(frame_id + 1, len(anim.frames)):
        for axis in range(3):
            assert -2048 <= after[f][axis] < 2048

    # The whole shifted animation survives the delta re-encoding
    manager.save_file(str(work))
    manager.init_from_file(str(work))
    reloaded = [[int(axis.get_rotate_raw()) for axis in f.rotation_vector_data[bone_id]]
                for f in manager.enemy.animation_data.animations[anim_id].frames]
    for f, (expected, got) in enumerate(zip(after, reloaded)):
        for axis in range(3):
            assert (got[axis] - expected[axis]) % 4096 == 0, f"frame {f} axis {axis}"


@pytestmark_realfile
def test_propagated_rotation_keeps_relative_motion(manager, tmp_path):
    """A propagated edit must not distort the animation: the frame-to-frame
    motion of every following frame is unchanged, the whole tail is offset."""
    _load_work_copy(manager, tmp_path)
    anim_id, frame_id, bone_id = 0, 1, 1
    anim = manager.enemy.animation_data.animations[anim_id]

    def steps():
        raws = [int(f.rotation_vector_data[bone_id][0].get_rotate_raw()) for f in anim.frames]
        return [(raws[i] - raws[i - 1]) % 4096 for i in range(frame_id + 2, len(raws))]

    before = steps()
    rot = anim.frames[frame_id].rotation_vector_data[bone_id]
    manager.set_animation_frame_bone_rotation(
        anim_id, frame_id, bone_id,
        rot[0].get_rotate_deg() + 90.0, rot[1].get_rotate_deg(), rot[2].get_rotate_deg(),
        propagate_to_next_frames=True)
    assert steps() == before


@pytestmark_realfile
def test_rotation_drag_defers_propagation_to_release(manager, tmp_path, qapp):
    """While the mouse moves, only the displayed frame is recomputed: the
    following frames must not move until the drag is released (and then they
    must land on the drag's total)."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(1)

    frames = manager.enemy.animation_data.animations[0].frames
    last_before = int(frames[-1].rotation_vector_data[1][0].get_rotate_raw())

    for total in (10.0, 20.0, 30.0):
        widget._on_bone_rotation_dragged(0, total)
        # mid-drag: the tail is untouched, no work wasted on it
        assert int(frames[-1].rotation_vector_data[1][0].get_rotate_raw()) == last_before

    widget._on_bone_rotation_drag_finished()
    # released: the tail moved by the drag total (30 deg), once
    last_after = int(frames[-1].rotation_vector_data[1][0].get_rotate_raw())
    assert (last_after - last_before) % 4096 == pytest.approx(round(30.0 * 4096 / 360.0), abs=2)


@pytestmark_realfile
def test_drag_result_matches_a_direct_edit(manager, tmp_path, qapp):
    """A dragged rotation and the same rotation typed in one go must produce
    exactly the same animation — the preview/release split must not drift."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    def raws():
        return [[int(a.get_rotate_raw()) for a in f.rotation_vector_data[1]]
                for f in manager.enemy.animation_data.animations[0].frames]

    # via the ring drag (many mouse-moves, then release)
    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(1)
    for total in (3.0, 11.0, 24.0, 40.0, 45.0):
        widget._on_bone_rotation_dragged(1, total)   # Y ring
    widget._on_bone_rotation_drag_finished()
    dragged = raws()

    # via one direct edit of the same 45 degrees
    _load_work_copy(manager, tmp_path)
    rot = manager.enemy.animation_data.animations[0].frames[0].rotation_vector_data[1]
    start_y = rot[1].get_rotate_deg()
    manager.set_animation_frame_bone_rotation(
        0, 0, 1, rot[0].get_rotate_deg(),
        ((start_y + 45.0 + 180.0) % 360.0) - 180.0, rot[2].get_rotate_deg(),
        propagate_to_next_frames=True)
    typed = raws()

    assert dragged == typed


@pytestmark_realfile
def test_propagated_drag_shifts_tail_by_drag_total(manager, tmp_path, qapp):
    """A ring drag with the checkbox ON (its default) shifts the following
    frames by the drag's TOTAL, not by the sum of each mouse step."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(1)
    assert widget.bone_editor.propagate_rotation_cb.isChecked(), "must default to ON"

    frames = manager.enemy.animation_data.animations[0].frames
    last_before = int(frames[-1].rotation_vector_data[1][0].get_rotate_raw())

    for total in (10.0, 20.0, 25.0, 30.0):   # one call per mouse-move
        widget._on_bone_rotation_dragged(0, total)
    widget._on_bone_rotation_drag_finished()

    last_after = int(frames[-1].rotation_vector_data[1][0].get_rotate_raw())
    # 30 degrees total = 341 raw, NOT 10+20+25+30
    assert (last_after - last_before) % 4096 == pytest.approx(round(30.0 * 4096 / 360.0), abs=2)


@pytestmark_realfile
def test_add_bone_extends_skeleton_and_survives_save(manager, tmp_path):
    """add_bone must grow the bone section AND every animation frame, without
    touching the existing bones' animation data, and survive the re-encoded
    save + reload."""
    work = _load_work_copy(manager, tmp_path)
    nb_before = len(manager.enemy.bone_data.bones)
    rotations_before = _all_rotations_raw(manager.enemy.animation_data.animations[0])

    new_id = manager.add_bone(parent_id=1, length=-0.75)

    assert new_id == nb_before
    assert manager.enemy.bone_data.nb_bone == nb_before + 1
    for anim in manager.enemy.animation_data.animations:
        for frame in anim.frames:
            assert len(frame.rotation_vector_data) == nb_before + 1
            assert len(frame.bone_matrices) == nb_before + 1
    # The new bone hangs from bone 1's joint in the viewer
    lines, parents = manager.get_skeleton_lines(0, 0)
    assert parents[new_id] == 1
    assert lines[new_id] is not None

    manager.save_file(str(work))
    manager.init_from_file(str(work))

    bones = manager.enemy.bone_data.bones
    assert len(bones) == nb_before + 1
    assert bones[new_id].parent_id == 1
    assert bones[new_id].get_size() == pytest.approx(-0.75, abs=1.0 / 2048)
    reloaded = _all_rotations_raw(manager.enemy.animation_data.animations[0])
    for frame_before, frame_after in zip(rotations_before, reloaded):
        # existing bones keep their exact animation, the new bone is all zero
        assert frame_after[:nb_before] == [tuple(r % 4096 for r in b) for b in
                                           frame_before] or frame_after[:nb_before] == frame_before
        assert all(r % 4096 == 0 for r in frame_after[new_id])


@pytestmark_realfile
def test_reset_skeleton_keeps_only_root_and_survives_save(manager, tmp_path):
    """reset_skeleton leaves a single root bone, re-skins the whole mesh to
    it (including the raw section-2 bytes the save uses), and the file still
    loads and animates."""
    work = _load_work_copy(manager, tmp_path)
    nb_vertices = len(manager.enemy.geometry_data.get_vertices())

    manager.reset_skeleton()

    assert len(manager.enemy.bone_data.bones) == 1
    assert manager.enemy.bone_data.nb_bone == 1
    assert manager.enemy.bone_data.bones[0].parent_id == 0xFFFF
    assert all(vd.bone_id == 0
               for obj in manager.enemy.geometry_data.object_data
               for vd in obj.vertices_data)
    assert len(manager.get_animated_vertices(0, 0)) == nb_vertices

    manager.save_file(str(work))
    manager.init_from_file(str(work))

    assert len(manager.enemy.bone_data.bones) == 1
    assert all(vd.bone_id == 0
               for obj in manager.enemy.geometry_data.object_data
               for vd in obj.vertices_data)
    assert len(manager.get_animated_vertices(0, 0)) == nb_vertices
    # And a new skeleton can be built on top of the fresh root
    new_id = manager.add_bone(parent_id=0)
    assert new_id == 1
    lines, parents = manager.get_skeleton_lines(0, 0)
    assert parents[new_id] == 0


@pytestmark_realfile
def test_add_bone_shortcut_adds_child_of_selected(manager, tmp_path, qapp):
    """The B shortcut adds a child to the selected joint and selects the new
    bone — only while the skeleton is displayed."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(2)
    nb_before = len(manager.enemy.bone_data.bones)

    widget._on_add_bone_shortcut()          # skeleton hidden: must do nothing
    assert len(manager.enemy.bone_data.bones) == nb_before

    widget.set_show_skeleton(True)
    widget._on_add_bone_shortcut()
    bones = manager.enemy.bone_data.bones
    assert len(bones) == nb_before + 1
    assert bones[-1].parent_id == 2
    assert widget.bone_editor.bone_spin.value() == nb_before  # new bone selected


@pytestmark_realfile
def test_length_drag_outward_extends_bone(manager, tmp_path, qapp):
    """Dragging outward (positive delta along the drawn bone) must make the
    bone VISUALLY longer. FF8 sizes are negative (child = parent + Z*size),
    so 'longer' means the stored size moves away from zero, not upward."""
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    _load_work_copy(manager, tmp_path)
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    widget.bone_editor.bone_spin.setValue(1)

    start = manager.enemy.bone_data.bones[1].get_size()
    assert start < 0  # the FF8 convention this test is about

    widget._on_bone_length_dragged(0.5)  # 0.5 world units outward
    widget._on_bone_length_drag_finished()

    end = manager.enemy.bone_data.bones[1].get_size()
    assert abs(end) > abs(start), "outward drag must extend the bone"
    assert end == pytest.approx(start - 0.5, abs=1.0 / 2048)
