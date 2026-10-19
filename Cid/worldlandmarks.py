"""Read-only map labels from wmset's location records and localised names."""
import struct


def read_landmarks(data, game_data):
    """Return (name, block_x, block_y) references, without changing source bytes.

    Section 30's first two bytes are low-resolution map-icon positions; its
    signed world X/Y values retain more precision. World origin is at the
    centre of the 128x96 block map, with Y increasing northwards. Section 31
    owns the names. These are fixed reference locations, not a simulation of
    which cities/vehicles are available in the selected story phases.
    """
    if len(data) < 48 * 4:
        raise ValueError('Truncated wmset header')
    offsets = struct.unpack_from('<48I', data)
    sections = []
    for index in (30, 31):
        start, end = offsets[index:index + 2]
        if not 192 <= start < end <= len(data):
            raise ValueError('Invalid location section bounds')
        sections.append(data[start:end])
    records, text = sections
    if len(records) < 4 or len(text) < 8:
        raise ValueError('Truncated locations')
    end = struct.unpack_from('<I', records)[0]
    if not 4 <= end <= len(records) or (end - 4) % 12:
        raise ValueError('Invalid location records')
    first_text = struct.unpack_from('<I', text)[0]
    if not 8 <= first_text <= len(text) or first_text % 4:
        raise ValueError('Invalid location name table')
    names = []
    for pos in range(0, first_text, 4):
        offset = struct.unpack_from('<I', text, pos)[0]
        if offset == 0:
            break
        if not first_text <= offset < len(text):
            raise ValueError('Invalid location name offset')
        terminator = text.find(b'\0', offset)
        if terminator < 0:
            raise ValueError('Unterminated location name')
        name = game_data.translate_hex_to_str(text[offset:terminator])
        # The decoder renders location dictionary tokens as {Balamb}, etc.
        names.append(name.replace('{', '').replace('}', '').strip())
    result, seen = [], set()
    for _, _, location_id, _, x, y in struct.iter_unpack('<BBBBii', records[4:end]):
        if location_id >= len(names) or not names[location_id]:
            continue
        bx, by = 64 + x / 2048, 48 - y / 2048
        item = (names[location_id], bx, by)
        if 0 <= bx < 128 and 0 <= by < 96 and item not in seen:
            result.append(item)
            seen.add(item)
    return result
