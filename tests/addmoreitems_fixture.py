"""Build FFNx AddMoreItems test files from the vanilla extracted ones, the way the FFNx branch's
own tests/ff8_items/make_fixture.py does: ids 199+ named "Extra Potion", battle records copied
from the Potion. Section numbers are kernel.bin's own (0-based) here: 7 = battle items,
8 = item names, 39 = their text."""
import struct

POTION_NAME = "Extra Potion"


def _encode(word):
    """FF8's Latin glyph encoding for plain letters and spaces."""
    return bytes(ord(c) + 4 if c.isupper() else ord(c) - 2 if c.islower() else 0x20 for c in word) + b"\0"


def extended_kernel(vanilla: bytes, added_names=57, added_battle=56) -> bytes:
    count = struct.unpack_from("<I", vanilla)[0]
    offsets = list(struct.unpack_from(f"<{count}I", vanilla, 4))
    sections = [vanilla[a:b] for a, b in zip(offsets, offsets[1:] + [len(vanilla)])]
    assert len(sections[7]) == 33 * 24 and len(sections[8]) == 166 * 4, "expects a vanilla kernel.bin"
    text = bytearray(sections[39])
    name = len(text)
    text += _encode(POTION_NAME)
    desc = len(text)
    text += _encode("Item expansion test")
    sections[39] = bytes(text)
    sections[8] += struct.pack("<HH", name, desc) * added_names
    sections[7] += sections[7][24:48] * added_battle
    result = bytearray(struct.pack("<I", count) + bytes(count * 4))
    new_offsets = []
    for section in sections:
        new_offsets.append(len(result))
        result.extend(section)
    struct.pack_into(f"<{count}I", result, 4, *new_offsets)
    return bytes(result)


def extended_menu_file(vanilla: bytes, rows=256) -> bytes:
    """mitem.bin / price.bin grown to `rows` rows, the new ones copied from the Potion's."""
    assert len(vanilla) == 199 * 4
    return vanilla + vanilla[4:8] * (rows - 199)
