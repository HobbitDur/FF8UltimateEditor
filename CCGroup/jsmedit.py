"""
Inserting and removing instructions in the middle of a field script (.jsm).

The script data is a flat array of 4-byte instructions; everything that points into it must follow
when instructions move:
  - the script entry-point table (u16 per script, position in instructions in the low 15 bits, a flag
    in bit 15; its last entry is the end of the data): every position after the edit shifts;
  - the relative jumps JMP (0x02) and JPF (0x03): param = target index - own index (24-bit signed).
    Each one is recomputed from its own new position and its target's new position.
Nothing else in a .jsm holds an instruction position: GJMP and the REQ family name a script, LBL holds
its own script index, and the header offsets point before the script data.

Inserted instructions belong to the instruction they are put before: a jump that targeted it now
lands on the first inserted one, so every path that reached it runs them too (e.g. a value stored
right before a CARDGAME's pushes is set whichever branch leads to the match).
"""
import struct

OPCODE_JMP = 0x02
OPCODE_JPF = 0x03
RELATIVE_JUMP_OPCODES = (OPCODE_JMP, OPCODE_JPF)
MAX_POSITION = 0x7FFF  # 15-bit instruction position in the entry table


def encode(opcode: int, param: int = 0):
    """An instruction word: opcode in the high byte, 24-bit param (negative values wrap)."""
    return (opcode << 24) | (param & 0xFFFFFF)


def _sign_extend_24(value: int):
    return value - 0x1000000 if value & 0x800000 else value


def _layout(data: bytes):
    offset_section1, offset_script = struct.unpack_from("<HH", data, 4)
    if offset_section1 > offset_script or offset_script > len(data):
        raise ValueError("Not a field script: bad header offsets")
    nb_entries = (offset_script - offset_section1) // 2
    nb_instructions = (len(data) - offset_script) // 4
    return offset_section1, offset_script, nb_entries, nb_instructions


def _rebuild(data: bytes, new_words: list, position_map, target_map, old_words: list):
    """New file: entry table remapped with position_map, every relative jump re-aimed (its own new
    index from position_map, its target's from target_map). old_words[i] is None for a removed one."""
    offset_section1, offset_script, nb_entries, nb_instructions = _layout(data)
    result = bytearray(data[:offset_script])
    for entry_index in range(nb_entries):
        entry_offset = offset_section1 + entry_index * 2
        entry = struct.unpack_from("<H", data, entry_offset)[0]
        position = position_map(entry & 0x7FFF)
        if position > MAX_POSITION:
            raise ValueError("The field script is too long: its script table cannot address it")
        struct.pack_into("<H", result, entry_offset, (entry & 0x8000) | position)
    words = list(new_words)
    for old_index, word in enumerate(old_words):
        if word is None or word >> 24 not in RELATIVE_JUMP_OPCODES:
            continue
        new_index = position_map(old_index)
        target = target_map(old_index + _sign_extend_24(word & 0xFFFFFF))
        offset = target - new_index
        if not -0x800000 <= offset <= 0x7FFFFF:
            raise ValueError("A jump does not fit after the edit")
        words[new_index] = encode(word >> 24, offset)
    for word in words:
        result += struct.pack("<I", word)
    result += data[offset_script + nb_instructions * 4:]  # trailing bytes (none in vanilla files)
    return result


def instruction_words(data: bytes):
    _, offset_script, _, nb_instructions = _layout(data)
    return [struct.unpack_from("<I", data, offset_script + index * 4)[0] for index in range(nb_instructions)]


def insert_instructions(data: bytes, index: int, words: list):
    """A copy of the .jsm with `words` inserted before instruction `index` (relative to the script
    data). Refused before a script's first instruction (its LBL): the new code would end the
    previous script instead."""
    _, _, nb_entries, nb_instructions = _layout(data)
    if not 0 < index < nb_instructions:
        raise ValueError(f"Cannot insert at instruction {index}")
    offset_section1 = struct.unpack_from("<H", data, 4)[0]
    starts = {struct.unpack_from("<H", data, offset_section1 + entry * 2)[0] & 0x7FFF for entry in range(nb_entries)}
    if index in starts:
        raise ValueError(f"Instruction {index} starts a script: insert after its LBL")
    count = len(words)
    old_words = instruction_words(data)
    new_words = old_words[:index] + list(words) + old_words[index:]

    def position_map(position):
        return position + count if position >= index else position

    def target_map(target):
        return target + count if target > index else target

    return _rebuild(data, new_words, position_map, target_map, old_words)


def remove_instructions(data: bytes, index: int, count: int):
    """A copy of the .jsm without instructions [index, index + count). Jumps into the removed range
    land on what follows it. Refused when it would remove a script start or a jump."""
    _, _, nb_entries, nb_instructions = _layout(data)
    if count <= 0 or not 0 < index or index + count > nb_instructions:
        raise ValueError(f"Cannot remove instructions {index}-{index + count - 1}")
    offset_section1 = struct.unpack_from("<H", data, 4)[0]
    starts = {struct.unpack_from("<H", data, offset_section1 + entry * 2)[0] & 0x7FFF for entry in range(nb_entries)}
    if any(index <= start < index + count for start in starts):
        raise ValueError("The instructions to remove hold a script start")
    old_words = instruction_words(data)
    if any(word >> 24 in RELATIVE_JUMP_OPCODES for word in old_words[index:index + count]):
        raise ValueError("The instructions to remove hold a jump")
    new_words = old_words[:index] + old_words[index + count:]
    kept_words = old_words[:index] + [None] * count + old_words[index + count:]

    def position_map(position):
        return position - count if position >= index + count else position

    def target_map(target):
        if target >= index + count:
            return target - count
        return min(target, index)

    return _rebuild(data, new_words, position_map, target_map, kept_words)
