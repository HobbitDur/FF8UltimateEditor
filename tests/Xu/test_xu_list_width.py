"""Xu's fixed list column fits every complete model name without horizontal scrolling."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem

from Xu.xuwidget import XuWidget


@pytest.fixture
def widget():
    w = XuWidget()
    w.manager.monster_names[71] = "G-Soldier with a longer alternate model name"
    w._fill_row_list()
    w.resize(1400, 800)
    w.show()
    QApplication.processEvents()
    return w


def assert_full_names_fit(widget):
    listing = widget.row_list
    option = QStyleOptionViewItem()
    option.initFrom(listing)
    option.widget = listing
    assert listing.textElideMode() == Qt.TextElideMode.ElideNone
    assert listing.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not listing.horizontalScrollBar().isVisible()
    assert listing.horizontalScrollBar().maximum() == 0
    for row in range(listing.count()):
        size = listing.itemDelegate().sizeHint(option, listing.model().index(row, 0))
        assert size.width() <= listing.viewport().width()


def test_list_has_fixed_width_and_shows_full_names(widget):
    holder = widget._row_list_holder
    assert holder.minimumWidth() == holder.maximumWidth() == holder.width()
    assert_full_names_fit(widget)


def test_resizing_and_splitter_drag_do_not_narrow_the_list(widget):
    holder = widget._row_list_holder
    width = holder.width()
    widget.resize(1100, 700)
    holder.parentWidget().setSizes([20, 500, 500])
    for _ in range(3):
        QApplication.processEvents()
    assert holder.width() == width
    assert_full_names_fit(widget)


def test_filtering_keeps_the_full_name_width(widget):
    width = widget._row_list_holder.width()
    widget.filter_edit.setText("Squall")
    QApplication.processEvents()
    assert widget._row_list_holder.width() == width
    assert_full_names_fit(widget)


def test_new_names_update_the_fixed_width(widget):
    width = widget._row_list_holder.width()
    widget.manager.monster_names[71] += " with another long description"
    widget._fill_row_list()
    QApplication.processEvents()
    assert widget._row_list_holder.width() > width
    assert_full_names_fit(widget)
