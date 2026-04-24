from typing import List

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSpinBox, QFrame, QSizePolicy, QLabel, QComboBox, QPlainTextEdit

from FF8GameData.dat.commandanalyser import CommandAnalyser
from FF8GameData.monsterdata import EntityType
from IfritAI.qspinhex import QSpinHex


class OpIdChangedEmitter(QObject):
    op_id_signal = pyqtSignal()


class SeqWidget(QWidget):
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MIN_OP_ID = 0
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0
    SEQ_DESCRIPTION_CHARA = [
        "None",
        "Basic Standing Animation loop",
        "Exhausted - low hp animation loop",
        "Death loop",
        "Damage Taken into a low hp phase",
        "Damage Taken Normal",
        "Damage Taken Crit",
        "Nothing happens",
        "Appearance (like at the start of the battle)",
        "Staying in 'rdy to attack standing'",
        "Draw command fail animation",
        "Magic animation",
        "Basic Standing Animation",
        "Attack - normal",
        "Guardian Force Summoning (Disappear)",
        "Item Use",
        "Runaway 1",
        "Runaway 2 - Escaped disappear",
        "Victory Animation",
        "Changing into 'rdy to attack standing'",
        "Guardian Force Summoning (Re-appear)",
        "Limit break 1 (Normal)",
        "Draw/Defend Phase again?",
        "Changing into Defend/Draw Phase",
        "Kamikaze Command - Running to the enemy",
        "Attack - Darkside",
        "Runaway 2? (same as 1) - maybe used at Edea Disc 1 fight? (Rinoa / Irvine appearance)",
        "Defend/Draw stock",
        "Limit break 2 (Special, e.g. Squall/Zell Blue aura)",
        "Defend command standing again",
        "Draw Stock Magic"
    ]
    def __init__(self, seq: bytearray, id: int, entity_type:EntityType=EntityType.MONSTER ):
        QWidget.__init__(self)
        # Parameters
        self._sequence = seq
        self._id = id
        self.entity_type = entity_type

        # signal
        self.op_id_changed_signal_emitter = OpIdChangedEmitter()

        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        # op_id widget
        if entity_type.WEAPON:
            self.sequence_title = QLabel(f"Seq ID {id}")
        else:
            self.sequence_title = QLabel(f"Seq ID {id}")
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
    def getId(self):
        return self._id


