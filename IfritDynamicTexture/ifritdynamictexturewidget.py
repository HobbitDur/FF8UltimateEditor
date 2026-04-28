from PyQt6.QtWidgets import QWidget, QVBoxLayout

from Ifrit.ifritmanager import IfritManager
from IfritDynamicTexture.dynamictexturesectionwidget import DynamicTextureSectionWidget


class IfritDynamicTextureWidget(QWidget):
    """Main widget for texture animation management"""

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager

        layout = QVBoxLayout(self)
        self.anim_section = DynamicTextureSectionWidget(ifrit_manager)
        layout.addWidget(self.anim_section)

    def load_file(self, file_path: str):
        self.anim_section.load_file(file_path)

    def save_file(self):
        self.anim_section.save_file()