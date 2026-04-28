from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget, QGroupBox, QHBoxLayout, QLabel, QScrollArea, QSpinBox, QGridLayout

from IfritDynamicTexture.destinationwidget import DestinationWidget


class DynamicTextureEntryWidget(QGroupBox):
    """Widget for editing a single texture animation entry (source -> multiple targets)"""

    dataChanged = pyqtSignal()

    def __init__(self, entry_index: int, parent=None):
        super().__init__(f"Animation Entry {entry_index}", parent)
        self.entry_index = entry_index
        self.destination_widgets = []

        layout = QVBoxLayout(self)

        # Source texture coordinates
        source_group = QGroupBox("Source Sub-texture (will be copied)")
        source_layout = QGridLayout(source_group)

        self.src_x = QSpinBox()
        self.src_x.setRange(0, 65535)
        self.src_x.setToolTip("Source X coordinate")
        self.src_y = QSpinBox()
        self.src_y.setRange(0, 65535)
        self.src_y.setToolTip("Source Y coordinate")
        self.src_width = QSpinBox()
        self.src_width.setRange(1, 65535)
        self.src_width.setValue(32)
        self.src_height = QSpinBox()
        self.src_height.setRange(1, 65535)
        self.src_height.setValue(32)

        for spin in [self.src_x, self.src_y, self.src_width, self.src_height]:
            spin.valueChanged.connect(self.dataChanged.emit)

        source_layout.addWidget(QLabel("X:"), 0, 0)
        source_layout.addWidget(self.src_x, 0, 1)
        source_layout.addWidget(QLabel("Y:"), 0, 2)
        source_layout.addWidget(self.src_y, 0, 3)
        source_layout.addWidget(QLabel("Width:"), 1, 0)
        source_layout.addWidget(self.src_width, 1, 1)
        source_layout.addWidget(QLabel("Height:"), 1, 2)
        source_layout.addWidget(self.src_height, 1, 3)

        layout.addWidget(source_group)

        # Destinations section
        destinations_group = QGroupBox("Destination Sub-textures (where it will be copied)")
        destinations_layout = QVBoxLayout(destinations_group)

        # Header for destinations
        dest_header = QHBoxLayout()
        dest_header.addWidget(QLabel("Destinations:"))
        dest_header.addStretch()
        self.add_dest_btn = QPushButton("+ Add Destination")
        self.add_dest_btn.clicked.connect(self._add_destination)
        dest_header.addWidget(self.add_dest_btn)
        destinations_layout.addLayout(dest_header)

        # Scroll area for destinations
        self.dest_scroll = QScrollArea()
        self.dest_scroll.setWidgetResizable(True)
        self.dest_scroll.setMaximumHeight(200)

        self.dest_container = QWidget()
        self.dest_layout = QVBoxLayout(self.dest_container)
        self.dest_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.dest_scroll.setWidget(self.dest_container)
        destinations_layout.addWidget(self.dest_scroll)

        layout.addWidget(destinations_group)

        # Remove entry button
        self.remove_btn = QPushButton("Remove Entry")
        self.remove_btn.setStyleSheet("background-color: #8B0000; color: white;")
        layout.addWidget(self.remove_btn)

    def _add_destination(self):
        """Add a new destination widget"""
        dest_index = len(self.destination_widgets)
        dest_widget = DestinationWidget(dest_index)
        dest_widget.dataChanged.connect(self.dataChanged.emit)
        dest_widget.removeRequested.connect(self._remove_destination)
        self.destination_widgets.append(dest_widget)
        self.dest_layout.addWidget(dest_widget)
        self.dataChanged.emit()

    def _remove_destination(self, dest_index: int):
        """Remove a destination widget"""
        if 0 <= dest_index < len(self.destination_widgets):
            widget = self.destination_widgets.pop(dest_index)
            widget.deleteLater()
            # Renumber remaining widgets
            for i, w in enumerate(self.destination_widgets):
                w.dest_index = i
                w.setTitle(f"Destination {i}")
            self.dataChanged.emit()

    def get_data(self) -> dict:
        destinations = []
        for w in self.destination_widgets:
            destinations.append(w.get_data())

        return {
            'src_x': self.src_x.value(),
            'src_y': self.src_y.value(),
            'src_width': self.src_width.value(),
            'src_height': self.src_height.value(),
            'destinations': destinations
        }

    def set_data(self, src_x: int, src_y: int, src_width: int, src_height: int, destinations: list):
        self.src_x.setValue(src_x)
        self.src_y.setValue(src_y)
        self.src_width.setValue(src_width)
        self.src_height.setValue(src_height)

        # Clear existing destinations
        for w in self.destination_widgets:
            w.deleteLater()
        self.destination_widgets.clear()

        # Add new destinations
        for i, dest in enumerate(destinations):
            dest_widget = DestinationWidget(i)
            dest_widget.set_data(dest.get('x', 0), dest.get('y', 0))
            dest_widget.dataChanged.connect(self.dataChanged.emit)
            dest_widget.removeRequested.connect(self._remove_destination)
            self.destination_widgets.append(dest_widget)
            self.dest_layout.addWidget(dest_widget)

