"""Arrow-toggle section shared by editor panels."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSizePolicy


class CollapsibleSection(QWidget):
    """A titled section that folds away by clicking an arrow (▼ open / ▶ collapsed).

    Used for both the sets and the animation slots, matching the fold-to-focus feel of the
    Sequence tab but with an arrow toggle instead of a checkbox. Extra header widgets (e.g. a
    Preview button) sit next to the arrow; content goes in content_layout(), slightly indented.
    """

    def __init__(self, title: str, parent=None, expanded: bool = True, tooltip: str = ""):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._toggle = QToolButton()
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setText(title)
        if tooltip:
            self._toggle.setToolTip(tooltip)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle.clicked.connect(self.__on_toggle)

        self._header = QHBoxLayout()
        self._header.setContentsMargins(0, 0, 0, 0)
        self._header.addWidget(self._toggle)
        self._header.addStretch(1)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 0, 0, 0)  # indent under the arrow
        self._content.setVisible(expanded)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addLayout(self._header)
        outer.addWidget(self._content)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_header_widget(self, widget):
        self._header.insertWidget(self._header.count() - 1, widget)  # before the stretch

    def set_expanded(self, expanded: bool):
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded
                                  else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)

    def __on_toggle(self):
        self.set_expanded(self._toggle.isChecked())
