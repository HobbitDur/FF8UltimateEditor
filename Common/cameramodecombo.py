"""A drop-down for a camera keyframe's coordinate mode (FF8GameData.dat.cameramodes) instead of a
bare number. Each entry names the reference frame; its tooltip says what the mode does."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox

from FF8GameData.dat.cameramodes import mode_choices, mode_help, mode_name


class CameraModeCombo(QComboBox):
    """Lists the useful modes; a value outside the list (a file's odd byte) is added so it shows
    as it is. valueChanged(int) like a spin box."""

    valueChanged = pyqtSignal(int)

    def __init__(self, value: int, base_tooltip: str = "", parent=None):
        super().__init__(parent)
        self._base_tooltip = base_tooltip
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        values = []
        for choice, label in mode_choices():
            self.addItem(label, choice)
            values.append(choice)
        if value not in values:
            self.insertItem(0, mode_name(value), value)
        for index in range(self.count()):
            self.setItemData(index, mode_help(self.itemData(index)), Qt.ItemDataRole.ToolTipRole)
        self.setCurrentIndex(self.findData(value))
        self._show_help()
        self.currentIndexChanged.connect(self._on_index)

    def value(self) -> int:
        return self.currentData()

    def setValue(self, value: int):
        index = self.findData(value)
        if index < 0:
            self.insertItem(0, mode_name(value), value)
            self.setItemData(0, mode_help(value), Qt.ItemDataRole.ToolTipRole)
            index = 0
        self.setCurrentIndex(index)

    def _show_help(self):
        help_text = mode_help(self.currentData())
        self.setToolTip(f"{self._base_tooltip}\n\n{help_text}" if self._base_tooltip else help_text)

    def _on_index(self, _index):
        self._show_help()
        self.valueChanged.emit(self.currentData())
