import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QCheckBox, QLabel, QFrame, QComboBox, QHBoxLayout, \
    QFileDialog, QLayout

from TonberryShop.tonberrymanager import TonberryManager, Shop


class TonberryShop(QWidget):
    NB_COLUMN_ITEM = 4
    IMAGE_LIST = ["pet-shop-timber.png", "shop-balamb.png", "shop-dollet.png", "shop-timber.png",
                  "shop-deling-city.png", "shop-winhill.png", "shop-horizon.png", "", "shops-esthar.png", "", "", "", "",
                  "shop-winhill-laguna.png", "", "", "shop-man-from-garden", "shops-esthar.png", "shops-esthar.png",
                  "shops-esthar.png"]

    def __init__(self, resource_folder='Resources'):

        QWidget.__init__(self)
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

        self.file_dialog = QFileDialog()
        self.file_dialog_button = QPushButton()
        self.file_dialog_button.setIcon(QIcon(os.path.join(resource_folder, 'folder.png')))
        self.file_dialog_button.setFixedSize(30, 30)
        self.file_dialog_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(resource_folder, 'save.svg')))
        self.save_button.setFixedSize(30, 30)
        self.save_button.clicked.connect(self.save_file)

        self.shop_list = QComboBox()
        self.shop_list.addItems(self.tonberry_manager.SHOP_NAME_LIST)
        self.shop_list.activated.connect(self.reload_item)

        self.item_combo = [QComboBox() for i in range(Shop.NB_ITEM_PER_SHOP)]
        self.item_rare = [QCheckBox("Rare") for i in range(Shop.NB_ITEM_PER_SHOP)]
        [rare.setLayoutDirection(Qt.LayoutDirection.RightToLeft) for rare in self.item_rare]
        self.item_label = [QLabel(f"Item n°{i + 1}: ") for i in range(Shop.NB_ITEM_PER_SHOP)]
        self.layout_single_item = [QHBoxLayout() for i in range(Shop.NB_ITEM_PER_SHOP)]
        for i in range(Shop.NB_ITEM_PER_SHOP):
            self.item_combo[i].addItems(list(self.tonberry_manager.item_values.values()))
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


        self.layout_top.addWidget(self.file_dialog_button)
        self.layout_top.addWidget(self.save_button)
        self.layout_top.addWidget(self.shop_list)
        self.layout_top.addStretch(1)

        self.layout_main.addLayout(self.layout_top)
        self.layout_main.addLayout(self.layout_item)
        self.layout_main.addLayout(self.image_location_layout)
        self.layout_main.addStretch(1)

        self.setLayout(self.layout_main)
        #self.show()

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search shop.bin file", filter="*.bin",
                                                     directory=os.getcwd())[0]
        if file_name:
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
        for item_index in range(Shop.NB_ITEM_PER_SHOP):
            self.tonberry_manager.shop_info[self.current_shop_index].item[item_index] = self.item_combo[
                item_index].currentText()
            self.tonberry_manager.shop_info[self.current_shop_index].rare[item_index] = self.item_rare[
                item_index].isChecked()


    def reload_item(self):
        self.current_shop_index = self.shop_list.currentIndex()
        for item_index in range(Shop.NB_ITEM_PER_SHOP):
            with QSignalBlocker(self.item_combo[item_index]):
                self.item_combo[item_index].setCurrentText(
                    self.tonberry_manager.shop_info[self.current_shop_index].item[item_index])
            with QSignalBlocker(self.item_rare[item_index]):
                self.item_rare[item_index].setChecked(
                    self.tonberry_manager.shop_info[self.current_shop_index].rare[item_index])
        self.__update_image()

    def __update_image(self):
        self.image_location = QPixmap(os.path.join(self._resource_folder, self.IMAGE_LIST[self.current_shop_index]))
        self.image_location_drawer.setPixmap(self.image_location)

