"""
Dialog of the NPC tab's "+ Add card game": the texts and options of a card game given to an NPC
that has none (see jsmnpc.add_card_game).
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox, QPlainTextEdit,
                             QDialogButtonBox, QSpinBox)

from CCGroup import cardlocation, jsmnpc

CARD_NAMES_PLACEHOLDER = [""] * cardlocation.NB_CARDS  # location_label only needs names for 200-232

TOOLTIP_TEXTS = ("One line per window line. For the question, the 2nd and 3rd lines are the answers\n"
                 "(the first one = play). The texts are added to the map's .msd and can be edited later\n"
                 "in the card player's Texts panel.")


class AddCardGameDialog(QDialog):
    def __init__(self, parent, map_name: str, entity_name: str, has_card_master: bool, region_calls: str,
                 region_guess: int, free_deck_id=None, deck_id_users=None):
        """free_deck_id: preset Deck ID (unused by anyone); deck_id_users(deck_id) -> list of what
        already uses a Deck ID, for the live note."""
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

        self.deck_id_users = deck_id_users or (lambda _: [])
        self.deck_id_spinbox = QSpinBox()
        self.deck_id_spinbox.setRange(0, 255)
        self.deck_id_spinbox.setValue(free_deck_id if free_deck_id is not None else 0)
        self.deck_id_spinbox.setToolTip(
            "The NPC's rare card pocket. A Deck ID of its own (the preset: nobody else uses it) means a\n"
            "rare card the player loses to this NPC stays with it, and only it can play it back.")
        self.deck_id_note = QLabel()
        self.deck_id_note.setWordWrap(True)
        self.deck_id_spinbox.valueChanged.connect(self.__deck_id_changed)
        deck_row = QHBoxLayout()
        deck_row.addWidget(self.deck_id_spinbox)
        deck_row.addWidget(self.deck_id_note, 1)
        form.addRow("Deck ID:", deck_row)
        self.__deck_id_changed(self.deck_id_spinbox.value())

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

        note = QLabel("The NPC starts with 0 % rare chance, the weakest AI and Lv1-2 cards: set them in the"
                      " editor once added.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add card game")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, self.sizeHint().height())

    def __deck_id_changed(self, deck_id: int):
        if cardlocation.is_reserved_location(deck_id):
            self.deck_id_note.setText(f"Reserved: {cardlocation.location_label(deck_id, CARD_NAMES_PLACEHOLDER)}"
                                      if deck_id not in range(200, 233) else
                                      "Reserved: the starting owner of a rare card (this NPC would share it)")
            return
        users = self.deck_id_users(deck_id)
        if not users:
            self.deck_id_note.setText("Unique: no other card player uses it")
        else:
            shown = ", ".join(users[:4]) + (f" and {len(users) - 4} more" if len(users) > 4 else "")
            self.deck_id_note.setText(f"Shared with {shown}")

    def deck_id(self):
        return self.deck_id_spinbox.value()

    def region(self):
        return self.region_combobox.currentIndex()

    def on_no(self):
        return self.on_no_combobox.currentData()

    def question_text(self):
        return self.question_edit.toPlainText()

    def not_enough_text(self):
        return self.not_enough_edit.toPlainText()
