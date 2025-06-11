import csv
import os
import pathlib

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog, QHBoxLayout, QLabel, \
    QMessageBox, QComboBox

from FF8GameData.gamedata import GameData, FileType, SectionType, RemasterCardType
from .model.battle.battlemanager import BattleManager
from .model.exe.exemanager import ExeManager
from .model.exe.remasterdatmanager import RemasterDatManager
from .model.field.fieldfsmanager import FieldFsManager
from .model.kernel.kernelmanager import KernelManager
from .model.mngrp.mngrpmanager import MngrpManager
from .model.mngrp.string.sectionstring import SectionString
from .model.world.worldfsmanager import WorldFsManager
from .view.sectionwidget import SectionWidget
from .view.tabholderwidget import TabHolderWidget


class ShumiTranslator(QWidget):
    CSV_FOLDER = "csv"
    FILE_MANAGED = ['kernel.bin', 'namedic.bin', 'mngrp.bin', 'FF8.exe/remaster.dat', 'c0mxx.dat', 'field.fs', 'world.fs']
    FILE_MANAGED_REGEX = ['*kernel*.bin', '*namedic*.bin', '*mngrp*.bin', 'FF8*.exe;off_cards_names_*.dat', "c0m*.dat", 'field*.fs', 'world*.fs']

    def __init__(self, icon_path='Resources',game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        # Special data
        self.game_data = GameData(game_data_folder)
        self.game_data.load_kernel_data()
        self.game_data.load_mngrp_data()
        self.game_data.load_item_data()
        self.game_data.load_magic_data()
        self.game_data.load_card_data()
        self.game_data.load_stat_data()
        self.game_data.load_ai_data()
        self.game_data.load_monster_data()
        self.game_data.load_status_data()
        self.game_data.load_gforce_data()
        self.game_data.load_special_action_data()
        self.game_data.load_enemy_abilities_data()
        #self.game_data.load_all()

        self.translation_list = []
        self.file_loaded = ""
        self.file_mngrphd_loaded = ""
        self.csv_loaded = ""
        self.file_loaded_type = FileType.NONE

        self.lang_list = ["en", "sp", "fr", "it", "ge"]

        # Window management
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)

        self.layout_main = QVBoxLayout()
        self.scroll_widget.setLayout(self.layout_main)

        self.setWindowTitle("ShumiTranslator")
        self.setMinimumSize(800, 800)
        self.__shumi_icon = QIcon(os.path.join(icon_path, 'icon.ico'))
        self.setWindowIcon(self.__shumi_icon)

        # Top management
        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.file_dialog_button.setIconSize(QSize(30, 30))
        self.file_dialog_button.setFixedSize(40, 40)
        self.file_dialog_button.setToolTip("Open data file (choose a file type first")
        self.file_dialog_button.clicked.connect(self.__load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save to file")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.__save_file)

        self.csv_save_dialog = QFileDialog()
        self.csv_save_button = QPushButton()
        self.csv_save_button.setIcon(QIcon(os.path.join(icon_path, 'csv_save.png')))
        self.csv_save_button.setIconSize(QSize(30, 30))
        self.csv_save_button.setFixedSize(40, 40)
        self.csv_save_button.setToolTip("Save to csv")
        self.csv_save_button.setEnabled(False)
        self.csv_save_button.clicked.connect(self.__save_csv)

        self.csv_upload_button = QPushButton()
        self.csv_upload_button.setIcon(QIcon(os.path.join(icon_path, 'csv_upload.png')))
        self.csv_upload_button.setIconSize(QSize(30, 30))
        self.csv_upload_button.setFixedSize(40, 40)
        self.csv_upload_button.setToolTip("Upload csv")
        self.csv_upload_button.setEnabled(False)
        self.csv_upload_button.clicked.connect(self.__open_csv)

        self.compress_button = QPushButton()
        self.compress_button.setIcon(QIcon(os.path.join(icon_path, 'compress.png')))
        self.compress_button.setIconSize(QSize(30, 30))
        self.compress_button.setFixedSize(40, 40)
        self.compress_button.setToolTip("Compress data")
        self.compress_button.setEnabled(False)
        self.compress_button.clicked.connect(self.__compress_data)

        self.uncompress_button = QPushButton()
        self.uncompress_button.setIcon(QIcon(os.path.join(icon_path, 'uncompress.png')))
        self.uncompress_button.setIconSize(QSize(30, 30))
        self.uncompress_button.setFixedSize(40, 40)
        self.uncompress_button.setToolTip("Uncompress data")
        self.uncompress_button.setEnabled(False)
        self.uncompress_button.clicked.connect(self.__uncompress_data)

        self.file_type_selection_label = QLabel("File type to load:")
        self.file_type_selection_widget = QComboBox()
        self.file_type_selection_widget.addItems(self.FILE_MANAGED)
        self.file_type_selection_widget.setToolTip("Allow you to choose which file to load")
        self.file_type_selection_widget.setCurrentIndex(0)  # Change this for faster test

        self.file_type_layout = QHBoxLayout()
        self.file_type_layout.addWidget(self.file_type_selection_label)
        self.file_type_layout.addWidget(self.file_type_selection_widget)

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        self.info_button.setIconSize(QSize(30, 30))
        self.info_button.setFixedSize(40, 40)
        self.info_button.setToolTip("Show toolmaker info")
        self.info_button.clicked.connect(self.__show_info)

        self.text_file_loaded = QLabel("File loaded: None")
        self.text_file_loaded.hide()
        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self.file_dialog_button)
        self.layout_top.addWidget(self.save_button)
        self.layout_top.addWidget(self.csv_save_button)
        self.layout_top.addWidget(self.csv_upload_button)
        self.layout_top.addWidget(self.compress_button)
        self.layout_top.addWidget(self.uncompress_button)
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addLayout(self.file_type_layout)
        self.layout_top.addSpacing(20)
        self.layout_top.addWidget(self.text_file_loaded)
        self.layout_top.addStretch(1)

        # Warning
        self.warning_kernel_label_widget = QLabel(
            "{x0...} are yet unknown text correspondence. Pls don't modify them.<br/>"
            "Value between {} are \"compressed\" data. Pls don't remove bracket around.<br/>"
            "The file as a size max (40456?).<br/>"
            "If you wish to get rid of parenthesis you can uncompress<br/>"
            "But pls compress before saving to avoid size problem.")
        self.warning_comx_label_widget = QLabel(
            "c0m127 and all files > 143 are garbage so they are ignored even if selected")
        self.warning_comx_label_widget.hide()
        self.warning_kernel_label_widget.hide()
        self.warning_mngrp_label_widget = QLabel(
            "{x0...} are yet unknown text correspondence. Pls don't modify them.<br/>"
            "Value between {} are \"compressed\" data. Pls don't remove bracket around.<br/>")
        self.warning_mngrp_label_widget.hide()
        self.warning_exe_label_widget = QLabel(
            "/!\\ Only compatible with FFNx (2000 and 2013 version)<br/>"
            "When saving, this tool produce<br/>"
            "msd files that need to be put in the folder direct/exe/<br/>")
        self.warning_exe_label_widget.hide()
        self.warning_field_label_widget = QLabel(
            "This tool use deling, an external tool done my myst6re, to manage all field text (what character says). <br/> Due to this, the tool doesn't offer direct "
            "modification but allows to export and import csv. <br/> "
            "The input is the field.fs file (need the .fi and .fl with same name and in same folder than field.fs)<br/>"
            "It will output a folder containing only the msd files which correspond to the file text.<br/>"
            "For the moment, it only works on Windows.<br/>"
            "<b>/!\\ When saving or uploading csv, there is a lot of work being done, so be patient.</b><br/>"
            "The save put all files in a field folder that can be directly put in the direct folder of FFNx.")
        self.warning_field_label_widget.hide()
        self.warning_world_label_widget = QLabel(
            "This tool use deling, an external tool done my myst6re, to manage all world text (Draw point, aubel,...). <br/> Due to this, the tool doesn't offer direct "
            "modification but allows to export and import csv. <br/> "
            "The input is the world.fs file (need the .fi and .fl with same name and in same folder than world.fs)<br/>"
            "It will output a folder containing only the msd files which correspond to the file text.<br/>"
            "For the moment, it only works on Windows.<br/>"
            "<b>/!\\ When saving or uploading csv, there is a lot of work being done, so be patient.</b><br/>"
            "The save put all files in a world folder that can be directly put in the direct folder of FFNx.")
        self.warning_world_label_widget.hide()

        self.layout_full_top = QVBoxLayout()
        self.layout_full_top.addLayout(self.layout_top)

        self._tab_widget = TabHolderWidget(FileType.MNGRP)
        self._tab_widget.currentChanged.connect(self.adjustSize)
        self._tab_widget.hide()
        self._tab_layout = QVBoxLayout()
        self._tab_layout.addWidget(self._tab_widget)
        self._tab_layout.addStretch(1)

        # Translation management
        self.section_list = []

        self.section_widget_list = []
        self.layout_translation_lines = QVBoxLayout()

        # Main management
        self.window_layout.addLayout(self.layout_full_top)
        self.layout_main.addWidget(self.warning_kernel_label_widget)
        self.layout_main.addWidget(self.warning_comx_label_widget)
        self.layout_main.addWidget(self.warning_mngrp_label_widget)
        self.layout_main.addWidget(self.warning_exe_label_widget)
        self.layout_main.addWidget(self.warning_field_label_widget)
        self.layout_main.addWidget(self.warning_world_label_widget)
        self.layout_main.addLayout(self._tab_layout)
        self.layout_main.addLayout(self.layout_translation_lines)
        self.layout_main.addStretch(1)

        self.window_layout.addWidget(self.scroll_area)

        self.kernel_manager = KernelManager(game_data=self.game_data)
        self.namedic_manager = SectionString(game_data=self.game_data)
        self.mngrp_manager = MngrpManager(game_data=self.game_data)
        self.exe_manager = ExeManager(game_data=self.game_data)
        self.battle_manager = BattleManager(game_data=self.game_data)
        self.remaster_dat_manager = RemasterDatManager(game_data=self.game_data)
        self.field_fs_manager = FieldFsManager(game_data=self.game_data)
        self.world_fs_manager = WorldFsManager(game_data=self.game_data)

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Riccardo</b> for beta testing.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__shumi_icon)
        message_box.setWindowTitle("ShumiTranslator - Info")
        message_box.exec()

    def __compress_data(self):
        # Not all data can be compressed, so we do case by case
        # We give to the subsection the offset that can be compressed (0=None, 1=First, 2 = Second, 3=Both)
        self.scroll_area.setEnabled(False)
        for index_section, section_widget in enumerate(self.section_widget_list):
            compressibility_factor = \
                [x["compressibility_factor"] for x in self.game_data.kernel_data_json["sections"] if
                 x["id"] == section_widget.section.id][
                    0]
            section_widget.compress_str(compressibility_factor)
        self.scroll_area.setEnabled(True)

    def __uncompress_data(self):
        self.scroll_area.setEnabled(False)
        for index_section, section_widget in enumerate(self.section_widget_list):
            section_widget.uncompress_str()
        self.scroll_area.setEnabled(True)

    def __save_file(self):
        self.save_button.setDown(True)
        self.scroll_area.setEnabled(False)
        if self.file_loaded:
            print("file loaded")
            popup_save = True
            if self.file_loaded_type == FileType.KERNEL:
                self.kernel_manager.save_file(self.file_loaded)
                popup_text = "Data saved to file <b>{}</b>".format(pathlib.Path(self.file_loaded).name)
            elif self.file_loaded_type == FileType.NAMEDIC:
                self.namedic_manager.save_file(self.file_loaded)
                popup_text = "Data saved to file <b>{}</b>".format(pathlib.Path(self.file_loaded).name)
            elif self.file_loaded_type == FileType.MNGRP:
                self.mngrp_manager.save_file(self.file_loaded, self.file_mngrphd_loaded)
                popup_text = "Data saved to file <b>{}</b>".format(pathlib.Path(self.file_loaded).name)
            elif self.file_loaded_type == FileType.EXE:
                folder_to_save = self.file_dialog.getExistingDirectory(parent=self, caption="Save msd file", directory=os.getcwd())
                if folder_to_save:
                    self.exe_manager.save_file(folder_to_save)
                    popup_text = "Msd files saved to folder <b>{}</b>".format(pathlib.Path(folder_to_save).name)
                else:
                    popup_save = False
            elif self.file_loaded_type == FileType.DAT:
                self.battle_manager.save_all_file()
                if len(self.file_loaded) == 1:
                    popup_text = "Data saved to file <b>{}</b>".format(pathlib.Path(self.file_loaded[0]).name)
                else:
                    popup_text = "Data saved to file c0mxx.dat"
            elif self.file_loaded_type == FileType.REMASTER_DAT:
                self.remaster_dat_manager.save_file(self.file_loaded)
                popup_text = "Data saved to file <b>{}</b>".format(pathlib.Path(self.file_loaded).name)
            elif self.file_loaded_type == FileType.FIELD_FS:
                self.scroll_area.setEnabled(False)
                self.csv_upload_button.setEnabled(False)
                self.csv_save_button.setEnabled(False)
                folder_to_save = self.file_dialog.getExistingDirectory(parent=self, caption="Save field fs unpacked", directory=os.getcwd())
                if folder_to_save:
                    self.field_fs_manager.save_file(folder_to_save)
                    popup_text = "Msd files saved to folder <b>{}</b>".format(pathlib.Path(folder_to_save).name)
                else:
                    popup_save = False
                self.scroll_area.setEnabled(True)
                self.csv_upload_button.setEnabled(True)
                self.csv_save_button.setEnabled(True)
            elif self.file_loaded_type == FileType.WORLD_FS:
                self.scroll_area.setEnabled(False)
                self.csv_upload_button.setEnabled(False)
                self.csv_save_button.setEnabled(False)
                folder_to_save = self.file_dialog.getExistingDirectory(parent=self, caption="Save world fs unpacked", directory=os.getcwd())
                if folder_to_save:
                    self.world_fs_manager.save_file(folder_to_save)
                    popup_text = "wmsetxx.obj file saved to folder <b>{}</b>".format(pathlib.Path(folder_to_save).name)
                else:
                    popup_save = False
                self.scroll_area.setEnabled(True)
                self.csv_upload_button.setEnabled(True)
                self.csv_save_button.setEnabled(True)

            if popup_save:
                message_box = QMessageBox()
                message_box.setText(popup_text)
                message_box.setIcon(QMessageBox.Icon.Information)
                message_box.setWindowTitle("ShumiTranslator - Data saved")
                message_box.setWindowIcon(self.__shumi_icon)
                message_box.exec()
        self.save_button.setDown(False)
        self.scroll_area.setEnabled(True)

    def __open_csv(self, csv_to_load: str = ""):
        self.scroll_area.setEnabled(False)
        if self.file_loaded:
            if not csv_to_load:
                if os.path.isdir(self.CSV_FOLDER):
                    directory = self.CSV_FOLDER
                else:
                    directory = os.getcwd()
                csv_to_load = \
                    self.csv_save_dialog.getOpenFileName(parent=self, caption="Find csv file (in UTF8 format only)",
                                                         filter="*.csv", directory=directory)[0]
            if csv_to_load:
                try:
                    if self.file_loaded_type == FileType.FIELD_FS or self.file_loaded_type == FileType.WORLD_FS:
                        self.scroll_area.setEnabled(False)
                        self.csv_upload_button.setEnabled(False)
                        self.csv_save_button.setEnabled(False)
                        if self.file_loaded_type == FileType.FIELD_FS:
                            self.field_fs_manager.load_csv(csv_to_load=csv_to_load)
                        elif self.file_loaded_type == FileType.WORLD_FS:
                            self.world_fs_manager.load_csv(csv_to_load=csv_to_load)
                        self.scroll_area.setEnabled(True)
                        self.csv_upload_button.setEnabled(True)
                        self.csv_save_button.setEnabled(True)
                        message_box = QMessageBox()
                        popup_text = "Csv uploaded to the fs file ! (Thanks for your patience)"
                        message_box.setText(popup_text)
                        message_box.setIcon(QMessageBox.Icon.Information)
                        message_box.setWindowTitle("ShumiTranslator - Data saved")
                        message_box.setWindowIcon(self.__shumi_icon)
                        message_box.exec()
                    else:

                        with open(csv_to_load, newline='', encoding="utf-8") as csv_file:

                            csv_data = csv.reader(csv_file, delimiter=GameData.find_delimiter_from_csv_file(csv_to_load), quotechar='§')
                            #   ['Section data name', 'Section widget id', 'Text Sub id', 'Text']
                            for row_index, row in enumerate(csv_data):
                                if row_index == 0:  # Ignoring title row
                                    continue
                                # section_data_name = row[0]
                                section_widget_id = int(row[1])
                                text_sub_id = int(row[2])
                                text_loaded = row[3]

                                if text_loaded == "":
                                    continue
                                # Managing this case as many people do the mistake.
                                text_loaded = text_loaded.replace('`', "'")
                                self.section_widget_list[section_widget_id].set_text_from_id(text_sub_id, text_loaded)

                except UnicodeDecodeError as e:
                    print(e)
                    message_box = QMessageBox()
                    message_box.setText("Wrong <b>encoding</b>, please use <b>UTF8</b> formating only.<br>"
                                        "In excel, you can go to the \"Data tab\", \"Import text file\" and choose UTF8 encoding")
                    message_box.setIcon(QMessageBox.Icon.Critical)
                    message_box.setWindowTitle("ShumiTranslator - Wrong CSV encoding")
                    message_box.setWindowIcon(self.__shumi_icon)
                    message_box.exec()

        self.scroll_area.setEnabled(True)

    def __save_csv(self):
        os.makedirs(self.CSV_FOLDER, exist_ok=True)
        if self.file_type_selection_widget.currentIndex() == 4:
            if self.file_loaded == 1:
                csv_name = pathlib.Path(self.file_loaded[0]).name
            else:
                csv_name = "c0mxx.dat"
        else:
            csv_name = pathlib.Path(self.file_loaded).name
        csv_name = csv_name.split('.')[0] + '.csv'
        default_file_name = os.path.join(self.CSV_FOLDER, csv_name)
        file_to_save = self.csv_save_dialog.getSaveFileName(parent=self, caption="Find csv file", filter="*.csv", directory=default_file_name)[0]

        if file_to_save:
            if self.file_loaded_type == FileType.FIELD_FS:
                self.scroll_area.setEnabled(False)
                self.csv_upload_button.setEnabled(False)
                self.csv_save_button.setEnabled(False)
                self.field_fs_manager.save_csv(file_to_save)
            if self.file_loaded_type == FileType.WORLD_FS:
                self.scroll_area.setEnabled(False)
                self.csv_upload_button.setEnabled(False)
                self.csv_save_button.setEnabled(False)
                self.world_fs_manager.save_csv(file_to_save)
            else:
                with open(file_to_save, 'w', newline='', encoding="utf-8") as csv_file:
                    csv_writer = csv.writer(csv_file, delimiter=GameData.find_delimiter_from_csv_file(file_to_save), quotechar='§', quoting=csv.QUOTE_MINIMAL)
                    csv_writer.writerow(['Section data name', 'Section Widget id', 'Text Sub id', 'Text'])

                    for section_widget_id, section_widget in enumerate(self.section_widget_list):
                        for ff8_widget_id, ff8_text in enumerate(section_widget.section.get_text_list()):
                            csv_writer.writerow([section_widget.section.name, section_widget_id, ff8_widget_id, ff8_text.get_str().replace('\n', '\\n')])

        if self.file_loaded_type == FileType.FIELD_FS or self.file_loaded_type == FileType.WORLD_FS:
            self.scroll_area.setEnabled(True)
            self.csv_upload_button.setEnabled(True)
            self.csv_save_button.setEnabled(True)

    def __load_file(self, file_to_load: str = ""):
        print("Loading file")

        self.scroll_area.setEnabled(False)
        self.csv_upload_button.setEnabled(False)
        self.csv_save_button.setEnabled(False)
        self.compress_button.setEnabled(False)
        self.uncompress_button.setEnabled(False)
        self._tab_widget.hide()
        self.compress_button.hide()
        self.uncompress_button.hide()
        self.warning_kernel_label_widget.hide()
        self.warning_comx_label_widget.hide()
        self.warning_mngrp_label_widget.hide()
        self.warning_exe_label_widget.hide()
        self.warning_field_label_widget.hide()

        # file_to_load = [os.path.join("OriginalFiles", "battle", "c0m028.dat")]  # For developing faster
        #file_to_load = os.path.join("OriginalFiles", "kernel.bin")  # For developing faster
        # file_to_load = ['I:/Mod_FF8/Outils modding/Fichier de travail/GitProject/ShumiTranslator/OriginalFiles/c0m001.dat']  # For developing faster
        #file_to_load = [os.path.join("OriginalFiles", "c0m034.dat")]  # For developing faster
        if not file_to_load:
            filter_file = self.FILE_MANAGED_REGEX[self.file_type_selection_widget.currentIndex()]
            if self.file_type_selection_widget.currentIndex() == 4:  # c0mxx.dat
                file_to_load = self.file_dialog.getOpenFileNames(parent=self, caption="Find file", filter=filter_file, directory=os.getcwd())[0]
                new_file_to_load = []
                for file in file_to_load:
                    file_name = pathlib.Path(file).name.split('.')[0].split("m")[1]
                    if int(file_name) < 144 and int(file_name) != 127:  # Not Garbage data
                        new_file_to_load.append(file)
                file_to_load = new_file_to_load
            else:
                file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Find file", filter=filter_file, directory=os.getcwd())[0]

        if file_to_load:
            self.file_dialog_button.setEnabled(False)
            self.file_loaded = file_to_load
            if self.file_type_selection_widget.currentIndex() == 4:
                if len(self.file_loaded) == 1:
                    file_name = pathlib.Path(self.file_loaded[0]).name
                else:
                    file_name = self.FILE_MANAGED[self.file_type_selection_widget.currentIndex()]
            else:
                file_name = pathlib.Path(self.file_loaded).name
            self.text_file_loaded.setText("File loaded: " + file_name)

            for section_widget in self.section_widget_list:
                section_widget.setParent(None)
                section_widget.deleteLater()
            self.section_widget_list = []

            # Choose which manager to load
            if "kernel" in file_name and ".bin" in file_name:
                self.file_loaded_type = FileType.KERNEL
                self.kernel_manager.load_file(self.file_loaded)
                first_section_line_index = 2  # Start at 2 as in the CSV
                for section in self.kernel_manager.section_list:
                    if section.type == SectionType.FF8_TEXT:
                        self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                        self.layout_translation_lines.addWidget(self.section_widget_list[-1])
                        first_section_line_index += len(section.section_data_linked.get_all_offset())
                self.compress_button.setEnabled(True)
                self.uncompress_button.setEnabled(True)
                self.compress_button.show()
                self.uncompress_button.show()
                self.warning_kernel_label_widget.show()
            elif "namedic" in file_name and ".bin" in file_name:
                self.file_loaded_type = FileType.NAMEDIC
                self.namedic_manager.load_file(self.file_loaded)
                # Only one section
                first_section_line_index = 2  # Start at 2 as in the CSV
                self.section_widget_list.append(SectionWidget(self.namedic_manager.get_text_section(), first_section_line_index))
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])
            elif "mngrp" in file_name and ".bin" in file_name:
                self.file_loaded_type = FileType.MNGRP
                #self.file_mngrphd_loaded = os.path.join("OriginalFiles", "mngrphd.bin")  # For developing faster
                self.file_mngrphd_loaded = self.file_dialog.getOpenFileName(parent=self, caption="Find mngrphd", filter="*mngrphd*.bin",
                                                                           directory=os.getcwd())[0]

                if self.file_mngrphd_loaded:
                    self.mngrp_manager.load_file(self.file_mngrphd_loaded, self.file_loaded)
                    first_section_line_index = 2
                    for section in self.mngrp_manager.mngrp.get_section_list():
                        if section.type in (
                                SectionType.TKMNMES, SectionType.MNGRP_STRING, SectionType.FF8_TEXT, SectionType.MNGRP_TEXTBOX, SectionType.MNGRP_M00MSG):
                            if section.type == SectionType.MNGRP_STRING:
                                self.section_widget_list.append(SectionWidget(section.get_text_section(), first_section_line_index))
                                first_section_line_index += len(section.get_text_list())
                            elif section.type == SectionType.FF8_TEXT or section.type == SectionType.MNGRP_M00MSG:
                                self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                                first_section_line_index += len(section.get_text_list())
                            elif section.type == SectionType.TKMNMES:
                                for i in range(section.get_nb_text_section()):
                                    self.section_widget_list.append(SectionWidget(section.get_text_section_by_id(i), first_section_line_index))
                                    first_section_line_index += len(section.get_text_section_by_id(i).get_text_list())
                            elif section.type == SectionType.MNGRP_TEXTBOX:
                                self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                                first_section_line_index += len(section.get_text_list())
                        self.warning_mngrp_label_widget.show()

                for section_widget in self.section_widget_list:
                    self._tab_widget.add_section(section_widget)
                self._tab_widget.show()
            elif ".exe" in file_name:
                self.file_loaded_type = FileType.EXE
                data_hex_exe = bytearray()
                with open(self.file_loaded, "rb") as file:
                    data_hex_exe.extend(file.read())
                self.exe_manager.load_file(self.file_loaded)
                first_section_line_index = 2
                self.section_widget_list.append(SectionWidget(self.exe_manager.get_exe_section().get_section_draw_text().get_text_section(), first_section_line_index))
                first_section_line_index += len(self.exe_manager.get_exe_section().get_section_draw_text().get_text_section().get_text_list())
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])

                self.section_widget_list.append(SectionWidget(self.exe_manager.get_exe_section().get_section_card_misc_text().get_text_section(), first_section_line_index))
                first_section_line_index += len(self.exe_manager.get_exe_section().get_section_card_misc_text().get_text_section().get_text_list())
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])

                self.section_widget_list.append(SectionWidget(self.exe_manager.get_exe_section().get_section_card_name().get_text_section(), first_section_line_index))
                first_section_line_index += len(self.exe_manager.get_exe_section().get_section_card_name().get_text_section().get_text_list())
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])

                self.section_widget_list.append(SectionWidget(self.exe_manager.get_exe_section().get_section_scan_text().get_text_section(), first_section_line_index))
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])

                self.warning_exe_label_widget.show()
            elif ".dat" in file_name and "c0m" in file_name:
                self.warning_comx_label_widget.show()
                self.battle_manager.reset()
                self.file_loaded_type = FileType.DAT
                for file_to_load in self.file_loaded:
                    self.battle_manager.add_file(file_to_load)

                text_section_list = self.battle_manager.get_section_list()
                first_section_line_index = 2
                for section in text_section_list:
                    self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                    first_section_line_index += len(section.get_text_list())
                    self.layout_translation_lines.addWidget(self.section_widget_list[-1])
            elif ".dat" in file_name:  # Remaster file
                self.file_loaded_type = FileType.REMASTER_DAT
                if "off_cards_names" in file_name and "2" not in file_name:
                    type_to_load = RemasterCardType.CARD_NAME
                elif "off_cards_names" in file_name and "2" in file_name:
                    type_to_load = RemasterCardType.CARD_NAME2
                else:
                    print(f"Unexpected file name: {file_name}")
                    type_to_load = RemasterCardType.CARD_NAME

                self.remaster_dat_manager.load_file(file_to_load, type_to_load)
                first_section_line_index = 2
                self.section_widget_list.append(SectionWidget(self.remaster_dat_manager.get_section().get_text_section(), first_section_line_index))
                self.layout_translation_lines.addWidget(self.section_widget_list[-1])
            elif "field" in file_name and ".fs" in file_name:
                self.warning_field_label_widget.show()
                self.file_loaded_type = FileType.FIELD_FS
                self.field_fs_manager.load_file(self.file_loaded)
            elif "world" in file_name and ".fs" in file_name:
                self.warning_world_label_widget.show()
                self.file_loaded_type = FileType.WORLD_FS
                self.world_fs_manager.load_file(self.file_loaded)

            self.csv_save_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.csv_upload_button.setEnabled(True)
            self.file_dialog_button.setEnabled(True)

            self.text_file_loaded.show()

        self.scroll_area.setEnabled(True)

    def __disable_all(self):
        self.csv_save_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.csv_upload_button.setEnabled(False)
        self.compress_button.setEnabled(False)
        self.uncompress_button.setEnabled(False)
        self.scroll_area.setEnabled(False)

    def __enable_all(self):
        self.csv_save_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.csv_upload_button.setEnabled(True)
        self.compress_button.setEnabled(True)
        self.uncompress_button.setEnabled(True)
        self.scroll_area.setEnabled(True)
