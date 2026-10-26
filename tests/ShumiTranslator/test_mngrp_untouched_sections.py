"""mngrp.bin is written the same way whatever tool edits it.

MngrpManager writes a section nobody changed exactly as it was loaded: re-encoding it drops what
the codec does not keep (the 4-byte padding of the SeeD test strings...), so a one-line text edit
in ShumiTranslator used to rewrite 47 sections, and a Shiva save of that file rewrote them again.
The SeeD test sections are one shared model (SectionSeedTest): ShumiTranslator edits their text,
Shiva their text and answers, and both write them identically.
"""
import pathlib
import shutil
import struct

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.seedtest.sectionseedtest import SectionSeedTest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"
REAL_MNGRP = pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _seed_section(game_data, questions) -> bytearray:
    """{u16 count, u16 offsets, {answer, text, 0x00} zero-padded to 4 bytes} - the vanilla layout."""
    offset = 2 + 2 * len(questions)
    offset_list, data = [], bytearray()
    for answer, text in questions:
        encoded = bytearray([answer]) + bytearray(game_data.translate_str_to_hex(text)) + b"\x00"
        encoded += b"\x00" * (-len(encoded) % 4)
        offset_list.append(offset)
        data += encoded
        offset += len(encoded)
    return bytearray(struct.pack(f"<H{len(questions)}H", len(questions), *offset_list)) + data


def test_seed_rows_show_the_answer_and_keep_the_padding(game_data):
    original = _seed_section(game_data, [(0, "Are you ready?"), (1, "Is it so?"), (0, "Yes")])
    section = SectionSeedTest(game_data, bytearray(original), id=43, own_offset=0, name="SeeD Test 1")
    assert [row.get_str() for row in section.get_text_list()] == ["{x00}Are you ready?", "{x01}Is it so?", "{x00}Yes"]
    assert [seed_string.answer for seed_string in section.strings] == [0, 1, 0]
    for row in section.get_text_list():
        row.set_str(row.get_str())  # what the translator pane does on a save
    assert bytes(section.update_data_hex()) == bytes(original)

    section.get_text_list()[1].set_str("Is it really so?")  # no prefix: the answer stays
    section.get_text_list()[2].set_str("{x01}Yes")  # the prefix sets the answer
    edited = section.update_data_hex()
    assert edited == _seed_section(game_data, [(0, "Are you ready?"), (1, "Is it really so?"), (1, "Yes")])


def _load(game_data, folder):
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    manager = MngrpManager(game_data)
    manager.load_file(str(folder / "mngrphd.bin"), str(folder / "mngrp.bin"))
    return manager


def _slots(folder):
    header = (folder / "mngrphd.bin").read_bytes()
    data = (folder / "mngrp.bin").read_bytes()
    slots = []
    for index in range(len(header) // 8):
        seek, size = struct.unpack_from("<II", header, index * 8)
        slots.append(b"" if seek in (0, 0xFFFFFFFF) or not size else data[seek - 1:seek - 1 + size])
    return slots


@REAL_MNGRP
def test_unedited_mngrp_saves_back_byte_exact(game_data, tmp_path):
    _load(game_data, MENU).save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    assert (tmp_path / "mngrp.bin").read_bytes() == (MENU / "mngrp.bin").read_bytes()
    assert (tmp_path / "mngrphd.bin").read_bytes() == (MENU / "mngrphd.bin").read_bytes()


@REAL_MNGRP
def test_a_text_edit_rewrites_only_its_section(game_data, tmp_path):
    from FF8GameData.gamedata import SectionType
    manager = _load(game_data, MENU)
    section = next(section for section in manager.mngrp.get_section_list() if section.type == SectionType.MNGRP_STRING)
    text = section.get_text_list()[0]
    text.set_str(text.get_str() + "!")
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    changed = [slot for slot, (before, after) in enumerate(zip(_slots(MENU), _slots(tmp_path)))
               if before.rstrip(b"\0") != after.rstrip(b"\0")]
    assert len(changed) == 1, f"one edited section, slots {changed} rewritten"


@REAL_MNGRP
def test_shiva_and_shumitranslator_write_the_same_seed_edit(game_data, tmp_path):
    """The same SeeD question text edit, through each tool's model, gives the same files."""
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    from FF8GameData.gamedata import SectionType
    new_text = "Edited by both tools"

    shiva = _load(game_data, MENU)
    SeedTestSet.from_mngrp(game_data, shiva.mngrp).test_list[4].strings[2].set_text(new_text)
    (tmp_path / "shiva").mkdir()
    shiva.save_file(str(tmp_path / "shiva" / "mngrp.bin"), str(tmp_path / "shiva" / "mngrphd.bin"))

    shumi = _load(game_data, MENU)  # ShumiTranslator's pane: the sections' text lists, in file order
    seed_sections = [section for section in shumi.mngrp.get_section_list()
                     if section.type == SectionType.MNGRP_SEED_TEST]
    seed_sections[5].get_text_list()[2].set_str(new_text)  # [0] is the exam UI section, [5] test 5
    (tmp_path / "shumi").mkdir()
    shumi.save_file(str(tmp_path / "shumi" / "mngrp.bin"), str(tmp_path / "shumi" / "mngrphd.bin"))

    for name in ("mngrp.bin", "mngrphd.bin"):
        assert (tmp_path / "shiva" / name).read_bytes() == (tmp_path / "shumi" / name).read_bytes(), name
    assert (tmp_path / "shiva" / "mngrp.bin").read_bytes() != (MENU / "mngrp.bin").read_bytes()
    reloaded = SeedTestSet.from_mngrp(game_data, _load(game_data, tmp_path / "shiva").mngrp)
    assert reloaded.test_list[4].strings[2].get_text() == new_text


@REAL_MNGRP
def test_saving_twice_writes_the_same_files(game_data, tmp_path):
    manager = _load(game_data, MENU)
    text = manager.mngrp.get_section_by_id(43).strings[0].text
    text.set_str(text.get_str() + " (edited)")
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    first = (tmp_path / "mngrp.bin").read_bytes(), (tmp_path / "mngrphd.bin").read_bytes()
    manager.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    assert ((tmp_path / "mngrp.bin").read_bytes(), (tmp_path / "mngrphd.bin").read_bytes()) == first
    shutil.copy(tmp_path / "mngrp.bin", tmp_path / "copy.bin")
    _load(game_data, tmp_path).save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd.bin"))
    assert (tmp_path / "mngrp.bin").read_bytes() == (tmp_path / "copy.bin").read_bytes()
