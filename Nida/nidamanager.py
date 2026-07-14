import os
import re

from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd
from FF8GameData.gamedata import GameData

# FF8 text codes followed by one parameter byte (the parameter must be skipped
# when scanning for cursor stops, it could be 0x0B itself).
_TWO_BYTE_CODES = (0x03, 0x04, 0x05, 0x06, 0x09, 0x0B, 0x0C, 0x0E, 0x19, 0x1A, 0x1B)

_CURSOR_MARKER_RE = re.compile(r"\{Cursor_location_id:0x([0-9a-fA-F]{2})\}")


class SeedString:
    """One string of a SeeD test section: {u8 expected answer, FF8 text}.

    The engine reads the first byte as the expected answer (0-based cursor-stop
    index: 0 = YES, 1 = NO on the standard questions) and displays the FF8 text
    after it. The text marks each selectable choice with a 0x0B n cursor-stop
    code (n = 0x20 + choice index, {Cursor_location_id:0xnn} in the codec); the
    engine counts the stops at display time, so adding a stop adds a choice.

    The original text bytes are kept as loaded and only re-encoded when the
    text is changed, so an untouched file saves back byte-exactly.
    """
    CURSOR_STOP_CODE = 0x0B
    CURSOR_STOP_BASE = 0x20
    STRING_PADDING = 4  # answer + text + 0x00 terminator, zero-padded to 4 bytes

    def __init__(self, game_data: GameData, answer=0, text_hex=bytearray()):
        self._game_data = game_data
        self.answer = answer
        self._text_hex = bytearray(text_hex)  # FF8 text without answer byte nor terminator

    def __str__(self):
        return f"SeedString(answer: {self.answer}, text: {self.get_text()})"

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_bytes(cls, game_data: GameData, string_hex: bytearray):
        """Parse {answer byte, FF8 text, 0x00 terminator (+ alignment padding)}."""
        answer = string_hex[0]
        terminator = string_hex.find(0x00, 1)
        if terminator == -1:
            terminator = len(string_hex)
        return cls(game_data=game_data, answer=answer, text_hex=string_hex[1:terminator])

    def to_bytes(self):
        string_hex = bytearray()
        string_hex.append(self.answer)
        string_hex.extend(self._text_hex)
        string_hex.append(0x00)
        while len(string_hex) % self.STRING_PADDING != 0:
            string_hex.append(0x00)
        return string_hex

    def get_text(self):
        return self._game_data.translate_hex_to_str(self._text_hex, cursor_location_size=2)

    def set_text(self, text: str):
        if text == self.get_text():  # Don't lose the original bytes on a no-op
            return
        self._text_hex = bytearray(self._game_data.translate_str_to_hex(text))

    def get_cursor_stops(self):
        """The 0x0B parameters in text order (0x20 = choice 0, 0x21 = choice 1...)."""
        stops = []
        i = 0
        while i < len(self._text_hex):
            code = self._text_hex[i]
            if code in _TWO_BYTE_CODES:
                if code == self.CURSOR_STOP_CODE and i + 1 < len(self._text_hex):
                    stops.append(self._text_hex[i + 1])
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


class SeedTest:
    """One SeeD test section: a string section whose strings all carry the answer byte."""
    HEADER_SIZE = 2
    OFFSET_SIZE = 2

    def __init__(self, name, section_pos, strings):
        self.name = name
        self.section_pos = section_pos  # Position among the valid mngrp sections
        self.strings = strings  # [SeedString], one per question for the test sections

    def __str__(self):
        return f"SeedTest({self.name}: {len(self.strings)} strings)"

    @classmethod
    def from_section_bytes(cls, game_data: GameData, section_hex: bytearray, name, section_pos):
        nb_string = int.from_bytes(section_hex[0:cls.HEADER_SIZE], byteorder='little')
        offset_list = []
        for index in range(nb_string):
            start = cls.HEADER_SIZE + index * cls.OFFSET_SIZE
            offset_list.append(int.from_bytes(section_hex[start:start + cls.OFFSET_SIZE], byteorder='little'))
        strings = []
        for index, offset in enumerate(offset_list):
            end = None
            for later_offset in offset_list[index + 1:]:  # 0 would mean an unused slot
                if later_offset:
                    end = later_offset
                    break
            if end is None:  # Last string: up to its terminator (the rest is section padding)
                end = section_hex.find(0x00, offset + 1) + 1
            strings.append(SeedString.from_bytes(game_data, section_hex[offset:end]))
        return cls(name=name, section_pos=section_pos, strings=strings)

    def to_section_bytes(self):
        string_hex_list = [seed_string.to_bytes() for seed_string in self.strings]
        section_hex = bytearray()
        section_hex.extend(len(string_hex_list).to_bytes(length=self.HEADER_SIZE, byteorder='little'))
        offset = self.HEADER_SIZE + self.OFFSET_SIZE * len(string_hex_list)
        for string_hex in string_hex_list:
            section_hex.extend(offset.to_bytes(length=self.OFFSET_SIZE, byteorder='little'))
            offset += len(string_hex)
        for string_hex in string_hex_list:
            section_hex.extend(string_hex)
        return section_hex


