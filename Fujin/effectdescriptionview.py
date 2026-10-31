"""Choreography's Description tab: an effect's description (docs/fujin-effect-description.md) as
Fujin holds it - its parts, its tasks (phases, spawns, draws...), its director and pools - edited
as JSON beside the part tabs' parameters. Apply checks it compiles (Fujin/effectprogram.py) before
taking it; New effect makes a copy of it in a free slot of the game's effect table; the previews
and Save (direct/exe/effect_NNN.fxprog, run in the game by FujinEffects.dll) use what it holds.
"""
import json

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from Fujin.effectprogram import DescriptionError, compile_program

NO_DESCRIPTION = ("No description for this effect: it runs from the exe's code (or FFNx's port). Fujin describes "
                  "Cure (1), Potion (50) and Hypnotize (133); New effect starts from one of them.")


def description_text(description):
    return json.dumps(description, indent=1) + "\n"


class EffectDescriptionView(QWidget):
    """applied(description): a checked description to take for the effect shown; new_requested():
    New effect; reset_requested(): back to Fujin's description (an edited one) or the new effect
    deleted."""
    applied = pyqtSignal(dict)
    new_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.effect = None
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.text = QPlainTextEdit()
        self.text.setFont(QFont("Consolas", 10))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.textChanged.connect(self._edited)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b")
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Check the description compiles, then use it: previews, part tabs and Save")
        self.apply_button.clicked.connect(self.apply)
        self.new_button = QPushButton("New effect from this…")
        self.new_button.setToolTip("A copy of this effect in a free slot of the game's effect table "
                                   "(224, 225, 346-400): a kernel.bin entry naming that effect id casts it")
        self.new_button.clicked.connect(self.new_requested)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self.reset_requested)
        buttons = QHBoxLayout()
        for button in (self.apply_button, self.new_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        self._shown = ""

    def show_description(self, effect, description, kind):
        """`description` of `effect` (None: it has none); kind: "shipped" (Fujin's), "edited" (Fujin's,
        changed) or "new" (a new effect)."""
        self.effect = effect
        self._shown = description_text(description) if description is not None else ""
        self.text.blockSignals(True)
        self.text.setPlainText(self._shown)
        self.text.blockSignals(False)
        self.text.setEnabled(description is not None)
        self.error.clear()
        if description is None:
            self.note.setText(NO_DESCRIPTION)
        else:
            base = f" (made from effect {description['base']})" if "base" in description else ""
            self.note.setText({"shipped": "Fujin's description of this effect.",
                               "edited": "This effect's description, edited: Save writes its program.",
                               "new": f"A new effect{base}: Save writes its program and description."}[kind]
                              + " Values are numbers or $parameter keys; tasks, pools and parts are named by key.")
        self.new_button.setEnabled(description is not None)
        self.reset_button.setText("Delete this new effect" if kind == "new" else "Fujin's description")
        self.reset_button.setVisible(kind in ("new", "edited"))
        self.apply_button.setEnabled(False)

    def _edited(self):
        self.apply_button.setEnabled(self.text.toPlainText() != self._shown)
        self.error.clear()

    def apply(self):
        """The text, checked: applied() when it compiles, else the error shown; True when applied."""
        try:
            description = json.loads(self.text.toPlainText())
            if not isinstance(description, dict) or description.get("effect") != self.effect:
                raise DescriptionError(f"the description of effect {self.effect} keeps \"effect\": {self.effect}")
            compile_program(description)
        except ValueError as error:          # JSON's and DescriptionError
            self.error.setText(f"Not applied: {error}")
            return False
        except (KeyError, TypeError) as error:
            self.error.setText(f"Not applied: missing or wrong entry {error}")
            return False
        self._shown = self.text.toPlainText()
        self.apply_button.setEnabled(False)
        self.applied.emit(description)
        return True
