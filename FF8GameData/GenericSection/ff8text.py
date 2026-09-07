from .section import Section
from ..gamedata import GameData, SectionType

# Two characters sequences that the game can store on a single byte, written as a {tag} in the editor.
COMPRESS_LIST = ["{in}", "{e }", "{ne}", "{to}", "{re}", "{HP}", "{l }", "{ll}", "{GF}", "{nt}", "{il}", "{o }",
                 "{ef}", "{on}", "{ w}", "{ r}", "{wi}", "{fi}", "{EC}", "{s }", "{ar}", "{FE}", "{ S}", "{ag}"]


def split_tag(text: str):
    """Split text into (part, is_tag) couples, a tag being anything between { and }.

    Compression must never modify what is inside a tag, as {Yellow} would for example
    become {Ye{ll}ow}, which is not a valid tag anymore.
    """
    part_list = []
    index = 0
    while index < len(text):
        start_tag = text.find('{', index)
        end_tag = text.find('}', start_tag + 1) if start_tag != -1 else -1
        if start_tag == -1 or end_tag == -1:  # No tag left, all the rest is plain text
            part_list.append((text[index:], False))
            break
        if start_tag > index:
            part_list.append((text[index:start_tag], False))
        part_list.append((text[start_tag:end_tag + 1], True))
        index = end_tag + 1
    return part_list


class FF8Text(Section):
    def __init__(self, game_data: GameData, own_offset: int, data_hex: bytearray, id: int, cursor_location_size=2, first_hex_literal=False):
        Section.__init__(self, game_data=game_data, own_offset=own_offset, data_hex=data_hex, id=id, name="")
        self._cursor_location_size = cursor_location_size
        self._text_str = self._game_data.translate_hex_to_str(self._data_hex,
                                                              cursor_location_size=self._cursor_location_size, first_hex_literal=first_hex_literal)
        self.set_str(self._text_str)  # To remove unwanted 0 for example
        self.type = SectionType.FF8_TEXT

    def __str__(self):
        return self.get_str()

    def __repr__(self):
        return f"FF8Text({self._text_str})"  # - Hex: {self._data_hex.hex(sep=" ")}"

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

        for compress_el in COMPRESS_LIST:
            char_couple = compress_el[1:-1]
            new_str = ""
            for part, is_tag in split_tag(self._text_str):
                if is_tag:  # Already a tag ({in} or {Yellow}), leaving it untouched
                    new_str += part
                else:
                    new_str += part.replace(char_couple, compress_el)
            if new_str != self._text_str:
                self.set_str(new_str)

    def uncompress_str(self):
        for compress_el in COMPRESS_LIST:
            if compress_el not in self._text_str:
                continue
            self.set_str(self._text_str.replace(compress_el, compress_el[1:-1]))
