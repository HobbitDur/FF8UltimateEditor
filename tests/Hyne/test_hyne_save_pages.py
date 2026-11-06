"""Hyne's savemap tabs (progress, party, battle, shops, draw points, world map, Chocobo World, load
screen), the values the save holds twice, and the small additions to the Items, Characters and
G-Forces tabs. Offsets are the image's, as in myst6re's SaveData.h and FF8_EN.exe."""
import argparse
import json
import os
import pathlib
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSpinBox

_APP = QApplication.instance() or QApplication([])

from Cli.hyne import _cmd_export_json, _cmd_import_json
from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_LEN, CRC_SPAN_START, HyneManager, IMAGE_SIZE, crc16_ff8, lzss_compress,
    lzss_decompress,
)
from Hyne.hynesavemap import SHOP_UNVISITED_BYTES
from Hyne.hynewidget import HyneWidget

REPO = pathlib.Path(__file__).parent.parent.parent
BLOCK = 3664
VARS = 3808
WORLD = 5088
CHOCOBO = 5344
PARTY_BYTES = 3188
GIL = 3212
LAGUNA_GIL = 3216
CHARACTER = 1552
CHARACTER_SIZE = 152
HEADER_GIL = 396
HEADER_LEVEL = 404
HEADER_PARTY = 405
HEADER_TIME = 400
HEADER_DISC = 456
HEADER_HP = 390
HEADER_LOCATION = 388


def _image():
    """A CRC-correct image: Squall and Zell in the party, everything else zero or a plain pattern."""
    image = bytearray(IMAGE_SIZE)
    image[BLOCK:BLOCK + 144] = bytes((i * 7 + 3) & 0x7F for i in range(144))
    image[PARTY_BYTES:PARTY_BYTES + 4] = bytes([0, 1, 0xFF, 0xFF])
    struct.pack_into("<I", image, GIL, 1000)
    struct.pack_into("<I", image, LAGUNA_GIL, 2000)
    struct.pack_into("<I", image, VARS + 72, 1000)
    struct.pack_into("<I", image, VARS + 76, 2000)
    for index in range(8):
        image[CHARACTER + index * CHARACTER_SIZE + 8] = index
    struct.pack_into("<I", image, CHARACTER + 4, 5500)        # Squall's EXP: level 6
    struct.pack_into("<H", image, CHARACTER, 321)             # Squall's HP
    image[BLOCK + 82] = 0                                     # not in a dream
    image[VARS + 204] = 2                                     # disc 2
    struct.pack_into("<I", image, BLOCK, 3661)                # play time
    struct.pack_into("<I", image, HEADER_GIL, 1000)
    image[HEADER_LEVEL] = 6
    image[HEADER_PARTY:HEADER_PARTY + 3] = bytes([0, 1, 0xFF])
    struct.pack_into("<I", image, HEADER_TIME, 3661)
    struct.pack_into("<I", image, HEADER_DISC, 1)
    struct.pack_into("<H", image, HEADER_HP, 321)
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


def _changes(before, after):
    crc = {CRC_OFFSET_1, CRC_OFFSET_1 + 1, CRC_OFFSET_2, CRC_OFFSET_2 + 1}
    return {i for i in range(IMAGE_SIZE) if before[i] != after[i]} - crc


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
    """Refills only the savemap pages: a whole load rebuilds the Items table."""
    shared_widget.manager.load_file(str(save))
    shared_widget.tabs.setEnabled(True)
    for page in shared_widget.save_pages:
        page.reload()
    return shared_widget


