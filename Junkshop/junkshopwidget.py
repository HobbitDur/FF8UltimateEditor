import os

from PyQt6.QtCore import QSize, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QSpinBox, QComboBox, QGroupBox, QFormLayout)

from FF8GameData.gamedata import GameData
from Junkshop.junkshopmanager import JunkshopManager, WeaponUpgrade


class JunkshopWidget(QWidget):
    """mwepon.bin editor (Junk Shop weapon-upgrade recipes).

    Ported from the original JunkShop tool: each weapon upgrade has a price (stored as a
    multiple of 10) and a recipe of up to four (item, quantity) pairs the game consumes when
    the upgrade is bought. An item id of 0 (Nothing) disables that recipe slot."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.manager = JunkshopManager(self.game_data)

        # Ordered item id/name lists so a combo box index maps to the real item id
        self.item_ids = [item["id"] for item in self.game_data.item_data_json["items"]]
        self.item_names = [item["name"] for item in self.game_data.item_data_json["items"]]

        self.setWindowTitle("Junkshop")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'junkshop.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a mwepon.bin file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened mwepon.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Weapon list (left side)
        self.weapon_list = QListWidget()
        self.weapon_list.setFixedWidth(180)
        self.weapon_list.currentRowChanged.connect(self.reload_selected_weapon)

        # Editor (right side)
        self.weapon_name_label = QLabel("")
        self.weapon_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.price_spinbox = QSpinBox()
        self.price_spinbox.setRange(0, 2550)  # byte price * 10
        self.price_spinbox.setSingleStep(10)
        self.price_spinbox.setSuffix(" G")
        self.price_spinbox.setToolTip("Upgrade price in gils (stored as price / 10, so it is a multiple of 10)")
        self.price_spinbox.valueChanged.connect(self._on_data_changed)

        self.name_offset_label = QLabel("")
        self.name_offset_label.setToolTip(
            "Offset of this weapon's name inside mwepon.msg (bytes 0-1 of the record).\n"
            "Read-only: it is set by the original game files and has no effect on gameplay "
            "other than pointing to the name text, so it is preserved as-is on save.")

        price_group = QGroupBox("Price")
        price_form = QFormLayout()
        price_form.addRow("Upgrade price:", self.price_spinbox)
        price_form.addRow("Name offset (read-only):", self.name_offset_label)
        price_group.setLayout(price_form)

        # Four recipe slots (item + quantity)
        self.item_comboboxes = []
        self.quantity_spinboxes = []
        recipe_form = QFormLayout()
        for i in range(WeaponUpgrade.NB_ITEM):
            item_combobox = QComboBox()
            item_combobox.addItems(self.item_names)
            item_combobox.setToolTip("Item consumed by this recipe slot (Nothing = slot disabled)")
            item_combobox.currentIndexChanged.connect(self._on_data_changed)

            quantity_spinbox = QSpinBox()
            quantity_spinbox.setRange(0, 255)
            quantity_spinbox.setToolTip("Quantity of the item consumed")
            quantity_spinbox.valueChanged.connect(self._on_data_changed)

            self.item_comboboxes.append(item_combobox)
            self.quantity_spinboxes.append(quantity_spinbox)

            slot_layout = QHBoxLayout()
            slot_layout.addWidget(item_combobox)
            slot_layout.addWidget(QLabel("x"))
            slot_layout.addWidget(quantity_spinbox)
            recipe_form.addRow(f"Item {i + 1}:", slot_layout)

        recipe_group = QGroupBox("Recipe (items required to buy)")
        recipe_group.setLayout(recipe_form)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.weapon_name_label)
        editor_layout.addWidget(price_group)
        editor_layout.addWidget(recipe_group)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.weapon_list)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mwepon.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if file_name:
            self.manager.load_file(file_name)
            self.file_label.setText(os.path.basename(file_name))
            self.editor_container.setEnabled(True)
            with QSignalBlocker(self.weapon_list):
                self.weapon_list.clear()
                self.weapon_list.addItems([weapon.name for weapon in self.manager.weapon_upgrades])
            self.weapon_list.setCurrentRow(0)

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def reload_selected_weapon(self):
        weapon = self._selected_weapon()
        if not weapon:
            return
        self.weapon_name_label.setText(weapon.name)
        with QSignalBlocker(self.price_spinbox):
            self.price_spinbox.setValue(weapon.price)
        self.name_offset_label.setText(f"0x{weapon.name_offset:04X}")
        for i in range(WeaponUpgrade.NB_ITEM):
            item_id, quantity = weapon.items[i]
            with QSignalBlocker(self.item_comboboxes[i]):
                self.item_comboboxes[i].setCurrentIndex(self._combo_index_for_item(item_id))
            with QSignalBlocker(self.quantity_spinboxes[i]):
                self.quantity_spinboxes[i].setValue(quantity)

    def _selected_weapon(self):
        index = self.weapon_list.currentRow()
        if 0 <= index < len(self.manager.weapon_upgrades):
            return self.manager.weapon_upgrades[index]
        return None

    def _combo_index_for_item(self, item_id):
        if item_id in self.item_ids:
            return self.item_ids.index(item_id)
        return 0

    def _on_data_changed(self):
        weapon = self._selected_weapon()
        if not weapon:
            return
        weapon.price = self.price_spinbox.value()
        for i in range(WeaponUpgrade.NB_ITEM):
            weapon.items[i][0] = self.item_ids[self.item_comboboxes[i].currentIndex()]
            weapon.items[i][1] = self.quantity_spinboxes[i].value()
