"""ShumiTranslator's CSV of mngrp.bin, SeeD test rows included, through the pane the GUI uses.

A SeeD row is its expected answer as a leading {xNN} then the question text - the form these
rows always had - so a translator sets the answer by editing that prefix, and a CSV exported
before the SeeD sections got their own model still imports.
"""
import csv
import pathlib
import shutil
import sys

import pytest

from FF8GameData.gamedata import FileType, GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _copy(folder):
    folder.mkdir()
    for name in ("mngrp.bin", "mngrphd.bin"):
        shutil.copy(MENU / name, folder / name)
    return folder


def _pane(game_data, folder):
    from ShumiTranslator.shumifilepane import ShumiFilePane
    return ShumiFilePane(game_data, FileType.MNGRP, str(folder / "mngrp.bin"), str(folder / "mngrphd.bin"))


def _rows(path):
    with open(path, newline="", encoding="utf-8") as csv_file:
        return list(csv.reader(csv_file, delimiter="|", quotechar="§"))


def _seed_tests(game_data, folder):
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    manager = MngrpManager(game_data)
    manager.load_file(str(folder / "mngrphd.bin"), str(folder / "mngrp.bin"))
    return SeedTestSet.from_mngrp(game_data, manager.mngrp)


def test_seed_rows_carry_the_answer_as_a_prefix(qapp, game_data, tmp_path):
    folder = _copy(tmp_path / "files")
    _pane(game_data, folder).save_csv(str(tmp_path / "mngrp.csv"))
    seed_rows = [row for row in _rows(tmp_path / "mngrp.csv") if row[0] == "SeeD Test 1"]
    test_1 = _seed_tests(game_data, folder).test_list[0]
    assert len(seed_rows) == len(test_1.strings) == 10
    for row, question in zip(seed_rows, test_1.strings):
        assert row[3] == "{{x{:02x}}}".format(question.answer) + question.get_text().replace("\n", "\\n")


def test_csv_export_then_import_changes_nothing(qapp, game_data, tmp_path):
    folder = _copy(tmp_path / "files")
    _pane(game_data, folder).save_csv(str(tmp_path / "mngrp.csv"))
    pane = _pane(game_data, folder)
    pane.open_csv(str(tmp_path / "mngrp.csv"))
    pane.save(None)
    for name in ("mngrp.bin", "mngrphd.bin"):
        assert (folder / name).read_bytes() == (MENU / name).read_bytes(), name


def test_csv_sets_a_seed_answer_and_text(qapp, game_data, tmp_path):
    folder = _copy(tmp_path / "files")
    _pane(game_data, folder).save_csv(str(tmp_path / "mngrp.csv"))
    rows = _rows(tmp_path / "mngrp.csv")
    before = _seed_tests(game_data, folder).test_list[1]  # Test 2
    question = before.strings[3]
    index = next(i for i, row in enumerate(rows) if row[0] == "SeeD Test 2" and row[2] == "3")
    new_answer = 1 - question.answer
    rows[index][3] = "{{x{:02x}}}Question 4\\n\\nEdited in the CSV.\\n\\n\\n\\n  " \
                     "{{Cursor_location_id:0x20}}YES     {{Cursor_location_id:0x21}}NO".format(new_answer)
    with open(tmp_path / "edited.csv", "w", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file, delimiter="|", quotechar="§", quoting=csv.QUOTE_MINIMAL).writerows(rows)

    pane = _pane(game_data, folder)
    pane.open_csv(str(tmp_path / "edited.csv"))
    pane.save(None)

    after = _seed_tests(game_data, folder).test_list[1]
    assert after.strings[3].answer == new_answer
    assert "Edited in the CSV." in after.strings[3].get_text()
    for other in (0, 1, 2, 4, 9):
        assert after.strings[other].answer == before.strings[other].answer
        assert after.strings[other].get_text() == before.strings[other].get_text()


def test_every_text_shown_can_be_edited(qapp, game_data, tmp_path):
    """Each text ShumiTranslator shows for mngrp.bin (tkmnmes, strings, SeeD tests, tutorial text
    boxes and captions, refine texts) keeps its edit through a save and a reload."""
    from FF8GameData.FF8HexReader.mngrphd import Mngrphd
    folder = _copy(tmp_path / "files")
    pane = _pane(game_data, folder)
    expected = []
    for widget in pane.section_widget_list:
        for index, text in enumerate(widget.section.get_text_list()):
            text.set_str(text.get_str() + f" E{index}")
            expected.append(text.get_str())
    assert len(expected) > 2500
    pane.save(None)

    Mngrphd(None, bytearray((folder / "mngrphd.bin").read_bytes())).check_matches((folder / "mngrp.bin").stat().st_size)
    reloaded = [text.get_str() for widget in _pane(game_data, folder).section_widget_list
                for text in widget.section.get_text_list()]
    assert reloaded == expected
