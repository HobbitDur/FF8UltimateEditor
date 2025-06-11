from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType
from ShumiTranslator.model.mngrp.textbox.textboxentry import TextBoxEntry


class SectionTextBoxEntry(Section):

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, name: str):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self.string_entry_list = []
        self.type = SectionType.MNGRP_TEXTBOX

    def __str__(self):
        return f"SectionComplexStringEntry: {self.string_entry_list}"

    def __repr__(self):
        return self.__str__()

    def init_section(self, offset_map_list):
        for i, offset in enumerate(offset_map_list):
            if i == len(offset_map_list) - 1:
                next_offset = self._size
            else:
                next_offset = offset_map_list[i + 1]
            new_entry = TextBoxEntry(game_data=self._game_data, data_hex=self._data_hex[offset:next_offset], id=i, own_offset=offset, name="")
            self.string_entry_list.append(new_entry)

    def get_text_list(self):
        entry_list = []
        for entry in self.string_entry_list:
            entry_list.extend(entry.get_text_section().get_text_list())
        return entry_list

    def get_nb_entry_section(self):
        return len(self.string_entry_list)

    def get_entry_section_by_id(self, id):
        return self.string_entry_list[id]

    def get_concatenate_text_list(self):
        entry_list = []
        for entry in self.string_entry_list:
            entry_list.append(entry.get_text_section().get_text_list()[0]+entry.get_text_section().get_text_list()[1])
        return entry_list

    def update_data_hex(self):
        self._data_hex = bytearray()
        for string in self.string_entry_list:
            string.update_data_hex()
            self._data_hex.extend(string.get_data_hex())
        self._size = len(self._data_hex)


