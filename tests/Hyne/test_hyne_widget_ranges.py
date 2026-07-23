"""The Hyne editor must show every value a save can legally hold.

EXP and gil are 32-bit UNSIGNED in the save (0 .. 4294967295), but the widget put them in a
QSpinBox, which is limited to a SIGNED 32-bit int and stops at 2147483647. The upper half of the
range was therefore not reachable at all - and a save actually holding such a value did not just
display wrong, it killed the editor: Qt's setValue raises OverflowError, the exception escaped
inside the load slot, and PyQt aborts the process on that (no traceback, no message box).

A save with 3 billion gil is not exotic; every hacked or maxed save has one. So these tests use
values above the signed limit throughout - they fail (by dying) on the old widget.
"""
import os
import pathlib
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from Hyne.hynemanager import (IMAGE_SIZE, CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_START,
                              CRC_SPAN_LEN, crc16_ff8, lzss_compress_all_literal)
from Hyne.hynewidget import HyneWidget, U32_MAX

REPO = pathlib.Path(__file__).parent.parent.parent

# Above the signed 32-bit limit the old spin boxes stopped at, and a legal u32.
HUGE = 3_000_000_000


@pytest.fixture(scope="module")
def widget():
    return HyneWidget(str(REPO / "Resources"), str(REPO / "FF8GameData"))


def _write_save(path, patch=None):
    """A CRC-correct .ff8 save, optionally patched at (offset, u32 value) pairs."""
    image = bytearray((i * 167 + 41) & 0xFF for i in range(IMAGE_SIZE))
    for offset, value in (patch or []):
        struct.pack_into("<I", image, offset, value)
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress_all_literal(bytes(image))
    with open(path, "wb") as handle:
        handle.write(struct.pack("<I", len(compressed)))
        handle.write(compressed)
    return str(path)


def test_the_32_bit_fields_can_reach_the_whole_range(widget):
    """Every field backed by a u32 in the save has to go all the way to 4294967295."""
    for spin in (widget.gf_exp_spin, widget.char_exp_spin,
                 widget.misc_gil_spin, widget.misc_gil_laguna_spin):
        assert spin.maximum() >= U32_MAX
        assert spin.minimum() == 0


def test_a_32_bit_field_keeps_a_value_above_the_signed_limit(widget):
    """The old spin box silently clamped there, when it did not raise."""
    widget.gf_exp_spin.setValue(HUGE)
    assert widget.gf_exp_spin.value() == HUGE


def test_a_32_bit_field_hands_back_a_whole_number(widget):
    """It is a QDoubleSpinBox underneath (the only Qt spin box that spans a u32), so it must
    still give the manager an int to pack into the save, not a float."""
    widget.misc_gil_spin.setValue(HUGE)
    assert isinstance(widget.misc_gil_spin.value(), int)


def test_a_save_holding_values_above_the_signed_limit_opens(widget, tmp_path):
    """The whole point: this used to abort the editor while loading.

    The byte pattern gives the first GF an EXP well past the signed limit, which is what the old
    spin box choked on - so the check is that the value survives the trip to the screen intact,
    not merely that the file opened.
    """
    save = _write_save(tmp_path / "slot1_save01.ff8")
    widget.load_file(save)                       # the process dies here on the old widget
    assert widget.manager.file_path == save

    shown = widget.gf_exp_spin.value()
    assert shown == widget.manager.gf_entries[0].exp
    assert shown > 2147483647, "the pattern must exercise the range the old widget could not show"


def test_a_field_the_widget_cannot_show_is_clamped_rather_than_fatal(widget, tmp_path):
    """A save is not always what this editor expects - hacked, from another game, or a field
    this project has not decoded right. Whatever comes out of it, loading must not raise inside
    the slot, because that is fatal rather than merely wrong."""
    save = _write_save(tmp_path / "slot1_save02.ff8")
    widget.load_file(save)
    # A byte-wide field asked to show far more than a byte: clamped to its own maximum, and the
    # editor is still alive and usable.
    widget._set_spin_value(widget.char_str_spin, 999999)
    assert widget.char_str_spin.value() == widget.char_str_spin.maximum()
    assert widget.tabs.isEnabled()
