"""Real-file tests for Nida (SeeD written test editor, string sections 95-126 of menu/mngrp.bin).

Unlike the text-normalising ShumiTranslator save, NidaManager keeps the original
string bytes when they are not edited (only the answer byte, the offsets and the
4-byte string padding are rebuilt), so a load + save without edit must reproduce
BOTH mngrp.bin and mngrphd.bin byte-exactly. Edits are covered by reload checks.

Needs the real files, skipped otherwise (ff8data marker).
"""
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData
from Nida.nidamanager import NidaManager, SeedString

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"

MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


def _work_copy(tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)
    return work_mngrp, work_mngrphd


def _load(game_data, work_mngrp):
    manager = NidaManager(game_data)
    manager.load_file(str(work_mngrp))
    return manager


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_seed_semantics(game_data, tmp_path):
    """The parsed data matches the known game layout: 31 tests of 10 questions,
    2+ cursor stops each with sequential 0x20+i values, answers in range."""
    work_mngrp, _ = _work_copy(tmp_path)
    manager = _load(game_data, work_mngrp)
    assert len(manager.test_list) == NidaManager.NB_TESTS
    assert manager.general_section.strings, "no shared exam UI strings parsed"
    for test in manager.test_list:
        assert len(test.strings) == NidaManager.QUESTIONS_PER_TEST, f"{test.name}"
        for index, question in enumerate(test.strings):
            stops = question.get_cursor_stops()
            assert len(stops) >= 2, f"{test.name} question {index + 1} has fewer than 2 choices"
            assert stops == [SeedString.CURSOR_STOP_BASE + i for i in range(len(stops))], \
                f"{test.name} question {index + 1}: non-sequential cursor stops {stops}"
            assert 0 <= question.answer < len(stops), \
                f"{test.name} question {index + 1}: answer {question.answer} out of the {len(stops)} stops"
            assert len(question.get_choices()) == len(stops)


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_noedit_save_is_byte_exact(game_data, tmp_path):
    work_mngrp, work_mngrphd = _work_copy(tmp_path)
    manager = _load(game_data, work_mngrp)
    manager.save_file()
    assert work_mngrp.read_bytes() == MNGRP.read_bytes(), "mngrp.bin changed on a no-edit save"
    assert work_mngrphd.read_bytes() == MNGRPHD.read_bytes(), "mngrphd.bin changed on a no-edit save"


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_text_reencode_roundtrip(game_data, tmp_path):
    """Setting every string to its own decoded text (what a CSV import does) must
    re-encode to the same bytes: the codec round-trips the seed sections."""
    work_mngrp, work_mngrphd = _work_copy(tmp_path)
    manager = _load(game_data, work_mngrp)
    for test in [manager.general_section] + manager.test_list:
        for question in test.strings:
            # Bypass the set_text no-op guard to force a real re-encode
            question._text_hex = bytearray(game_data.translate_str_to_hex(question.get_text()))
    manager.save_file()
    assert work_mngrp.read_bytes() == MNGRP.read_bytes(), "re-encoded text does not round-trip byte-exactly"
    assert work_mngrphd.read_bytes() == MNGRPHD.read_bytes()


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_edit_persists(game_data, tmp_path):
    work_mngrp, work_mngrphd = _work_copy(tmp_path)
    manager = _load(game_data, work_mngrp)

    question = manager.test_list[4].strings[2]  # Test 5, question 3
    original_answer = question.answer
    question.answer = 1 - original_answer
    question.set_text(question.get_text().replace("Question 3", "Question 3 edited"))
    manager.test_list[0].strings[0].add_choice("MAYBE")  # 3rd cursor stop on Test 1 question 1
    manager.test_list[0].strings[0].answer = 2
    manager.save_file()

    reloaded = _load(game_data, work_mngrp)
    edited = reloaded.test_list[4].strings[2]
    assert edited.answer == 1 - original_answer
    assert "Question 3 edited" in edited.get_text()
    three_choices = reloaded.test_list[0].strings[0]
    assert three_choices.get_cursor_stops() == [0x20, 0x21, 0x22]
    assert three_choices.answer == 2
    assert three_choices.get_choices()[2][1] == "MAYBE"

    # The untouched sections must not have moved: same question count everywhere
    for test in reloaded.test_list:
        assert len(test.strings) == NidaManager.QUESTIONS_PER_TEST


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_edited_save_is_idempotent(game_data, tmp_path):
    work_mngrp, work_mngrphd = _work_copy(tmp_path)
    manager = _load(game_data, work_mngrp)
    manager.test_list[0].strings[0].add_choice("MAYBE")  # Grow a section so offsets shift
    manager.save_file()
    after_first = work_mngrp.read_bytes(), work_mngrphd.read_bytes()

    manager2 = _load(game_data, work_mngrp)
    manager2.save_file()
    after_second = work_mngrp.read_bytes(), work_mngrphd.read_bytes()
    assert after_first == after_second
