"""The SeeD written test sections of mngrp.bin (raw header entries 95-126, sections 42-73).

Entry 95 is the shared exam UI text, entries 96-125 the tests 1-30 (10 questions each, the
engine loads entry 96 + test number), entry 126 an unused "test 31" duplicate of test 30. Each
string is {u8 expected answer, FF8 text, 0x00}, zero-padded to 4 bytes: not a plain mngrp string,
so MngrpManager reads these sections with this class, and every tool (Shiva's SeeD tab, the Shiva
CLI, ShumiTranslator) edits and writes them the same way.
"""
import re

from FF8GameData.GenericSection.ff8text import FF8Text
from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType

# FF8 text codes followed by one parameter byte (the parameter must be skipped
# when scanning for cursor stops, it could be 0x0B itself).
_TWO_BYTE_CODES = (0x03, 0x04, 0x05, 0x06, 0x09, 0x0B, 0x0C, 0x0E, 0x19, 0x1A, 0x1B)

_CURSOR_MARKER_RE = re.compile(r"\{Cursor_location_id:0x([0-9a-fA-F]{2})\}")
_ANSWER_PREFIX_RE = re.compile(r"\{x([0-9a-fA-F]{2})\}")


class SeedText(FF8Text):
    """The text of a SeeD string, without its answer byte: what a translator edits.

    Its bytes are kept as loaded and only re-encoded when the text is changed, so an untouched
    string saves back byte-exactly."""

    def __init__(self, game_data: GameData, text_hex: bytearray, id=0):
        FF8Text.__init__(self, game_data=game_data, own_offset=0, data_hex=bytearray(text_hex), id=id,
                         cursor_location_size=2, terminate_empty=True, special_value_context="seed_test")
        self._data_hex = bytearray(text_hex) + b"\x00"
        self._size = len(self._data_hex)

    def set_str(self, text: str):
        if text == self._text_str:  # Don't lose the original bytes on a no-op
            return
        FF8Text.set_str(self, text)


