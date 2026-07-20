"""The Ifrit multi-file shell (Ifrit/ifritmonsterwidget.py) uses a deliberately simple model:

  * Opening files only parses each LEAN (structure + name for the side list) - no textures, no
    expanded animation, no editor widgets.
  * Exactly ONE file is fully loaded at a time. Clicking a file builds its whole editor (textures
    + expanded animation + all tabs + the 3D GL viewer) and tears the previous one down, freeing
    its 3D context and its ~30 MB expanded animation. No preload, no LRU, no RAM budget.
  * Switching away from a file with unsaved edits asks Save / Discard / Cancel first.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
FILES = [os.path.join(BATTLE, f"c0m{i:03d}.dat") for i in range(4)]

pytestmark = pytest.mark.skipif(not all(os.path.isfile(p) for p in FILES),
                                reason="c0m000-c0m003.dat not available")


def _make():
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "single_pane"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w.show()
    return w


def _built(w):
    return [i for i, f in enumerate(w._files) if f['pane'] is not None]


def _anim_expanded(w):
    return [i for i, f in enumerate(w._files)
            if getattr(f['manager'].enemy, '_animation_expanded', False)]


def test_opening_files_builds_no_panes_but_the_shown_one():
    w = _make()
    w._build_session(FILES)
    assert len(w._files) == 4
    assert _built(w) == [0] == [w._active_index]     # only the shown file is fully loaded


def test_switching_tears_the_previous_pane_down():
    w = _make()
    w._build_session(FILES)
    first_pane = w._files[0]['pane']
    w._activate_index(2)
    assert _built(w) == [2]                            # exactly one pane, the new one
    assert w._files[0]['pane'] is None                 # the previous was destroyed
    assert first_pane is not w._files[2]['pane']


def test_only_the_shown_file_has_an_expanded_animation():
    w = _make()
    w._build_session(FILES)
    assert _anim_expanded(w) == [0]                    # the others stay lean
    w._activate_index(3)
    assert _anim_expanded(w) == [3]                    # switching frees the old, expands the new


def test_no_ram_budget_or_preload_api_remains():
    w = _make()
    for gone in ("_ram_budget_spin", "_pane_cap", "_pane_lru", "_ensure_pane",
                 "_prebuild_panes", "_evict_pane", "_free_inactive_pane_animations"):
        assert not hasattr(w, gone), f"{gone} should be gone in the simple model"


# ── Unsaved-edit guard on switch ────────────────────────────────────
def test_cancel_on_unsaved_edits_aborts_the_switch(monkeypatch):
    w = _make()
    w._build_session(FILES)
    w._files[0]['pane'].dirty = True
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Cancel)
    w._activate_index(1)
    assert w._active_index == 0                         # stayed on the dirty file
    assert _built(w) == [0]


def test_discard_on_unsaved_edits_switches_and_drops_edits(monkeypatch):
    w = _make()
    w._build_session(FILES)
    w._files[0]['pane'].dirty = True
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Discard)
    w._activate_index(1)
    assert w._active_index == 1                         # moved on, edits discarded
    assert _built(w) == [1]


def test_save_on_unsaved_edits_saves_then_switches(monkeypatch, tmp_path):
    import shutil
    local = str(tmp_path / "c0m000.dat")
    shutil.copyfile(FILES[0], local)
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "single_pane_save"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w.show()
    w._build_session([local, FILES[1]])
    saved = {"n": 0}
    orig_save = w._files[0]['pane'].save
    def spy():
        saved["n"] += 1
        return orig_save()
    w._files[0]['pane'].save = spy
    w._files[0]['pane'].dirty = True
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Save)
    w._activate_index(1)
    assert saved["n"] == 1                              # it saved before leaving
    assert w._active_index == 1
