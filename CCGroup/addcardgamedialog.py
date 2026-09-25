"""
Dialog of the NPC tab's "+ Add card game": the texts and options of a card game given to an NPC
that has none (see jsmnpc.add_card_game).
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QComboBox, QPlainTextEdit,
                             QDialogButtonBox)

from CCGroup import jsmnpc

TOOLTIP_TEXTS = ("One line per window line. For the question, the 2nd and 3rd lines are the answers\n"
                 "(the first one = play). The texts are added to the map's .msd and can be edited later\n"
                 "in the card player's Texts panel.")


class AddCardGameDialog(QDialog):
    def __init__(self, parent, map_name: str, entity_name: str, has_card_master: bool, region_calls: str,
                 region_guess: int):
        QDialog.__init__(self, parent)
        self.setWindowTitle(f"Add a card game to {entity_name} ({map_name})")
        layout = QVBoxLayout()
        self.setLayout(layout)

        if has_card_master:
            region_name = jsmnpc.REGION_NAMES[jsmnpc.REGIONS.index(region_calls)] if region_calls in jsmnpc.REGIONS \
                else region_calls
            info = (f"<b>{map_name}</b> has a card master: the match uses the {region_name} rules and the Queen of"
                    f" Cards can spread or abolish rules after it, exactly like its other card players.")
        else:
            info = (f"<b>{map_name}</b> has <b>no card master</b>: the match uses the region's current rules"
                    f" directly, but the Queen of Cards will not spread or abolish rules after it.")
        info_label = QLabel(info)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        layout.addLayout(form)
        self.region_combobox = QComboBox()
        self.region_combobox.addItems(jsmnpc.REGION_NAMES)
        self.region_combobox.setCurrentIndex(region_guess)
        self.region_combobox.setToolTip("Whose rules this NPC plays with (savemap vars 272 + region, 280 + region).\n"
                                        "Preset to the region of the other card players of these maps.")
        if not has_card_master:
            form.addRow("Rules of the region:", self.region_combobox)

        self.on_no_combobox = QComboBox()
        self.on_no_combobox.addItem("Nothing (like the vanilla card players)", jsmnpc.ON_NO_NOTHING)
        self.on_no_combobox.addItem("The NPC's original dialogue", jsmnpc.ON_NO_ORIGINAL)
        self.on_no_combobox.setToolTip(
            "Vanilla card players say nothing when you decline. 'Original dialogue' keeps what the\n"
            "NPC said before (useful when it has story lines or gives something).")
        form.addRow("When the player says No:", self.on_no_combobox)

        self.question_edit = QPlainTextEdit(jsmnpc.DEFAULT_QUESTION)
        self.question_edit.setToolTip(TOOLTIP_TEXTS)
        self.question_edit.setFixedHeight(70)
        form.addRow("Question:", self.question_edit)
        self.not_enough_edit = QPlainTextEdit(jsmnpc.DEFAULT_NOT_ENOUGH_CARDS)
        self.not_enough_edit.setToolTip(TOOLTIP_TEXTS)
        self.not_enough_edit.setFixedHeight(55)
        form.addRow("Not enough cards:", self.not_enough_edit)

        note = QLabel("The NPC starts with Deck ID 0 (no rare card), 0 % rare chance, the weakest AI and Lv1-2"
                      " cards: set them in the editor once added.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add card game")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, self.sizeHint().height())

    def region(self):
        return self.region_combobox.currentIndex()

    def on_no(self):
        return self.on_no_combobox.currentData()

    def question_text(self):
        return self.question_edit.toPlainText()

    def not_enough_text(self):
        return self.not_enough_edit.toPlainText()
