"""End-to-end guard for the 3D editing loop: edit a model -> save -> re-open -> the 3D is the same.

Every edit the 3D tab offers (bone rotation/length/parent, per-frame rotation and squash-scale,
frame and animation authoring...) changes objects in memory, while the SAVE re-encodes those
objects into the .dat bit-stream and the RE-OPEN decodes them back. Nothing in the editor compares
the two, so any encoder/decoder mismatch shows up only as "the model looks different after
re-opening it" - which is exactly the class of regression these tests pin.

What is compared is the 3D itself, not the bytes: the posed skeleton of EVERY frame of EVERY
animation (the segments the viewer draws, and the pose every mesh vertex is skinned to), the
skinned vertices on a few sampled frames, and the static mesh (faces + UVs). A byte comparison
would be both too strict (the encoder is free to pick different storage widths) and too weak (it
says nothing about what the viewer computes from those bytes).

Edits are drawn from a SEEDED random pool, so a session is a realistic mix of edits but any
failure is reproducible by re-running the same seed. Angles are picked on the format's own
rotation grid (4096 raw units per turn), the same grid a value typed in degrees is rounded onto.

Needs the original battle files, so the whole module carries the shared @ff8data marker
(skipped automatically when extracted_files/battle is not there - see conftest.py).
"""
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from FF8GameData.dat import interpolation
from FF8GameData.dat.animsplitter import MAX_ANIMATION_ID
from FF8GameData.monsterdata import PositionType, RotationType
from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DATA_DIR = os.path.join(REPO, "FF8GameData")
BATTLE_DIR = os.path.join(REPO, "extracted_files", "battle")

# One file per shape the editor has to handle: a monster (12 sections, 35 bones, 28 animations),
# a character body (8 sections, 23 bones, 42 animations) and a weapon (9 sections, 42 animations
# on a 2-BONE skeleton - the small-skeleton edge case where "pick bone 3" is not even valid).
MODEL_FILES = {
    "monster": "c0m003.dat",
    "character": "d0c000.dat",
    "weapon": "d0w000.dat",
}

pytestmark = pytest.mark.ff8data(*(f"extracted_files/battle/{name}" for name in MODEL_FILES.values()))

# A full turn is 4096 raw units in both the frame rotations and the static bone rotations.
RAW_PER_TURN = 4096
DEGREES_PER_RAW = 360.0 / RAW_PER_TURN

# Model coordinates are in "bone size" units - a character is about 4 units tall - and the
# comparison rounds to 6 decimals, far below anything a viewer could show. It is there only to
# ignore last-bit float noise, not to tolerate a real difference.
POSITION_DECIMALS = 6


# ---------------------------------------------------------------------------
# Loading and snapshotting
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def game_data():
    """The FF8 JSON data, loaded once and shared by every manager in this module (~0.5s each)."""
    return IfritManager(GAME_DATA_DIR).game_data


def _open(path, game_data):
    """Open one model ready for the 3D view: parsed, with its bone matrices built.

    Deliberately not init_from_file(): that also runs the VincentTim texture extraction, which
    spawns tim.exe once per load and has no effect on the geometry and skeleton compared here.
    """
    manager = IfritManager(GAME_DATA_DIR, game_data=game_data)
    manager.enemy = manager.parse_file(path)
    manager._ensure_matrices()
    return manager


def _round_point(point):
    return tuple(round(value, POSITION_DECIMALS) for value in point)


def _skeleton_snapshot(manager):
    """The posed skeleton of every frame of every animation.

    One entry per frame: its bone parents and every bone segment (parent joint -> bone joint) as
    the viewer draws it. This is the whole animated pose - the mesh is only these matrices applied
    to static vertices - so any lost, truncated or misplaced edit shows up here.
    """
    manager._ensure_matrices()
    snapshot = []
    for anim_id, anim in enumerate(manager.enemy.animation_data.animations):
        for frame_id in range(anim.get_nb_frame()):
            lines, parents = manager.get_skeleton_lines(anim_id, frame_id)
            segments = tuple(None if line is None else (_round_point(line[0]), _round_point(line[1]))
                             for line in lines)
            snapshot.append((anim_id, frame_id, tuple(parents), segments))
    return snapshot


