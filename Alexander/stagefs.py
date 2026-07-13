"""Stateless FF8 FS/FI/FL archive reader (random access), enough to pull
battle stage files out of battle.fs. Kept independent of the app's streaming
FsManager, whose generators are single-pass and unsuited to on-demand picking."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass

COMP_NONE = 0
COMP_LZSS = 1


def lzss_decompress(src: bytes, expected_size: int | None = None) -> bytes:
    """FF7/FF8 LZSS: 12-bit window offset, 4-bit length (+3), 18-byte bias."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        control = src[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if control & (1 << bit):
                out.append(src[i])
                i += 1
            else:
                if i + 1 >= n:
                    break
                b1, b2 = src[i], src[i + 1]
                i += 2
                ofs = ((b2 & 0xF0) << 4) | b1
                length = (b2 & 0x0F) + 3
                pos = len(out) - ((len(out) - 18 - ofs) & 0xFFF)
                for _ in range(length):
                    out.append(out[pos] if pos >= 0 else 0)
                    pos += 1
        if expected_size is not None and len(out) >= expected_size:
            break
    if expected_size is not None:
        del out[expected_size:]
    return bytes(out)


@dataclass
class FsEntry:
    name: str
    size: int
    offset: int
    compression: int


class StageArchive:
    """Reader for one fs/fi/fl triplet, e.g. StageArchive(r'...\\lang-en\\battle')."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        with open(base_path + ".fl", "r", encoding="ascii", errors="replace") as f:
            names = [line.strip() for line in f if line.strip()]
        with open(base_path + ".fi", "rb") as f:
            fi = f.read()
        self.entries: list[FsEntry] = []
        for i, name in enumerate(names):
            size, offset, comp = struct.unpack_from("<III", fi, i * 12)
            self.entries.append(FsEntry(name, size, offset, comp))
        self._by_basename = {os.path.basename(e.name.replace("\\", "/")).lower(): e
                             for e in self.entries}

    def find(self, basename: str) -> FsEntry:
        try:
            return self._by_basename[basename.lower()]
        except KeyError:
            raise FileNotFoundError(f"{basename} not in {self.base_path}.fl") from None

    def read(self, name_or_entry) -> bytes:
        entry = name_or_entry if isinstance(name_or_entry, FsEntry) else self.find(name_or_entry)
        with open(self.base_path + ".fs", "rb") as f:
            f.seek(entry.offset)
            if entry.compression == COMP_NONE:
                return f.read(entry.size)
            if entry.compression == COMP_LZSS:
                (csize,) = struct.unpack("<I", f.read(4))
                return lzss_decompress(f.read(csize), entry.size)
        raise NotImplementedError(f"compression {entry.compression} not supported")

    def stage_basenames(self) -> list[str]:
        return sorted(n for n in self._by_basename if n.startswith("a0stg") and n.endswith(".x"))
