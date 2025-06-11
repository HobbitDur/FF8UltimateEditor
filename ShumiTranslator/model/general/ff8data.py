from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData


class FF8Data(Section):

    def __init__(self, game_data: GameData, own_offset: int, data_hex: bytearray, id: int, offset_type=False):
        Section.__init__(self, game_data=game_data, own_offset=own_offset, data_hex=data_hex, id=id, name="")
        self._offset_type = offset_type

    def __str__(self):
        return f"FF8Data(offset_type: {self._offset_type} - Data: {self._data_hex.hex(sep=" ", bytes_per_sep=1)})"

    def __repr__(self):
        return self.__str__()

    def get_size(self):
        return self._size

    def get_offset_value(self):
        """We only analyze data that have an offset, the others are garbage data"""
        if self._offset_type:
            return int.from_bytes(self._data_hex, byteorder="little")
        else:
            return None

    def set_offset_value(self, value: int):
        if not self._offset_type:
            pass #print("Can't set offset as the data is not an offset")
        elif int.from_bytes(self._data_hex) == 0xFFFF:
            pass #print("Unused data")
        else:
            self._data_hex = value.to_bytes(byteorder="little", length=len(self._data_hex))

    def get_offset_type(self):
        return self._offset_type
