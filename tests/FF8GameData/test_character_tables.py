"""The character tables texts are read and written with (GameData.CHARACTER_TABLES: Latin, Japanese,
Vietnamese), their files in Resources, and the Deling CSV conversion with a table other than Latin."""
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "FF8GameData" / "Resources"


@pytest.fixture()
def game_data():
    data = GameData(str(ROOT / "FF8GameData"))
    data.load_sysfnt_data()
    return data


@pytest.mark.parametrize("name", ["sysfnt.txt", "sysfnt_jp.txt", "sysfnt_viet.txt"])
def test_table_files_save_back_identical(tmp_path, name):
    copy = tmp_path / name
    shutil.copy(RESOURCES / name, copy)
    GameData.write_character_table_file(str(copy), GameData.read_character_table_file(str(copy)))
    assert copy.read_bytes() == (RESOURCES / name).read_bytes()


def test_vietnamese_table_is_the_latin_one_with_the_patch_letters(game_data):
    latin = game_data.latin_table
    game_data.set_character_table("vietnamese")
    viet = game_data.translate_hex_to_str_table
    assert len(viet) == len(latin) and not game_data.jp_encoding
    assert latin[:0x20] == viet[:0x20] and latin[0xe8:] == viet[0xe8:]  # control codes, {} pairs untouched
    assert game_data.translate_hex_to_str(game_data.translate_str_to_hex("Tấn công")) == "Tấn công"
    with game_data.using_latin_table():  # the bytes the Vietnamese patch writes for it
        patch_bytes = game_data.translate_str_to_hex("Tàn cœng")
    assert game_data.translate_str_to_hex("Tấn công") == patch_bytes  # same codes, read as Vietnamese


def test_vietnamese_table_has_the_capitals_ff8_ilp_draws(game_data):
    """FF8 ILP 2.0 draws the opening quote and 27 capitals with marks in cells the patch left unused,
    among them its second ớ (0xca) and ộ (0xcb): those two letters are written at 0x37 and 0x9b only."""
    from FF8GameData.GenericSection.ff8text import FF8Text
    game_data.set_character_table("vietnamese")
    table = game_data.translate_hex_to_str_table
    assert (table[0xba], table[0xca], table[0xcb], table[0xe7]) == ("“", "À", "Ê", "Ạ")
    assert "".join(table[0xcf:0xe2]) == "ẢỪỦƠÝỜỞỔĨẮẦẾẬỢỬÓƯÍÚ"
    assert game_data.translate_str_to_hex("ớộ") == [0x37, 0x9b]
    text = FF8Text(game_data, 0, bytearray(game_data.translate_str_to_hex("“ỞÊ”") + [0x00]), 0)
    assert text.get_str() == "“ỞÊ”" and bytes(text.get_data_hex()) == bytes([0xba, 0xd5, 0xcb, 0x3e, 0x00])


def test_switching_tables_and_editing_one(tmp_path, game_data):
    for name in ("sysfnt.txt", "sysfnt_jp.txt", "sysfnt_viet.txt"):
        shutil.copy(RESOURCES / name, tmp_path / name)
    game_data.resource_folder = str(tmp_path)
    game_data.set_character_table("japanese")
    assert game_data.jp_encoding and game_data.table_char(2, 0xc8 - 0x20) == "記"
    game_data.set_character_table("latin")
    assert not game_data.jp_encoding and game_data.table_char(0, 1) == "0"
    with pytest.raises(ValueError):
        game_data.set_table_char(1, 0, "x")  # a Latin-style table has one table only
    game_data.set_table_char(0, 1, "Ø")
    assert game_data.character_table_modified and game_data.translate_hex_to_str([0x21]) == "Ø"
    exported = game_data.export_character_table(str(tmp_path / "mine.txt"))
    assert GameData.read_character_table_file(exported)[0x21] == "Ø"
    assert GameData.read_character_table_file(str(tmp_path / "sysfnt.txt"))[0x21] == "0"  # its file: unchanged
    game_data.set_custom_character_table(exported)
    assert game_data.character_table == "custom" and game_data.translate_hex_to_str([0x21]) == "Ø"


def test_deling_conversion_with_the_vietnamese_table(game_data):
    from FF8GameData.fs.delingjp import from_deling, needs_conversion, to_deling
    assert not needs_conversion(game_data)
    game_data.set_character_table("vietnamese")
    assert needs_conversion(game_data)
    deling = "Tàn cœng"
    assert from_deling(game_data, deling) == "Tấn công"
    assert to_deling(game_data, "Tấn công") == deling
