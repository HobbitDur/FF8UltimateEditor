"""All tools must remain accessible in a window that fits a 720p desktop."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect, QSize
from PyQt6.QtWidgets import QApplication

from ff8ultimateeditorwidget import FF8UltimateEditorWidget


@pytest.fixture(scope="module")
def window():
    app = QApplication.instance() or QApplication([])
    widget = FF8UltimateEditorWidget()
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def settle():
    # Tool switches can post several layout requests through nested tabs and scroll areas.
    for _ in range(4):
        QApplication.processEvents()


def test_default_fits_720p_and_reserves_desktop_space(window, monkeypatch):
    monkeypatch.setattr(window, "screen", lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(0, 0, 1280, 680)))
    window._resize_for_screen()
    settle()
    assert window.size() == QSize(1200, 600)
    assert window.frameGeometry().width() <= 1280
    assert window.frameGeometry().height() < 720


def test_every_tool_can_expand_then_shrink_below_720p(window):
    for index in range(window.tool_stack.count()):
        window.tool_stack.setCurrentIndex(index)
        window.resize(1600, 1000)
        settle()
        assert window.size() == QSize(1600, 1000)
        window.resize(1200, 640)
        settle()
        name = type(window.tool_stack.currentWidget()).__name__
        assert window.size() == QSize(1200, 640), name
        assert window.minimumSizeHint().height() < 640, name
        assert window._tool_scroll.viewport().height() > 300, name


def test_tall_editor_scrolls_and_hidden_tools_stop_contributing(window):
    window.resize(1200, 640)
    window.tool_stack.setCurrentWidget(window._cid_widget)
    settle()
    area = window._tool_scroll
    bar = area.verticalScrollBar()
    assert bar.maximum() > 0  # Cid's form needs more than the available height.
    bar.setValue(bar.maximum())
    settle()
    assert area.widget().geometry().bottom() <= area.viewport().height()

    window.tool_stack.setCurrentWidget(window._ifrit_widget)
    settle()
    assert window.tool_stack.minimumSizeHint().height() < 640
    assert bar.maximum() == 0  # Hidden Cid/Fujin forms must not leave a tall blank canvas.


def test_expanded_file_list_cannot_force_window_beyond_desktop(window):
    window.resize(1200, 640)
    registry = window.file_registry
    panel = window._opened_files_panel
    for index in range(40):
        registry.open_file(f"layout_dummy_{index}.bin", f"layout/dummy_{index}.bin")
    panel.header_button.setChecked(True)
    settle()
    assert window.size() == QSize(1200, 640)
    assert window._header_scroll.height() <= 180
    assert window._header_scroll.verticalScrollBar().maximum() > 0
    assert window._tool_scroll.viewport().height() > 300
    panel.header_button.setChecked(False)
    for index in range(40):
        registry.close_file(f"layout_dummy_{index}.bin")
    settle()
    assert window._header_scroll.verticalScrollBar().maximum() == 0


def test_smaller_desktop_and_manual_resize_remain_supported(window, monkeypatch):
    monkeypatch.setattr(window, "screen", lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(0, 0, 1024, 600)))
    window._resize_for_screen()
    settle()
    assert window.size() == QSize(984, 520)
    window.resize(900, 500)
    settle()
    assert window.size() == QSize(900, 500)
