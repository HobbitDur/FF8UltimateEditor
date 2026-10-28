"""Ifrit's Opening dialog when switching to a file: its number of steps is known before the first
one (textures, animations, the editor, then one per tab the file shows and loads), so the bar goes
once from Step 1/N to Step N/N instead of growing its total and jumping back midway - and never
past it ("Step 9/8"): the "Exe - Limit anim." tab of a character body / weapon counts only when it
loads (the exe or an .animset open); without one it is greyed and loads nothing."""
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
SOLDIER = "extracted_files/battle/c0m071.dat"
BODY = "extracted_files/battle/d0c000.dat"
WEAPON = "extracted_files/battle/d0w000.dat"


EXE = "extracted_files/FF8_EN.exe"


def _check_every_file(widget, seen):
    current = widget._active_index
    for index in [i for i in (0, 1, 2) if i != current] + [current]:     # each file, a real switch
        seen.clear()
        widget._activate_index(index, show_busy=True)
        tabs = widget._files[index]['pane']._tabs
        usable = sum(tabs.isTabVisible(i) and tabs.isTabEnabled(i) for i in range(tabs.count()))
        total = 3 + usable
        assert [maximum for _value, maximum, _label in seen] == [total] * total
        assert [value for value, _maximum, _label in seen] == list(range(total))
        assert all(int(label.split("Step ")[1].split("/")[0]) <= total for _v, _m, label in seen)
        assert f"Step {total}/{total}: Loading tab" in seen[-1][2]


@pytest.mark.ff8data(SOLDIER, BODY, WEAPON)
def test_opening_bar_only_moves_forward(tmp_path, monkeypatch):
    QApplication.instance() or QApplication(sys.argv)
    from PyQt6.QtCore import QSettings
    import Ifrit.ifritmonsterwidget as imw
    seen = []
    step = imw._OpeningProgress.step

    def record(self, text):
        step(self, text)
        seen.append((self.dialog.value(), self.dialog.maximum(), self.dialog.labelText()))

    monkeypatch.setattr(imw._OpeningProgress, "step", record)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = imw.IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    widget._ask_ram_budget = lambda *a: True
    widget.load_file(str(ROOT / SOLDIER))
    widget._append_to_session([str(ROOT / BODY), str(ROOT / WEAPON)])
    _check_every_file(widget, seen)      # no exe: the anim set tab of the body / weapon is greyed
    widget.close()


@pytest.mark.ff8data(SOLDIER, BODY, WEAPON, EXE)
def test_opening_bar_counts_the_anim_set_tab_with_the_exe(tmp_path, monkeypatch):
    QApplication.instance() or QApplication(sys.argv)
    from PyQt6.QtCore import QSettings
    from Common.fileregistry import FileRegistry
    import Ifrit.ifritmonsterwidget as imw
    from Ifrit.IfritAnimSet.ifritanimsetwidget import EXE_FILE_NAME
    seen = []
    step = imw._OpeningProgress.step

    def record(self, text):
        step(self, text)
        seen.append((self.dialog.value(), self.dialog.maximum(), self.dialog.labelText()))

    monkeypatch.setattr(imw._OpeningProgress, "step", record)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    registry = FileRegistry()
    widget = imw.IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData",
                                    file_registry=registry)
    widget._ask_ram_budget = lambda *a: True
    registry.open_file(EXE_FILE_NAME, str(ROOT / EXE))     # only read here
    widget.load_file(str(ROOT / SOLDIER))
    widget._append_to_session([str(ROOT / BODY), str(ROOT / WEAPON)])
    _check_every_file(widget, seen)
    # Squall's body and gunblade: their anim set tab loaded and was counted
    for index in (1, 2):
        widget._activate_index(index)
        pane = widget._files[index]['pane']
        assert pane._tabs.isTabEnabled(pane._tabs.indexOf(pane._anim_set_widget))
    widget.close()
