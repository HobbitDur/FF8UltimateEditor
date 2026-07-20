"""The shared-toolbar Reload button (Common/filetoolbarwidget.py) fires FileRegistry.reload_all(),
which emits reload_requested to every tool. Tools with a per-file FileBinding re-read through the
binding; Ifrit is an Alexander-pattern tool with NO binding, so it must subscribe to the registry
signal directly. Before the fix, Reload was a silent no-op for Ifrit (reload_requested had zero
receivers). These tests lock in that Ifrit reloads all its files from disk on that signal, keeping
the single-live-GL-context guarantee.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from Common.fileregistry import FileRegistry
from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
MONSTER_FILES = [os.path.join(BATTLE, f"c0m{i:03d}.dat") for i in range(4)]

pytestmark = pytest.mark.skipif(
    not all(os.path.isfile(p) for p in MONSTER_FILES),
    reason="c0m000-c0m003.dat not available")


def _make_widget(name, registry):
    settings = QSettings("test", name)
    settings.setValue("ifrit/ram_budget_gb", 6)     # preload all 4
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=settings, icon_path="Resources",
                           game_data_folder="FF8GameData", file_registry=registry)
    w._game_data = base.game_data
    w.show()
    return w


def _live_gl(w):
    return [i for i, f in enumerate(w._files)
            if f['pane'] is not None and f['pane']._3d_widget.gl_widget is not None]


def test_ifrit_subscribes_to_the_shared_reload_signal():
    reg = FileRegistry()
    w = _make_widget("reload_sub", reg)
    assert reg.receivers(reg.reload_requested) >= 1   # was 0 -> Reload was a no-op


def test_reload_all_reparses_every_file_and_keeps_one_context():
    reg = FileRegistry()
    w = _make_widget("reload_all", reg)
    w._build_session(MONSTER_FILES)
    w._activate_index(2)
    panes_before = [id(f['pane']) for f in w._files if f['pane'] is not None]

    reg.reload_all()                                  # what the toolbar button does

    # every pane got rebuilt from the fresh parse (identities changed)
    panes_after = [id(f['pane']) for f in w._files if f['pane'] is not None]
    assert not (set(panes_before) & set(panes_after))
    # the previously-active file is shown again, with the only live GL context
    assert w._active_index == 2
    assert _live_gl(w) == [2]
    assert all(f['name'] for f in w._files)           # names re-resolved after reparse


def test_reload_with_nothing_loaded_is_a_noop():
    reg = FileRegistry()
    w = _make_widget("reload_empty", reg)
    reg.reload_all()                                  # must not raise with no files open
    assert w._files == []
