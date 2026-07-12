"""
Tests for Pandemona (refine abilities editor, m00x data of mngrp.bin).
A small synthetic mngrp.bin/mngrphd.bin pair is built with known entries so the tests
don't need the original game files.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.m00x.dataclass import TypeId
from Pandemona.pandemonamanager import PandemonaManager, RefineEntry

NB_VALID_SECTIONS = 116  # mngrp sections 0 to 115, the m00x data uses 106-110 (bin) and 111-115 (msg)
NB_REFINE_SECTIONS = 19  # 8 (m000) + 7 (m001) + 2 (m002) + 1 (m003) + 1 (m004)
NB_ENTRIES_PER_BIN = (102, 143, 10, 12, 110)


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    return GameData(str(project_root / "FF8GameData"))


def entry_text(bin_name, index_data, index_entry):
    return f"Refine {bin_name} data{index_data} entry{index_entry}"


def entry_values(global_index):
    """Deterministic test values for the entry of a bin file at the given global index."""
    return {
        "element_in_id": (global_index * 3) % 110,  # Card IDs go up to 109
        "amount_required": global_index % 9 + 1,
        "element_out_id": (global_index * 7) % 57,  # Magic IDs go up to 56
        "amount_received": global_index % 5,
        "unk": 0x0100 + global_index,
    }


@pytest.fixture(scope="module")
def mngrp_files(tmp_path_factory, game_data):
    """Build a synthetic mngrp.bin/mngrphd.bin pair with formulaic refine entries."""
    manager = PandemonaManager(game_data)  # Only used for the m00x structure description
    section_data_list = [bytearray([index % 256] * 4) for index in range(NB_VALID_SECTIONS)]

    for mbin in manager.bin_list:
        bin_bytes = bytearray()
        msg_bytes = bytearray()
        global_index = 0
        for index_data, data in enumerate(mbin.list_data):
            for index_entry in range(data.nb_entries):
                values = entry_values(global_index)
                entry = RefineEntry(text=entry_text(mbin.name, index_data, index_entry), **values)
                text_hex = bytearray(game_data.translate_str_to_hex(entry.text))
                text_hex.append(0x00)
                bin_bytes.extend(entry.to_bytes(len(msg_bytes)))
                msg_bytes.extend(text_hex)
                global_index += 1
        section_data_list[mbin.mngrp_bin_id] = bin_bytes
        section_data_list[mbin.mngrp_msg_id] = msg_bytes

    mngrp_data = bytearray()
    mngrphd_data = bytearray()
    for section_data in section_data_list:
        seek = len(mngrp_data)
        mngrphd_data.extend((seek + 1).to_bytes(4, byteorder='little'))  # mngrphd seeks are stored +1
        mngrphd_data.extend(len(section_data).to_bytes(4, byteorder='little'))
        mngrp_data.extend(section_data)

    file_folder = tmp_path_factory.mktemp("mngrp")
    (file_folder / "mngrp.bin").write_bytes(mngrp_data)
    (file_folder / "mngrphd.bin").write_bytes(mngrphd_data)
    return file_folder


@pytest.fixture
def manager(game_data, mngrp_files, tmp_path):
    """A manager loaded with a fresh copy of the synthetic files (so tests can modify them)."""
    for file_name in ("mngrp.bin", "mngrphd.bin"):
        (tmp_path / file_name).write_bytes((mngrp_files / file_name).read_bytes())
    manager = PandemonaManager(game_data)
    manager.load_file(str(tmp_path / "mngrp.bin"))
    return manager


class TestRefineEntry:
    def test_bytes_roundtrip(self):
        entry_bytes = bytearray([0x34, 0x12, 5, 0xCD, 0xAB, 30, 2, 45])
        entry = RefineEntry.from_bytes(entry_bytes)
        assert entry.element_in_id == 30
        assert entry.amount_required == 2
        assert entry.element_out_id == 45
        assert entry.amount_received == 5
        assert entry.unk == 0xABCD
        assert entry.to_bytes(0x1234) == entry_bytes

    def test_to_bytes_text_offset(self):
        assert RefineEntry().to_bytes(0xBEEF)[0:2] == bytearray([0xEF, 0xBE])


class TestLoad:
    def test_all_sections_loaded(self, manager):
        assert len(manager.refine_sections) == NB_REFINE_SECTIONS
        assert [section.name for section in manager.refine_sections[:3]] == ["t_mag_rf", "i_mag_rf", "f_mag_rf"]
        assert manager.refine_sections[-1].name == "card_mod"
        assert sum(len(section.entries) for section in manager.refine_sections) == sum(NB_ENTRIES_PER_BIN)

    def test_section_types(self, manager):
        t_mag_rf = manager.refine_sections[0]
        assert t_mag_rf.bin_name == "m000"
        assert t_mag_rf.input_type == TypeId.ITEM
        assert t_mag_rf.output_type == TypeId.SPELL
        card_mod = manager.refine_sections[-1]
        assert card_mod.bin_name == "m004"
        assert card_mod.input_type == TypeId.CARD
        assert card_mod.output_type == TypeId.ITEM

    def test_entry_values(self, manager):
        # First entry of m000 (global index 0 of the bin)
        first_entry = manager.refine_sections[0].entries[0]
        for attribute, value in entry_values(0).items():
            assert getattr(first_entry, attribute) == value, attribute
        # First entry of i_mag_rf, second data of m000 (global index 7: t_mag_rf has 7 entries)
        entry = manager.refine_sections[1].entries[0]
        for attribute, value in entry_values(7).items():
            assert getattr(entry, attribute) == value, attribute
        # Last entry of card_mod (m004 has a single data of 110 entries)
        last_entry = manager.refine_sections[-1].entries[-1]
        for attribute, value in entry_values(109).items():
            assert getattr(last_entry, attribute) == value, attribute

    def test_entry_texts(self, manager):
        assert manager.refine_sections[0].entries[0].text == entry_text("m000", 0, 0)
        assert manager.refine_sections[1].entries[3].text == entry_text("m000", 1, 3)
        assert manager.refine_sections[-1].entries[109].text == entry_text("m004", 0, 109)

    def test_missing_mngrphd_raises(self, game_data, mngrp_files, tmp_path):
        (tmp_path / "mngrp.bin").write_bytes((mngrp_files / "mngrp.bin").read_bytes())
        manager = PandemonaManager(game_data)
        with pytest.raises(FileNotFoundError):
            manager.load_file(str(tmp_path / "mngrp.bin"))


class TestSave:
    def test_save_without_load_raises(self, game_data):
        with pytest.raises(ValueError):
            PandemonaManager(game_data).save_file()

    def test_save_unmodified_roundtrip(self, manager, game_data, tmp_path):
        saved_mngrp = tmp_path / "saved_mngrp.bin"
        saved_mngrphd = tmp_path / "saved_mngrphd.bin"
        manager.save_file(str(saved_mngrp), str(saved_mngrphd))

        reloaded = PandemonaManager(game_data)
        reloaded.load_file(str(saved_mngrp), str(saved_mngrphd))
        assert len(reloaded.refine_sections) == NB_REFINE_SECTIONS
        for original_section, reloaded_section in zip(manager.refine_sections, reloaded.refine_sections):
            for original_entry, reloaded_entry in zip(original_section.entries, reloaded_section.entries):
                assert reloaded_entry.text == original_entry.text
                assert reloaded_entry.element_in_id == original_entry.element_in_id
                assert reloaded_entry.amount_required == original_entry.amount_required
                assert reloaded_entry.element_out_id == original_entry.element_out_id
                assert reloaded_entry.amount_received == original_entry.amount_received
                assert reloaded_entry.unk == original_entry.unk

    def test_save_in_place_by_default(self, manager, game_data):
        manager.refine_sections[0].entries[0].amount_required = 42
        manager.save_file()

        reloaded = PandemonaManager(game_data)
        reloaded.load_file(manager.mngrp_path, manager.mngrphd_path)
        assert reloaded.refine_sections[0].entries[0].amount_required == 42

    def test_modify_values_and_save(self, manager, game_data, tmp_path):
        card_mod_entry = manager.refine_sections[-1].entries[5]
        card_mod_entry.element_in_id = 77
        card_mod_entry.amount_required = 3
        card_mod_entry.element_out_id = 33
        card_mod_entry.amount_received = 12
        card_mod_entry.unk = 0xCAFE
        saved_mngrp = tmp_path / "saved_mngrp.bin"
        saved_mngrphd = tmp_path / "saved_mngrphd.bin"
        manager.save_file(str(saved_mngrp), str(saved_mngrphd))

        reloaded = PandemonaManager(game_data)
        reloaded.load_file(str(saved_mngrp), str(saved_mngrphd))
        reloaded_entry = reloaded.refine_sections[-1].entries[5]
        assert reloaded_entry.element_in_id == 77
        assert reloaded_entry.amount_required == 3
        assert reloaded_entry.element_out_id == 33
        assert reloaded_entry.amount_received == 12
        assert reloaded_entry.unk == 0xCAFE
        # Neighbour entries are untouched
        for attribute, value in entry_values(4).items():
            assert getattr(reloaded.refine_sections[-1].entries[4], attribute) == value, attribute
        for attribute, value in entry_values(6).items():
            assert getattr(reloaded.refine_sections[-1].entries[6], attribute) == value, attribute

    def test_modify_text_recomputes_offsets(self, manager, game_data, tmp_path):
        # A longer first text shifts all the following texts of the same msg section
        manager.refine_sections[0].entries[0].text = "A much longer text than the original one"
        saved_mngrp = tmp_path / "saved_mngrp.bin"
        saved_mngrphd = tmp_path / "saved_mngrphd.bin"
        manager.save_file(str(saved_mngrp), str(saved_mngrphd))

        reloaded = PandemonaManager(game_data)
        reloaded.load_file(str(saved_mngrp), str(saved_mngrphd))
        assert reloaded.refine_sections[0].entries[0].text == "A much longer text than the original one"
        assert reloaded.refine_sections[0].entries[1].text == entry_text("m000", 0, 1)
        # Last section of m000 still reads its texts correctly
        assert reloaded.refine_sections[7].entries[-1].text == entry_text("m000", 7, 5)
        # Other m00x files are untouched
        assert reloaded.refine_sections[-1].entries[0].text == entry_text("m004", 0, 0)

    def test_other_mngrp_sections_untouched(self, manager, game_data, tmp_path):
        manager.refine_sections[0].entries[0].text = "Making the m000 msg section bigger to shift the sections"
        saved_mngrp = tmp_path / "saved_mngrp.bin"
        saved_mngrphd = tmp_path / "saved_mngrphd.bin"
        manager.save_file(str(saved_mngrp), str(saved_mngrphd))

        # The non-m00x sections (0-105) keep their content, re-read through the new header
        from FF8GameData.FF8HexReader.mngrp import Mngrp
        from FF8GameData.FF8HexReader.mngrphd import Mngrphd
        mngrphd = Mngrphd(game_data=game_data, data_hex=bytearray(saved_mngrphd.read_bytes()))
        assert len(mngrphd.get_valid_entry_list()) == NB_VALID_SECTIONS
        mngrp = Mngrp(game_data=game_data, data_hex=bytearray(saved_mngrp.read_bytes()),
                      header_entry_list=mngrphd.get_valid_entry_list())
        for section_id in (0, 50, 105):
            section_data = mngrp.get_section_by_id(section_id).get_data_hex()
            assert section_data[:4] == bytearray([section_id % 256] * 4)
