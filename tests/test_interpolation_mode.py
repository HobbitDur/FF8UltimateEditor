"""The interpolation curves offered wherever the editor inserts in-between frames.

Two features insert frames - the fps conversion (15 fps native -> 30/60) and the manual
"interpolate between two frames" - and both now let the user pick the curve instead of always
blending linearly (FF8GameData/dat/interpolation.py).

The property that matters most is the same for every mode and is what these tests spend the most
effort on: the ORIGINAL frames come out untouched, and there are exactly as many inserted frames
as before. Animation ids and frame indices are addressed by the animation sequences and the AI, so
a curve is only ever allowed to change the values of the frames it adds.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from FF8GameData.dat import interpolation
from FF8GameData.monsterdata import (Animation, AnimationFrame, Bone, PositionType, RotationType)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DATA_DIR = os.path.join(REPO, "FF8GameData")
BATTLE_DIR = os.path.join(REPO, "extracted_files", "battle")


# ---------------------------------------------------------------------------
# The curves themselves (no model needed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_every_mode_starts_on_the_first_value(mode):
    """Step 0 is the segment's own start, whatever the curve - an inserted frame never begins
    somewhere the animation was not."""
    assert interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, 0.0, mode) == 10.0


@pytest.mark.parametrize("mode", [interpolation.LINEAR, interpolation.SMOOTH, interpolation.SPLINE])
def test_the_blending_modes_end_on_the_second_value(mode):
    """Step 1 is the segment's end. Hold is excluded on purpose: not blending at all is the point
    of it."""
    assert interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, 1.0, mode) == pytest.approx(20.0)


def test_hold_repeats_the_pose_it_starts_from():
    for step in (0.0, 0.25, 0.5, 0.99):
        assert interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, step,
                                               interpolation.HOLD) == 10.0


def test_linear_moves_at_a_constant_speed():
    values = [interpolation.interpolate_value(None, 0.0, 100.0, None, step / 10, interpolation.LINEAR)
              for step in range(11)]
    gaps = [b - a for a, b in zip(values, values[1:])]
    assert all(gap == pytest.approx(gaps[0]) for gap in gaps)


def test_smooth_starts_and_ends_slower_than_linear():
    """Ease in and out: behind linear in the first half, ahead of it in the second, symmetric
    about the middle."""
    def at(step, mode):
        return interpolation.interpolate_value(None, 0.0, 100.0, None, step, mode)

    assert at(0.1, interpolation.SMOOTH) < at(0.1, interpolation.LINEAR)
    assert at(0.9, interpolation.SMOOTH) > at(0.9, interpolation.LINEAR)
    assert at(0.5, interpolation.SMOOTH) == pytest.approx(50.0)
    assert at(0.25, interpolation.SMOOTH) == pytest.approx(100.0 - at(0.75, interpolation.SMOOTH))


def test_sine_leaves_and_arrives_with_no_speed():
    """Half a cosine period: flat at both ends. That is what rounds off the apex when an axis goes
    up over one range and down over the next - the point of having it for positions."""
    def at(step):
        return interpolation.interpolate_value(None, 0.0, 100.0, None, step, interpolation.SINE)

    assert at(0.0) == pytest.approx(0.0)
    assert at(1.0) == pytest.approx(100.0)
    assert at(0.5) == pytest.approx(50.0)
    # The first and last tenth cover far less ground than the middle one
    assert (at(0.1) - at(0.0)) < (at(0.55) - at(0.45))
    assert (at(1.0) - at(0.9)) < (at(0.55) - at(0.45))


def test_sine_is_symmetric_about_the_middle():
    def at(step):
        return interpolation.interpolate_value(None, 0.0, 100.0, None, step, interpolation.SINE)

    for step in (0.1, 0.25, 0.4):
        assert at(step) == pytest.approx(100.0 - at(1.0 - step))


def test_sine_rounds_the_turnaround_of_an_up_and_down_movement():
    """The three-keyframe recipe: bottom, top, bottom. Around the top, sine must be flatter than
    linear - that is the difference between floating up and stopping dead."""
    def height(mode, step, going_up):
        # second half of the climb, then first half of the fall
        if going_up:
            return interpolation.interpolate_value(None, 0.0, 100.0, None, step, mode)
        return interpolation.interpolate_value(None, 100.0, 0.0, None, step, mode)

    sine_gap = height(interpolation.SINE, 1.0, True) - height(interpolation.SINE, 0.9, True)
    linear_gap = height(interpolation.LINEAR, 1.0, True) - height(interpolation.LINEAR, 0.9, True)
    assert sine_gap < linear_gap
    sine_gap = height(interpolation.SINE, 0.0, False) - height(interpolation.SINE, 0.1, False)
    linear_gap = height(interpolation.LINEAR, 0.0, False) - height(interpolation.LINEAR, 0.1, False)
    assert sine_gap < linear_gap


def test_spline_keeps_a_constant_speed_motion_constant():
    """Evenly spaced keyframes = the motion is already at constant speed, and a curve that flows
    through them has nothing to bend: the spline must agree with linear there."""
    for step in (0.25, 0.5, 0.75):
        spline = interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, step, interpolation.SPLINE)
        linear = interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, step, interpolation.LINEAR)
        assert spline == pytest.approx(linear)


def test_spline_bends_towards_where_the_motion_is_going():
    """A segment followed by a much bigger jump is the start of an acceleration, so the spline
    stays behind the straight line through the segment instead of ignoring what comes next."""
    step = 0.5
    spline = interpolation.interpolate_value(0.0, 10.0, 20.0, 200.0, step, interpolation.SPLINE)
    linear = interpolation.interpolate_value(0.0, 10.0, 20.0, 200.0, step, interpolation.LINEAR)
    assert spline != pytest.approx(linear)
    assert spline < linear


def test_spline_falls_back_to_the_segment_at_the_ends_of_an_animation():
    """No neighbour (the first/last segment of a one-shot animation): the curve flattens into that
    end rather than raising - it must still produce a usable in-between."""
    value = interpolation.interpolate_value(None, 10.0, 20.0, None, 0.5, interpolation.SPLINE)
    assert 10.0 < value < 20.0


def test_an_unknown_mode_falls_back_to_linear():
    """An interpolation is never worth losing an edit over."""
    assert interpolation.interpolate_value(0.0, 10.0, 20.0, 30.0, 0.5,
                                           "something-that-does-not-exist") == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Rotations wrap around: 4090 and -6 raw are the same angle
# ---------------------------------------------------------------------------

def test_a_rotation_is_unwrapped_onto_the_nearest_turn():
    assert interpolation.unwrap_rotation_raw(4090, 6) == 4102       # forwards past the wrap
    assert interpolation.unwrap_rotation_raw(6, 4090) == -6         # backwards past the wrap
    assert interpolation.unwrap_rotation_raw(1000, 1200) == 1200    # nothing to unwrap


@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_a_rotation_across_the_wrap_takes_the_short_way(mode):
    """4090 -> 6 raw is 12 units forwards, not 4084 backwards. Every mode works on unwrapped
    values, so none of them sends the bone the long way round."""
    start, end = 4090, interpolation.unwrap_rotation_raw(4090, 6)
    middle = interpolation.interpolate_value(None, start, end, None, 0.5, mode)
    assert 4084 <= middle <= 4102


# ---------------------------------------------------------------------------
# On a real animation
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


@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_the_original_frames_survive_the_conversion_untouched(mode):
    """Whatever the curve: same number of frames out, and every original pose still there, at the
    index the conversion puts it (frame k of the source becomes frame k * factor). The sequences
    and the AI address frames by index, so this is the rule no mode may break."""
    factor = 4
    source, bones = _straight_line_animation()
    original = [(frame.position[2].get_pos_raw(),
                 int(frame.rotation_vector_data[1][2].get_rotate_raw()))
                for frame in source.frames]

    anim, bones = _straight_line_animation()
    anim.create_interpolated_frames(bones, factor, smooth_loop=False, mode=mode)

    assert len(anim.frames) == (len(original) - 1) * factor + 1
    for source_index, expected in enumerate(original):
        frame = anim.frames[source_index * factor]
        assert (frame.position[2].get_pos_raw(),
                int(frame.rotation_vector_data[1][2].get_rotate_raw())) == expected


@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_every_mode_produces_the_same_frame_count(mode):
    """The curve changes the values, never how many frames there are - the frame count IS the
    animation's duration for the engine (one frame per tick)."""
    anim, bones = _straight_line_animation()
    anim.create_interpolated_frames(bones, 4, smooth_loop=False, mode=mode)
    assert len(anim.frames) == 17


