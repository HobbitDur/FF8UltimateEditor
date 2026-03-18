import logging
import os
import pathlib

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QCheckBox, QComboBox, QLabel, QHBoxLayout, QSpinBox, QFileDialog, \
    QMessageBox, QPlainTextEdit

from IfritTexture.ifrittexturemanager import IfritTextureManager
from IfritXlsx.ifritxlsxmanager import IfritXlsxManager


class IfritTextureWidget(QWidget):
    WORK_OPTION = ["Dat -> Xlsx", "Xlsx -> Dat"]

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ifrit_manager = IfritTextureManager()
        self.logger = logging.getLogger(__name__)

        self.general_info_label_widget = QLabel(
            "This tool allow to extract/import texture files<br/>"
            "First you extract c0mxxx.dat files (with deling for example)<br/>"
            "With this, you'll transform those .dat in a xlsx file<br/>"
            "Then you can edit this xlsx file with either Excel (recommended) or libreOffice<br/>"
            "Once you have finished editing the xlsx file, you save it<br/>"
            "and you can then patch c0mxxx.dat files with the xlsx you have<br/><br/>")

        self.process_info_label_widget = QLabel(
            "<u>Step 1:</u> Choose which process you want:<ul>"
            "<li><b>Dat -> Xlsx</b> to transform your c0mxxx.dat files to a xlsx file</li>"
            "<li><b>Xlsx -> Dat</b> to patch your c0mxxx.dat files with a xlsx file</li></ul>")

        self._button_layout = QHBoxLayout()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self._analyse_button = QPushButton("Analyse")
        self._analyse_button.clicked.connect(self._analyze)
        self._button_layout.addWidget(self._analyse_button)


        self._meta_text = QPlainTextEdit()
        self._meta_text_title = QLabel("Meta")
        self._meta_layout = QHBoxLayout()
        self._meta_layout.addWidget(self._meta_text)
        self._meta_layout.addWidget(self._meta_text_title)

        self.main_layout.addLayout(self._button_layout)
        self.main_layout.addLayout(self._meta_layout)

        self._file_dialog_folder = ""
        self._file_dialog = QFileDialog()

    def _analyze(self):
        file_to_load = None
        file_to_load = "c0m001.dat" # for developping faster
        if file_to_load is None:
            file_to_load = self._file_dialog.getOpenFileName(parent=self, caption="File containing the TIM", filter="", directory=self._file_dialog_folder)[0]
        self.ifrit_manager.analyze(file_to_load)