"""Camera keyframe coordinate modes: named list (FF8GameData.dat.cameramodes) and its drop-down."""
import os
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.cameracollection import (control_easing, make_control_word, parse_camera_collection,
                                              set_block_control)
from FF8GameData.dat.cameramodes import easing_name, mode_choices, mode_help, mode_name


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _collection(pos_mode=0xA1, look_mode=0x6B) -> bytes:
    """One set, one animation, one block, one keyframe."""
    data = bytearray(struct.pack("<HH", 1, 6))
    eof = len(data)
    data += struct.pack("<H", 0)
    data += struct.pack("<h", 8) + b"".join(struct.pack("<h", -1) for _ in range(7))
    data += struct.pack("<H", 0x0001)
    data += (struct.pack("<H", 13) + struct.pack("<BB", pos_mode, 0) + struct.pack("<hhh", -4001, 1739, 2985)
             + struct.pack("<BB", look_mode, 0) + struct.pack("<hhh", 0, 0, 0))
    data += struct.pack("<HH", 0xFFFF, 0xFFFF)
    struct.pack_into("<H", data, eof, len(data))
    return bytes(data)


def test_modes_follow_the_engine_frames():
    # getCameraScalingFactor: high digit = entity (9 attacker, A target, 0-6 slot), low digit =
    # skeleton anchor 0-3 or F origin, scaled by size; 0xB0 and up = target ground, not scaled
    assert mode_name(0xA1) == "A1 Target, model centre (size-scaled)"
    assert mode_name(0x9F) == "9F Attacker, origin (size-scaled)"
    assert mode_name(0x31) == "31 Slot 3 (1st monster), model centre (size-scaled)"
    assert mode_name(0x02) == "02 Party slot 0, anchor 0xF2 (size-scaled)"
    assert mode_name(0xB0) == "B0 Target ground, not scaled"
    assert mode_name(0xC4) == "C4 Target ground, not scaled (= B0)"
    assert mode_name(0xF0).endswith("(= B0)") and mode_name(0xFF).endswith("(= B0)")
    assert mode_name(0xF2) == "F2 Attacker-target midpoint, not scaled"
    assert mode_name(0xF3) == "F3 Current camera position" and mode_name(0xFB) == "FB World"
    assert "no such battle slot" in mode_name(0x75)        # only 7 battle slots
    assert "invalid point" in mode_name(0xA7)              # only 4 anchor bytes in the skeleton
    assert all(mode_help(value) for value in range(256))


def test_the_list_offers_only_valid_modes_once():
    values = [value for value, _label in mode_choices()]
    assert len(values) == len(set(values))
    assert values[0] == 0xA1                               # the target's centre comes first
    assert {0xF3, 0xF4, 0xF2, 0xB0, 0xFB} <= set(values)
    assert not any(0x70 <= value < 0x90 or (value < 0xB0 and (value & 0xF) not in (0, 1, 2, 3, 0xF))
                   for value in values)


def test_combo_edits_the_mode_byte(app):
    from Common.cameramodecombo import CameraModeCombo
    collection = parse_camera_collection(_collection(look_mode=0x7C))
    frame = collection.sets[0].animations[0].blocks[0].frames[0]
    combo = CameraModeCombo(frame.pos_interp_mode.get())
    combo.valueChanged.connect(lambda value: frame.pos_interp_mode.set(value))   # CameraField: no weakref
    assert combo.value() == 0xA1 and "size" in combo.toolTip()
    combo.setCurrentIndex(combo.findData(0xB0))
    assert frame.pos_interp_mode.get() == 0xB0
    assert collection.get_bytes()[frame.pos_interp_mode.offset] == 0xB0
    # A byte outside the list (here an invalid slot) still shows as it is
    odd = CameraModeCombo(frame.look_interp_mode.get())
    assert odd.value() == 0x7C and odd.currentText().startswith("7C")


def test_keyframe_grids_use_the_combo(app):
    from Common.cameracollectionwidget import CameraCollectionWidget
    from Common.cameramodecombo import CameraModeCombo
    collection = parse_camera_collection(_collection())
    widget = CameraCollectionWidget(collection)
    block = collection.sets[0].animations[0].blocks[0]
    container = widget._build_block(0, block)
    combos = container.findChildren(CameraModeCombo)
    assert sorted(combo.value() for combo in combos) == [0x6B, 0xA1]
    combos[0].setCurrentIndex(combos[0].findData(0xF3))
    assert 0xF3 in (block.frames[0].pos_interp_mode.get(), block.frames[0].look_interp_mode.get())


def test_block_control_word_fields():
    # BS_Camera_EaseTime 0x503FE0: bits 1-5 signed; Disease Breath's 0x03FF block eases in once
    assert control_easing(0x03FF) == -1 and control_easing(0x03C1) == 0 and control_easing(0x001E) == 15
    assert make_control_word(3, 3, 1, -1) == 0x03FF and make_control_word(1, 1, 0, 0) == 0x0140
    assert easing_name(0) == "Linear" and easing_name(-2) == "Ease in x2"
    assert easing_name(15) == "Ease out x15 + save return view"


def test_set_block_control_keeps_the_values_it_can():
    data = _collection()      # block: FOV/roll mode 0 (no words), layout 1
    fixed = set_block_control(data, 0, 0, 0, fov_mode=2, roll_mode=3, easing=-3)
    block = parse_camera_collection(fixed).sets[0].animations[0].blocks[0]
    assert (block.fov_mode, block.roll_mode, block.layout, block.easing) == (2, 3, 1, -3)
    assert block.fov_start.get() == 512 and (block.roll_start.get(), block.roll_end.get()) == (0, 0)
    assert block.frames[0].pos_x.get() == 1739 and block.frames[0].pos_interp_mode.get() == 0xA1
    pair = set_block_control(_with_fov(fixed, 352), 0, 0, 0, fov_mode=3)
    block = parse_camera_collection(pair).sets[0].animations[0].blocks[0]
    assert (block.fov_start.get(), block.fov_end.get()) == (352, 352)       # a fixed FOV becomes start = end
    back = parse_camera_collection(set_block_control(pair, 0, 0, 0, fov_mode=1, roll_mode=1))
    block = back.sets[0].animations[0].blocks[0]
    assert block.fov_start is None and block.roll_start is None and block.frames[0].pos_x.get() == 1739


def _with_fov(data, value):
    collection = parse_camera_collection(data)
    collection.sets[0].animations[0].blocks[0].fov_start.set(value)
    return collection.get_bytes()


def test_block_settings_are_lists_in_the_editor(app):
    from Common.cameracollectionwidget import CameraCollectionWidget
    from Common.cameramodecombo import WidestEntryCombo
    collection = parse_camera_collection(_collection())
    widget = CameraCollectionWidget(collection, structure_edits=True)
    rebuilt = []
    widget.collection_rebuilt.connect(rebuilt.append)
    container = widget._build_block(0, collection.sets[0].animations[0].blocks[0], (0, 0))
    lists = [combo for combo in container.findChildren(WidestEntryCombo) if combo.count() == 32]
    assert len(lists) == 1 and lists[0].currentText() == "Linear"           # the easing list
    lists[0].setCurrentIndex(lists[0].findData(4))
    assert parse_camera_collection(rebuilt[-1]).sets[0].animations[0].blocks[0].easing == 4
