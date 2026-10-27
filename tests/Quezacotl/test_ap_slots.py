"""Quezacotl names the AP slots of a GF from an opened kernel.bin.

BuildGFAbilityList: AP slot k is the AP earned toward entry k of the GF's 21-entry ability list in
the Junctionable GFs section (byte 1 = unlock: GF level <= 100, or 101 + the slot whose ability
comes first; byte 3 = ability), and the AP the ability costs is byte 4 of its own kernel entry.
"""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MAIN = PROJECT_ROOT / "extracted_files" / "main"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data("extracted_files/main/init.out", "extracted_files/main/kernel.bin")
def test_ap_slots_are_named_from_kernel_bin(qapp, tmp_path):
    from Quezacotl.quezacotlwidget import QuezacotlWidget
    for name in ("init.out", "kernel.bin"):
        shutil.copy(MAIN / name, tmp_path / name)
    widget = QuezacotlWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.init_binding.open_path(str(tmp_path / "init.out"))
    widget.gf_list.setCurrentRow(0)
    assert widget.gf_ap_labels[16].text() == "Slot 17:" and widget.gf_ap_infos[16].text() == ""

    widget.kernel_names.binding.open_path(str(tmp_path / "kernel.bin"))
    assert widget.gf_ap_labels[15].text() == "Slot 16: Card"  # Quezacotl
    assert widget.gf_ap_labels[16].text() == "Slot 17: Card Mod"
    assert widget.gf_ap_infos[16].text() == "/ 80 AP - after Card"
    assert widget.gf_ap_infos[0].text() == "/ 40 AP - from the start"
    assert widget.gf_ap_labels[21].text() == "Slot 22: -"  # init.out has 22 slots, a GF list 21

    widget.gf_list.setCurrentRow(2)  # Ifrit: Ammo-RF from GF level 10, Str-J learned from the start
    assert (widget.gf_ap_labels[8].text(), widget.gf_ap_infos[8].text()) == \
        ("Slot 9: Ammo-RF", "/ 30 AP - from GF level 10")
    assert widget.gf_ap_infos[18].text() == "/ 50 AP - from the start - learned"
    check = widget.gf_ability_checks[next(i for i in widget.gf_ability_checks
                                          if widget.kernel_names.ability_name(i) == "Str-J")]
    check.setChecked(False)
    assert widget.gf_ap_infos[18].text() == "/ 50 AP - from the start"

    widget.kernel_names.binding.registry.close_file("kernel.bin")
    assert widget.gf_ap_labels[8].text() == "Slot 9:"