class SeedString:
    """One string of a SeeD test section: {u8 expected answer, FF8 text}.

    The engine reads the first byte as the expected answer (0-based cursor-stop
    index: 0 = YES, 1 = NO on the standard questions) and displays the FF8 text
    after it. The text marks each selectable choice with a 0x0B n cursor-stop
    code (n = 0x20 + choice index, {Cursor_location_id:0xnn} in the codec); the
    engine counts the stops at display time, so adding a stop adds a choice.
    """
    CURSOR_STOP_CODE = 0x0B
    CURSOR_STOP_BASE = 0x20
    STRING_PADDING = 4  # answer + text + 0x00 terminator, zero-padded to 4 bytes

    def __init__(self, game_data: GameData, answer=0, text_hex=bytearray(), id=0):
        self.answer = answer
        self.text = SeedText(game_data, text_hex, id)

    def __str__(self):
        return f"SeedString(answer: {self.answer}, text: {self.get_text()})"

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_bytes(cls, game_data: GameData, string_hex: bytearray, id=0):
        """Parse {answer byte, FF8 text, 0x00 terminator (+ alignment padding)}."""
        answer = string_hex[0]
        terminator = string_hex.find(0x00, 1)
        if terminator == -1:
            terminator = len(string_hex)
        return cls(game_data=game_data, answer=answer, text_hex=string_hex[1:terminator], id=id)

    def to_bytes(self):
        string_hex = bytearray([self.answer])
        string_hex.extend(self.text.get_data_hex())  # ends with its 0x00 terminator
        while len(string_hex) % self.STRING_PADDING != 0:
            string_hex.append(0x00)
        return string_hex

    def get_text(self):
        return self.text.get_str()

    def set_text(self, text: str):
        self.text.set_str(text)

    def get_cursor_stops(self):
        """The 0x0B parameters in text order (0x20 = choice 0, 0x21 = choice 1...)."""
        text_hex = self.text.get_data_hex()[:-1]
        stops = []
        i = 0
        while i < len(text_hex):
            code = text_hex[i]
            if code in _TWO_BYTE_CODES:
                if code == self.CURSOR_STOP_CODE and i + 1 < len(text_hex):
                    stops.append(text_hex[i + 1])
                i += 2
            else:
                i += 1
        return stops

    def get_choices(self):
        """[(stop value, display snippet), ...]: the text following each cursor stop."""
        text = self.get_text()
        choices = []
        matches = list(_CURSOR_MARKER_RE.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            snippet = text[match.end():end]
            snippet = re.sub(r"\{[^}]*\}", "", snippet)  # Drop the remaining {codes}
            snippet = snippet.replace("\\n", " ")  # The codec renders line breaks as a literal \n
            snippet = " ".join(snippet.split())  # Collapse whitespace
            choices.append((int(match.group(1), 16), snippet))
        return choices

    def add_choice(self, choice_text="New choice"):
        """Append a new cursor stop (next free index) and its text on a new line."""
        next_stop = self.CURSOR_STOP_BASE + len(self.get_cursor_stops())
        self.set_text(self.get_text() + "\n{{Cursor_location_id:0x{:02x}}}{}".format(next_stop, choice_text))


class SeedRowText:
    """A SeeD string as a text editor shows it: the answer byte as a leading {xNN}, then the text.

    That is the form ShumiTranslator always had (and its CSV files hold), so a translator still
    sets the expected answer by editing that prefix. Writing a row without the prefix keeps the
    answer."""

    def __init__(self, seed_string: SeedString):
        self.seed_string = seed_string
        self.id = seed_string.text.id

    def __str__(self):
        return self.get_str()

    def get_str(self):
        return "{{x{:02x}}}".format(self.seed_string.answer) + self.seed_string.get_text()

    def set_str(self, text: str):
        prefix = _ANSWER_PREFIX_RE.match(text)
        if prefix:
            self.seed_string.answer = int(prefix.group(1), 16)
            text = text[prefix.end():]
        self.seed_string.set_text(text)

    def compress_str(self, compressible=3):
        self.seed_string.text.compress_str(compressible)

    def uncompress_str(self):
        self.seed_string.text.uncompress_str()


class SectionSeedTest(Section):
    """One SeeD test section: {u16 count, u16 offsets[count], SeedString...}."""
    HEADER_SIZE = 2
    OFFSET_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, name=""):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self.type = SectionType.MNGRP_SEED_TEST
        self.strings = self.__parse(bytearray(data_hex))  # [SeedString], one per question for a test
        self._rows = [SeedRowText(seed_string) for seed_string in self.strings]

    def __parse(self, section_hex):
        nb_string = int.from_bytes(section_hex[0:self.HEADER_SIZE], byteorder='little')
        offset_list = []
        for index in range(nb_string):
            start = self.HEADER_SIZE + index * self.OFFSET_SIZE
            offset_list.append(int.from_bytes(section_hex[start:start + self.OFFSET_SIZE], byteorder='little'))
        strings = []
        for index, offset in enumerate(offset_list):
            end = None
            for later_offset in offset_list[index + 1:]:  # 0 would mean an unused slot
                if later_offset:
                    end = later_offset
                    break
            if end is None:  # Last string: up to its terminator (the rest is section padding)
                end = section_hex.find(0x00, offset + 1) + 1
            strings.append(SeedString.from_bytes(self._game_data, section_hex[offset:end], id=index))
        return strings

    def get_text_list(self):
        """The strings as rows of text ({xNN} answer prefix + text), for ShumiTranslator."""
        return self._rows

    def update_data_hex(self):
        string_hex_list = [seed_string.to_bytes() for seed_string in self.strings]
        section_hex = bytearray(len(string_hex_list).to_bytes(length=self.HEADER_SIZE, byteorder='little'))
        offset = self.HEADER_SIZE + self.OFFSET_SIZE * len(string_hex_list)
        for string_hex in string_hex_list:
            section_hex.extend(offset.to_bytes(length=self.OFFSET_SIZE, byteorder='little'))
            offset += len(string_hex)
        for string_hex in string_hex_list:
            section_hex.extend(string_hex)
        self._data_hex = section_hex
        self._size = len(self._data_hex)
        return self._data_hex
