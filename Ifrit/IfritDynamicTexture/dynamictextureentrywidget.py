from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget, QGroupBox, QHBoxLayout, QLabel, QScrollArea, QSpinBox, QGridLayout

from Ifrit.IfritDynamicTexture.framewidget import FrameWidget


class DynamicTextureEntryWidget(QGroupBox):
    """Widget for editing one dynamic-texture entry: the destination rectangle the model's polygons
    sample, and the sprites the game copies onto it (sprite 0 at rest, the others in turn)"""

    dataChanged = pyqtSignal()

    def __init__(self, entry_index: int, parent=None):
        super().__init__(f"Entry {entry_index}", parent)
        self.entry_index = entry_index
        self.frame_widgets = []

        layout = QVBoxLayout(self)

        # Destination: the spot on the model
        destination_group = QGroupBox("Destination (the spot on the model: its polygons sample it)")
        destination_group.setToolTip(
            "The game never moves the UVs: it copies one sprite at a time ONTO this rectangle in\n"
            "video memory (a VRAM-to-VRAM copy), so every polygon sampling it shows that sprite.\n"
            "Squall: the right painted eye, which both eyes of the mesh use.")
        destination_layout = QGridLayout(destination_group)

        self.anchor_x = QSpinBox()
        self.anchor_x.setRange(0, 510)
        self.anchor_x.setSingleStep(2)
        self.anchor_x.setToolTip("Destination X in the texture, in pixels (VRAM halfwords in the file:\n"
                                 "always even)")
        self.anchor_y = QSpinBox()
        self.anchor_y.setRange(0, 255)
        self.anchor_y.setToolTip("Destination Y in the texture, in pixels")
        self.anchor_width = QSpinBox()
        self.anchor_width.setRange(2, 510)
        self.anchor_width.setSingleStep(2)
        self.anchor_width.setValue(32)
        self.anchor_width.setToolTip("Width of the destination and of every sprite, in pixels (even)")
        self.anchor_height = QSpinBox()
        self.anchor_height.setRange(1, 255)
        self.anchor_height.setValue(32)
        self.anchor_height.setToolTip("Height of the destination and of every sprite, in pixels")

        for spin in [self.anchor_x, self.anchor_y, self.anchor_width, self.anchor_height]:
            spin.valueChanged.connect(self.dataChanged.emit)

        destination_layout.addWidget(QLabel("X:"), 0, 0)
        destination_layout.addWidget(self.anchor_x, 0, 1)
        destination_layout.addWidget(QLabel("Y:"), 0, 2)
        destination_layout.addWidget(self.anchor_y, 0, 3)
        destination_layout.addWidget(QLabel("Width:"), 1, 0)
        destination_layout.addWidget(self.anchor_width, 1, 1)
        destination_layout.addWidget(QLabel("Height:"), 1, 2)
        destination_layout.addWidget(self.anchor_height, 1, 3)

        self.anim_speed = QSpinBox()
        self.anim_speed.setRange(0, 255)
        self.anim_speed.setToolTip(
            "Animation speed, for the sequences' opcode 80 (step the animation):\n"
            "8 = one sprite per tick; any other value steps by value/8 of a sprite per tick;\n"
            "0 = the destination is scrolled instead of swapping sprites.\n"
            "The eye blink does not use it: the idle timer (every 15-59 ticks) and the opcodes\n"
            "BD / 9B / 9F / BE copy a given sprite.")
        self.anim_speed.valueChanged.connect(self.dataChanged.emit)
        destination_layout.addWidget(QLabel("Speed:"), 2, 0)
        destination_layout.addWidget(self.anim_speed, 2, 1)

        layout.addWidget(destination_group)

        # Sprites
        frames_group = QGroupBox("Sprites (each one is copied onto the destination)")
        frames_layout = QVBoxLayout(frames_group)

        frame_header = QHBoxLayout()
        frame_header.addWidget(QLabel("Sprite 0 is the resting picture (the open eye), "
                                      "sprite 1 the next (the closed eye)..."))
        frame_header.addStretch()
        self.add_frame_btn = QPushButton("+ Add Sprite")
        self.add_frame_btn.clicked.connect(self._add_frame)
        frame_header.addWidget(self.add_frame_btn)
        frames_layout.addLayout(frame_header)

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

    def _new_frame_widget(self, index: int) -> FrameWidget:
        frame_widget = FrameWidget(index)
        frame_widget.dataChanged.connect(self.dataChanged.emit)
        frame_widget.removeRequested.connect(self._remove_frame)
        self.frame_widgets.append(frame_widget)
        self.frame_layout.addWidget(frame_widget)
        return frame_widget

    def _add_frame(self):
        """Add a sprite, where the last one is"""
        frame_widget = self._new_frame_widget(len(self.frame_widgets))
        if len(self.frame_widgets) > 1:
            previous = self.frame_widgets[-2].get_data()
            frame_widget.set_data(previous['x'], previous['y'])
        self._update_remove_buttons()
        self.dataChanged.emit()

    def _remove_frame(self, frame_index: int):
        """Remove a sprite (an entry keeps at least sprite 0)"""
        if 0 <= frame_index < len(self.frame_widgets) and len(self.frame_widgets) > 1:
            widget = self.frame_widgets.pop(frame_index)
            widget.deleteLater()
            for i, w in enumerate(self.frame_widgets):
                w.set_index(i)
            self._update_remove_buttons()
            self.dataChanged.emit()

    def _update_remove_buttons(self):
        for w in self.frame_widgets:
            w.remove_btn.setEnabled(len(self.frame_widgets) > 1)

    def get_data(self) -> dict:
        return {
            'destination_x': self.anchor_x.value(),
            'destination_y': self.anchor_y.value(),
            'width': self.anchor_width.value(),
            'height': self.anchor_height.value(),
            'anim_speed': self.anim_speed.value(),
            'sprites': [w.get_data() for w in self.frame_widgets],
        }

    def set_data(self, destination_x: int, destination_y: int, width: int, height: int, sprites: list,
                 anim_speed: int = 0):
        for spin, value in ((self.anchor_x, destination_x), (self.anchor_y, destination_y),
                            (self.anchor_width, width), (self.anchor_height, height),
                            (self.anim_speed, anim_speed)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

        for w in self.frame_widgets:
            w.deleteLater()
        self.frame_widgets.clear()
        for i, sprite in enumerate(sprites):
            frame_widget = self._new_frame_widget(i)
            frame_widget.dst_x.blockSignals(True)
            frame_widget.dst_y.blockSignals(True)
            frame_widget.set_data(sprite.get('x', 0), sprite.get('y', 0))
            frame_widget.dst_x.blockSignals(False)
            frame_widget.dst_y.blockSignals(False)
        self._update_remove_buttons()
