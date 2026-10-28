"""Hyne and FFNx's AddMoreAbility learned-ability block (Hyne/hynemanager.py docstring).

FFNx keeps learned ability ids 128-254 in a 524-byte block at image offset 0x1810 and uses it
only when it is valid and its copy of the 16 GF learned fields equals the savemap's. Hyne edits
those ids through the block, writes one only when an id past 127 is ticked, keeps its copy of
the learned fields current on save, and leaves a stale block alone.
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    HyneManager, IMAGE_SIZE, GAMESTATE_BASE, CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_START, CRC_SPAN_LEN,
    crc16_ff8, lzss_compress, lzss_decompress,
)
from Quezacotl.quezacotlmanager import GF_DATA_OFFSET, GF_ENTRY_SIZE

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BLOCK = 0x1810
BLOCK_SIZE = 524


def _learned(gf):
    return GAMESTATE_BASE + GF_DATA_OFFSET + gf * GF_ENTRY_SIZE + 20


def _fnv(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) % 2 ** 32
    return value


def _image(native_bits=(), block_native=None, block_extended=None):
    """native_bits: (gf, id < 128) learned in the savemap. block_*: 256-byte halves of a block."""
    image = bytearray(IMAGE_SIZE)
    for gf, ability_id in native_bits:
        image[_learned(gf) + ability_id // 8] |= 1 << (ability_id % 8)
    if block_native is not None:
        data = block_native + block_extended
        image[BLOCK:BLOCK + BLOCK_SIZE] = struct.pack("<IHHI", 0x42415846, 1, 16, _fnv(data)) + data
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    return bytes(image)


def _native_fields(image):
    return b"".join(bytes(image[_learned(gf):_learned(gf) + 16]) for gf in range(16))


def _write(path, image):
    compressed = lzss_compress(image)
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


def _read_image(path):
    raw = path.read_bytes()
    return lzss_decompress(raw[4:4 + struct.unpack_from("<I", raw)[0]])


def _ffnx_learned(image, gf, ability_id):
    """Whether FFNx sees the id learned after loading this image (kernel_ability.cpp rules)."""
    if ability_id < 128:
        return bool(image[_learned(gf) + ability_id // 8] & (1 << (ability_id % 8)))
    magic, version, count, checksum = struct.unpack_from("<IHHI", image, BLOCK)
    data = bytes(image[BLOCK + 12:BLOCK + BLOCK_SIZE])
    if not (magic == 0x42415846 and version == 1 and count == 16 and checksum == _fnv(data)
            and data[:256] == _native_fields(image)):
        return False
    extended = data[256:]
    index = ability_id - 128
    return bool(extended[gf * 16 + index // 8] & (1 << (index % 8)))


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


def test_a_vanilla_save_gets_the_block_when_an_id_past_127_is_ticked(game_data, tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image(native_bits=[(2, 5)]))
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.ability_extension == "none"
    gf = manager.gf_entries[2]
    assert gf.has_ability(5) and not gf.has_ability(130)

    gf.set_ability(130, True)
    gf.set_ability(9, True)
    manager.save_file(backup=False)

    image = _read_image(path)
    assert _ffnx_learned(image, 2, 130) and _ffnx_learned(image, 2, 5) and _ffnx_learned(image, 2, 9)
    assert not _ffnx_learned(image, 3, 130)
    reloaded = HyneManager(game_data)
    reloaded.load_file(str(path))
    assert reloaded.ability_extension == "extended" and reloaded.gf_entries[2].has_ability(130)


def test_a_save_without_ids_past_127_stays_vanilla(game_data, tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image(native_bits=[(0, 20)]))
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    manager.gf_entries[0].set_ability(200, False)    # unticking needs no block
    manager.gf_entries[0].set_ability(21, True)
    manager.save_file(backup=False)
    image = _read_image(path)
    assert image[BLOCK:BLOCK + BLOCK_SIZE] == bytes(BLOCK_SIZE)
    assert _ffnx_learned(image, 0, 21)


def test_learned_field_edits_keep_the_block_valid(game_data, tmp_path):
    """FFNx compares the block's copy of the learned fields with the savemap: editing an id
    below 128 must update that copy, or FFNx would drop every id past 127."""
    extended = bytearray(256)
    extended[4 * 16] = 0x01                           # GF 4 has learned id 128
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image(block_native=_native_fields(_image()), block_extended=bytes(extended)))
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.ability_extension == "extended" and manager.gf_entries[4].has_ability(128)
    manager.gf_entries[4].set_ability(40, True)
    manager.save_file(backup=False)
    image = _read_image(path)
    assert _ffnx_learned(image, 4, 128) and _ffnx_learned(image, 4, 40)


def test_a_stale_block_is_left_alone(game_data, tmp_path):
    """The learned fields changed after the block (saved without FFNx): FFNx ignores the block,
    and so does Hyne - its ids are not shown, and it is not rewritten."""
    extended = bytes([0xFF]) + bytes(255)
    path = tmp_path / "slot1_save01.ff8"
    image = _image(native_bits=[(0, 3)], block_native=_native_fields(_image()), block_extended=extended)
    _write(path, image)
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.ability_extension == "stale" and not manager.gf_entries[0].has_ability(128)
    manager.gf_entries[0].set_ability(4, True)
    manager.save_file(backup=False)
    saved = _read_image(path)
    assert saved[BLOCK:BLOCK + BLOCK_SIZE] == image[BLOCK:BLOCK + BLOCK_SIZE]
    assert not _ffnx_learned(saved, 0, 128)
