"""Hyne with a mod's files: magic names from kernel.bin, draw_data.csv, shop.bin, field folders naming the
Deck IDs, and scene.out telling where the enemies scanned once are (FFNx moves them)."""
import os
import pathlib
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from CCGroup.cardlocation import LOCATION_PLAYER, RARE_CARD_FIRST_ID, starting_location
from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    HyneManager, CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_LEN, CRC_SPAN_START, IMAGE_SIZE, crc16_ff8, lzss_compress, lzss_decompress,
)
from Hyne.hynesavemap import read_shop_file, scene_uses_extra_monsters
from Hyne.hynewidget import HyneWidget

REPO = pathlib.Path(__file__).parent.parent.parent
VANILLA_SHOP = REPO / "extracted_files" / "menu" / "shop.bin"
BLOCK = 3664
VARS = 3808
SCANNED_VANILLA = BLOCK + 60
SCANNED_MOVED = VARS + 785


def _write_save(path, moved_bits=False):
    image = bytearray(IMAGE_SIZE)
    if moved_bits:
        image[SCANNED_MOVED + 2] = 0x04     # bit 18
    image[SCANNED_VANILLA] = 0x80           # bit 7, in the vanilla list
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress(bytes(image))
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


def lzss_decompress_save(path):
    raw = path.read_bytes()
    return lzss_decompress(raw[4:4 + struct.unpack_from("<I", raw)[0]])


def write_image(path, image):
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    compressed = lzss_compress(bytes(image))
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


@pytest.fixture(scope="module")
def shared_widget():
    return HyneWidget(str(REPO / "Resources"), str(REPO / "FF8GameData"))


