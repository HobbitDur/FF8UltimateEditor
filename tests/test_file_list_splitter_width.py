"""The multi-file shell's QSplitter (loaded-files list | active pane) couldn't be dragged wider
than a sliver for the file list unless the window was maximized. Root cause: QTabWidget/
QStackedWidget report the size of their LARGEST page as their own minimumSizeHint - even for a
page that's hidden or never shown - so that floor stacked up at three levels: (1) the 3D tab's
toolbar (a plain QWidget with ~15 controls in one un-wrapped QHBoxLayout, ~2700px wide), (2) a
long single-line help QLabel with no word wrap (~1500px), (3) a pane's own QTabWidget taking the
widest of its 7 tabs regardless of which is shown (up to ~1400px, worse with nested Stat/AI
sub-tabs), and (4) the shell's QStackedWidget of per-file panes taking the widest of ALL loaded
files' panes, not just the active one. Each floor propagated up through the QSplitter, pinning
the file list's max width to whatever the window's total width minus that floor allowed - only
satisfied on very large/maximized windows. Fixed at each level in
Ifrit/Ifrit3D/ifrit3dwidget.py (toolbar wrapped in a horizontally-scrollable QScrollArea, the help
label word-wrapped) and Ifrit/ifritmonsterwidget.py (_shrink_stack_to_current: gives every
non-current page of a QTabWidget/QStackedWidget an Ignored size policy so only the page actually
on screen counts toward its minimumSizeHint).
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
BODY = os.path.join(BATTLE, "d0c000.dat")     # character: exercises the nested Stat/AI sub-tabs too

pytestmark = pytest.mark.skipif(not os.path.isfile(BODY), reason="d0c000.dat not available")


def _make_shell(settings_name):
    settings = QSettings("test", settings_name)
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    return w


def test_a_single_loaded_pane_has_a_small_minimum_width():
    w = _make_shell("splitter_width_single")
    w.load_file(BODY)
    w.show()
    # Before the fix this was 1500-2700+ px (the 3D toolbar's/help label's/other tabs' full width).
    assert w._stack.minimumSizeHint().width() < 700


def test_splitter_honors_a_wide_list_request_in_a_normal_sized_window():
    w = _make_shell("splitter_width_windowed")
    w.load_file(BODY)
    w.show()
    w.resize(1280, 800)   # a typical, NON-maximized window - the exact case that used to fail
    QApplication.processEvents()

    w._splitter.setSizes([600, w.width() - 600])
    QApplication.processEvents()
    assert w._splitter.sizes()[0] >= 550


def test_many_prebuilt_panes_do_not_reintroduce_the_floor():
    """Even a pane that's pre-built but NOT currently active must not count its own width toward
    the shared stack's minimum - only the active pane may."""
    settings = QSettings("test", "splitter_width_multi")
    settings.setValue("ifrit/ram_budget_gb", 5)
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda n: True
    w.show()

    paths = [os.path.join(BATTLE, "c0m000.dat"), os.path.join(BATTLE, "c0m001.dat"), BODY]
    w._build_session(paths)
    assert all(f['pane'] is not None for f in w._files), "test assumes every file got pre-built"

    w.resize(1280, 800)
    QApplication.processEvents()
    assert w._stack.minimumSizeHint().width() < 700

    w._splitter.setSizes([700, w.width() - 700])
    QApplication.processEvents()
    assert w._splitter.sizes()[0] >= 650
