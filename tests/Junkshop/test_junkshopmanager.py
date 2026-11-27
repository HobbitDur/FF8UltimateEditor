"""
Tests for Junkshop (mwepon.bin weapon-upgrade editor).

mwepon.bin is a flat array of 12-byte entries indexed by weapon-upgrade id:
    - uint16 name_offset (into mwepon.msg, preserved as-is)
    - byte   padding (unused, preserved as-is)
    - byte   price / 10
    - 4 x (byte item_id, byte quantity)   -> the ingredients consumed on upgrade

A small synthetic mwepon.bin is built with known entries so the tests don't need
the original game files.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Junkshop.junkshopmanager import JunkshopManager, WeaponUpgrade

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_item_data()
    return gd


@pytest.fixture
def manager(game_data):
    return JunkshopManager(game_data)


def _weapon_bytes(name_offset, padding, price_div10, items):
    data = bytearray(12)
    data[0] = name_offset & 0xFF
    data[1] = (name_offset >> 8) & 0xFF
    data[2] = padding & 0xFF
    data[3] = price_div10 & 0xFF
    for i, (item_id, quantity) in enumerate(items):
        data[4 + i * 2] = item_id
        data[5 + i * 2] = quantity
    return bytes(data)


@pytest.fixture
def mwepon_file(tmp_path):
    """mwepon.bin with 2 known weapon upgrades."""
    entries = [
        # weapon 0: name_offset 0x10, padding 0, price 800 (stored 80),
        #   4 ingredients
        (0x10, 0, 80, [(1, 2), (7, 1), (0, 0), (0, 0)]),
        # weapon 1: non-zero padding, price 1500 (stored 150)
        (0x2A, 0x00, 150, [(9, 3), (0, 0), (0, 0), (0, 0)]),
    ]
    data = bytearray()
    for name_offset, padding, price_div10, items in entries:
        data += _weapon_bytes(name_offset, padding, price_div10, items)
    file_path = tmp_path / "mwepon.bin"
    file_path.write_bytes(data)
    return file_path, entries


class TestWeaponUpgrade:
    def test_price_is_stored_value_times_ten(self):
        upgrade = WeaponUpgrade(0, "Revolver", price_div10=80)
        assert upgrade.price == 800

    def test_price_setter_divides_by_ten(self):
        upgrade = WeaponUpgrade(0, "Revolver")
        upgrade.price = 2500
        assert upgrade.price_div10 == 250
        assert upgrade.price == 2500

    def test_default_items_are_four_empty_pairs(self):
        upgrade = WeaponUpgrade(0, "Revolver")
        assert upgrade.items == [[0, 0], [0, 0], [0, 0], [0, 0]]

    def test_to_bytes_layout(self):
        upgrade = WeaponUpgrade(0, "X", name_offset=0x1234, padding=0x56,
                                price_div10=0x78, items=[[1, 2], [3, 4], [5, 6], [7, 8]])
        assert upgrade.to_bytes() == bytes([0x34, 0x12, 0x56, 0x78, 1, 2, 3, 4, 5, 6, 7, 8])


class TestJunkshopManager:
    def test_weapon_names_come_only_from_a_kernel_bin(self, manager):
        # No built-in names: without a kernel.bin every weapon is just its id.
        assert manager.weapon_name_list == []
        assert manager.get_weapon_name(0) == "Weapon 0"
        manager.set_weapon_names(["Revolver", "Shear Trigger"])
        assert manager.get_weapon_name(0) == "Revolver"
        assert manager.get_weapon_name(9999) == "Weapon 9999"
        manager.set_weapon_names([])
        assert manager.get_weapon_name(1) == "Weapon 1"

    def test_load_file(self, manager, mwepon_file):
        file_path, entries = mwepon_file
        manager.load_file(str(file_path))
        assert len(manager.weapon_upgrades) == len(entries)

        first = manager.weapon_upgrades[0]
        assert first.name_offset == 0x10
        assert first.price == 800
        assert first.items[0] == [1, 2]
        assert first.items[1] == [7, 1]

    def test_item_names_come_from_item_json(self, manager, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        assert manager.get_item_name(1) == "Potion"
        assert manager.get_item_name(0) == "Nothing"
        assert manager.get_item_name(9999) == "Item 9999"

    def test_save_without_modification_is_identical(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        assert saved.read_bytes() == file_path.read_bytes()

    def test_name_offset_and_padding_preserved(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[1].price = 9990  # only touch price
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        data = saved.read_bytes()
        # name_offset (bytes 0-1) and padding (byte 2) of weapon 1 are untouched
        assert data[12:14] == bytes([0x2A, 0x00])
        assert data[15] == 999 & 0xFF

    def test_modify_ingredients_and_save(self, manager, mwepon_file, tmp_path):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[0].items[2] = [5, 9]
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        data = saved.read_bytes()
        assert data[8:10] == bytes([5, 9])
        # weapon 1 untouched
        assert data[12:24] == _weapon_bytes(0x2A, 0, 150, [(9, 3), (0, 0), (0, 0), (0, 0)])

    def test_save_defaults_to_loaded_path(self, manager, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        manager.weapon_upgrades[0].items[0] = [42, 1]
        manager.save_file()
        assert file_path.read_bytes()[4] == 42

    def test_reload_roundtrip(self, manager, game_data, mwepon_file):
        file_path, _ = mwepon_file
        manager.load_file(str(file_path))
        # price is stored in a single byte as price/10, so the max representable value is 2550
        manager.weapon_upgrades[0].price = 2500
        manager.weapon_upgrades[0].items[3] = [11, 22]
        manager.save_file()

        reloaded = JunkshopManager(game_data)
        reloaded.load_file(str(file_path))
        assert reloaded.weapon_upgrades[0].price == 2500
        assert reloaded.weapon_upgrades[0].items[3] == [11, 22]


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_a_recipe_item_past_the_game_ones_survives_an_edit(qapp, tmp_path):
    """FFNx's AddMoreItems adds items 199-255. A recipe using one was shown as the first entry of
    the list and written back as item 0 on the next edit; it is kept now, and a kernel.bin that
    defines it names it and offers it."""
    from Junkshop.junkshopwidget import JunkshopWidget
    path = tmp_path / "mwepon.bin"
    path.write_bytes(_weapon_bytes(0x10, 0, 80, [(230, 2), (1, 1), (0, 0), (0, 0)]))
    widget = JunkshopWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.load_file(str(path))
    combo = widget.item_comboboxes[0]
    assert combo.currentData() == 230 and combo.currentText() == "230: (unknown)"
    widget.quantity_spinboxes[0].setValue(3)
    widget.save_file()
    assert path.read_bytes()[4:6] == bytes([230, 3])

    widget.kernel_names.items = {230: "Mega Tonic"}
    widget.kernel_names.changed.emit()
    combo = widget.item_comboboxes[0]
    assert combo.currentText() == "230: Mega Tonic"
    combo.setCurrentIndex(combo.findData(1))
    widget.save_file()
    assert path.read_bytes()[4] == 1


class TestCronosPrices:
    """Cronos's JunkShopPrice16.hext: byte 2 is the high byte of price / 10 (up to 655,350 gil)."""

    def test_byte_2_is_the_high_byte_with_cronos_only(self, manager, tmp_path):
        path = tmp_path / "mwepon.bin"
        path.write_bytes(_weapon_bytes(0x10, 0x30, 0x39, []))
        manager.load_file(str(path))
        assert manager.weapon_upgrades[0].price == 570  # vanilla: byte 3 only
        manager.set_cronos(True)
        assert manager.weapon_upgrades[0].price == 123450
        assert manager.max_price == 655350

    def test_a_vanilla_file_reads_the_same_either_way(self, manager, mwepon_file):
        file_path, entries = mwepon_file
        manager.load_file(str(file_path))
        vanilla = [upgrade.price for upgrade in manager.weapon_upgrades]
        manager.set_cronos(True)
        assert [upgrade.price for upgrade in manager.weapon_upgrades] == vanilla

    @pytest.mark.parametrize("price,byte2,byte3", [(655350, 0xFF, 0xFF), (2570, 1, 1), (123450, 0x30, 0x39),
                                                   (2550, 0, 0xFF), (700000, 0xFF, 0xFF)])
    def test_cronos_writes_price_over_bytes_3_and_2(self, manager, mwepon_file, tmp_path, price, byte2, byte3):
        file_path, _ = mwepon_file
        manager.set_cronos(True)
        manager.load_file(str(file_path))
        manager.weapon_upgrades[1].price = price
        saved = tmp_path / "saved_mwepon.bin"
        manager.save_file(str(saved))
        data = saved.read_bytes()
        assert (data[12 + 2], data[12 + 3]) == (byte2, byte3)
        assert data[12:14] == bytes([0x2A, 0x00]) and data[16:] == file_path.read_bytes()[16:]

    def test_vanilla_mode_leaves_byte_2_alone(self, manager, tmp_path):
        path = tmp_path / "mwepon.bin"
        path.write_bytes(_weapon_bytes(0x10, 0x30, 0x39, []))
        manager.load_file(str(path))
        manager.weapon_upgrades[0].price = 1000
        manager.save_file()
        assert path.read_bytes()[2:4] == bytes([0x30, 100])
        assert manager.weapon_upgrades[0].cronos_price == (0x30 * 256 + 100) * 10


