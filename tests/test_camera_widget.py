"""Widget-level guards for the Camera tab (Ifrit/IfritCameraSeq).

These pin two behaviours that are invisible to the byte-level model tests but easy to break:
- editing a spin box actually writes back into the section bytes (a missing valueChanged ->
  field.set connection once made the whole editor read-only without any error);
- the spin boxes ignore the mouse wheel, so scrolling the tab cannot change a value.
"""
import os
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QSpinBox
from PyQt6.QtCore import Qt, QPointF, QPoint
from PyQt6.QtGui import QWheelEvent

from FF8GameData.dat.cameracollection import parse_camera_collection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _synthetic_collection() -> bytes:
    """One set, one animation, one block, one keyframe - enough to bind a spin to a field."""
    data = bytearray()
    data += struct.pack("<H", 1) + struct.pack("<H", 8)
    eof = len(data)
    data += struct.pack("<H", 0) + struct.pack("<H", 0)
    data += struct.pack("<h", 8) + b"".join(struct.pack("<h", -1) for _ in range(7))
    data += struct.pack("<H", 0x03C1) + struct.pack("<HH", 0x200, 0x210) + struct.pack("<HH", 0, 5)
    data += (struct.pack("<H", 13) + struct.pack("<BB", 0x90, 0) + struct.pack("<hhh", -4001, 1739, 2985)
             + struct.pack("<BB", 0x90, 0) + struct.pack("<hhh", 316, 355, 236))
    data += struct.pack("<H", 0xFFFF) + struct.pack("<H", 0xFFFF)
    struct.pack_into("<H", data, eof, len(data))
    return bytes(data)


def test_editing_a_spin_writes_back_to_the_section_bytes(app):
    from Ifrit.IfritCameraSeq.ifritcameraseqwidget import _bind_spin
    collection = parse_camera_collection(_synthetic_collection())
    frame = collection.sets[0].animations[0].blocks[0].frames[0]
    spin = _bind_spin(frame.pos_x)
    before = bytes(collection.get_bytes())
    spin.setValue(-1234)  # a user edit fires valueChanged -> field.set
    assert frame.pos_x.get() == -1234
    changed = bytes(collection.get_bytes())
    assert changed != before
    assert changed[frame.pos_x.offset:frame.pos_x.offset + 2] == (-1234).to_bytes(2, "little", signed=True)


def test_spin_boxes_ignore_the_mouse_wheel(app):
    from Ifrit.IfritCameraSeq.ifritcameraseqwidget import NoWheelSpinBox
    no_wheel = NoWheelSpinBox()
    no_wheel.setRange(-100, 100)
    no_wheel.setValue(10)
    plain = QSpinBox()
    plain.setRange(-100, 100)
    plain.setValue(10)

    def scroll(widget):
        event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(widget, event)

    scroll(no_wheel)
    scroll(plain)
    assert no_wheel.value() == 10, "NoWheelSpinBox must ignore the wheel"
    assert plain.value() != 10, "a plain QSpinBox would have changed - the guard is meaningful"
