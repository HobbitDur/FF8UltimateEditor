from PyQt6.QtWidgets import QWidget, QVBoxLayout

from Ifrit.ifritmanager import IfritManager
from IfritDynamicTexture.dynamictexturesectionwidget import DynamicTextureSectionWidget


class IfritDynamicTextureWidget(QWidget):
    """Main widget for texture animation management"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager

        layout = QVBoxLayout(self)
        self.dynamic_texture_widget = DynamicTextureSectionWidget(ifrit_manager)
        layout.addWidget(self.dynamic_texture_widget)

    def load_file(self, file_path: str):
        self.dynamic_texture_widget.load_file(file_path)

    def save_file(self):
        self.dynamic_texture_widget.save_file()