from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
                             QScrollArea, QGridLayout, QSizePolicy, QFileDialog)

from IfritTexture.ifrittexturemanager import IfritTextureManager
from IfritTexture.texturewidget import TextureWidget


class IfritTextureWidget(QWidget):
    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.ifrit_manager = IfritTextureManager()

        # 1. Main Root Layout
        self.main_layout = QVBoxLayout(self)

        # 2. Top Button Bar
        self._button_layout = QHBoxLayout()
        self._analyse_button = QPushButton("Analyse")
        self._analyse_button.clicked.connect(self._analyze)
        self._button_layout.addWidget(self._analyse_button)
        self.main_layout.addLayout(self._button_layout)

        # 3. Scroll Area Setup
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # 4. The "Container" for the Grid
        self.scroll_content = QWidget()
        # Ensure it only takes as much vertical space as it needs
        #self.scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._texture_layout = QGridLayout(self.scroll_content)
        self._texture_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._texture_layout.setSpacing(10)

        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll)

        self._texture_widget = []

    def sizeHint(self):
        """Provide a proper size hint based on content"""
        # Get button bar height
        button_height = self._button_layout.sizeHint().height()

        # Get content height (if any widgets exist)
        if self._texture_widget:
            content_height = self.scroll_content.sizeHint().height()
        else:
            content_height = 100  # Minimum height when empty

        # Add margins
        margins = self.layout().contentsMargins()
        total_height = (button_height + content_height +
                        margins.top() + margins.bottom() +
                        self.layout().spacing() + 20)

        return QSize(400, total_height)  # Width can be whatever default you want

    def _analyze(self):
        file_to_load = "c0m001.dat"
        self.ifrit_manager.analyze(file_to_load)

        # Clear existing widgets
        while self._texture_widget:
            widget = self._texture_widget.pop()
            widget.setParent(None)
            widget.deleteLater()

        # Build the 2-column grid
        for index, texture in enumerate(self.ifrit_manager.texture_data):
            new_widget = TextureWidget(texture, title=f"Texture {index}")
            new_widget.setMinimumWidth(300)
            self._texture_widget.append(new_widget)
            self._texture_layout.addWidget(new_widget, index // 2, index % 2)

        # Create the "Infinite Stretch" at the very bottom
        last_row = (len(self.ifrit_manager.texture_data) // 2) + 1
        for r in range(self._texture_layout.rowCount()):
            self._texture_layout.setRowStretch(r, 0)
        self._texture_layout.setRowStretch(last_row, 1)

        self.window().adjustSize()
