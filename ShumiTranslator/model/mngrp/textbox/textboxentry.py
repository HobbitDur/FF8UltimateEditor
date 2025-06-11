from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData
from FF8GameData.GenericSection.listff8text import ListFF8Text


class TextBoxEntry(Section):
    TEXT_BOX_ID_SIZE = 2
    ENTRY_LENGTH = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, name: str):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self._text_box_origin_id = int.from_bytes(self._data_hex[0:self.TEXT_BOX_ID_SIZE], byteorder='little')
        self._text_box_left_id = int.from_bytes(self._data_hex[self.TEXT_BOX_ID_SIZE:self.TEXT_BOX_ID_SIZE * 2], byteorder='little')
        self._text_box_right_id = int.from_bytes(self._data_hex[self.TEXT_BOX_ID_SIZE * 2:self.TEXT_BOX_ID_SIZE * 3], byteorder='little')
        self._length = int.from_bytes(self._data_hex[self.TEXT_BOX_ID_SIZE * 3:self.TEXT_BOX_ID_SIZE * 3 + self.ENTRY_LENGTH],
                                      byteorder='little') + 1
        text_data_hex = self._data_hex[self.TEXT_BOX_ID_SIZE * 3 + self.ENTRY_LENGTH:]
        offset_end_title = text_data_hex.index(b'\x00')
        self._text_section = ListFF8Text(game_data=game_data, data_hex=text_data_hex, id=0, own_offset=0, name="", cursor_location_size=3)
        self._text_section.init_text([0, offset_end_title])

    def __str__(self):
        return (
            f"SectionComplexStringEntry: Ori:{self._text_box_origin_id} - left:{self._text_box_left_id} - right:{self._text_box_right_id} - length:{self._length} - text_section: {self._text_section}")

    def __repr__(self):
        return self.__str__()

    def get_text_section(self):
        return self._text_section

    def get_text_list(self):
        return self._text_section.get_text_list()

    def update_data_hex(self):
        self._data_hex = bytearray()
        self._data_hex.extend(self._text_box_origin_id.to_bytes(length=self.TEXT_BOX_ID_SIZE, byteorder='little'))
        self._data_hex.extend(self._text_box_left_id.to_bytes(length=self.TEXT_BOX_ID_SIZE, byteorder='little'))
        self._data_hex.extend(self._text_box_right_id.to_bytes(length=self.TEXT_BOX_ID_SIZE, byteorder='little'))
        self._text_section.update_data_hex()
        self._length = len(self._text_section) + self.ENTRY_LENGTH + self.TEXT_BOX_ID_SIZE*3 - 1
        title =  self._text_section.get_text_list()[0].get_data_hex()
        text =  self._text_section.get_text_list()[1].get_data_hex()
        self._data_hex.extend(self._length.to_bytes(length=self.ENTRY_LENGTH, byteorder='little'))
        self._data_hex.extend(title)
        self._data_hex.extend(text)
        self._size = len(self._data_hex)

