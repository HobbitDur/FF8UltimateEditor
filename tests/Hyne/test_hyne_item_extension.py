"""Hyne and FFNx's AddMoreItems inventory block (255 slots, Hyne/hynemanager.py docstring).

FFNx writes all 255 slots in a 522-byte block at image offset 0x1600 and uses it only when it is
valid and its first 198 slots equal the savemap's item table. Hyne edits that block when there is
one, copies the first 198 into the table on save, keeps the slots acceptable to FFNx, and can add
the block to a vanilla save.
"""
import pathlib
import struct

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    HyneManager, IMAGE_SIZE, GAMESTATE_BASE, CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_START, CRC_SPAN_LEN,
    crc16_ff8, lzss_compress, lzss_decompress, normalize_item_slots,
)
from Quezacotl.quezacotlmanager import ITEMS_DATA_OFFSET

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
ITEM_TABLE = GAMESTATE_BASE + ITEMS_DATA_OFFSET
BLOCK = 0x1600


def _fnv(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) % 2 ** 32
    return value


def _image(slots, block_slots=None):
    image = bytearray(IMAGE_SIZE)
    for index, (item_id, quantity) in enumerate(slots):
        image[ITEM_TABLE + 2 * index:ITEM_TABLE + 2 * index + 2] = bytes([item_id, quantity])
    if block_slots is not None:
        raw = bytes(b for pair in block_slots for b in pair).ljust(510, b"\0")
        image[BLOCK:BLOCK + 522] = struct.pack("<IHHI", 0x4D495846, 1, 255, _fnv(raw)) + raw
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    return bytes(image)


def _write(path, image):
    compressed = lzss_compress(image)
    path.write_bytes(struct.pack("<I", len(compressed)) + compressed)


def _read_image(path):
    raw = path.read_bytes()
    return lzss_decompress(raw[4:4 + struct.unpack_from("<I", raw)[0]])


def _ffnx_inventory(image):
    """The 255 slots FFNx loads from an image, following its own rules (kernel_item.cpp)."""
    native = [tuple(image[ITEM_TABLE + 2 * i:ITEM_TABLE + 2 * i + 2]) for i in range(198)]
    magic, version, count, checksum = struct.unpack_from("<IHHI", image, BLOCK)
    raw = image[BLOCK + 12:BLOCK + 522]
    block = [tuple(raw[2 * i:2 * i + 2]) for i in range(255)]
    ids = [i for i, _ in block if i]
    valid = (magic == 0x4D495846 and version == 1 and count == 255 and checksum == _fnv(raw)
             and all(q <= 100 and bool(i) == bool(q) for i, q in block) and len(ids) == len(set(ids))
             and block[:198] == native)
    return block if valid else native + [(0, 0)] * 57


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


def test_a_vanilla_save_gets_the_255_slots_on_request(game_data, tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image([(1, 10), (33, 2)]))
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.item_extension == "none" and len(manager.item_entries) == 198

    manager.enable_item_extension()
    assert manager.item_extension == "extended" and len(manager.item_entries) == 255
    assert (manager.item_entries[1].item_id, manager.item_entries[1].quantity) == (33, 2)
    manager.item_entries[230].item_id, manager.item_entries[230].quantity = 201, 5
    manager.save_file(backup=False)

    inventory = _ffnx_inventory(_read_image(path))
    assert inventory[:2] == [(1, 10), (33, 2)] and inventory[230] == (201, 5)
    reloaded = HyneManager(game_data)
    reloaded.load_file(str(path))
    assert reloaded.item_extension == "extended"
    assert (reloaded.item_entries[230].item_id, reloaded.item_entries[230].quantity) == (201, 5)


def test_slot_edits_reach_the_vanilla_table_and_stay_acceptable(game_data, tmp_path):
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image([(1, 10)], block_slots=[(1, 10)]))
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.item_extension == "extended"
    entries = manager.item_entries
    entries[0].quantity = 60
    entries[200].item_id, entries[200].quantity = 1, 70     # the same item twice
    entries[3].item_id, entries[3].quantity = 5, 0          # an item with nothing held
    entries[10].item_id, entries[10].quantity = 250, 200    # more than FFNx keeps
    manager.save_file(backup=False)
    inventory = _ffnx_inventory(_read_image(path))
    assert inventory[0] == (1, 100) and inventory[200] == (0, 0)
    assert inventory[3] == (0, 0) and inventory[10] == (250, 100)


def test_a_stale_block_is_left_alone(game_data, tmp_path):
    """The item table changed after the block (the vanilla game saved over it): FFNx takes the
    table, and so does Hyne - the block is not shown, nor rewritten."""
    path = tmp_path / "slot1_save01.ff8"
    image = _image([(2, 3)], block_slots=[(1, 10), (0, 0)] + [(0, 0)] * 220 + [(240, 1)])
    _write(path, image)
    manager = HyneManager(game_data)
    manager.load_file(str(path))
    assert manager.item_extension == "stale" and len(manager.item_entries) == 198
    manager.item_entries[0].quantity = 4
    manager.save_file(backup=False)
    saved = _read_image(path)
    assert saved[BLOCK:BLOCK + 522] == image[BLOCK:BLOCK + 522]
    assert _ffnx_inventory(saved)[0] == (2, 4)


def test_normalize_item_slots():
    assert normalize_item_slots([(1, 50), (0, 3), (1, 60), (7, 0), (9, 150)]) == \
        [(1, 100), (0, 0), (0, 0), (0, 0), (9, 100)]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_the_items_tab_offers_the_kernel_items(qapp, tmp_path):
    from Hyne.hynewidget import HyneWidget
    from tests.addmoreitems_fixture import POTION_NAME, extended_kernel
    path = tmp_path / "slot1_save01.ff8"
    _write(path, _image([(1, 10)], block_slots=[(1, 10)] + [(0, 0)] * 200 + [(201, 4)]))
    kernel = tmp_path / "kernel.bin"
    kernel.write_bytes(extended_kernel((PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin").read_bytes()))
    widget = HyneWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.load_file(str(path))
    assert widget.items_table.rowCount() == 255
    assert widget.item_extension_button.isHidden()
    combo = widget.items_table.cellWidget(201, 0)
    assert combo.currentText() == "201: (unknown)"      # no kernel.bin: kept, by its id
    assert combo.findData(230) < 0
    widget.kernel_names._load(str(kernel))
    combo = widget.items_table.cellWidget(201, 0)
    assert combo.currentText() == f"201: {POTION_NAME}"
    assert combo.findData(255) >= 0 and combo.findData(1) >= 0
