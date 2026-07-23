"""Re-valuing one root-position axis across frames that already exist.

Each of the three Pos X/Y/Z rows of the Frame Position tab has an "Interpolate…" button: pick two
frames that already exist, and every frame BETWEEN them has that one axis rewritten along the
chosen curve. Unlike the fps conversion and the manual insert, nothing is added or removed here -
the animation keeps its length, so the sequences and the AI (which name frames by index) are not
disturbed, and only the chosen channel moves.

The up-and-down movement this exists for is the three-keyframe recipe: bottom, top, bottom on
Pos Y, then run it on each half with the sine curve.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from FF8GameData.dat import interpolation
from Ifrit.ifritmanager import IfritManager

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DATA_DIR = os.path.join(REPO, "FF8GameData")
BATTLE_DIR = os.path.join(REPO, "extracted_files", "battle")
MONSTER_FILE = "c0m003.dat"

pytestmark = pytest.mark.ff8data(f"extracted_files/battle/{MONSTER_FILE}")


@pytest.fixture(scope="module")
def game_data():
    return IfritManager(GAME_DATA_DIR).game_data


@pytest.fixture
def manager(game_data):
    mgr = IfritManager(GAME_DATA_DIR, game_data=game_data)
    mgr.enemy = mgr.parse_file(os.path.join(BATTLE_DIR, MONSTER_FILE))
    mgr._ensure_matrices()
    return mgr


def _positions(manager, anim_id, axis):
    return [frame.position[axis].get_pos_raw()
            for frame in manager.enemy.animation_data.animations[anim_id].frames]


def _rotations(manager, anim_id):
    return [[[int(rot.get_rotate_raw()) for rot in bone] for bone in frame.rotation_vector_data]
            for frame in manager.enemy.animation_data.animations[anim_id].frames]


def _long_animation(manager, min_frames=6):
    """An animation of the loaded file with enough frames to interpolate over."""
    for anim_id, anim in enumerate(manager.enemy.animation_data.animations):
        if anim.get_nb_frame() >= min_frames:
            return anim_id
    pytest.skip(f"no animation with {min_frames} frames in {MONSTER_FILE}")


def test_the_two_chosen_frames_keep_their_own_value(manager):
    anim_id = _long_animation(manager)
    before = _positions(manager, anim_id, 1)
    manager.interpolate_frame_position(anim_id, 1, 0, 5, mode=interpolation.LINEAR)
    after = _positions(manager, anim_id, 1)
    assert after[0] == before[0]
    assert after[5] == before[5]


def test_the_frames_in_between_follow_the_curve(manager):
    """A straight ramp between the two keyframes, in raw units."""
    anim_id = _long_animation(manager)
    anim = manager.enemy.animation_data.animations[anim_id]
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[4].position[1].set_pos_raw(400)

    nb_changed = manager.interpolate_frame_position(anim_id, 1, 0, 4, mode=interpolation.LINEAR)

    assert nb_changed == 3
    assert _positions(manager, anim_id, 1)[:5] == [0, 100, 200, 300, 400]


def test_nothing_is_added_or_removed(manager):
    """The frame count IS the animation's duration for the engine, and the sequences name frames
    by index - this feature must never touch either."""
    anim_id = _long_animation(manager)
    nb_before = manager.enemy.animation_data.animations[anim_id].get_nb_frame()
    manager.interpolate_frame_position(anim_id, 2, 0, 5, mode=interpolation.SINE)
    assert manager.enemy.animation_data.animations[anim_id].get_nb_frame() == nb_before


def test_only_the_chosen_axis_moves(manager):
    anim_id = _long_animation(manager)
    other_axes_before = (_positions(manager, anim_id, 0), _positions(manager, anim_id, 2))
    rotations_before = _rotations(manager, anim_id)

    manager.interpolate_frame_position(anim_id, 1, 0, 5, mode=interpolation.SINE)

    assert (_positions(manager, anim_id, 0), _positions(manager, anim_id, 2)) == other_axes_before
    assert _rotations(manager, anim_id) == rotations_before


def test_only_the_chosen_animation_moves(manager):
    anim_id = _long_animation(manager)
    other_id = next(other for other in range(manager.enemy.animation_data.nb_animations)
                    if other != anim_id)
    before = _positions(manager, other_id, 1)
    manager.interpolate_frame_position(anim_id, 1, 0, 5, mode=interpolation.LINEAR)
    assert _positions(manager, other_id, 1) == before


def test_the_frames_are_accepted_in_either_order(manager):
    """Typing the later frame first must do the same thing, not nothing."""
    anim_id = _long_animation(manager)
    anim = manager.enemy.animation_data.animations[anim_id]
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[4].position[1].set_pos_raw(400)
    manager.interpolate_frame_position(anim_id, 1, 4, 0, mode=interpolation.LINEAR)
    assert _positions(manager, anim_id, 1)[:5] == [0, 100, 200, 300, 400]


@pytest.mark.parametrize("mode", interpolation.ALL_MODES)
def test_every_curve_stays_between_the_two_keyframes_or_close(mode, manager):
    """Only the spline is allowed to overshoot (that is its follow-through), and even then not
    wildly - a curve that ran away would throw the model off the screen."""
    anim_id = _long_animation(manager)
    anim = manager.enemy.animation_data.animations[anim_id]
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[5].position[1].set_pos_raw(1000)

    manager.interpolate_frame_position(anim_id, 1, 0, 5, mode=mode)

    values = _positions(manager, anim_id, 1)[1:5]
    assert all(-500 <= value <= 1500 for value in values)


def test_a_range_with_nothing_between_is_refused(manager):
    anim_id = _long_animation(manager)
    with pytest.raises(ValueError):
        manager.interpolate_frame_position(anim_id, 1, 2, 3, mode=interpolation.LINEAR)
    with pytest.raises(ValueError):
        manager.interpolate_frame_position(anim_id, 1, 2, 2, mode=interpolation.LINEAR)


def test_a_frame_out_of_range_is_refused(manager):
    anim_id = _long_animation(manager)
    nb_frames = manager.enemy.animation_data.animations[anim_id].get_nb_frame()
    with pytest.raises(ValueError):
        manager.interpolate_frame_position(anim_id, 1, 0, nb_frames, mode=interpolation.LINEAR)


def test_a_bad_axis_is_refused(manager):
    anim_id = _long_animation(manager)
    with pytest.raises(ValueError):
        manager.interpolate_frame_position(anim_id, 3, 0, 5, mode=interpolation.LINEAR)


def test_an_up_and_down_movement_reads_as_an_arc(manager):
    """The recipe the sine curve is there for: bottom, top, bottom over two ranges. Every frame in
    between must sit between the bottom and the top, rising then falling, with no flat stretch."""
    anim_id = _long_animation(manager, min_frames=9)
    anim = manager.enemy.animation_data.animations[anim_id]
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[4].position[1].set_pos_raw(1000)
    anim.frames[8].position[1].set_pos_raw(0)

    manager.interpolate_frame_position(anim_id, 1, 0, 4, mode=interpolation.SINE)
    manager.interpolate_frame_position(anim_id, 1, 4, 8, mode=interpolation.SINE)

    height = _positions(manager, anim_id, 1)[:9]
    assert height[0] == 0 and height[4] == 1000 and height[8] == 0
    assert height[:5] == sorted(height[:5])            # rises to the top
    assert height[4:] == sorted(height[4:], reverse=True)   # then comes back down
    assert all(0 <= value <= 1000 for value in height)
    # The apex is rounded: the last step up is smaller than the middle one
    assert (height[4] - height[3]) < (height[2] - height[1])


def test_the_edit_survives_save_and_reopen(manager, tmp_path, game_data):
    """Positions are delta-encoded with a per-value bit width, so re-valuing frames in the middle
    of an animation has to refresh those widths or the save truncates the new deltas."""
    anim_id = _long_animation(manager)
    anim = manager.enemy.animation_data.animations[anim_id]
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[5].position[1].set_pos_raw(2000)
    manager.interpolate_frame_position(anim_id, 1, 0, 5, mode=interpolation.SINE)
    expected = _positions(manager, anim_id, 1)

    saved = str(tmp_path / "position_interpolated.dat")
    manager.save_file(saved)
    reopened = IfritManager(GAME_DATA_DIR, game_data=game_data)
    reopened.enemy = reopened.parse_file(saved)

    assert _positions(reopened, anim_id, 1) == expected


# ---------------------------------------------------------------------------
# The buttons themselves
# ---------------------------------------------------------------------------

def test_the_frame_position_tab_has_one_button_per_axis():
    from Ifrit.Ifrit3D.boneeditorwidget import AnimEditor

    editor = AnimEditor()
    assert len(editor.position_interpolate_buttons) == 3


def test_each_button_asks_for_its_own_axis():
    """X, Y and Z must not all ask for the same channel - a copy/paste slip that no visual check
    would catch."""
    from Ifrit.Ifrit3D.boneeditorwidget import AnimEditor

    editor = AnimEditor()
    asked = []
    editor.position_interpolation_requested.connect(asked.append)
    for button in editor.position_interpolate_buttons:
        button.click()
    assert asked == [0, 1, 2]


def test_the_popup_asks_for_two_frames_and_a_curve(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QDialog
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    manager = MagicMock()
    manager.enemy.bone_section = None
    manager.bone_data = []
    viewer = Ifrit3DWidget(manager, show_controls=False)

    frame_a, frame_b, mode = viewer._ask_position_interpolation("Interpolate Pos Y", "Y", 10)
    assert (frame_a, frame_b) == (0, 9)      # the shown frame, through to the last one
    assert mode in interpolation.ALL_MODES


def test_the_button_reaches_the_model_through_the_viewer(monkeypatch, game_data, tmp_path):
    """End to end from the button: the click asks, the viewer runs it, the model changes and the
    file is marked dirty."""
    import shutil

    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QDialog
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    working_copy = tmp_path / MONSTER_FILE
    shutil.copy(os.path.join(BATTLE_DIR, MONSTER_FILE), working_copy)

    widget = IfritMonsterWidget(settings=QSettings("test", "frame_position_interp"),
                                icon_path=os.path.join(REPO, "Resources"),
                                game_data_folder=GAME_DATA_DIR)
    widget.show()
    widget._build_session([str(working_copy)])
    _APP.processEvents()
    pane = widget._files[0]['pane']
    viewer = pane._3d_widget

    anim = viewer.ifrit_manager.enemy.animation_data.animations[viewer.current_anim_id]
    if anim.get_nb_frame() < 3:
        pytest.skip("the first animation is too short to interpolate over")
    anim.frames[0].position[1].set_pos_raw(0)
    anim.frames[-1].position[1].set_pos_raw(2000)
    before = [frame.position[1].get_pos_raw() for frame in anim.frames]

    viewer.bone_editor.position_interpolate_buttons[1].click()   # the Pos Y button
    _APP.processEvents()

    after = [frame.position[1].get_pos_raw() for frame in anim.frames]
    assert len(after) == len(before)          # no frame added or removed
    assert after[0] == 0 and after[-1] == 2000
    assert after[1:-1] != before[1:-1]        # the frames in between were rewritten
    assert pane.dirty
