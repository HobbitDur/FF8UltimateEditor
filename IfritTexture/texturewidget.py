from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QSpinBox, QGroupBox, QLabel, QHBoxLayout, QVBoxLayout, QComboBox

from IfritTexture.ifrittexturemanager import MetaData, TextureData


class TextureWidget(QGroupBox):
    DEPTH_POSSIBLE = [4, 8, 16]
    def __init__(self, texture_data:TextureData, title:str = ""):
        super().__init__()

        self._depth = QComboBox()
        self._depth.addItems([str(x) for x in self.DEPTH_POSSIBLE])
        depth_index = [i for i, x in enumerate(self.DEPTH_POSSIBLE) if x == texture_data.meta.depth]
        if depth_index:
            self._depth.setCurrentIndex(depth_index[0])
        else:
            print(f"Error: the depth {texture_data.meta.depth} is not expected")
        self._depth.activated.connect(self._depth_changed)
        self._depth_title = QLabel("Depth")
        self._depth_layout = QHBoxLayout()
        self._depth_layout.addStretch(1)
        self._depth_layout.addWidget(self._depth_title)
        self._depth_layout.addWidget(self._depth)

        self._imageX = QSpinBox()
        self._imageX.setMaximum(65535)
        self._imageX.setValue(texture_data.meta.imageX)
        self._imageX_title = QLabel("imageX")
        self._imageX_layout = QHBoxLayout()
        self._imageX_layout.addStretch(1)
        self._imageX_layout.addWidget(self._imageX_title)
        self._imageX_layout.addWidget(self._imageX)

        self._imageY = QSpinBox()
        self._imageY.setMaximum(65535)
        self._imageY.setValue(texture_data.meta.imageY)
        self._imageY_title = QLabel("imageY")
        self._imageY_layout = QHBoxLayout()
        self._imageY_layout.addStretch(1)
        self._imageY_layout.addWidget(self._imageY_title)
        self._imageY_layout.addWidget(self._imageY)

        self._paletteX = QSpinBox()
        self._paletteX.setMaximum(65535)
        self._paletteX.setValue(texture_data.meta.paletteX)
        self._paletteX_title = QLabel("paletteX")
        self._paletteX_layout = QHBoxLayout()
        self._paletteX_layout.addStretch(1)
        self._paletteX_layout.addWidget(self._paletteX_title)
        self._paletteX_layout.addWidget(self._paletteX)

        self._paletteY = QSpinBox()
        self._paletteY.setMaximum(65535)
        self._paletteY.setValue(texture_data.meta.paletteY)
        self._paletteY_title = QLabel("paletteY")
        self._paletteY_layout = QHBoxLayout()
        self._paletteY_layout.addStretch(1)
        self._paletteY_layout.addWidget(self._paletteY_title)
        self._paletteY_layout.addWidget(self._paletteY)


        self._texture_image = QPixmap(str(texture_data.texture_path))
        self._texture_image_widget = QLabel()
        self._texture_image_widget.setMaximumSize(256, 256)
        self._texture_image_widget.setPixmap(self._texture_image)

        self._palette_image = QPixmap(str(texture_data.palette_path))
        self._palette_image = self._palette_image.scaled(
            256, 10,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._palette_image_widget = QLabel()
        self._palette_image_widget.setPixmap(self._palette_image)

        self.setTitle(title)

        self._meta_column = QVBoxLayout()
        self._meta_column.addStretch(1)
        self._meta_column.addLayout(self._depth_layout)
        self._meta_column.addLayout(self._imageX_layout)
        self._meta_column.addLayout(self._imageY_layout)
        self._meta_column.addLayout(self._paletteX_layout)
        self._meta_column.addLayout(self._paletteY_layout)

        self._texture_palette_layout = QVBoxLayout()
        self._texture_palette_layout.addWidget(self._texture_image_widget)
        self._texture_palette_layout.addWidget(self._palette_image_widget)
        self._texture_palette_layout.addStretch(1)

        self._main_layout = QHBoxLayout()
        self._main_layout.addLayout(self._texture_palette_layout)
        self._main_layout.addLayout(self._meta_column)
        self._main_layout.addStretch(1)

        self.setLayout(self._main_layout)

    def _depth_changed(self):
        if self._depth.currentIndex() == 2:
            self._palette_image_widget.hide()
        else:
            self._palette_image_widget.show()

    def set_meta_data(self, meta_data:MetaData):
        self._depth.setValue(meta_data.depth)
        self._imageX.setValue(meta_data.imageX)
        self._imageY.setValue(meta_data.imageY)
        self._paletteX.setValue(meta_data.paletteX)
        self._paletteY.setValue(meta_data.paletteY)
