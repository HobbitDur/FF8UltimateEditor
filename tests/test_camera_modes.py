"""Camera keyframe coordinate modes: named list (FF8GameData.dat.cameramodes) and its drop-down."""
import os
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.dat.cameramodes import mode_choices, mode_help, mode_name


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