def test_the_cronos_checkbox_switches_to_16_bit_prices(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from Junkshop.junkshopwidget import JunkshopWidget
    QSettings("HobbitDur", "FF8UltimateEditor").remove("junkshop/cronos_checkbox")
    path = tmp_path / "mwepon.bin"
    path.write_bytes(_weapon_bytes(0x10, 0x30, 0x39, [(1, 1)]) + _weapon_bytes(0x20, 0, 80, [(2, 1)]))
    widget = JunkshopWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    assert not widget.cronos_checkbox.isChecked()
    widget.load_file(str(path))
    assert widget.price_spinbox.maximum() == 2550 and widget.price_spinbox.value() == 570
    assert not widget.cronos_price_label.isHidden()
    assert "123,450" in widget.cronos_price_label.text()

    widget.cronos_checkbox.setChecked(True)
    assert widget.price_spinbox.maximum() == 655350 and widget.price_spinbox.value() == 123450
    assert widget.cronos_price_label.isHidden()
    widget.price_spinbox.setValue(500000)
    widget.save_file()
    assert path.read_bytes()[2:4] == bytes([50000 >> 8, 50000 & 0xFF])

    # Unticking narrows the range without writing a clamped price into the record
    widget.cronos_checkbox.setChecked(False)
    widget.save_file()
    assert path.read_bytes()[2:4] == bytes([50000 >> 8, 50000 & 0xFF])
    assert QSettings("HobbitDur", "FF8UltimateEditor").value("junkshop/cronos_checkbox", type=bool) is False

    widget.cronos_checkbox.setChecked(True)
    assert JunkshopWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData")).cronos_checkbox.isChecked()
    QSettings("HobbitDur", "FF8UltimateEditor").remove("junkshop/cronos_checkbox")


def test_the_cli_reads_and_writes_16_bit_prices_with_cronos(tmp_path):
    from Cli.junkshop import JunkshopCliTool
    path = tmp_path / "mwepon.bin"
    path.write_bytes(_weapon_bytes(0x10, 0x30, 0x39, [(1, 1)]))
    tool = JunkshopCliTool()
    csv_path = tmp_path / "mwepon.csv"
    assert tool.execute(tool.build_parser().parse_args(
        ["export-csv", "-i", str(path), "-o", str(csv_path), "--cronos"])) == 0
    assert "|123450|" in csv_path.read_text(encoding="utf-8-sig")
    csv_path.write_text(csv_path.read_text(encoding="utf-8-sig").replace("|123450|", "|655350|"), encoding="utf-8")
    assert tool.execute(tool.build_parser().parse_args(
        ["import-csv", "-i", str(path), "-c", str(csv_path), "--cronos"])) == 0
    assert path.read_bytes()[2:4] == b"\xFF\xFF"
