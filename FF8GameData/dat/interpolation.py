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

Every curve but the linear one has parameters (MODE_PARAMETERS): how many waves a sine makes
across the segment, how round it is, how much the spline lets the neighbours pull it, where a hold
snaps... They travel with the mode itself, as an InterpolationMode - a string carrying the values,
so every layer that only forwards `mode` (the fps converter, the splitter, the manager) keeps
working, and so does anything comparing it to LINEAR/SINE/... or using it as a dict key.
The parameters DEFAULT to the curve as it was before they existed: a plain "sine" string and an
InterpolationMode("sine") with untouched parameters produce exactly the same frames.

On top of those, SHARED_PARAMETERS apply whatever the curve is, because they are not about its
shape: the only one so far is `shortest_arc`, which says whether the bone rotations are blended as
3D rotations (FF8GameData/dat/rotation3d.py) instead of three numbers moving on their own. Ask a
curve for everything it offers with parameters_for(); MODE_PARAMETERS stays what the CURVE itself
has to adjust.
"""
import math
from dataclasses import dataclass

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
          "down instead of shooting up and stopping dead at the top.\nOr do the whole thing in "
          "one go: two half-waves go up and come back inside a single range, and more of them "
          "repeat it.",
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


# ---------------------------------------------------------------------------
# The knobs of each curve
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeParameter:
    """One knob of one curve, and everything the popup needs to show it.

    `default` is always the value the curve had before it was made adjustable, so leaving a
    parameter alone can never change what a conversion produces.
    """
    key: str
    label: str
    default: float
    minimum: float = 0.0
    maximum: float = 1.0
    step: float = 0.05
    decimals: int = 2
    kind: str = "float"          # "float", "int" or "bool"
    description: str = ""

    def clamp(self, value):
        """The value as the curve will use it: right type, inside the allowed range."""
        if self.kind == "bool":
            return bool(value)
        if self.kind == "int":
            return int(max(self.minimum, min(self.maximum, int(round(float(value))))))
        return float(max(self.minimum, min(self.maximum, float(value))))


MODE_PARAMETERS = {
    # Linear is the one curve with nothing to adjust: a straight line is a straight line.
    LINEAR: (),
    SMOOTH: (
        ModeParameter(
            "strength", "Ease strength", default=1.00, minimum=0.00, maximum=1.00,
            description="How much of the ease is applied. 1.00 is the full ease in and out, "
                        "0.00 is a straight line (linear), and the values between blend the two "
                        "- use them when the ease feels too soft for a fast motion."),
        ModeParameter(
            "bias", "Ease bias (start <-> end)", default=0.00, minimum=-1.00, maximum=1.00,
            description="Which end the ease sits on. 0.00 eases both ends equally. Towards -1.00 "
                        "only the start is eased, so the motion builds up and arrives at full "
                        "speed; towards +1.00 only the end is, so it leaves at full speed and "
                        "settles - the usual choice for a blow landing or a recoil."),
    ),
    SINE: (
        ModeParameter(
            "half_waves", "Half-waves across the segment", default=1, minimum=1, maximum=16,
            step=1, decimals=0, kind="int",
            description="How many times the value travels the segment. 1 goes from the first "
                        "pose to the second one (the plain rounded ease). 2 goes to the second "
                        "and comes back, so ONE range does a whole up-and-down without needing a "
                        "third keyframe; 4 does it twice - a hover, a breathing idle, a shiver. "
                        "An even count lands back on the first pose, an odd one on the second."),
        ModeParameter(
            "curvature", "Curvature", default=1.00, minimum=0.00, maximum=2.00,
            description="The shape of the wave. 1.00 is the true sine. Below it the wave "
                        "straightens towards a triangle (sharp turnarounds, constant speed "
                        "between them), 0.00 being fully straight. Above it the turnarounds "
                        "flatten out and the middle gets steeper, which reads as hanging at the "
                        "top before dropping."),
        ModeParameter(
            "amplitude", "Amplitude", default=1.00, minimum=0.00, maximum=2.00,
            description="How far the wave swings, as a fraction of the distance between the two "
                        "poses. 1.00 reaches the second pose exactly. Above it the motion "
                        "overshoots past it and comes back; below it stops short. Everything is "
                        "measured between the two poses, so they have to differ: a wave between "
                        "two frames holding the same value stays flat, whatever the settings."),
    ),
    SPLINE: (
        ModeParameter(
            "tension", "Neighbour pull", default=0.50, minimum=0.00, maximum=1.50,
            description="How much the frames before and after the segment steer it. 0.50 is the "
                        "standard Catmull-Rom. 0.00 ignores them and eases through the poses "
                        "instead; above 0.50 the curve leans harder into where the motion is "
                        "going, with more overshoot (follow-through, whip)."),
        ModeParameter(
            "clamp", "Never overshoot the two poses", default=False, kind="bool",
            description="A spline can swing slightly past a pose before coming back, which is "
                        "usually good. Tick this where it cannot be allowed - a foot that would "
                        "sink through the floor, an axis already at its limit."),
    ),
    HOLD: (
        ModeParameter(
            "switch", "Snap point", default=1.00, minimum=0.05, maximum=1.00,
            description="Where in the segment the pose snaps to the second one. 1.00 never "
                        "snaps: every inserted frame repeats the first pose, which is the "
                        "classic hold. 0.50 holds the first pose for half the segment then the "
                        "second one - a two-step motion instead of a blend."),
    ),
}

# Offered with every curve: these say WHAT is being blended, not what shape the blend follows.
SHARED_PARAMETERS = (
    ModeParameter(
        "shortest_arc", "Turn the bones the short way (3D arc)", default=False, kind="bool",
        description="Blends each bone as a 3D rotation instead of three separate angles: the "
                    "bone makes one turn, around one axis, the short way round.\nLeave it off to "
                    "raise the frame rate of a motion (the poses are a frame apart, the two "
                    "blends agree, and the curves can still read the neighbouring frames). Turn "
                    "it on to morph between two poses far apart - a stance change, an arm going "
                    "from held out to down at the side. Blended angle by angle those bones swing "
                    "through poses that are in neither keyframe, the arms flying out through a "
                    "T-pose being the usual sight.\nOnly the bone rotations are concerned; the "
                    "skeleton position and the bone scales follow the curve as they always do."),
)

# Every setting the popup shows for a curve. MODE_PARAMETERS stays what that curve itself has to
# adjust, so a straight line still has nothing of its own.
def parameters_for(mode) -> tuple:
    return MODE_PARAMETERS.get(str(mode), ()) + SHARED_PARAMETERS


class InterpolationMode(str):
    """A curve name carrying the parameters the user set on it.

    It IS the mode string (`InterpolationMode("sine") == SINE`, `MODE_LABEL[mode]` works, and it
    can be used as a file name or a dict key), so it travels through every layer that only
    forwards `mode` without any of them having to know parameters exist. Only interpolate_value,
    at the very end, reads them.
    """

    def __new__(cls, name: str, parameters: dict = None):
        mode = super().__new__(cls, str(name))
        # Copying a mode keeps its parameters, so InterpolationMode(other_mode) is a valid clone.
        merged = dict(getattr(name, "parameters", None) or {})
        merged.update(parameters or {})
        mode.parameters = merged
        # Read once here rather than on every value: interpolate_value runs a few hundred thousand
        # times in one fps conversion, and a mode is built once per popup. A mode is therefore to
        # be treated as fixed - change one with with_parameters(), not by writing in `parameters`.
        mode.resolved_parameters = _resolve_parameters(str(mode), merged)
        return mode

    def with_parameters(self, **parameters) -> 'InterpolationMode':
        return InterpolationMode(self, parameters)

    def __repr__(self):
        return f"InterpolationMode({str(self)!r}, {self.parameters!r})"


def _resolve_parameters(name: str, given: dict) -> dict:
    """The values a curve will actually use: the ones given where they are usable, the defaults
    everywhere else. Unknown keys and out-of-range or unreadable values are dropped rather than
    trusted - an interpolation is never worth losing an edit over."""
    values = {}
    for spec in parameters_for(name):
        try:
            values[spec.key] = spec.clamp(given[spec.key]) if spec.key in given else spec.default
        except (TypeError, ValueError):
            values[spec.key] = spec.default
    return values


# The plain curves, resolved once at import. A mode with nothing set is by far the most common
# thing interpolate_value is handed, and it must not pay for the machinery.
_DEFAULT_PARAMETERS = {name: _resolve_parameters(name, {}) for name in MODE_PARAMETERS}
_NO_PARAMETER = {}


def parameters_of(mode) -> dict:
    """Every parameter of `mode`: the user's value where there is one, the default everywhere else.

    A plain string has none set, so it always describes the curve as it was before parameters
    existed. The dict that comes back is shared and meant to be read, not written.
    """
    if type(mode) is InterpolationMode:
        return mode.resolved_parameters
    return _DEFAULT_PARAMETERS.get(str(mode), _NO_PARAMETER)


def landing_ratio(mode) -> float:
    """Where the curve is at the very end of the segment, 1.0 being the second pose.

    The default of every blending curve lands exactly on it, but a sine set to an even number of
    half-waves comes back to the first pose (0.0) and a large amplitude sails past (> 1.0). That
    is legitimate - it is how one range does a whole up-and-down - but the two keyframes always
    keep their own values, so a curve landing anywhere else leaves a jump at the end of the range
    and the popups say so.
    """
    return shaped_step(1.0, mode)


def shaped_step(step: float, mode) -> float:
    """How far along the segment the curve is at `step`, as one number: 0.0 is the first pose and
    1.0 the second.

    The curves work channel by channel because that is all a number needs, but a rotation blended
    as a whole (the shortest_arc setting) has a single fraction to advance by, and this is it. The
    curves that read the frames outside the segment see none here - there is no "neighbouring
    value" of a fraction - so a spline flattens into an ease through the two poses.
    """
    return interpolate_value(None, 0.0, 1.0, None, step, mode)


def rotates_in_arc(mode) -> bool:
    """Whether bone rotations are to be blended as 3D rotations (rotation3d) rather than three
    angles each moving on their own."""
    return bool(parameters_of(mode).get("shortest_arc", False))


def describe_parameters(mode) -> str:
    """The non-default parameters of `mode`, for a report or a tooltip ("" when it is the plain
    curve)."""
    values = parameters_of(mode)
    changed = [f"{spec.label}: {values[spec.key]:g}" if spec.kind != "bool"
               else f"{spec.label}: {'yes' if values[spec.key] else 'no'}"
               for spec in parameters_for(mode)
               if values[spec.key] != spec.default]
    return ", ".join(changed)


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
    frames just outside it, or None where there is none. `mode` is a curve name, on its own or as
    an InterpolationMode carrying the parameters the user set on it (parameters_of fills in the
    defaults). Unknown modes fall back to linear rather than raising: an interpolation is never
    worth losing an edit over.
    """
    if mode == LINEAR:
        # The straight line has no settings at all, and this is by far the most travelled path:
        # answer before touching any of the parameter machinery.
        return value_a + (value_b - value_a) * step
    parameters = parameters_of(mode)
    if mode == HOLD:
        # The classic hold (snap point 1.00) never blends: every inserted frame repeats the pose
        # it starts from. Bring the snap point in and the segment becomes a two-step motion.
        switch = parameters["switch"]
        return value_b if switch < 1.0 and step >= switch else value_a
    if mode == SMOOTH:
        step = _smooth_shape(step, parameters)
    elif mode == SINE:
        step = _sine_shape(step, parameters)
    elif mode == SPLINE:
        value = _cardinal_spline(value_a if before is None else before, value_a, value_b,
                                 value_b if after is None else after, step,
                                 parameters["tension"])
        if parameters["clamp"]:
            value = min(max(value, min(value_a, value_b)), max(value_a, value_b))
        return value
    return value_a + (value_b - value_a) * step


