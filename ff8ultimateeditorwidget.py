import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QSslKey
from PyQt6.QtWidgets import QWidget, QComboBox, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFileDialog, QSizePolicy

from IfritAI.ifritaiwidget import IfritAIWidget
from IfritAI.ifritmanager import IfritManager
from IfritXlsx.ifritxlsxwidget import IfritXlsxWidget
from ShumiTranslator.shumitranslator import ShumiTranslator
from ifritguilauncher import IfritGuiLauncher


class FF8UltimateEditorWidget(QWidget):

    def __init__(self, icon_path='Resources'):
        QWidget.__init__(self)
        self.setWindowTitle("FF8 ultimate editor")
        #self.setMinimumSize(1280, 720)
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'icon.ico')))
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)

        self.HOBBIT_OPTION_ITEMS = ["AI editor (IfritAI)", "Stat editor (IfritXlsx)", "Kernel text editor (ShumiTranslator)"]

        # Top widget to select what option we want
        self._program_option_title = QLabel("Hobbit tools:")
        self._program_option = QComboBox()
        self._program_option.addItems(self.HOBBIT_OPTION_ITEMS)
        self._program_option.setCurrentIndex(0)
        self._program_option.activated.connect(self._program_option_change)
        self._program_option.setToolTip("Choose which program to edit your c0m file")
        self._program_option_layout = QHBoxLayout()
        self._program_option_layout.addWidget(self._program_option_title)
        self._program_option_layout.addWidget(self._program_option)

        # External program
        self._external_program_title = QLabel("External program:")
        self._ifrit_gui_button = QPushButton()
        self._ifrit_gui_button.setIcon(QIcon(os.path.join(icon_path, 'ifritGui.ico')))
        self._ifrit_gui_button.setIconSize(QSize(30, 30))
        self._ifrit_gui_button.setFixedSize(40, 40)
        self._ifrit_gui_button.clicked.connect(self._launch_ifritGui)
        self._ifrit_gui_button.setToolTip("Launch original ifrit soft")

        self._external_program_layout = QHBoxLayout()
        self._external_program_layout.addWidget(self._external_program_title)
        self._external_program_layout.addWidget(self._ifrit_gui_button)
        self._external_program_layout.addStretch(1)


        self._enhance_layout = QHBoxLayout()
        self._enhance_layout.addLayout(self._program_option_layout)
        self._enhance_layout.addLayout(self._external_program_layout)
        self._enhance_layout.addStretch(1)



        # Man made widget
        self._ifritAI_widget = IfritAIWidget(icon_path=os.path.join("IfritAI", "Resources"), game_data_folder=os.path.join("FF8GameData"))
        self._ifritxlsx_widget = IfritXlsxWidget(icon_path=os.path.join("IfritXlsx", "Resources"), game_data_folder=os.path.join("FF8GameData"))
        self._shumi_translator_widget = ShumiTranslator(icon_path=os.path.join("ShumiTranslator", "Resources"), game_data_folder=os.path.join("FF8GameData"))

        self._ifritAI_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._ifritxlsx_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._ifritxlsx_widget.hide()
        self._shumi_translator_widget.hide()
        self.ifritGui_launcher = IfritGuiLauncher(os.path.join("IfritGui", "publish", "Ifrit.exe"), callback=self._ifritGui_exit)

        self._main_layout.addLayout(self._enhance_layout)
        self._main_layout.addWidget(self._ifritAI_widget)
        self._main_layout.addWidget(self._ifritxlsx_widget)
        self._main_layout.addWidget(self._shumi_translator_widget)

        self._ifritAI_widget.adjustSize()
        self._ifritxlsx_widget.adjustSize()
        self.adjustSize()

    def _launch_ifritGui(self):
        self.ifritGui_launcher.launch()

    def _ifritGui_exit(self):
        pass
        #if not self._ifritAI_widget.isVisible() and not self._ifritxlsx_widget.isVisible():
        #    exit(0)

    def _program_option_change(self):
        if self._program_option.currentIndex() == 0:
            self._ifritAI_widget.show()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.hide()
        elif self._program_option.currentIndex() == 1:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.show()
            self._shumi_translator_widget.hide()
        elif self._program_option.currentIndex() == 2:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.show()
        else:
            print(f"Unexpected program option index:{self._program_option.currentIndex()} and name {self._program_option.currentText()}")

        self._ifritAI_widget.adjustSize()
        self._ifritxlsx_widget.adjustSize()
        self.adjustSize()