class TestFieldsAreWhereTheSaveHasThem:
    def test_progress(self, manager):
        buffer = manager.buffer
        struct.pack_into("<I", buffer, VARS + 4, 123456)
        struct.pack_into("<H", buffer, VARS + 16, 1250)
        struct.pack_into("<H", buffer, VARS + 256, 894)
        buffer[VARS + 204] = 3
        buffer[BLOCK + 99] = 30
        progress = manager.progress
        assert (progress.steps, progress.seed_points, progress.story_moment, progress.disc, progress.seed_test_level) == (
            123456, 1250, 894, 3, 30)
        assert progress.game_time == 3661

    def test_party(self, manager):
        buffer = manager.buffer
        buffer[BLOCK + 104:BLOCK + 107] = bytes([8, 9, 10])
        struct.pack_into("<HHH", buffer, BLOCK + 112, 2, 136, 546)
        struct.pack_into("<h", buffer, BLOCK + 118 + 2, -5)
        struct.pack_into("<h", buffer, BLOCK + 124 + 2, 7)
        struct.pack_into("<H", buffer, BLOCK + 130 + 2, 300)
        buffer[BLOCK + 136 + 1] = 64
        party = manager.party
        assert (party.party_1, party.party_2, party.party_3) == (8, 9, 10)
        assert (party.module, party.location, party.last_location) == (2, 136, 546)
        assert party.position(1) == (-5, 7, 300, 64)

    def test_battle(self, manager):
        buffer = manager.buffer
        struct.pack_into("<I", buffer, BLOCK + 12, 160)
        struct.pack_into("<H", buffer, BLOCK + 18, 8)
        struct.pack_into("<I", buffer, BLOCK + 24, 20)
        buffer[BLOCK + 52] = 0x02
        buffer[BLOCK + 60 + 2] = 0x01
        battle = manager.battle
        assert (battle.wins, battle.escapes, battle.tonberries) == (160, 8, 20)
        assert battle.magic_drawn[1] and not battle.magic_drawn[0]
        assert battle.enemies_scanned[16]

    def test_a_copy_written_twice(self, manager):
        manager.battle.wins = 321
        manager.battle.escapes = 12
        assert struct.unpack_from("<I", manager.buffer, BLOCK + 12)[0] == 321
        assert struct.unpack_from("<I", manager.buffer, VARS + 20)[0] == 321
        assert struct.unpack_from("<H", manager.buffer, BLOCK + 18)[0] == 12
        assert struct.unpack_from("<H", manager.buffer, VARS + 26)[0] == 12

    def test_battle_flags_keep_their_other_bits(self, manager):
        struct.pack_into("<I", manager.buffer, BLOCK + 28, 0x100)
        manager.battle.tonberry_king = True
        assert struct.unpack_from("<I", manager.buffer, BLOCK + 28)[0] == 0x101
        manager.battle.tonberry_king = False
        assert struct.unpack_from("<I", manager.buffer, BLOCK + 28)[0] == 0x100

    def test_world_map(self, manager):
        buffer = manager.buffer
        struct.pack_into("<H", buffer, WORLD + 96, 915)
        buffer[WORLD + 98] = 255
        buffer[WORLD + 110] = 2
        struct.pack_into("<H", buffer, WORLD + 112, 43640)
        buffer[WORLD + 116] = 0x04
        buffer[WORLD + 117] = 0x80
        buffer[WORLD + 118 + 3] = 0x02
        struct.pack_into("<h", buffer, WORLD + 2 * (2 * 6 + 1), -77)
        world = manager.world_map
        assert (world.steps, world.rental_car, world.displayed_map, world.car_steps) == (915, 255, 2, 43640)
        assert world.vehicles[2] and world.pupu_quest[7]
        assert world.obel_quest[3 * 8 + 1]
        assert world.position(2, 1) == -77

    def test_chocobo_numbers_are_decimal_digits(self, manager):
        buffer = manager.buffer
        struct.pack_into("<H", buffer, CHOCOBO + 4, 0x1234)
        struct.pack_into("<H", buffer, CHOCOBO + 12, 0xF567)
        buffer[CHOCOBO + 6] = 0
        chocobo = manager.chocobo
        assert (chocobo.weapon, chocobo.boko_id, chocobo.rank) == (1234, 567, 1)
        chocobo.weapon = 9087
        chocobo.boko_id = 123
        chocobo.rank = 5
        assert struct.unpack_from("<H", buffer, CHOCOBO + 4)[0] == 0x9087
        assert struct.unpack_from("<H", buffer, CHOCOBO + 12)[0] == 0xF123   # its high digit is not the ID's
        assert buffer[CHOCOBO + 6] == 4

    def test_chocobo_bad_digit_reads_as_nine_and_is_not_rewritten(self, manager):
        struct.pack_into("<H", manager.buffer, CHOCOBO + 4, 0x000F)
        assert manager.chocobo.weapon == 9
        assert struct.unpack_from("<H", manager.buffer, CHOCOBO + 4)[0] == 0x000F

    def test_draw_points_take_two_bits_each(self, manager):
        points = manager.draw_points
        points.set_state(0, 3)
        points.set_state(5, 2)
        points.set_state(255, 1)
        assert manager.buffer[VARS + 116] == 0x03
        assert manager.buffer[VARS + 116 + 1] == 0x02 << 2
        assert manager.buffer[VARS + 116 + 63] == 0x01 << 6
        assert (points.state(0), points.state(5), points.state(255), points.state(1)) == (3, 2, 1, 0)
        points.set_state(0, 0)
        assert manager.buffer[VARS + 116] == 0

    def test_shops(self, manager):
        shops = manager.shops
        shops.set_visited(2, True, rare_slots=(1, 3))
        start = 2768 + 2 * 20
        assert manager.buffer[start + 16] == 1
        assert list(manager.buffer[start:start + 4]) == [1, 0, 1, 0]
        shops.set_item(2, 1, True)
        assert shops.has_item(2, 1)
        shops.set_visited(2, False)
        assert bytes(manager.buffer[start:start + 16]) == SHOP_UNVISITED_BYTES
        assert not shops.is_visited(2)

    def test_names(self, manager):
        header = manager.header
        header.squall_name = "Squall"
        header.boko_name = "Boko"
        assert header.squall_name == "Squall"
        assert header.boko_name == "Boko"
        assert manager.buffer[408:420].rstrip(b"\x00")
        assert manager.buffer[444:456].rstrip(b"\x00")
        assert not any(manager.buffer[420:444])


