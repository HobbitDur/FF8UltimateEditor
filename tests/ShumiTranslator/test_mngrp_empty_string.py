"""An empty string in a mngrp string section keeps its own offset on save.

The engine reads a string by its slot offset (Menu_Magazine_Draw: word_1D773A6[text_id]), so an
empty string saved as 0 bytes shares its offset with the next string, which the game then draws
in its place. Pet Pals had exactly that: each volume's empty text slot under "Angelo Strike!"
showed the title of the next volume once the file went through ShumiTranslator.
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.string.sectionstring import SectionString

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _build_section(game_data, text_list) -> bytearray:
    """Section = {u16 count, u16 offsets[count], texts}, an empty text being a lone \\x00."""
    offset = 2 + 2 * len(text_list)
    offset_list = []
    text_data = bytearray()
    for text in text_list:
        offset_list.append(offset)
        encoded = bytearray(game_data.translate_str_to_hex(text)) + b"\x00"
        text_data.extend(encoded)
        offset += len(encoded)
    return bytearray(struct.pack(f"<H{len(text_list)}H", len(text_list), *offset_list)) + text_data


def _text_at(data: bytes, offset: int) -> bytes:
    return bytes(data[offset:data.index(0, offset)])


def test_empty_string_keeps_its_own_offset(game_data):
    text_list = ["Pet Pals Vol.1", "", "Pet Pals Vol.2"]
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, text_list))

    saved = section.update_data_hex()

    offset_list = struct.unpack_from("<3H", saved, 2)
    assert len(set(offset_list)) == 3, f"slots share an offset: {offset_list}"
    assert _text_at(saved, offset_list[1]) == b""
    assert _text_at(saved, offset_list[2]) == bytes(game_data.translate_str_to_hex("Pet Pals Vol.2"))


def test_string_emptied_by_the_user_keeps_its_own_offset(game_data):
    text_list = ["Title", "Angelo Strike!", "Next title"]
    section = SectionString(game_data=game_data, data_hex=_build_section(game_data, text_list))

    section.get_text_list()[1].set_str("")
    saved = section.update_data_hex()

    # Read the way the engine does (offset, then up to \x00): the tool's own reader would see ""
    # even for a 0-byte text, so it cannot tell the broken file apart.
    offset_list = struct.unpack_from("<3H", saved, 2)
    assert [_text_at(saved, offset) for offset in offset_list] == [
        bytes(game_data.translate_str_to_hex("Title")), b"",
        bytes(game_data.translate_str_to_hex("Next title"))]
