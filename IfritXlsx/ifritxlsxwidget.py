import logging
import os
import pathlib

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QCheckBox, QComboBox, QLabel, QHBoxLayout, QSpinBox, QFileDialog, \
    QMessageBox, QFrame

from Ifrit.ifritmanager import IfritManager


class IfritXlsxWidget(QWidget):
    WORK_OPTION = ["Dat -> Xlsx", "Xlsx -> Dat"]

    def __init__(self, ifrit_manager:IfritManager,icon_path="Resources"):
        QWidget.__init__(self)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ifrit_manager = ifrit_manager
        self.xlsx_file_selected = ""
        self.file_dialog = QFileDialog()
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))

        self.general_info_label_widget = QLabel(
            "This tool process is pretty simple<br/>"
            "First you extract c0mxxx.dat files (with deling for example)<br/>"
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
        self.process_selector.activated.connect(self.__process_change)

        self.process_layout = QHBoxLayout()
        self.process_layout.addStretch(1)
        self.process_layout.addWidget(self.process_selector)
        self.process_layout.addStretch(1)

        self.load_csv_label_widget = QLabel("<u>Step 2:</u> Open xlsx file that will either be read or created")
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

        self.autoopen_info_label_widget = QLabel(
            "<u>Step 3:</u> Just to auto-open xlsx file if you want")

        self.open_xlsx = QCheckBox("Open xlsx when finish")

        self.autoopen_layout = QHBoxLayout()
        self.autoopen_layout.addStretch(1)
        self.autoopen_layout.addWidget(self.open_xlsx)
        self.autoopen_layout.addStretch(1)

        self.launch_info_label_widget = QLabel("<u>Step 4:</u> Launch work !")
        self.launch_button = QPushButton()
        self.launch_button.setText("Launch")
        # self.file_dialog_button.setFixedSize(30, 30)
        self.launch_button.clicked.connect(self.__launch)
        self.launch_button.setFixedHeight(60)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.separator.setFrameShadow(QFrame.Shadow.Sunken)

        # 2. Make it "Big"
        self.separator.setLineWidth(3)  # Adjust this number for thickness

        self.main_layout = QVBoxLayout()
        self.step_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        self.main_layout.addWidget(self.general_info_label_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.left_layout.addWidget(self.process_info_label_widget)
        self.left_layout.addLayout(self.process_layout)
        self.left_layout.addWidget(self.load_csv_label_widget)
        self.left_layout.addLayout(self.load_csv_layout)
        self.left_layout.addStretch(1)
        self.right_layout.addWidget(self.autoopen_info_label_widget)
        self.right_layout.addLayout(self.autoopen_layout)
        self.right_layout.addWidget(self.launch_info_label_widget)
        self.right_layout.addStretch(1)

        self.step_layout.addLayout(self.left_layout)
        self.step_layout.addWidget(self.separator)
        self.step_layout.addLayout(self.right_layout)

        self.main_layout.addLayout(self.step_layout)
        self.main_layout.addWidget(self.launch_button)

        #self.show()
        self.__process_change()

    def __process_change(self):
        if self.process_selector.currentIndex() == 0:  # Dat to xlsx
            self.csv_upload_button.hide()
            self.csv_save_button.show()
        elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
            self.csv_upload_button.show()
            self.csv_save_button.hide()

    def __load_xlsx_file(self, file_to_load: str = ""):
        # file_to_load = os.path.join("OriginalFiles", "c0m014.dat")  # For developing faster
        if not file_to_load:
            if self.process_selector.currentIndex() == 0:  # Dat to xlsx
                file_to_load = self.file_dialog.getSaveFileName(parent=self, caption="Select xlsx file", filter="*.xlsx")[0]
            elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
                file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Select xlsx file", filter="*.xlsx")[0]
        self.xlsx_file_selected = file_to_load
        if self.xlsx_file_selected:
            print(f"Selected following .xlsx file: {self.xlsx_file_selected}")
            self.csv_loaded_label.show()

    def __launch(self):
        text_error = ""
        if not self.xlsx_file_selected:
            text_error = "Please first select xlsx file"
        elif not self.ifrit_manager.enemy.origin_path:
            text_error = "Please first select dat file"
        if text_error:
            message_box = QMessageBox()
            message_box.setText(text_error)
            message_box.setIcon(QMessageBox.Icon.Critical)
            message_box.setWindowIcon(self.__ifrit_icon)
            message_box.setWindowTitle("IfritXlsx - Error")
            message_box.exec()
            return
        else:

            dat_file_current_list = (self.ifrit_manager.enemy.origin_path,)
            dat_id_current_list = (self.ifrit_manager.enemy.id,)
            if self.process_selector.currentIndex() == 0:  # Dat to xlsx
                self.ifrit_manager.create_xlsx_file(self.xlsx_file_selected)
                self.ifrit_manager.dat_to_xlsx(dat_file_current_list, False)
            elif self.process_selector.currentIndex() == 1:  # Xlsx to dat
                self.ifrit_manager.load_xlsx_file(self.xlsx_file_selected)
                self.ifrit_manager.xlsx_to_dat(dat_file_current_list, dat_id_current_list)
            self.ifrit_manager.close_xlsx_file()
            if self.open_xlsx.isChecked():
                os.startfile(self.xlsx_file_selected)
        print("Xlsx work done !")
