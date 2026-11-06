"""The Variables tab: the field variables the game and Cronos use, named, shown and edited by number."""
import json
import os
import pathlib
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from Common.dirtytracking import install_dirty_tracking
from Hyne.hynemanager import (
    CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_LEN, CRC_SPAN_START, HyneManager, IMAGE_SIZE, crc16_ff8, lzss_compress,
    lzss_decompress,
)
from Hyne.hynesavemap import FIELD_VARS_ELSEWHERE, FieldVariables, NB_FIELD_VARS, field_var_tab
from Hyne.hynewidget import HyneWidget

REPO = pathlib.Path(__file__).parent.parent.parent
CATALOGUE = REPO / "FF8GameData" / "Resources" / "json" / "hyne_field_variables.json"
VARS = 3808
FFNX_RESERVED = range(753, 817)


def _write_save(path, values=()):
    image = bytearray(IMAGE_SIZE)
    for var, value in values:
        image[VARS + var] = value
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress(bytes(image))
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


def _image(path):
    raw = path.read_bytes()
    return bytearray(lzss_decompress(raw[4:4 + struct.unpack_from("<I", raw)[0]]))


@pytest.fixture(scope="module")
def entries():
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shared_widget():
    return HyneWidget(str(REPO / "Resources"), str(REPO / "FF8GameData"))


