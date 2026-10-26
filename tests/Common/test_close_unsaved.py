"""Closing the editor with unsaved edits asks first: Discard closes, Cancel keeps it open."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPlainTextEdit, QLineEdit, QTextEdit

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def main_window():
    _app = QApplication.instance() or QApplication(sys.argv)
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget
    return FF8UltimateEditorWidget("Resources", "FF8GameData")


def _answer(monkeypatch, button, asked):
    def fake_warning(*args, **kwargs):
        asked.append(args[2])   # the message text
        return button
    monkeypatch.setattr(QMessageBox, "warning", fake_warning)


def test_clean_editor_closes_without_asking(main_window, monkeypatch):
    asked = []
    _answer(monkeypatch, QMessageBox.StandardButton.Cancel, asked)
    assert main_window.unsaved_tool_names() == []
    assert main_window.close() is True
    assert asked == []


def test_unsaved_edits_ask_and_cancel_keeps_the_window(main_window, monkeypatch):
    siren = main_window._siren_widget
    siren.dirty_state.mark()
    try:
        asked = []
        _answer(monkeypatch, QMessageBox.StandardButton.Cancel, asked)
        assert main_window.close() is False
        assert len(asked) == 1 and "Siren (price.bin editor)" in asked[0]

        _answer(monkeypatch, QMessageBox.StandardButton.Discard, asked)
        assert main_window.close() is True
    finally:
        siren.dirty_state.clear()


def test_edits_outside_widgets_count_too(main_window, monkeypatch):
    """Seed edits animations in its 3D viewer, not in a tracked widget: its own hook answers."""
    seed = main_window._seed_widget
    monkeypatch.setattr(seed.seed_manager, "modified_entry_names", lambda: ["d000"])
    assert "Seed (Field model viewer)" in main_window.unsaved_tool_names()


@pytest.mark.ff8data("extracted_files")
def test_shumitranslator_tab_tracks_its_own_edits(main_window, tmp_path):
    shumi = main_window._shumi_translator_widget
    main_window.tool_stack.setCurrentWidget(shumi)   # Shumi only builds a tab while it is shown
    kernel = str(shutil.copy(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin", tmp_path))
    main_window.file_registry.open_file("kernel.bin", kernel)
    pane = shumi.tab_widget.currentWidget()
    assert pane is not None
    assert not shumi.has_unsaved_changes()           # loading is not an edit
    assert "ShumiTranslator(All text editor)" not in main_window.unsaved_tool_names()

    editor = next(w for w in pane.findChildren((QLineEdit, QPlainTextEdit, QTextEdit)) if w.isEnabled())
    if isinstance(editor, QLineEdit):
        editor.textEdited.emit("edited")
    else:
        editor.setPlainText("edited")
    assert shumi.has_unsaved_changes()
    assert "ShumiTranslator(All text editor)" in main_window.unsaved_tool_names()
    pane.dirty_state.clear()


def test_self_update_restart_closes_the_editor_window(main_window):
    """The update closes this window first, so the unsaved-changes question comes up there."""
    assert main_window._tool_update_widget.window() is main_window


def test_scrollbars_and_loads_never_mark_dirty(main_window):
    """Scrolling a view and a tool filling its widgets during a load are not edits: they used
    to star the title (Xu, Chocoboy, CCGroup) and would now pop the close question for nothing."""
    from PyQt6.QtWidgets import QScrollBar, QSpinBox, QWidget
    from Common.dirtytracking import DirtyState, ignoring_marks
    tool = QWidget()
    scrollbar, spin = QScrollBar(tool), QSpinBox(tool)
    state = DirtyState(tool)
    state.track(tool)
    scrollbar.setValue(scrollbar.value() + 1)
    assert not state.dirty
    with ignoring_marks():
        spin.setValue(spin.value() + 1)
    assert not state.dirty
    spin.setValue(spin.value() + 1)   # a real edit still counts
    assert state.dirty
