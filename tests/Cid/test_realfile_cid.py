"""Real-file round-trip test for the Cid tool (world-map draw points).

The Cid stores world draw-point *positions* in Section 34 of the world-map
``wmsetxx.obj`` file (see ``Cid/worlddrawsection.py``). ``WorldDrawSection.load``
consumes the *whole* wmset.obj: it reads the 48-entry section-offset table at the start
of the file, slices out Section 34, then splits it into a 0x2C header + N 4-byte records
``(x, y, sub_id, pad)``. This mirrors exactly what ``CidWidget._load_wmset`` feeds
into it (the file the user picks with the "Load wmsetxx.obj" button), which is why the test
passes the wmset.obj path directly rather than a pre-sliced section.

The editor rebuilds Section 34 in place, preserving the header and every other section and
keeping the record count constant, so a no-edit round-trip is **byte-exact / lossless** and
the test asserts that (strongest invariant). Real file: extracted_files/world/dat/wmset.obj
(the EN game's world-map file; it holds 128 records = the 128 world draw points, Draw IDs
129..256). Needs the real file, skipped otherwise (ff8data marker).
"""
import pathlib

import pytest

from Cid.worlddrawsection import WorldDrawSection

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
WMSET_REL = "extracted_files/world/dat/wmset.obj"
WMSET = PROJECT_ROOT / WMSET_REL


def _records_snapshot(section):
    return [list(record) for record in section.records]


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_roundtrip_is_byte_exact():
    """Load real wmset.obj -> save unchanged -> bytes identical (lossless)."""
    import tempfile

    section = WorldDrawSection()
    section.load(str(WMSET))
    assert section.is_loaded()
    assert section.get_nb_record() == 128, "expected 128 world draw-point records"

    out = pathlib.Path(tempfile.mkdtemp()) / "wmset_rt.obj"
    section.save(str(out))

    assert out.read_bytes() == WMSET.read_bytes(), "no-edit round-trip was not byte-exact"


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_records_survive_reload(tmp_path):
    """Parsed draw-point records (positions) survive a save + reload unchanged."""
    section = WorldDrawSection()
    section.load(str(WMSET))
    before = _records_snapshot(section)

    out = tmp_path / "wmset.obj"
    section.save(str(out))

    reloaded = WorldDrawSection()
    reloaded.load(str(out))
    assert _records_snapshot(reloaded) == before
    assert reloaded.header == section.header


@pytest.mark.ff8data(WMSET_REL)
def test_real_wmset_edit_persists(tmp_path):
    """Editing one draw point's position survives save + reload; neighbours untouched."""
    section = WorldDrawSection()
    section.load(str(WMSET))

    index = 5
    neighbours_before = {i: list(section.records[i]) for i in (index - 1, index + 1)}
    original = list(section.records[index])
    new_x, new_y, new_sub = (original[0] ^ 0x11) & 0xFF, (original[1] ^ 0x22) & 0xFF, (original[2] ^ 0x0F) & 0xFF
    assert (new_x, new_y, new_sub) != tuple(original[:3]), "picked a no-op edit"

    section.set_position(index, new_x, new_y, new_sub)
    out = tmp_path / "wmset.obj"
    section.save(str(out))

    reloaded = WorldDrawSection()
    reloaded.load(str(out))
    assert reloaded.records[index][0] == new_x
    assert reloaded.records[index][1] == new_y
    assert reloaded.records[index][2] == new_sub
    # padding byte preserved, not clobbered
    assert reloaded.records[index][3] == original[3]
    # neighbours unchanged
    for i, value in neighbours_before.items():
        assert reloaded.records[i] == value, f"neighbour record {i} changed unexpectedly"
