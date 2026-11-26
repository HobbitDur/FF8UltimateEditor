"""ValueComboBox: named choices for a raw number, with the spin box API the forms already use."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from SmallWidget.valuecombo import ValueComboBox


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_a_value_outside_the_choices_is_kept_and_shown(qapp):
    combo = ValueComboBox(fallback="unknown")
    combo.set_choices([(0, "0: zero"), (1, "1: one")])
    combo.setValue(7)
    assert combo.value() == 7 and combo.currentText() == "7: unknown"
    combo.setValue(1)
    assert combo.currentText() == "1: one"
    assert combo.findText("7: unknown") < 0  # the fallback entry went with the value


def test_picking_a_choice_emits_valueChanged_and_programmatic_set_when_unblocked(qapp):
    combo = ValueComboBox()
    combo.set_choices([(0, "a"), (5, "b")])
    seen = []
    combo.valueChanged.connect(seen.append)
    combo.setCurrentIndex(combo.findData(5))  # as the user picking it
    combo.blockSignals(True)
    combo.setValue(0)  # a form being filled: silent
    combo.blockSignals(False)
    assert seen == [5] and combo.value() == 0


def test_new_choices_keep_the_value_and_labels_can_change(qapp):
    combo = ValueComboBox(fallback="gone")
    combo.set_choices([(3, "3: old")])
    combo.setValue(3)
    combo.set_label(3, "3: renamed")
    assert combo.currentText() == "3: renamed"
    combo.set_choices([(4, "4: other")])
    assert combo.value() == 3 and combo.currentText() == "3: gone"
