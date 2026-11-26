"""A combo box picking a number from named choices, with the QSpinBox API a form already uses.

A field stored as a raw number (an id, an index) often has a known set of meanings: offering them
by name beats typing the number. ValueComboBox keeps value() / setValue() / valueChanged(int), so
it replaces a spin box without touching the code that reads and fills the form. A value that is
none of the choices (a modded file, a choice list not loaded yet) is still shown and kept, as
"N: <fallback>", instead of being lost.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox

from SmallWidget.fitwidth import fit_combo, fit_combo_popup


class ValueComboBox(QComboBox):
    valueChanged = pyqtSignal(int)

    def __init__(self, fallback="not in the list", parent=None, min_chars=16):
        QComboBox.__init__(self, parent)
        fit_combo(self, min_chars)  # the names readable closed, and in full in the drop-down
        self._fallback = fallback
        self._choices = []          # [(value, label)]
        self._value = 0
        self.currentIndexChanged.connect(self._index_changed)

    def wheelEvent(self, event):
        event.ignore()  # Scrolling the form must not change the value (see SmallWidget/nowheel.py)

    def set_choices(self, choices, fallback=None):
        """Replace the choices, [(value, label)], keeping the current value (shown with the fallback
        label if it is not one of them). Emits nothing."""
        if fallback is not None:
            self._fallback = fallback
        self._choices = [(int(value), label) for value, label in choices]
        self._rebuild()

    def set_label(self, value, label):
        """Rename one choice (e.g. a text line edited), without rebuilding the list."""
        for position, (choice, _old) in enumerate(self._choices):
            if choice == value:
                self._choices[position] = (choice, label)
                index = self.findData(value)
                if index >= 0:
                    self.setItemText(index, label)
                    fit_combo_popup(self)
                return

    def value(self):
        return self._value

    def setValue(self, value):
        value = int(value)
        changed = value != self._value
        self._value = value
        if self.findData(value) < 0 or self._has_fallback_item():
            self._rebuild()
        else:
            was_blocked = self.blockSignals(True)
            self.setCurrentIndex(self.findData(value))
            self.blockSignals(was_blocked)
        if changed and not self.signalsBlocked():
            self.valueChanged.emit(value)

    def _has_fallback_item(self):
        return any(self.itemData(index) not in {value for value, _label in self._choices}
                   for index in range(self.count()))

    def _rebuild(self):
        was_blocked = self.blockSignals(True)
        self.clear()
        for value, label in self._choices:
            self.addItem(label, value)
        if self.findData(self._value) < 0:
            self.addItem(f"{self._value}: {self._fallback}", self._value)
        self.setCurrentIndex(self.findData(self._value))
        self.blockSignals(was_blocked)
        fit_combo_popup(self)

    def _index_changed(self, index):
        if index < 0:
            return
        value = self.itemData(index)
        if value is None or value == self._value:
            return
        self._value = int(value)
        if self._has_fallback_item():
            self._rebuild()  # the fallback entry of the old value goes
        self.valueChanged.emit(self._value)
