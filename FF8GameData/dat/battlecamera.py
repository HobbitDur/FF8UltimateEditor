"""Battle-context playback for DAT camera collections.

Coordinates here are engine XYZ (+Y down), not the editor's historical field names
(pos_z, pos_x, pos_y). Reuses the GF cinematic scene's engine look-at basis (magcine.cinescene) and Watts' timing/easing
and spline implementation. References: EN 503520, 5035E0, 503C70, 50D300, 50D790.
Actor poses/placements are supplied by the preview, not inferred from an isolated DAT.
Floating-point matrices/splines approximate the engine's fixed-point rounding.
"""
from dataclasses import dataclass, field
import math

import numpy as np

from FF8GameData.magcine.cinescene import look_at
from .camerabake import _ease, _natural_cubic_spline


@dataclass
class CameraPose:
    eye: tuple
    target: tuple
    projection: float = 512.0
    roll: float = 0.0
    block: int = 0


@dataclass
class CameraActor:
    position: tuple = (0., 0., 0.)
    yaw: float = 0.0                 # radians, rotation about engine Y
    scale: float = 0.25             # camera offset scale: model_scale / 512
    anchor: object = None           # (selector 0..15, tick) -> WORLD engine XYZ

    @property
    def rotation(self):
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return np.array(((c, 0, s), (0, 1, 0), (-s, 0, c)))

    def point(self, selector, tick):
        if self.anchor is not None:
            return np.asarray(self.anchor(selector, tick), float)
        return np.asarray(self.position, float)


