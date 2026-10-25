"""Every tool fits a 1080p desktop without vertical scrolling; the default window fits 720p."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect, QSize, Qt
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


def test_every_tool_fits_1080p_without_vertical_scroll(window):
    # 1920x1080 maximized: the taskbar and the title bar leave a 1920x1001 client area
    assert window._tool_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    for index in range(window.tool_stack.count()):
        window.tool_stack.setCurrentIndex(index)
        window.resize(1920, 1001)
        settle()
        name = type(window.tool_stack.currentWidget()).__name__
        assert window.minimumSizeHint().height() <= 1001, name
        assert window.size() == QSize(1920, 1001), name
        # The tool fills the window exactly: nothing hidden below, no blank space to scroll into
        assert window._tool_scroll.widget().height() == window._tool_scroll.viewport().height(), name


def test_hidden_tools_stop_contributing(window):
    window.resize(1920, 1001)
    window.tool_stack.setCurrentWidget(window._cid_widget)
    settle()
    window.tool_stack.setCurrentWidget(window._ifrit_widget)
    settle()
    assert window.tool_stack.minimumSizeHint().height() < 640
    # A word-wrapped label in another tool (height-for-width) must not stretch this one
    assert not window._tool_scroll.widget().hasHeightForWidth()
    assert window._tool_scroll.widget().height() == window._tool_scroll.viewport().height()


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
