import os
import pathlib
import re
from email.policy import default
from typing import List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog, QComboBox, QHBoxLayout, QLabel, \
    QColorDialog, QCheckBox, QMessageBox

from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from IfritAI.codeanalyser import CodeAnalyser
from IfritAI.codewidget import CodeWidget

from IfritAI.commandwidget import CommandWidget
from IfritAI.ifritmanager import IfritManager
from IfritSeq.seqwidget import SeqWidget
from IfritXlsx.ifritxlsxmanager import IfritXlsxManager
from bs4 import BeautifulSoup

class IfritSeqWidget(QWidget):
    ADD_LINE_SELECTOR_ITEMS = ["Condition", "Command"]
    EXPERT_SELECTOR_ITEMS = ["User-friendly", "Hex-editor", "Raw-code", "IfritAI-code"]
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, icon_path="Resources",game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.current_if_index = 0
        self.file_loaded = ""
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        self.ifrit_manager = IfritManager(game_data_folder)
        self.current_if_type = CurrentIfType.NONE
        # Main window
        self.setWindowTitle("IfritAI")
        #self.setMinimumSize(1280, 600)
        self.setMinimumHeight(600)
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'icon.ico'))
        self.setWindowIcon(self.__ifrit_icon)
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.clicked.connect(self.__save_file)
        self.layout_main = QVBoxLayout()
        self.save_button.setToolTip("Save all modification in the .dat (irreversible)")

        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.file_dialog_button.setIconSize(QSize(30, 30))
        self.file_dialog_button.setFixedSize(40, 40)
        self.file_dialog_button.clicked.connect(self.__load_file)
        self.file_dialog_button.setToolTip("Open a .dat file")

        self.reset_button = QPushButton()
        self.reset_button.setIcon(QIcon(os.path.join(icon_path, 'reset.png')))
        self.reset_button.setIconSize(QSize(30, 30))
        self.reset_button.setFixedSize(40, 40)
        self.reset_button.clicked.connect(self.__reload_file)
        self.reset_button.setToolTip("Reload the file. /!\\ This will delete any local unsaved change made")

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        # self.info_button.setIconSize(QSize(40, 40))
        self.info_button.setIconSize(QSize(30, 30))
        self.info_button.setFixedSize(40, 40)
        self.info_button.setToolTip("Show toolmaker info")
        self.info_button.clicked.connect(self.__show_info)

        self.seq_data_widget= []
        self.monster_name_label = QLabel()
        self.monster_name_label.hide()

        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self.file_dialog_button)
        self.layout_top.addWidget(self.save_button)
        self.layout_top.addWidget(self.reset_button)
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addWidget(self.monster_name_label)
        self.layout_top.addStretch(1)


        # The main horizontal will be for code expert, when ai layout will be for others

        self.main_vertical_layout = QVBoxLayout()

        self.window_layout.addLayout(self.layout_top)
        self.window_layout.addWidget(self.scroll_area)
        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.main_vertical_layout)

        #self.show()

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Nihil</b> for beta testing and finding unknown values.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.<br/>"
                            f"For more info on the command, you can check the <a href=\"https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/battle/battle-scripts/\">wiki</a>.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__ifrit_icon)
        message_box.setWindowTitle("IfritAI - Info")
        message_box.exec()


    def __save_file(self):
        self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = []
        for index, seq_widget in enumerate(self.seq_data_widget):
            self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'].append(seq_widget.getByteData())
        self.ifrit_manager.save_file(self.file_loaded)
        print("File saved")

    def __load_file(self, file_to_load: str = ""):
        #file_to_load = os.path.join("c0m028.dat")  # For developing faster
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat")[0]
        if file_to_load:
            #self.__clear_lines(delete_data=True)
            self.ifrit_manager.init_from_file(file_to_load)
            self.monster_name_label.setText(
                "Monster : {}, file: {}".format(self.ifrit_manager.enemy.info_stat_data['monster_name'].get_str(),
                                                pathlib.Path(file_to_load).name))
            self.monster_name_label.show()
            self.file_loaded = file_to_load
            self.clear_lines()
            self.__setup_section_data()

    def __reload_file(self):
        self.clear_lines()

        self.__load_file(self.file_loaded)

    def clear_lines(self):
        for index_to_remove in range(len(self.seq_data_widget)):
            self.seq_data_widget[index_to_remove].deleteLater()
            self.seq_data_widget[index_to_remove].setParent(None)
            self.main_vertical_layout.takeAt(index_to_remove)
        self.seq_data_widget= []

    def __setup_section_data(self):
        for index, seq_data in enumerate(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data']):
            self.seq_data_widget.append(SeqWidget(seq_data, index))
        for index, seq_widget in enumerate( self.seq_data_widget):
            self.main_vertical_layout.addWidget(seq_widget)

