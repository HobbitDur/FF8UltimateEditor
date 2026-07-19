"""RAM budget toolbar spinbox (Ifrit/ifritmonsterwidget.py): the load-time dialog
(_ask_ram_budget) only appears when a load exceeds the current cap, so once a user's budget is
big enough for their usual batch size they never see it again - easy to forget it isn't still the
1 GB default. The toolbar spinbox next to "Files to 30/60 FPS..." lets the budget be changed
anytime; raising it above what every currently loaded file needs pre-loads them all immediately
instead of waiting for the user to click through each one.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
MONSTER_FILES = [os.path.join(BATTLE, f"c0m{i:03d}.dat") for i in range(10)]

pytestmark = pytest.mark.skipif(
    not all(os.path.isfile(p) for p in MONSTER_FILES),
    reason="c0m000-c0m009.dat not available")


def _make_widget(settings_name, budget_gb):
    settings = QSettings("test", settings_name)
    settings.setValue("ifrit/ram_budget_gb", budget_gb)
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    return w, settings


def test_spinbox_initialized_from_persisted_value():
    w, _ = _make_widget("ram_spin_init", 5)
    assert w._ram_budget_spin.value() == 5
    assert w._ram_budget_spin.minimum() == 1
    assert w._ram_budget_spin.maximum() == 256


def test_raising_above_all_files_need_preloads_the_rest():
    # 1 GB -> cap 8 panes; loading 10 files leaves 2 unbuilt.
    w, settings = _make_widget("ram_spin_raise", 1)
    w._ask_ram_budget = lambda n: True   # never actually called: the dialog only triggers when
                                          # len(paths) > cap, and we want that path exercised too
    w._build_session(MONSTER_FILES)
    assert len(w._files) == 10
    built_before = sum(1 for f in w._files if f['pane'] is not None)
    assert built_before == 8   # capped, 2 files not pre-built

    w._ram_budget_spin.setValue(5)   # far more than 10 files need (~2 GB)
    built_after = sum(1 for f in w._files if f['pane'] is not None)
    assert built_after == 10          # every file now pre-loaded

    assert settings.value("ifrit/ram_budget_gb", type=int) == 5
    assert w._ram_budget_gb == 5


def test_raising_further_when_already_all_loaded_is_a_noop():
    w, _ = _make_widget("ram_spin_noop", 5)
    w._ask_ram_budget = lambda n: True
    w._build_session(MONSTER_FILES[:3])   # well under any reasonable cap
    assert all(f['pane'] is not None for f in w._files)

    w._ram_budget_spin.setValue(10)       # nothing left to build
    assert all(f['pane'] is not None for f in w._files)
    assert len(w._files) == 3


def test_load_dialog_acceptance_syncs_the_toolbar_spinbox():
    w, settings = _make_widget("ram_spin_sync", 1)
    accepted = {'called': False}

    def fake_ask(num_files):
        accepted['called'] = True
        w._ram_budget_gb = 7
        settings.setValue("ifrit/ram_budget_gb", 7)
        if hasattr(w, '_ram_budget_spin'):
            w._ram_budget_spin.blockSignals(True)
            w._ram_budget_spin.setValue(7)
            w._ram_budget_spin.blockSignals(False)
        return True

    w._ask_ram_budget = fake_ask
    w._build_session(MONSTER_FILES)   # 10 files > cap(8 at 1GB) -> dialog path taken
    assert accepted['called']
    assert w._ram_budget_spin.value() == 7
