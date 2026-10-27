"""Ifrit's Opening dialog when switching to a file: its number of steps is known before the first
one (textures, animations, the editor, then one per tab the file shows), so the bar goes once from
Step 1/N to Step N/N instead of growing its total and jumping back midway."""
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
SOLDIER = "extracted_files/battle/c0m071.dat"
BODY = "extracted_files/battle/d0c000.dat"
WEAPON = "extracted_files/battle/d0w000.dat"


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
    current = widget._active_index
    for index in [i for i in (0, 1, 2) if i != current] + [current]:     # each file, a real switch
        seen.clear()
        widget._activate_index(index, show_busy=True)
        tabs = widget._files[index]['pane']._tabs
        shown = sum(tabs.isTabVisible(i) for i in range(tabs.count()))
        total = 3 + shown
        assert [maximum for _value, maximum, _label in seen] == [total] * total
        assert [value for value, _maximum, _label in seen] == list(range(total))
        assert f"Step {total}/{total}: Loading tab" in seen[-1][2]
    widget.close()
