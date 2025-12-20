from FF8GameData.GenericSection.ff8data import FF8Data
from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData

from FF8GameData.GenericSection.listff8text import ListFF8Text


class SectionData(Section):
    OFFSET_SIZE = 2
    HEADER_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, nb_offset: int, name: str,
                 section_text_linked: ListFF8Text = None, ignore_empty_offset=True):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self.section_text_linked = section_text_linked
        self._nb_offset = nb_offset
        self._offset_list = []
        self.__analyse_data(nb_offset, ignore_empty_offset)

    def __str__(self):
        return f"SectionData({str(self._offset_list)})"

    def __repr__(self):
        self.__str__()

    def __bool__(self):
        return bool(self._offset_list)

    def __analyse_data(self, nb_offset, ignore_empty_offset=True):
        for i in range(nb_offset):
            data_offset = self._data_hex[i * self.OFFSET_SIZE:(i + 1) * self.OFFSET_SIZE]
            if ignore_empty_offset and bytes(data_offset) == bytes(b'\x00\x00'):
                continue
            new_data = FF8Data(game_data=self._game_data, own_offset=i * self.OFFSET_SIZE,
                               data_hex=data_offset, id=i,
                               offset_type=True)
            self._offset_list.append(new_data)
        self._nb_offset = len(self._offset_list)  # As some offset are ignored, changing the nb of offset

    def get_all_offset(self):
        offset_list = []
        for ff8_data in self._offset_list:
            offset_list.append(ff8_data.get_offset_value())
        return offset_list

    def set_all_offset_by_text_list(self, text_list, shift=0):
        if len(text_list) != self._nb_offset:
            print(
                f"The size of the text list ({len(text_list)}) is different than the nb of offset ({self._nb_offset})")

        new_list = []
        index_value_list = 0
        current_offset = shift
        for i in range(len(self._offset_list)):  # Assuming offset data is always at the beginning of the subsection
            if self._offset_list[i].get_offset_value() == 0:
                new_hex = bytes([0, 0])
            else:
                new_hex = current_offset.to_bytes(length=self.OFFSET_SIZE, byteorder='little')
                current_offset += len(text_list[index_value_list])
                index_value_list += 1
            new_data = FF8Data(game_data=self._game_data, own_offset=i * self.OFFSET_SIZE,
                               data_hex=new_hex, id=i,
                               offset_type=True)
            new_list.append(new_data)
        self._offset_list = new_list

    def set_all_offset_by_value_list(self, value_list):
        if len(value_list) != self._nb_offset:
            print(
                f"The size of the value list ({len(value_list)}) is different than the nb of offset ({self._nb_offset})")
        new_list = []
        index_value_list = 0
        for i in range(len(self._offset_list)):  # Assuming offset data is always at the beginning of the subsection
            if self._offset_list[i].get_offset_value() == 0:
                new_hex = bytes([0, 0])
            else:
                new_hex = value_list[index_value_list].to_bytes(length=self.OFFSET_SIZE, byteorder='little')
                index_value_list += 1
            new_data = FF8Data(game_data=self._game_data, own_offset=self.HEADER_SIZE + i * self.OFFSET_SIZE,
                               data_hex=new_hex, id=i,
                               offset_type=True)
            new_list.append(new_data)
        self._offset_list = new_list

    def update_data_hex(self):
        self._data_hex = bytearray()
        for data in self._offset_list:
            self._data_hex.extend(data.get_data_hex())
        self._size = len(self._data_hex)
