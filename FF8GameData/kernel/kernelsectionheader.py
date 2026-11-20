from FF8GameData.GenericSection.ff8data import FF8Data
from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType


class SectionHeader(Section):
    OFFSET_SIZE = 4

    def __init__(self, game_data: GameData, data_hex, name):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=0, own_offset=0, name=name)
        self._data_list = []
        self.type = SectionType.KERNEL_HEADER
        self.analyze_data()

    def __str__(self):
        return f"KernelSectionHeader - Data list: {self._data_list}"

    def __repr__(self):
        return self.__str__()

    def __add_data(self, data_hex):
        if self._data_list:
            offset = self._data_list[-1].own_offset + self._data_list[-1].get_size()
            id = self._data_list[-1].id + 1
            offset_type = True
        else:
            offset = 0
            id = 0
            offset_type = False  # Only first section without an offset but with the number of section instead

        self._data_list.append(FF8Data(game_data=self._game_data, data_hex=data_hex, own_offset=offset, id=id, offset_type=offset_type))

    def analyze_data(self):
        for i in range(0, len(self._data_hex), self.OFFSET_SIZE):
            self.__add_data(self._data_hex[i:i + self.OFFSET_SIZE])
        if len(self._data_list) != len(self._game_data.kernel_data_json['sections'])+1:
            print(
                f"Problem when analyzing data, the size is not what is expected: size_list: {len(self._data_list)},"
                f" size expected: {len(self._game_data.kernel_data_json['sections'])}")

    def get_section_offset_value_from_id(self, id: int):
        # This class as the ID 0, so thats why we do the ID -1
        if id < len(self._data_list):
            return self._data_list[id].get_offset_value()  # Offset start from start of file but there is section_header first
        else:
            print(f"Section ID unknown. Id: {id}")
            return None

    def get_section_header_offset_from_id(self, id: int):
        if id < len(self._data_list):
            return self._data_list[id].own_offset
        else:
            print(f"Section ID unknown. Id: {id}")
            return None

    def set_section_offset_value_from_id(self, id: int, value: int):
        if id >= len(self._data_list):
            print(f"Section ID unknown. Id: {id}")
            return
        else:
            self._data_list[id].set_offset_value(value)
            self._data_hex = bytearray()
            for data in self._data_list:
                self._data_hex.extend(data.get_data_hex())
            self._size = len(self._data_hex)
