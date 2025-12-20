from ..gamedata import GameData, SectionType


class Section:
    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, name: str=""):
        self._data_hex = data_hex
        self._size = len(self._data_hex)
        self.id = id
        self._game_data = game_data
        self.own_offset = own_offset
        self.name = name
        self.type = SectionType.DATA

    def get_size(self):
        return self._size

    def __len__(self):
        return self._size

    def __str__(self):
        return f"Section(OwnOffet: {self.own_offset}, data_hex: {self._data_hex.hex(sep=" ", bytes_per_sep=1)})"

    def get_data_hex(self):
        return self._data_hex

    def _set_data_hex(self, new_data_hex):
        self._data_hex = new_data_hex
        self._size = len(self._data_hex)

    def update_data_hex(self):
        self._size = len(self._data_hex)

    def fill(self, fill_value=256):
        while len(self._data_hex)%fill_value != 0:
            self._data_hex.extend([0x00])
        self._size = len(self._data_hex)