class TestValuesHeldTwice:
    def test_an_untouched_save_comes_back_identical(self, manager, save):
        before = _read_image(save)
        manager.save_file()
        assert _changes(before, _read_image(save)) == set()

    def test_a_copy_already_different_stays_when_untouched(self, game_data, save):
        """A save whose second copy differs (a hacked one) is left alone until gil is edited."""
        image = _image()
        struct.pack_into("<I", image, VARS + 72, 2)
        _write_save(save, image)
        manager = HyneManager(game_data)
        manager.load_file(str(save))
        manager.save_file()
        assert struct.unpack_from("<I", _read_image(save), VARS + 72)[0] == 2

    def test_gil_reaches_its_copy_and_the_load_screen(self, manager, save):
        before = _read_image(save)
        manager.misc.gil = 7777
        manager.save_file()
        after = _read_image(save)
        assert struct.unpack_from("<I", after, VARS + 72)[0] == 7777
        assert struct.unpack_from("<I", after, HEADER_GIL)[0] == 7777
        assert _changes(before, after) <= {*range(GIL, GIL + 4), *range(VARS + 72, VARS + 76), *range(HEADER_GIL, HEADER_GIL + 4)}

    def test_laguna_gil_reaches_the_load_screen_in_a_dream_only(self, manager, save):
        manager.misc.gil_laguna = 55
        manager.save_file()
        assert struct.unpack_from("<I", _read_image(save), VARS + 76)[0] == 55
        assert struct.unpack_from("<I", _read_image(save), HEADER_GIL)[0] == 1000
        manager.battle.special_flags |= 1
        manager.save_file()
        assert struct.unpack_from("<I", _read_image(save), HEADER_GIL)[0] == 55

    def test_kills_reach_their_copies_and_the_total(self, manager, save):
        manager.character_entries[1].kills = 40
        manager.character_entries[1].kos = 3
        manager.save_file()
        after = _read_image(save)
        assert struct.unpack_from("<H", after, VARS + 30)[0] == 40
        assert struct.unpack_from("<H", after, VARS + 46)[0] == 3
        assert struct.unpack_from("<I", after, VARS + 68)[0] == 40


