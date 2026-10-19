"""Xu info bar: the Scan screen's one-line pages, built like manageScanText_Dup (0xB68390)."""
import sys

import pytest

from Xu.xuinfobar import (InfoBarBuilder, InfoBarSubject, affinity_group, ai_scan_texts, icon_sprite_id,
                          icon_table_from_exe, scan_text_bytes, MISC_NUMBERS_SYMBOLS, MISC_LEVEL, MISC_HP,
                          MISC_MONSTER, MISC_VERY_WEAK_AGAINST, MISC_FLY, MISC_ELEM_FIRE, MISC_5_QUESTION_MARKS,
                          MISC_UNDEAD)

KERNEL = "extracted_files/main/kernel.bin"
EXE = "extracted_files/FF8_EN.exe"
ICON_SP1 = "extracted_files/menu/icon.sp1"


@pytest.fixture(scope="module")
def game_data():
    from FF8GameData.gamedata import GameData
    data = GameData("FF8GameData")
    data.load_exe_data()
    return data


def synthetic_misc(game_data):
    """Misc texts made up for the test (no game text in the repo): marked so a test sees where
    each part came from. The element names are icon codes, as in the game."""
    misc = [b""] * 128

    def encode(text):
        return bytes(game_data.translate_str_to_hex(text))

    misc[MISC_NUMBERS_SYMBOLS] = encode(" 0123456789ABCDEF:/,")  # 0 = space, 1-10 digits, 18 = "/"
    misc[MISC_LEVEL] = encode("LV")
    misc[MISC_HP] = encode("PV")
    misc[MISC_MONSTER] = encode("Mon")
    misc[MISC_FLY] = encode("Fl")
    misc[MISC_UNDEAD] = encode("Und")
    misc[MISC_5_QUESTION_MARKS] = encode("?????")
    for group in range(5):
        misc[MISC_VERY_WEAK_AGAINST + group] = encode(f"G{group}")
    for element in range(8):
        misc[MISC_ELEM_FIRE + element] = bytes((0x05, 0x5D + element))
    return misc


@pytest.fixture(scope="module")
def builder(game_data):
    return InfoBarBuilder(synthetic_misc(game_data))


def text(game_data, data):
    return game_data.translate_hex_to_str(data)


def test_affinity_groups():
    """ScanText_CollectElementsByAffinity: <=600, 601-799, 801-899, ==900, >900; 800 is normal."""
    assert [affinity_group(v) for v in (0, 600, 601, 799, 800, 801, 899, 900, 901, 2550)] == \
        [0, 0, 1, 1, None, 2, 2, 3, 4, 4]


def test_level_hp_line(game_data, builder):
    subject = InfoBarSubject(level=7, current_hp=345, max_hp=1200)
    assert text(game_data, builder.lines(subject)[0].data) == "LV 7 PV 345/1200"
    hidden = InfoBarSubject(level=100, current_hp=345, max_hp=1200, hp_hidden=True)
    assert text(game_data, builder.lines(hidden)[0].data) == "LV 100 PV ?????/?????"
    huge = InfoBarSubject(level=1, current_hp=123456, max_hp=99999)  # over 5 digits: ?????
    assert text(game_data, builder.lines(huge)[0].data) == "LV 1 PV ?????/99999"


def test_undead_fly_and_element_lines(game_data, builder):
    subject = InfoBarSubject(level=1, current_hp=1, max_hp=1, zombie=True, fly=True,
                             elem_def=[1000, 600, 800, 800, 800, 750, 900, 850])
    lines = builder.lines(subject)
    assert [line.label for line in lines] == ["Level and HP", "Undead Fly monster", "Very weak against (1)",
                                              "Weak against (1)", "Strong against (1)", "Has no effect (1)",
                                              "Absorbs (1)"]
    # every one of the 4 / 9 parts is joined with a space, the empty ones too
    assert lines[1].data == bytes(game_data.translate_str_to_hex("Und Fl Mon "))
    assert lines[2].data.rstrip(b" " if False else bytes((builder.symbol(0),))) == \
        bytes(game_data.translate_str_to_hex("G0 ")) + bytes((0x05, 0x5E))  # ice
    assert lines[6].data.startswith(bytes(game_data.translate_str_to_hex("G4 ")) + bytes((0x05, 0x5D)))


def test_hidden_hp_hides_the_elements(builder):
    subject = InfoBarSubject(hp_hidden=True, elem_def=[600] * 8, fly=True)
    assert [line.label for line in builder.lines(subject)] == ["Level and HP", "Fly monster"]


def test_character_has_only_level_and_hp(builder):
    subject = InfoBarSubject(level=12, current_hp=900, max_hp=900, monster=False, zombie=True)
    assert [line.label for line in builder.lines(subject, scan_text=b"\x30\x31")] == ["Level and HP"]


def test_scan_text_line_is_24_bytes_at_most(builder):
    long_text = bytes(range(0x30, 0x30 + 40))
    lines = builder.lines(InfoBarSubject(), scan_text=long_text)
    assert lines[-1].label.startswith("AI scan text") and lines[-1].data == long_text[:23]
    assert scan_text_bytes(b"\x30\x31\x00\x32") == b"\x30\x31"


