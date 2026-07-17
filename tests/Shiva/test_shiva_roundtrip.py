"""Shiva writes mngrp.bin back section per section, from a model every tab shares.

The gate for every tab ported into it: saving the real file without editing anything must
leave every section no tab edits byte for byte. A tab damaging a section it does not own, or
an offset rebuilt from the wrong baseline, shows up here.

The sections a tab does edit are re-encoded on save, so their bytes can move even when nothing
changed; only their content is guaranteed. tests/ShumiTranslator/test_realfile_roundtrip_all.py
covers that side, by checking the text survives a save.

Needs the real game files, which are not in the repo (copyright), so it is skipped without them.
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd
from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def qapp():
    # The tabs build real Qt widgets, so a QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()  # The m00x sections name their refine entries from the item/magic/card data
    return game_data


def _sections_by_id(game_data, mngrp_path, mngrphd_path):
    """The bytes of every valid section of a mngrp.bin file, read again from the disk."""
    mngrphd = Mngrphd(game_data=game_data, data_hex=bytearray(pathlib.Path(mngrphd_path).read_bytes()))
    mngrp = Mngrp(game_data=game_data, data_hex=bytearray(pathlib.Path(mngrp_path).read_bytes()),
                  header_entry_list=mngrphd.get_entry_list())
    return {section.id: bytes(section.get_data_hex())
            for section in mngrp.get_section_list() if section.id != -1}


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_saving_does_not_touch_the_sections_no_tab_edits(game_data, tmp_path):
    """A section no tab knows about must come back byte for byte.

    The sections a tab edits are re-encoded on save (their text is rebuilt and the offsets
    recomputed), so their bytes may move: that is accepted, only their content matters. But a
    section nobody edits has no reason to change at all. MngrpManager keeps those as plain
    Section objects, holding the bytes it read, which is how they stay untouched here."""
    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))

    # A section still a plain Section was not parsed into an editable model: no tab edits it.
    untouched_ids = {section.id for section in manager.mngrp.get_section_list()
                     if type(section) is Section and section.id != -1}
    assert untouched_ids, "every section is parsed, this test can no longer tell them apart"

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    before = _sections_by_id(game_data, MENU / "mngrp.bin", MENU / "mngrphd.bin")
    after = _sections_by_id(game_data, out_mngrp, out_mngrphd)
    changed = sorted(section_id for section_id in untouched_ids
                     if before[section_id] != after.get(section_id))
    assert not changed, f"sections no tab edits were rewritten: {changed}"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_a_section_is_reachable_by_its_id_not_its_place(game_data):
    """The invalid header entries take a place in the section list but have the id -1, so the
    place of a section is not its id. Every tab addresses its sections by id."""
    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))

    section_list = manager.mngrp.get_section_list()
    assert any(section.id != place for place, section in enumerate(section_list)), \
        "no invalid entry in this mngrphd.bin, the test cannot tell id and place apart"

    for section in section_list:
        if section.id == -1:  # Invalid entry, it has no id to be found by
            continue
        assert manager.mngrp.get_section_by_id(section.id).id == section.id


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_sprite_tab_saves_its_section_back_unchanged(qapp, game_data, tmp_path):
    """The Sprite tab reads section 4 as an SP2 table and, untouched, saves it back identical.

    Compared after a real save: the section kept in the model is padded to the sector size,
    while an SP2 table is only as long as its quads, so the padding is put back when the file
    is rebuilt, not when the tab hands its section over."""
    from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))

    tab = ShivaSpriteWidget()
    tab.load_from_mngrp(manager)
    assert tab.sp2.sprites, "the SP2 table of section 4 was read empty"

    tab.save_to_mngrp(manager)
    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    before = _sections_by_id(game_data, MENU / "mngrp.bin", MENU / "mngrphd.bin")
    after = _sections_by_id(game_data, out_mngrp, out_mngrphd)
    section_id = ShivaSpriteWidget.MNGRP_SP2_SECTION_ID
    assert after[section_id] == before[section_id], "the Sprite tab changed its section without an edit"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_refine_tab_reads_every_entry_with_its_text(game_data):
    """The refine entries are read from the shared mngrp, their text from the msg section next
    to them. This checked entry for entry against Pandemona's own parser while it existed; it
    now guards the shape that parser produced: 377 entries, each with a text of its own."""
    from Shiva.ShivaRefine.refineview import build_refine_views

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    views = build_refine_views(manager)

    entries = [entry for view in views for entry in view.entries]
    assert len(entries) == 377, f"{len(entries)} refine entries read, the m00x sections hold 377"
    for view in views:
        assert len(view.texts) == len(view.entries), f"{view.bin_name}/{view.name}: text and entries not lined up"
        assert all(text.get_str() for text in view.texts), f"{view.bin_name}/{view.name}: an entry has no text"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_refine_tab_edit_survives_a_save(game_data, tmp_path):
    """An edited entry and its text must come back from the saved file, with the text offsets
    recomputed by the m00x manager."""
    from Shiva.ShivaRefine.refineview import build_refine_views

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    views = build_refine_views(manager)

    entry = views[0].entries[0]
    new_amount = (entry.amount_required % 9) + 1
    entry.amount_required = new_amount
    views[0].texts[0].set_str("Claude was here")

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    reloaded = MngrpManager(game_data=game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    reloaded_views = build_refine_views(reloaded)
    assert reloaded_views[0].entries[0].amount_required == new_amount
    assert reloaded_views[0].texts[0].get_str() == "Claude was here"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_full_widget_noedit_save_is_byte_exact(qapp, game_data, tmp_path):
    """The whole tool, every tab loaded: saving without editing must reproduce mngrp.bin and
    mngrphd.bin byte for byte. The tabs write their own sections back unchanged, and the raw
    pass keeps every other section as read, so nothing moves."""
    import shutil
    from Shiva.shivawidget import ShivaWidget

    work = tmp_path / "mngrp.bin"
    work_hd = tmp_path / "mngrphd.bin"
    shutil.copy(MENU / "mngrp.bin", work)
    shutil.copy(MENU / "mngrphd.bin", work_hd)

    shiva = ShivaWidget()
    shiva.load_file(str(work))
    shiva.save_file()

    assert work.read_bytes() == (MENU / "mngrp.bin").read_bytes(), "mngrp.bin changed on a no-edit Shiva save"
    assert work_hd.read_bytes() == (MENU / "mngrphd.bin").read_bytes(), "mngrphd.bin changed on a no-edit save"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_seed_tab_reads_every_string_with_its_answer(game_data):
    """The SeeD tab reads the tests out of the shared mngrp. This checked string for string
    against Nida's own parser while it existed; it now guards the shape that parser produced:
    the exam section plus 31 tests of 10 strings, each with an answer and a non-empty text."""
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)

    strings = [(test_id, seed_string) for test_id, test in seed_tests.iter_sections()
               for seed_string in test.strings]
    assert len(seed_tests.test_list) == SeedTestSet.NB_TESTS
    assert all(len(test.strings) == SeedTestSet.QUESTIONS_PER_TEST for test in seed_tests.test_list)
    for test_id, seed_string in strings:
        assert seed_string.get_text(), f"test {test_id}: an empty SeeD string"
        assert seed_string.answer >= 0


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_seed_tab_edit_survives_a_save(qapp, game_data, tmp_path):
    """An edited SeeD answer and question text must come back from the saved file."""
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)

    question = seed_tests.test_list[4].strings[2]  # Test 5, question 3
    question.answer = 1 - question.answer
    question.set_text(question.get_text().replace("Question 3", "Question 3 edited"))
    new_answer = question.answer
    seed_tests.save_to_mngrp(manager.mngrp)

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    reloaded = MngrpManager(game_data=game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    reloaded_tests = SeedTestSet.from_mngrp(game_data, reloaded.mngrp)
    edited = reloaded_tests.test_list[4].strings[2]
    assert edited.answer == new_answer
    assert "Question 3 edited" in edited.get_text()


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_seed_semantics_match_the_game_layout(game_data):
    """31 tests of 10 questions, 2+ sequential cursor stops each, answers in range (migrated
    from the Nida real-file test)."""
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet, SeedString

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)

    assert len(seed_tests.test_list) == SeedTestSet.NB_TESTS
    assert seed_tests.general_section.strings, "no shared exam UI strings parsed"
    for test in seed_tests.test_list:
        assert len(test.strings) == SeedTestSet.QUESTIONS_PER_TEST, test.name
        for index, question in enumerate(test.strings):
            stops = question.get_cursor_stops()
            assert len(stops) >= 2, f"{test.name} question {index + 1} has fewer than 2 choices"
            assert stops == [SeedString.CURSOR_STOP_BASE + i for i in range(len(stops))], \
                f"{test.name} question {index + 1}: non-sequential cursor stops {stops}"
            assert 0 <= question.answer < len(stops), \
                f"{test.name} question {index + 1}: answer {question.answer} out of range"
            assert len(question.get_choices()) == len(stops)


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_seed_add_choice_persists(qapp, game_data, tmp_path):
    """Adding a cursor stop adds a choice that survives a save (migrated from Nida)."""
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet

    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(MENU / "mngrphd.bin"), str(MENU / "mngrp.bin"))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)
    seed_tests.test_list[0].strings[0].add_choice("MAYBE")  # 3rd cursor stop on Test 1 question 1
    seed_tests.test_list[0].strings[0].answer = 2
    seed_tests.save_to_mngrp(manager.mngrp)

    out_mngrp = tmp_path / "mngrp.bin"
    out_mngrphd = tmp_path / "mngrphd.bin"
    manager.save_file(str(out_mngrp), str(out_mngrphd))

    reloaded = MngrpManager(game_data=game_data)
    reloaded.load_file(str(out_mngrphd), str(out_mngrp))
    reloaded_tests = SeedTestSet.from_mngrp(game_data, reloaded.mngrp)
    three = reloaded_tests.test_list[0].strings[0]
    assert three.get_cursor_stops() == [0x20, 0x21, 0x22]
    assert three.answer == 2
    assert three.get_choices()[2][1] == "MAYBE"
    for test in reloaded_tests.test_list:  # untouched tests keep their question count
        assert len(test.strings) == SeedTestSet.QUESTIONS_PER_TEST
