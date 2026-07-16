"""Reading strings out of the two mngrp.bin text layouts.

* **String sections** (raw files 87+, the book text): a u16 count, then u16
  offsets from the start of the section, then the FF8-encoded strings. Offsets
  are positional - a text id is an offset slot and a zero offset is an empty
  string - which is how the engine indexes them (word_1D773A6[id]).

* **tkmnmes files** (raw files 0-2): a 2-level version of the same, read by
  getMenuString(useMenu, section, index, variant) at 0x4BD630. The section
  offset picks a subtable, then the entry is subtable[2 * index + variant].
"""


def _u16(data, offset):
    return int.from_bytes(data[offset:offset + 2], byteorder='little')


def decode_string_section(game_data, section_data):
    """Every string of a mngrp string section, indexed by text id."""
    nb_offset = _u16(section_data, 0)
    offset_list = [_u16(section_data, 2 + i * 2) for i in range(nb_offset)]
    sorted_offsets = sorted(offset for offset in offset_list if offset != 0)
    text_list = []
    for offset in offset_list:
        if offset == 0:
            text_list.append("")
            continue
        next_index = sorted_offsets.index(offset) + 1
        end = sorted_offsets[next_index] if next_index < len(sorted_offsets) else len(section_data)
        text_list.append(game_data.translate_hex_to_str(section_data[offset:end]))
    return text_list


def menu_string(game_data, tkmnmes_data, section, index, variant=0):
    """One string of a tkmnmes file, the way getMenuString (0x4BD630) reads it.

    Returns "" when the section or the entry has a zero offset (the engine
    returns its EMPTY_STRING there)."""
    section_offset = _u16(tkmnmes_data, 2 * section + 2)
    if not section_offset:
        return ""
    subtable = tkmnmes_data[section_offset:]
    entry = variant + 2 * index
    entry_offset = _u16(subtable, 2 * entry + 2)
    if not entry_offset:
        return ""
    raw = subtable[entry_offset:]
    end = raw.find(b"\x00")
    return game_data.translate_hex_to_str(raw[:end] if end >= 0 else raw)
