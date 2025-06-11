import os

from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSpinBox, QLabel, QHBoxLayout, QComboBox

from CCGroup.card import Card


class CardWidget(QWidget):
    TILES_WIDTH_EL = 100
    TILES_HEIGHT_EL = 100

    def __init__(self, card: Card):
        QWidget.__init__(self)
        self.card = card
        self.__main_layout = QHBoxLayout()
        self.setLayout(self.__main_layout)

        self.__left_value_widget = QSpinBox()
        self.__left_value_widget.setMaximum(10)
        self.__left_value_widget.setValue(self.card.left_value)
        self.__left_value_widget.wheelEvent = lambda event: None
        self.__left_value_widget.valueChanged.connect(self.__left_changed)
        self.__right_value_widget = QSpinBox()
        self.__right_value_widget.setMaximum(10)
        self.__right_value_widget.setValue(self.card.right_value)
        self.__right_value_widget.wheelEvent = lambda event: None
        self.__right_value_widget.valueChanged.connect(self.__right_changed)
        self.__down_value_widget = QSpinBox()
        self.__down_value_widget.setMaximum(10)
        self.__down_value_widget.setValue(self.card.down_value)
        self.__down_value_widget.wheelEvent = lambda event: None
        self.__down_value_widget.valueChanged.connect(self.__down_changed)
        self.__top_value_widget = QSpinBox()
        self.__top_value_widget.setMaximum(10)
        self.__top_value_widget.setValue(self.card.top_value)
        self.__top_value_widget.wheelEvent = lambda event: None
        self.__top_value_widget.valueChanged.connect(self.__top_changed)

        self.__card_image_location_drawer = QLabel()
        self.__card_image_location_drawer.setPixmap(self.card.get_image())

        self.__name_label_widget = QLabel("Name: " + self.card.get_name())

        self.__power_label_widget = QLabel("Power")
        self.__power_label_widget.setToolTip("When game is lost, the PNJ take the card with the highest level")
        self.__power_value_widget = QSpinBox()
        self.__power_value_widget.setMaximum(255)
        self.__power_value_widget.setValue(self.card.power_value)
        self.__power_value_widget.wheelEvent = lambda event: None
        self.__power_value_widget.valueChanged.connect(self.__power_changed)

        self.__elemental_label_widget = QLabel("Elemental: ")
        self.__elemental_widget = QComboBox()
        for el in self.card.game_data.card_data_json["card_type"]:
            self.__elemental_widget.addItem(QIcon(QPixmap.fromImage(ImageQt(el["img"]))), el["name"])
        self.__elemental_widget.wheelEvent = lambda event: None
        self.__elemental_widget.currentIndexChanged.connect(self.__elemental_changed)

        self.__element_layout = QHBoxLayout()
        self.__element_layout.addWidget(self.__elemental_label_widget)
        self.__element_layout.addWidget(self.__elemental_widget)

        self.__power_layout = QHBoxLayout()
        self.__power_layout.addWidget(self.__power_label_widget)
        self.__power_layout.addWidget(self.__power_value_widget)

        self.__left_layout = QVBoxLayout()
        self.__middle_layout = QVBoxLayout()
        self.__right_layout = QVBoxLayout()
        self.__text_layout = QVBoxLayout()
        self.__main_layout.addLayout(self.__left_layout)
        self.__main_layout.addLayout(self.__middle_layout)
        self.__main_layout.addLayout(self.__right_layout)
        self.__main_layout.addSpacing(20)
        self.__main_layout.addLayout(self.__text_layout)
        self.__main_layout.addStretch(1)

        self.__left_layout.addStretch(1)
        self.__left_layout.addWidget(self.__left_value_widget)
        self.__left_layout.addStretch(1)

        self.__middle_layout.addStretch(1)
        self.__middle_layout.addWidget(self.__top_value_widget)
        self.__middle_layout.addWidget(self.__card_image_location_drawer)
        self.__middle_layout.addWidget(self.__down_value_widget)
        self.__middle_layout.addStretch(1)

        self.__right_layout.addStretch(1)
        self.__right_layout.addWidget(self.__right_value_widget)
        self.__right_layout.addStretch(1)

        self.__text_layout.addStretch(1)
        self.__text_layout.addWidget(self.__name_label_widget)
        self.__text_layout.addLayout(self.__power_layout)
        self.__text_layout.addLayout(self.__element_layout)
        self.__text_layout.addStretch(1)

    def change_card_mod(self, mod:int, size):
        self.card.change_card_mod(mod, size)
        self.__card_image_location_drawer.setPixmap(self.card.get_image())
        self.__name_label_widget.setText("Name: " + self.card.get_name())

    def __top_changed(self):
        self.card.top_value = self.__top_value_widget.value()

    def __down_changed(self):
        self.card.down_value = self.__down_value_widget.value()

    def __left_changed(self):
        self.card.left_value = self.__left_value_widget.value()

    def __right_changed(self):
        self.card.right_value = self.__right_value_widget.value()

    def __power_changed(self):
        self.card.power_value = self.__power_value_widget.value()

    def __elemental_changed(self):
        self.card.set_elemental([x['id'] for x in self.card.game_data.card_data_json['card_type'] if x['name'] == self.__elemental_widget.currentText()][0])
