from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget, QGroupBox, QHBoxLayout, QLabel, QScrollArea, QSpinBox, QGridLayout

from Ifrit.IfritDynamicTexture.framewidget import FrameWidget


class DynamicTextureEntryWidget(QGroupBox):
    """Widget for editing a single texture animation entry (anchor position <- cycling frames)"""

    dataChanged = pyqtSignal()

    def __init__(self, entry_index: int, parent=None):
        super().__init__(f"Animation Entry {entry_index}", parent)
        self.entry_index = entry_index
        self.frame_widgets = []

        layout = QVBoxLayout(self)

        # Anchor texture coordinates
        anchor_group = QGroupBox("Anchor position (fixed spot on the model, sampled by its polygons)")
        anchor_layout = QGridLayout(anchor_group)

        self.anchor_x = QSpinBox()
        self.anchor_x.setRange(0, 65535)
        self.anchor_x.setToolTip("Anchor X coordinate")
        self.anchor_y = QSpinBox()
        self.anchor_y.setRange(0, 65535)
        self.anchor_y.setToolTip("Anchor Y coordinate")
        self.anchor_width = QSpinBox()
        self.anchor_width.setRange(1, 65535)
        self.anchor_width.setValue(32)
        self.anchor_height = QSpinBox()
        self.anchor_height.setRange(1, 65535)
        self.anchor_height.setValue(32)

        for spin in [self.anchor_x, self.anchor_y, self.anchor_width, self.anchor_height]:
            spin.valueChanged.connect(self.dataChanged.emit)

        anchor_layout.addWidget(QLabel("X:"), 0, 0)
        anchor_layout.addWidget(self.anchor_x, 0, 1)
        anchor_layout.addWidget(QLabel("Y:"), 0, 2)
        anchor_layout.addWidget(self.anchor_y, 0, 3)
        anchor_layout.addWidget(QLabel("Width:"), 1, 0)
        anchor_layout.addWidget(self.anchor_width, 1, 1)
        anchor_layout.addWidget(QLabel("Height:"), 1, 2)
        anchor_layout.addWidget(self.anchor_height, 1, 3)

        layout.addWidget(anchor_group)

        # Frames section
        frames_group = QGroupBox("Animation frames (cycled into the anchor position over time)")
        frames_layout = QVBoxLayout(frames_group)

        # Header for frames
        frame_header = QHBoxLayout()
        frame_header.addWidget(QLabel("Frames:"))
        frame_header.addStretch()
        self.add_frame_btn = QPushButton("+ Add Frame")
        self.add_frame_btn.clicked.connect(self._add_frame)
        frame_header.addWidget(self.add_frame_btn)
        frames_layout.addLayout(frame_header)

        # Scroll area for frames
        self.frame_scroll = QScrollArea()
        self.frame_scroll.setWidgetResizable(True)
        self.frame_scroll.setMaximumHeight(200)

        self.frame_container = QWidget()
        self.frame_layout = QVBoxLayout(self.frame_container)
        self.frame_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.frame_scroll.setWidget(self.frame_container)
        frames_layout.addWidget(self.frame_scroll)

        layout.addWidget(frames_group)

        # Remove entry button
        self.remove_btn = QPushButton("Remove Entry")
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white;")
        layout.addWidget(self.remove_btn)

    def _add_frame(self):
        """Add a new frame widget"""
        frame_index = len(self.frame_widgets)
        frame_widget = FrameWidget(frame_index)
        frame_widget.dataChanged.connect(self.dataChanged.emit)
        frame_widget.removeRequested.connect(self._remove_frame)
        self.frame_widgets.append(frame_widget)
        self.frame_layout.addWidget(frame_widget)
        self.dataChanged.emit()

    def _remove_frame(self, frame_index: int):
        """Remove a frame widget"""
        if 0 <= frame_index < len(self.frame_widgets):
            widget = self.frame_widgets.pop(frame_index)
            widget.deleteLater()
            # Renumber remaining widgets
            for i, w in enumerate(self.frame_widgets):
                w.frame_index = i
                w.setTitle(f"Frame {i}")
            self.dataChanged.emit()

    def get_data(self) -> dict:
        frames = []
        for w in self.frame_widgets:
            frames.append(w.get_data())

        return {
            'anchor_x': self.anchor_x.value(),
            'anchor_y': self.anchor_y.value(),
            'anchor_width': self.anchor_width.value(),
            'anchor_height': self.anchor_height.value(),
            'frames': frames
        }

    def set_data(self, anchor_x: int, anchor_y: int, anchor_width: int, anchor_height: int, frames: list):
        self.anchor_x.setValue(anchor_x)
        self.anchor_y.setValue(anchor_y)
        self.anchor_width.setValue(anchor_width)
        self.anchor_height.setValue(anchor_height)

        # Clear existing frames
        for w in self.frame_widgets:
            w.deleteLater()
        self.frame_widgets.clear()

        # Add new frames
        for i, frame in enumerate(frames):
            frame_widget = FrameWidget(i)
            frame_widget.set_data(frame.get('x', 0), frame.get('y', 0))
            frame_widget.dataChanged.connect(self.dataChanged.emit)
            frame_widget.removeRequested.connect(self._remove_frame)
            self.frame_widgets.append(frame_widget)
            self.frame_layout.addWidget(frame_widget)
