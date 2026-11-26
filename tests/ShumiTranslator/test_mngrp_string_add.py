"""A line added to a mngrp string section (the book text of a new magazine) gets its own id.

The menu picks a string by its slot in the offset table (a page's text overlay id), so an added
line needs a new slot at the end of the table - the next id - not just bytes after the last text.
ShumiTranslator's "+ Add entry" appends to the text list; SectionString grows the table on save.
"""
import pathlib
import shutil
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.string.sectionstring import SectionString

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"
BOOK_TEXT_RAW_FILE = 87


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _build_section(game_data, text_list) -> bytearray:
    """Section = {u16 count, u16 offsets[count], texts}; None is an empty slot (offset 0)."""
    offset = 2 + 2 * len(text_list)
    offset_list = []
    text_data = bytearray()
    for text in text_list:
        if text is None:
            offset_list.append(0)
            continue
        offset_list.append(offset)
        encoded = bytearray(game_data.translate_str_to_hex(text)) + b"\x00"
        text_data.extend(encoded)
        offset += len(encoded)
    return bytearray(struct.pack(f"<H{len(text_list)}H", len(text_list), *offset_list)) + text_data


def test_added_text_gets_the_next_slot(game_data):
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, ["First", None, "Third"]))
    section.get_text_section().add_text(bytearray())
    section.get_text_list()[-1].set_str("Added")

    saved = SectionString(game_data=game_data, data_hex=section.update_data_hex())

    assert saved.get_text_by_slot() == ["First", "", "Third", "Added"]


def test_two_added_texts_and_a_second_save(game_data):
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, ["A", "B"]))
    for text in ("C", "D"):
        section.get_text_section().add_text(bytearray())
        section.get_text_list()[-1].set_str(text)
    section.update_data_hex()
    data = section.update_data_hex()  # a second save must not add slots again

    assert struct.unpack_from("<H", data, 0)[0] == 4
    assert SectionString(game_data=game_data, data_hex=data).get_text_by_slot() == ["A", "B", "C", "D"]


def test_max_text_count_leaves_room_for_the_empty_slots(game_data):
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, ["A", None, None, "B"]))
    assert section.get_max_text_count() == SectionString.MAX_TEXT - 2


def test_add_button_stops_at_the_limit(qapp, game_data):
    from ShumiTranslator.view.sectionwidget import SectionWidget
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, ["A", "B"]))
    widget = SectionWidget(section.get_text_section(), 2, allow_add=True, max_entries=3)

    assert widget.add_entry() is not None
    assert widget.add_entry() is None
    assert len(section.get_text_list()) == 3


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_book_text_line_added_in_the_real_mngrp(game_data, tmp_path):
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    for name in ("mngrp.bin", "mngrphd.bin"):
        shutil.copy(MENU / name, tmp_path / name)
    manager = MngrpManager(game_data)
    manager.load_file(str(tmp_path / "mngrphd.bin"), str(tmp_path / "mngrp.bin"))
    book_text = manager.mngrp.get_section_list()[BOOK_TEXT_RAW_FILE]
    before = book_text.get_text_by_slot()
    book_text.get_text_section().add_text(bytearray())
    book_text.get_text_list()[-1].set_str("A new book")
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))

    reloaded = MngrpManager(game_data)
    reloaded.load_file(str(tmp_path / "mngrphd.bin"), str(tmp_path / "mngrp.bin"))
    after = reloaded.mngrp.get_section_list()[BOOK_TEXT_RAW_FILE].get_text_by_slot()
    assert after == before + ["A new book"]
