from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

from FF8GameData import itemids


class ItemRowControls(QWidget):
    """"+ Add item" / "- Remove last item" under a list of item-id rows (mitem.bin, price.bin).

    Those files hold one row per item id, 0-198 in the game. FFNx's AddMoreItems reads them up to
    id 255 (FF8GameData/itemids.py), so a mod adding items extends them to the same id as its
    kernel.bin. Rows go and come only at the end: a row's position is its item id, and the game
    never had rows 199+, so only those can be removed again.

    The owner connects add_requested / remove_requested, changes its rows, then calls
    set_row_count."""

    add_requested = pyqtSignal()
    remove_requested = pyqtSignal()

    TOOLTIP = ("FFNx's AddMoreItems reads this file up to item 255. Give every item a mod adds to its\n"
               "kernel.bin (SolomonRing, Item Names) a row here too: a missing row is an item with no\n"
               "{what}. Only the items the game never had (199+) can be removed, from the last one.")

    def __init__(self, what="field use", parent=None):
        QWidget.__init__(self, parent)
        self.add_button = QPushButton("+ Add item")
        self.remove_button = QPushButton("- Remove last item")
        self.count_label = QLabel()
        self.count_label.setStyleSheet("font-size: 9pt;")
        self.count_label.setWordWrap(True)
        tooltip = self.TOOLTIP.format(what=what)
        for widget in (self.add_button, self.remove_button, self.count_label):
            widget.setToolTip(tooltip)
        self.add_button.clicked.connect(lambda _checked=False: self.add_requested.emit())
        self.remove_button.clicked.connect(lambda _checked=False: self.remove_requested.emit())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.add_button)
        layout.addWidget(self.remove_button)
        layout.addWidget(self.count_label)
        self.set_row_count(0)

    def set_row_count(self, rows):
        self.add_button.setEnabled(0 < rows < itemids.ITEM_ID_COUNT)
        self.remove_button.setEnabled(rows > itemids.VANILLA_ITEM_COUNT)
        self.count_label.setText(f"{rows} / {itemids.ITEM_ID_COUNT} items (ids 0-{rows - 1})" if rows else "")