class TestLoadScreenFollowsEdits:
    def test_exp_changes_the_level(self, manager, save):
        manager.character_entries[0].exp = 49999
        manager.save_file()
        assert _read_image(save)[HEADER_LEVEL] == 50

    def test_level_stops_at_100(self, manager, save):
        manager.character_entries[0].exp = 5_000_000
        manager.save_file()
        assert _read_image(save)[HEADER_LEVEL] == 100

    def test_party_shows_model_ids_and_the_new_leader(self, manager, save):
        manager.misc.party_mem1 = 0xFF
        manager.misc.party_mem2 = 3
        manager.character_entries[3].model_id = 9
        struct.pack_into("<I", manager.buffer, CHARACTER + 3 * CHARACTER_SIZE + 4, 12000)
        manager.character_entries[3].current_hp = 77
        manager.save_file()
        after = _read_image(save)
        assert list(after[HEADER_PARTY:HEADER_PARTY + 3]) == [0xFF, 9, 0xFF]
        assert after[HEADER_LEVEL] == 13
        assert struct.unpack_from("<H", after, HEADER_HP)[0] == 77

    def test_time_and_disc(self, manager, save):
        manager.progress.game_time = 9000
        manager.progress.disc = 3
        manager.save_file()
        after = _read_image(save)
        assert struct.unpack_from("<I", after, HEADER_TIME)[0] == 9000
        assert struct.unpack_from("<I", after, HEADER_DISC)[0] == 2

    def test_a_value_set_by_hand_stays(self, manager, save):
        manager.header.gil = 123
        manager.header.location = 44
        manager.save_file()
        after = _read_image(save)
        assert struct.unpack_from("<I", after, HEADER_GIL)[0] == 123
        assert struct.unpack_from("<H", after, HEADER_LOCATION)[0] == 44

    def test_a_second_save_keeps_following(self, manager, save):
        manager.misc.gil = 1
        manager.save_file()
        manager.misc.gil = 2
        manager.save_file()
        assert struct.unpack_from("<I", _read_image(save), HEADER_GIL)[0] == 2


class TestCli:
    def test_round_trip_is_byte_exact(self, save, tmp_path):
        exported = tmp_path / "save.json"
        output = tmp_path / "out.ff8"
        assert _cmd_export_json(argparse.Namespace(input=str(save), output=str(exported))) == 0
        data = json.loads(exported.read_text(encoding="utf-8"))
        kept = {key: data[key] for key in ("savemap", "gf_forgotten", "character_exist_flags")}
        exported.write_text(json.dumps(kept), encoding="utf-8")
        assert _cmd_import_json(argparse.Namespace(input=str(save), json=str(exported), output=str(output), no_backup=True)) == 0
        assert _read_image(output) == _read_image(save)

    def test_import_applies_a_section(self, save, tmp_path):
        patch = tmp_path / "patch.json"
        patch.write_text(json.dumps({"savemap": {"progress": {"steps": 42}, "world_map": {"vehicles": [0, 4]},
                                                 "draw_points": {"states": [3]}}}), encoding="utf-8")
        assert _cmd_import_json(argparse.Namespace(input=str(save), json=str(patch), output=None, no_backup=True)) == 0
        image = _read_image(save)
        assert struct.unpack_from("<I", image, VARS + 4)[0] == 42
        assert image[WORLD + 116] == 0x11
        assert image[VARS + 116] == 0x03


