from typing import Callable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QCheckBox


class ExternalToolWidget(QWidget):
    def __init__(self, icon_path: str, func_callback: Callable, tooltip_text: str = ""):
        QWidget.__init__(self)
        self.update_selected = False

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self._check_update = QCheckBox()
        self._check_update.stateChanged.connect(self._on_checkbox_changed)
        self._check_update.setToolTip("Select if you want to update this program when updating all tools")

        self._tool_button = QPushButton()
        self._tool_button.setIcon(QIcon(icon_path))
        self._tool_button.setIconSize(QSize(30, 30))
        self._tool_button.setFixedSize(40, 40)
        self._tool_button.clicked.connect(func_callback)
        if tooltip_text:
            self._tool_button.setToolTip(tooltip_text)

        self.main_layout.addWidget(self._check_update, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self._tool_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_checkbox_changed(self):
        if self._check_update.checkState() == Qt.CheckState.Checked:
            self.update_selected = True
        elif self._check_update.checkState() == Qt.CheckState.Unchecked:
            self.update_selected = False
