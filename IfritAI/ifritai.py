import os
import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog, QComboBox, QHBoxLayout, QLabel, \
    QColorDialog, QCheckBox

from command import Command
from commandwidget import CommandWidget
from ifritmanager import IfritManager


class IfritAI(QWidget):
    ADD_LINE_SELECTOR_ITEMS = ["Condition", "Command"]
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, icon_path='Resources'):

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
        self.ifrit_manager = IfritManager()
        # Main window
        self.setWindowTitle("IfritAI")
        self.setMinimumSize(1280, 720)
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'icon.ico')))

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setFixedSize(30, 30)
        self.save_button.clicked.connect(self.__save_file)
        self.layout_main = QVBoxLayout()

        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.file_dialog_button.setFixedSize(30, 30)
        self.file_dialog_button.clicked.connect(self.__load_file)

        self.reset_button = QPushButton()
        self.reset_button.setIcon(QIcon(os.path.join(icon_path, 'reset.png')))
        self.reset_button.setFixedSize(30, 30)
        self.reset_button.clicked.connect(self.__reload_file)

        self.script_section = QComboBox()
        self.script_section.addItems(self.ifrit_manager.game_data.AI_SECTION_LIST)
        self.script_section.activated.connect(self.__section_change)

        self.button_color_picker = QPushButton()
        self.button_color_picker.setText('Color')
        self.button_color_picker.setFixedSize(35, 30)
        self.button_color_picker.clicked.connect(self.__select_color)


        self.expert_selector = QCheckBox()
        self.expert_selector.setChecked(False)
        self.expert_selector.setText("Expert mode")
        self.expert_selector.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.expert_selector.toggled.connect(self.__change_expert)

        self.monster_name_label = QLabel()
        self.monster_name_label.hide()


        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self.file_dialog_button)
        self.layout_top.addWidget(self.save_button)
        self.layout_top.addWidget(self.reset_button)
        self.layout_top.addWidget(self.button_color_picker)
        self.layout_top.addWidget(self.expert_selector)
        self.layout_top.addWidget(self.script_section)
        self.layout_top.addWidget(self.monster_name_label)
        self.layout_top.addStretch(1)

        self.ai_layout = QVBoxLayout()
        self.ai_layout.addStretch(1)
        self.command_line_widget = []
        self.ai_line_layout = []
        self.add_button_widget = []
        self.remove_button_widget = []

        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.layout_top)
        self.layout_main.addLayout(self.ai_layout)
        self.layout_main.addStretch(1)

        self.show()

    def __change_expert(self):
        expert_chosen = self.expert_selector.isChecked()
        for line in self.command_line_widget:
            line.change_expert(expert_chosen)

    def __select_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.ifrit_manager.game_data.color = color.name()
            for command_widget in self.command_line_widget:
                command_widget.command.set_color(color.name())
                command_widget.set_text()

    def __save_file(self):
        self.ifrit_manager.save_file(self.file_loaded)

    def __section_change(self):
        self.__clear__lines()
        self.__setup_section_data()

    def __insert_line(self, command: Command):
        index_insert = command.line_index
        for index, command_widget in enumerate(self.command_line_widget):
            if command_widget.command.line_index >= command.line_index:
                command_widget.command.line_index += 1
        self.__add_line(Command(0, [], self.ifrit_manager.game_data, line_index=index_insert), True)
        self.__compute_if()

    def __add_line(self, command: Command, insert=False):
        # Add the + button
        add_button = QPushButton()
        add_button.setText("+")
        add_button.setFixedSize(30, 30)
        add_button.clicked.connect(lambda: self.__insert_line(command))
        remove_button = QPushButton()
        remove_button.setText("-")
        remove_button.setFixedSize(30, 30)
        remove_button.clicked.connect(lambda: self.__remove_line(command))

        # Creating new element to list
        self.add_button_widget.insert(command.line_index, add_button)
        self.remove_button_widget.insert(command.line_index, remove_button)
        command_widget = CommandWidget(command)
        command_widget.op_id_changed_signal_emitter.op_id_signal.connect(self.__compute_if)
        self.command_line_widget.insert(command.line_index, command_widget)
        self.ai_line_layout.insert(command.line_index, QHBoxLayout())
        # Adding widget to layout
        self.ai_line_layout[command.line_index].addWidget(self.add_button_widget[command.line_index])
        self.ai_line_layout[command.line_index].addWidget(self.remove_button_widget[command.line_index])
        self.ai_line_layout[command.line_index].addWidget(self.command_line_widget[command.line_index])

        # Adding to the "main" layout
        self.ai_layout.insertLayout(command.line_index, self.ai_line_layout[command.line_index])

    def __remove_line(self, command):
        # Removing the widget
        index_to_remove = -1
        # Updating the line index of all command widget
        for index, command_widget in enumerate(self.command_line_widget):
            if command_widget.command.line_index == command.line_index:
                index_to_remove = index
            elif command_widget.command.line_index > command.line_index:
                command_widget.command.line_index -= 1

        self.add_button_widget[index_to_remove].setParent(None)
        self.add_button_widget[index_to_remove].deleteLater()
        self.remove_button_widget[index_to_remove].setParent(None)
        self.remove_button_widget[index_to_remove].deleteLater()
        self.command_line_widget[index_to_remove].setParent(None)
        self.command_line_widget[index_to_remove].deleteLater()
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
        array_sorted = self.command_line_widget
        array_sorted = self.qsort_command_widget(array_sorted)
        if_index = 0
        for command_widget in array_sorted:
            if command_widget.command.get_id() == 35:
                if command_widget.command.get_op_code()[0] == 0 or command_widget.command.get_op_code()[0] == 3:
                    if_index -= 1
            command_widget.set_if_index(if_index)
            if command_widget.command.get_id() == 2:
                if_index += 1

    def qsort_command_widget(self, inlist: [CommandWidget]):
        if inlist == []:
            return []
        else:
            pivot = inlist[0]
            lesser = self.qsort_command_widget(
                [x for x in inlist[1:] if x.command.line_index < pivot.command.line_index])
            greater = self.qsort_command_widget(
                [x for x in inlist[1:] if x.command.line_index >= pivot.command.line_index])
            return lesser + [pivot] + greater

    def __load_file(self, file_to_load: str = ""):
        #file_to_load = os.path.join("OriginalFiles", "c0m028.dat") # For developing faster
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat",
                                                            directory=os.getcwd())[0]
        if file_to_load:
            self.ifrit_manager.init_from_file(file_to_load)
            self.monster_name_label.setText(
                "Monster : {}, file: {}".format(self.ifrit_manager.ennemy.info_stat_data['monster_name'],
                                                pathlib.Path(file_to_load).name))
            self.monster_name_label.show()
            self.file_loaded = file_to_load
            self.__setup_section_data()

    def __reload_file(self):
        self.__clear__lines()
        self.__load_file(self.file_loaded)

    def __clear__lines(self):
        for i in range(len(self.add_button_widget)):
            self.add_button_widget[i].setParent(None)
            self.add_button_widget[i].deleteLater()
            self.remove_button_widget[i].setParent(None)
            self.remove_button_widget[i].deleteLater()
            self.command_line_widget[i].setParent(None)
            self.command_line_widget[i].deleteLater()
            self.ai_layout.takeAt(i)

        # Deleting element from list
        self.add_button_widget = []
        self.remove_button_widget = []
        self.command_line_widget = []
        self.ai_line_layout = []

    def __setup_section_data(self):
        line_index = 0
        index_section = self.ifrit_manager.game_data.AI_SECTION_LIST.index(self.script_section.currentText())
        if self.ifrit_manager.ai_data:
            for command in self.ifrit_manager.ai_data[index_section]:
                command.line_index = line_index
                command.set_color(self.ifrit_manager.game_data.color)
                self.__add_line(command)
                line_index += 1
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
