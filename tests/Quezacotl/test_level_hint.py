"""Quezacotl shows the level an EXP gives, "Lvl N + X xp", from the EXP curves of an opened kernel.bin.

Characters (Stat_ComputeLevelFromExp) and GFs (GetGFLevelFromExperience) share one loop: level n+1 at
10 * A * n + n * n * B / 256 EXP, A and B two kernel.bin bytes (character: Characters section +6/+7 of
its comId entry; GF: Junctionable GFs section +24/+25), capped at 100.
"""
import pathlib
import random
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.kernellevels import LevelCurve

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MAIN = PROJECT_ROOT / "extracted_files" / "main"


def _exe_level(exp, linear, quadratic):
    """GetGFLevelFromExperience / Stat_ComputeLevelFromExp, transcribed as the exe loops."""
    level, quad_acc, lin_acc = 1, quadratic, 10 * linear
    while True:
        if exp < lin_acc + level * quad_acc // 256:
            break
        level += 1
        quad_acc += quadratic
        lin_acc += 10 * linear
        if level >= 100:
            break
    return level


def test_level_from_exp_is_the_exe_loop():
    rng = random.Random(8)
    for _ in range(5000):
        linear, quadratic, exp = rng.randrange(256), rng.randrange(256), rng.randrange(3_000_000)
        assert LevelCurve(linear, quadratic).level_from_exp(exp)[0] == _exe_level(exp, linear, quadratic)
    squall = LevelCurve(100, 0)  # vanilla characters: one level per 1000 EXP
    assert squall.level_from_exp(0) == (1, 0)
    assert squall.level_from_exp(21500) == (22, 500)
    assert squall.level_from_exp(99000)[0] == 100


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data("extracted_files/main/init.out", "extracted_files/main/kernel.bin")
def test_exp_fields_show_the_level(qapp, tmp_path):
    from Quezacotl.quezacotlwidget import QuezacotlWidget
    for name in ("init.out", "kernel.bin"):
        shutil.copy(MAIN / name, tmp_path / name)
    widget = QuezacotlWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.init_binding.open_path(str(tmp_path / "init.out"))
    widget.character_list.setCurrentRow(0)
    assert widget.char_exp_hint.text() == "Lvl ? (needs kernel.bin)"

    widget.kernel_names.binding.open_path(str(tmp_path / "kernel.bin"))
    assert widget.char_exp_hint.text() == f"Lvl {widget.char_exp_spin.value() // 1000 + 1} + " \
                                          f"{widget.char_exp_spin.value() % 1000} xp"
    widget.char_exp_spin.setValue(21500)
    assert widget.char_exp_hint.text() == "Lvl 22 + 500 xp"
    widget.char_exp_spin.setValue(250000)
    assert widget.char_exp_hint.text() == "Lvl 100 (max)"

    widget.gf_list.setCurrentRow(0)  # Quezacotl: 500 EXP per level in vanilla
    widget.gf_exp_spin.setValue(1250)
    assert widget.gf_exp_hint.text() == "Lvl 3 + 250 xp"

    # f(x): the formula with the GF's two kernel.bin bytes, following the EXP as it is edited
    widget._open_level_popup("gf")
    popup = widget.level_popup
    assert popup.title.text() == "Level from EXP: Quezacotl"
    assert "A (linear) = 50, B (quadratic) = 0" in popup.parameters.text()
    assert "byte 24 (A) and byte 25 (B)" in popup.parameters.text()
    assert "GF level modifier 1" in popup.parameters.text()
    assert popup.substituted.text().endswith("Lvl 3 + 250 xp (250 to the next level)")
    widget.gf_exp_spin.setValue(4100)
    assert popup.substituted.text().endswith("Lvl 9 + 100 xp (400 to the next level)")

    widget.kernel_names.binding.registry.close_file("kernel.bin")
    assert widget.gf_exp_hint.text() == "Lvl ? (needs kernel.bin)"
    assert "No kernel.bin is open" in popup.parameters.text()
    popup.close()