class TestPages:
    def test_every_tab_is_there(self, widget):
        names = [widget.tabs.tabText(index) for index in range(widget.tabs.count())]
        assert names[6:] == ["Progress", "Party", "Battle", "Shops", "Draw points", "World map", "Chocobo World", "Load screen",
                             "Variables"]

    def test_refilling_writes_nothing(self, widget, save):
        assert bytes(widget.manager.buffer) == bytes(_read_image(save))

    def test_a_moment_row_sets_the_moment_and_the_disc(self, widget):
        page = widget.progress_page
        row = next(index for index, (value, _location) in enumerate(page.moments) if value >= 901)
        page.moment_table.setCurrentCell(row, 0)
        progress = widget.manager.progress
        assert progress.story_moment == page.moments[row][0]
        assert progress.disc == 3
        assert page.moment_spin.value() == progress.story_moment

    def test_the_moment_value_selects_its_row(self, widget):
        page = widget.progress_page
        page.moment_spin.setValue(page.moments[20][0])
        assert page.moment_table.currentRow() == 20
        assert widget.manager.progress.disc == 1

    def test_disc_stays_with_the_option_off(self, widget):
        page = widget.progress_page
        page.auto_disc_check.setChecked(False)
        page.moment_spin.setValue(3900)
        assert widget.manager.progress.disc == 2
        page.auto_disc_check.setChecked(True)

    def test_seed_rank_is_shown(self, widget):
        widget.progress_page.seed_points_spin.setValue(1250)
        assert widget.progress_page.seed_rank_label.text() == "rank 12"

    def test_a_check_list_edits_its_bit_and_selects_all(self, widget):
        group = widget.progress_page.tutorial_group
        group.list_widget.item(9).setCheckState(Qt.CheckState.Checked)
        assert widget.manager.progress.tutorials[9]
        group.list_widget.item(9).setCheckState(Qt.CheckState.Unchecked)
        assert not widget.manager.progress.tutorials[9]
        group.all_check.click()
        assert all(widget.manager.progress.tutorials)
        assert group.list_widget.item(100).checkState() == Qt.CheckState.Checked

    def test_party_and_position(self, widget):
        page = widget.party_page
        page.party_combos[1].setCurrentIndex(page.party_combos[1].findData(8))
        assert widget.manager.party.party_2 == 8
        page.position_spins[2][0].setValue(-100)
        assert widget.manager.party.position(2)[0] == -100
        page.location_combo.setCurrentIndex(page.location_combo.findData(136, Qt.ItemDataRole.UserRole))
        assert widget.manager.party.location == 136
        page.dream_check.setChecked(True)
        assert widget.manager.battle.special_flags & 1

    def test_world_map_preset(self, widget):
        page = widget.party_page
        page.preset_combo.setCurrentIndex(2)
        preset = page.preset_combo.currentData()
        page.preset_button.click()
        assert widget.manager.party.position(0) == (preset["x"], preset["y"], preset["triangle"], preset["direction"])
        assert widget.manager.party.position(1) == (0, 0, 0, 0)

    def test_scan_list_names_the_monsters(self, widget):
        scan = widget.battle_page.scan_group.list_widget
        assert scan.item(0).text() == "Squall"
        assert scan.item(16 + 2).text() == "c0m002: Blobra"
        scan.item(16 + 2).setCheckState(Qt.CheckState.Checked)
        assert widget.manager.battle.enemies_scanned[18]

    def test_shop_page(self, widget):
        page = widget.shops_page
        page.shop_list.setCurrentRow(8)
        assert not page.items_group.isEnabled()
        page.visited_check.setChecked(True)
        assert widget.manager.shops.is_visited(8)
        assert page.items_group.isEnabled()
        assert not page.item_checks[11].isChecked()   # a rare item of the Esthar shop
        assert page.item_checks[0].isChecked()
        page.item_checks[0].setChecked(False)
        assert not widget.manager.shops.has_item(8, 0)
        page.shop_list.setCurrentRow(0)
        assert not page.visited_check.isChecked()

    def test_draw_points_page(self, widget):
        page = widget.draw_points_page
        page.state_combos[200].setCurrentIndex(3)
        assert widget.manager.draw_points.state(200) == 3
        page.all_combo.setCurrentIndex(2)
        page.all_button.click()
        assert widget.manager.draw_points.states == [2] * 256
        assert page.state_combos[0].currentIndex() == 2
        assert page.table.item(0, 1).text().startswith("Field - ")
        assert page.table.item(200, 1).text().startswith("World map - ")

    def test_chocobo_page(self, widget):
        page = widget.chocobo_page
        widget.manager.chocobo.level = 50
        widget.manager.chocobo.weapon = 1234
        page.reload()
        spins = {spin.value() for spin in page.findChildren(QSpinBox)}
        assert {50, 1234} <= spins
        weapon = next(spin for spin in page.findChildren(QSpinBox) if spin.value() == 1234)
        weapon.setValue(4321)
        assert struct.unpack_from("<H", widget.manager.buffer, CHOCOBO + 4)[0] == 0x4321

    def test_load_screen_refreshes_after_a_save(self, widget):
        widget.manager.misc.gil = 4242
        widget.save_file()
        assert widget.manager.header.gil == 4242


