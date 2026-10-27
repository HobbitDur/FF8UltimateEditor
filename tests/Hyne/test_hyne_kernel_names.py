"""Hyne names every ability from an opened kernel.bin, like Quezacotl: the equipped abilities, the
learned ones, the Learning choice and the AP slots (slot k = entry k of the GF's kernel.bin list).
"""
import os
import pathlib
import shutil
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from Hyne.hynemanager import (IMAGE_SIZE, GAMESTATE_BASE, CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_START,
                              CRC_SPAN_LEN, crc16_ff8, lzss_compress_all_literal)
from Hyne.hynewidget import HyneWidget

REPO = pathlib.Path(__file__).parent.parent.parent
MAIN = REPO / "extracted_files" / "main"


def _save_from_init_out(path):
    """A CRC-correct .ff8 whose savemap+80 is the vanilla init.out (the same layout)."""
    image = bytearray((i * 167 + 41) & 0xFF for i in range(IMAGE_SIZE))
    init_out = (MAIN / "init.out").read_bytes()
    image[GAMESTATE_BASE:GAMESTATE_BASE + len(init_out)] = init_out
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress_all_literal(bytes(image))
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)
    return str(path)


@pytest.mark.ff8data("extracted_files/main/init.out", "extracted_files/main/kernel.bin")
def test_abilities_are_named_from_kernel_bin(tmp_path):
    shutil.copy(MAIN / "kernel.bin", tmp_path / "kernel.bin")
    widget = HyneWidget(str(REPO / "Resources"), str(REPO / "FF8GameData"))
    widget.ff8_binding.open_path(_save_from_init_out(tmp_path / "slot1_save01.ff8"))
    widget.gf_list.setCurrentRow(0)
    assert widget.gf_ap_labels[16].text() == "Slot 17:" and widget.gf_ap_infos[16].text() == ""
    assert not widget.gf_learning_ability_combo.isEnabled()

    widget.kernel_names.binding.open_path(str(tmp_path / "kernel.bin"))
    assert widget.gf_ap_labels[15].text() == "Slot 16: Card"  # Quezacotl
    assert widget.gf_ap_labels[16].text() == "Slot 17: Card Mod"
    assert widget.gf_ap_infos[16].text() == "/ 80 AP - after Card"
    assert widget.gf_ap_labels[21].text() == "Slot 22: -"  # the save has 22 slots, a GF list 21
    learning = widget.gf_learning_ability_combo
    assert learning.isEnabled() and learning.count() == 22  # None + Quezacotl's 21 abilities
    assert learning.findText("Card Mod", flags=_contains()) >= 0

    widget.gf_list.setCurrentRow(2)  # Ifrit: Str-J learned from the start
    assert widget.gf_ap_infos[18].text() == "/ 50 AP - from the start - learned"
    str_j = next(i for i in widget.gf_ability_checks if widget.kernel_names.ability_name(i) == "Str-J")
    assert widget.gf_ability_checks[str_j].text() == "Str-J"
    widget.gf_ability_checks[str_j].setChecked(False)
    assert widget.gf_ap_infos[18].text() == "/ 50 AP - from the start"

    assert all(":" in c.currentText() and "kernel.bin" not in c.currentText()
               for c in widget.char_active_combos + widget.char_passive_combos)

    widget.kernel_names.binding.registry.close_file("kernel.bin")
    assert widget.gf_ap_labels[8].text() == "Slot 9:"
    assert not learning.isEnabled()


def _contains():
    from PyQt6.QtCore import Qt
    return Qt.MatchFlag.MatchContains
