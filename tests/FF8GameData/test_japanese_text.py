"""Japanese text: GameData's 4-table Japanese font, FF8Text round trips and the deling-cli conversion
(FF8GameData.fs.delingjp) used for Japanese field and world CSVs."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def game_data():
    from FF8GameData.gamedata import GameData
    data = GameData(str(ROOT / "FF8GameData"))
    data.load_sysfnt_data()
    data.jp_encoding = True
    return data


def test_numbered_tags_keep_their_whole_number(game_data):
    # {Jp011} used to come back as 0x1c 0x21 (its last digit only), {Wait048} as 0x09 0x28
    raw = bytes([0x1c, 0x2b, 0x09, 0x50, 0x1c, 0x20, 0x09, 0x20])
    text = game_data.translate_hex_to_str(list(raw))
    assert text == "{Jp011}{Wait048}{Jp000}{Wait000}"
    assert bytes(game_data.translate_str_to_hex(text)) == raw
    game_data.jp_encoding = False  # waits are not Japanese only
    assert bytes(game_data.translate_str_to_hex("{Wait048}")) == bytes([0x09, 0x50])


def test_deling_new_page_form(game_data):
    # Deling writes 0x01 as "\n{NewPage}\n": both line breaks belong to it
    assert game_data.translate_str_to_hex("A\n{NewPage}\nB") == game_data.translate_str_to_hex("A{NewPage}B")
    a, b = game_data.translate_str_to_hex("A")[0], game_data.translate_str_to_hex("B")[0]
    assert game_data.translate_str_to_hex("A\n{NewPage}\n\nB") == [a, 0x01, 0x02, b]


def test_glyph_drawn_in_two_tables_keeps_its_code(game_data):
    from FF8GameData.GenericSection.ff8text import FF8Text
    # 記 is both 0x1ac8 (field texts) and 0x1ba1 (SeeD test menu): an unchanged text saves back identical
    for raw in (b"\x1b\xa1\x1b\xa2\x00", b"\x1a\xc8\x00"):
        text = FF8Text(game_data, 0, bytearray(raw), 0)
        assert text.get_str().startswith("記")
        assert bytes(text.get_data_hex()) == raw
    edited = FF8Text(game_data, 0, bytearray(b"\x1b\xa1\x00"), 0)
    edited.set_str("記憶")
    assert bytes(edited.get_data_hex()) == b"\x1b\xa1\x1b\xa2\x00"


def test_deling_latin_conversion_round_trip(game_data):
    from FF8GameData.fs.delingjp import japanese_to_latin, latin_to_japanese
    japanese = "{Squall}\n「記憶……{Wait016}\n{NewPage}\n\n　{Jp011}テスト！」"
    latin = japanese_to_latin(game_data, japanese)
    assert "{Squall}" not in latin and "{x0330}" in latin  # control codes in Deling's raw tag form
    assert "\n{NewPage}\n{x02}" in latin                 # Deling's import drops "\n{NewPage}\n\n"
    assert latin_to_japanese(game_data, latin) == japanese
    assert game_data.jp_encoding  # the conversion restores the caller's mode


def test_deling_csv_conversion(tmp_path, game_data):
    from FF8GameData.fs.delingjp import convert_csv
    source = tmp_path / "latin.csv"
    japanese = "セルフィ\n「あ～！」"
    from FF8GameData.fs.delingjp import japanese_to_latin
    rows = [["jp", "Comment"], ["#bgroom_1", "2"], [japanese_to_latin(game_data, japanese), "note"], ["", ""]]
    import csv
    with open(source, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    convert_csv(game_data, str(source), str(tmp_path / "jp.csv"), from_deling_csv=True)
    with open(tmp_path / "jp.csv", encoding="utf-8", newline="") as f:
        out = list(csv.reader(f))
    assert out == [["jp", "Comment"], ["#bgroom_1", "2"], [japanese, "note"], ["", ""]]
    convert_csv(game_data, str(tmp_path / "jp.csv"), str(tmp_path / "back.csv"), from_deling_csv=False)
    assert (tmp_path / "back.csv").read_bytes() == source.read_bytes()
