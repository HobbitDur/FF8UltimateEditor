import csv
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFileDialog, QPushButton, QHBoxLayout, QLabel, QComboBox, QCheckBox, QSlider, QSpinBox, QMessageBox

from CCGroup.card import Card
from CCGroup.cardwidget import CardWidget
from DrawEditor.draw import Draw
from DrawEditor.drawwidget import DrawWidget
from FF8GameData.gamedata import GameData


class DrawEditorWidget(QWidget):
    GENERAL_OFFSET = 0x400000
    VERSION_LIST = ["OG (2013)"]

    def __init__(self, icon_path='Resources', game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        # Window management
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        # self.setWindowTitle("CC Group")
        # self.setMinimumSize(600, 600)
        # self.setWindowIcon(QIcon(os.path.join(icon_path, 'icon.ico')))

        self.__file_dialog = QFileDialog()
        self.__file_dialog_button = QPushButton()
        self.__file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.__file_dialog_button.setIconSize(QSize(30, 30))
        self.__file_dialog_button.setFixedSize(40, 40)
        self.__file_dialog_button.setToolTip("Open data file")
        self.__file_dialog_button.clicked.connect(self.__load_file)

        self.csv_save_dialog = QFileDialog()
        self.__save_dialog = QFileDialog()
        self.__save_button = QPushButton()
        self.__save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.__save_button.setIconSize(QSize(30, 30))
        self.__save_button.setFixedSize(40, 40)
        self.__save_button.setToolTip("Save to file")
        self.__save_button.clicked.connect(self.__save_file)

        self.csv_upload_button = QPushButton()
        self.csv_upload_button.setIcon(QIcon(os.path.join(icon_path, 'csv_upload.png')))
        self.csv_upload_button.setIconSize(QSize(30, 30))
        self.csv_upload_button.setFixedSize(40, 40)
        self.csv_upload_button.setToolTip("Upload csv")
        self.csv_upload_button.clicked.connect(self.__open_csv)

        self.csv_save_button = QPushButton()
        self.csv_save_button.setIcon(QIcon(os.path.join(icon_path, 'csv_save.png')))
        self.csv_save_button.setIconSize(QSize(30, 30))
        self.csv_save_button.setFixedSize(40, 40)
        self.csv_save_button.setToolTip("Save to csv")
        self.csv_save_button.clicked.connect(self.__save_csv)

        self.__version_label_widget = QLabel("Game version")
        self.__version_widget = QComboBox(parent=self)
        self.__version_widget.addItems(self.VERSION_LIST)
        self.__version_widget.setToolTip("Select version of the game")
        self.__version_layout = QHBoxLayout()
        self.__version_layout.addWidget(self.__version_label_widget)
        self.__version_layout.addWidget(self.__version_widget)

        self.__layout_top = QHBoxLayout()
        self.__layout_top.addWidget(self.__file_dialog_button)
        self.__layout_top.addWidget(self.__save_button)
        self.__layout_top.addWidget(self.csv_upload_button)
        self.__layout_top.addWidget(self.csv_save_button)
        self.__layout_top.addLayout(self.__version_layout)
        self.__layout_top.addStretch(1)

        self.current_file_data = bytearray()
        self.game_data = GameData(game_data_folder)
        self.game_data.load_field_data()
        self.game_data.load_exe_data()
        self.game_data.load_magic_data()
        self.game_data.load_draw_data()

        self.__draw_list = []
        self.__draw_widget = DrawWidget(self.game_data, parent=self)

        self.window_layout.addLayout(self.__layout_top)
        self.window_layout.addWidget(self.__draw_widget)

        self.__nb_draw = 256

    def __load_file(self, file_to_load: str = ""):
        self.__file_dialog_button.setEnabled(False)
        self.__save_button.setEnabled(False)
        self.__version_widget.setEnabled(False)

        #file_to_load = os.path.join("FF8_EN.exe")  # For developing faster
        if not file_to_load:
            file_to_load = self.__file_dialog.getOpenFileName(parent=self, caption="Find FF8 exe", filter="*.exe",
                                                              directory=os.getcwd())[0]
        if file_to_load:
            self.file_loaded = file_to_load

            self.current_file_data = bytearray()
            with open(self.file_loaded, "rb") as in_file:
                while el := in_file.read(1):
                    self.current_file_data.extend(el)

            if self.__version_widget.currentIndex() == 0:
                draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
            else:
                draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
            draw_data_size = self.game_data.exe_data_json["draw_data_offset"]["size"]
            self.__draw_list = []
            for draw_data_index in range(draw_data_size):
                new_draw = Draw(game_data=self.game_data, id=draw_data_index + 1, data_hex=self.current_file_data[draw_offset + draw_data_index: draw_offset + draw_data_index + 1])
                self.__draw_list.append(new_draw)

            self.__draw_widget.set_draw(self.__draw_list)

        self.__file_dialog_button.setEnabled(True)
        self.__save_button.setEnabled(True)
        self.__version_widget.setEnabled(True)

    def __save_csv(self):
        file_to_save = self.csv_save_dialog.getSaveFileName(parent=self, caption="Find csv file", filter="*.csv", directory="draw_data" )[0]
        if file_to_save:
            with open(file_to_save, 'w', newline='', encoding="utf-8") as csv_file:
                csv_writer = csv.writer(csv_file, delimiter=GameData.find_delimiter_from_csv_file(file_to_save), quotechar='§', quoting=csv.QUOTE_MINIMAL)
                csv_writer.writerow(['Draw ID', 'Magic ID', 'High Yield', 'Refill'])

                for draw in self.__draw_list:
                    csv_writer.writerow([draw.get_id(), draw.magic_index, int(draw.high_yield), int(draw.refill)])

    def __open_csv(self, csv_to_load: str = ""):
        csv_to_load = \
            self.csv_save_dialog.getOpenFileName(parent=self, caption="Find csv file (in UTF8 format only)",
                                                 filter="*.csv")[0]
        if csv_to_load:
            with open(csv_to_load, newline='', encoding="utf-8") as csv_file:
                try:
                    csv_data = csv.reader(csv_file, delimiter=GameData.find_delimiter_from_csv_file(csv_to_load), quotechar='§')
                    #   ['Draw ID', 'Magic ID', 'High Yield', 'Refill']
                    self.__draw_list = []
                    for row_index, row in enumerate(csv_data):
                        if row_index == 0:  # Ignoring title row
                            continue
                        new_draw = Draw(self.game_data,row_index, bytearray())
                        new_draw.set_id(int(row[0]))
                        new_draw.magic_index = int(row[1])
                        new_draw.high_yield = bool(int(row[2]))
                        new_draw.refill = bool(int(row[3]))
                        self.__draw_list.append(new_draw)
                except UnicodeDecodeError as e:
                    print(e)
                    message_box = QMessageBox()
                    message_box.setText("Wrong <b>encoding</b>, please use <b>UTF8</b> formating only.<br>"
                                        "In excel, you can go to the \"Data tab\", \"Import text file\" and choose UTF8 encoding")
                    message_box.setIcon(QMessageBox.Icon.Critical)
                    message_box.setWindowTitle("Draw Editor - Wrong CSV encoding")
                    # message_box.setWindowIcon(self.__shumi_icon)
                    message_box.exec()
            self.__draw_widget.set_draw(self.__draw_list)


    def __save_file(self):
        default_file_name = os.path.join(os.getcwd(), "draw_data_injection.hext")
        file_to_save = self.__save_dialog.getSaveFileName(parent=self, caption="Save hext file", filter="*.hext",
                                                          directory=default_file_name)[0]
        if file_to_save:
            hext_str = ""
            # First writing base data (not sure why necessary, but everyone does it)
            # Then adding the offset of the data
            hext_str += "#Offset to dynamic data\n"
            hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET)

            draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]

            # Now adding the card data for the menu
            hext_str += "#Data represent the following values:\n"
            hext_str += "#Magic ID, High Yield, Refill\n"
            hext_str += "#Data are concatenated into a single byte value\n"

            hext_str += "#Start of draw data is at 0x{:X}\n\n".format(draw_offset)

            for draw_index, draw_data in enumerate(self.__draw_list):
                hext_str += f"#Address  MM HY RF for draw ID {draw_data.get_id()}\n"
                hext_str += "#{:X}".format(draw_offset + draw_index)
                hext_str += " = "
                hext_str += "{:02X}".format(draw_data.magic_index) + " " + "{:02X}".format(draw_data.high_yield) + " " + "{:02X}".format(draw_data.refill)
                hext_str += "\n"
                hext_str += " {:X}".format(draw_offset + draw_index)
                hext_str += " = "
                value_to_set = draw_data.magic_index
                if draw_data.high_yield:
                    value_to_set = value_to_set | 0x80
                if draw_data.refill:
                    value_to_set = value_to_set | 0x40
                hext_str += "{:02X}".format(value_to_set)
                hext_str += "\n\n"


            # Saving hext
            with open(file_to_save, "w") as hext_file:
                hext_file.write(hext_str)