def _sample_frames(manager, nb_samples=4):
    """A few (anim_id, frame_id) spread over the file, for the expensive per-vertex checks."""
    all_frames = [(anim_id, frame_id)
                  for anim_id, anim in enumerate(manager.enemy.animation_data.animations)
                  for frame_id in range(anim.get_nb_frame())]
    if len(all_frames) <= nb_samples:
        return all_frames
    step = len(all_frames) // nb_samples
    return [all_frames[i * step] for i in range(nb_samples)]


def _vertices_snapshot(manager, frames):
    """The skinned mesh vertices on the given frames - the actual points the viewer draws."""
    manager._ensure_matrices()
    return [tuple(_round_point(vertex) for vertex in manager.get_animated_vertices(anim_id, frame_id))
            for anim_id, frame_id in frames]


def _mesh_snapshot(manager):
    """The static mesh: faces with their UVs and the flat-coloured ones. Unchanged by animation
    edits, but re-skinning (reset_skeleton) rewrites section 2, so it is worth pinning too."""
    geometry = manager.enemy.geometry_data
    return (tuple(_round_point(vertex) for vertex in geometry.get_vertices()),
            tuple(geometry.get_triangles_with_uv(include_hidden=True)),
            tuple(geometry.get_quads_with_uv(include_hidden=True)),
            len(geometry.get_colored_triangles_with_color(include_hidden=True)),
            len(geometry.get_colored_quads_with_color(include_hidden=True)))


def _assert_3d_survives_save_and_reopen(manager, tmp_path, game_data, what):
    """Save `manager` to a scratch .dat, re-open it and assert the 3D is unchanged.

    `what` describes the edits that were applied, so a failure names them.
    """
    frames = _sample_frames(manager)
    skeleton_before = _skeleton_snapshot(manager)
    vertices_before = _vertices_snapshot(manager, frames)
    mesh_before = _mesh_snapshot(manager)

    saved_path = str(tmp_path / "saved.dat")
    manager.save_file(saved_path)
    reopened = _open(saved_path, game_data)

    skeleton_after = _skeleton_snapshot(reopened)
    assert len(skeleton_after) == len(skeleton_before), (
        f"after {what}: the file re-opened with {len(skeleton_after)} frames "
        f"instead of {len(skeleton_before)}")
    differing = [(before[0], before[1])
                 for before, after in zip(skeleton_before, skeleton_after) if before != after]
    assert not differing, (
        f"after {what}: {len(differing)} frame(s) are posed differently once re-opened, "
        f"first (anim {differing[0][0]}, frame {differing[0][1]})")

    assert _vertices_snapshot(reopened, frames) == vertices_before, (
        f"after {what}: the skinned mesh moved once re-opened")
    assert _mesh_snapshot(reopened) == mesh_before, (
        f"after {what}: the static mesh changed once re-opened")
    return reopened


# ---------------------------------------------------------------------------
# The random edits
# ---------------------------------------------------------------------------

def _on_grid_degrees(rng, max_turn_fraction=0.25):
    """A rotation the format can store EXACTLY: a whole number of raw units.

    Rotations are stored as 4096 units per turn, so a value typed in degrees is rounded on save
    and comes back slightly different. Staying on the grid keeps that (real, separately tested)
    quantization out of the way, so these tests fail only on an actually lost or corrupted edit.
    """
    max_raw = round(max_turn_fraction * RAW_PER_TURN)
    return rng.randint(-max_raw, max_raw) * DEGREES_PER_RAW


def _random_bone(manager, rng):
    return rng.randrange(len(manager.enemy.bone_data.bones))


