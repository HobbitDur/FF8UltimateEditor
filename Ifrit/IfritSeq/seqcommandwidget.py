"""One row of the IfritSeq command editor: a command as widgets instead of hex.

The row is a projection of a SequenceCommand: an op code dropdown (names from the VM's
json), one hex spinbox per parameter byte, and the live description shared with the analyser
(describe_command). Editing emits data_changed; the owning SeqWidget rebuilds the sequence
bytes through the one walker, so what the row shows is by construction what the engine will
read.

The row is VM-agnostic: it drives an entity animation sequence or a camera sequence
depending on the SequenceVM it is built with (op code set, whether a bare op code is an
animation, which op codes grow an FF-terminated list all come from the VM).
"""
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy

from FF8GameData.dat.sequenceanalyser import describe_command
from FF8GameData.dat.sequencecommand import (SequenceCommand, default_parameters,
                                             get_op_code_info, normalize_parameters)
from FF8GameData.dat.sequencevm import as_sequence_vm
from Ifrit.IfritAI.qspinhex import QSpinHex

# The dropdown entry every op code < the animation range shares: the op code IS the
# animation id, so the row shows one "Anim" entry plus an id spinbox instead of 128
# dropdown lines. Only used by VMs that have an animation range (the entity VM).
ANIM_COMBO_VALUE = -1


def build_op_code_model(game_data_or_vm) -> QStandardItemModel:
    """The op code dropdown content, built once and shared by every row.

    A file has hundreds of commands and each row carries this dropdown; sharing one model
    instead of re-filling each combo keeps the tab snappy. The op codes and their labels
    come from the VM's json, so the same builder serves the entity and camera editors.
    """
    vm = as_sequence_vm(game_data_or_vm)
    model = QStandardItemModel()
    if vm.animation_op_code_max > 0:
        # Entity VM: fold every op code < 0x80 into one "Anim" entry + an id spinbox.
        anim_item = QStandardItem("Anim")
        anim_item.setData(ANIM_COMBO_VALUE, Qt.ItemDataRole.UserRole)
        anim_item.setData("Play animation <id> and wait for it to end "
                          "(the op code byte IS the animation id)", Qt.ItemDataRole.ToolTipRole)
        model.appendRow(anim_item)
    for info in vm.data_json["op_code_info"]:
        # The shared 0x00 "play animation" entry is represented by the Anim row above on a
        # VM with an animation range; on the camera VM 0x00 is a real op code, keep it.
        if info['op_code'] == 0x00 and vm.animation_op_code_max > 0:
            continue
        item = QStandardItem(f"{info['op_code']:02X} {info.get('short_text', '')}")
        item.setData(info['op_code'], Qt.ItemDataRole.UserRole)
        item.setData(info['text'], Qt.ItemDataRole.ToolTipRole)
        model.appendRow(item)
    return model


