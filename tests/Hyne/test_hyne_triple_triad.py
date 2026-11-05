"""Hyne's Triple Triad tab: cards, rare card locations, rules, Queen of Cards, CC Group, counts.

The layout comes from the exe's TTCardData struct and the field scripts' card variables (see
Hyne/hynemanager.py). The game ignores a card's copies or location without its "ever obtained" flag
(GetOwnedCardCount@0x534950), so the tests also hold the tab to keeping them together.
"""
import argparse
import json
import os
import pathlib
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from CCGroup.cardlocation import LOCATION_PLAYER, NB_CARDS, RARE_CARD_FIRST_ID, starting_location
from Cli.hyne import _cmd_export_json, _cmd_import_json
from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_LEN, CRC_SPAN_START, FIELD_VARS_OFFSET, HyneManager, IMAGE_SIZE,
    TT_DATA_OFFSET, TT_FLAGS, TT_RARE_LOCATIONS, TT_RARE_OBTAINED, TT_SEED, TT_WINS,
    crc16_ff8, lzss_compress, lzss_decompress,
)
from Hyne.hynewidget import HyneWidget

REPO = pathlib.Path(__file__).parent.parent.parent
FIRST_RARE = RARE_CARD_FIRST_ID
LAST_RARE = NB_CARDS - 1


def _image():
    """A CRC-correct image with no card, no flag and every card variable at 0."""
    image = bytearray((i * 167 + 41) & 0xFF for i in range(IMAGE_SIZE))
    image[TT_DATA_OFFSET:TT_DATA_OFFSET + 128] = bytes(128)
    image[FIELD_VARS_OFFSET + 272:FIELD_VARS_OFFSET + 301] = bytes(29)
    image[FIELD_VARS_OFFSET + 475:FIELD_VARS_OFFSET + 479] = bytes(4)
    for card_id in range(FIRST_RARE, NB_CARDS):
        image[TT_RARE_LOCATIONS + card_id - FIRST_RARE] = starting_location(card_id)
    return image


def _write_save(path, image):
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress(bytes(image))
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


def _read_image(path):
    raw = path.read_bytes()
    return bytearray(lzss_decompress(raw[4:4 + struct.unpack_from("<I", raw)[0]]))


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(REPO / "FF8GameData"))


