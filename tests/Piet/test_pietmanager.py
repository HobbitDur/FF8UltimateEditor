"""Tests for the Piet manager (mtmag.bin: tutorial-menu book page ranges).

The synthetic tests build a 12-byte mtmag.bin in memory; the real-file tests
load the original game file from extracted_files/ and are skipped when it is
missing (see the ff8data marker in the project-root conftest.py).
"""
import pathlib

import pytest

from Piet.pietmanager import PietManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MTMAG_BIN = PROJECT_ROOT / "extracted_files" / "menu" / "mtmag.bin"

# Retail English PC data: battle tutorial 43-50, card rules 51-63, card icons 64-67
RETAIL_DATA = bytes([43, 50, 0, 0, 51, 63, 0, 0, 64, 67, 0, 0])


@pytest.fixture
def retail_file(tmp_path):
    file_path = tmp_path / "mtmag.bin"
    file_path.write_bytes(RETAIL_DATA)
    return file_path


def test_load_parses_the_three_books(retail_file):
    manager = PietManager()
    manager.load_file(str(retail_file))
    assert [(b.first_entry, b.last_entry) for b in manager.books] == [(43, 50), (51, 63), (64, 67)]
    assert [b.nb_page for b in manager.books] == [8, 13, 4]
    assert manager.books[0].name == "Battle tutorial"


def test_synthetic_roundtrip_is_lossless(retail_file, tmp_path):
    # Non-zero padding must survive too
    data = bytearray(RETAIL_DATA)
    data[2:4] = (0xBEEF).to_bytes(2, "little")
    retail_file.write_bytes(bytes(data))

    manager = PietManager()
    manager.load_file(str(retail_file))
    out = tmp_path / "out.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == bytes(data)


def test_set_range_edit_persists(retail_file, tmp_path):
    manager = PietManager()
    manager.load_file(str(retail_file))
    manager.set_range(1, 51, 60)
    out = tmp_path / "out.bin"
    manager.save_file(str(out))

    reloaded = PietManager()
    reloaded.load_file(str(out))
    assert (reloaded.books[1].first_entry, reloaded.books[1].last_entry) == (51, 60)
    # Other books untouched
    assert (reloaded.books[0].first_entry, reloaded.books[0].last_entry) == (43, 50)
    assert (reloaded.books[2].first_entry, reloaded.books[2].last_entry) == (64, 67)


@pytest.mark.parametrize("book_id, first, last", [
    (3, 0, 5),      # bad book id
    (-1, 0, 5),     # bad book id
    (0, 10, 5),     # first > last
    (0, 0, 69),     # past the last mmag entry
    (0, -1, 5),     # negative entry
])
def test_set_range_rejects_invalid_values(retail_file, book_id, first, last):
    manager = PietManager()
    manager.load_file(str(retail_file))
    with pytest.raises(ValueError):
        manager.set_range(book_id, first, last)


def test_load_rejects_wrong_size(tmp_path):
    file_path = tmp_path / "mtmag.bin"
    file_path.write_bytes(bytes(10))
    with pytest.raises(ValueError):
        PietManager().load_file(str(file_path))


@pytest.mark.ff8data("extracted_files/menu/mtmag.bin")
def test_real_mtmag_bin_roundtrip_is_lossless(tmp_path):
    """Load the real mtmag.bin, save it, and expect identical bytes."""
    manager = PietManager()
    manager.load_file(str(MTMAG_BIN))
    assert len(manager.books) == PietManager.NB_BOOK

    out = tmp_path / "mtmag.bin"
    manager.save_file(str(out))
    assert out.read_bytes() == MTMAG_BIN.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mtmag.bin")
def test_real_mtmag_bin_matches_retail_ranges():
    """The English PC release defines books 43-50, 51-63 and 64-67."""
    manager = PietManager()
    manager.load_file(str(MTMAG_BIN))
    assert [(b.first_entry, b.last_entry) for b in manager.books] == [(43, 50), (51, 63), (64, 67)]
