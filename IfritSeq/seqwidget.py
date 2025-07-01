from typing import List

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSpinBox, QFrame, QSizePolicy, QLabel, QComboBox, QPlainTextEdit

from FF8GameData.dat.commandanalyser import CommandAnalyser
from IfritAI.qspinhex import QSpinHex


class OpIdChangedEmitter(QObject):
    op_id_signal = pyqtSignal()


class SeqWidget(QWidget):
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MIN_OP_ID = 0
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, seq: bytearray, id: int ):
        QWidget.__init__(self)
        # Parameters
        self._sequence = seq
        self._id = id

        # signal
        self.op_id_changed_signal_emitter = OpIdChangedEmitter()

        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        # op_id widget
        self.sequence_title = QLabel(f"Seq ID {id}:")
        self.sequence_text_widget = QPlainTextEdit()
        self.sequence_text_widget.setPlainText(self._sequence.hex(" "))


        self.sequence_layout = QHBoxLayout()
        self.sequence_layout.addWidget(self.sequence_title)
        self.sequence_layout.addWidget(self.sequence_text_widget)
        #self.sequence_layout.addStretch(1)


        self.main_layout.addLayout(self.sequence_layout)


    def __str__(self):
        return str(self._sequence)
    def __repr__(self):
        return self.__str__()

    def getByteData(self):
        return bytearray.fromhex(self.sequence_text_widget.toPlainText())


