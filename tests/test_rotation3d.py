"""Blending bone poses as 3D rotations (FF8GameData/dat/rotation3d.py) and the setting that turns
it on (interpolation's shared `shortest_arc`).

The curves blend each of a bone's three angles on its own, which is exact while the two poses are
close - the fps conversion inserts a frame between two frames a fifteenth of a second apart - and
wrong once they are far apart: the same pose can be written with very different angle triples, so
the numbers travel through poses the bone never takes. The usual sight is a pair of arms leaving
through a T-pose while morphing from "held forward" to "down at the side".

Two things are checked here, in this order:
  * the geometry itself, against Matrix4x4 - this module claims to know the engine's own Euler
    convention, and that claim is worth testing rather than believing;
  * what the setting changes in an inserted frame: the poses it goes through, and the fact that it
    changes nothing else (the keyframes, the frame count, the positions and scales).
"""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from FF8GameData.dat import interpolation, rotation3d
from FF8GameData.monsterdata import (Animation, AnimationFrame, Bone, Matrix4x4, PositionType,
                                     RotationType)

RAW_PER_TURN = rotation3d.RAW_PER_TURN

# A spread of poses: neutral, one axis at a time, mixed, and the gimbal singularity (X on a
# quarter turn, where the Y and Z axes point at each other).
POSE_LIST = [
    (0, 0, 0),
    (500, 0, 0), (0, 500, 0), (0, 0, 500),
    (-1300, 800, 2000), (2047, -2047, 1024), (123, -456, 789),
    (1024, 700, -700), (-1024, 300, 1900),
    (2048, 0, 0), (0, 2048, 0), (0, 0, 2048),
]


def engine_matrix(pose):
    """The 3x3 the engine builds, taken from Matrix4x4 the way set_bone_matrix does it."""
    degrees = [raw * 360.0 / RAW_PER_TURN for raw in pose]
    matrix = Matrix4x4.MultiplyColumnMajor(Matrix4x4.CreateRotationY(-degrees[1]),
                                           Matrix4x4.CreateRotationX(-degrees[0]))
    matrix = Matrix4x4.MultiplyColumnMajor(Matrix4x4.CreateRotationZ(-degrees[2]), matrix)
    return [[matrix.M11, matrix.M12, matrix.M13],
            [matrix.M21, matrix.M22, matrix.M23],
            [matrix.M31, matrix.M32, matrix.M33]]


def biggest_gap(matrix_a, matrix_b) -> float:
    return max(abs(matrix_a[row][column] - matrix_b[row][column])
               for row in range(3) for column in range(3))


# ---------------------------------------------------------------------------
# The geometry: the same rotation the engine builds, and a way back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pose", POSE_LIST)
def test_the_matrix_is_the_one_the_engine_builds(pose):
    """Not "a" rotation convention: the one AnimationFrame.set_bone_matrix uses, which is what
    makes the blend describe the pose the model is actually in."""
    assert biggest_gap(rotation3d.euler_raw_to_matrix(pose), engine_matrix(pose)) < 1e-9


@pytest.mark.parametrize("pose", POSE_LIST)
def test_a_pose_survives_the_trip_through_the_matrix(pose):
    """Angles -> matrix -> angles has to come back to the SAME POSE. Not necessarily the same
    three numbers: several triples describe one pose and the way back picks the handiest."""
    back = rotation3d.matrix_to_euler_raw(rotation3d.euler_raw_to_matrix(pose), pose)
    assert biggest_gap(rotation3d.euler_raw_to_matrix(back), engine_matrix(pose)) < 1e-6


