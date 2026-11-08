"""FFNx section chunks for battle .dat files.

FFNx reads `direct/battle/c0mNNN.dat.chunk.K` (K = 1..11, the section number) and rebuilds the monster
file in memory: each section that has a chunk file is taken from it, the others from the file the game
loaded (vanilla or another mod's). So a mod can ship only the sections it changes.

FFNx does it only for c0m000..c0m143 files with 11 sections (src/ff8/vram.cpp
ff8_battle_open_and_read_file, battle file ids 166-309): the extended monsters c0m144..c0m199, the
character bodies and weapons (dXc, dXw) and the other battle files are still replaced whole.
"""

import pathlib
import re
import struct

CHUNK_SECTION_COUNT = 11
LAST_CHUNK_MONSTER = 143
_MONSTER_NAME = re.compile(r"c0m(\d{3})\.dat", re.IGNORECASE)


def section_list(data: bytes) -> list:
    """The sections of a battle .dat (count, count + 1 offsets, then the sections); [] if it has none."""
    if len(data) < 8:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0 or 4 + 4 * (count + 1) > len(data):
        return []
    offset_list = struct.unpack_from(f"<{count + 1}I", data, 4)
    return [data[offset_list[i]:offset_list[i + 1]] for i in range(count)]


def accepts_chunks(file_name: str, data: bytes) -> bool:
    """FFNx rebuilds this file from chunks: c0m000..c0m143 with 11 sections."""
    match = _MONSTER_NAME.fullmatch(file_name)
    return (match is not None and int(match.group(1)) <= LAST_CHUNK_MONSTER
            and len(section_list(data)) == CHUNK_SECTION_COUNT)


def changed_section_list(reference: bytes, modded: bytes) -> list:
    """Section numbers (1-based) of `modded` that differ from `reference`."""
    reference_list, modded_list = section_list(reference), section_list(modded)
    if len(reference_list) != len(modded_list):
        raise ValueError(f"{len(modded_list)} sections, the reference has {len(reference_list)}")
    return [i + 1 for i, (a, b) in enumerate(zip(reference_list, modded_list)) if a != b]


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
