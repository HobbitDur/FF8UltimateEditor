import os
import pathlib
from typing import List
from PyQt6.QtWidgets import (QSpinBox, QGroupBox, QLabel, QHBoxLayout,
                             QVBoxLayout, QComboBox, QPushButton, QWidget)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor

from IfritTexture.editabletexturewidget import EditableTextureWidget
from IfritTexture.ifrittexturemanager import TextureData


class TextureWidget(QGroupBox):
    # Signal emitted when the plus button is clicked
    request_new_texture = pyqtSignal()

    DEPTH_POSSIBLE = [4, 8, 16]

    def __init__(self, texture_data: TextureData, icon_path="Resources", title: str = "", plus_type=False):
        super().__init__()
        self.icon_path = icon_path
        self.texture_data = texture_data
        self._title = title

        # Set up the main layout
        self._main_layout = QHBoxLayout()
        self.setLayout(self._main_layout)
        self._plus_type = plus_type

        if plus_type:
            self._init_plus_ui()
        else:
            self._init_full_ui()

    def set_title(self, title):
        self._title = title
        self.setTitle(title)

    def set_plus_type(self, plus=True):
        if plus:
            self._init_plus_ui()
            self._plus_type = True
        else:
            self._plus_button.hide()
            self._init_full_ui()
            self._plus_type = False

    def get_plus_type(self):
        return self._plus_type

    def _init_plus_ui(self):
        """UI for the 'Add New' placeholder state."""
        self.setTitle(self._title or "Add New")
        self.setFixedSize(350, 250)  # Maintain consistent size in the grid

        # Big + Button
        self._plus_button = QPushButton("+")
        self._plus_button.setFixedSize(80, 80)
        self._plus_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_button.setStyleSheet("""
            QPushButton {
                font-size: 40px;
                font-weight: 900;
                color: #000000;              /* Black '+' symbol */
                background-color: #f0f0f0;   /* Light grey background so black is visible */
                border: 3px solid #ffffff;   /* Thick White Border */
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #ffffff;   /* Brighten on hover */
                border: 3px solid #000000;   /* Swap to black border on hover */
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        self._plus_button.clicked.connect(self.request_new_texture.emit)
        self._plus_button.clicked.connect(lambda: self.set_plus_type(False))

        self._main_layout.addStretch(1)
        self._main_layout.addWidget(self._plus_button)
        self._main_layout.addStretch(1)


    def _init_full_ui(self):
        """The standard UI for existing or newly created textures."""
        self.setTitle(self._title)

        # --- LEFT COLUMN: Images ---
        self._texture_palette_layout = QVBoxLayout()

        self._texture_image_widget = EditableTextureWidget(self.texture_data.texture_image, max_size=256, icon_path=self.icon_path)
        self._palette_image_widget = EditableTextureWidget(self.texture_data.palette_image, max_size=256, icon_path=self.icon_path, type=1)

        self._texture_palette_layout.addWidget(self._texture_image_widget)
        self._texture_palette_layout.addWidget(self._palette_image_widget)
        self._texture_palette_layout.addStretch(1)

        # --- RIGHT COLUMN: Meta Data ---
        self._meta_column = QVBoxLayout()

        # Depth
        self._depth = QComboBox()
        self._depth.addItems([str(x) for x in self.DEPTH_POSSIBLE])
        depth_val = self.texture_data.meta.depth if self.texture_data.meta else 8
        try:
            idx = self.DEPTH_POSSIBLE.index(depth_val)
            self._depth.setCurrentIndex(idx)
        except ValueError:
            print(f"Error: depth {depth_val} unexpected")
        self._depth.activated.connect(self._depth_changed)

        # Spinboxes
        self._imageX = self._create_spin_row("imageX", self.texture_data.meta.imageX if self.texture_data.meta else 0)
        self._imageY = self._create_spin_row("imageY", self.texture_data.meta.imageY if self.texture_data.meta else 0)
        self._paletteX = self._create_spin_row("paletteX", self.texture_data.meta.paletteX if self.texture_data.meta else 0)
        self._paletteY = self._create_spin_row("paletteY", self.texture_data.meta.paletteY if self.texture_data.meta else 0)

        # Assemble Right Column
        self._add_to_meta_layout("Depth", self._depth)
        self._meta_column.addLayout(self._imageX_layout)
        self._meta_column.addLayout(self._imageY_layout)
        self._meta_column.addLayout(self._paletteX_layout)
        self._meta_column.addLayout(self._paletteY_layout)
        self._meta_column.addStretch(1)

        # Assemble Main
        self._main_layout.addLayout(self._texture_palette_layout)
        self._main_layout.addLayout(self._meta_column)
        self._main_layout.addStretch(1)

    def _create_spin_row(self, label_text, value):
        """Helper to create labeled spinbox rows."""
        layout = QHBoxLayout()
        layout.addStretch(1)
        label = QLabel(label_text)
        spin = QSpinBox()
        spin.setMaximum(65535)
        spin.setValue(value)
        layout.addWidget(label)
        layout.addWidget(spin)
        # Store layout on self so we can add it later
        setattr(self, f"_{label_text}_layout", layout)
        return spin

    def _add_to_meta_layout(self, label_text, widget):
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(QLabel(label_text))
        row.addWidget(widget)
        self._meta_column.addLayout(row)



    def _depth_changed(self):
        # 16-bit depth usually means no palette needed in many FF8 formats
        if self.get_depth() == 16:
            self._palette_image_widget.hide()
        else:
            self._palette_image_widget.show()

    # --- Getters ---
    def get_depth(self):
        return int(self._depth.currentText())

    def get_imageX(self):
        return self._imageX.value()

    def get_imageY(self):
        return self._imageY.value()

    def get_paletteX(self):
        return self._paletteX.value()

    def get_paletteY(self):
        return self._paletteY.value()

    def get_texture_img(self):
        return self._texture_image_widget.get_image()

    def get_palette_img(self):
        return self._palette_image_widget.get_image()