"""Raw section file (.bin): the exact section bytes, for sections no readable format exists for
yet (skeleton, geometry, animation, sounds). Lossless by construction."""
import pathlib


def write_section_bytes(section_bytes: bytes, file_path: pathlib.Path):
    file_path.write_bytes(bytes(section_bytes))


def read_section_bytes(file_path: pathlib.Path) -> bytes:
    return file_path.read_bytes()
