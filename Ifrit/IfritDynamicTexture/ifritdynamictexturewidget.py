from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritDynamicTexture.dynamictexturesectionwidget import DynamicTextureSectionWidget


class IfritDynamicTextureWidget(QWidget):
    """Main widget for texture animation management"""

    data_edited = pyqtSignal()   # forwarded from the inner section widget (a real dyntex data edit)

    def __init__(self, ifrit_manager: IfritManager, parent=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager

        layout = QVBoxLayout(self)
        self.dynamic_texture_widget = DynamicTextureSectionWidget(ifrit_manager)
        self.dynamic_texture_widget.data_edited.connect(self.data_edited)
        layout.addWidget(self.dynamic_texture_widget)

    def load_file(self, file_path: str):
        self.dynamic_texture_widget.load_file(file_path)

    def save_file(self):
        self.dynamic_texture_widget.save_file()