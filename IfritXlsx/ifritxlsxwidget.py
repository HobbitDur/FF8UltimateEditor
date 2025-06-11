import logging
import os
import pathlib

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QCheckBox, QComboBox, QLabel, QHBoxLayout, QSpinBox, QFileDialog, \
    QMessageBox

from IfritXlsx.ifritxlsxmanager import IfritXlsxManager


class IfritXlsxWidget(QWidget):
    WORK_OPTION = ["Dat -> Xlsx", "Xlsx -> Dat"]

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ifrit_manager = IfritXlsxManager(game_data_folder)
        self.setWindowTitle("Ifrit-XLSX")
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'icon.ico'))
        self.setWindowIcon(self.__ifrit_icon)
        self.dat_file_selected = []
        self.xlsx_file_selected = ""
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename='ifritXlsx.log', level=logging.INFO)
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'icon.ico'))
        # self.setMinimumSize(300,200)

        self.general_info_label_widget = QLabel(
            "This tool process is pretty simple<br/>"
            "First you transform c0mxxx.dat files (with deling for example)<br/>"
            "With this, you'll transform those .dat in a xlsx file<br/>"
            "Then you can edit this xlsx file with either Excel (recommended) or libreOffice<br/>"
            "Once you have finished editing the xlsx file, you save it<br/>"
            "and you can then patch c0mxxx.dat files with the xlsx you have<br/><br/>")

        self.process_info_label_widget = QLabel(
            "<u>Step 1:</u> Choose which process you want:<ul>"
            "<li><b>Dat -> Xlsx</b> to transform your c0mxxx.dat files to a xlsx file</li>"
            "<li><b>Xlsx -> Dat</b> to patch your c0mxxx.dat files with a xlsx file</li></ul>")
        self.process_selector = QComboBox()
        self.process_selector.addItems(self.WORK_OPTION)
        self.process_selector.setCurrentIndex(0)
        self.process_selector.setFixedSize(100, 30)
        self.process_selector.activated.connect(self.__process_change)

        self.process_layout = QHBoxLayout()
        self.process_layout.addStretch(1)
        self.process_layout.addWidget(self.process_selector)
        self.process_layout.addStretch(1)

        self.load_dat_label_widget = QLabel("<u>Step 2:</u> Open dat file that will either be read or patched")
        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.file_dialog_button.setIconSize(QSize(30, 30))
        self.file_dialog_button.setFixedSize(40, 40)
        self.file_dialog_button.clicked.connect(self.__load_dat_file)

        self.dat_loaded_label = QLabel("Done")
        self.dat_loaded_label.hide()

        self.open_dat_file_layout = QHBoxLayout()
        self.open_dat_file_layout.addStretch(1)
        self.open_dat_file_layout.addWidget(self.file_dialog_button)
        self.open_dat_file_layout.addWidget(self.dat_loaded_label)

        self.open_dat_file_layout.addStretch(1)

        self.load_csv_label_widget = QLabel("<u>Step 3:</u> Open xlsx file that will either be read or created")
        self.csv_save_dialog = QFileDialog()
        self.csv_save_button = QPushButton()
        self.csv_save_button.setIcon(QIcon(os.path.join(icon_path, 'csv_save.png')))
        self.csv_save_button.setIconSize(QSize(30, 30))
        self.csv_save_button.setFixedSize(40, 40)
        self.csv_save_button.clicked.connect(self.__load_xlsx_file)

        self.csv_upload_button = QPushButton()
        self.csv_upload_button.setIcon(QIcon(os.path.join(icon_path, 'csv_upload.png')))
        self.csv_upload_button.setIconSize(QSize(30, 30))
        self.csv_upload_button.setFixedSize(40, 40)
        self.csv_upload_button.clicked.connect(self.__load_xlsx_file)

        self.csv_loaded_label = QLabel("Done")
        self.csv_loaded_label.hide()

        self.load_csv_layout = QHBoxLayout()
        self.load_csv_layout.addStretch(1)
        self.load_csv_layout.addWidget(self.csv_save_button)
        self.load_csv_layout.addWidget(self.csv_upload_button)
        self.load_csv_layout.addWidget(self.csv_loaded_label)
        self.load_csv_layout.addStretch(1)

        self.limit_info_label_widget = QLabel(
            "<u>Step 4</u>: Select which monster to work on:<br/>"
            "The process can be quite long, so you can choose which monster ID you can to load"
            "-1 means all monster (by default)<br/>"
            "Useful if you want to write only certain .dat from a big xlsx file with all monsters")
        self.limit_option = QSpinBox()
        self.limit_option.setMaximum(200)
        self.limit_option.setMinimum(-1)
        self.limit_option.setValue(-1)
        self.limit_option.setFixedSize(50, 30)
        self.limit_option_label = QLabel("File ID: ")

        self.limit_layout = QHBoxLayout()
        self.limit_layout.addStretch(1)
        self.limit_layout.addWidget(self.limit_option)
        self.limit_layout.addStretch(1)

        self.autoopen_info_label_widget = QLabel(
            "<u>Step 5:</u> Just to auto-open xlsx file if you want")

        self.open_xlsx = QCheckBox("Open xlsx when finish")

        self.autoopen_layout = QHBoxLayout()
        self.autoopen_layout.addStretch(1)
        self.autoopen_layout.addWidget(self.open_xlsx)
        self.autoopen_layout.addStretch(1)

        self.analyse_ai_info_label_widget = QLabel(
            "<u>Step 6:</u> You can analyse and write the AI when reading dat file<br/>"
            "Writing back was possible, but deleted as IfritAI super seed this way.<br/>")
        self.analyse_ai = QCheckBox("Analyse IA")
        self.analyse_ai.setChecked(False)

        self.analyse_ai_layout = QHBoxLayout()
        self.analyse_ai_layout.addStretch(1)
        self.analyse_ai_layout.addWidget(self.analyse_ai)
        self.analyse_ai_layout.addStretch(1)

        self.launch_info_label_widget = QLabel("<u>Step 7:</u> Launch work !")
        self.launch_button = QPushButton()
        self.launch_button.setText("Launch")
        # self.file_dialog_button.setFixedSize(30, 30)
        self.launch_button.clicked.connect(self.__launch)
        self.launch_button.setFixedHeight(60)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.main_layout.addWidget(self.general_info_label_widget)
        self.main_layout.addWidget(self.process_info_label_widget)
        self.main_layout.addLayout(self.process_layout)
        self.main_layout.addWidget(self.load_dat_label_widget)
        self.main_layout.addLayout(self.open_dat_file_layout)
        self.main_layout.addWidget(self.load_csv_label_widget)
        self.main_layout.addLayout(self.load_csv_layout)
        self.main_layout.addWidget(self.limit_info_label_widget)
        self.main_layout.addLayout(self.limit_layout)
        self.main_layout.addWidget(self.autoopen_info_label_widget)
        self.main_layout.addLayout(self.autoopen_layout)
        self.main_layout.addWidget(self.analyse_ai_info_label_widget)
        self.main_layout.addLayout(self.analyse_ai_layout)
        self.main_layout.addWidget(self.launch_info_label_widget)
        self.main_layout.addWidget(self.launch_button)

        #self.show()
        self.__process_change()

        # self.dat_file_selected = ["C:/Users/Ludovic/Documents/Junction VIII/ilp-wip/Test/battle/c0m028.dat"]
        # self.xlsx_file_selected = "C:/Users/Ludovic/Documents/Junction VIII/ilp-wip/Test/battle/test.xlsx"
        # self.analyse_ai.setChecked(False)
        # self.open_xlsx.setChecked(False)
        # self.process_selector.setCurrentIndex(0)
        # self.limit_option.setValue(28)

    def __process_change(self):
        if self.process_selector.currentIndex() == 0:  # Dat to xlsx
            self.csv_upload_button.hide()
            self.csv_save_button.show()
            self.analyse_ai_info_label_widget.show()
            self.analyse_ai.show()
        elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
            self.csv_upload_button.show()
            self.csv_save_button.hide()
            self.analyse_ai_info_label_widget.hide()
            self.analyse_ai.hide()

    def __load_dat_file(self, file_to_load: str = ""):
        # file_to_load = os.path.join("OriginalFiles", "c0m014.dat")  # For developing faster
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileNames(parent=self, caption="Select dat file", filter="*.dat",
                                                             directory=os.getcwd())[0]
        self.dat_file_selected = file_to_load
        if self.dat_file_selected:
            self.logger.info(f"Selected following .dat files: {self.dat_file_selected}")
            self.dat_loaded_label.show()

    def __load_xlsx_file(self, file_to_load: str = ""):
        # file_to_load = os.path.join("OriginalFiles", "c0m014.dat")  # For developing faster
        if not file_to_load:
            if self.process_selector.currentIndex() == 0:  # Dat to xlsx
                file_to_load = self.file_dialog.getSaveFileName(parent=self, caption="Select xlsx file", filter="*.xlsx")[0]
            elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
                file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Select xlsx file", filter="*.xlsx")[0]
        self.xlsx_file_selected = file_to_load
        if self.xlsx_file_selected:
            self.logger.info(f"Selected following .xlsx file: {self.xlsx_file_selected}")
            self.csv_loaded_label.show()

    def __launch(self):
        if not self.dat_file_selected or not self.xlsx_file_selected:
            text_error = "Please first select {} file"
            if not self.dat_file_selected:
                text_error = text_error.format(".dat")
            elif not self.xlsx_file_selected:
                text_error = text_error.format(".xlsx")
            message_box = QMessageBox()
            message_box.setText(text_error)
            message_box.setIcon(QMessageBox.Icon.Critical)
            message_box.setWindowIcon(self.__ifrit_icon)
            message_box.setWindowTitle("IfritXlsx - Error")
            message_box.exec()
        else:
            if self.limit_option.value() != -1:
                dat_file_current_list = []
                for current_path in self.dat_file_selected:
                    if int(int(pathlib.Path(current_path).name.replace('c0m','').replace('.dat', ''))) == self.limit_option.value():
                        dat_file_current_list = [current_path]
                if not dat_file_current_list:
                    text_error = "Monster ID {} not found in .dat file loaded, please either change loaded files or the monster ID".format(
                        self.limit_option.value())
                    message_box = QMessageBox()
                    message_box.setText(text_error)
                    message_box.setIcon(QMessageBox.Icon.Critical)
                    message_box.setWindowIcon(self.__ifrit_icon)
                    message_box.setWindowTitle("IfritXlsx - Error")
                    message_box.exec()
                    return
            else:
                dat_file_current_list = self.dat_file_selected
            if self.process_selector.currentIndex() == 0:  # Dat to xlsx
                self.ifrit_manager.create_file(self.xlsx_file_selected)
                self.ifrit_manager.dat_to_xlsx(dat_file_current_list, self.analyse_ai.isChecked())

            elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
                self.ifrit_manager.load_file(self.xlsx_file_selected)
                self.ifrit_manager.xlsx_to_dat(dat_file_current_list, self.limit_option.value())
            if self.open_xlsx.isChecked():
                os.startfile(self.xlsx_file_selected)
        print("Launch over !")
