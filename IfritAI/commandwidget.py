from PyQt6.QtCore import QObject, pyqtSignal, QSignalBlocker
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSpinBox, QFrame, QSizePolicy, QLabel, QComboBox

from command import Command


class OpIdChangedEmmiter(QObject):
    op_id_signal = pyqtSignal()


class CommandWidget(QWidget):
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MIN_OP_ID = 0
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, command: Command):
        QWidget.__init__(self)

        # Parameters
        self.command = command
        self.expert_chosen = False

        # signal
        self.op_id_changed_signal_emitter = OpIdChangedEmmiter()

        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        # op_id widget
        self.op_id_widget = QSpinBox()


        # Line for cool gui
        frame = QFrame()
        frame.setFrameStyle(0x05)
        frame.setLineWidth(2)
        self.layout_id = QHBoxLayout()
        self.layout_id.addWidget(self.op_id_widget)
        self.layout_id.addWidget(frame)

        self.__reset_op_id_widget()

        # Create the op_code widgets
        self.layout_op_code = QHBoxLayout()
        self.widget_op_code = []
        self.__reset_op_code_widget()

        # And the cool line with it
        self.frame_text = QFrame()
        self.frame_text.setFrameStyle(0x05)
        self.frame_text.setLineWidth(2)

        # Now the text
        self.layout_text = QHBoxLayout()
        self.widget_text = QLabel(command.get_text())
        self.layout_text_spacing = QHBoxLayout()
        self.layout_text.addLayout(self.layout_text_spacing)
        self.layout_text.addWidget(self.widget_text)

        self.layout_stretch = QHBoxLayout()
        self.layout_stretch.addStretch(1)

        self.main_layout.addLayout(self.layout_id)
        self.main_layout.addLayout(self.layout_op_code)
        self.main_layout.addWidget(self.frame_text)
        self.main_layout.addLayout(self.layout_text)
        self.main_layout.addLayout(self.layout_stretch)

    def set_text(self):
        self.widget_text.setText(self.command.get_text())

    def set_if_index(self, if_index):
        self.command.set_if_index(if_index)
        self.layout_text_spacing.takeAt(0)
        self.layout_text_spacing.addSpacing(if_index * 20)

    def change_expert(self, expert_chosen):
        self.expert_chosen = expert_chosen
        self.__reset_op_id_widget()
        self.__reset_op_code_widget()

    def __op_id_change(self):
        if self.expert_chosen:
            self.command.set_op_id(self.op_id_widget.value())
        else:
            dict_data = [x["id"] for x in self.command.id_possible_list if x["data"] == self.op_id_widget.currentText()]
            if dict_data:
                self.command.set_op_id(dict_data[0])
            else:
                print("No data found for value: {}".format(self.op_id_widget.currentText()))
        self.__reset_op_code_widget()
        self.widget_text.setText(self.command.get_text())
        self.op_id_changed_signal_emitter.op_id_signal.emit()

    def __op_code_change(self):
        op_code = []

        for i in range(0, len(self.command.get_op_code())):
            try:
                op_code.append(self.widget_op_code[i].value())
            except AttributeError:
                op_code.append([x['id'] for x in self.command.param_possible_list[i] if
                                x['data'] == self.widget_op_code[i].currentText()][0])
            except:
                print("Unexpected widget with type: {}".format(type(self.widget_op_code[i])))
        self.command.set_op_code(op_code)
        self.widget_text.setText(self.command.get_text())
        if self.command.get_id() == 2:  # If an if, reset the left condition as it can change of type
            self.__reset_op_code_widget((1,))

    def __reset_op_id_widget(self):
        self.op_id_widget.setParent(None)
        self.op_id_widget.deleteLater()
        if not self.expert_chosen and self.command.id_possible_list:
            self.op_id_widget = QComboBox()
            self.op_id_widget.addItems([x['data'] for x in self.command.id_possible_list])
            self.op_id_widget.setFixedSize(80, 30)

            op_line_data = [x['short_text'] for x in self.command.game_data.ai_data_json['op_code_info'] if x["op_code"] == self.command.get_id()]
            if op_line_data:
                self.op_id_widget.setCurrentText(op_line_data[0])
            else:
                print("Id not found: {}".format(self.command.get_id()))
            self.op_id_widget.view().setMinimumWidth(self.__get_largest_size_from_combobox(self.op_id_widget) + 40)
            self.op_id_widget.currentIndexChanged.connect(self.__op_id_change)
            self.op_id_widget.wheelEvent = lambda event: None
        else:
            self.op_id_widget = QSpinBox()
            self.op_id_widget.setFixedSize(50, 30)
            self.op_id_widget.setValue(self.command.get_id())
            self.op_id_widget.setMaximum(self.MAX_OP_ID)
            self.op_id_widget.setMinimum(self.MIN_OP_ID)
            self.op_id_widget.valueChanged.connect(self.__op_id_change)
            self.op_id_widget.wheelEvent = lambda event: None

        self.layout_id.insertWidget(0, self.op_id_widget)

    def __reset_op_code_widget(self, list_to_reset=()):
        if not list_to_reset:
            list_to_reset = range(self.MAX_COMMAND_PARAM)
        for i in list_to_reset:
            if i < len(self.widget_op_code):
                self.widget_op_code[i].setParent(None)
                self.widget_op_code[i].deleteLater()
                del self.widget_op_code[i]
            if not self.expert_chosen and self.command.param_possible_list and len(
                    self.command.param_possible_list) > i and self.command.param_possible_list[i]:
                self.widget_op_code.insert(i, QComboBox())
                items = []
                current_text = ""
                for el in self.command.param_possible_list[i]:
                    if i < len(self.command.get_op_code()) and el['id'] == self.command.get_op_code()[i]:
                        current_text = el['data']
                    items.append(el["data"])
                self.widget_op_code[i].addItems(items)
                self.widget_op_code[i].setCurrentText(current_text)
                self.widget_op_code[i].view().setMinimumWidth(self.__get_largest_size_from_combobox(self.widget_op_code[i]) + 40)
                self.widget_op_code[i].setFixedSize(80, 30)
                self.widget_op_code[i].currentIndexChanged.connect(self.__op_code_change)
                self.widget_op_code[i].wheelEvent = lambda event: None
            else:
                self.widget_op_code.insert(i, QSpinBox())
                self.widget_op_code[i].setFixedSize(50, 30)
                self.widget_op_code[i].setMaximum(self.MAX_OP_CODE_VALUE)
                self.widget_op_code[i].setMinimum(self.MIN_OP_CODE_VALUE)
                self.widget_op_code[i].wheelEvent = lambda event: None

                if i < len(self.command.get_op_code()):
                    self.widget_op_code[i].setValue(self.command.get_op_code()[i])
                else:
                    self.widget_op_code[i].setValue(0)
                self.widget_op_code[i].valueChanged.connect(self.__op_code_change)
            if i > 5:  # Only if has more than 5 parameters
                self.widget_op_code[i].setFixedSize(50, 30)
            elif self.expert_chosen:
                self.widget_op_code[i].setFixedSize(50, 30)
            else:
                self.widget_op_code[i].setFixedSize(80, 30)
            if i >= len(self.command.get_op_code()):
                retain_policy = QSizePolicy()
                retain_policy.setRetainSizeWhenHidden(True)
                self.widget_op_code[i].setSizePolicy(retain_policy)
                self.widget_op_code[i].hide()

            self.layout_op_code.insertWidget(i, self.widget_op_code[i])

    def __get_largest_size_from_combobox(self, combo_box: QComboBox):
        largest = 0
        for i in range(combo_box.count()):
            if QLabel(combo_box.itemText(i)).fontMetrics().boundingRect(combo_box.itemText(i)).width() > largest:
                largest = QLabel(combo_box.itemText(i)).fontMetrics().boundingRect(combo_box.itemText(i)).width()
        return largest
