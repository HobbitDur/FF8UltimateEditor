import sys

import pytest
from PyQt6.QtWidgets import QApplication, QListWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_the_list_grows_to_its_longest_item_within_bounds(qapp):
    from SmallWidget.fitwidth import fit_list_width
    widget = QListWidget()
    fit_list_width(widget)
    assert widget.width() == 240  # empty: the minimum
    widget.addItem("26: Weapons Monthly August Issue 3/4" * 2)
    fit_list_width(widget, minimum=10, maximum=10000)
    assert widget.width() > widget.sizeHintForColumn(0)  # the whole text, plus the frame and bar
    fit_list_width(widget, minimum=10, maximum=100)
    assert widget.width() == 100


def test_a_value_combo_shows_its_names_in_full(qapp):
    """Closed, at least ~16 characters wide; open, the drop-down is as wide as the longest name."""
    from SmallWidget.valuecombo import ValueComboBox
    combo = ValueComboBox()
    combo.set_choices([(0, "0: short"), (1, "1: a much longer name than the box itself shows")])
    assert combo.minimumContentsLength() == 16
    assert combo.view().minimumWidth() > combo.view().sizeHintForColumn(0)
