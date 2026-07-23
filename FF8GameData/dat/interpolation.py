"""The curves offered wherever the editor creates in-between frames.

Two features insert frames: the fps conversion (15 fps native -> 30/60, one frame added between
each pair) and the manual "interpolate between two frames" (as many as asked). Both used to blend
linearly, which is not always what the motion wants, so both now let the user pick a curve. The
choice only changes the VALUES of the inserted frames - never how many there are, nor the frames
that were already there, which every mode leaves untouched (animation ids and frame indices are
addressed by the sequences and the AI, so the original poses have to stay put).

Each mode works on one channel at a time (a bone rotation axis, a root position axis, a bone
scale axis) and gets the two frames of the segment plus their neighbours outside it, because a
curve that flows through the keyframes needs to know where the motion comes from and where it
goes. `before`/`after` are None at the ends of a non-looping animation, where every mode falls
back to the segment alone.

The same curves also re-value frames that ALREADY exist: the frame-position tab can take two
frames as keyframes and rewrite one position axis on every frame between them
(IfritManager.interpolate_frame_position). Nothing is inserted or removed there either - only the
values of the frames in between change, and the two keyframes themselves are left alone.
"""
import math

LINEAR = "linear"
SMOOTH = "smooth"
SINE = "sine"
SPLINE = "spline"
HOLD = "hold"

ALL_MODES = (LINEAR, SMOOTH, SINE, SPLINE, HOLD)

# Shown in the interpolation combo box, in this order.
MODE_LABEL = {
    LINEAR: "Linear (constant speed)",
    SMOOTH: "Smooth (ease in and out)",
    SINE: "Sine (rounded turnaround)",
    SPLINE: "Spline (flows through the keyframes)",
    HOLD: "Hold (no blending)",
}

MODE_DESCRIPTION = {
    LINEAR: "Moves at a constant speed from one pose to the other. The motion changes speed "
            "abruptly on every original frame, which is visible once the frame rate goes up.",
    SMOOTH: "Starts and ends slowly, fastest in the middle. Best when morphing between two poses "
            "that the motion stops on - a stance change, an impact hold.",
    SINE: "Follows a sine curve: it leaves and arrives with no speed at all, so two segments put "
          "end to end round off where they meet instead of forming a corner.\nThis is the one for "
          "an up-and-down movement on a position axis - set the bottom, the top and the bottom "
          "again on three frames, apply it to both halves, and the model floats up and comes back "
          "down instead of shooting up and stopping dead at the top.",
    SPLINE: "Follows a curve through the frames before and after the segment, so the speed flows "
            "through the original poses instead of breaking on them.\nBest for raising the frame "
            "rate of a continuous motion. It can slightly overshoot a pose, which usually reads "
            "as natural follow-through.",
    HOLD: "No blending at all: the inserted frames repeat the pose they start from. Keeps a "
          "deliberately snappy animation snappy at a higher frame rate.",
}

# What each feature offers first (the user can always pick another one).
DEFAULT_FOR_FPS_CONVERSION = SPLINE      # a continuous motion being resampled
DEFAULT_FOR_MANUAL_INSERT = SMOOTH       # a pose-to-pose morph the user chose the ends of

ROTATION_RAW_PER_TURN = 4096


def unwrap_rotation_raw(reference: int, raw: int) -> int:
    """`raw` expressed on the turn nearest `reference`.

    Rotations are stored modulo 4096 raw units, so 4090 and -6 are the same angle. Interpolating
    the stored values directly would send the bone the long way round; unwrapping every value of
    the segment against the one before it keeps all of them on one continuous line, which is what
    the curves below need (linear included - this is the old "shortest way" rule generalised).
    """
    half = ROTATION_RAW_PER_TURN // 2
    return reference + (((raw - reference + half) % ROTATION_RAW_PER_TURN) - half)


def interpolate_value(before, value_a, value_b, after, step: float, mode: str) -> float:
    """One channel of one inserted frame.

    value_a/value_b are the segment's ends (step 0.0 and 1.0), before/after the values of the
    frames just outside it, or None where there is none. Unknown modes fall back to linear rather
    than raising: an interpolation is never worth losing an edit over.
    """
    if mode == HOLD:
        return value_a
    if mode == SMOOTH:
        # smoothstep: zero slope at both ends
        step = step * step * (3.0 - 2.0 * step)
    elif mode == SINE:
        # Half a cosine period: zero slope at both ends like smoothstep, but rounder in the
        # middle - it spends less time at full speed, which is what makes an axis that goes up
        # and then down read as a float rather than a shove.
        step = (1.0 - math.cos(math.pi * step)) / 2.0
    elif mode == SPLINE:
        return _catmull_rom(value_a if before is None else before, value_a, value_b,
                            value_b if after is None else after, step)
    return value_a + (value_b - value_a) * step


def _catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Uniform Catmull-Rom: the cubic through p1 and p2 whose slope at each of them follows the
    line between its own neighbours. Passes exactly through p1 (t=0) and p2 (t=1) - the original
    poses are preserved - and joins the neighbouring segments with a continuous speed.

    Duplicating an end (p0 = p1, or p3 = p2) is how the ends of a non-looping animation are
    handled: the curve then simply flattens into that end, like a one-sided ease.
    """
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (2.0 * p1
                  + (p2 - p0) * t
                  + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3)
