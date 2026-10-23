from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSpinBox, QGroupBox, QPushButton, QLabel


def sprite_title(index: int) -> str:
    return "Sprite 0 (resting picture)" if index == 0 else f"Sprite {index}"


class FrameWidget(QGroupBox):
    """Widget for editing where one sprite of a dynamic-texture entry is stored in the texture
    (the picture the game copies onto the entry's destination)"""

    dataChanged = pyqtSignal()
    removeRequested = pyqtSignal(int)

    def __init__(self, frame_index: int, parent=None):
        super().__init__(sprite_title(frame_index), parent)
        self.frame_index = frame_index

        layout = QHBoxLayout(self)

        self.dst_x = QSpinBox()
        self.dst_x.setRange(0, 510)
        self.dst_x.setSingleStep(2)
        self.dst_x.setToolTip("Sprite X in the texture, in pixels (the file stores VRAM halfwords:\n"
                              "2 pixels, so X is always even)")
        self.dst_x.valueChanged.connect(self.dataChanged.emit)

        self.dst_y = QSpinBox()
        self.dst_y.setRange(0, 255)
        self.dst_y.setToolTip("Sprite Y in the texture, in pixels")
        self.dst_y.valueChanged.connect(self.dataChanged.emit)

        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setToolTip("Remove this sprite")
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white; font-weight: bold;")
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self.frame_index))

        layout.addWidget(QLabel("X:"))
        layout.addWidget(self.dst_x)
        layout.addWidget(QLabel("Y:"))
        layout.addWidget(self.dst_y)
        layout.addWidget(self.remove_btn)

    def set_index(self, index: int):
        self.frame_index = index
        self.setTitle(sprite_title(index))

    def get_data(self) -> dict:
        return {
            'x': self.dst_x.value(),
            'y': self.dst_y.value()
        }

    def set_data(self, x: int, y: int):
        self.dst_x.setValue(x)
        self.dst_y.setValue(y)
