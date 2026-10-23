"""The editor's app-level WheelGuard keeps the mouse wheel from changing combo boxes and spin
boxes (values were changed by mistake while scrolling a form): the wheel scrolls what holds them,
and an open combo popup (its own window) still scrolls its list."""
import sys

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from Common.wheelguard import WheelGuard


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _wheel_down(widget):
    event = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_wheel_scrolls_the_form_not_the_values(qapp):
    event_filter = WheelGuard()
    qapp.installEventFilter(event_filter)
    try:
        area = QScrollArea()
        content = QWidget()
        layout = QVBoxLayout(content)
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(50)
        combo = QComboBox()
        combo.addItems([str(i) for i in range(10)])
        combo.setCurrentIndex(5)
        layout.addWidget(spin)
        layout.addWidget(combo)
        layout.addSpacing(3000)
        area.setWidget(content)
        area.resize(200, 200)
        area.show()
        qapp.processEvents()

        _wheel_down(spin.lineEdit())   # the part of a spin box under the mouse
        _wheel_down(combo)
        qapp.processEvents()
        assert spin.value() == 50
        assert combo.currentIndex() == 5
        assert area.verticalScrollBar().value() > 0, "the wheel should scroll the form instead"

        assert WheelGuard.value_widget(combo.view()) is None, \
            "an open combo popup is its own window: its list must keep scrolling"
        area.close()
    finally:
        qapp.removeEventFilter(event_filter)
