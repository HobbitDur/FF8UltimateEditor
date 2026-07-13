import os

from PyQt6.QtCore import QSize, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QSpinBox, QGroupBox, QFormLayout)

from FF8GameData.gamedata import GameData
from Siren.sirenmanager import SirenManager


class SirenWidget(QWidget):
    """price.bin editor (shop item buy/sell prices).

    Ported from the original Siren tool: each item has a buy price (a multiple of 10) and a
    sell price multiplier. The sell price shown in shops is round((buy / 10 / 2) * mult)."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.manager = SirenManager(self.game_data)

        self.setWindowTitle("Siren")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'siren.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a price.bin file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened price.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Item list (left side)
        self.item_list = QListWidget()
        self.item_list.setFixedWidth(180)
        self.item_list.currentRowChanged.connect(self.reload_selected_item)

        # Editor (right side)
        self.item_name_label = QLabel("")
        self.item_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.buy_spinbox = QSpinBox()
        self.buy_spinbox.setRange(0, 655350)  # uint16 price * 10
        self.buy_spinbox.setSingleStep(10)
        self.buy_spinbox.setSuffix(" G")
        self.buy_spinbox.setToolTip("Buy price in gils (stored as buy price / 10, so it is a multiple of 10)")
        self.buy_spinbox.valueChanged.connect(self._on_data_changed)

        self.sell_mult_spinbox = QSpinBox()
        self.sell_mult_spinbox.setRange(0, 255)
        self.sell_mult_spinbox.setToolTip("Sell price multiplier")
        self.sell_mult_spinbox.valueChanged.connect(self._on_data_changed)

        self.sell_price_label = QLabel("0 G")
        self.sell_price_label.setToolTip("Sell price = round((buy price / 10 / 2) * sell multiplier)")

        edit_group = QGroupBox("Prices")
        edit_form = QFormLayout()
        edit_form.addRow("Buy price:", self.buy_spinbox)
        edit_form.addRow("Sell price multiplier:", self.sell_mult_spinbox)
        edit_form.addRow("Sell price*:", self.sell_price_label)
        edit_form.addRow(QLabel("*Sell price = ((Buy price / 10) / 2) * Sell mult"))
        edit_group.setLayout(edit_form)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.item_name_label)
        editor_layout.addWidget(edit_group)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.item_list)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search price.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if file_name:
            self.manager.load_file(file_name)
            self.file_label.setText(os.path.basename(file_name))
            self.editor_container.setEnabled(True)
            with QSignalBlocker(self.item_list):
                self.item_list.clear()
                self.item_list.addItems([price_entry.name for price_entry in self.manager.price_entries])
            self.item_list.setCurrentRow(0)

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def reload_selected_item(self):
        price_entry = self._selected_price_entry()
        if not price_entry:
            return
        self.item_name_label.setText(price_entry.name)
        with QSignalBlocker(self.buy_spinbox):
            self.buy_spinbox.setValue(price_entry.buy_price)
        with QSignalBlocker(self.sell_mult_spinbox):
            self.sell_mult_spinbox.setValue(price_entry.sell_mult)
        self._update_sell_price(price_entry)

    def _selected_price_entry(self):
        index = self.item_list.currentRow()
        if 0 <= index < len(self.manager.price_entries):
            return self.manager.price_entries[index]
        return None

    def _update_sell_price(self, price_entry):
        self.sell_price_label.setText(f"{price_entry.sell_price} G")

    def _on_data_changed(self):
        price_entry = self._selected_price_entry()
        if not price_entry:
            return
        price_entry.buy_price = self.buy_spinbox.value()
        price_entry.sell_mult = self.sell_mult_spinbox.value()
        self._update_sell_price(price_entry)
