"""Engine-faithful playback of a battle camera animation (shared by Ifrit's camera tab
and Watts' victory-camera preview).

Replicates `ProcessCameraAnimation` (FF8_EN.exe 0x5035E0) + `BS_Camera_ReadAnimation`
(0x503C70): a camera animation is a chain of blocks; each block holds keyframes and its
own timing, and the camera plays through the whole chain. Per block the engine steps
`CurrentAnimationTime += 16` per frame up to `TotalAnimationDuration = sum(duration)*16`,
with keyframe timings `= cumsum(duration)*16`, and interpolates (verified in IDA):

  - 1 keyframe  -> static hold,
  - 2 keyframes -> eased-linear between the two (kf0 + (ease(t)*(kf1-kf0))>>12), then hold
                   the second for its remaining duration,
  - 3+          -> a natural cubic spline through the keyframes (0x50D060 solves the
                   moments, 0x50D240 evaluates; endpoints have zero 2nd derivative).

Timing can be eased by the block control word (`bs_camera_timeOp_unk` 0x503FE0): control
word 0x3C1 is linear, 0x3C5 applies the PSX sine ease twice.

Faithful in structure, timing, hold and curve shape. Two deliberate approximations: (1) the
per-keyframe position "mode" resolves through the *live* battle camera matrix at runtime,
which a static preview cannot reproduce, so raw coordinates are used (the same raw
coordinates the 3D viewer is fed); (2) FOV and roll are not applied (the viewer has a fixed
lens). The PSX sine table is approximated with math.sin/cos.
"""
import math


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _compute_sin(angle: int) -> int:
    # PSX-style: 4096 units == a full turn, result scaled to 4096 == 1.0
    return round(4096 * math.sin(angle * 2 * math.pi / 4096))


def _compute_cos(angle: int) -> int:
    return round(4096 * math.cos(angle * 2 * math.pi / 4096))


