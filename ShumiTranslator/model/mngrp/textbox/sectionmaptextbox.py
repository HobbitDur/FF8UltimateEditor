from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType


class SeekLocationInfo:
    def __init__(self, seek_location: int, section_number: int):
        self.seek_location = seek_location
        self.section_number = section_number

    def __str__(self):
        return f"Seek_location: {str(self.seek_location)} - Section_number: {str(self.section_number)}"

    def __repr__(self):
        return self.__str__()


class SectionMapTextBox(Section):
    OFFSET_SIZE = 2
    HEADER_SIZE = 4
    SEEK_LOCATION_SIZE = 2
    SEEK_SECTION_NB_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, name: str):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self._nb_seek_location = int.from_bytes(self._data_hex[0:self.HEADER_SIZE], byteorder="little")
        self._seek_location_info_list = []
        for i in range(self._nb_seek_location):
            seek_location = int.from_bytes(self._data_hex[self.HEADER_SIZE + (
                        self.SEEK_LOCATION_SIZE + self.SEEK_SECTION_NB_SIZE) * i:self.HEADER_SIZE + (
                    self.SEEK_LOCATION_SIZE + self.SEEK_SECTION_NB_SIZE) * i + self.SEEK_LOCATION_SIZE],
                                           byteorder="little")
            section_number = int.from_bytes(self._data_hex[self.HEADER_SIZE + (
                    self.SEEK_LOCATION_SIZE + self.SEEK_SECTION_NB_SIZE) * i + self.SEEK_LOCATION_SIZE:self.HEADER_SIZE + (
                    self.SEEK_LOCATION_SIZE + self.SEEK_SECTION_NB_SIZE) * i + self.SEEK_LOCATION_SIZE + self.SEEK_SECTION_NB_SIZE],
                                            byteorder="little")
            self._seek_location_info_list.append(SeekLocationInfo(seek_location, section_number))
        self.type = SectionType.MNGRP_MAP_COMPLEX_STRING

    def __str__(self):
        return f"SectionMapComplexString: nb_seek:{self._nb_seek_location} - seek_info:{self._seek_location_info_list}"

    def __repr__(self):
        return self.__str__()

    def get_offset_list_from_id(self, section_id: int):
        offset_list = []
        for location_info in self._seek_location_info_list:
            if location_info.section_number == section_id:
                offset_list.append(location_info.seek_location)
        return offset_list

    def set_offset_from_text_list(self, text_list, p_section_number, shift = 0):
        # First remove all previous data of the section
        cleared_list = []
        for i in range(len(self._seek_location_info_list)):
            if self._seek_location_info_list[i].section_number != p_section_number:
                cleared_list.append(self._seek_location_info_list[i])
        location=0
        for i in range(0, len(text_list), 2):
            new_seek_location = SeekLocationInfo(seek_location=location, section_number=p_section_number)
            location +=len(text_list[i]) + len(text_list[i+1]) + shift
            cleared_list.append(new_seek_location)

        self._seek_location_info_list = cleared_list

    def update_data_hex(self):
        self._data_hex = bytearray()
        self._data_hex.extend(self._nb_seek_location.to_bytes(length=self.HEADER_SIZE,byteorder="little"))
        for seek_location in self._seek_location_info_list:
            self._data_hex.extend(seek_location.seek_location.to_bytes(length=self.SEEK_LOCATION_SIZE, byteorder="little"))
            self._data_hex.extend(seek_location.section_number.to_bytes(length=self.SEEK_SECTION_NB_SIZE, byteorder="little"))
        self._size = len(self._data_hex)

