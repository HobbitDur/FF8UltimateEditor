"""
Tests for Alexander's stage archive layer (Alexander/stagefs.py):
  - the FF7/FF8 LZSS decompressor
  - the fs/fi/fl archive reader (StageArchive)

A small synthetic fs/fi/fl triplet is built with known entries so the tests don't
need the original game files.
"""
import struct

import pytest

from Alexander.stagefs import (lzss_decompress, StageArchive, FsEntry,
                               COMP_NONE, COMP_LZSS)


class TestLzssDecompress:
    def test_all_literals(self):
        # control byte 0xFF => all 8 following bytes are literals
        assert lzss_decompress(bytes([0xFF]) + b"ABCDEFGH") == b"ABCDEFGH"

    def test_partial_literal_run(self):
        # control 0x0F => only the first 4 bits are literals, stream ends after them
        assert lzss_decompress(bytes([0x0F]) + b"WXYZ") == b"WXYZ"

    def test_back_reference_rle(self):
        # control 0x01: bit0 literal 'A', bit1 back-reference copying from the just-written
        # byte, length (0x02 + 3) = 5 -> RLE-fills five more 'A's.
        assert lzss_decompress(bytes([0x01, 0x41, 0xEE, 0xF2])) == b"AAAAAA"

    def test_expected_size_truncates(self):
        assert lzss_decompress(bytes([0xFF]) + b"ABCDEFGH", expected_size=3) == b"ABC"

    def test_empty_input(self):
        assert lzss_decompress(b"") == b""


def _build_archive(folder, entries):
    """entries: list of (name, payload, compression, decompressed_size).

    The .fi size field holds the *decompressed* size; COMP_LZSS payloads are stored
    behind a 4-byte compressed-size prefix, exactly as StageArchive expects.
    Returns the base path (no extension).
    """
    fs = bytearray()
    fi = bytearray()
    fl_lines = []
    for name, payload, compression, decompressed_size in entries:
        offset = len(fs)
        if compression == COMP_LZSS:
            fs += struct.pack("<I", len(payload)) + payload
        else:
            fs += payload
        fi += struct.pack("<III", decompressed_size, offset, compression)
        fl_lines.append(name)
    base = folder / "battle"
    (folder / "battle.fs").write_bytes(bytes(fs))
    (folder / "battle.fi").write_bytes(bytes(fi))
    (folder / "battle.fl").write_text("\r\n".join(fl_lines) + "\r\n", encoding="ascii")
    return str(base)


@pytest.fixture
def archive(tmp_path):
    raw_none = b"hello stage"
    lzss_stream = bytes([0xFF]) + b"ABCDEFGH"   # decompresses to 8 literal bytes
    entries = [
        ("c:\\ff8\\battle\\stage0.dat", raw_none, COMP_NONE, len(raw_none)),
        ("c:\\ff8\\battle\\stage1.dat", lzss_stream, COMP_LZSS, 8),
    ]
    base = _build_archive(tmp_path, entries)
    return base, raw_none


class TestStageArchive:
    def test_entries_parsed(self, archive):
        base, _ = archive
        arc = StageArchive(base)
        assert len(arc.entries) == 2
        assert all(isinstance(e, FsEntry) for e in arc.entries)

    def test_find_by_basename_is_case_insensitive(self, archive):
        base, _ = archive
        arc = StageArchive(base)
        assert arc.find("STAGE0.DAT").compression == COMP_NONE
        assert arc.find("stage1.dat").compression == COMP_LZSS

    def test_find_unknown_raises(self, archive):
        base, _ = archive
        arc = StageArchive(base)
        with pytest.raises(FileNotFoundError):
            arc.find("missing.dat")

    def test_read_uncompressed(self, archive):
        base, raw_none = archive
        arc = StageArchive(base)
        assert arc.read("stage0.dat") == raw_none

    def test_read_lzss(self, archive):
        base, _ = archive
        arc = StageArchive(base)
        assert arc.read("stage1.dat") == b"ABCDEFGH"

    def test_read_by_entry_object(self, archive):
        base, raw_none = archive
        arc = StageArchive(base)
        entry = arc.find("stage0.dat")
        assert arc.read(entry) == raw_none
