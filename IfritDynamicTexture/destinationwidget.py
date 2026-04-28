from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSpinBox, QGroupBox, QPushButton, QLabel


class DestinationWidget(QGroupBox):
    """Widget for editing a single destination UV"""

    dataChanged = pyqtSignal()
    removeRequested = pyqtSignal(int)

    def __init__(self, dest_index: int, parent=None):
        super().__init__(f"Destination {dest_index}", parent)
        self.dest_index = dest_index

        layout = QHBoxLayout(self)

        self.dst_x = QSpinBox()
        self.dst_x.setRange(0, 65535)
        self.dst_x.setToolTip("Destination X coordinate")
        self.dst_x.valueChanged.connect(self.dataChanged.emit)

        self.dst_y = QSpinBox()
        self.dst_y.setRange(0, 65535)
        self.dst_y.setToolTip("Destination Y coordinate")
        self.dst_y.valueChanged.connect(self.dataChanged.emit)

        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white; font-weight: bold;")
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self.dest_index))

        layout.addWidget(QLabel("X:"))
        layout.addWidget(self.dst_x)
        layout.addWidget(QLabel("Y:"))
        layout.addWidget(self.dst_y)
        layout.addWidget(self.remove_btn)

    def get_data(self) -> dict:
        return {
            'x': self.dst_x.value(),
            'y': self.dst_y.value()
        }

    def set_data(self, x: int, y: int):
        self.dst_x.setValue(x)
        self.dst_y.setValue(y)