"""Arrow-toggle section shared by editor panels."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSizePolicy


class CollapsibleSection(QWidget):
    """A titled section that folds away by clicking an arrow (▼ open / ▶ collapsed).

    Used for both the sets and the animation slots, matching the fold-to-focus feel of the
    Sequence tab but with an arrow toggle instead of a checkbox. Extra header widgets (e.g. a
    Preview button) sit next to the arrow; content goes in content_layout(), slightly indented.
    remember() keeps the folded state across sessions in the app's QSettings.
    """

    toggled = pyqtSignal(bool)  # the user folded (False) or unfolded (True) the section

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

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def remember(self, settings, key):
        """Restore the folded state saved under key, and save it whenever the user toggles it.
        settings is the app's QSettings (FileRegistry.settings); None (a tool used alone) keeps
        the state for this session only."""
        if settings is None:
            return
        if settings.contains(key):
            self.set_expanded(settings.value(key, True, type=bool))
        self.toggled.connect(lambda expanded: settings.setValue(key, expanded))

    def __on_toggle(self):
        self.set_expanded(self._toggle.isChecked())
        self.toggled.emit(self._toggle.isChecked())