@pytest.mark.parametrize("pose", POSE_LIST)
def test_the_angles_come_back_written_next_to_the_pose_asked_for(pose):
    """Each frame is stored as a delta from the previous one, so of the many triples describing
    one pose the one near the pose we came from is the one that costs the fewest bits."""
    back = rotation3d.matrix_to_euler_raw(rotation3d.euler_raw_to_matrix(pose), pose)
    assert all(abs(back[axis] - pose[axis]) <= RAW_PER_TURN // 2 for axis in range(3))


def test_a_pose_written_a_whole_turn_away_is_the_same_pose():
    plain = rotation3d.euler_raw_to_matrix((300, -200, 100))
    turned = rotation3d.euler_raw_to_matrix((300 + RAW_PER_TURN, -200 - RAW_PER_TURN, 100))
    assert biggest_gap(plain, turned) < 1e-9


# ---------------------------------------------------------------------------
# The blend itself
# ---------------------------------------------------------------------------

def test_the_ends_of_the_blend_are_the_two_poses():
    pose_a, pose_b = (100, -400, 250), (-900, 1500, -1200)
    for ratio, expected in ((0.0, pose_a), (1.0, pose_b)):
        blended = rotation3d.blend_euler_raw(pose_a, pose_b, ratio)
        assert biggest_gap(rotation3d.euler_raw_to_matrix(blended),
                           rotation3d.euler_raw_to_matrix(expected)) < 1e-6


def test_the_bone_turns_at_a_constant_speed_around_one_axis():
    """The point of the arc: the turn is split evenly, so half way is half the angle - which is
    what makes the speed of the motion the curve's business and nothing else's."""
    pose_a, pose_b = (0, 0, 0), (-1300, 800, 2000)
    matrix_a = rotation3d.euler_raw_to_matrix(pose_a)
    matrix_b = rotation3d.euler_raw_to_matrix(pose_b)

    def angle_from_a(matrix):
        relative = rotation3d._multiply(rotation3d._transpose(matrix_a), matrix)
        return rotation3d._axis_angle(relative)[1]

    full = angle_from_a(matrix_b)
    for ratio in (0.25, 0.5, 0.75):
        blended = rotation3d.blend_euler_raw(pose_a, pose_b, ratio)
        assert angle_from_a(rotation3d.euler_raw_to_matrix(blended)) == pytest.approx(
            full * ratio, abs=1e-3)


def test_the_turn_is_never_made_the_long_way_round():
    """Whatever the numbers say - here a pose written a whole turn plus an eighth away from the
    other - the bone takes the eighth, so no frame is ever inserted on the far side."""
    pose_a = (0, 0, 0)
    eighth = RAW_PER_TURN // 8
    pose_b = (0, RAW_PER_TURN + eighth, 0)
    half_way = rotation3d.blend_euler_raw(pose_a, pose_b, 0.5)
    assert biggest_gap(rotation3d.euler_raw_to_matrix(half_way),
                       rotation3d.euler_raw_to_matrix((0, eighth // 2, 0))) < 1e-6


# ---------------------------------------------------------------------------
# The setting, on a two-bone arm
# ---------------------------------------------------------------------------

def build_arm():
    """A shoulder and a straight arm hanging off it, in the file's own classes."""
    root = Bone()
    root.parent_id = 0xFFFF
    root.set_size(0.0)
    arm = Bone()
    arm.parent_id = 0
    arm.set_size(-2.0)                               # sizes are negative in every real model
    return [root, arm]


def build_frame(bones, pose_list):
    frame = AnimationFrame(len(bones))
    frame.position = [PositionType(0, 0, axis=axis) for axis in range(3)]
    for bone_index, pose in enumerate(pose_list):
        frame.rotation_vector_data[bone_index] = [RotationType(True, 0, raw) for raw in pose]
    frame.set_all_bones_matrix(bones)
    return frame


def hand_position(frame, bones):
    """Where the tip of the arm ends up, which is what the animation is judged on."""
    matrix = frame.bone_matrices[1]
    length = bones[1].get_size()
    return (matrix.M13 * length + matrix.M41,
            matrix.M23 * length + matrix.M42,
            matrix.M33 * length + matrix.M43)


ARM_A = [(0, 0, 0), (0, 0, 0)]
# The same arm turned by a bit more than a third of a turn, written the way a real file does -
# three angles that share the work, which is exactly the case the per-axis blend gets wrong.
ARM_B = [(0, 0, 0), (600, 1400, -1100)]


def blend_arm(mode, nb_insert=6):
    bones = build_arm()
    frame_a = build_frame(bones, ARM_A)
    frame_b = build_frame(bones, ARM_B)
    return bones, [Animation._create_frame_between(frame_a, frame_b, index / (nb_insert + 1),
                                                   bones, mode=mode)
                   for index in range(1, nb_insert + 1)]


def turn_between(pose_a, pose_b) -> float:
    """How far one pose is from the other, as the single turn that takes one to the other."""
    relative = rotation3d._multiply(rotation3d._transpose(rotation3d.euler_raw_to_matrix(pose_a)),
                                   rotation3d.euler_raw_to_matrix(pose_b))
    return rotation3d._axis_angle(relative)[1]


def detour_of(frame_list) -> float:
    """The worst detour the inserted poses make: how much further than the turn itself a frame
    sits from the two keyframes put together. 0 means every frame is ON the way."""
    straight = turn_between(ARM_A[1], ARM_B[1])
    worst = 0.0
    for frame in frame_list:
        pose = [frame.rotation_vector_data[1][axis].get_rotate_raw() for axis in range(3)]
        worst = max(worst, turn_between(ARM_A[1], pose) + turn_between(pose, ARM_B[1]) - straight)
    return worst


def test_the_arc_puts_every_inserted_pose_on_the_way_and_the_angles_do_not():
    """The whole reason the setting exists. Every arc frame is ON the turn from one pose to the
    other - the two halves add up to the whole - while blending the three angles separately sends
    the bone off the way and back, which is the T-pose an arm goes through in a real file."""
    arc = interpolation.InterpolationMode(interpolation.LINEAR, {"shortest_arc": True})
    assert detour_of(blend_arm(arc)[1]) < math.radians(0.5)
    assert detour_of(blend_arm(interpolation.LINEAR)[1]) > math.radians(10.0)


def test_the_arc_keeps_the_bone_the_length_it_is():
    """A turn cannot move the tip nearer or further than the bone is long - a good sign nothing
    but a rotation came out of the blend."""
    bones = build_arm()
    length = abs(bones[1].get_size())
    _, frame_list = blend_arm(interpolation.InterpolationMode(interpolation.SMOOTH,
                                                              {"shortest_arc": True}))
    for frame in frame_list:
        assert math.dist((0.0, 0.0, 0.0), hand_position(frame, bones)) == pytest.approx(
            length, rel=1e-3)


def test_the_arc_never_leaves_the_pose_the_two_keyframes_agree_on():
    """The shoulder holds the same pose in both keyframes, so no inserted frame is allowed to
    move it - a bone that does not turn must not be given a turn by the blend."""
    _, frame_list = blend_arm(interpolation.InterpolationMode(interpolation.SPLINE,
                                                              {"shortest_arc": True}))
    for frame in frame_list:
        for axis in range(3):
            assert frame.rotation_vector_data[0][axis].get_rotate_raw() == 0


def test_the_setting_is_off_unless_it_is_asked_for():
    """Every file converted before this existed has to keep converting the same way."""
    for mode in interpolation.ALL_MODES:
        assert not interpolation.rotates_in_arc(mode)
        assert not interpolation.rotates_in_arc(interpolation.InterpolationMode(mode))
    plain = blend_arm(interpolation.SMOOTH)[1]
    same = blend_arm(interpolation.InterpolationMode(interpolation.SMOOTH,
                                                     {"shortest_arc": False}))[1]
    for frame_plain, frame_same in zip(plain, same):
        for bone_index in range(2):
            for axis in range(3):
                assert (frame_plain.rotation_vector_data[bone_index][axis].get_rotate_raw()
                        == frame_same.rotation_vector_data[bone_index][axis].get_rotate_raw())


def test_the_curve_still_shapes_the_speed_of_the_arc():
    """The setting says WHAT is blended, the curve says how fast: an eased arc has to start
    slower than a linear one and still arrive at the same pose."""
    linear = blend_arm(interpolation.InterpolationMode(interpolation.LINEAR,
                                                       {"shortest_arc": True}))[1]
    smooth = blend_arm(interpolation.InterpolationMode(interpolation.SMOOTH,
                                                       {"shortest_arc": True}))[1]
    bones = build_arm()
    frame_a = build_frame(bones, ARM_A)
    start = hand_position(frame_a, bones)
    assert (math.dist(start, hand_position(smooth[0], bones))
            < math.dist(start, hand_position(linear[0], bones)))


def test_the_arc_leaves_the_position_and_the_scales_to_the_curve():
    """Only the rotations change space: the skeleton position keeps following the curve, so a
    model that travels during the morph goes on travelling the same way."""
    bones = build_arm()
    frame_a = build_frame(bones, ARM_A)
    frame_b = build_frame(bones, ARM_B)
    frame_b.position = [PositionType(0, 400, axis=axis) for axis in range(3)]
    arc = interpolation.InterpolationMode(interpolation.LINEAR, {"shortest_arc": True})
    for step in (0.25, 0.5, 0.75):
        by_angle = Animation._create_frame_between(frame_a, frame_b, step, bones,
                                                   mode=interpolation.LINEAR)
        by_arc = Animation._create_frame_between(frame_a, frame_b, step, bones, mode=arc)
        for axis in range(3):
            assert (by_arc.position[axis].get_pos_raw()
                    == by_angle.position[axis].get_pos_raw() == round(400 * step))
