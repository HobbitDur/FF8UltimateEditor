"""Tests for the engine-faithful camera baker (FF8GameData/dat/camerabake.py)."""
import pathlib

import pytest

from FF8GameData.dat.camerabake import (bake_camera_animation, zoom_out,
                              BakedAnimation, _natural_cubic_spline, _ease)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
R0WIN = PROJECT_ROOT / "extracted_files" / "battle" / "r0win.dat"
R0WIN_MARK = "extracted_files/battle/r0win.dat"


# --------------------------------------------------------------------- synthetic
class _Field:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _Frame:
    def __init__(self, duration, x, y, z, lx, ly, lz):
        self.duration = _Field(duration)
        self.pos_x, self.pos_y, self.pos_z = _Field(x), _Field(y), _Field(z)
        self.look_x, self.look_y, self.look_z = _Field(lx), _Field(ly), _Field(lz)


class _Block:
    def __init__(self, control_word, frames):
        self.control_word = control_word
        self.frames = frames


class _Animation:
    def __init__(self, blocks):
        self.blocks = blocks


def test_ease_linear_control_word():
    # 0x3C1 is the linear control word: the fraction passes through unchanged
    assert _ease(0, 0x3C1) == 0
    assert _ease(2048, 0x3C1) == 2048
    assert _ease(4096, 0x3C1) == 4096


def test_ease_sine_control_word_bows():
    # 0x3C5 applies the sine ease twice: endpoints fixed, middle pulled off the diagonal
    assert _ease(0, 0x3C5) == 0
    assert _ease(4096, 0x3C5) == 4096
    assert _ease(2048, 0x3C5) != 2048


def test_two_keyframe_linear_then_hold():
    # 4 frames glide 0 -> 400, then 1 frame holds at 400 (last keyframe's duration)
    block = _Block(0x3C1, [_Frame(4, 0, 0, 0, 0, 0, 0), _Frame(1, 400, 0, 0, 0, 0, 0)])
    frames = bake_camera_animation(_Animation([block]))
    assert len(frames) == 5  # sum of durations
    xs = [f[0] for f in frames]
    assert xs[0] == 0
    assert xs == sorted(xs)          # monotone glide
    assert xs[:4] == [0, 100, 200, 300]  # linear over the first keyframe's 4-frame span
    assert xs[4] == 400              # last frame snaps to / holds the second keyframe


def test_single_keyframe_holds():
    block = _Block(0x3C1, [_Frame(3, 7, 8, 9, 1, 2, 3)])
    frames = bake_camera_animation(_Animation([block]))
    assert len(frames) == 3
    assert all(f == (7, 8, 9, 1, 2, 3) for f in frames)


def test_blocks_are_chained():
    block_a = _Block(0x3C1, [_Frame(2, 0, 0, 0, 0, 0, 0), _Frame(1, 100, 0, 0, 0, 0, 0)])
    block_b = _Block(0x3C1, [_Frame(2, 500, 0, 0, 0, 0, 0), _Frame(1, 600, 0, 0, 0, 0, 0)])
    frames = bake_camera_animation(_Animation([block_a, block_b]))
    assert len(frames) == 6  # 3 + 3
    assert frames[0][0] == 0 and frames[3][0] == 500  # second block starts at its own kf0


def test_baked_animation_accepts_prebaked_list():
    frames = [(1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)]
    wrapped = BakedAnimation(frames)
    assert len(wrapped.blocks[0].frames) == 2
    assert wrapped.blocks[0].frames[0].pos_x.get() == 1
    assert BakedAnimation([]).is_empty()


def test_zoom_out_dollies_camera_back_keeping_lookat():
    # factor 1.0 is a no-op
    assert zoom_out([(5, 5, 5, 1, 1, 1)], 1.0) == [(5, 5, 5, 1, 1, 1)]
    # camera at x=100 looking at x=0, factor 2 -> camera moves to x=200, look-at unchanged
    assert zoom_out([(100, 0, 0, 0, 0, 0)], 2.0) == [(200, 0, 0, 0, 0, 0)]
    # offset look-at: pull back along the camera->look vector only
    assert zoom_out([(100, 50, 0, 40, 50, 0)], 3.0) == [(220, 50, 0, 40, 50, 0)]


def test_natural_cubic_spline_passes_through_points():
    xs = [0, 10, 20]
    ys = [0, 100, 0]
    spline = _natural_cubic_spline(xs, ys)
    assert round(spline(0)) == 0
    assert round(spline(10)) == 100
    assert round(spline(20)) == 0
    # a natural spline through (0,0),(10,100),(20,0) overshoots 100 near the middle-left
    assert spline(5) > 50


# --------------------------------------------------------------------- real file
@pytest.mark.ff8data(R0WIN_MARK)
def test_real_bake_frame_counts():
    from Watts.wattsmanager import WattsManager
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    for camera_set in manager.camera_collection.sets:
        for animation in camera_set.animations:
            if not animation.blocks:
                continue
            expected = sum(f.duration.get() for b in animation.blocks for f in b.frames)
            baked = bake_camera_animation(animation)
            assert len(baked) == expected  # one baked frame per engine tick
            wrapped = BakedAnimation(animation)
            assert not wrapped.is_empty()
            assert len(wrapped.blocks[0].frames) == expected
