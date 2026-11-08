"""FFNx section chunks for battle .dat files.

FFNx reads `direct/battle/<name>.dat.chunk.K` (K = 1..N, the section number) and rebuilds the battle
model file in memory: each section that has a chunk file is taken from it, the others from the file the
game loaded (vanilla or another mod's), packed again after a fresh header. So a mod can ship only the
sections it changes.

FFNx does it for (src/ff8/vram.cpp ff8_battle_open_and_read_file):
  - the monsters c0m000..c0m143 with 11 sections (battle file ids 166-309);
  - the character bodies dXcNNN.dat and weapons dXwNNN.dat, with the section count of their header
    (7 or 10 for a body, 8 or 5 for a weapon), from the FFNx version after 1.25.2.
The extended monsters c0m144..c0m199 and the other battle files are still replaced whole.
"""

import pathlib
import re
import struct

CHUNK_SECTION_COUNT = 11
LAST_CHUNK_MONSTER = 143
MAX_CHARACTER_SECTION_COUNT = 0x10       # FFNx refuses a dXc/dXw header with more sections
_MONSTER_NAME = re.compile(r"c0m(\d{3})\.dat", re.IGNORECASE)
_CHARACTER_NAME = re.compile(r"d[0-9a-z][cw]\d{3}\.dat", re.IGNORECASE)


def section_list(data: bytes) -> list:
    """The sections of a battle .dat (count, count + 1 offsets, then the sections); [] if it has none."""
    if len(data) < 8:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0 or 4 + 4 * (count + 1) > len(data):
        return []
    offset_list = struct.unpack_from(f"<{count + 1}I", data, 4)
    return [data[offset_list[i]:offset_list[i + 1]] for i in range(count)]


def _character_header_is_valid(data: bytes) -> bool:
    """What FFNx checks before rebuilding a dXc/dXw: 1..16 sections, the first one right after the
    header, offsets that never go back."""
    if len(data) < 8:
        return False
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0 or count > MAX_CHARACTER_SECTION_COUNT or 4 + 4 * (count + 1) > len(data):
        return False
    offset_list = struct.unpack_from(f"<{count + 1}I", data, 4)
    return (offset_list[0] == 4 * (count + 2) and offset_list[-1] <= len(data)
            and all(a <= b for a, b in zip(offset_list, offset_list[1:])))


def accepts_chunks(file_name: str, data: bytes) -> bool:
    """FFNx rebuilds this file from chunks: c0m000..c0m143 with 11 sections, or a dXc/dXw file."""
    match = _MONSTER_NAME.fullmatch(file_name)
    if match is not None:
        return int(match.group(1)) <= LAST_CHUNK_MONSTER and len(section_list(data)) == CHUNK_SECTION_COUNT
    return _CHARACTER_NAME.fullmatch(file_name) is not None and _character_header_is_valid(data)


def changed_section_list(reference: bytes, modded: bytes) -> list:
    """Section numbers (1-based) of `modded` that differ from `reference`."""
    reference_list, modded_list = section_list(reference), section_list(modded)
    if len(reference_list) != len(modded_list):
        raise ValueError(f"{len(modded_list)} sections, the reference has {len(reference_list)}")
    return [i + 1 for i, (a, b) in enumerate(zip(reference_list, modded_list)) if a != b]


def rebuild(loaded: bytes, chunk_folder, file_name: str) -> bytes:
    """What FFNx makes of `loaded` with the chunks of `chunk_folder`: each section from its chunk file
    when there is one, else from `loaded`, packed after a fresh header with the same section count."""
    chunk_folder = pathlib.Path(chunk_folder)
    section_bytes = []
    for number, section in enumerate(section_list(loaded), 1):
        chunk = chunk_folder / f"{file_name}.chunk.{number}"
        section_bytes.append(chunk.read_bytes() if chunk.exists() else section)
    offset_list, position = [], 4 * (len(section_bytes) + 2)
    for section in section_bytes:
        offset_list.append(position)
        position += len(section)
    return struct.pack(f"<{len(section_bytes) + 2}I", len(section_bytes), *offset_list, position) + b"".join(section_bytes)


def write_chunks(file_name: str, reference: bytes, modded: bytes, folder) -> list:
    """Write <folder>/<file_name>.chunk.K for every section of `modded` that differs from `reference`;
    returns the section numbers written. Chunks of that file left by an earlier run are removed."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    changed = changed_section_list(reference, modded)
    modded_list = section_list(modded)
    for stale in folder.glob(f"{file_name}.chunk.*"):
        stale.unlink()
    for number in changed:
        (folder / f"{file_name}.chunk.{number}").write_bytes(modded_list[number - 1])
    return changed
