"""Combo/spin widgets that ignore mouse-wheel scrolling.

Hovering over a QComboBox / QSpinBox and turning the wheel normally changes the
value, which makes it very easy to corrupt data while just scrolling a form.
These subclasses ``ignore()`` the wheel event instead: the value never changes,
and the event propagates to the surrounding scroll area so the wheel scrolls the
form as expected. An open combo popup still scrolls normally (that view is a
separate widget). Values can still be changed by clicking, typing or arrow keys.
"""
from PyQt6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()
