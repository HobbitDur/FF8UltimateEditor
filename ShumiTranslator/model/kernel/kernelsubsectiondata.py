from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData
from ShumiTranslator.model.general.ff8data import FF8Data


class SubSectionData(Section):
    OFFSET_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, nb_text_offset: int):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name="")
        self._nb_text_offset = nb_text_offset
        self._data_list = []
        self._analyze_data()

    def _analyze_data(self):
        """We consider the subsection to have N+1 data, with N data of offset and 1 big data of whatever (the offset are always at the beggining)"""
        for i in range(self._nb_text_offset):
            self.add_data(self._data_hex[i * self.OFFSET_SIZE: self.OFFSET_SIZE * (i + 1)], offset_type=True)
        self.add_data(self._data_hex[(self._nb_text_offset * self.OFFSET_SIZE):], offset_type=False)

    def add_data(self, data_hex, offset_type=False):
        if self._data_list:
            offset = self._data_list[-1].own_offset + self._data_list[-1].get_size()
            id = self._data_list[-1].id + 1
        else:
            offset = 0
            id = 0
        self._data_list.append(FF8Data(game_data=self._game_data, data_hex=data_hex, own_offset=offset, id=id, offset_type=offset_type))



    def get_all_offset(self):
        offset_list = []
        for data in self._data_list:
            offset = data.get_offset_value()
            if offset is not None:
                offset_list.append(offset)
        return offset_list

    def nb_data_with_offset(self):
        nb_data = 0
        for kernel_data in self._data_list:
            if kernel_data.get_offset_type():
                nb_data += 1
        return nb_data

    def set_offset_values(self, text_list, last_offset):
        if len(text_list) != self.nb_data_with_offset():
            print(
                f"The size of the offset list ({len(text_list)}) is different than the nb of offset data of the subsection ({self.nb_data_with_offset()})")

        current_subsection_offset = last_offset
        for i in range(len(text_list)):  # Assuming offset data is always at the beginning of the subsection
            text_size = len(text_list[i])
            self._data_list[i].set_offset_value(current_subsection_offset)
            current_subsection_offset += text_size

        # Updating subsection data
        self._data_hex = bytearray()
        for data in self._data_list:
            self._data_hex.extend(data.get_data_hex())
        self._size = len(self._data_hex)

        return current_subsection_offset

    def get_data_list(self):
        return self._data_list

    def set_offset_from_id(self, data_id, value: int):
        self._data_list[data_id].set_offset_value(value)
