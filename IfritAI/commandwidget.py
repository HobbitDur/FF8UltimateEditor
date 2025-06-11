from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSpinBox, QFrame, QSizePolicy, QLabel, QComboBox

from FF8GameData.dat.commandanalyser import CommandAnalyser
from qspinhex import QSpinHex


class OpIdChangedEmitter(QObject):
    op_id_signal = pyqtSignal()


class CommandWidget(QWidget):
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MIN_OP_ID = 0
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, command: CommandAnalyser, expert_chosen=0, print_hex=False):
        QWidget.__init__(self)
        # Parameters
        self._command = command
        self._expert_chosen = expert_chosen
        self._print_hex = print_hex

        # signal
        self.op_id_changed_signal_emitter = OpIdChangedEmitter()

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
        self.widget_text = QLabel(command.get_text(html=True))
        self.widget_text.setTextFormat(Qt.TextFormat.RichText)
        self.layout_text_spacing = QHBoxLayout()
        self.layout_text.addLayout(self.layout_text_spacing)
        self.layout_text.addWidget(self.widget_text)

        self.main_layout.addLayout(self.layout_id)
        self.main_layout.addLayout(self.layout_op_code)
        self.main_layout.addWidget(self.frame_text)
        self.main_layout.addLayout(self.layout_text)

        self.__hide_show_expert()

    def get_command(self):
        return self._command

    def set_command(self, command):
        self._command = command
        self.__reset_op_id_widget()
        self.__reset_op_code_widget()

    def set_text(self):
        self.widget_text.setText(self._command.get_text(html=True))

    def set_if_index(self, if_index):
        self._command.set_if_index(if_index)
        self.layout_text_spacing.takeAt(0)
        self.layout_text_spacing.addSpacing(if_index * 20)

    def change_expert(self, expert_chosen):
        self._expert_chosen = expert_chosen
        self.__reset_op_id_widget()
        self.__reset_op_code_widget()
        self.__hide_show_expert()

    def __hide_show_expert(self):
        if self._expert_chosen == 2 or self._expert_chosen == 3:
            for i in range(len(self.widget_op_code)):
                self.widget_op_code[i].hide()
                if i >= len(self._command.get_op_code()):
                    retain_policy = QSizePolicy()
                    retain_policy.setRetainSizeWhenHidden(False)
                    self.widget_op_code[i].setSizePolicy(retain_policy)
            self.op_id_widget.hide()
            self.frame_text.hide()
        else:
            self.frame_text.show()

    def change_print_hex(self, print_hex):
        self._print_hex = print_hex
        self.__reset_op_id_widget()
        self.__reset_op_code_widget()
        self.__hide_show_expert()

    def __op_id_change(self):
        if self._expert_chosen:
            self._command.set_op_id(self.op_id_widget.value())
        else:
            dict_data = [x["id"] for x in self._command.id_possible_list if x["data"] == self.op_id_widget.currentText()]
            if dict_data:
                self._command.set_op_id(dict_data[0])
            else:
                print("No data found for value: {}".format(self.op_id_widget.currentText()))
        self.__reset_op_code_widget()
        self.widget_text.setText(self._command.get_text(html=True))
        self.op_id_changed_signal_emitter.op_id_signal.emit()

    def __op_code_change(self):
        op_code = []

        for i in range(0, len(self._command.get_op_code())):
            try:
                op_code.append(self.widget_op_code[i].value())
            except AttributeError:
                op_code.append([x['id'] for x in self._command.param_possible_list[i] if
                                x['data'] == self.widget_op_code[i].currentText()][0])
            except:
                print("Unexpected widget with type: {}".format(type(self.widget_op_code[i])))
        self._command.set_op_code(op_code)
        self.widget_text.setText(self._command.get_text(html=True))
        self.__reset_op_code_widget()

    def __reset_op_id_widget(self):
        self.op_id_widget.setParent(None)
        self.op_id_widget.deleteLater()
        if self._expert_chosen != 1 and self._command.id_possible_list:
            self.op_id_widget = QComboBox()
            self.op_id_widget.addItems([x['data'] for x in self._command.id_possible_list])
            self.op_id_widget.setFixedSize(80, 30)

            op_line_data = [x['short_text'] for x in self._command.game_data.ai_data_json['op_code_info'] if x["op_code"] == self._command.get_id()]
            if op_line_data:
                self.op_id_widget.setCurrentText(op_line_data[0])
            else:
                print("Id not found: {}".format(self._command.get_id()))
            self.op_id_widget.view().setMinimumWidth(self.__get_largest_size_from_combobox(self.op_id_widget) + 40)
            self.op_id_widget.currentIndexChanged.connect(self.__op_id_change)
            self.op_id_widget.wheelEvent = lambda event: None
        else:
            if self._print_hex:
                self.op_id_widget = QSpinHex()
            else:
                self.op_id_widget = QSpinBox()
            self.op_id_widget.setFixedSize(50, 30)
            self.op_id_widget.setMaximum(self.MAX_OP_ID)
            self.op_id_widget.setMinimum(self.MIN_OP_ID)

            self.op_id_widget.wheelEvent = lambda event: None
            self.op_id_widget.setValue(self._command.get_id())
            self.op_id_widget.valueChanged.connect(self.__op_id_change)

        self.layout_id.insertWidget(0, self.op_id_widget)

    def __reset_op_code_widget(self, list_to_reset=()):
        if not list_to_reset:
            list_to_reset = range(self.MAX_COMMAND_PARAM)
        for i in list_to_reset:
            if i < len(self.widget_op_code):
                self.widget_op_code[i].setParent(None)
                self.widget_op_code[i].deleteLater()
                del self.widget_op_code[i]
            if self._expert_chosen != 1 and self._command.param_possible_list and len(
                    self._command.param_possible_list) > i and self._command.param_possible_list[i]:
                self.widget_op_code.insert(i, QComboBox())
                items = []
                current_text = ""
                for el in self._command.param_possible_list[i]:
                    if i < len(self._command.get_op_code()) and el['id'] == self._command.get_op_code()[i]:
                        current_text = el['data']
                    items.append(el["data"])
                self.widget_op_code[i].addItems(items)
                self.widget_op_code[i].setCurrentText(current_text)
                self.widget_op_code[i].view().setMinimumWidth(self.__get_largest_size_from_combobox(self.widget_op_code[i]) + 40)
                self.widget_op_code[i].setFixedSize(80, 30)
                self.widget_op_code[i].currentIndexChanged.connect(self.__op_code_change)
                self.widget_op_code[i].wheelEvent = lambda event: None
            else:
                if self._print_hex:
                    self.widget_op_code.insert(i, QSpinHex())
                else:
                    self.widget_op_code.insert(i, QSpinBox())
                self.widget_op_code[i].setFixedSize(50, 30)
                self.widget_op_code[i].setMaximum(self.MAX_OP_CODE_VALUE)
                self.widget_op_code[i].setMinimum(self.MIN_OP_CODE_VALUE)
                self.widget_op_code[i].wheelEvent = lambda event: None
                self.widget_op_code[i].setKeyboardTracking(False)
                if i < len(self._command.get_op_code()):
                    self.widget_op_code[i].setValue(self._command.get_op_code()[i])
                else:
                    self.widget_op_code[i].setValue(0)
                self.widget_op_code[i].valueChanged.connect(self.__op_code_change)
            if i > 5:  # Only if has more than 5 parameters
                self.widget_op_code[i].setFixedSize(50, 30)
            elif self._expert_chosen:
                self.widget_op_code[i].setFixedSize(50, 30)
            else:
                self.widget_op_code[i].setFixedSize(80, 30)
            if i >= len(self._command.get_op_code()):
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
