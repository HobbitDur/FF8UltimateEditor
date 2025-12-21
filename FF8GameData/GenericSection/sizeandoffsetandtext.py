from sys import byteorder

from .offsetandtext import SectionOffsetAndText
from .section import Section
from ..gamedata import GameData, SectionType
from .listff8text import ListFF8Text


class SectionSizeAndOffsetAndText(Section):

    def __init__(self, game_data: GameData, data_hex, id=0, own_offset=0, name="", nb_offset_size = 2, offset_size=2, ignore_empty_offset=True):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self._nb_offset = int.from_bytes(self._data_hex[0:nb_offset_size], byteorder="little")
        self._section = SectionOffsetAndText( game_data, data_hex[nb_offset_size:], id=id, own_offset=nb_offset_size, name=name, offset_size=offset_size, nb_offset=self._nb_offset, ignore_empty_offset=ignore_empty_offset, nb_byte_shift=2)
        self._ignore_empty_offset = ignore_empty_offset
        self.type = SectionType.SIZE_AND_OFFSET_AND_TEXT

    def __str__(self):
        if not self.__bool__():
            return "SectionSizeAndOffsetAndText(Empty)"
        return f"SectionSizeAndOffsetAndText({str(self._section)})"

    def __bool__(self):
        if not self._section:
            return False
        else:
            return True

    def __repr__(self):
        return self.__str__()

    def update_data_hex(self):
        self._section.update_data_hex()

        self._data_hex = bytearray()
        self._data_hex.extend(self._nb_offset.to_bytes(byteorder='little', length=2))
        self._data_hex.extend(self._section.get_data_hex())
        self._size = len(self._data_hex)
        return self._data_hex

    def get_text_section(self) -> ListFF8Text:
        return self._section.get_text_section()

    def get_offset_section(self):
        return self._section.get_offset_section()