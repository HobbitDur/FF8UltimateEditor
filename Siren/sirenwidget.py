import os

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QSpinBox, QGroupBox, QFormLayout)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.itemrowcontrols import ItemRowControls
from Common.kernelnamesource import KernelNameSource
from FF8GameData.gamedata import GameData
from Siren.sirenmanager import SirenManager
from SmallWidget.listsearchbar import ListSearchBar


class SirenWidget(QWidget):
    """price.bin editor (shop item buy/sell prices).

    Ported from the original Siren tool: each item has a buy price (a multiple of 10) and a
    sell price multiplier. The sell price shown in shops is round((buy / 10 / 2) * mult)."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.manager = SirenManager(self.game_data)

        self.setWindowTitle("Siren")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'siren.ico')))

        # File section: price.bin is this tool's one editable file, driven by the shared
        # header toolbar (Import / Save) through the registry.
        self.price_binding = FileBinding("price.bin", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file)
        # kernel.bin, complementary: the names of the items a mod adds (FFNx AddMoreItems, 199+)
        # and of the ones it renames.
        self.kernel_names = KernelNameSource(self.game_data, file_registry)
        self.kernel_names.changed.connect(self._on_kernel_names_changed)

        # Item list (left side), with a Ctrl+F search bar filtering it (item name or item id)
        self.item_list = QListWidget()
        self.item_list.setFixedWidth(180)
        self.item_list.currentRowChanged.connect(self.reload_selected_item)
        self.item_search = ListSearchBar.wrap(self.item_list, match_index=True)
        # Items 199-255 (FFNx AddMoreItems): rows added or removed at the end of the list.
        self.item_rows = ItemRowControls("price")
        self.item_rows.add_requested.connect(self._add_item)
        self.item_rows.remove_requested.connect(self._remove_last_item)
        self.item_search.column.layout().addWidget(self.item_rows)

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
        main_editor_layout.addWidget(self.item_search.column)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

        self.price_binding.load_opened_file()  # Another tool may have opened price.bin already
        self.kernel_names.binding.load_opened_file()  # ...or a kernel.bin

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool: price.bin, and kernel.bin as
        a complementary file naming the items."""
        return [self.price_binding, self.kernel_names.binding]

    def _on_kernel_names_changed(self):
        self.manager.item_names = dict(self.kernel_names.items)
        self.manager.rename_items()
        for row, price_entry in enumerate(self.manager.price_entries):
            item = self.item_list.item(row)
            if item is not None:
                item.setText(self._item_label(price_entry))
        price_entry = self._selected_price_entry()
        if price_entry:
            self.item_name_label.setText(price_entry.name)

    @staticmethod
    def _item_label(price_entry):
        return f"{price_entry.item_id}: {price_entry.name}" if price_entry.item_id >= 199 else price_entry.name

    def _add_item(self):
        if self.manager.append_item() is None:
            return
        self.item_list.addItem(self._item_label(self.manager.price_entries[-1]))
        self.item_list.setCurrentRow(self.item_list.count() - 1)
        self.item_rows.set_row_count(len(self.manager.price_entries))
        self._mark_edited()

    def _remove_last_item(self):
        if not self.manager.remove_last_item():
            return
        self.item_list.takeItem(self.item_list.count() - 1)
        self.item_rows.set_row_count(len(self.manager.price_entries))
        self._mark_edited()

    def _mark_edited(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    def load_file(self, file_name):
        self.manager.load_file(file_name)
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.item_list):
            self.item_list.clear()
            self.item_list.addItems([self._item_label(price_entry) for price_entry in self.manager.price_entries])
        self.item_rows.set_row_count(len(self.manager.price_entries))
        self.item_search.select_first_match()  # Row 0, or the first match if a search is typed in

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
