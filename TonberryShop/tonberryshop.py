import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QFrame, QComboBox, QHBoxLayout

from Common.filebinding import FileBinding
from Common.itemfiles import ItemFiles
from Common.fileregistry import FileRegistry
from TonberryShop.tonberrymanager import TonberryManager, Shop


class TonberryShop(QWidget):
    NB_COLUMN_ITEM = 4
    IMAGE_LIST = ["pet-shop-timber.png", "shop-balamb.png", "shop-dollet.png", "shop-timber.png",
                  "shop-deling-city.png", "shop-winhill.png", "shop-horizon.png", "", "shops-esthar.png", "", "", "", "",
                  "shop-winhill-laguna.png", "", "", "shop-man-from-garden", "shops-esthar.png", "shops-esthar.png",
                  "shops-esthar.png"]

    def __init__(self, resource_folder='Resources', file_registry=None, game_data_folder='FF8GameData'):

        QWidget.__init__(self)
        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self._resource_folder = resource_folder
        self.tonberry_manager = TonberryManager(resource_folder)
        self.file_path = ""
        self.current_shop_index = 0
        # Main window
        self.setWindowTitle("TonberryShop")
        self.setWindowIcon(QIcon(os.path.join(resource_folder, 'icon.png')))

        self.layout_top = QHBoxLayout()
        self.layout_item = QHBoxLayout()
        self.layout_main = QVBoxLayout()

        # shop.bin, this tool's one editable file, driven by the shared header toolbar.
        self.shop_binding = FileBinding("shop.bin", file_registry,
                                        load_callback=self.load_file, save_callback=self.save_file)

        self.shop_list = QComboBox()
        self.shop_list.addItems(self.tonberry_manager.SHOP_NAME_LIST)
        self.shop_list.activated.connect(self.reload_item)

        self.item_combo = [QComboBox() for i in range(Shop.NB_ITEM_PER_SHOP)]
        self.item_rare = [QCheckBox("Rare") for i in range(Shop.NB_ITEM_PER_SHOP)]
        [rare.setLayoutDirection(Qt.LayoutDirection.RightToLeft) for rare in self.item_rare]
        self.item_label = [QLabel(f"Item n°{i + 1}: ") for i in range(Shop.NB_ITEM_PER_SHOP)]
        self.layout_single_item = [QHBoxLayout() for i in range(Shop.NB_ITEM_PER_SHOP)]
        for i in range(Shop.NB_ITEM_PER_SHOP):
            for item_id, name in self.tonberry_manager.item_values.items():
                self.item_combo[i].addItem(f"{item_id}: {name}", item_id)
            self.item_combo[i].activated.connect(self.__item_combo_activated)
            self.item_rare[i].toggled.connect(self.__item_rare_activated)

            self.layout_single_item[i].addWidget(self.item_label[i])
            self.layout_single_item[i].addWidget(self.item_rare[i])
            self.layout_single_item[i].addWidget(self.item_combo[i])

        self.layout_sub_item = [QVBoxLayout() for i in range(self.NB_COLUMN_ITEM)]
        self.qframe = [QFrame() for i in range(self.NB_COLUMN_ITEM - 1)]
        for i in range(self.NB_COLUMN_ITEM):
            self.layout_item.addLayout(self.layout_sub_item[i])
            if i < self.NB_COLUMN_ITEM - 1:
                self.qframe[i].setFrameStyle(0x05)
                self.qframe[i].setLineWidth(2)
                self.layout_item.addWidget(self.qframe[i])
            for j in range(i * self.NB_COLUMN_ITEM, i * self.NB_COLUMN_ITEM + self.NB_COLUMN_ITEM):
                self.layout_sub_item[i].addLayout(self.layout_single_item[j])

        self.image_location = QPixmap(os.path.join(self._resource_folder, self.IMAGE_LIST[0]))
        self.image_location_drawer = QLabel()
        self.image_location_drawer.setPixmap(self.image_location)
        self.image_location_layout = QHBoxLayout()
        self.image_location_layout.addStretch(1)
        self.image_location_layout.addWidget(self.image_location_drawer)
        self.image_location_layout.addStretch(1)


        self.layout_top.addWidget(self.shop_list)
        self.layout_top.addStretch(1)

        self.layout_main.addLayout(self.layout_top)
        self.layout_main.addLayout(self.layout_item)
        self.layout_main.addLayout(self.image_location_layout)
        self.layout_main.addStretch(1)

        self.setLayout(self.layout_main)
        #self.show()

        self.item_files = ItemFiles.for_registry(file_registry, game_data_folder)
        self.item_files.names_changed.connect(self._refresh_item_names)
        self._refresh_item_names()
        self.shop_binding.load_opened_file()  # Another tool may have opened shop.bin already

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool (just shop.bin)."""
        return [self.shop_binding, self.item_files.kernel_binding]

    def load_file(self, file_name):
        self.file_path = file_name
        self.tonberry_manager.read_shop_file(file_name)
        self.tonberry_manager.analyze_shop_file()
        self.reload_item()

    def save_file(self):
        if self.file_path:
            self.tonberry_manager.write_shop_file(self.file_path)

    def __item_combo_activated(self):
        self.__save_to_shop_info()

    def __item_rare_activated(self):
        self.__save_to_shop_info()


    def __save_to_shop_info(self):
        if not self.file_path:
            return
        for item_index in range(Shop.NB_ITEM_PER_SHOP):
            item_id = self.item_combo[item_index].currentData()
            shop = self.tonberry_manager.shop_info[self.current_shop_index]
            shop.item_ids[item_index] = item_id
            shop.item[item_index] = self.tonberry_manager.item_values[item_id]
            self.tonberry_manager.shop_info[self.current_shop_index].rare[item_index] = self.item_rare[
                item_index].isChecked()


    def reload_item(self):
        self.current_shop_index = self.shop_list.currentIndex()
        for item_index in range(Shop.NB_ITEM_PER_SHOP):
            with QSignalBlocker(self.item_combo[item_index]):
                item_id = self.tonberry_manager.shop_info[self.current_shop_index].item_ids[item_index]
                combo = self.item_combo[item_index]
                if combo.findData(item_id) < 0:
                    combo.addItem(f"{item_id}: Item {item_id}", item_id)
                combo.setCurrentIndex(combo.findData(item_id))
            with QSignalBlocker(self.item_rare[item_index]):
                self.item_rare[item_index].setChecked(
                    self.tonberry_manager.shop_info[self.current_shop_index].rare[item_index])
        self.__update_image()

    def __update_image(self):
        self.image_location = QPixmap(os.path.join(self._resource_folder, self.IMAGE_LIST[self.current_shop_index]))
        self.image_location_drawer.setPixmap(self.image_location)


    def _refresh_item_names(self):
        manager = self.tonberry_manager
        manager.item_values = dict(manager._baseline_item_values)
        manager.item_values.update({i: name or f"Item {i}" for i, name in self.item_files.names.items()})
        for shop in manager.shop_info:
            for slot, item_id in enumerate(shop.item_ids):
                manager.item_values.setdefault(item_id, f"Item {item_id}")
                shop.item[slot] = manager.item_values[item_id]
        for combo in self.item_combo:
            item_id = combo.currentData()
            with QSignalBlocker(combo):
                combo.clear()
                for value, name in sorted(manager.item_values.items()):
                    combo.addItem(f"{value}: {name}", value)
                combo.setCurrentIndex(max(0, combo.findData(item_id)))
        if self.file_path:
            self.reload_item()

