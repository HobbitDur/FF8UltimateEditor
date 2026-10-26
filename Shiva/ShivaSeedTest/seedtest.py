"""The SeeD written test data of mngrp.bin, read from a shared MngrpManager.

No Qt here: the Shiva tab and the CLI both read the SeeD tests this way, so they cannot
disagree on the section layout or the answer-byte handling.

The sections themselves (SectionSeedTest, one SeedString per question) are parsed by
MngrpManager, the same objects ShumiTranslator edits the text of: this only groups them into
the exam UI section and the 31 tests, and handles the CSV exchange.
"""
from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.seedtest.sectionseedtest import SectionSeedTest, SeedString  # noqa: F401 (re-export)


class SeedTestSet:
    """The SeeD test sections of a shared mngrp: the exam UI section and the 31 tests.

    The exam text lives in section 42, the tests in sections 43-73 (the id is the same as the
    position among the valid sections, so get_section_by_id reaches them). They are the shared
    model's own sections: an edit here is in mngrp.bin on the next save."""

    GENERAL_SECTION_POS = 42  # Raw header entry 95
    FIRST_TEST_POS = 43  # Raw header entry 96
    NB_TESTS = 31  # Tests 1-30 + the unused test 31
    QUESTIONS_PER_TEST = 10

    GENERAL_TEST_ID = "general"  # CSV/CLI row key for the shared exam UI section
    CSV_HEADER = ["Test", "String", "Answer", "Text"]

    def __init__(self, game_data: GameData, general_section, test_list):
        self.game_data = game_data
        self.general_section = general_section  # SectionSeedTest with the shared exam UI strings
        self.test_list = test_list  # [SectionSeedTest], index 0 = test 1

    @classmethod
    def from_mngrp(cls, game_data: GameData, mngrp):
        sections = [mngrp.get_section_by_id(cls.GENERAL_SECTION_POS)]
        sections += [mngrp.get_section_by_id(cls.FIRST_TEST_POS + index) for index in range(cls.NB_TESTS)]
        if not all(isinstance(section, SectionSeedTest) for section in sections):
            raise ValueError("The SeeD test sections are read by MngrpManager: load mngrp.bin through it")
        return cls(game_data, sections[0], sections[1:])

    def iter_sections(self):
        """(csv test id, SectionSeedTest): 'general' then '1'..NB_TESTS."""
        yield self.GENERAL_TEST_ID, self.general_section
        for index, test in enumerate(self.test_list):
            yield str(index + 1), test

    def get_test_by_csv_id(self, test_id: str):
        """Resolve a CSV/CLI test id ('general' or '1'..NB_TESTS) to its SectionSeedTest."""
        if test_id == self.GENERAL_TEST_ID:
            return self.general_section
        test_number = int(test_id)
        if not 1 <= test_number <= self.NB_TESTS:
            raise ValueError(f"Test number must be 1-{self.NB_TESTS} (or '{self.GENERAL_TEST_ID}'), got {test_id}")
        return self.test_list[test_number - 1]

    def to_csv_rows(self):
        """One row [test id, string index, answer, decoded text] per string (CSV export)."""
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