def _ease(t: int, control_word: int) -> int:
    """bs_camera_timeOp_unk: maps a linear fraction t in [0, 4096] to an eased one."""
    iterations = _signed16((control_word << 10) & 0xFFFF) >> 11
    if (control_word & 0x20) == 0:
        if (control_word & 0xFFFE) == 0 or iterations <= 0:
            return t
        result = t
        for _ in range(iterations):
            result = _compute_sin(result // 4)
        return result
    if iterations >= 0:
        return t
    result = t
    for _ in range(-iterations):
        result = 4096 - _compute_cos(result // 4)
    return result


def _natural_cubic_spline(xs, ys):
    """Return f(x) for the natural cubic spline through (xs, ys) - second derivative zero
    at both ends, matching sub_50D060 / interpolateCameraParameter."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    moments = [0.0] * n  # second derivatives; ends stay 0 (natural boundary)
    if n > 2:
        lower = [0.0] * n
        diag = [1.0] * n
        upper = [0.0] * n
        rhs = [0.0] * n
        for i in range(1, n - 1):
            lower[i] = h[i - 1]
            diag[i] = 2 * (h[i - 1] + h[i])
            upper[i] = h[i]
            rhs[i] = 6 * ((ys[i + 1] - ys[i]) / h[i] - (ys[i] - ys[i - 1]) / h[i - 1])
        for i in range(1, n - 1):  # Thomas forward elimination
            w = lower[i] / diag[i - 1]
            diag[i] -= w * upper[i - 1]
            rhs[i] -= w * rhs[i - 1]
        for i in range(n - 2, 0, -1):  # back substitution
            moments[i] = (rhs[i] - upper[i] * moments[i + 1]) / diag[i]

    def evaluate(x):
        segment = 0
        while segment < n - 2 and x >= xs[segment + 1]:
            segment += 1
        step = h[segment]
        dt = x - xs[segment]
        m0, m1 = moments[segment], moments[segment + 1]
        y0, y1 = ys[segment], ys[segment + 1]
        b = (y1 - y0) / step - step * (2 * m0 + m1) / 6
        return y0 + b * dt + (m0 / 2) * dt * dt + (m1 - m0) / (6 * step) * dt ** 3

    return evaluate


_FRAME_STEP = 16      # CurrentAnimationTime += 16 per frame
_MAX_FRAMES = 4096    # safety cap for a pathological animation


def bake_camera_animation(animation):
    """[(x, y, z, look_x, look_y, look_z)] for every frame of the whole animation, in order.

    Coordinates are in the same raw space the 3D viewer is fed."""
    frames = []
    for block in getattr(animation, "blocks", []):
        keyframes = block.frames
        if not keyframes:
            continue
        control_word = block.control_word
        durations = [f.duration.get() for f in keyframes]
        timings = []
        accumulated = 0
        for duration in durations:
            timings.append(accumulated)
            accumulated += _FRAME_STEP * duration
        total = accumulated
        if total <= 0:
            continue
        columns = {
            name: [getattr(f, name).get() for f in keyframes]
            for name in ("pos_x", "pos_y", "pos_z", "look_x", "look_y", "look_z")
        }
        count = len(keyframes)
        splines = None
        if count >= 3:
            splines = {name: _natural_cubic_spline(timings, values)
                       for name, values in columns.items()}

        time = 0
        while time < total and len(frames) < _MAX_FRAMES:
            if count == 1:
                sample = {name: values[0] for name, values in columns.items()}
            elif count == 2:
                if time >= timings[1]:
                    sample = {name: values[1] for name, values in columns.items()}
                else:
                    fraction = _ease((time << 12) // timings[1], control_word)
                    sample = {name: values[0] + ((fraction * (values[1] - values[0])) >> 12)
                              for name, values in columns.items()}
            else:
                eased_time = (_ease((time << 12) // total, control_word) * total) >> 12
                if eased_time >= timings[-1]:
                    sample = {name: values[-1] for name, values in columns.items()}
                else:
                    sample = {name: int(round(splines[name](eased_time)))
                              for name in columns}
            frames.append((sample["pos_x"], sample["pos_y"], sample["pos_z"],
                           sample["look_x"], sample["look_y"], sample["look_z"]))
            time += _FRAME_STEP
    return frames


def zoom_out(frames, factor):
    """Dolly every camera position away from its own look-at by `factor` (>1 pulls the
    camera back, so the subject looks smaller and fits in frame). The look-at is kept, so
    the framing direction is unchanged - only the distance grows."""
    if factor == 1.0:
        return frames
    result = []
    for x, y, z, look_x, look_y, look_z in frames:
        result.append((
            round(look_x + (x - look_x) * factor),
            round(look_y + (y - look_y) * factor),
            round(look_z + (z - look_z) * factor),
            look_x, look_y, look_z))
    return result


# --- adapters so CameraPreviewPanel can play the baked path unchanged ------------------
# The panel reads animation.blocks[].frames[].{pos_x,pos_y,pos_z,look_x,look_y,look_z,
# duration}.get(); we present one block of one-tick frames holding the baked poses, so the
# panel's own per-tick playback reproduces the engine-faithful motion exactly.
class _BakedField:
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _BakedFrame:
    def __init__(self, sample):
        x, y, z, look_x, look_y, look_z = sample
        self.pos_x, self.pos_y, self.pos_z = _BakedField(x), _BakedField(y), _BakedField(z)
        self.look_x = _BakedField(look_x)
        self.look_y = _BakedField(look_y)
        self.look_z = _BakedField(look_z)
        self.duration = _BakedField(1)  # one preview tick per baked engine frame


class _BakedBlock:
    def __init__(self, frames):
        self.frames = frames


class BakedAnimation:
    """A CameraPreviewPanel-compatible animation whose keyframes are the per-frame baked
    poses of the real animation (so the panel's linear per-tick playback is engine-faithful)."""

    def __init__(self, source):
        # source may be a CameraAnimation to bake, or an already-baked list of poses
        # (e.g. after recentre + zoom post-processing).
        baked = source if isinstance(source, list) else bake_camera_animation(source)
        self.blocks = [_BakedBlock([_BakedFrame(sample) for sample in baked])]
        self.empty = not baked

    def is_empty(self):
        return self.empty