@pytest.fixture
def save(tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write_save(path, [(261, 3), (730, 0x05), (819, 2), (72, 9)])
    return path


@pytest.fixture
def page(shared_widget, save):
    shared_widget.manager.load_file(str(save))
    shared_widget.tabs.setEnabled(True)
    page = shared_widget.field_variables_page
    page.search_edit.clear()
    page.cronos_check.setChecked(True)
    page.only_set_check.setChecked(False)
    page.reload()
    return page


def _select(page, var):
    row = next(row for row, entry in enumerate(page.entries) if entry["var"] == var)
    page.table.setCurrentCell(row, 0)
    return row


def _tracked(tool):
    if not hasattr(tool, "dirty_state"):   # the host window installs it
        install_dirty_tracking(tool)
    tool.dirty_state.clear()
    return tool


def _shown(page):
    return [entry["var"] for row, entry in enumerate(page.entries) if not page.table.isRowHidden(row)]


class TestCatalogue:
    def test_variables_never_overlap(self, entries):
        end = 0
        for entry in entries:
            assert entry["var"] >= end, entry["var"]
            end = entry["var"] + entry["size"]
        assert end <= NB_FIELD_VARS

    def test_every_entry_says_something(self, entries):
        for entry in entries:
            assert entry["size"] in (1, 2, 4) and entry["text"], entry["var"]
            assert "**" not in entry["text"] and "<sub>" not in entry["text"], entry["var"]
            assert entry["nb_fields"] >= len(entry["fields"])

    def test_named_flags_are_bits_of_a_byte(self, entries):
        for entry in entries:
            if "flags" in entry:
                assert entry["size"] == 1, entry["var"]
                assert set(entry["flags"]) <= {str(1 << bit) for bit in range(8)}, entry["var"]

    def test_nothing_sits_in_the_blocks_ffnx_reserves(self, entries):
        assert not [entry["var"] for entry in entries if entry["var"] in FFNX_RESERVED]

    def test_cronos_gives_each_quest_its_own_byte(self, entries):
        cronos = {entry["var"]: entry for entry in entries if entry.get("mod") == "Cronos"}
        assert sorted(cronos) == [817, 818, 819, 820, 821, 822, 1020, 1022]
        assert cronos[818]["fields"] == ["bgbook_1"] and cronos[819]["fields"] == ["bgeat_1"]

    def test_the_card_rules_are_named(self, entries):
        by_var = {entry["var"]: entry for entry in entries}
        assert "card game rules" in by_var[292]["text"]

    def test_each_use_of_a_reused_variable_is_told(self, entries):
        by_var = {entry["var"]: entry for entry in entries}
        assert "Tomb of the Unknown King" in by_var[728]["text"] and "Timber" in by_var[728]["text"]

    def test_how_sure_is_always_said(self, entries):
        for entry in entries:
            assert entry.get("certainty") in ("sure", "likely", "unknown", None), entry["var"]

    def test_what_the_engine_alone_uses_is_listed(self, entries):
        by_var = {entry["var"]: entry for entry in entries}
        assert by_var[180]["nb_fields"] == 0 and "Draw point" in by_var[180]["text"]
        assert by_var[243]["flags"]["128"] == "Saving sealed"

    def test_named_values_are_numbers(self, entries):
        for entry in entries:
            assert all(key.lstrip("-").isdigit() for key in entry.get("values", {})), entry["var"]


class TestView:
    def test_values_by_width_and_sign(self):
        view = FieldVariables(bytearray(IMAGE_SIZE))
        view.set_value(16, -2, 2, True)
        assert view.value(16, 2, True) == -2 and view.value(16, 2) == 0xFFFE and view.value(16) == 0xFE
        view.set_value(72, 0x01020304, 4)
        assert view.value(72, 4) == 0x01020304 and view.value(72) == 4

    def test_json_leaves_out_zeros_and_what_another_tab_holds(self):
        view = FieldVariables(bytearray(IMAGE_SIZE))
        view.set_value(261, 3)
        view.set_value(72, 9)
        assert view.to_dict() == {"261": 3}

    def test_json_does_not_write_what_another_tab_holds(self):
        view = FieldVariables(bytearray(IMAGE_SIZE))
        view.from_dict({"261": 3, "72": 9})
        assert view.value(261) == 3 and view.value(72) == 0

    def test_negative_values_read_as_negative(self, entries):
        by_var = {entry["var"]: entry for entry in entries}
        for var in (108, 112, 184, 186, 199, 200, 202, 213, 448):
            assert by_var[var]["signed"], var
        image = bytearray(IMAGE_SIZE)
        image[VARS + 112:VARS + 116] = b"\xFF" * 4
        assert FieldVariables(image).value(112, 4, True) == -1

    def test_json_round_trip(self):
        view = FieldVariables(bytearray(IMAGE_SIZE))
        view.set_value(730, 5)
        view.set_value(1020, 40, 2)
        other = FieldVariables(bytearray(IMAGE_SIZE))
        other.from_dict(view.to_dict())
        assert other.buffer == view.buffer

    def test_the_tabs_are_named(self):
        assert field_var_tab(72) == "Misc" and field_var_tab(256) == "Progress" and field_var_tab(261) is None
        assert field_var_tab(785) == "Battle" and field_var_tab(816) == "Battle" and field_var_tab(817) is None
        for first, last, _tab in FIELD_VARS_ELSEWHERE:
            assert first <= last


class TestPage:
    def test_values_come_from_the_save(self, page):
        row = _select(page, 261)
        assert page.table.item(row, page.COLUMN_VALUE).text() == "3"
        assert page.value_spin.value() == 3 and page.value_spin.isEnabled()

    def test_editing_writes_only_that_variable(self, page, save):
        manager = page.tool.manager
        _select(page, 261)
        page.value_spin.setValue(77)
        assert manager.field_variables.value(261) == 77
        manager.save_file(str(save), backup=False)
        saved = _image(save)
        assert saved[VARS + 261] == 77 and saved[VARS + 262] == 0

    def test_a_bit_keeps_the_others(self, page):
        _select(page, 730)
        assert page.bit_checks[0].isChecked() and page.bit_checks[2].isChecked() and not page.bit_checks[1].isChecked()
        page.bit_checks[1].setChecked(True)
        assert page.tool.manager.field_variables.value(730) == 7
        assert page.value_spin.value() == 7
        page.bit_checks[0].setChecked(False)
        assert page.tool.manager.field_variables.value(730) == 6

    def test_bits_carry_their_names(self, page):
        _select(page, 730)
        assert "Joined Garden Festival" in page.bit_checks[0].text()
        _select(page, 258)
        assert page.bit_checks[3].text() == "8"     # no meaning found for this bit

    def test_bits_only_for_a_byte(self, page):
        _select(page, 1020)
        assert page.bit_group.isHidden()
        _select(page, 819)
        assert not page.bit_group.isHidden()

    def test_a_variable_another_tab_holds_is_only_shown(self, page):
        _select(page, 72)
        assert not page.value_spin.isEnabled() and "Misc" in page.fields_label.text()
        assert page.value_spin.value() == 9

    def test_the_value_is_named(self, page):
        _select(page, 720)
        page.value_spin.setValue(2)
        assert page.value_name_label.text() == "SeeD uniform"
        assert "2: SeeD uniform" in page.text_view.toPlainText()
        page.value_spin.setValue(9)
        assert page.value_name_label.text() == ""

    def test_how_sure_is_shown(self, page):
        row = _select(page, 261)
        assert page.table.item(row, 3).text() == "Sure"

    def test_a_word_stays_in_range(self, page):
        _select(page, 1020)
        assert page.value_spin.maximum() == 0xFFFF and page.value_spin.minimum() == 0

    def test_search(self, page):
        page.search_edit.setText("buel")
        assert {817, 819} <= set(_shown(page))     # the quest flag and its counter
        page.search_edit.setText("fish fins cronos")
        assert 818 in _shown(page)
        page.search_edit.setText("Rosetta Stone taken")      # a bit's name
        assert 375 in _shown(page)
        page.search_edit.setText("730")
        assert _shown(page) == [730]

    def test_cronos_variables_come_with_the_box(self, page):
        page.cronos_check.setChecked(False)
        assert 261 in _shown(page) and not {817, 818, 819, 820, 821, 822, 1020, 1022} & set(_shown(page))
        page.cronos_check.setChecked(True)
        assert {261, 817, 818, 819, 820, 821, 822, 1020, 1022} <= set(_shown(page))

    def test_the_box_is_remembered(self, page, monkeypatch):
        stored = {}

        class Settings:
            def value(self, key, default=None, type=None):
                return stored.get(key, default)

            def setValue(self, key, value):
                stored[key] = value
        monkeypatch.setattr(page.tool, "settings", Settings())
        page.cronos_check.setChecked(False)
        assert stored[page.CRONOS_SETTING] is False
        page.cronos_check.setChecked(True)
        assert stored[page.CRONOS_SETTING] is True

    def test_only_values_set(self, page):
        page.only_set_check.setChecked(True)
        assert _shown(page) == [72, 261, 730, 819]

    def test_choosing_what_to_show_edits_nothing(self, page):
        tool = _tracked(page.tool)
        page.search_edit.setText("x")
        page.cronos_check.click()
        page.only_set_check.click()
        _select(page, 261)
        page.reload()
        assert not tool.dirty_state.dirty

    def test_an_edit_is_unsaved(self, page):
        tool = _tracked(page.tool)
        _select(page, 261)
        page.value_spin.setValue(9)
        assert tool.dirty_state.dirty