@dataclass
class BattleCameraContext:
    caster: CameraActor = field(default_factory=CameraActor)
    target: CameraActor = field(default_factory=lambda: CameraActor(position=(0., 0., 5000.)))
    initial: CameraPose = field(default_factory=lambda: CameraPose(
        (-4000., -2500., -7000.), (0., -500., 2500.)))
    slots: dict = field(default_factory=dict)
    mirrored: bool = False
    warnings: set = field(default_factory=set)

    def resolve(self, point, mode, previous, tick):
        """cameraTranslation: interpret a local point in its selected reference frame."""
        p = np.asarray(point, float).copy()
        if mode == 0xFB:             # already resolved/world space
            return p
        if self.mirrored:
            p[0] *= -1
        if mode == 0xF1:             # no matrix: raw coordinates (mirrored on Z)
            p = np.asarray(point, float).copy()
            if self.mirrored:
                p[2] *= -1
            return p
        if mode in (0xF3, 0xF4):
            return p + np.asarray(previous.eye if mode == 0xF3 else previous.target)
        if mode == 0xF2 or 0xF5 <= mode <= 0xF8:
            # F2: unscaled base-position midpoint. F5..F8: the four combinations
            # of the skeleton's F0/F1 effect attachment points, distance-normalized.
            if mode == 0xF2:
                a, b = np.asarray(self.caster.position), np.asarray(self.target.position)
                scale = 1.0
            else:
                which = mode - 0xF5
                a = self.caster.point(which // 2, tick)
                b = self.target.point(which % 2, tick)
                distance = np.linalg.norm(b - a)
                scale = distance / 5000.0 if distance else 1.0
            basis = look_at(a, b)[:3, :3] if np.linalg.norm(b - a) else self.caster.rotation
            return (a + b) / 2 + basis @ (p * scale)
        if mode == 0xF9:
            self.warnings.add('Effect-owned frame F9 is unavailable; using the target frame')
            return np.asarray(self.target.position) + self.target.rotation @ p
        if 0xB0 <= mode <= 0xF0 or mode >= 0xFA:
            # Target-side reference used by the generic world-frame modes.
            return np.asarray(self.target.position) + self.target.rotation @ p
        slot, selector = mode >> 4, mode & 15
        actor = self.caster if slot == 9 else self.target if slot == 10 else self.slots.get(slot)
        if actor is None:
            self.warnings.add(f"Slot {slot} is not placed in this preview")
            return p
        return actor.point(selector, tick) + actor.rotation @ (p * actor.scale)


def _point(frame, prefix):
    return np.array([getattr(frame, prefix + axis).get() for axis in ('z', 'x', 'y')], float)


def _lens(block, prefix, mode, old, default):
    start, end = getattr(block, prefix + '_start', None), getattr(block, prefix + '_end', None)
    if mode == 0:
        return old
    if mode == 1:
        return default, default
    a = start.get() if start is not None else default
    return a, end.get() if end is not None else a


def play_camera_animation(animation, context, max_frames=4096):
    """One CameraPose per 15 Hz engine tick, retaining modes, block boundaries and lens.

    Layout 1 resolves ALL keyframes once when entering the block, against the same
    preceding view. Layout 0 resolves interpolated coordinates live. This distinction
    matters for F3/F4: zero offsets hold the previous view, never the model origin.
    """
    result = []
    previous = context.initial
    fov_pair = (previous.projection, previous.projection)
    for block_id, block in enumerate(getattr(animation, 'blocks', [])):
        keyframes = block.frames
        if not keyframes:
            continue
        durations = [max(0, f.duration.get()) for f in keyframes]
        timings = np.cumsum([0] + durations[:-1]).tolist()
        total = sum(durations)
        if total <= 0:
            continue
        cw = block.control_word
        fov_pair = _lens(block, 'fov', (cw >> 6) & 3, fov_pair, 512)
        roll_pair = _lens(block, 'roll', (cw >> 8) & 3, (previous.roll, previous.roll), 0)
        modes = {prefix: [getattr(f, prefix + 'interp_mode').get() for f in keyframes]
                 for prefix in ('pos_', 'look_')}
        points = {prefix: [_point(f, prefix) for f in keyframes] for prefix in modes}
        frozen = bool(cw & 1)
        start_tick = len(result)
        if frozen:
            points = {prefix: [context.resolve(p, mode, previous, start_tick)
                               for p, mode in zip(values, modes[prefix])]
                      for prefix, values in points.items()}
        # Coalesce zero-duration controls before spline construction (no zero denominators).
        indices = [i for i in range(len(timings)) if i == len(timings) - 1 or timings[i + 1] > timings[i]]
        times = [timings[i] for i in indices]
        values = {prefix: [v[i] for i in indices] for prefix, v in points.items()}
        active_modes = {prefix: [v[i] for i in indices] for prefix, v in modes.items()}
        count = len(indices)
        splines = None
        if count > 2:
            splines = {prefix: [_natural_cubic_spline(times, [p[axis] for p in v]) for axis in range(3)]
                       for prefix, v in values.items()}
        for time in range(min(total, max_frames - len(result))):
            at = time if count < 3 else _ease((time << 12) // total, cw) * total / 4096
            if count == 1 or at >= times[-1]:
                segment, fraction = count - 1, 0.0
            else:
                segment = next(i for i in range(count - 1) if at < times[i + 1])
                fraction = (at - times[segment]) / (times[segment + 1] - times[segment])
                if count == 2:
                    fraction = _ease(int(fraction * 4096), cw) / 4096
            world = []
            for prefix in ('pos_', 'look_'):
                v = values[prefix]
                if count == 1 or segment == count - 1:
                    p = v[segment]
                elif count == 2:
                    p = v[0] + (v[1] - v[0]) * fraction
                else:
                    p = np.array([s(at) for s in splines[prefix]])
                if not frozen:
                    m = active_modes[prefix]
                    p0 = context.resolve(p, m[segment], previous, len(result))
                    if fraction and m[segment] != m[segment + 1]:
                        p1 = context.resolve(p, m[segment + 1], previous, len(result))
                        p0 = p0 + (p1 - p0) * fraction
                    p = p0
                world.append(tuple(p))
            # The engine advances the clock before applying the projection and roll.
            lens_t = (time + 1) / total
            previous = CameraPose(*world, fov_pair[0] + (fov_pair[1] - fov_pair[0]) * lens_t,
                                  roll_pair[0] + (roll_pair[1] - roll_pair[0]) * lens_t, block_id)
            result.append(previous)
        if len(result) >= max_frames:
            break
    return result


def projection_frustum(projection, near=0.01):
    """FF8 projection H, screen centre (160,108), in the 320x240 game viewport."""
    h = max(float(projection), 1.0)
    return (-160 * near / h, 160 * near / h, -132 * near / h, 108 * near / h)