@pytest.fixture
def save(tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write_save(path, _image())
    return path


@pytest.fixture
def manager(game_data, save):
    manager = HyneManager(game_data)
    manager.load_file(str(save))
    return manager


@pytest.fixture(scope="module")
def shared_widget():
    return HyneWidget(str(REPO / "Resources"), str(REPO / "FF8GameData"))


@pytest.fixture
def widget(shared_widget, save):
    """Reloads only this tab: a whole load rebuilds the Items table, ~3 s for each test."""
    shared_widget.manager.load_file(str(save))
    shared_widget.tabs.setEnabled(True)
    shared_widget._reload_triple_triad()
    return shared_widget


class TestLayout:
    def test_block_is_where_the_exe_has_it(self):
        assert TT_DATA_OFFSET == 5216
        assert TT_RARE_OBTAINED - TT_DATA_OFFSET == 110
        assert TT_FLAGS - TT_DATA_OFFSET == 115
        assert TT_WINS - TT_DATA_OFFSET == 116
        assert TT_SEED - TT_DATA_OFFSET == 124
        assert FIELD_VARS_OFFSET + 272 == 4080   # savemap image offset = 3808 + variable

    def test_reads_the_raw_bytes(self, manager):
        buffer = manager.buffer
        buffer[TT_DATA_OFFSET + 5] = 0x80 | 42
        buffer[TT_RARE_OBTAINED + 1] = 0x02        # bit 9 = card 77 + 9
        buffer[TT_RARE_LOCATIONS + 9] = LOCATION_PLAYER
        struct.pack_into("<3H", buffer, TT_WINS, 7, 8, 9)
        struct.pack_into("<I", buffer, TT_SEED, 3_000_000_000)
        buffer[TT_FLAGS] = 1
        tt = manager.triple_triad
        assert (tt.is_obtained(5), tt.copies(5)) == (True, 42)
        assert not tt.is_obtained(6)
        assert (tt.is_obtained(86), tt.location(86)) == (True, LOCATION_PLAYER)
        assert not tt.is_obtained(85)
        assert (tt.wins, tt.losses, tt.draws, tt.seed) == (7, 8, 9, 3_000_000_000)
        assert tt.collection_complete


class TestKeptTogether:
    def test_copies_set_the_flag(self, manager):
        manager.triple_triad.set_copies(3, 12)
        assert manager.buffer[TT_DATA_OFFSET + 3] == 0x80 | 12

    def test_zero_copies_keep_the_flag(self, manager):
        """A card lost later stays known: the game keeps the flag too."""
        tt = manager.triple_triad
        tt.set_copies(3, 12)
        tt.set_copies(3, 0)
        assert manager.buffer[TT_DATA_OFFSET + 3] == 0x80

    def test_taking_the_flag_takes_the_copies(self, manager):
        tt = manager.triple_triad
        tt.set_copies(3, 12)
        tt.set_obtained(3, False)
        assert manager.buffer[TT_DATA_OFFSET + 3] == 0

    def test_rare_at_the_player_sets_the_flag(self, manager):
        tt = manager.triple_triad
        tt.set_location(FIRST_RARE, LOCATION_PLAYER)
        assert tt.is_obtained(FIRST_RARE)
        assert manager.buffer[TT_RARE_OBTAINED] == 0x01

    def test_rare_elsewhere_keeps_the_flag_as_it_was(self, manager):
        """A rare lost to a card player stays 'ever obtained'; one never owned stays not."""
        tt = manager.triple_triad
        tt.set_location(FIRST_RARE, 40)
        assert not tt.is_obtained(FIRST_RARE)
        tt.set_location(FIRST_RARE, LOCATION_PLAYER)
        tt.set_location(FIRST_RARE, 40)
        assert tt.is_obtained(FIRST_RARE)

    def test_taking_the_flag_of_a_held_rare_returns_it_to_its_first_owner(self, manager):
        tt = manager.triple_triad
        tt.set_location(LAST_RARE, LOCATION_PLAYER)
        tt.set_obtained(LAST_RARE, False)
        assert tt.location(LAST_RARE) == starting_location(LAST_RARE)

    def test_taking_the_flag_of_a_rare_held_by_someone_keeps_its_place(self, manager):
        tt = manager.triple_triad
        tt.set_obtained(LAST_RARE, True)
        tt.set_location(LAST_RARE, 40)
        tt.set_obtained(LAST_RARE, False)
        assert tt.location(LAST_RARE) == 40

    def test_last_rare_bit_is_the_33rd(self, manager):
        manager.triple_triad.set_obtained(LAST_RARE, True)
        assert manager.buffer[TT_RARE_OBTAINED + 4] == 0x01


class TestSharedBytes:
    def test_trade_rule_keeps_the_high_bits(self, manager):
        tt = manager.triple_triad
        tt.set_var(281, 0xF9)
        tt.set_region_trade_rule(1, 3)
        assert tt.var(281) == 0xFB
        assert tt.region_trade_rule(1) == 3

    def test_cc_quest_can_go_back_and_keeps_the_other_bits(self, manager):
        """myst6re's Hyne only ORs it in, so a step can never be taken back there."""
        tt = manager.triple_triad
        tt.set_var(475, 0x41)
        tt.set_var(477, 0xE0)
        tt.cc_quest = 0x221F
        assert (tt.var(475), tt.var(477)) == (0x41 | 0x22, 0xE0 | 0x1F)
        assert tt.cc_quest == 0x221F
        tt.cc_quest = 0x01
        assert (tt.var(475), tt.var(477)) == (0x41, 0xE1)
        assert tt.cc_quest == 0x01


class TestSave:
    def test_only_the_edited_bytes_and_the_crc_change(self, manager, save):
        before = bytearray(manager.buffer)
        manager.triple_triad.set_copies(3, 12)
        manager.triple_triad.set_location(FIRST_RARE, LOCATION_PLAYER)
        manager.save_file()
        after = _read_image(save)
        changed = {i for i in range(IMAGE_SIZE) if before[i] != after[i]}
        expected = {TT_DATA_OFFSET + 3, TT_RARE_LOCATIONS, TT_RARE_OBTAINED}
        assert expected <= changed <= expected | {CRC_OFFSET_1, CRC_OFFSET_1 + 1, CRC_OFFSET_2, CRC_OFFSET_2 + 1}

    def test_reloads(self, game_data, manager, save):
        manager.triple_triad.set_copies(76, 99)
        manager.triple_triad.wins = 321
        manager.save_file()
        reloaded = HyneManager(game_data)
        reloaded.load_file(str(save))
        assert reloaded.triple_triad.copies(76) == 99
        assert reloaded.triple_triad.wins == 321


class TestCli:
    def test_round_trip_is_byte_exact(self, save, tmp_path):
        exported = tmp_path / "save.json"
        output = tmp_path / "out.ff8"
        image = _image()
        image[TT_DATA_OFFSET + 7] = 0x80          # obtained, then lost
        image[TT_DATA_OFFSET + 8] = 0x80 | 100
        image[TT_RARE_OBTAINED] = 0x03
        image[TT_RARE_LOCATIONS] = LOCATION_PLAYER
        image[TT_RARE_LOCATIONS + 1] = 40
        image[FIELD_VARS_OFFSET + 272] = 0x87
        image[FIELD_VARS_OFFSET + 297] = 77
        _write_save(save, image)
        assert _cmd_export_json(argparse.Namespace(input=str(save), output=str(exported))) == 0
        data = json.loads(exported.read_text(encoding="utf-8"))["triple_triad"]
        assert data["common_cards"][8] == [True, 100]
        exported.write_text(json.dumps({"triple_triad": data}), encoding="utf-8")
        assert _cmd_import_json(argparse.Namespace(input=str(save), json=str(exported), output=str(output),
                                                   no_backup=True)) == 0
        assert _read_image(output) == _read_image(save)

    def test_import_applies_the_cards(self, save, tmp_path):
        patch = tmp_path / "patch.json"
        patch.write_text(json.dumps({"triple_triad": {"common_cards": [[True, 50]], "wins": 12, "cc_quest": 3}}))
        assert _cmd_import_json(argparse.Namespace(input=str(save), json=str(patch), output=None, no_backup=True)) == 0
        image = _read_image(save)
        assert image[TT_DATA_OFFSET] == 0x80 | 50
        assert struct.unpack_from("<H", image, TT_WINS)[0] == 12
        assert image[FIELD_VARS_OFFSET + 477] & 0x1F == 3


class TestWidget:
    def test_tab_shows_every_card(self, widget):
        assert widget.tabs.tabText(5) == "Triple Triad"
        assert widget.tt_common_table.rowCount() == 77
        assert widget.tt_rare_table.rowCount() == 33
        assert "Geezard" in widget.tt_common_table.item(0, 0).text()
        assert widget.tt_rare_table.item(0, 0).text().startswith("Lv8")
        assert widget.tt_rare_table.item(32, 0).text().startswith("Lv10")

    def test_loading_writes_nothing(self, widget, save):
        assert bytes(widget.manager.buffer) == bytes(_read_image(save))

    def test_copies_tick_obtained(self, widget):
        widget.tt_common_spins[9].setValue(33)
        assert widget.manager.buffer[TT_DATA_OFFSET + 9] == 0x80 | 33
        assert widget.tt_common_checks[9].isChecked()

    def test_unticking_obtained_clears_the_copies(self, widget):
        widget.tt_common_spins[9].setValue(33)
        widget.tt_common_checks[9].setChecked(False)
        assert widget.manager.buffer[TT_DATA_OFFSET + 9] == 0
        assert widget.tt_common_spins[9].value() == 0

    def test_location_to_player_ticks_obtained(self, widget):
        combo = widget.tt_rare_combos[FIRST_RARE]
        combo.setCurrentIndex(combo.findData(LOCATION_PLAYER, Qt.ItemDataRole.UserRole))
        assert widget.manager.triple_triad.location(FIRST_RARE) == LOCATION_PLAYER
        assert widget.tt_rare_checks[FIRST_RARE].isChecked()

    def test_rare_combo_shows_the_saved_location(self, widget):
        assert widget.tt_rare_combos[LAST_RARE].currentData(Qt.ItemDataRole.UserRole) == starting_location(LAST_RARE)
        assert "starting owner" in widget.tt_rare_combos[LAST_RARE].currentText()

    def test_all_copies_and_all_to_player(self, widget):
        widget.tt_all_copies_spin.setValue(100)
        widget.tt_all_copies_button.click()
        widget.tt_all_rare_button.click()
        tt = widget.manager.triple_triad
        assert all(tt.is_obtained(c) and tt.copies(c) == 100 for c in range(FIRST_RARE))
        assert all(tt.is_obtained(c) and tt.location(c) == LOCATION_PLAYER for c in range(FIRST_RARE, NB_CARDS))
        assert widget.tt_all_common_check.isChecked() and widget.tt_all_rare_check.isChecked()

    def test_all_obtained_checkboxes(self, widget):
        widget.tt_all_copies_button.click()
        widget.tt_all_common_check.click()    # the button ticked it: this unticks all
        tt = widget.manager.triple_triad
        assert not any(tt.is_obtained(c) or tt.copies(c) for c in range(FIRST_RARE))

    def test_rules_edit_their_own_bit(self, widget):
        tt = widget.manager.triple_triad
        tt.set_var(274, 0x20)     # a bit no rule uses, kept
        widget._reload_triple_triad()
        check = next(c for number, mask, c in widget.tt_rule_checks if number == 274 and mask == 0x04)
        check.setChecked(True)
        assert tt.var(274) == 0x24
        check.setChecked(False)
        assert tt.var(274) == 0x20

    def test_last_rules_and_regions(self, widget):
        tt = widget.manager.triple_triad
        check = next(c for number, mask, c in widget.tt_rule_checks if number == 289 and mask == 0x80)
        check.setChecked(True)
        assert tt.var(289) == 0x80
        number, combo = widget.tt_last_region_combos[1]
        combo.setCurrentIndex(combo.findData(8))
        assert (number, tt.var(291)) == (291, 8)

    def test_trade_rule_queen_and_cc_group(self, widget):
        tt = widget.manager.triple_triad
        widget.tt_trade_combos[7].setCurrentIndex(widget.tt_trade_combos[7].findData(4))
        assert tt.region_trade_rule(7) == 4
        widget.tt_queen_location_combo.setCurrentIndex(widget.tt_queen_location_combo.findData(6))
        assert tt.var(295) == 6
        widget.tt_queen_quest_combo.setCurrentIndex(widget.tt_queen_quest_combo.findData(5))
        assert tt.var(300) == 5
        widget.tt_rating_spin.setValue(200)
        assert tt.var(297) == 200
        widget.tt_cc_combo.setCurrentIndex(widget.tt_cc_combo.findData(0x221F))
        assert tt.cc_quest == 0x221F

    def test_counts(self, widget):
        tt = widget.manager.triple_triad
        widget.tt_count_spins["draws"].setValue(60000)
        assert tt.draws == 60000
        widget.tt_bgu_wins_spin.setValue(9)
        assert tt.var(478) == 9
        widget.tt_seed_spin.setValue(3_000_000_000)
        assert tt.seed == 3_000_000_000
        widget.tt_complete_check.setChecked(True)
        assert tt.collection_complete

    def test_unknown_values_are_kept(self, widget, save):
        """A save with values outside the known lists shows them and changes nothing."""
        image = _image()
        image[FIELD_VARS_OFFSET + 477] = 0x09     # not a CC Group step
        image[FIELD_VARS_OFFSET + 299] = 7        # no trade rule has this number
        _write_save(save, image)
        widget.load_file(str(save))     # the whole load path, once
        assert widget.tt_cc_combo.currentData() == 0x09
        assert widget.tt_queen_trade_combo.currentData() == 7
        assert bytes(widget.manager.buffer) == bytes(_read_image(save))

    def test_preview_follows_the_selection(self, widget):
        widget.tt_common_table.setCurrentCell(4, 0)
        assert widget.tt_card_name.text() == widget._card_info[4]["name"]
        assert widget.tt_card_preview.pixmap().width() == 128
        widget.tt_rare_table.setCurrentCell(2, 0)
        assert widget.tt_card_name.text() == widget._card_info[FIRST_RARE + 2]["name"]