def _random_frame(manager, rng):
    anim_id = rng.randrange(len(manager.enemy.animation_data.animations))
    return anim_id, rng.randrange(manager.enemy.animation_data.animations[anim_id].get_nb_frame())


# Every edit below applies one change and returns a short description of it, or None when the
# loaded file cannot take it (a 2-bone weapon has no bone to re-parent, a 1-frame animation no
# frame to delete...). Used both one at a time and mixed into a random session.

def _edit_frame_rotation(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    bone_id = _random_bone(manager, rng)
    angles = [_on_grid_degrees(rng) for _ in range(3)]
    manager.set_animation_frame_bone_rotation(anim_id, frame_id, bone_id, *angles)
    return f"rotating bone {bone_id} on animation {anim_id} frame {frame_id}"


def _edit_frame_rotation_propagated(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    bone_id = _random_bone(manager, rng)
    angles = [_on_grid_degrees(rng) for _ in range(3)]
    manager.set_animation_frame_bone_rotation(anim_id, frame_id, bone_id, *angles,
                                              propagate_to_next_frames=True)
    return f"rotating bone {bone_id} from animation {anim_id} frame {frame_id} onwards"


def _edit_bone_length(manager, rng):
    bone_id = _random_bone(manager, rng)
    # FF8 bone sizes are negative (the child joint sits at parent + Z * size)
    length = -round(rng.uniform(0.2, 3.0), 3)
    manager.set_bone_length(bone_id, length)
    return f"setting bone {bone_id} length to {length}"


def _edit_bone_static_rotation(manager, rng):
    bone_id = _random_bone(manager, rng)
    angles = [_on_grid_degrees(rng) for _ in range(3)]
    manager.set_bone_static_rotation(bone_id, *angles)
    return f"setting the base rotation of bone {bone_id}"


def _edit_bone_parent(manager, rng):
    if len(manager.enemy.bone_data.bones) < 3:
        return None
    # A bone is only ever re-parented to an EARLIER one: FF8 skeletons store children after their
    # parent and the matrix recompute walks them in that order (see _recompute_frame_matrices).
    bone_id = rng.randrange(2, len(manager.enemy.bone_data.bones))
    parent_id = rng.randrange(bone_id)
    manager.set_bone_parent(bone_id, parent_id)
    return f"re-parenting bone {bone_id} to bone {parent_id}"


def _edit_add_bone(manager, rng):
    parent_id = _random_bone(manager, rng)
    new_id = manager.add_bone(parent_id, -round(rng.uniform(0.2, 2.0), 3))
    return f"adding bone {new_id} under bone {parent_id}"


def _edit_frame_bone_scale(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    bone_id = _random_bone(manager, rng)
    # Scales are stored as 1024 raw = 1.0, so 3 decimals stay representable
    factors = [round(rng.uniform(0.25, 3.0), 3) for _ in range(3)]
    manager.set_animation_frame_bone_scale(anim_id, frame_id, bone_id, *factors)
    return f"scaling bone {bone_id} on animation {anim_id} frame {frame_id}"


def _edit_frame_scale_mode(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    frame = manager.enemy.animation_data.animations[anim_id].frames[frame_id]
    enabled = frame.mode_bit != 1
    manager.set_animation_frame_scale_mode(anim_id, frame_id, enabled)
    return f"turning the scale mode {'on' if enabled else 'off'} on animation {anim_id} frame {frame_id}"


def _edit_move_frame_position(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    axis = rng.randrange(3)
    # The root position is a raw integer per axis: moving it by raw units is lossless
    offset = rng.randint(-500, 500)
    manager.enemy.animation_data.animations[anim_id].frames[frame_id].position[axis].move_raw(offset)
    return f"moving animation {anim_id} frame {frame_id} by {offset} on axis {axis}"


def _edit_duplicate_frame(manager, rng):
    anim_id, frame_id = _random_frame(manager, rng)
    new_frame_id = manager.duplicate_animation_frame(anim_id, frame_id)
    return f"duplicating animation {anim_id} frame {frame_id} into frame {new_frame_id}"


def _edit_delete_frame(manager, rng):
    candidates = [anim_id for anim_id, anim in enumerate(manager.enemy.animation_data.animations)
                  if anim.get_nb_frame() > 1]
    if not candidates:
        return None
    anim_id = rng.choice(candidates)
    frame_id = rng.randrange(manager.enemy.animation_data.animations[anim_id].get_nb_frame())
    manager.delete_animation_frame(anim_id, frame_id)
    return f"deleting animation {anim_id} frame {frame_id}"


def _edit_interpolate_frames(manager, rng):
    candidates = [anim_id for anim_id, anim in enumerate(manager.enemy.animation_data.animations)
                  if anim.get_nb_frame() > 1]
    if not candidates:
        return None
    anim_id = rng.choice(candidates)
    nb_frames = manager.enemy.animation_data.animations[anim_id].get_nb_frame()
    frame_a = rng.randrange(nb_frames - 1)
    nb_insert = rng.randint(1, 3)
    # Any of the curves the editor offers: a smoother one produces bigger frame-to-frame jumps
    # than linear, which the delta encoder has to be able to store
    mode = rng.choice(sorted(interpolation.ALL_MODES))
    manager.interpolate_between_frames(anim_id, frame_a, frame_a + 1, nb_insert, mode=mode)
    return (f"inserting {nb_insert} '{mode}' interpolated frame(s) after animation {anim_id} "
            f"frame {frame_a}")


def _edit_copy_paste_frames(manager, rng):
    source_id, start = _random_frame(manager, rng)
    end = min(start + rng.randint(0, 2),
              manager.enemy.animation_data.animations[source_id].get_nb_frame() - 1)
    frames = manager.copy_animation_frames(source_id, start, end)
    target_id, at_index = _random_frame(manager, rng)
    nb_pasted = manager.paste_animation_frames(target_id, at_index, frames)
    return (f"pasting {nb_pasted} frame(s) of animation {source_id} "
            f"into animation {target_id} after frame {at_index}")


def _edit_new_animation_from_range(manager, rng):
    # A bare sequence op code IS the animation id, so the format stops at 128 animations
    if manager.enemy.animation_data.nb_animations > MAX_ANIMATION_ID:
        return None
    source_id, start = _random_frame(manager, rng)
    end = min(start + rng.randint(0, 4),
              manager.enemy.animation_data.animations[source_id].get_nb_frame() - 1)
    new_id = manager.create_animation_from_frame_range(source_id, start, end)
    return f"creating animation {new_id} from animation {source_id} frames {start}-{end}"


def _edit_delete_last_animation(manager, rng):
    last_id = manager.enemy.animation_data.nb_animations - 1
    if not manager.delete_animation(last_id):
        return None
    return f"deleting animation {last_id}"


def _edit_reset_skeleton(manager, rng):
    if len(manager.enemy.bone_data.bones) < 2:
        return None
    manager.reset_skeleton()
    return "resetting the skeleton to its root bone"


EDIT_KINDS = {
    "frame rotation": _edit_frame_rotation,
    "frame rotation propagated": _edit_frame_rotation_propagated,
    "bone length": _edit_bone_length,
    "bone static rotation": _edit_bone_static_rotation,
    "bone parent": _edit_bone_parent,
    "add bone": _edit_add_bone,
    "frame bone scale": _edit_frame_bone_scale,
    "frame scale mode": _edit_frame_scale_mode,
    "frame position": _edit_move_frame_position,
    "duplicate frame": _edit_duplicate_frame,
    "delete frame": _edit_delete_frame,
    "interpolate frames": _edit_interpolate_frames,
    "copy paste frames": _edit_copy_paste_frames,
    "new animation from range": _edit_new_animation_from_range,
    "delete animation": _edit_delete_last_animation,
    "reset skeleton": _edit_reset_skeleton,
}


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_kind", sorted(MODEL_FILES))
def test_saving_an_untouched_model_keeps_the_3d_identical(model_kind, tmp_path, game_data):
    """Baseline: without any edit, save + re-open must change nothing at all. If this fails, every
    other failure in this module is about the plain save path, not about the edits."""
    manager = _open(os.path.join(BATTLE_DIR, MODEL_FILES[model_kind]), game_data)
    _assert_3d_survives_save_and_reopen(manager, tmp_path, game_data, "no edit at all")


@pytest.mark.parametrize("model_kind", sorted(MODEL_FILES))
@pytest.mark.parametrize("edit_name", sorted(EDIT_KINDS))
def test_one_edit_survives_save_and_reopen(edit_name, model_kind, tmp_path, game_data):
    """Each kind of edit on its own, so a failure names the culprit instead of a random mix."""
    manager = _open(os.path.join(BATTLE_DIR, MODEL_FILES[model_kind]), game_data)
    rng = random.Random(f"{edit_name}/{model_kind}")
    description = EDIT_KINDS[edit_name](manager, rng)
    if description is None:
        pytest.skip(f"{MODEL_FILES[model_kind]} is too small for '{edit_name}'")
    _assert_3d_survives_save_and_reopen(manager, tmp_path, game_data, description)


@pytest.mark.parametrize("model_kind", sorted(MODEL_FILES))
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_random_edit_session_survives_save_and_reopen(seed, model_kind, tmp_path, game_data):
    """A realistic session: several random edits of random kinds, one after the other, then save
    and re-open. Catches what a single edit cannot - edits interacting through the frame delta
    chain, a bone added then rotated, an animation created then re-timed..."""
    manager = _open(os.path.join(BATTLE_DIR, MODEL_FILES[model_kind]), game_data)
    rng = random.Random(seed)
    applied = []
    for _ in range(8):
        edit_name = rng.choice(sorted(EDIT_KINDS))
        description = EDIT_KINDS[edit_name](manager, rng)
        if description is not None:
            applied.append(description)
    assert applied, "the random session applied no edit at all"
    _assert_3d_survives_save_and_reopen(manager, tmp_path, game_data,
                                        f"seed {seed}: " + ", then ".join(applied))


@pytest.mark.parametrize("model_kind", sorted(MODEL_FILES))
def test_two_save_reopen_cycles_are_stable(model_kind, tmp_path, game_data):
    """Saving what was just re-opened must not drift: the second file's 3D matches the first's.
    A rounding that only bites on re-encoding would slowly deform a model edited over several
    sessions, which one round trip does not show."""
    manager = _open(os.path.join(BATTLE_DIR, MODEL_FILES[model_kind]), game_data)
    rng = random.Random(f"two-cycles/{model_kind}")
    for edit_name in ("frame rotation", "bone length", "duplicate frame", "frame bone scale"):
        EDIT_KINDS[edit_name](manager, rng)

    reopened = _assert_3d_survives_save_and_reopen(manager, tmp_path, game_data, "the first save")
    second_path = str(tmp_path / "saved_again.dat")
    reopened.save_file(second_path)
    twice_reopened = _open(second_path, game_data)

    assert _skeleton_snapshot(twice_reopened) == _skeleton_snapshot(reopened), (
        "the model drifted on the second save/re-open cycle")


def _open_in_editor(path, name):
    """The real UI path: the multi-file editor with one file open, its pane fully built (3D
    viewer included). Returns (widget, pane, viewer)."""
    settings = QSettings("test", f"3d_roundtrip_{name}")
    widget = IfritMonsterWidget(settings=settings, icon_path=os.path.join(REPO, "Resources"),
                                game_data_folder=GAME_DATA_DIR)
    widget.show()
    widget._build_session([path])
    _APP.processEvents()
    pane = widget._files[0]['pane']
    return widget, pane, pane._3d_widget


def _viewer_snapshot(viewer):
    """What the 3D viewer is actually showing right now: the vertices and skeleton segments it
    last pushed to the GL widget."""
    return ([_round_point(vertex) for vertex in viewer.gl_widget.vertices],
            [None if line is None else (_round_point(line[0]), _round_point(line[1]))
             for line in viewer.gl_widget.skeleton_lines],
            list(viewer.gl_widget.bone_parents))


def test_edits_made_in_the_3d_tab_come_back_after_a_real_save_and_reopen(tmp_path, game_data):
    """The whole user-visible loop, through the widgets rather than the manager: edit in the 3D
    tab, hit Save, open the saved file again, and the viewer draws the same thing.

    Goes through the editor's own handlers and IfritFilePane.save() (which first folds the pending
    per-tab edits into the model), so it also covers the commit step the manager-level tests skip.
    """
    working_copy = tmp_path / "c0m003.dat"
    working_copy.write_bytes(open(os.path.join(BATTLE_DIR, MODEL_FILES["monster"]), "rb").read())

    widget, pane, viewer = _open_in_editor(str(working_copy), "before")
    viewer.set_animation(0)
    viewer.set_frame(1)
    # The same slots the bone editor's spin boxes and the in-view dragging are wired to.
    # The rotation is a big one (~90 deg, on the format's grid): a small turn fits whatever
    # storage width the frame already had, so it would still round-trip with a broken re-encoder.
    viewer._on_bone_length_changed(4, -1.25)
    viewer._on_animation_rotation_changed(0, 1, 3, 1024 * DEGREES_PER_RAW,
                                          -900 * DEGREES_PER_RAW, 1500 * DEGREES_PER_RAW)
    viewer._on_animation_scale_changed(0, 1, 3, 1.5, 0.75, 2.0)
    viewer._on_bone_parent_changed(6, 2)
    viewer.update_skeleton()
    viewer.update_animated_mesh()
    _APP.processEvents()
    before = _viewer_snapshot(viewer)

    pane.save()
    assert pane.dirty is False

    _, _, reopened_viewer = _open_in_editor(str(working_copy), "after")
    reopened_viewer.set_animation(0)
    reopened_viewer.set_frame(1)
    _APP.processEvents()

    assert _viewer_snapshot(reopened_viewer) == before, (
        "the 3D view of the re-opened file differs from what was on screen when it was saved")


def test_the_root_position_uses_the_same_axis_directions_as_the_mesh():
    """The skeleton's per-frame root position (where the whole model stands) is expressed in the
    same space as the posed vertices, on all three axes.

    Z used to be the exception: X and Y are mirrored into vertex space and Z was mirrored too, so
    the forward/backward axis ran the opposite way in game to what the editor showed. The mirror
    now lives in PositionType.AXIS_SCALE and nowhere else. The stored raw value is untouched -
    this is a display/edit convention, not a change to the file format.
    """
    pos_x, pos_y, pos_z = (PositionType(0, 1000, axis=axis) for axis in range(3))

    assert pos_x.get_pos_world() == pos_y.get_pos_world()
    assert pos_z.get_pos_world() == -pos_x.get_pos_world()   # Z alone is not mirrored
    assert pos_z.get_pos_world() > 0                          # +raw Z moves along the mesh's +Z
    assert pos_z.get_pos_raw() == 1000                        # nothing changed on disk

    # Typing a world position back gives the raw value it came from, on every axis
    for position in (pos_x, pos_y, pos_z):
        world = position.get_pos_world()
        position.set_pos_world(world)
        assert position.get_pos_raw() == 1000


def test_the_frame_position_editor_moves_the_model_the_way_it_was_typed(tmp_path, game_data):
    """The forward/backward axis end to end: type a root position in the frame-position tab, the
    viewer moves the model by exactly that, and a save + re-open gives it back unchanged.

    Pins the direction too - a positive Z must stay positive all the way to the GL translation -
    so the axis cannot silently flip back to mirroring the mesh."""
    working_copy = tmp_path / "c0m003.dat"
    working_copy.write_bytes(open(os.path.join(BATTLE_DIR, MODEL_FILES["monster"]), "rb").read())

    widget, pane, viewer = _open_in_editor(str(working_copy), "frame_position")
    viewer.set_animation(0)
    viewer.set_frame(0)
    # 204.8 raw units per world unit, so these are whole raw values (2048 / -1024 / 4096)
    typed = (10.0, -5.0, 20.0)
    viewer.on_frame_position_changed(0, 0, *typed)
    _APP.processEvents()

    assert viewer.gl_widget.model_translation == pytest.approx(typed), (
        "the viewer does not move the model by the position that was typed")

    pane.save()
    reopened = _open(str(working_copy), game_data)
    frame = reopened.enemy.animation_data.animations[0].frames[0]
    assert [frame.position[axis].get_pos_world() for axis in range(3)] == pytest.approx(typed), (
        "the root position came back different after a save and re-open")


def _rotation_raw_values(manager):
    """Every stored per-frame bone rotation, as the raw integers the file actually holds."""
    return [[[int(rotation.get_rotate_raw()) for rotation in bone]
             for bone in frame.rotation_vector_data]
            for anim in manager.enemy.animation_data.animations
            for frame in anim.frames]


@pytest.mark.parametrize("model_kind", sorted(MODEL_FILES))
def test_a_rotation_typed_in_degrees_is_shown_exactly_as_it_will_be_saved(
        model_kind, tmp_path, game_data):
    """A rotation typed in plain degrees cannot be stored exactly - the format holds 4096 steps per
    turn, so 30 deg is not representable - but the VIEWER must still show the pose that will be
    saved, not the one that was typed.

    RotationType used to keep the typed degrees next to the rounded raw value and pose the model
    from the typed ones, so the model silently shifted the first time the file was re-opened. It
    now derives the degrees from the rounded raw value (RotationType.rotate_deg), which makes this
    an exact round trip like every other edit - hence the plain equality below and not a tolerance.
    """
    path = os.path.join(BATTLE_DIR, MODEL_FILES[model_kind])
    manager = _open(path, game_data)
    bone_id = min(3, len(manager.enemy.bone_data.bones) - 1)
    # Deliberately off-grid values: 30 deg is 341.33 raw units, 45 deg is 512 exactly
    manager.set_animation_frame_bone_rotation(0, 0, bone_id, 30.0, -12.5, 45.0)

    saved_path = str(tmp_path / "typed_degrees.dat")
    manager.save_file(saved_path)
    reopened = _open(saved_path, game_data)

    assert _rotation_raw_values(reopened) == _rotation_raw_values(manager), (
        "the rotation that was stored is not the one that came back")
    assert _skeleton_snapshot(reopened) == _skeleton_snapshot(manager), (
        "the pose on screen was not the pose that got saved")


@pytest.mark.parametrize("typed_degrees", [30.0, -12.5, 0.3, 179.9])
def test_a_typed_rotation_reads_back_as_the_nearest_storable_angle(typed_degrees):
    """The rounding itself, on the data model alone: whatever is typed, reading the rotation back
    gives the angle of the raw unit it was stored on - never the typed value. Pure quantization
    (<= half a unit = 0.044 deg), and the same value the file will hold."""
    rotation = RotationType()
    rotation.rotate_deg(typed_degrees)

    raw = rotation.get_rotate_raw()
    assert raw == round(typed_degrees / DEGREES_PER_RAW)
    assert rotation.get_rotate_deg() == raw * DEGREES_PER_RAW
    assert abs(rotation.get_rotate_deg() - typed_degrees) <= DEGREES_PER_RAW / 2
