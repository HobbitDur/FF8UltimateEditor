"""The timeline's comparison of a model's animations with a reference (FF8GameData.dat.animdiff)."""
from FF8GameData.dat.animdiff import (ROW_POSITION, STATUS_CHANGED, STATUS_NEW, STATUS_REMOVED,
                                      STATUS_SAME, diff_animation, diff_animations,
                                      reference_frame_map, wrap_rotation)


def frame(position=(0, 0, 0), rotations=((0, 0, 0), (0, 0, 0)), scales=None):
    return position, tuple(rotations), scales


def test_same_animation_has_no_cells():
    animation = [frame(), frame(rotations=((10, 0, 0), (0, 0, 0)))]
    diff = diff_animation(0, animation, list(animation))
    assert diff.status == STATUS_SAME and not diff.cells and not diff.retimed


def test_rotation_position_and_scale_cells():
    reference = [frame(), frame()]
    current = [frame(rotations=((0, 0, 0), (100, 0, -50))),
               frame(position=(4, 0, 0), scales=((1024, 1024, 1024), (2048, 1024, 1024)))]
    diff = diff_animation(3, current, reference)
    assert diff.status == STATUS_CHANGED
    assert set(diff.cells) == {(1, 0), (ROW_POSITION, 1), (1, 1)}
    assert diff.cells[(1, 0)].rotation == (100, 0, -50)
    assert round(diff.cells[(1, 0)].rotation_degrees, 2) == round(100 * 360 / 4096, 2)
    assert diff.cells[(ROW_POSITION, 1)].position == (4, 0, 0)
    assert diff.cells[(1, 1)].scale_changed and not any(diff.cells[(1, 1)].rotation)
    assert diff.changed_frames() == {0, 1} and diff.changed_rows() == {1, ROW_POSITION}


def test_a_full_turn_is_no_change_and_deltas_take_the_short_way():
    assert wrap_rotation(4096) == 0
    assert wrap_rotation(4000) == -96
    diff = diff_animation(0, [frame(rotations=((4096, 0, 0), (0, 0, 0)))], [frame()])
    assert not diff.cells    # stored differently, same pose: no dot


def test_new_and_removed_animations_and_new_bones():
    reference = [[frame()]]
    current = [[frame(rotations=((0, 0, 0), (0, 0, 0), (5, 0, 0)))], [frame()]]
    diffs = diff_animations(current, reference)
    assert diffs[0].cells[(2, 0)].new_bone
    assert diffs[1].status == STATUS_NEW
    assert diff_animations([], reference)[0].status == STATUS_REMOVED


def test_frame_count_change_compares_the_same_point_in_time():
    assert reference_frame_map(3, 3) == [0, 1, 2]
    assert reference_frame_map(5, 3) == [0, 0, 1, 2, 2]     # 30 fps doubled: frame 2 <-> 1
    reference = [frame(), frame(rotations=((40, 0, 0), (0, 0, 0))), frame()]
    current = [frame(), frame(), frame(rotations=((40, 0, 0), (0, 0, 0))), frame(), frame()]
    diff = diff_animation(0, current, reference)
    assert diff.retimed and diff.status == STATUS_CHANGED
    assert not diff.cells    # every frame matches its reference frame
