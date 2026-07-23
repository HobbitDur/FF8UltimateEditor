"""The interpolation-curve chooser, shared by every feature that inserts in-between frames.

Both the fps conversion and the manual "interpolate between two frames" ask for it, and both used
to blend linearly with no way to say otherwise. They offer the same curves (see
FF8GameData/dat/interpolation.py) but not the same default: raising the frame rate of a continuous
motion wants a curve that flows through the original poses, while morphing between two poses the
user picked themselves usually wants to ease in and out of them.

Two shapes of the same thing:
  * InterpolationSelector, a labelled combo to drop into a dialog that asks other things too;
  * ask_interpolation_mode(), a standalone popup for a flow that has nothing else to ask.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget)

from FF8GameData.dat import interpolation


class InterpolationSelector(QWidget):
    """A combo of every interpolation curve, with the description of the selected one below it."""

    def __init__(self, parent=None, default_mode: str = interpolation.LINEAR,
                 label: str = "Interpolation between the frames:"):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(label))
        self._combo = QComboBox()
        for mode in interpolation.ALL_MODES:
            self._combo.addItem(interpolation.MODE_LABEL[mode], mode)
            self._combo.setItemData(self._combo.count() - 1,
                                    interpolation.MODE_DESCRIPTION[mode], role=3)  # tooltip
        self._combo.currentIndexChanged.connect(self._refresh_description)
        layout.addWidget(self._combo)

        # The descriptions are what makes the choice meaningful, so one is always on screen
        # rather than hidden in a tooltip the user has to go looking for.
        self._description = QLabel()
        self._description.setWordWrap(True)
        self._description.setStyleSheet("color:#999; font-size:10px;")
        layout.addWidget(self._description)

        self.set_mode(default_mode)

    def get_mode(self) -> str:
        return self._combo.currentData()

    def set_mode(self, mode: str):
        index = self._combo.findData(mode)
        self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._refresh_description()

    def _refresh_description(self):
        self._description.setText(interpolation.MODE_DESCRIPTION.get(self.get_mode(), ""))


def ask_interpolation_mode(parent, title: str, default_mode: str = interpolation.LINEAR,
                           intro: str = ""):
    """Popup asking only for the curve. Returns the chosen mode, or None if the user cancels."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    if intro:
        intro_label = QLabel(intro)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

    selector = InterpolationSelector(dialog, default_mode)
    layout.addWidget(selector)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return selector.get_mode()
