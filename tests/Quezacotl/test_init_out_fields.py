"""init.out fields checked against FF8_EN.exe in the "unknown / unused" pass (2026-10-27).

- Character +0x94 is a bit field (SCRIPT_ADDMEMBER 0x09/0x0D, SUBMEMBER clears 0x09, HOLD 0x06, the
  dream party setup reads 0x08), so editing one bit must keep the others.
- GF +0x41-0x43: one "forgotten" bit per slot of the GF's kernel.bin list (BuildGFAbilityList).
- AP slot 22: no code reads or writes it, so the tool never writes it either.
- The Learning ability only earns AP when it is in the GF's kernel.bin list (GF_AddApToLearningAbility).
"""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from Quezacotl.quezacotlmanager import CharacterEntry, ConfigEntry, QuezacotlManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MAIN = PROJECT_ROOT / "extracted_files" / "main"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def files(tmp_path):
    for name in ("init.out", "kernel.bin"):
        shutil.copy(MAIN / name, tmp_path / name)
    return tmp_path


def _manager(path):
    manager = QuezacotlManager(GameData(str(PROJECT_ROOT / "FF8GameData")))
    manager.load_file(str(path))
    return manager


@pytest.mark.ff8data("extracted_files/main/init.out")
def test_party_flags_keep_their_other_bits(files):
    manager = _manager(files / "init.out")
    squall = manager.character_entries[0]
    squall.set_exist_flag(0x0D, True)            # what SCRIPT_ADDMEMBER gives Squall
    squall.exist = False                         # the roster bit only
    assert squall.exist_flags == 0x0C
    squall.set_exist_flag(0x04, False)
    assert squall.exist_flags == 0x08 and not squall.exist
    assert [mask for mask, _ in CharacterEntry.EXIST_BITS] == [0x01, 0x02, 0x04, 0x08]


@pytest.mark.ff8data("extracted_files/main/init.out")
def test_forgotten_bits_are_one_per_slot(files):
    manager = _manager(files / "init.out")
    gf = manager.gf_entries[3]
    gf.set_forgotten(1, True)
    gf.set_forgotten(9, True)
    gf.set_forgotten(21, True)
    assert [gf.is_forgotten(slot) for slot in (1, 2, 9, 21)] == [True, False, True, True]
    assert manager.buffer[3 * 68 + 65:3 * 68 + 68] == bytes((0x01, 0x01, 0x10))
    gf.set_forgotten(9, False)
    assert not gf.is_forgotten(9) and gf.is_forgotten(1)


def test_config_flag_names_follow_the_exe():
    names = dict(ConfigEntry.FLAG_BITS)
    assert names[0x01].startswith("Battle Mode: Wait")   # Battle_ShouldAtbKeepRunning
    assert names[0x80].startswith("Swap analog sticks")   # sub_4C3010 -> sub_49F0A0 axis ^ 2


@pytest.mark.ff8data("extracted_files/main/init.out", "extracted_files/main/kernel.bin")
def test_widget_party_flags_forgotten_learning_and_slot_22(qapp, files):
    from Quezacotl.quezacotlwidget import QuezacotlWidget
    widget = QuezacotlWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.init_binding.open_path(str(files / "init.out"))
    squall = widget.manager.character_entries[0]
    squall.set_exist_flag(0x0C, True)
    widget.character_list.setCurrentRow(1)
    widget.character_list.setCurrentRow(0)
    checks = dict(widget.char_exist_checks)
    assert [checks[mask].isChecked() for mask in (0x01, 0x02, 0x04, 0x08)] == [True, False, True, True]
    checks[0x01].setChecked(False)               # the old checkbox wrote 0 here, wiping 0x0C
    assert squall.exist_flags == 0x0C

    widget.gf_list.setCurrentRow(0)              # Quezacotl
    combo = widget.gf_learning_ability_combo
    assert combo.count() == 1  # no kernel.bin: no names, only the file's value is kept
    widget.kernel_names.binding.open_path(str(files / "kernel.bin"))
    names = [combo.itemText(i) for i in range(combo.count())]
    assert combo.count() == 22 and names[0] == "0: None"  # None + the GF's 21 abilities
    assert any(text.endswith("Card Mod") for text in names)
    assert any("(learned)" in text for text in names)

    gf = widget.manager.gf_entries[0]
    widget.gf_forgotten_checks[16].setChecked(True)   # slot 17 = Card Mod
    assert gf.is_forgotten(17)
    assert any(text.endswith("Card Mod (forgotten)") for text in
               (combo.itemText(i) for i in range(combo.count())))

    gf.learning_ability = 60                     # not an ability of Quezacotl's list
    widget._reload_gf()
    assert combo.currentText() == "60: not in this GF's list - earns no AP"

    slot_22 = widget.gf_ap_spins[21]
    assert slot_22.isReadOnly() and len(widget.gf_forgotten_checks) == 21
    before = gf.get_ap_ability(22)
    widget.gf_ap_spins[0].setValue(5)
    assert gf.get_ap_ability(1) == 5 and gf.get_ap_ability(22) == before