def _smoothstep(t: float) -> float:
    """The classic ease in and out: zero slope at both ends."""
    return t * t * (3.0 - 2.0 * t)


def _smooth_shape(step: float, parameters: dict) -> float:
    """Smoothstep, moved towards one end by `bias` and diluted towards a straight line by
    `strength`. At the defaults (bias 0, strength 1) it IS smoothstep."""
    shape = _smoothstep(step)
    bias = parameters["bias"]
    if bias < 0.0:
        # Ease only where the motion starts: a slow build-up arriving at full speed.
        shape += (step * step - shape) * -bias
    elif bias > 0.0:
        # Ease only where it ends: leaves at full speed and settles into the second pose.
        shape += ((1.0 - (1.0 - step) ** 2) - shape) * bias
    strength = parameters["strength"]
    return step + (shape - step) * strength


def _sine_shape(step: float, parameters: dict) -> float:
    """A cosine wave over the segment: `half_waves` trips between the two poses, rounded (or
    straightened) by `curvature` and scaled by `amplitude`.

    One half-wave is the original curve - it leaves and arrives with no speed at all, so two
    segments put end to end round off where they meet instead of forming a corner. Two half-waves
    do the whole up-and-down inside one segment.
    """
    position = parameters["half_waves"] * step
    wave = (1.0 - math.cos(math.pi * position)) / 2.0
    curvature = parameters["curvature"]
    if curvature < 1.0:
        # Towards a triangle wave: the turnarounds sharpen into corners and the speed between
        # them becomes constant. At 0 it is a plain linear zig-zag.
        triangle = math.fmod(position, 2.0)
        triangle = triangle if triangle <= 1.0 else 2.0 - triangle
        wave = triangle + (wave - triangle) * curvature
    elif curvature > 1.0:
        # The other way: smoothstep applied to the wave itself flattens the turnarounds and
        # steepens the crossings - it hangs at the top, then drops.
        wave += (_smoothstep(min(1.0, max(0.0, wave))) - wave) * min(1.0, curvature - 1.0)
    return wave * parameters["amplitude"]


def _cardinal_spline(p0: float, p1: float, p2: float, p3: float, t: float,
                     tension: float = 0.5) -> float:
    """The cubic through p1 and p2 whose slope at each of them follows the line between its own
    neighbours, scaled by `tension`. At the default 0.5 this is uniform Catmull-Rom.

    Passes exactly through p1 (t=0) and p2 (t=1) - the original poses are preserved - and joins
    the neighbouring segments with a continuous speed. At tension 0 both slopes are flat and it
    becomes an ease in and out of the segment alone; above 0.5 it leans harder into where the
    motion is going and overshoots more.

    Duplicating an end (p0 = p1, or p3 = p2) is how the ends of a non-looping animation are
    handled: the curve then simply flattens into that end, like a one-sided ease.
    """
    t2 = t * t
    t3 = t2 * t
    slope_1 = tension * (p2 - p0)
    slope_2 = tension * (p3 - p1)
    return ((2.0 * t3 - 3.0 * t2 + 1.0) * p1
            + (t3 - 2.0 * t2 + t) * slope_1
            + (-2.0 * t3 + 3.0 * t2) * p2
            + (t3 - t2) * slope_2)