class NidaManager:
    """Read/write of the SeeD written test data inside mngrp.bin/mngrphd.bin.

    The tests live in the mngrp string sections at raw header entries 95-126
    (positions 42-73 among the valid sections): entry 95 is the shared exam UI
    text, entries 96-125 the tests 1-30 (10 questions each, the engine loads
    entry 96 + test number), entry 126 an unused "test 31" duplicate of test 30.
    """
    GENERAL_SECTION_POS = 42  # Raw header entry 95
    FIRST_TEST_POS = 43  # Raw header entry 96
    NB_TESTS = 31  # Tests 1-30 + the unused test 31
    QUESTIONS_PER_TEST = 10

    GENERAL_TEST_ID = "general"  # CSV/Excel row key for the shared exam UI section
    CSV_HEADER = ["Test", "String", "Answer", "Text"]

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        if not self.game_data.mngrp_data_json:
            self.game_data.load_mngrp_data()
        self.general_section = None  # SeedTest with the shared exam UI strings
        self.test_list = []  # [SeedTest], index 0 = test 1
        self.mngrp_path = ""
        self.mngrphd_path = ""
        self._mngrp_data = bytearray()
        self._mngrphd_data = bytearray()

    def load_file(self, mngrp_path, mngrphd_path=""):
        """Load the SeeD test data from mngrp.bin, mngrphd.bin is searched next to it if not given."""
        if not mngrphd_path:
            mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                    f"not found at: {mngrphd_path}")
        self.mngrp_path = mngrp_path
        self.mngrphd_path = mngrphd_path
        with open(mngrp_path, "rb") as in_file:
            self._mngrp_data = bytearray(in_file.read())
        with open(mngrphd_path, "rb") as in_file:
            self._mngrphd_data = bytearray(in_file.read())

        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_valid_entry_list())

        self.general_section = SeedTest.from_section_bytes(
            self.game_data, mngrp.get_section_by_id(self.GENERAL_SECTION_POS).get_data_hex(),
            name="Exam UI text", section_pos=self.GENERAL_SECTION_POS)
        self.test_list = []
        for test_index in range(self.NB_TESTS):
            section_pos = self.FIRST_TEST_POS + test_index
            name = f"Test {test_index + 1}" if test_index < 30 else "Test 31 (unused)"
            self.test_list.append(SeedTest.from_section_bytes(
                self.game_data, mngrp.get_section_by_id(section_pos).get_data_hex(),
                name=name, section_pos=section_pos))

    def save_file(self, mngrp_path="", mngrphd_path=""):
        """Write back the SeeD test sections inside the loaded mngrp.bin/mngrphd.bin (in place
        by default). The other mngrp sections are untouched, mngrphd offsets are rebuilt."""
        if not self.general_section:
            raise ValueError("No file loaded")
        if not mngrp_path:
            mngrp_path = self.mngrp_path
        if not mngrphd_path:
            mngrphd_path = self.mngrphd_path

        # The full entry list (invalid included) is used so the rebuilt mngrphd keeps all its entries
        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_entry_list())

        for section in [self.general_section] + self.test_list:
            mngrp.set_section_by_id_and_bytearray(section.section_pos, section.to_section_bytes())

        mngrp.update_data_hex()
        mngrphd.update_from_section_list(mngrp.get_section_list())
        mngrphd.update_data_hex()

        with open(mngrp_path, "wb") as out_file:
            out_file.write(mngrp.get_data_hex())
        with open(mngrphd_path, "wb") as out_file:
            out_file.write(mngrphd.get_data_hex())

    def iter_sections(self):
        """(csv test id, SeedTest): '{general}' then '1'..'{NB_TESTS}'."""
        yield self.GENERAL_TEST_ID, self.general_section
        for index, test in enumerate(self.test_list):
            yield str(index + 1), test

    def get_test_by_csv_id(self, test_id: str):
        """Resolve a CSV/CLI test id ('general' or '1'..NB_TESTS) to its SeedTest."""
        if test_id == self.GENERAL_TEST_ID:
            return self.general_section
        test_number = int(test_id)
        if not 1 <= test_number <= self.NB_TESTS:
            raise ValueError(f"Test number must be 1-{self.NB_TESTS} (or '{self.GENERAL_TEST_ID}'), got {test_id}")
        return self.test_list[test_number - 1]

    def to_csv_rows(self):
        """One row [test id, string index, answer, decoded text] per string (Excel/CSV export)."""
        rows = []
        for test_id, test in self.iter_sections():
            for index, seed_string in enumerate(test.strings):
                rows.append([test_id, index, seed_string.answer, seed_string.get_text()])
        return rows

    def apply_csv_rows(self, rows):
        """Apply rows produced by to_csv_rows back onto the loaded data. Returns the count applied."""
        applied = 0
        for row in rows:
            if not row or not str(row[0]).strip():
                continue
            test = self.get_test_by_csv_id(str(row[0]).strip())
            seed_string = test.strings[int(row[1])]
            seed_string.answer = int(row[2])
            seed_string.set_text(row[3])
            applied += 1
        return applied
