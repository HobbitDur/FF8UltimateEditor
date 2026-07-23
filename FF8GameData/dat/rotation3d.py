"""Bone poses as 3D rotations, so an in-between frame can turn a bone the way it really turns.

A frame stores a bone's pose as three angles - X, Y and Z, in raw units with 4096 to the turn -
and the engine builds one matrix out of them (AnimationFrame.set_bone_matrix). Blending two poses
by moving each of the three angles along its own line, which is what every curve in
interpolation.py does, is fine while the two poses are CLOSE: that is the fps conversion, where a
frame is inserted between two frames a fifteenth of a second apart.

It is not fine between two poses far apart, and the reason is that the three angles are not three
independent directions - they multiply. Two poses whose bones differ by a modest turn can be
written with wildly different angle triples (the same arm, one turn, +148 deg on Y and -119 on Z),
and interpolating those numbers sends the bone somewhere neither pose ever goes. On c0m144's
"stand up and lower the arms" the arms leave through a full T-pose before coming back down.

This module blends in rotation space instead: each pose becomes a matrix, the rotation FROM one
TO the other is read as an axis and an angle, a fraction of that angle is applied, and the result
is turned back into the three angles the file stores. The bone then makes exactly one turn, around
one axis, the short way round - the motion the animator posed, and the same thing a 3D package
does when it interpolates a bone.

The convention is the engine's own, read off set_bone_matrix (which negates X and Y but not Z):

    M = Ry(-ry) . Rx(-rx) . Rz(rz)          angles in degrees, matrix rows M11..M33

tests/test_rotation3d.py checks that against Matrix4x4 itself rather than trusting this comment.

Matrices here are plain 3x3 row lists ([[M11, M12, M13], [M21, ...], ...]) - the same numbers
Matrix4x4 carries, without the translation row it does not need.
"""
import math

RAW_PER_TURN = 4096
_RAW_TO_RAD = 2.0 * math.pi / RAW_PER_TURN
_RAD_TO_RAW = RAW_PER_TURN / (2.0 * math.pi)

# Below this, a rotation is too small for its axis to be worth computing (the two poses are the
# same pose) and, in the decomposition, the pose is on the gimbal singularity.
_EPSILON = 1e-7


def unwrap_raw(reference: int, raw: int) -> int:
    """`raw` expressed on the turn nearest `reference` - the same rule as
    interpolation.unwrap_rotation_raw, kept here so this module stays pure geometry."""
    half = RAW_PER_TURN // 2
    return reference + (((raw - reference + half) % RAW_PER_TURN) - half)


def euler_raw_to_matrix(rotation_raw) -> list:
    """The 3x3 the engine builds for a bone holding these three raw angles."""
    # The negated X and Y are the engine's, not a mistake: set_bone_matrix passes -rx and -ry.
    v = -rotation_raw[0] * _RAW_TO_RAD
    u = -rotation_raw[1] * _RAW_TO_RAD
    w = rotation_raw[2] * _RAW_TO_RAD
    cu, su = math.cos(u), math.sin(u)
    cv, sv = math.cos(v), math.sin(v)
    cw, sw = math.cos(w), math.sin(w)
    # Ry(u) . Rx(v) . Rz(w), multiplied out.
    return [[cu * cw + su * sv * sw, -cu * sw + su * sv * cw, su * cv],
            [cv * sw, cv * cw, -sv],
            [-su * cw + cu * sv * sw, su * sw + cu * sv * cw, cu * cv]]


