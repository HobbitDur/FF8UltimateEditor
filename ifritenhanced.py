import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from IfritAI.ifritaiwidget import IfritAIWidget
from IfritXlsx.ifritxlsxwidget import IfritXlsxWidget

from ifritguilauncher import IfritGuiLauncher


class IfritEnhancedWidget(QWidget):

    def __init__(self, icon_path='Resources'):
        QWidget.__init__(self)
        self.setWindowTitle("IfritEnhanced")
        self.setMinimumSize(1280, 720)
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'icon.ico')))

        # Man made widget
        self.ifritAI_widget = IfritAIWidget(icon_path=os.path.join("IfritAI", "Resources"), game_data_folder=os.path.join("IfritAI", "FF8GameData"))
        self.ifritxlsx_widget = IfritXlsxWidget(icon_path=os.path.join("IfritXlsx", "Resources"), game_data_folder=os.path.join("IfritXlsx", "FF8GameData"))
        self.ifritGui_launcher = IfritGuiLauncher(os.path.join("IfritGui", "publish", "Ifrit.exe"), callback=self.ifritGui_exit)
        self.ifritGui_launcher.launch()

    def ifritGui_exit(self):
        if not self.ifritAI_widget.isVisible() and not self.ifritxlsx_widget.isVisible():
            exit(0)