@pytest.fixture
def save(tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write_save(path)
    return path


@pytest.fixture
def widget(shared_widget, save):
    shared_widget.manager.scene_uses_extra_monsters = None
    shared_widget.kernel_names.magic = {}
    shared_widget._relabel_magic()
    shared_widget.draw_points_page.set_magic_ids(None)
    shared_widget.shops_page.file_shops = None
    shared_widget.set_deck_users({})
    shared_widget.manager.load_file(str(save))
    shared_widget.tabs.setEnabled(True)
    for page in shared_widget.save_pages:
        page.reload()
    shared_widget._reload_triple_triad()
    return shared_widget


class TestMagicNames:
    def test_the_kernel_names_every_list(self, widget):
        widget.kernel_names.magic = {43: "Reaper"}
        widget._relabel_magic()
        combo = widget.char_magic_combos[0]
        assert combo.itemText(combo.findData(43)) == "43: Reaper"
        junction = widget.char_junction_combos["jun_str"]
        assert junction.itemText(junction.findData(43)) == "43: Reaper"
        assert widget.battle_page.magic_group.list_widget.item(42).text() == "Reaper"

    def test_without_a_kernel_the_built_in_name_comes_back(self, widget):
        built_in = widget._magic_names[43]
        widget.kernel_names.magic = {43: "Reaper"}
        widget._relabel_magic()
        widget.kernel_names.magic = {}
        widget._relabel_magic()
        assert widget.char_magic_combos[0].itemText(widget.char_magic_combos[0].findData(43)) == f"43: {built_in}"

    def test_relabeling_edits_nothing(self, widget, save):
        before = bytes(widget.manager.buffer)
        widget.kernel_names.magic = {1: "Flame", 43: "Reaper"}
        widget._relabel_magic()
        assert bytes(widget.manager.buffer) == before

    def test_a_real_kernel_gives_magic_names(self, shared_widget):
        kernel = REPO / "extracted_files" / "main" / "kernel.bin"
        if not kernel.exists():
            pytest.skip("no extracted kernel.bin")
        from FF8GameData.kernelnames import read_weapon_and_ability_names
        shared_widget.game_data.load_kernel_data()
        names = read_weapon_and_ability_names(shared_widget.game_data, str(kernel))
        assert names["magic"][1] == "Fire"


class TestDrawData:
    def test_csv_replaces_the_magic(self, widget, tmp_path):
        path = tmp_path / "draw_data.csv"
        path.write_text("Draw ID|Magic ID|High Yield|Refill|X|Y|Sub ID\n1|43|0|1|0|0|0\n256|1|0|0|0|0|0\n", encoding="utf-8")
        widget._load_draw_data(str(path))
        page = widget.draw_points_page
        assert page.magic_ids[0] == 43
        assert page.magic_ids[255] == 1
        assert page.magic_ids[1] == widget.hyne_data["draw_point_magic"][1]
        assert page.table.item(0, 0).text() == widget.magic_label(43)
        assert "draw_data.csv" in page.note.text()

    def test_closing_gives_the_vanilla_magic_back(self, widget, tmp_path):
        path = tmp_path / "draw_data.csv"
        path.write_text("Draw ID|Magic ID\n1|43\n", encoding="utf-8")
        widget._load_draw_data(str(path))
        widget.draw_points_page.set_magic_ids(None)
        assert widget.draw_points_page.magic_ids == widget.hyne_data["draw_point_magic"]

    def test_a_magic_rename_reaches_the_table(self, widget, tmp_path):
        path = tmp_path / "draw_data.csv"
        path.write_text("Draw ID|Magic ID\n1|43\n", encoding="utf-8")
        widget._load_draw_data(str(path))
        widget.kernel_names.magic = {43: "Reaper"}
        widget._relabel_magic()
        assert widget.draw_points_page.table.item(0, 0).text() == "Reaper"

    def test_a_bad_file_keeps_the_list(self, widget, tmp_path, monkeypatch):
        from Hyne import hynewidget
        monkeypatch.setattr(hynewidget.QMessageBox, "warning", lambda *_args: None)
        path = tmp_path / "other.csv"
        path.write_text("a|b\n1|2\n", encoding="utf-8")
        widget._load_draw_data(str(path))
        assert widget.draw_points_page.magic_ids == widget.hyne_data["draw_point_magic"]


class TestShopFile:
    def _file(self, doubled=False):
        data = bytearray()
        for shop in range(20):
            for slot in range(16):
                data += bytes([shop + slot + 1, 0x00 if slot == 3 else 0xFF])
        return bytes(data) + bytes(640) if doubled else bytes(data)

    def test_reads_items_and_rare_flags(self):
        shops = read_shop_file(self._file())
        assert shops[2][0][:3] == [3, 4, 5]
        assert shops[2][1] == [3]

    def test_only_the_first_640_bytes_count(self):
        """Cronos's file has the vanilla list again after its own: the game reads the first."""
        assert read_shop_file(self._file(doubled=True)) == read_shop_file(self._file())

    def test_too_small_is_refused(self):
        with pytest.raises(ValueError):
            read_shop_file(bytes(100))

    @pytest.mark.skipif(not VANILLA_SHOP.exists(), reason="no extracted shop.bin")
    def test_vanilla_file_is_the_built_in_table(self, shared_widget):
        shops = read_shop_file(VANILLA_SHOP.read_bytes())
        page = shared_widget.shops_page
        for shop in range(20):
            table = page.SHOP_ITEM_TABLES.get(shop, 1)
            assert shops[shop][0] == page.item_tables[table]

    def test_page_shows_the_file(self, widget, tmp_path):
        path = tmp_path / "shop.bin"
        path.write_bytes(self._file())
        widget._load_shop_file(str(path))
        page = widget.shops_page
        page.shop_list.setCurrentRow(0)
        assert page.item_labels[0].text() == widget.kernel_names.item_name(1)
        assert page.item_labels[3].font().italic()
        assert not page.item_labels[4].font().italic()
        assert read_shop_file(bytes([1, 128, 2, 129] * 320))[0][1] == list(range(0, 16, 2))    # as the game's test


class TestDeckIdNames:
    def _combo(self, widget):
        widget.manager.triple_triad.set_location(RARE_CARD_FIRST_ID, starting_location(RARE_CARD_FIRST_ID))
        widget._reload_cards()
        return widget.tt_rare_combos[RARE_CARD_FIRST_ID]

    def test_vanilla_place_without_folders(self, widget):
        combo = self._combo(widget)
        assert "starting owner" in combo.currentText()

    def test_folders_name_the_card_players(self, widget):
        location = starting_location(RARE_CARD_FIRST_ID)
        widget.set_deck_users({location: ["bgmon_4 joker", "rgroad11 joker"]})
        text = self._combo(widget).currentText()
        assert "bgmon_4 joker +1" in text
        assert not widget.tt_deck_clear_button.isHidden()

    def test_a_pocket_nobody_uses_says_so_with_folders(self, widget):
        widget.set_deck_users({3: ["bcmin21a Mam"]})
        model = widget.tt_location_model
        text = {model.item(row).data(Qt.ItemDataRole.UserRole): model.item(row).text() for row in range(model.rowCount())}
        assert text[3].endswith("bcmin21a Mam")
        assert " - " not in text[4]   # the vanilla place no longer applies

    def test_relabeling_keeps_the_location(self, widget):
        combo = self._combo(widget)
        combo.setCurrentIndex(combo.findData(LOCATION_PLAYER, Qt.ItemDataRole.UserRole))
        widget.set_deck_users({3: ["x y"]})
        assert widget.manager.triple_triad.location(RARE_CARD_FIRST_ID) == LOCATION_PLAYER
        assert combo.currentData(Qt.ItemDataRole.UserRole) == LOCATION_PLAYER

    @pytest.mark.skipif(not (REPO / "extracted_files" / "field" / "mapdata").exists(), reason="no extracted field folder")
    def test_real_folder(self, shared_widget):
        users = HyneWidget.read_deck_users(str(REPO / "extracted_files" / "field"))
        assert any("joker" in name for name in users[213])
        assert any("queen" in name for name in users[1])


class TestMagicPlace:
    """FFNx AddMoreMagic: a kernel.bin with a magic id of 96 or more moves the drawn-once list to variables 753-784."""

    def _kernel(self, widget, magic):
        widget.kernel_names.magic = magic
        widget._on_kernel_names_changed()

    @pytest.fixture(autouse=True)
    def _no_kernel_after(self, shared_widget):
        yield
        self._kernel(shared_widget, {})

    def test_a_stock_kernel_leaves_the_list_in_the_save(self, widget):
        self._kernel(widget, {43: "Reaper"})
        assert not widget.manager.battle.magic_moved
        assert len(widget.manager.battle.magic_drawn) == 64

    def test_a_grown_kernel_moves_it(self, widget):
        self._kernel(widget, {96: "Meltdown"})
        battle = widget.manager.battle
        assert battle.magic_moved and len(battle.magic_drawn) == 256
        battle.magic_drawn[95] = True      # magic id 96
        assert widget.manager.buffer[VARS + 753 + 95 // 8] & (1 << (95 % 8))

    def test_exactly_96_entries_stay_in_the_save(self, widget):
        self._kernel(widget, {95: "Last"})   # ids 0-95, the count FFNx still leaves alone
        assert not widget.manager.battle.magic_moved

    def test_the_block_alone_moves_nothing(self, shared_widget, tmp_path):
        path = tmp_path / "old_cronos.ff8"
        _write_save(path)
        image_bytes = bytearray(lzss_decompress_save(path))
        image_bytes[VARS + 753] = 5        # quest flags of an older Cronos
        write_image(path, image_bytes)
        shared_widget.manager.load_file(str(path))
        assert not shared_widget.manager.battle.magic_moved

    def test_rows_follow_the_list_length(self, widget):
        rows = widget.battle_page.magic_group.list_widget
        widget.battle_page.reload()
        assert rows.count() == 256 and rows.item(63).isHidden() is False and rows.item(64).isHidden()
        self._kernel(widget, {96: "Meltdown"})
        assert not rows.item(95).isHidden()
        assert "Meltdown" in rows.item(95).text()

    def test_added_spells_can_be_chosen(self, widget):
        self._kernel(widget, {97: "Meltdown", 98: ""})   # the built-in list stops at 96
        combo = widget.char_magic_combos[0]
        assert combo.findData(97) >= 0 and "Meltdown" in combo.itemText(combo.findData(97))
        assert combo.findData(98) < 0        # a dummy row names nothing
        junction = next(iter(widget.char_junction_combos.values()))
        assert junction.findData(97) >= 0
        self._kernel(widget, {})
        assert combo.findData(97) < 0 and junction.findData(97) < 0

    def test_a_chosen_added_spell_stays_without_its_kernel(self, widget):
        self._kernel(widget, {97: "Meltdown"})
        combo = widget.char_magic_combos[0]
        combo.setCurrentIndex(combo.findData(97))
        self._kernel(widget, {})
        assert combo.currentData() == 97 and combo.currentText() == "97: (unknown)"


class TestScanPlace:
    def _scene(self, com_id):
        data = bytearray(128 * 3)
        data[128 + 56 + 2] = com_id
        return bytes(data)

    def test_scene_test_is_ffnx_s(self):
        assert not scene_uses_extra_monsters(self._scene(159))
        assert scene_uses_extra_monsters(self._scene(160))

    def test_default_is_the_vanilla_list(self, widget):
        battle = widget.manager.battle
        assert not battle.scan_moved
        assert battle.enemies_scanned[7]
        assert widget.battle_page.scan_group.list_widget.item(200).isHidden()

    def test_the_block_alone_shows_nothing_in_the_tool(self, widget, save):
        _write_save(save, moved_bits=True)
        widget.manager.load_file(str(save))
        widget.battle_page.reload()
        assert not widget.manager.battle.scan_moved
        assert widget.battle_page.scan_moved_check.isHidden()
        assert widget.manager.buffer[SCANNED_MOVED + 2] == 0x04     # still in the save

    def test_the_cli_goes_by_the_block(self, save):
        _write_save(save, moved_bits=True)
        manager = HyneManager(GameData(str(REPO / "FF8GameData")))
        manager.load_file(str(save))
        assert manager.battle.scan_moved and manager.battle.enemies_scanned[18]

    def test_scene_out_decides(self, widget, tmp_path):
        scene = tmp_path / "scene.out"
        scene.write_bytes(self._scene(165))
        widget._load_scene_file(str(scene))
        assert widget.manager.battle.scan_moved
        assert widget.battle_page.scan_moved_check.isChecked()
        assert not widget.battle_page.scan_moved_check.isHidden()
        assert not widget.battle_page.scan_moved_check.isEnabled()      # it only tells
        assert not widget.battle_page.scan_group.list_widget.item(200).isHidden()
        widget._clear_scene_file()
        assert not widget.manager.battle.scan_moved

    def test_a_vanilla_scene_overrides_the_block(self, widget, save, tmp_path):
        _write_save(save, moved_bits=True)
        widget.manager.load_file(str(save))
        scene = tmp_path / "scene.out"
        scene.write_bytes(self._scene(100))
        widget._load_scene_file(str(scene))
        assert not widget.manager.battle.scan_moved

    def test_edits_go_to_the_place_shown(self, widget):
        page = widget.battle_page
        page.scan_moved_check.setChecked(True)
        page.scan_group.list_widget.item(200).setCheckState(Qt.CheckState.Checked)
        assert widget.manager.buffer[SCANNED_MOVED + 25] == 0x01
        before = widget.manager.buffer[SCANNED_VANILLA]
        page.scan_group.list_widget.item(0).setCheckState(Qt.CheckState.Checked)
        assert widget.manager.buffer[SCANNED_VANILLA] == before
        assert widget.manager.buffer[SCANNED_MOVED] & 0x01

    def test_new_monster_rows_are_named(self, widget):
        widget.battle_page.scan_moved_check.setChecked(True)
        text = widget.battle_page.scan_group.list_widget.item(16 + 145).text()
        assert text.startswith("c0m145")

    def test_the_place_goes_through_the_cli_json(self, widget):
        battle = widget.manager.battle
        battle.scan_moved = True
        data = battle.to_dict()
        assert data["scan_moved"] is True
        battle.scan_moved = False
        battle.from_dict({"scan_moved": True, "enemies_scanned": [200]})
        assert battle.scan_moved
        assert widget.manager.buffer[SCANNED_MOVED + 25] == 0x01
