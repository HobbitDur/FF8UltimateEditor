"""The settings each interpolation curve carries (FF8GameData/dat/interpolation.py).

The curves used to be five fixed shapes: a sine always made half a wave, a spline always let the
neighbours pull it exactly as much as Catmull-Rom does. They now have knobs - how many waves, how
round, how much pull, where a hold snaps - and the knobs travel inside the mode itself, so nothing
between the popup and the curve had to learn about them.

Two rules matter more than any particular shape and most of this file is about them:
  * the DEFAULTS reproduce the old curves exactly, so an untouched popup converts a file the same
    way it did before the settings existed;
  * a mode carrying settings is still the mode string, because every layer in between (the fps
    converter, the splitter, the manager, the batch report) only forwards it.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from FF8GameData.dat import interpolation
from FF8GameData.monsterdata import Animation, AnimationFrame, Bone, PositionType, RotationType

STEP_LIST = [index / 16 for index in range(17)]


def at(mode, step, value_a=0.0, value_b=100.0, before=None, after=None):
    return interpolation.interpolate_value(before, value_a, value_b, after, step, mode)


# ---------------------------------------------------------------------------
# The defaults are the curves as they were before they had settings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_an_untouched_mode_is_exactly_the_plain_curve(mode):
    """The one rule that protects every file converted before this existed: wrapping a mode
    without setting anything must not move a single value."""
    wrapped = interpolation.InterpolationMode(mode)
    for step in STEP_LIST:
        assert at(wrapped, step, 10.0, 20.0, before=-5.0, after=41.0) == at(
            mode, step, 10.0, 20.0, before=-5.0, after=41.0)


@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_setting_a_parameter_to_its_own_default_changes_nothing(mode):
    defaults = {spec.key: spec.default for spec in interpolation.MODE_PARAMETERS[mode]}
    explicit = interpolation.InterpolationMode(mode, defaults)
    for step in STEP_LIST:
        assert at(explicit, step, 10.0, 20.0, before=0.0, after=30.0) == at(
            mode, step, 10.0, 20.0, before=0.0, after=30.0)


def test_the_linear_curve_has_nothing_to_adjust():
    """A straight line is a straight line: the popup shows no settings for it rather than
    inventing some."""
    assert interpolation.MODE_PARAMETERS[interpolation.LINEAR] == ()


# ---------------------------------------------------------------------------
# A mode carrying settings is still the mode
# ---------------------------------------------------------------------------

def test_a_mode_with_settings_still_compares_and_looks_up_like_the_plain_string():
    """Everything between the popup and the curve treats the mode as a string - it is compared to
    SINE, used as a dict key, even used as a directory name by the batch converter."""
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 4})
    assert mode == interpolation.SINE
    assert mode in interpolation.ALL_MODES
    assert interpolation.MODE_LABEL[mode] == interpolation.MODE_LABEL[interpolation.SINE]
    assert str(mode) == "sine"
    assert os.path.join("folder", mode) == os.path.join("folder", "sine")


def test_copying_a_mode_keeps_its_settings():
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 4})
    assert interpolation.InterpolationMode(mode).parameters == {"half_waves": 4}
    assert mode.with_parameters(amplitude=1.5).parameters == {"half_waves": 4, "amplitude": 1.5}


def test_a_plain_string_reads_as_the_default_settings():
    values = interpolation.parameters_of(interpolation.SINE)
    assert values == {spec.key: spec.default
                      for spec in interpolation.MODE_PARAMETERS[interpolation.SINE]}


def test_junk_settings_fall_back_to_the_defaults_instead_of_raising():
    """Same rule as an unknown mode: an interpolation is never worth losing an edit over."""
    mode = interpolation.InterpolationMode(
        interpolation.SINE, {"half_waves": "not a number", "unknown": 3, "amplitude": 99.0})
    values = interpolation.parameters_of(mode)
    assert values["half_waves"] == 1                 # unreadable -> default
    assert "unknown" not in values                   # not a setting of this curve -> dropped
    assert values["amplitude"] == 2.0                # out of range -> clamped to the maximum
    assert at(mode, 0.0) == 0.0                      # and the curve still works


def test_an_unknown_mode_has_no_settings_and_still_blends_linearly():
    assert interpolation.parameters_of("something-that-does-not-exist") == {}
    assert at("something-that-does-not-exist", 0.5) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Sine: the number of waves, their shape, how far they swing
# ---------------------------------------------------------------------------

def test_two_half_waves_go_up_and_come_back_inside_one_range():
    """The point of the setting: a hover no longer needs three keyframes and two operations - one
    range does the whole up-and-down."""
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 2})
    assert at(mode, 0.0) == pytest.approx(0.0)
    assert at(mode, 0.5) == pytest.approx(100.0)     # the top, halfway through
    assert at(mode, 1.0) == pytest.approx(0.0)       # and back where it started


def test_four_half_waves_do_it_twice():
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 4})
    assert at(mode, 0.25) == pytest.approx(100.0)
    assert at(mode, 0.5) == pytest.approx(0.0)
    assert at(mode, 0.75) == pytest.approx(100.0)


def test_an_odd_number_of_half_waves_still_arrives_on_the_second_pose():
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 3})
    assert at(mode, 1.0) == pytest.approx(100.0)


def test_curvature_zero_makes_the_wave_a_straight_zig_zag():
    """Fully straightened, one half-wave is just a linear ramp and two are a linear up and down -
    the corners are sharp, which is exactly what the setting is for."""
    straight = interpolation.InterpolationMode(interpolation.SINE, {"curvature": 0.0})
    for step in STEP_LIST:
        assert at(straight, step) == pytest.approx(at(interpolation.LINEAR, step))

    triangle = interpolation.InterpolationMode(interpolation.SINE,
                                               {"curvature": 0.0, "half_waves": 2})
    assert at(triangle, 0.25) == pytest.approx(50.0)
    assert at(triangle, 0.75) == pytest.approx(50.0)


def test_more_curvature_flattens_the_turnaround():
    """Above 1 the wave hangs at the top instead of rounding through it, and the crossing in the
    middle gets steeper in exchange."""
    plain = interpolation.SINE
    flat = interpolation.InterpolationMode(interpolation.SINE, {"curvature": 2.0})
    hang = interpolation.InterpolationMode(interpolation.SINE,
                                           {"curvature": 2.0, "half_waves": 2})
    plain_hang = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 2})
    # nearer the top for longer around the apex...
    assert at(hang, 0.4) > at(plain_hang, 0.4)
    # ...and covering more ground in the middle of a one-way trip
    assert (at(flat, 0.55) - at(flat, 0.45)) > (at(plain, 0.55) - at(plain, 0.45))


def test_amplitude_over_one_overshoots_the_second_pose_and_comes_back():
    mode = interpolation.InterpolationMode(interpolation.SINE, {"amplitude": 1.5})
    assert max(at(mode, step) for step in STEP_LIST) > 100.0
    mode = interpolation.InterpolationMode(interpolation.SINE, {"amplitude": 0.5})
    assert max(at(mode, step) for step in STEP_LIST) == pytest.approx(50.0)


def test_a_wave_between_two_identical_poses_stays_flat():
    """Everything is measured between the two poses, so there is nothing to swing between when
    they hold the same value. Said in the amplitude description, checked here."""
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 2})
    assert all(at(mode, step, 70.0, 70.0) == 70.0 for step in STEP_LIST)


# ---------------------------------------------------------------------------
# Smooth: how much ease, and on which end
# ---------------------------------------------------------------------------

def test_no_ease_strength_is_a_straight_line():
    mode = interpolation.InterpolationMode(interpolation.SMOOTH, {"strength": 0.0})
    for step in STEP_LIST:
        assert at(mode, step) == pytest.approx(at(interpolation.LINEAR, step))


def test_half_the_ease_strength_sits_between_linear_and_the_full_ease():
    half = interpolation.InterpolationMode(interpolation.SMOOTH, {"strength": 0.5})
    assert at(interpolation.SMOOTH, 0.25) < at(half, 0.25) < at(interpolation.LINEAR, 0.25)


def test_a_negative_bias_eases_only_the_start():
    """It builds up and arrives at full speed: the last tenth of the range covers more ground than
    the first one."""
    mode = interpolation.InterpolationMode(interpolation.SMOOTH, {"bias": -1.0})
    assert (at(mode, 0.1) - at(mode, 0.0)) < (at(mode, 1.0) - at(mode, 0.9))
    assert at(mode, 1.0) == pytest.approx(100.0)


def test_a_positive_bias_eases_only_the_end():
    mode = interpolation.InterpolationMode(interpolation.SMOOTH, {"bias": 1.0})
    assert (at(mode, 0.1) - at(mode, 0.0)) > (at(mode, 1.0) - at(mode, 0.9))
    assert at(mode, 1.0) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Spline: how much the neighbours pull, and whether it may overshoot
# ---------------------------------------------------------------------------

def test_no_neighbour_pull_eases_through_the_segment_alone():
    """At 0 both slopes are flat, which is an ease in and out - and it must then ignore the
    neighbours completely, however far away they are."""
    mode = interpolation.InterpolationMode(interpolation.SPLINE, {"tension": 0.0})
    for step in STEP_LIST:
        assert at(mode, step, before=-500.0, after=900.0) == pytest.approx(
            at(mode, step, before=0.0, after=0.0))
        assert at(mode, step, before=-500.0, after=900.0) == pytest.approx(
            at(interpolation.SMOOTH, step))


def test_more_pull_means_more_overshoot():
    """A segment followed by a much bigger jump: the harder the neighbours pull, the further the
    curve leans towards where the motion is going."""
    before, after = 0.0, 900.0
    values = [at(interpolation.InterpolationMode(interpolation.SPLINE, {"tension": tension}),
                 0.5, 10.0, 20.0, before, after) for tension in (0.0, 0.5, 1.5)]
    assert values[0] > values[1] > values[2]


def test_the_clamp_keeps_the_curve_between_the_two_poses():
    """For an axis that cannot go past its pose - a foot through the floor - whatever the pull."""
    pulled = interpolation.InterpolationMode(interpolation.SPLINE, {"tension": 1.5})
    clamped = pulled.with_parameters(clamp=True)
    # A huge jump waiting after the segment makes the curve dip well under the first pose before
    # swinging up into it - the kind of swing the clamp exists for.
    assert at(pulled, 0.5, 10.0, 20.0, before=0.0, after=900.0) < 10.0
    for step in STEP_LIST:
        assert 10.0 <= at(clamped, step, 10.0, 20.0, before=0.0, after=900.0) <= 20.0


# ---------------------------------------------------------------------------
# Hold: where it snaps
# ---------------------------------------------------------------------------

def test_the_snap_point_turns_a_hold_into_a_two_step_motion():
    mode = interpolation.InterpolationMode(interpolation.HOLD, {"switch": 0.5})
    assert at(mode, 0.0) == 0.0
    assert at(mode, 0.49) == 0.0
    assert at(mode, 0.5) == 100.0
    assert at(mode, 0.99) == 100.0


def test_the_default_snap_point_never_snaps():
    for step in (0.0, 0.25, 0.5, 0.99):
        assert at(interpolation.HOLD, step) == 0.0


# ---------------------------------------------------------------------------
# Where the curve lands, which the popups warn about
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", [interpolation.LINEAR, interpolation.SMOOTH,
                                  interpolation.SINE, interpolation.SPLINE])
def test_a_default_blending_curve_lands_on_the_second_pose(mode):
    assert interpolation.landing_ratio(mode) == pytest.approx(1.0)


def test_an_even_wave_count_lands_back_on_the_first_pose():
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 2})
    assert interpolation.landing_ratio(mode) == pytest.approx(0.0)


def test_the_settings_that_were_changed_can_be_listed():
    """For a tooltip or a report: only what the user actually moved."""
    assert interpolation.describe_parameters(interpolation.SINE) == ""
    mode = interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 2})
    assert "2" in interpolation.describe_parameters(mode)
    assert "Amplitude" not in interpolation.describe_parameters(mode)


# ---------------------------------------------------------------------------
# All the way through a real animation
# ---------------------------------------------------------------------------

def _straight_line_animation(nb_frames=5, nb_bones=2):
    """A tiny animation whose root walks along Z and whose bone turns, both at a steady rate."""
    bones = []
    for index in range(nb_bones):
        bone = Bone()
        bone.parent_id = 0xFFFF if index == 0 else index - 1
        bone.set_size(-1.0)
        bones.append(bone)

    anim = Animation()
    for frame_index in range(nb_frames):
        frame = AnimationFrame(nb_bones)
        frame.position = [PositionType(0, 0, axis=0), PositionType(0, 0, axis=1),
                          PositionType(0, 100 * frame_index, axis=2)]
        for bone_index in range(nb_bones):
            frame.rotation_vector_data[bone_index] = [
                RotationType(True, 0, 0), RotationType(True, 0, 0),
                RotationType(True, 0, 64 * frame_index)]
        frame.set_all_bones_matrix(bones)
        anim.frames.append(frame)
    return anim, bones


def _positions(anim):
    return [frame.position[2].get_pos_raw() for frame in anim.frames]


def test_the_settings_reach_the_frames_a_conversion_inserts():
    """Guards the wiring: the mode travels from the popup to the curve through
    create_interpolated_frames without anything on the way flattening it back to a bare name."""
    plain, bones = _straight_line_animation()
    plain.create_interpolated_frames(bones, 4, smooth_loop=False, mode=interpolation.SINE)
    waved, bones = _straight_line_animation()
    waved.create_interpolated_frames(bones, 4, smooth_loop=False,
                                     mode=interpolation.InterpolationMode(interpolation.SINE,
                                                                          {"half_waves": 2}))
    assert _positions(plain) != _positions(waved)


def test_the_original_frames_survive_whatever_the_settings():
    """The rule no curve and no setting may break: the frames that were there keep their values
    and their indices - the sequences and the AI address them by index."""
    source, bones = _straight_line_animation()
    original = _positions(source)

    for mode in (interpolation.InterpolationMode(interpolation.SINE,
                                                 {"half_waves": 3, "amplitude": 2.0}),
                 interpolation.InterpolationMode(interpolation.SPLINE, {"tension": 1.5}),
                 interpolation.InterpolationMode(interpolation.HOLD, {"switch": 0.25}),
                 interpolation.InterpolationMode(interpolation.SMOOTH, {"bias": -1.0})):
        anim, bones = _straight_line_animation()
        anim.create_interpolated_frames(bones, 4, smooth_loop=False, mode=mode)
        assert len(anim.frames) == (len(original) - 1) * 4 + 1
        for source_index, value in enumerate(original):
            assert anim.frames[source_index * 4].position[2].get_pos_raw() == value


# ---------------------------------------------------------------------------
# The popup
# ---------------------------------------------------------------------------

def _selector(mode=interpolation.SINE):
    from SmallWidget.interpolationselector import InterpolationSelector

    selector = InterpolationSelector(None, mode)
    return selector


def test_the_popup_shows_one_widget_per_setting_of_the_selected_curve():
    selector = _selector(interpolation.SINE)
    assert sorted(selector._widget_dict) == sorted(
        spec.key for spec in interpolation.MODE_PARAMETERS[interpolation.SINE])
    selector.set_mode(interpolation.LINEAR)
    assert selector._widget_dict == {}          # nothing to adjust on a straight line


def test_the_popup_hands_back_the_settings_inside_the_mode():
    selector = _selector(interpolation.SINE)
    selector._widget_dict["half_waves"].setValue(4)
    mode = selector.get_mode()
    assert mode == interpolation.SINE                       # still just the curve, for the callers
    assert interpolation.parameters_of(mode)["half_waves"] == 4


def test_the_popup_keeps_the_settings_of_a_curve_while_another_one_is_selected():
    """Trying the curves out one after the other must not throw away what was already dialled
    in."""
    selector = _selector(interpolation.SINE)
    selector._widget_dict["amplitude"].setValue(1.5)
    selector.set_mode(interpolation.SPLINE)
    selector.set_mode(interpolation.SINE)
    assert interpolation.parameters_of(selector.get_mode())["amplitude"] == pytest.approx(1.5)
    assert selector._widget_dict["amplitude"].value() == pytest.approx(1.5)


def test_the_popup_can_put_a_curve_back_to_its_plain_shape():
    selector = _selector(interpolation.SINE)
    selector._widget_dict["half_waves"].setValue(4)
    selector.reset_parameters()
    for step in STEP_LIST:
        assert at(selector.get_mode(), step) == pytest.approx(at(interpolation.SINE, step))


def test_the_popup_takes_the_settings_of_the_mode_it_is_given():
    from SmallWidget.interpolationselector import InterpolationSelector

    selector = InterpolationSelector(
        None, interpolation.InterpolationMode(interpolation.SINE, {"half_waves": 4}))
    assert selector.get_mode() == interpolation.SINE
    assert interpolation.parameters_of(selector.get_mode())["half_waves"] == 4
    assert selector._widget_dict["half_waves"].value() == 4


def test_the_preview_draws_the_curve_that_was_chosen():
    """The preview samples the curve itself, so it can never show something else than what the
    frames will get - which is the only reason to trust it."""
    selector = _selector(interpolation.SINE)
    selector._widget_dict["half_waves"].setValue(2)
    samples = dict(selector._preview.sample_list())
    assert samples[0.5] == pytest.approx(1.0)      # the top of the wave, halfway
    assert samples[1.0] == pytest.approx(0.0)      # back to the first pose


def test_the_popup_warns_when_the_curve_does_not_arrive_on_the_second_pose():
    selector = _selector(interpolation.SINE)
    assert selector._landing_warning.text() == ""
    selector._widget_dict["half_waves"].setValue(2)
    assert "first pose" in selector._landing_warning.text()
    selector.reset_parameters()
    assert selector._landing_warning.text() == ""