def test_hold_leaves_the_inserted_frames_on_the_pose_before_them():
    anim, bones = _straight_line_animation()
    anim.create_interpolated_frames(bones, 4, smooth_loop=False, mode=interpolation.HOLD)
    # Frames 1..3 repeat frame 0, 5..7 repeat frame 4, ...
    for index in range(1, 4):
        assert anim.frames[index].position[2].get_pos_raw() == anim.frames[0].position[2].get_pos_raw()
        assert anim.frames[index + 4].position[2].get_pos_raw() == anim.frames[4].position[2].get_pos_raw()


def _converted_pair(mode_a, mode_b, factor=4, smooth_loop=False):
    """The same animation converted twice, once per mode, as two frame lists."""
    converted = []
    for mode in (mode_a, mode_b):
        anim, bones = _straight_line_animation()
        anim.create_interpolated_frames(bones, factor, smooth_loop=smooth_loop, mode=mode)
        converted.append(anim.frames)
    return converted


def test_spline_matches_linear_inside_a_steady_motion():
    """The spline only bends where the motion changes speed. On a steady one it has nothing to
    bend, so every segment that HAS both its neighbours must come out exactly like linear - a good
    check that the neighbour frames are read in the right order (swap them and this fails).

    With 5 source frames at factor 4, frames 4..12 are the two interior segments; the first and
    last segments are checked below, where the fallback is the point."""
    linear_frames, spline_frames = _converted_pair(interpolation.LINEAR, interpolation.SPLINE)
    for index in range(4, 13):
        assert (linear_frames[index].position[2].get_pos_raw()
                == spline_frames[index].position[2].get_pos_raw())
        assert (int(linear_frames[index].rotation_vector_data[1][2].get_rotate_raw())
                == int(spline_frames[index].rotation_vector_data[1][2].get_rotate_raw()))


