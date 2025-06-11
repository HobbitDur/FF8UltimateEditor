import os
import pathlib
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog, QComboBox, QHBoxLayout, QLabel, \
    QColorDialog, QCheckBox, QMessageBox

from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from codewidget import CodeWidget
from commandwidget import CommandWidget
from ifritmanager import IfritManager


class IfritAIWidget(QWidget):
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
        self.window_layout.addWidget(self.scroll_area)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        self.ifrit_manager = IfritManager(game_data_folder)
        self.current_if_type = CurrentIfType.NONE
        # Main window
        self.setWindowTitle("IfritAI")
        self.setMinimumSize(1280, 720)
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'icon.ico'))
        self.setWindowIcon(self.__ifrit_icon)
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setFixedSize(30, 30)
        self.save_button.clicked.connect(self.__save_file)
        self.layout_main = QVBoxLayout()
        self.save_button.setToolTip("Save all modification in the .dat (irreversible)")

        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.file_dialog_button.setFixedSize(30, 30)
        self.file_dialog_button.clicked.connect(self.__load_file)
        self.file_dialog_button.setToolTip("Open a .dat file")

        self.reset_button = QPushButton()
        self.reset_button.setIcon(QIcon(os.path.join(icon_path, 'reset.png')))
        self.reset_button.setFixedSize(30, 30)
        self.reset_button.clicked.connect(self.__reload_file)
        self.reset_button.setToolTip("Reload the file. /!\\ This will delete any local unsaved change made")

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        # self.info_button.setIconSize(QSize(30, 30))
        self.info_button.setFixedSize(30, 30)
        self.info_button.setToolTip("Show toolmaker info")
        self.info_button.clicked.connect(self.__show_info)

        self.script_section = QComboBox()
        self.script_section.addItems(self.ifrit_manager.game_data.AIData.AI_SECTION_LIST)
        self.script_section.setCurrentIndex(1)
        self.script_section.activated.connect(self.__section_change)
        self.script_section.setToolTip("Enemy AI as 5 section, you can choose which one you want to edit there")

        self.button_color_picker = QPushButton()
        self.button_color_picker.setText('Color')
        self.button_color_picker.setFixedSize(35, 30)
        self.button_color_picker.clicked.connect(self.__select_color)
        self.button_color_picker.setToolTip("To choose which color to highlight the variable")

        expert_tooltip_text = "IfritAI offer 4 different mod of editing:<br/>" + \
                              self.EXPERT_SELECTOR_ITEMS[0] + ": For modifying having a set of expected value<br/>" + \
                              self.EXPERT_SELECTOR_ITEMS[1] + ": For modifying directly the hex<br/>" + \
                              self.EXPERT_SELECTOR_ITEMS[2] + ": For getting raw function with list of value<br/>" + \
                              self.EXPERT_SELECTOR_ITEMS[3] + ": AI editor with IfritAI language."
        self.expert_selector_title = QLabel("Expert mode: ")
        self.expert_selector_title.setToolTip(expert_tooltip_text)
        self.expert_selector = QComboBox()
        self.expert_selector.addItems(self.EXPERT_SELECTOR_ITEMS)
        self.expert_selector.setCurrentIndex(3)
        self.expert_selector.activated.connect(self.__change_expert)

        self.expert_layout = QHBoxLayout()
        self.expert_layout.addWidget(self.expert_selector_title)
        self.expert_layout.addWidget(self.expert_selector)
        self.expert_selector.setToolTip(expert_tooltip_text)

        self.hex_selector = QCheckBox()
        self.hex_selector.setChecked(False)
        self.hex_selector.setText("Hex value")
        self.hex_selector.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.hex_selector.toggled.connect(self.__change_hex)
        self.hex_selector.setToolTip("Change all int value to hex value. Doesn't work on IfritAI code")

        self.monster_name_label = QLabel()
        self.monster_name_label.hide()

        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self.file_dialog_button)
        self.layout_top.addWidget(self.save_button)
        self.layout_top.addWidget(self.reset_button)
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addWidget(self.button_color_picker)
        self.layout_top.addLayout(self.expert_layout)
        self.layout_top.addWidget(self.hex_selector)
        self.layout_top.addWidget(self.script_section)
        self.layout_top.addWidget(self.monster_name_label)
        self.layout_top.addStretch(1)

        self.code_widget = CodeWidget(self.ifrit_manager.game_data, ennemy_data=self.ifrit_manager.ennemy, expert_level=self.expert_selector.currentIndex(),
                                      code_changed_hook=self.code_expert_changed_hook)
        self.code_widget.hide()

        self.main_horizontal_layout = QHBoxLayout()
        self.main_horizontal_layout.addWidget(self.code_widget)

        # The main horizontal will be for code expert, when ai layout will be for others

        self.ai_layout = QVBoxLayout()
        self.main_horizontal_layout.addLayout(self.ai_layout)
        self.ai_layout.addLayout(QHBoxLayout())
        self.ai_layout.addStretch(1)
        self.command_line_widget = []
        self.ai_line_layout = []
        self.add_button_widget = []
        self.remove_button_widget = []

        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.layout_top)
        self.layout_main.addLayout(self.main_horizontal_layout)

        self.show()

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Nihil</b> for beta testing and finding unknown values.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__ifrit_icon)
        message_box.setWindowTitle("IfritAI - Info")
        message_box.exec()

    def code_expert_changed_hook(self, command_list: List[CommandAnalyser]):
        command_list_from_widget = [command_widget.get_command() for command_widget in self.command_line_widget]
        for command in command_list_from_widget:
            self.__remove_line(command, delete_data=True)
        for command in command_list:
            self.__append_line(new_command=command, create_data=True)
        self.__hide_show_expert()

    def __hide_show_expert(self):
        expert_chosen = self.expert_selector.currentIndex()
        if expert_chosen == 2 or expert_chosen == 3:  # Expert mode
            self.code_widget.show()
            for i in range(len(self.add_button_widget)):
                self.add_button_widget[i].hide()
            for i in range(len(self.remove_button_widget)):
                self.remove_button_widget[i].hide()
        else:
            self.code_widget.hide()
            for i in range(len(self.add_button_widget)):
                self.add_button_widget[i].show()
            for i in range(len(self.remove_button_widget)):
                self.remove_button_widget[i].show()

    def __change_expert(self):
        expert_chosen = self.expert_selector.currentIndex()
        for line in self.command_line_widget:
            line.change_expert(expert_chosen)
        self.__hide_show_expert()
        self._set_text_expert()

    def _set_text_expert(self):
        expert_chosen = self.expert_selector.currentIndex()
        command_list = [command_widget.get_command() for command_widget in self.command_line_widget]
        if expert_chosen == 2:  # Raw data
            self.code_widget.set_text_from_command(command_list)
        elif expert_chosen == 3:  # IfritAI language
            self.code_widget.set_ifrit_ai_code_from_command(command_list)
        if expert_chosen in (2, 3):
            self.code_widget.change_expert_level(expert_chosen)

    def __change_hex(self):
        hex_chosen = self.hex_selector.isChecked()
        self.code_widget.change_hex(hex_chosen)
        for line in self.command_line_widget:
            line.change_print_hex(hex_chosen)

    def __select_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.ifrit_manager.game_data.color = color.name()
            for command_widget in self.command_line_widget:
                command_widget.get_command().set_color(color.name())
                command_widget.set_text()


    def __save_file(self):
        self.ifrit_manager.save_file(self.file_loaded)
        self.__section_change()
        print("File saved")

    def __section_change(self):
        self.__clear_lines(delete_data=False)
        self.__setup_section_data()

    def __append_line(self, new_command: CommandAnalyser = None, create_data=True):
        if not new_command:
            new_command = CommandAnalyser(0, [], self.ifrit_manager.game_data, info_stat_data=self.ifrit_manager.ennemy.info_stat_data,
                                          battle_text=self.ifrit_manager.ennemy.battle_script_data['battle_text'], line_index=len(self.command_line_widget),current_if_type=self.current_if_type)
            self.current_if_type = new_command.get_current_if_type()
        if create_data:
            self.ifrit_manager.ennemy.insert_command(self.script_section.currentIndex(), new_command, len(self.command_line_widget))

        self.__add_line(new_command)
        self.__compute_if()

    def __insert_line(self, current_line_command: CommandAnalyser = None, new_command: CommandAnalyser = None, create_data=True):
        # As we are inserting, moving all lines by 1
        if current_line_command:
            index_insert = current_line_command.line_index
            for index, command_widget in enumerate(self.command_line_widget):
                if command_widget.get_command().line_index >= current_line_command.line_index:
                    command_widget.get_command().line_index += 1
        else:
            index_insert = 0

        if not new_command: # Shouldn't need the current if type
            new_command = CommandAnalyser(0, [], self.ifrit_manager.game_data, info_stat_data=self.ifrit_manager.ennemy.info_stat_data,
                                          battle_text=self.ifrit_manager.ennemy.battle_script_data['battle_text'], line_index=index_insert)

        if create_data:
            self.ifrit_manager.ennemy.insert_command(self.script_section.currentIndex(), new_command, index_insert)

        self.__add_line(new_command)
        self.__compute_if()

    def __add_line(self, command: CommandAnalyser):
        # Add the + button
        add_button = QPushButton()
        add_button.setText("+")
        add_button.setFixedSize(30, 30)
        add_button.clicked.connect(lambda: self.__insert_line(command, create_data=True))
        remove_button = QPushButton()
        remove_button.setText("-")
        remove_button.setFixedSize(30, 30)
        remove_button.clicked.connect(lambda: self.__remove_line(command, delete_data=True))
        # Creating new element to list
        self.add_button_widget.insert(command.line_index, add_button)
        self.remove_button_widget.insert(command.line_index, remove_button)
        command_widget = CommandWidget(command, self.expert_selector.currentIndex(), self.hex_selector.isChecked())
        command_widget.op_id_changed_signal_emitter.op_id_signal.connect(self.__compute_if)
        self.command_line_widget.insert(command.line_index, command_widget)

        # Adding widget to layout
        self.ai_line_layout.insert(command.line_index, QHBoxLayout())
        self.ai_line_layout[command.line_index].addWidget(self.add_button_widget[command.line_index])
        self.ai_line_layout[command.line_index].addWidget(self.remove_button_widget[command.line_index])
        self.ai_line_layout[command.line_index].addWidget(self.command_line_widget[command.line_index])
        # Adding to the "main" layout
        self.ai_layout.insertLayout(command.line_index, self.ai_line_layout[command.line_index])

    def __pop_command_widget(self, delete_data=True):
        self.__remove_line(self.command_line_widget[-1].command, delete_data=delete_data)

    def __remove_line(self, command, delete_data=True):
        # Removing the widget
        index_to_remove = -1
        # Updating the line index of all command widget
        for index, command_widget in enumerate(self.command_line_widget):
            if command_widget.get_command().line_index == command.line_index:
                index_to_remove = index
            elif command_widget.get_command().line_index > command.line_index:
                command_widget.get_command().line_index -= 1
        if delete_data:
            self.ifrit_manager.ennemy.remove_command(self.script_section.currentIndex(), index_to_remove)

        self.add_button_widget[index_to_remove].deleteLater()
        self.add_button_widget[index_to_remove].setParent(None)
        self.remove_button_widget[index_to_remove].deleteLater()
        self.remove_button_widget[index_to_remove].setParent(None)
        self.command_line_widget[index_to_remove].deleteLater()
        self.command_line_widget[index_to_remove].setParent(None)
        # Deleting element from list
        del self.add_button_widget[index_to_remove]
        del self.remove_button_widget[index_to_remove]
        del self.command_line_widget[index_to_remove]
        del self.ai_line_layout[index_to_remove]
        self.ai_layout.takeAt(index_to_remove)

        self.__compute_if()

    def __clear_layout_except_item(self, layout):
        if layout:
            for i in reversed(range(layout.count())):
                item = layout.takeAt(i)
                widget = item.widget()
                sub_layout = item.layout()
                if sub_layout:
                    self.__clear_layout_except_item(sub_layout)
                    layout.removeItem(sub_layout)
                elif widget:
                    widget.setParent(None)
                    widget.deleteLater()

    def __compute_if(self):
        array_sorted = self.qsort_command_widget(self.command_line_widget)
        if_index = 0
        for command_widget in array_sorted:
            if command_widget.get_command().get_id() == 35:
                if command_widget.get_command().get_op_code()[0] == 0 or command_widget.get_command().get_op_code()[0] == 3:
                    if_index -= 1
            command_widget.set_if_index(if_index)
            if command_widget.get_command().get_id() == 2:
                if_index += 1

    def __reset_if(self):
        for command_widget in self.command_line_widget:
            command_widget.set_if_index(0)

    def qsort_command_widget(self, inlist: [CommandWidget]):
        if inlist == []:
            return []
        else:
            pivot = inlist[0]
            lesser = self.qsort_command_widget(
                [x for x in inlist[1:] if x.get_command().line_index < pivot.get_command().line_index])
            greater = self.qsort_command_widget(
                [x for x in inlist[1:] if x.get_command().line_index >= pivot.get_command().line_index])
            return lesser + [pivot] + greater

    def __load_file(self, file_to_load: str = ""):
        # file_to_load = os.path.join("OriginalFiles", "c0m065.dat")  # For developing faster
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat",
                                                            directory=os.getcwd())[0]
        if file_to_load:
            self.__clear_lines(delete_data=True)
            self.ifrit_manager.init_from_file(file_to_load)
            self.monster_name_label.setText(
                "Monster : {}, file: {}".format(self.ifrit_manager.ennemy.info_stat_data['monster_name'].get_str(),
                                                pathlib.Path(file_to_load).name))
            self.monster_name_label.show()
            self.file_loaded = file_to_load
            self.__setup_section_data()

    def __reload_file(self):
        self.__load_file(self.file_loaded)

    def __clear_lines(self, delete_data=False):
        command_list = [x.get_command() for x in self.command_line_widget]
        for command in command_list:
            self.__remove_line(command, delete_data)

    def __setup_section_data(self):
        line_index = 0
        index_section = self.ifrit_manager.game_data.AIData.AI_SECTION_LIST.index(self.script_section.currentText())
        if self.ifrit_manager.ai_data:
            for command in self.ifrit_manager.ai_data[index_section]:
                command.line_index = line_index
                command.set_color(self.ifrit_manager.game_data.AIData.COLOR)
                self.__append_line(command, create_data=False)
                line_index += 1
        self._set_text_expert()
        self.__hide_show_expert()
        self.__compute_if()

    def __set_title(self):
        font = QFont()
        font.setBold(True)
        label = QLabel("Command ID")
        label.setFont(font)
        self.layout_title.addWidget(label)
        label = QLabel("Op code")
        label.setFont(font)
        self.layout_title.addWidget(label)
        label = QLabel("Text")
        label.setFont(font)
        self.layout_title.addWidget(label)
