"""
Tests for Kadowaki (mitem.bin item menu editor).
Tests the file manager (read/modify/write) and the consistency of the mitem.json game data.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Kadowaki.kadowakimanager import KadowakiManager

NB_MITEM_ENTRIES = 199  # mitem.bin contains one 4-byte entry per item ID (0x00 to 0xC6)


@pytest.fixture
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    game_data = GameData(str(project_root / "FF8GameData"))
    game_data.load_item_data()
    game_data.load_mitem_data()
    game_data.load_gforce_data()
    return game_data


@pytest.fixture
def manager(game_data):
    return KadowakiManager(game_data)


@pytest.fixture
def mitem_file(tmp_path):
    """Build a small mitem.bin with known entries."""
    file_data = bytearray(NB_MITEM_ENTRIES * 4)
    # Item 1 (Potion): heal character, usable in menu + target chara, 4x50=200HP, no status cured
    file_data[4:8] = bytes([0, 0x03, 4, 0])
    # Item 7 (Phoenix Down): revive character, usable in menu + target chara + target dead, cure Death
    file_data[28:32] = bytes([1, 0x23, 0, 0x01])
    # Item 100: GF compatibility, target GF, all GFs, amount 25
    file_data[400:404] = bytes([16, 0x04, 255, 25])
    file_path = tmp_path / "mitem.bin"
    file_path.write_bytes(file_data)
    return file_path


class TestMitemJson:
    """Consistency of the mitem.json game data (the WIP association between item types and param types)"""

    def test_item_types_are_all_defined(self, game_data):
        item_types = game_data.mitem_data_json["item_type"]
        assert [item_type["id"] for item_type in item_types] == list(range(22))
        for item_type in item_types:
            assert item_type["name"], f"Item type {item_type['id']} has no name"
            assert item_type["description"], f"Item type {item_type['id']} has no description"

    def test_flags_are_all_defined(self, game_data):
        flags = game_data.mitem_data_json["flag"]
        assert [flag["bit"] for flag in flags] == list(range(8))
        for flag in flags:
            assert flag["name"], f"Flag bit {flag['bit']} has no name"
            assert flag["description"], f"Flag bit {flag['bit']} has no description"

    def test_item_types_reference_existing_param_types(self, game_data, manager):
        for item_type in game_data.mitem_data_json["item_type"]:
            for param_key in ("param1", "param2"):
                param_type_name = item_type[param_key]
                assert manager.get_param_type_info(param_type_name), \
                    f"Item type {item_type['id']} references unknown param type '{param_type_name}'"

    def test_param_types_have_valid_widget(self, game_data):
        for param_type in game_data.mitem_data_json["param_type"]:
            assert param_type["widget"] in ("none", "int", "flags", "list"), \
                f"Param type '{param_type['name']}' has unknown widget '{param_type['widget']}'"

    def test_flags_param_types_have_named_bits(self, game_data):
        for param_type in game_data.mitem_data_json["param_type"]:
            if param_type["widget"] == "flags":
                bits = [value["bit"] for value in param_type["values"]]
                assert bits == list(range(len(bits))), \
                    f"Param type '{param_type['name']}' bits are not sequential from 0"
                assert len(bits) <= 8

    def test_list_param_types_resolve_values(self, game_data, manager):
        for param_type in game_data.mitem_data_json["param_type"]:
            if param_type["widget"] == "list":
                list_values = manager.get_param_list_values(param_type)
                assert list_values, f"Param type '{param_type['name']}' resolves to an empty list"
                for value in list_values:
                    assert "id" in value and "name" in value

    def test_gf_target_contains_gf_and_all(self, manager):
        gf_target = manager.get_param_type_info("gf_target")
        list_values = manager.get_param_list_values(gf_target)
        names = [value["name"] for value in list_values]
        assert "Ifrit" in names
        assert "All GFs" in names
        assert list_values[-1]["id"] == 255

    def test_gf_ability_resolves_kernel_ability_names(self, manager):
        """gf_ability values come from the shared kernel ability enum (kernel_lookups.json)."""
        gf_ability = manager.get_param_type_info("gf_ability")
        assert gf_ability["widget"] == "list"
        names = {value["id"]: value["name"] for value in manager.get_param_list_values(gf_ability)}
        # Vanilla item-taught abilities: HP-J Scroll (1), Ribbon (77), Steel Pipe (83)
        assert names[1] == "HP-J"
        assert names[77] == "Ribbon"
        assert names[83] == "SumMag+10%"

    def test_quistis_limit_resolves_blue_magic_names(self, manager):
        """quistis_limit values come from the Blue Magic list in kernel order (limit_break.json)."""
        quistis_limit = manager.get_param_type_info("quistis_limit")
        assert quistis_limit["widget"] == "list"
        names = {value["id"]: value["name"] for value in manager.get_param_list_values(quistis_limit)}
        assert len(names) == 16
        # Vanilla teaching items: Spider Web (1), Dark Matter (15)
        assert names[1] == "Ultra Waves"
        assert names[15] == "Shockwave Pulsar"


class TestKadowakiManager:
    """Read/modify/write of the mitem.bin file"""

    def test_load_file(self, manager, mitem_file):
        manager.load_file(str(mitem_file))
        assert len(manager.menu_items) == NB_MITEM_ENTRIES

        potion = manager.menu_items[1]
        assert potion.name == "Potion"
        assert potion.type_id == 0
        assert potion.flags == 0x03
        assert potion.param1 == 4
        assert potion.param2 == 0

        phoenix_down = manager.menu_items[7]
        assert phoenix_down.name == "Phoenix Down"
        assert phoenix_down.type_id == 1
        assert phoenix_down.flags == 0x23
        assert phoenix_down.param2 == 0x01

    def test_item_names_come_from_item_json(self, manager, mitem_file):
        manager.load_file(str(mitem_file))
        assert manager.menu_items[0].name == "Nothing"
        assert manager.menu_items[9].name == "Elixir"

    def test_save_without_modification_is_identical(self, manager, mitem_file, tmp_path):
        manager.load_file(str(mitem_file))
        saved_file = tmp_path / "saved_mitem.bin"
        manager.save_file(str(saved_file))
        assert saved_file.read_bytes() == mitem_file.read_bytes()

    def test_modify_and_save(self, manager, mitem_file, tmp_path):
        manager.load_file(str(mitem_file))
        potion = manager.menu_items[1]
        potion.type_id = 20  # Stat up
        potion.flags = 0x01  # Usable in menu
        potion.param1 = 10  # Amount
        potion.param2 = 0x02  # Str
        saved_file = tmp_path / "saved_mitem.bin"
        manager.save_file(str(saved_file))

        saved_data = saved_file.read_bytes()
        assert saved_data[4:8] == bytes([20, 0x01, 10, 0x02])
        # Other entries are untouched
        assert saved_data[28:32] == bytes([1, 0x23, 0, 0x01])
        assert len(saved_data) == NB_MITEM_ENTRIES * 4

    def test_save_to_same_file_by_default(self, manager, mitem_file):
        manager.load_file(str(mitem_file))
        manager.menu_items[0].param1 = 42
        manager.save_file()
        assert mitem_file.read_bytes()[2] == 42

    def test_get_item_type_info(self, manager):
        assert manager.get_item_type_info(0)["name"] == "Heal character"
        assert manager.get_item_type_info(16)["param1"] == "gf_target"
        assert manager.get_item_type_info(200) is None

    def test_get_param_type_info(self, manager):
        assert manager.get_param_type_info("status_mask")["widget"] == "flags"
        assert manager.get_param_type_info("does_not_exist") is None