class SeqCommandRow(QWidget):
    """One command of a sequence, editable without touching hex."""

    data_changed = pyqtSignal()
    insert_requested = pyqtSignal(object)  # self: insert a new command after this row
    remove_requested = pyqtSignal(object)  # self

    def __init__(self, game_data_or_vm, command: SequenceCommand, op_code_model=None):
        QWidget.__init__(self)
        self.vm = as_sequence_vm(game_data_or_vm)
        self.command = command
        self._updating = False

        self.address_label = QLabel()
        self.address_label.setFixedWidth(40)
        self.address_label.setToolTip("Offset of this command in the sequence")

        self.op_code_combo = QComboBox()
        self.op_code_combo.setModel(op_code_model if op_code_model is not None
                                    else build_op_code_model(self.vm))
        self.op_code_combo.currentIndexChanged.connect(self.__op_code_changed)
        self.op_code_combo.wheelEvent = lambda event: None

        self.param_widget_list = []
        self.param_layout = QHBoxLayout()
        self.param_layout.setSpacing(2)

        self.append_step_button = QPushButton("+step")
        self.append_step_button.setFixedSize(40, 22)
        self.append_step_button.setToolTip("Append one step before the FF terminator")
        self.append_step_button.clicked.connect(self.__append_list_step)
        self.append_step_button.hide()

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                             QSizePolicy.Policy.Preferred)

        self.insert_button = QPushButton("+")
        self.insert_button.setFixedSize(22, 22)
        self.insert_button.setToolTip("Insert a new command after this one")
        self.insert_button.clicked.connect(lambda: self.insert_requested.emit(self))
        self.remove_button = QPushButton("−")
        self.remove_button.setFixedSize(22, 22)
        self.remove_button.setToolTip("Remove this command")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(2, 0, 2, 0)
        main_layout.addWidget(self.address_label)
        main_layout.addWidget(self.op_code_combo)
        main_layout.addLayout(self.param_layout)
        main_layout.addWidget(self.append_step_button)
        main_layout.addWidget(self.description_label, stretch=1)
        main_layout.addWidget(self.insert_button)
        main_layout.addWidget(self.remove_button)
        self.setLayout(main_layout)

        self.refresh_from_command()

    # ------------------------------------------------------------------ view
    def refresh_from_command(self):
        """Align every widget on self.command (no signals fired back)."""
        self._updating = True
        self.address_label.setText(f"0x{self.command.address:02X}")
        if self.command.is_animation():
            combo_value = ANIM_COMBO_VALUE
            param_values = [self.command.op_code]
        else:
            combo_value = self.command.op_code
            param_values = list(self.command.parameters or b"")
        index = self.op_code_combo.findData(combo_value)
        self.op_code_combo.setCurrentIndex(index if index >= 0 else 0)

        for widget in self.param_widget_list:
            widget.setParent(None)
            widget.deleteLater()
        self.param_widget_list = []
        for param_position, value in enumerate(param_values):
            spin = QSpinHex()
            if self.command.is_animation():
                spin.setRange(0, self.vm.animation_op_code_max - 1)
                spin.setToolTip("Animation id (section 3)")
            else:
                spin.setToolTip(self.__param_tooltip(param_position))
            spin.setValue(value)
            spin.valueChanged.connect(self.__param_changed)
            spin.wheelEvent = lambda event: None
            self.param_layout.addWidget(spin)
            self.param_widget_list.append(spin)

        self.append_step_button.setVisible(self.command.op_code in self.vm.ff_list_ops)

        if self.command.is_unknown():
            self.description_label.setText(
                f"Unknown op code: the rest of the sequence cannot be decoded "
                f"({len(self.command.unknown_tail)} byte(s) kept as-is)")
        else:
            self.__refresh_description()
            if not self.description_label.toolTip():
                info = self.command.get_op_code_info()
                self.description_label.setToolTip(info['text'] if info else "")
        self._updating = False

    def __param_tooltip(self, param_position: int) -> str:
        info = get_op_code_info(self.vm, self.command.op_code)
        if info:
            for index_in_text, param_type in enumerate(info.get('param_type', [])):
                if index_in_text < len(info.get('param_index', [])) \
                        and info['param_index'][index_in_text] == param_position:
                    return param_type
        return f"Parameter {param_position}"

    def refresh_address(self):
        """Only the address moved (a previous command was edited): no spinbox rebuild."""
        self.address_label.setText(f"0x{self.command.address:02X}")

    # ----------------------------------------------------------------- edits
    def __op_code_changed(self):
        if self._updating:
            return
        combo_value = self.op_code_combo.currentData()
        if combo_value == ANIM_COMBO_VALUE:
            self.command = SequenceCommand(self.vm, 0x00)
        else:
            self.command = SequenceCommand(self.vm, combo_value,
                                           default_parameters(self.vm, combo_value))
        self.refresh_from_command()
        self.data_changed.emit()

    def __param_changed(self):
        if self._updating:
            return
        if self.command.is_animation():
            self.command.op_code = self.param_widget_list[0].value()
            self.data_changed.emit()
            return
        new_parameters = bytearray(spin.value() for spin in self.param_widget_list)
        normalized = normalize_parameters(self.vm, self.command.op_code, new_parameters)
        self.command.parameters = normalized
        if normalized != new_parameters:
            # A flag bit grew or shrank the block (sound channel mask, hit effect extra
            # bytes, FF truncating a list): the spin boxes no longer match, rebuild them.
            self.refresh_from_command()
        else:
            self.__refresh_description()
        self.data_changed.emit()

    def __append_list_step(self):
        """FF-list op codes only: one more step before the terminator."""
        parameters = bytearray(self.command.parameters or b"")
        insert_at = parameters.index(0xFF) if 0xFF in parameters else len(parameters)
        parameters.insert(insert_at, 0x00)
        self.command.parameters = normalize_parameters(self.vm, self.command.op_code,
                                                       parameters)
        self.refresh_from_command()
        self.data_changed.emit()

    def __refresh_description(self):
        description = describe_command(self.command)
        first_line = description.split("\n")[0] if description else ""
        self.description_label.setText(first_line)
        if description and description != first_line:
            self.description_label.setToolTip(description)
