"""Ifrit multi-file shell: closing single files from the side list (the cross on each row) and the
'modified' flag following real changes only.

  * Browsing - another AI section, another AI editing mode, hex display - is not an edit.
  * A value changed then put back leaves the file clean (the flag compares the file's bytes).
  * The cross of a row closes that file; the shown file's unsaved edits ask Save / Discard / Cancel,
    and Discard really drops them (the model goes back to the file on disk).
"""
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QSpinBox
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
NAMES = [f"c0m{i:03d}.dat" for i in range(3)]

pytestmark = pytest.mark.skipif(not all(os.path.isfile(os.path.join(BATTLE, n)) for n in NAMES),
                                reason="c0m000-c0m002.dat not available")


@pytest.fixture
def files(tmp_path):
    paths = []
    for n in NAMES:
        shutil.copy(os.path.join(BATTLE, n), tmp_path / n)
        paths.append(str(tmp_path / n))
    return paths


def _make(files):
    w = IfritMonsterWidget(settings=QSettings("test", "ifrit_close_dirty"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w.resize(1200, 800)
    w.show()
    w._build_session(files)
    _settle()
    return w


def _settle():
    for _ in range(5):
        QApplication.processEvents()


def _pane(w):
    return w._files[w._active_index]['pane']


def _commit(w):
    """What the 500 ms debounce does after an edit."""
    _settle()
    w._undo_debounce.stop()
    w._commit_active_undo()


def _answer(monkeypatch, button):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: button)


def _first_ai_spin(pane):
    pane._tabs.setCurrentWidget(pane._ai_container)
    _settle()
    ai = pane._ai_widget
    for row in ai.command_line_widget:     # hex-editor mode: each parameter is a plain spin box
        if row.get_command().get_op_code() and isinstance(row.widget_op_code[0], QSpinBox):
            return row.widget_op_code[0]
    return None


# ── false 'modified' ──────────────────────────────────────────────────

def test_browsing_ai_sections_and_modes_does_not_modify(files):
    w = _make(files)
    pane = _pane(w)
    pane._tabs.setCurrentWidget(pane._ai_container)
    _settle()
    ai = pane._ai_widget
    for k in range(ai.script_section.count()):
        ai.script_section.setCurrentIndex(k)
        ai.script_section.activated.emit(k)
        _settle()
    for k in range(ai.expert_selector.count()):
        ai.expert_selector.setCurrentIndex(k)
        ai.expert_selector.activated.emit(k)
        _settle()
    ai.hex_selector.click()
    ai.hex_selector.click()
    _commit(w)
    assert not pane.dirty
    assert not w._list_label(w._active_index).startswith("*")


def test_every_tab_and_sub_tab_is_clean_after_browsing(files):
    w = _make(files)
    pane = _pane(w)
    for t in range(pane._tabs.count()):
        if pane._tabs.isTabVisible(t):
            pane._tabs.setCurrentIndex(t)
            _settle()
    for sub in (pane._stat_container, pane._ai_container):
        for k in range(sub.count()):
            sub.setCurrentIndex(k)
            _settle()
    _commit(w)
    assert not pane.dirty


def test_real_ai_edit_after_switching_section_is_detected(files):
    """Switching section rebuilds the command rows; edits on the new rows still count."""
    w = _make(files)
    pane = _pane(w)
    pane._tabs.setCurrentWidget(pane._ai_container)
    _settle()
    ai = pane._ai_widget
    ai.expert_selector.setCurrentIndex(1)            # hex-editor: plain spin boxes
    ai.expert_selector.activated.emit(1)
    spin = None
    for k in range(ai.script_section.count()):       # another section with an editable parameter
        if k == ai.script_section.currentIndex():
            continue
        ai.script_section.setCurrentIndex(k)
        ai.script_section.activated.emit(k)
        _settle()
        spin = _first_ai_spin(pane)
        if spin is not None:
            break
    assert spin is not None
    old = spin.value()
    spin.setValue(old + 1 if old < spin.maximum() else old - 1)
    _commit(w)
    assert pane.dirty


def test_value_put_back_is_clean(files):
    w = _make(files)
    pane = _pane(w)
    pane._tabs.setCurrentWidget(pane._ai_container)
    _settle()
    ai = pane._ai_widget
    ai.expert_selector.setCurrentIndex(1)
    ai.expert_selector.activated.emit(1)
    _settle()
    spin = _first_ai_spin(pane)
    if spin is None:
        pytest.skip("no AI command in the default section")
    old = spin.value()
    spin.setValue(old + 1 if old < spin.maximum() else old - 1)
    _commit(w)
    assert pane.dirty
    spin = _first_ai_spin(pane)                      # the row rebuilds its controls on change
    spin.setValue(old)
    _commit(w)
    assert not pane.dirty


# ── closing files ─────────────────────────────────────────────────────

def test_closing_another_file_keeps_the_shown_one(files):
    w = _make(files)
    w._activate_index(1)
    shown = w._files[1]
    w._close_file(0)
    assert len(w._files) == 2 and w._file_list.count() == 2
    assert w._files[w._active_index] is shown
    assert w._file_list.currentRow() == w._active_index == 0


def test_closing_the_shown_file_shows_its_neighbour(files):
    w = _make(files)
    w._activate_index(2)
    w._close_file(2)
    assert [os.path.basename(f['path']) for f in w._files] == NAMES[:2]
    assert w._active_index == 1 and w._files[1]['pane'] is not None


def test_closing_the_last_file_empties_the_session(files):
    w = _make(files[:1])
    w._close_file(0)
    assert w._files == [] and w._active_index == -1
    assert w._stack.currentWidget() is w._placeholder
    assert w.REGISTRY_NAME not in w.file_registry.paths


def _make_ai_edit(w):
    pane = _pane(w)
    ai = pane._ai_widget
    ai.expert_selector.setCurrentIndex(1)
    ai.expert_selector.activated.emit(1)
    spin = _first_ai_spin(pane)
    old = spin.value()
    spin.setValue(old + 1 if old < spin.maximum() else old - 1)
    _commit(w)
    assert pane.dirty


def test_close_dirty_cancel_keeps_it(files, monkeypatch):
    w = _make(files)
    _make_ai_edit(w)
    _answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    w._close_file(0)
    assert len(w._files) == 3 and _pane(w).dirty


def test_close_dirty_discard_leaves_disk_untouched(files, monkeypatch):
    before = open(files[0], "rb").read()
    w = _make(files)
    _make_ai_edit(w)
    _answer(monkeypatch, QMessageBox.StandardButton.Discard)
    w._close_file(0)
    assert len(w._files) == 2
    assert open(files[0], "rb").read() == before


def test_close_dirty_save_writes_it(files, monkeypatch):
    before = open(files[0], "rb").read()
    w = _make(files)
    _make_ai_edit(w)
    _answer(monkeypatch, QMessageBox.StandardButton.Save)
    w._close_file(0)
    assert len(w._files) == 2
    assert open(files[0], "rb").read() != before


def test_discard_when_switching_really_drops_the_edit(files, monkeypatch):
    """Editors write the model live: Discard must put the file back to its on-disk content, not
    just hide the '*' (the edit used to come back on reopening, and be saved later)."""
    w = _make(files)
    disk = bytes(w._files[0]['manager'].enemy.get_bytes(w._game_data))
    _make_ai_edit(w)
    _answer(monkeypatch, QMessageBox.StandardButton.Discard)
    w._activate_index(1)
    assert bytes(w._files[0]['manager'].enemy.get_bytes(w._game_data)) == disk
    w._activate_index(0)
    _commit(w)
    assert not _pane(w).dirty


def test_clicking_the_cross_closes_that_row(files):
    w = _make(files)
    lst = w._file_list
    delegate = lst.itemDelegate()
    rect = lst.visualRect(lst.model().index(1, 0))
    pos = delegate.cross_rect(rect).center()
    QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    _settle()
    assert [os.path.basename(f['path']) for f in w._files] == [NAMES[0], NAMES[2]]
    assert w._active_index == 0                      # the cross does not select/open the row


def test_clicking_the_name_still_selects(files):
    w = _make(files)
    lst = w._file_list
    rect = lst.visualRect(lst.model().index(1, 0))
    QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(rect.left() + 10, rect.center().y()))
    _settle()
    assert len(w._files) == 3 and w._active_index == 1
