"""Texture section as one TIM file per texture: texture_00.tim, texture_01.tim...

The section is a table followed by the TIM files back to back:
    u32 texture count
    u32 offset of each TIM (from the section start)
    u32 end offset (the section size)
    TIM data
Each TIM is written untouched, so every palette (CLUT) it carries is kept and any TIM tool can
open or produce it.
"""
import pathlib

from .common import SectionFileError

FILE_PREFIX = "texture_"
FILE_PATTERN = FILE_PREFIX + "*.tim"


def _read_u32(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], byteorder='little')


def split_tims(section_bytes: bytes) -> list:
    """Section bytes -> list of TIM byte streams, in table order."""
    if len(section_bytes) < 4:
        return []
    nb_texture = _read_u32(section_bytes, 0)
    offsets = [_read_u32(section_bytes, 4 + index * 4) for index in range(nb_texture)]
    tim_list = []
    for index, start in enumerate(offsets):
        if index + 1 < len(offsets):
            end = offsets[index + 1]
        else:
            end = len(section_bytes)
        tim_list.append(bytes(section_bytes[start:end]))
    return tim_list


def join_tims(tim_list: list) -> bytearray:
    """List of TIM byte streams -> section bytes (same layout the .dat writer produces)."""
    section = bytearray()
    section.extend(len(tim_list).to_bytes(4, byteorder='little'))
    current_offset = 4 + len(tim_list) * 4 + 4
    for tim in tim_list:
        section.extend(current_offset.to_bytes(4, byteorder='little'))
        current_offset += len(tim)
    section.extend(current_offset.to_bytes(4, byteorder='little'))
    for tim in tim_list:
        section.extend(tim)
    return section


def tim_files_of(folder: pathlib.Path) -> list:
    """The texture files of a section folder, in texture order."""
    return sorted(pathlib.Path(folder).glob(FILE_PATTERN), key=index_of_tim_file)


def index_of_tim_file(path: pathlib.Path) -> int:
    """texture_03.tim -> 3, or -1 for a name that does not carry an index."""
    digits = path.stem[len(FILE_PREFIX):]
    return int(digits) if digits.isdigit() else -1


def write_section_bytes(section_bytes: bytes, folder: pathlib.Path):
    """One file per texture, next to the other section files (not in a sub-folder, so selecting
    every file of a section folder selects the textures too)."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for old_tim in tim_files_of(folder):
        old_tim.unlink()
    for index, tim in enumerate(split_tims(section_bytes)):
        (folder / f"{FILE_PREFIX}{index:02d}.tim").write_bytes(tim)


def read_section_bytes(folder: pathlib.Path) -> bytearray:
    """Every texture_NN.tim of `folder` (the whole set: the section is all of them, so picking one
    texture file means taking the textures of its folder)."""
    folder = pathlib.Path(folder)
    tim_files = tim_files_of(folder)
    for expected_index, tim_file in enumerate(tim_files):
        if index_of_tim_file(tim_file) != expected_index:
            raise SectionFileError(f"{folder}: {FILE_PREFIX}{expected_index:02d}.tim is missing, "
                                   f"the textures must be numbered without gaps")
    return join_tims([tim_file.read_bytes() for tim_file in tim_files])