def matrix_to_euler_raw(matrix, near=(0, 0, 0)) -> list:
    """The three raw angles a bone needs to hold `matrix`, written as close to `near` as possible.

    A pose has more than one triple of angles (two branches of the decomposition, and any number
    of whole turns on each axis) and they all describe the SAME pose, so the choice is free. It is
    made on how the frame will be stored: each frame is written as a delta from the previous one,
    so the triple nearest the pose we came from is the one that costs the fewest bits and keeps
    the numbers in the 3D tab readable.
    """
    best = None
    # M[1][2] is -sin(-rx), which pins X down to two possibilities: the arcsine and its mirror.
    x_angle = math.asin(max(-1.0, min(1.0, -matrix[1][2])))
    for angle in (x_angle, math.pi - x_angle):
        cos_x = math.cos(angle)
        if abs(cos_x) < _EPSILON:
            # Gimbal lock: X points the Y and Z axes at each other, so only their sum is defined.
            # Everything of the pose is kept, the sharing between the two axes is the arbitrary
            # part - and it is Z, the axis the file leaves un-negated, that is given the zero.
            y_angle = math.atan2(-matrix[2][0], matrix[0][0])
            z_angle = 0.0
        else:
            y_angle = math.atan2(matrix[0][2] / cos_x, matrix[2][2] / cos_x)
            z_angle = math.atan2(matrix[1][0] / cos_x, matrix[1][1] / cos_x)
        candidate = [unwrap_raw(near[index], round(value * _RAD_TO_RAW))
                     for index, value in enumerate((-angle, -y_angle, z_angle))]
        cost = sum(abs(candidate[index] - near[index]) for index in range(3))
        if best is None or cost < best[0]:
            best = (cost, candidate)
    return best[1]


def slerp_matrix(matrix_a, matrix_b, ratio: float) -> list:
    """The rotation `ratio` of the way from `matrix_a` to `matrix_b`, turning around one axis.

    ratio 0 gives back matrix_a and 1 gives matrix_b; in between, the bone turns at a constant
    speed around the single axis that takes one pose to the other, the short way round (a turn is
    never made the long way, whatever the numbers in the file say). Values outside 0..1 keep
    turning around that same axis, which is what a curve overshooting its segment asks for.
    """
    relative = _multiply(_transpose(matrix_a), matrix_b)
    axis, angle = _axis_angle(relative)
    if angle < _EPSILON:
        return [row[:] for row in matrix_a]
    return _multiply(matrix_a, _rotation_around(axis, angle * ratio))


def blend_euler_raw(rotation_a, rotation_b, ratio: float) -> list:
    """The three raw angles `ratio` of the way from one pose to the other, turning the short way.

    The one call the frame builder needs: the poses go in as the triples the file holds and the
    answer comes back in the same form, written near the first pose (see matrix_to_euler_raw).
    """
    matrix = slerp_matrix(euler_raw_to_matrix(rotation_a), euler_raw_to_matrix(rotation_b), ratio)
    return matrix_to_euler_raw(matrix, rotation_a)


# ---------------------------------------------------------------------------
# The 3x3 arithmetic this needs, kept local rather than pulling numpy into the data layer
# ---------------------------------------------------------------------------

def _transpose(matrix) -> list:
    return [[matrix[row][column] for row in range(3)] for column in range(3)]


def _multiply(left, right) -> list:
    return [[sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
            for row in range(3)]


def _axis_angle(matrix):
    """A rotation matrix as the axis it turns around and how far it turns (radians, 0..pi)."""
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    angle = math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0)))
    if angle < _EPSILON:
        return (0.0, 0.0, 1.0), 0.0
    sin_angle = math.sin(angle)
    if abs(sin_angle) < _EPSILON:
        # Half a turn: the off-diagonal terms cancel out, so the axis is read off the diagonal
        # (its squares) and the signs are recovered from the largest component.
        axis = [math.sqrt(max(0.0, (matrix[index][index] + 1.0) / 2.0)) for index in range(3)]
        largest = axis.index(max(axis))
        if largest == 0:
            axis[1] = math.copysign(axis[1], matrix[0][1])
            axis[2] = math.copysign(axis[2], matrix[0][2])
        elif largest == 1:
            axis[0] = math.copysign(axis[0], matrix[0][1])
            axis[2] = math.copysign(axis[2], matrix[1][2])
        else:
            axis[0] = math.copysign(axis[0], matrix[0][2])
            axis[1] = math.copysign(axis[1], matrix[1][2])
        return _normalized(axis), angle
    axis = [(matrix[2][1] - matrix[1][2]) / (2.0 * sin_angle),
            (matrix[0][2] - matrix[2][0]) / (2.0 * sin_angle),
            (matrix[1][0] - matrix[0][1]) / (2.0 * sin_angle)]
    return _normalized(axis), angle


def _normalized(axis):
    length = math.sqrt(sum(value * value for value in axis))
    if length < _EPSILON:
        return (0.0, 0.0, 1.0)
    return tuple(value / length for value in axis)


def _rotation_around(axis, angle: float) -> list:
    """Rodrigues' formula: the matrix that turns by `angle` around `axis`."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1.0 - c
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
