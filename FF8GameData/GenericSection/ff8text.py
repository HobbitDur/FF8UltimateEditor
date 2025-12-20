from .section import Section
from ..gamedata import GameData, SectionType


class FF8Text(Section):
    def __init__(self, game_data: GameData, own_offset: int, data_hex: bytearray, id: int, cursor_location_size=2, first_hex_literal=False):
        Section.__init__(self, game_data=game_data, own_offset=own_offset, data_hex=data_hex, id=id, name="")
        self._cursor_location_size = cursor_location_size
        self._text_str = self._game_data.translate_hex_to_str(self._data_hex,
                                                              cursor_location_size=self._cursor_location_size, first_hex_literal=first_hex_literal)
        self.set_str(self._text_str)  # To remove unwanted 0 for example
        self.type = SectionType.FF8_TEXT

    def __str__(self):
        return f"FF8Text({self._text_str})"  # - Hex: {self._data_hex.hex(sep=" ")}"

    def __repr__(self):
        return self.__str__()

    def __add__(self, other):
        if self.own_offset <= other.own_offset:
            own_offset = self.own_offset
            data_hex = self._data_hex
            data_hex.extend(other._data_hex)
            new_id = self.id
            new_cursor_location_size = self._cursor_location_size
        else:
            own_offset = other.own_offset
            data_hex = other.get_data_hex()
            data_hex.extend(self._data_hex)
            new_id = other.id
            new_cursor_location_size = other._cursor_location_size

        return FF8Text(game_data=self._game_data, own_offset=own_offset, data_hex=data_hex, id=new_id,
                       cursor_location_size=new_cursor_location_size)

    def get_str(self):
        return self._text_str

    def set_str(self, text: str):
        converted_data_list = self._game_data.translate_str_to_hex(text)
        self._data_hex = bytearray(converted_data_list)
        self._text_str = text
        if text != "":  # If empty don't put \x00
            self._data_hex.extend([0x00])
        self._size = len(self._data_hex)

    def compress_str(self, compressible=3):
        if compressible == 0:  # Not compressible
            return
        if compressible == 2 and self.id % 2 == 0:  # Only second is compressible but we are id 0 of the subsection
            return
        if compressible == 1 and self.id % 2 == 1:  # Only first is compressible but we are id 1 of the subsection (not 0)
            return

        compress_list = ["{in}", "{e }", "{ne}", "{to}", "{re}", "{HP}", "{l }", "{ll}", "{GF}", "{nt}", "{il}", "{o }",
                         "{ef}", "{on}", "{ w}", "{ r}", "{wi}", "{fi}", "{EC}", "{s }", "{ar}", "{FE}", "{ S}", "{ag}"]
        for compress_el in compress_list:
            if compress_el[1:-1] not in self._text_str:
                continue
            new_str_double_bracket = self._text_str.replace(compress_el[1:-1], compress_el)
            new_str_double_bracket = new_str_double_bracket.replace('{{', '{')
            new_str_double_bracket = new_str_double_bracket.replace('}}', '}')
            self.set_str(new_str_double_bracket)

    def uncompress_str(self):
        compress_list = ["{in}", "{e }", "{ne}", "{to}", "{re}", "{HP}", "{l }", "{ll}", "{GF}", "{nt}", "{il}", "{o }",
                         "{ef}", "{on}", "{ w}", "{ r}", "{wi}", "{fi}", "{EC}", "{s }", "{ar}", "{FE}", "{ S}", "{ag}"]
        for compress_el in compress_list:
            if compress_el not in self._text_str:
                continue
            self.set_str(self._text_str.replace(compress_el, compress_el[1:-1]))