class TestOtherTabs:
    def test_names_on_the_misc_tab(self, widget):
        edit = widget.misc_name_edits["rinoa_name"]
        edit.setText("Rin")
        edit.editingFinished.emit()
        assert widget.manager.header.rinoa_name == "Rin"

    def test_gf_forgotten_slot(self, widget):
        widget.gf_list.clear()
        widget.gf_list.addItems([gf.gf_name for gf in widget.manager.gf_entries])
        widget.gf_list.setCurrentRow(2)
        widget.gf_forgotten_checks[4].setChecked(True)
        assert widget.manager.gf_entries[2].is_forgotten(5)
        widget.gf_forgotten_checks[4].setChecked(False)
        assert not widget.manager.gf_entries[2].is_forgotten(5)

    def test_character_lock_flags(self, widget):
        widget.character_list.clear()
        widget.character_list.addItems([c.name for c in widget.manager.character_entries])
        widget.character_list.setCurrentRow(1)
        mask, check = widget.char_exist_bit_checks[0]
        check.setChecked(True)
        assert widget.manager.character_entries[1].exist_flags & mask

    def test_battle_order_moves_keep_a_permutation(self, widget):
        widget.manager.misc.set_battle_order(list(range(32)))
        page = widget.items_extras_page
        page.reload()
        page.order_list.setCurrentRow(0)
        page.order_down.click()
        order = widget.manager.misc.get_battle_order()
        assert order[0] == 1 and order[1] == 0
        assert sorted(order) == list(range(32))
        assert page.order_list.currentRow() == 1

    def test_timber_maniacs(self, widget):
        widget.items_extras_page.timber_group.list_widget.item(3).setCheckState(Qt.CheckState.Checked)
        assert widget.manager.buffer[VARS + 304] & 0x08

    def test_all_items_and_sorting(self, widget):
        widget.manager.item_entries[0].item_id = 5
        widget.manager.item_entries[0].quantity = 9
        widget.manager.item_entries[1].item_id = 0
        widget.manager.item_entries[1].quantity = 0
        widget.manager.item_entries[2].item_id = 2
        widget.manager.item_entries[2].quantity = 4
        widget._sort_items(lambda item_id: item_id)
        pairs = [(entry.item_id, entry.quantity) for entry in widget.manager.item_entries]
        assert pairs[:3] == [(2, 4), (5, 9), (0, 0)]
        widget._fill_all_items()
        assert all(entry.item_id and entry.quantity == 100 for entry in widget.manager.item_entries[:198])
        assert len({entry.item_id for entry in widget.manager.item_entries[:198]}) == 198
