"""Long loaded-file names fit the viewport and leave the close cross visible."""
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from Ifrit.ifritmonsterwidget import IfritMonsterWidget


@pytest.fixture
def shell():
    widget = IfritMonsterWidget(settings=QSettings("test", "ifrit_list_width"),
                                icon_path="Resources", game_data_folder="FF8GameData")
    widget.resize(1100, 500)
    listing = widget._file_list
    listing.blockSignals(True)
    listing.addItems([f"c0m{index:03d}.dat - " + "Very long monster name " * 12
                      for index in range(40)])
    listing.blockSignals(False)
    widget.show()
    QApplication.processEvents()
    return widget


@pytest.mark.parametrize("width", [140, 220, 400])
def test_rows_fit_after_resize_and_close_cross_stays_clickable(shell, width):
    listing = shell._file_list
    shell._splitter.setSizes([width, shell.width() - width])
    for _ in range(3):
        QApplication.processEvents()
    assert listing.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not listing.horizontalScrollBar().isVisible()
    assert listing.horizontalScrollBar().maximum() == 0
    assert listing.verticalScrollBar().isVisible()
    delegate = listing.itemDelegate()
    index = listing.model().index(1, 0)
    rect = listing.visualRect(index)
    assert rect.width() <= listing.viewport().width()
    cross = delegate.cross_rect(rect)
    assert listing.viewport().rect().contains(cross)
    closed = Mock()
    delegate._on_close = closed
    QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton, pos=cross.center())
    closed.assert_called_once_with(1)


def test_rows_refit_when_existing_list_is_narrowed(shell):
    listing = shell._file_list
    shell._splitter.setSizes([450, 650])
    QApplication.processEvents()
    shell._splitter.setSizes([150, 950])
    for _ in range(3):
        QApplication.processEvents()
    for row in range(5):
        rect = listing.visualRect(listing.model().index(row, 0))
        assert rect.width() <= listing.viewport().width()
        assert listing.viewport().rect().contains(listing.itemDelegate().cross_rect(rect))
