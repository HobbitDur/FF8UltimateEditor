from FF8GameData.GenericSection.section import Section
from FF8GameData.GenericSection.sectiondata import SectionData
from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text


class SectionOffsetAndText(Section):
    OFFSET_SIZE = 2
    HEADER_SIZE = 2

    def __init__(self, game_data: GameData, data_hex, id=0, own_offset=0, name="", offset_size=2, nb_offset=1, ignore_empty_offset=True, nb_byte_shift=0,
                 text_offset_start_0=False):
        """text_offset_start_0 means that the first offset of the list is equal to zero as it is the offset from the text section itself.
        Usually, the offset is from the start of the file or the section containing the offset itself, so it doesn't start at 0"""
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self._offset_size = offset_size
        self._text_offset_start_0 = text_offset_start_0
        self._nb_offset = nb_offset
        self._nb_byte_shift = nb_byte_shift
        self._ignore_empty_offset = ignore_empty_offset
        self._offset_section = None
        self._text_section = None
        self.type = SectionType.OFFSET_AND_TEXT
        if data_hex:
            self.__analyse_data()
        else:
            self._offset_section = SectionData(game_data=game_data, data_hex=data_hex, id=0, own_offset=0, nb_offset=0, name="",
                                               ignore_empty_offset=ignore_empty_offset)
            self._text_section = ListFF8Text(game_data=game_data, data_hex=data_hex, id=0, own_offset=0, name="")

    def __str__(self):
        if not self.__bool__():
            return "SectionOffsetAndText(Empty)"
        return "SectionOffsetAndText(offset_section: " + str(self._offset_section) + '\n' + "text_section: " + str(self._text_section) + ")"

    def __bool__(self):
        if not self._offset_section or not self._text_section:
            return False
        else:
            return True

    def __repr__(self):
        return self.__str__()

    def update_data_hex(self):
        self._text_section.update_data_hex()
        self._offset_section.set_all_offset_by_text_list(self._text_section.get_text_list(), shift=self.OFFSET_SIZE * self._nb_offset)
        self._offset_section.update_data_hex()

        self._data_hex = bytearray()
        self._data_hex.extend(self._offset_section.get_data_hex())
        self._data_hex.extend(self._text_section.get_data_hex())
        self._size = len(self._data_hex)
        return self._data_hex

    def get_text_section(self) -> ListFF8Text:
        return self._text_section

    def get_offset_section(self) -> SectionData:
        return self._offset_section

    def __analyse_data(self):
        self._offset_section = SectionData(game_data=self._game_data,
                                           data_hex=self._data_hex[0:self._nb_offset * self._offset_size], id=0,
                                           own_offset=0, nb_offset=self._nb_offset, name=f"Offset of {self.name}",
                                           ignore_empty_offset=self._ignore_empty_offset)
        text_data_start = 0

        offset_list = self._offset_section.get_all_offset()
        if self._text_offset_start_0:
            text_data_start = self._nb_offset * self._offset_size
        else:
            for offset in offset_list:
                if offset != 0:
                    text_data_start = offset - self._nb_byte_shift
                    break

        text_data = self._data_hex[text_data_start:len(self._data_hex)]
        self._text_section = ListFF8Text(game_data=self._game_data, data_hex=text_data, id=self.id, own_offset=text_data_start, name=self.name,
                                         section_data_linked=self._offset_section)
        self._text_section.section_data_linked.section_text_linked = self._text_section

        if self._text_offset_start_0:
            self._text_section.init_text(offset_list)
        else:
            # The original offset start from the start of the section, so we need to shift them for the text offset.
            offset_text_list = []
            for i in range(len(offset_list)):
                if offset_list[i] != 0:
                    offset_text_list.append(offset_list[i] - text_data_start - self._nb_byte_shift)
            self._text_section.init_text(offset_text_list)

    def get_text_list(self):
        return self._text_section.get_text_list()
