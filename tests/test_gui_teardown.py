"""Destroying the GUI must not take the process down with it.

PyQt kills the process outright - abort(), exit code 0xC0000409, no exception and no message - for
two things this project did in several places:
  * destroying a QThread that is still running (ToolUpdateWidget started its download thread in
    its constructor and never stopped it);
  * letting an exception escape a Qt slot, which is what a QTimer.singleShot callback does when it
    finally runs on widgets whose C++ objects have already been deleted ("wrapped C/C++ object has
    been deleted").

Both showed up the same way: a test suite that died mid-run with no failure and no summary. A
module built a widget, its fixtures expired, the widget was garbage-collected, and the process
went down during whatever unrelated test happened to run the event loop next - a green run that
looked like a crash, naming a different innocent test each time.

These tests destroy the widgets on purpose, then drain the event queue, and assert the process is
still there. They would have caught both: they fail (by dying) on the old code.
"""
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_update_widget_does_not_run_a_thread_until_it_is_asked_to():
    """The download thread is what makes the widget dangerous to destroy, and nothing needs it
    before the user clicks Update - so it must not be running just because the editor is open."""
    from ToolUpdate.toolupdatewidget import ToolUpdateWidget

    widget = ToolUpdateWidget(QSettings("test", "toolupdate"), lambda: [])
    assert widget.installer_thread.isRunning() is False


def test_the_update_widget_survives_being_destroyed():
    from ToolUpdate.toolupdatewidget import ToolUpdateWidget

    widget = ToolUpdateWidget(QSettings("test", "toolupdate"), lambda: [])
    del widget
    gc.collect()          # the process aborts here on the old code


def test_a_started_download_thread_is_stopped_on_close():
    """Once it HAS been started, closing the widget has to stop it - the destructor that follows
    would abort otherwise."""
    from ToolUpdate.toolupdatewidget import ToolUpdateWidget

    widget = ToolUpdateWidget(QSettings("test", "toolupdate"), lambda: [])
    widget.installer_thread.start()
    assert widget.installer_thread.isRunning()

    widget.close()
    assert widget.installer_thread.isRunning() is False
    del widget
    gc.collect()


@pytest.mark.ff8data("FF8GameData/Resources/json/kernel_bin_data.json")
def test_the_whole_editor_survives_being_destroyed():
    """The real shape of the bug: the main window owns the update widget, so building the editor
    and dropping it was enough to kill the process."""
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget

    window = FF8UltimateEditorWidget(os.path.join(REPO, "Resources"),
                                     os.path.join(REPO, "FF8GameData"))
    del window
    gc.collect()


# ---------------------------------------------------------------------------
# Deferred calls that outlive the widget that scheduled them
# ---------------------------------------------------------------------------

MONSTER = os.path.join(REPO, "extracted_files", "battle", "c0m001.dat")


@pytest.mark.ff8data("extracted_files/battle/c0m001.dat")
def test_a_closed_file_pane_leaves_no_deferred_call_behind():
    """The editors finish some work one tick later (restore a scroll position, size a splitter,
    clear the loading flag). Scheduled with a bare QTimer.singleShot, those calls outlived the
    pane: closing the file - or a test simply dropping the widget - deleted the C++ objects, and
    the callback then ran on the wreckage, raising inside a Qt slot and aborting the process.

    Draining the event queue after dropping the pane is exactly what the next test does, and what
    the running editor does constantly, so it must be safe."""
    from PyQt6.QtWidgets import QApplication
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    widget = IfritMonsterWidget(settings=QSettings("test", "gui_teardown"),
                                icon_path=os.path.join(REPO, "Resources"),
                                game_data_folder=os.path.join(REPO, "FF8GameData"))
    widget._ask_ram_budget = lambda *a: True
    widget.load_file(MONSTER)
    assert len(widget._files) == 1

    del widget
    gc.collect()
    QApplication.processEvents()      # the process dies here on the old code
    QApplication.processEvents()


def test_a_deferred_call_is_dropped_when_its_owner_dies():
    """Common.deferredcall.defer is the fix, and this is the property it exists for.

    The owner is dropped and collected - destroyed there and then, which is what happens to a pane
    when its file is closed - and only then is the event queue drained, exactly as the crash did
    it. A bare QTimer.singleShot would run its callback at that point; this must not."""
    from PyQt6.QtWidgets import QApplication, QWidget
    from Common.deferredcall import defer

    called = []
    owner = QWidget()
    defer(owner, lambda: called.append("ran"))
    del owner
    gc.collect()
    QApplication.processEvents()
    QApplication.processEvents()
    assert called == [], "the deferred call outlived the widget that owned it"


def test_a_deferred_call_still_runs_for_a_living_owner():
    """...without breaking the reason the deferral is there in the first place."""
    from PyQt6.QtWidgets import QApplication, QWidget
    from Common.deferredcall import defer

    called = []
    owner = QWidget()
    defer(owner, lambda: called.append("ran"))
    QApplication.processEvents()
    QApplication.processEvents()
    assert called == ["ran"]
