"""Unit tests for the Moomba manager (mmag2.bin, Chocobo World screen pages).

Runs on a synthetic file so it does not need the real game data: builds
12 patterned 68-byte entries, then checks parsing, round-trip and editing.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.menu.menutext import decode_string_section
from Moomba.moombamanager import MoombaManager, MagPageEntry, OverlaySlot

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


def _build_synthetic_file(nb_entries=MoombaManager.NB_ENTRIES) -> bytes:
    """Every byte of every entry gets a distinct, entry-dependent value."""
    data = bytearray()
    for entry_index in range(nb_entries):
        data.extend(bytes((entry_index * 37 + offset * 11) % 256 for offset in range(MagPageEntry.SIZE)))
    return bytes(data)


@pytest.fixture
def synthetic_file(tmp_path):
    file_path = tmp_path / "mmag2.bin"
    file_path.write_bytes(_build_synthetic_file())
    return file_path


def test_synthetic_roundtrip_is_byte_exact(game_data, synthetic_file, tmp_path):
    manager = MoombaManager(game_data)
    manager.load_file(str(synthetic_file))
    assert len(manager.entries) == MoombaManager.NB_ENTRIES

    out = tmp_path / "out.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == synthetic_file.read_bytes()


def test_fields_are_parsed_at_the_documented_offsets(game_data, tmp_path):
    entry_bytes = bytearray(MagPageEntry.SIZE)
    entry_bytes[0x00:0x02] = (24).to_bytes(2, "little")  # window X
    entry_bytes[0x06:0x08] = (158).to_bytes(2, "little")  # window height
    entry_bytes[0x10] = 115  # picture X scale
    entry_bytes[0x14] = 0xC0  # paper background parameter B
    entry_bytes[0x16] = 6  # texture category
    entry_bytes[0x17] = 1  # texture page
    entry_bytes[0x23] = 1  # footer flag
    entry_bytes[0x24:0x28] = (10).to_bytes(2, "little") + bytes([12, 58])  # picture overlay 0
    entry_bytes[0x34:0x38] = (147).to_bytes(2, "little") + bytes([6, 0])  # text overlay 0
    entry_bytes[0x38:0x3C] = bytes([0, 0, 0, OverlaySlot.UNUSED_ID])  # text overlay 1 unused
    file_path = tmp_path / "one_entry.bin"
    file_path.write_bytes(entry_bytes)

    manager = MoombaManager(game_data)
    manager.load_file(str(file_path))
    entry = manager.entries[0]
    assert entry.window_x == 24
    assert entry.window_height == 158
    assert entry.picture_tint_r == 115
    assert entry.paper_e2 == 0xC0
    assert entry.texture_category == 6
    assert entry.texture_page == 1
    assert entry.footer_flag == 1
    assert (entry.picture_overlays[0].x, entry.picture_overlays[0].y,
            entry.picture_overlays[0].id) == (10, 12, 58)
    assert not entry.picture_overlays[0].unused
    assert (entry.text_overlays[0].x, entry.text_overlays[0].y, entry.text_overlays[0].id) == (147, 6, 0)
    assert entry.text_overlays[1].unused


def test_edit_persists_and_leaves_other_entries_untouched(game_data, synthetic_file, tmp_path):
    manager = MoombaManager(game_data)
    manager.load_file(str(synthetic_file))
    original = synthetic_file.read_bytes()

    entry = manager.entries[3]
    entry.texture_page = 1
    entry.text_overlays[0].id = 5
    entry.text_overlays[0].x = 13
    out = tmp_path / "edited.bin"
    manager.save_file(str(out))

    reloaded = MoombaManager(game_data)
    reloaded.load_file(str(out))
    assert reloaded.entries[3].texture_page == 1
    assert reloaded.entries[3].text_overlays[0].id == 5
    assert reloaded.entries[3].text_overlays[0].x == 13
    # Every other entry stays byte-exact
    rebuilt = out.read_bytes()
    for index in range(MoombaManager.NB_ENTRIES):
        if index == 3:
            continue
        assert rebuilt[index * MagPageEntry.SIZE:(index + 1) * MagPageEntry.SIZE] == \
               original[index * MagPageEntry.SIZE:(index + 1) * MagPageEntry.SIZE]


def test_bad_file_size_is_rejected(game_data, tmp_path):
    file_path = tmp_path / "bad.bin"
    file_path.write_bytes(bytes(MagPageEntry.SIZE + 1))
    manager = MoombaManager(game_data)
    with pytest.raises(ValueError):
        manager.load_file(str(file_path))


def test_string_section_decoding_is_positional(game_data):
    """Zero offsets are kept in place (empty string) so a text id keeps indexing its slot."""
    manager = MoombaManager(game_data)
    # 3 offset slots: "AB", empty slot, "C". Encode via the reverse table to stay
    # independent of the sysfnt layout.
    hex_ab = game_data.translate_str_to_hex("AB")
    hex_c = game_data.translate_str_to_hex("C")
    header_size = 2 + 3 * 2
    offsets = [header_size, 0, header_size + len(hex_ab) + 1]
    section = bytearray()
    section.extend((3).to_bytes(2, "little"))
    for offset in offsets:
        section.extend(offset.to_bytes(2, "little"))
    section.extend(hex_ab)
    section.append(0)
    section.extend(hex_c)
    section.append(0)

    texts = decode_string_section(game_data, bytes(section))
    assert texts == ["AB", "", "C"]
    manager.mngrp_text_list = texts
    assert manager.get_overlay_text(0) == "AB"
    assert manager.get_overlay_text(2) == "C"
    assert manager.get_overlay_text(OverlaySlot.UNUSED_ID) == ""


def test_entry_names_only_apply_to_a_12_entry_file(game_data, tmp_path):
    file_path = tmp_path / "short.bin"
    file_path.write_bytes(bytes(MagPageEntry.SIZE * 2))
    manager = MoombaManager(game_data)
    manager.load_file(str(file_path))
    assert manager.get_entry_name(0) == "Page 0"

    file_path12 = tmp_path / "full.bin"
    file_path12.write_bytes(_build_synthetic_file())
    manager.load_file(str(file_path12))
    assert "Story slide 1" in manager.get_entry_name(0)
    assert "ChocoboWorld" in manager.get_entry_name(11)
