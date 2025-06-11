import os

from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QPixmap

from PIL import Image

from FF8GameData.gamedata import GameData


class Card():
    TILES_WIDTH = 64
    TILES_WIDTH_EL = 128
    TILES_HEIGHT = 64
    TILES_HEIGHT_EL = 128

    def __init__(self, game_data: GameData, id: int, offset: int, data_hex: bytearray, mod:int=0, card_size=64):
        self.offset = offset
        self.game_data = game_data
        self._name = ""
        self._id = id
        self.top_value = 0
        self.down_value = 0
        self.left_value = 0
        self.right_value = 0
        self._elem_int = 0
        self._elem_str = ""
        self.power_value = 0
        self._image = 0
        self.card_info = [x for x in self.game_data.card_data_json["card_info"] if x["id"] == self._id][0]
        self.card_el_info = {}
        self.__analyze_data(mod, data_hex, card_size)

    def __str__(self):
        return f"n°{self._id} {self._name} T:{self.top_value} D:{self.down_value} L:{self.left_value} R:{self.right_value} Type:{self._elem_str} Power:{self.power_value}"

    def __repr__(self):
        return self.__str__()

    def __analyze_data(self, mod, data_hex, card_size):
        self.top_value = data_hex[0]
        self.down_value = data_hex[1]
        self.left_value = data_hex[2]
        self.right_value = data_hex[3]
        self._elem_int = data_hex[4]
        self.__set_elemental_str()
        self.power_value = data_hex[5]
        self.card_el_info = [x for x in self.game_data.card_data_json['card_type'] if x["id"] == self._elem_int][0]
        self.change_card_mod(mod, card_size)


    def get_image(self):
        return self._image

    def get_name(self):
        return self._name

    def get_type_int(self):
        return self._elem_int

    def get_id(self):
        return self._id

    def __set_elemental_str(self):
        self._elem_str = [x["name"] for x in self.game_data.card_data_json["card_type"] if x["id"] == self._elem_int][0]

    def set_elemental(self, elem_id: int):
        self._elem_int = elem_id
        self.__set_elemental_str()

    def change_card_mod(self, mod=0, size=64):
        print(mod)
        print(self._name)
        if mod == 1:
            self._image = self.card_info["img_remaster"]
            self._name = self.card_info["name"]
        elif mod == 2:
            self._image = self.card_info["img_xylomod"]
            self._name = self.card_info["name_xylomod"]
        else:
            self._image = self.card_info["img"]
            self._name = self.card_info["name"]
        print(self._name)
        self._image = self._image.resize((size, size), Image.BILINEAR)
        self._image = QPixmap.fromImage(ImageQt(self._image))
