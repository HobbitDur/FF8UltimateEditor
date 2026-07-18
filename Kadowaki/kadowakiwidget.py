import os

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                             QComboBox, QCheckBox, QGroupBox, QSpinBox, QGridLayout)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Kadowaki.kadowakimanager import KadowakiManager


class ParamWidget(QGroupBox):
    """One of the two type-dependent parameters (param1/param2).
    The inner widget adapts to the param type defined in mitem.json:
    - "none": the parameter is unused for this item type
    - "int": a raw byte value
    - "flags": 8 checkboxes, one per bit
    - "list": a choice between named values (from an inline list or another json like gforce.json)"""

    def __init__(self, title, manager: KadowakiManager, value_changed_callback):
        QGroupBox.__init__(self, title)
        self.manager = manager
        self._value_changed_callback = value_changed_callback
        self._widget_type = "none"
        self._raw_value = 0

        self._unused_label = QLabel("Unused")
        self._unused_label.setStyleSheet("font-style: italic;")

        self._int_spinbox = QSpinBox()
        self._int_spinbox.setRange(0, 255)
        self._int_spinbox.valueChanged.connect(self._on_value_changed)

        self._flag_checkboxes = [QCheckBox() for _ in range(8)]
        flag_layout = QGridLayout()
        for bit, checkbox in enumerate(self._flag_checkboxes):
            checkbox.toggled.connect(self._on_value_changed)
            flag_layout.addWidget(checkbox, bit % 4, bit // 4)
        self._flag_container = QWidget()
        self._flag_container.setLayout(flag_layout)

        self._list_combo = QComboBox()
        self._list_combo_ids = []
        self._list_combo.activated.connect(self._on_value_changed)

        self._layout = QVBoxLayout()
        self._layout.addWidget(self._unused_label)
        self._layout.addWidget(self._int_spinbox)
        self._layout.addWidget(self._flag_container)
        self._layout.addWidget(self._list_combo)
        self._layout.addStretch(1)
        self.setLayout(self._layout)

    def set_param_type(self, param_type_name):
        """Adapt the inner widget to the given param type of mitem.json (keeping the current byte value)."""
        current_value = self.get_value()
        param_type_info = self.manager.get_param_type_info(param_type_name)
        if not param_type_info:  # Unknown param type, fallback to raw int so the value stays editable
            param_type_info = {"name": param_type_name, "widget": "int", "description": "Unknown param type"}
        self._widget_type = param_type_info["widget"]
        self.setTitle(f"{self.title().split(':')[0]}: {param_type_info['name']}")
        self.setToolTip(param_type_info.get("description", ""))

        self._unused_label.setVisible(self._widget_type == "none")
        self._int_spinbox.setVisible(self._widget_type == "int")
        self._flag_container.setVisible(self._widget_type == "flags")
        self._list_combo.setVisible(self._widget_type == "list")

        if self._widget_type == "flags":
            flag_values = param_type_info["values"]
            for bit, checkbox in enumerate(self._flag_checkboxes):
                checkbox.setVisible(bit < len(flag_values))
                if bit < len(flag_values):
                    checkbox.setText(flag_values[bit]["name"])
                    checkbox.setToolTip(flag_values[bit].get("description", ""))
        elif self._widget_type == "list":
            with QSignalBlocker(self._list_combo):
                self._list_combo.clear()
                self._list_combo_ids = []
                for value_info in self.manager.get_param_list_values(param_type_info):
                    self._list_combo.addItem(value_info["name"])
                    self._list_combo_ids.append(value_info["id"])
        self.set_value(current_value)

    def set_value(self, value):
        with QSignalBlocker(self._int_spinbox):
            self._int_spinbox.setValue(value)
        for bit, checkbox in enumerate(self._flag_checkboxes):
            with QSignalBlocker(checkbox):
                checkbox.setChecked(bool(value & (1 << bit)))
        with QSignalBlocker(self._list_combo):
            if self._widget_type == "list":
                if value not in self._list_combo_ids:  # Unknown value, add a temporary entry to not lose it
                    self._list_combo.addItem(f"Unknown ({value})")
                    self._list_combo_ids.append(value)
                self._list_combo.setCurrentIndex(self._list_combo_ids.index(value))

    def get_value(self):
        if self._widget_type == "int":
            return self._int_spinbox.value()
        elif self._widget_type == "flags":
            value = 0
            for bit, checkbox in enumerate(self._flag_checkboxes):
                if checkbox.isChecked():
                    value += 1 << bit
            return value
        elif self._widget_type == "list":
            if self._list_combo.currentIndex() >= 0:
                return self._list_combo_ids[self._list_combo.currentIndex()]
            return 0
        else:  # "none": keep the raw byte value untouched
            return self._raw_value

    def set_raw_value(self, value):
        """Byte value kept for "none" param types, so unused data is written back unchanged."""
        self._raw_value = value

    def _on_value_changed(self):
        self._value_changed_callback()


class KadowakiWidget(QWidget):
    """Item menu editor (mitem.bin editor)."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.game_data.load_mitem_data()
        self.game_data.load_gforce_data()
        self.manager = KadowakiManager(self.game_data)

        self.setWindowTitle("Kadowaki")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section: mitem.bin, this tool's one editable file, driven by the shared
        # header toolbar (Import / Save) through the registry.
        self.mitem_binding = FileBinding("mitem.bin", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file)

        # Item list (left side)
        self.item_list = QListWidget()
        self.item_list.setFixedWidth(180)
        self.item_list.currentRowChanged.connect(self.reload_selected_item)

        # Editor (right side)
        self.item_name_label = QLabel("")
        self.item_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.type_combo = QComboBox()
        self.type_combo.setToolTip("Behaviour of the item in the menu, it defines how param1 and param2 are used")
        for index, item_type in enumerate(self.game_data.mitem_data_json["item_type"]):
            self.type_combo.addItem(item_type["name"])
            self.type_combo.setItemData(index, item_type["description"], Qt.ItemDataRole.ToolTipRole)
        self.type_combo.activated.connect(self._on_type_changed)
        type_layout = QHBoxLayout()
        type_label = QLabel("Type:")
        type_label.setToolTip(self.type_combo.toolTip())
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch(1)

        self.flag_group = QGroupBox("Flags")
        self.flag_group.setToolTip("Targeting and usability of the item")
        self.flag_checkboxes = [QCheckBox() for _ in range(8)]
        flag_layout = QGridLayout()
        for bit, flag_info in enumerate(self.game_data.mitem_data_json["flag"]):
            self.flag_checkboxes[bit].setText(flag_info["name"])
            self.flag_checkboxes[bit].setToolTip(flag_info["description"])
            self.flag_checkboxes[bit].toggled.connect(self._on_data_changed)
            flag_layout.addWidget(self.flag_checkboxes[bit], bit % 4, bit // 4)
        self.flag_group.setLayout(flag_layout)

        self.param1_widget = ParamWidget("Param 1", self.manager, self._on_data_changed)
        self.param2_widget = ParamWidget("Param 2", self.manager, self._on_data_changed)
        param_layout = QHBoxLayout()
        param_layout.addWidget(self.param1_widget)
        param_layout.addWidget(self.param2_widget)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.item_name_label)
        editor_layout.addLayout(type_layout)
        editor_layout.addWidget(self.flag_group)
        editor_layout.addLayout(param_layout)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.item_list)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

        self.mitem_binding.load_opened_file()  # Another tool may have opened mitem.bin already

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool (just mitem.bin)."""
        return [self.mitem_binding]

    def load_file(self, file_name):
        self.manager.load_file(file_name)
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.item_list):
            self.item_list.clear()
            self.item_list.addItems([menu_item.name for menu_item in self.manager.menu_items])
        self.item_list.setCurrentRow(0)

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def reload_selected_item(self):
        """Refresh the whole editor from the selected item data."""
        menu_item = self._selected_menu_item()
        if not menu_item:
            return
        self.item_name_label.setText(menu_item.name)
        with QSignalBlocker(self.type_combo):
            known_type = self.manager.get_item_type_info(menu_item.type_id) is not None
            if self.type_combo.count() > len(self.game_data.mitem_data_json["item_type"]):
                self.type_combo.removeItem(self.type_combo.count() - 1)  # Remove previous "Unknown" temporary entry
            if known_type:
                self.type_combo.setCurrentIndex(menu_item.type_id)
            else:
                self.type_combo.addItem(f"Unknown ({menu_item.type_id})")
                self.type_combo.setCurrentIndex(self.type_combo.count() - 1)
        for bit, checkbox in enumerate(self.flag_checkboxes):
            with QSignalBlocker(checkbox):
                checkbox.setChecked(bool(menu_item.flags & (1 << bit)))
        self._update_param_widgets(menu_item)

    def _selected_menu_item(self):
        index = self.item_list.currentRow()
        if 0 <= index < len(self.manager.menu_items):
            return self.manager.menu_items[index]
        return None

    def _update_param_widgets(self, menu_item):
        """Adapt param1/param2 widgets to the item type and show the item values."""
        item_type_info = self.manager.get_item_type_info(menu_item.type_id)
        if item_type_info:
            param1_type = item_type_info["param1"]
            param2_type = item_type_info["param2"]
        else:  # Unknown type, edit params as raw values
            param1_type = "unknown"
            param2_type = "unknown"
        self.param1_widget.set_raw_value(menu_item.param1)
        self.param2_widget.set_raw_value(menu_item.param2)
        self.param1_widget.set_param_type(param1_type)
        self.param2_widget.set_param_type(param2_type)
        self.param1_widget.set_value(menu_item.param1)
        self.param2_widget.set_value(menu_item.param2)

    def _on_type_changed(self):
        menu_item = self._selected_menu_item()
        if not menu_item:
            return
        if self.type_combo.currentIndex() < len(self.game_data.mitem_data_json["item_type"]):
            menu_item.type_id = self.game_data.mitem_data_json["item_type"][self.type_combo.currentIndex()]["id"]
        self._update_param_widgets(menu_item)  # Params keep their byte value but are reinterpreted for the new type

    def _on_data_changed(self):
        """Save the editor state to the selected item data."""
        menu_item = self._selected_menu_item()
        if not menu_item:
            return
        flags = 0
        for bit, checkbox in enumerate(self.flag_checkboxes):
            if checkbox.isChecked():
                flags += 1 << bit
        menu_item.flags = flags
        menu_item.param1 = self.param1_widget.get_value()
        menu_item.param2 = self.param2_widget.get_value()