def test_spline_eases_out_of_the_ends_of_a_one_shot_animation():
    """The very first and very last segments of a non-looping animation have no frame beyond them
    to flow from, so the spline flattens into that end (a one-sided ease) instead of running
    straight. That is deliberate - the animation does start and stop there."""
    linear_frames, spline_frames = _converted_pair(interpolation.LINEAR, interpolation.SPLINE)
    first_inserted = 1
    last_inserted = len(linear_frames) - 2
    assert (spline_frames[first_inserted].position[2].get_pos_raw()
            < linear_frames[first_inserted].position[2].get_pos_raw())
    assert (spline_frames[last_inserted].position[2].get_pos_raw()
            > linear_frames[last_inserted].position[2].get_pos_raw())


def test_a_looping_animation_finds_its_neighbours_across_the_wrap():
    """A smoothed loop has no ends: the frame before the first one is the LAST one. The spline
    must use it, so the seam of a loop is interpolated differently from the same segment in a
    one-shot animation, where there is nothing behind frame 0."""
    looping, one_shot = (_converted_pair(interpolation.SPLINE, interpolation.SPLINE,
                                         smooth_loop=wrap)[0] for wrap in (True, False))
    assert (looping[1].position[2].get_pos_raw() != one_shot[1].position[2].get_pos_raw())


def test_smooth_and_linear_disagree_on_the_frames_they_insert():
    """Guards the wiring: if `mode` were dropped somewhere between create_interpolated_frames and
    the curve, every mode would silently produce identical output and most tests here would still
    pass."""
    linear_anim, bones = _straight_line_animation()
    linear_anim.create_interpolated_frames(bones, 4, smooth_loop=False, mode=interpolation.LINEAR)
    smooth_anim, bones = _straight_line_animation()
    smooth_anim.create_interpolated_frames(bones, 4, smooth_loop=False, mode=interpolation.SMOOTH)

    inserted_differ = [index for index in range(len(linear_anim.frames))
                       if index % 4 != 0
                       and (linear_anim.frames[index].position[2].get_pos_raw()
                            != smooth_anim.frames[index].position[2].get_pos_raw())]
    assert inserted_differ


# ---------------------------------------------------------------------------
# Through the editor, on a real file
# ---------------------------------------------------------------------------

def _accept_dialogs(monkeypatch):
    """Make every modal dialog answer OK immediately, so the popups can be exercised headless."""
    from PyQt6.QtWidgets import QDialog
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


def _mock_viewer():
    from unittest.mock import MagicMock
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    manager = MagicMock()
    manager.enemy.bone_section = None
    manager.bone_data = []
    return Ifrit3DWidget(manager, show_controls=False)


def test_the_fps_popup_asks_for_the_rate_and_the_curve_together(monkeypatch):
    """One popup for both questions, defaulting to the curve meant for resampling a motion."""
    _accept_dialogs(monkeypatch)
    target_fps, mode = _mock_viewer()._ask_target_fps("To 30/60 FPS")
    assert target_fps == 30                                       # the safer default rate
    assert mode == interpolation.DEFAULT_FOR_FPS_CONVERSION


