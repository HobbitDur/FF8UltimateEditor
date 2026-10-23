from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QWidget


class WheelGuard(QObject):
    """App-level event filter: the mouse wheel never changes a combo box or a spin box (values were
    changed by mistake while scrolling a form); it scrolls the list/table/scroll area holding them
    instead. An open combo popup is its own window, so its list still scrolls."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            value_widget = self.value_widget(obj)
            if value_widget is not None:
                scroll_area = self._scroll_area_holding(value_widget)
                if scroll_area is not None:
                    QApplication.sendEvent(scroll_area.viewport(), event)
                return True
        return False

    @staticmethod
    def value_widget(obj):
        """The combo box or spin box a wheel event over `obj` would change (obj itself or the widget
        it is part of, like a spin box's line edit), or None. The search stops at the window."""
        widget = obj if isinstance(obj, QWidget) else None
        while widget is not None:
            if isinstance(widget, (QComboBox, QAbstractSpinBox)):
                return widget
            if widget.isWindow():
                return None
            widget = widget.parentWidget()
        return None

    @staticmethod
    def _scroll_area_holding(widget):
        widget = widget.parentWidget()
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                return widget
            if widget.isWindow():
                return None
            widget = widget.parentWidget()
        return None