def test_subject_from_dat_stats():
    """A monster slot: level capped at 100, HP from the curve, elem_def = 10 x the .dat byte
    (Ifrit's damage % being 900 - 10 x byte)."""
    from FF8GameData.dat.monsterstatcurve import monster_hp
    stats = {'hp': [12, 20, 0, 4], 'elem_def': [100, -100, 200, 0, 50, 100, 100, 800],
             'byte_flag_1': {'Zombie': 1, 'Fly': 0, 'Hidden HP': 1}}
    subject = InfoBarSubject.from_info_stat(stats, 150)
    assert subject.level == 100
    assert subject.max_hp == subject.current_hp == monster_hp([12, 20, 0, 4], 100)
    assert subject.elem_def == [800, 1000, 700, 900, 850, 800, 800, 100]
    assert subject.zombie and not subject.fly and subject.hp_hidden


class _Command:
    def __init__(self, op_id, params):
        self._id, self._params = op_id, params

    def get_id(self):
        return self._id

    def get_op_code(self):
        return self._params


class _Text:
    def __init__(self, data):
        self._data = data

    def get_data_hex(self):
        return bytearray(self._data)


def test_ai_scan_texts():
    """Every text an AI can set with setScanText (0x25), once each, 0xFF (clear) left out."""
    script = {'battle_text': [_Text(b"\x30"), _Text(b"\x31"), _Text(b"\x32")],
              'ai_data': [{'command': [_Command(0x25, [1]), _Command(0x02, [1])]},
                          {'command': [_Command(0x25, [0xFF]), _Command(0x25, [1]), _Command(0x25, [2]),
                                       _Command(0x25, [9])]}]}
    assert ai_scan_texts(script) == [(1, b"\x31", 0), (2, b"\x32", 1)]


def test_icon_table_from_exe(game_data):
    """TEXT_ICON_CODE_TO_SPRITE read from the exe; codes 0x30-0x3F are icon id code + 80."""
    offsets = game_data.exe_data_json["text_icon_sprite_offset"]
    lang = game_data.exe_data_json["lang"]
    exe = bytearray(offsets["eng_section_start"] + 2 * offsets["nb_code"])
    exe[lang["offset"]] = lang["english_value"]
    start = offsets["eng_section_start"] + 2 * (0x5D - offsets["first_code"])
    exe[start:start + 2] = (288).to_bytes(2, "little")
    table = icon_table_from_exe(bytes(exe), game_data.exe_data_json)
    assert len(table) == offsets["nb_code"] and table[0x5D] == 288
    assert icon_sprite_id(0x5D, table) == 288
    assert icon_sprite_id(0x31, {}) == 0x31 + 80
    assert icon_sprite_id(0x5D, {}) is None and icon_sprite_id(0x21, table) is None  # pad buttons
    with pytest.raises(ValueError):
        icon_table_from_exe(bytes(exe[:100]), game_data.exe_data_json)


def test_hud_icon_advance(game_data):
    """An icon moves the pen by its sprite width + 1; without icon.sp1 a box of 12."""
    from Xu.xuhud import ScanHud, ICON_FALLBACK_ADVANCE

    class _Icons:
        def has(self, icon_id):
            return icon_id == 288

        def advance(self, _icon_id):
            return 15

        def image(self, _icon_id):
            return None

    hud = ScanHud(game_data)
    data = bytes((0x45, 0x05, 0x5D, 0x46))
    items = hud.battle_text_items(data)
    assert [(kind, x) for kind, _value, x, _w, _c in items] == [("glyph", 0), ("icon", 8),
                                                                ("glyph", 8 + ICON_FALLBACK_ADVANCE)]
    hud.icons, hud.icon_table = _Icons(), {0x5D: 288}
    items = hud.battle_text_items(data)
    assert items[1][1] == 288 and items[2][2] == 8 + 15
    assert hud.battle_text_width(data) == 8 + 15 + 8
    image = hud.render("", "", data)  # draws without the game font
    assert image.size == (320, 240) and image.getbbox()[1] >= 180


@pytest.mark.ff8data(KERNEL, EXE, ICON_SP1)
def test_real_files(game_data):
    """The vanilla files: kernel misc texts by FF8KernelMiscText index, element icons 288-295."""
    from Xu.xuhud import IconSheet
    from Xu.xuinfobar import misc_texts_from_kernel
    misc = misc_texts_from_kernel(game_data, KERNEL)
    assert text(game_data, misc[MISC_LEVEL]) == "LEVEL" and text(game_data, misc[MISC_UNDEAD]) == "Undead"
    with open(EXE, "rb") as file:
        table = icon_table_from_exe(file.read(), game_data.exe_data_json)
    assert [table[misc[MISC_ELEM_FIRE + i][1]] for i in range(8)] == list(range(288, 296))
    icons = IconSheet(ICON_SP1)
    assert all(icons.has(icon_id) and icons.advance(icon_id) > 1 for icon_id in range(288, 296))
    lines = InfoBarBuilder(misc).lines(InfoBarSubject(level=20, current_hp=600, max_hp=600, fly=True,
                                                      elem_def=[1000, 600, 800, 800, 800, 750, 800, 800]))
    assert text(game_data, lines[0].data) == "LEVEL 20 HP 600/600"
    assert text(game_data, lines[1].data).rstrip() == "Fly Monster"