def test_the_manual_insert_popup_asks_everything_at_once(monkeypatch):
    """Which two frames, how many to insert and which curve - defaulting to the pose-to-pose
    curve, which is what picking two frames by hand usually means."""
    _accept_dialogs(monkeypatch)
    frame_a, frame_b, count, mode = _mock_viewer()._ask_interpolation_settings(
        "Interpolate between two frames", nb_frames=10)
    assert (frame_a, frame_b) == (0, 1)     # the shown frame and the next one
    assert count >= 1
    assert mode == interpolation.DEFAULT_FOR_MANUAL_INSERT


def test_the_batch_dialog_hands_back_the_chosen_curve():
    from Ifrit.fpsbatchdialog import FpsBatchDialog

    dialog = FpsBatchDialog(None, ["c0m003.dat"])
    assert dialog.get_interpolation_mode() == interpolation.DEFAULT_FOR_FPS_CONVERSION
    dialog._interpolation.set_mode(interpolation.HOLD)
    assert dialog.get_interpolation_mode() == interpolation.HOLD


def test_the_selector_offers_every_mode_and_returns_the_chosen_one():
    """The popup is the only way a user reaches any of this, so it must list them all and hand
    back the mode itself (not its label)."""
    from SmallWidget.interpolationselector import InterpolationSelector

    selector = InterpolationSelector(None, interpolation.SPLINE)
    assert selector.get_mode() == interpolation.SPLINE
    for mode in interpolation.ALL_MODES:
        selector.set_mode(mode)
        assert selector.get_mode() == mode


@pytest.mark.ff8data("extracted_files/battle/c0m003.dat")
def test_the_batch_fps_conversion_uses_the_mode_it_is_given(tmp_path):
    """The batch converter reaches the curve through a different path than the 3D tab (it reparses
    each file and may split animations), so it gets its own check that the choice is not dropped
    on the way."""
    import shutil

    from Ifrit.ifritmanager import IfritManager

    manager = IfritManager(GAME_DATA_DIR)

    def converted_frames(mode):
        # One directory per mode, keeping the canonical file name: the batch converter refuses
        # anything not named like a stock model file (c0mXXX / dXcYYY / dXwYYY)
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        copy_path = str(mode_dir / "c0m003.dat")
        shutil.copy(os.path.join(BATTLE_DIR, "c0m003.dat"), copy_path)
        report = manager.convert_file_list_to_fps([copy_path], 30, mode=mode)[0]
        assert not report['error'] and report['nb_converted']
        enemy = manager.parse_file(copy_path)
        return [[int(rot.get_rotate_raw()) for bone in frame.rotation_vector_data for rot in bone]
                for frame in enemy.animation_data.animations[0].frames]

    linear = converted_frames(interpolation.LINEAR)
    hold = converted_frames(interpolation.HOLD)

    assert len(linear) == len(hold)      # the curve never changes the frame count
    assert linear != hold                # ...but it does change what is in the inserted frames


@pytest.mark.ff8data("extracted_files/battle/c0m003.dat")
@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_a_manual_insertion_survives_save_and_reopen(mode, tmp_path):
    """Each curve end to end: insert frames in a real model, save, re-open, and the animation is
    the one that was built (the encoder stores frames as deltas with per-value bit widths, so a
    curve that produces bigger jumps than linear must still be storable)."""
    from Ifrit.ifritmanager import IfritManager

    manager = IfritManager(GAME_DATA_DIR)
    manager.enemy = manager.parse_file(os.path.join(BATTLE_DIR, "c0m003.dat"))
    manager._ensure_matrices()

    nb_before = manager.enemy.animation_data.animations[0].get_nb_frame()
    nb_inserted = manager.interpolate_between_frames(0, 2, 3, 3, mode=mode)
    assert nb_inserted == 3

    def rotations(mgr):
        return [[[int(rot.get_rotate_raw()) for rot in bone] for bone in frame.rotation_vector_data]
                for frame in mgr.enemy.animation_data.animations[0].frames]

    before = rotations(manager)
    saved = str(tmp_path / "interpolated.dat")
    manager.save_file(saved)

    reopened = IfritManager(GAME_DATA_DIR, game_data=manager.game_data)
    reopened.enemy = reopened.parse_file(saved)
    reopened._ensure_matrices()

    assert reopened.enemy.animation_data.animations[0].get_nb_frame() == nb_before + 3
    assert rotations(reopened) == before
