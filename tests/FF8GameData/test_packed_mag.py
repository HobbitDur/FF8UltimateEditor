"""PackedMag: the pointer map of a packed MAG file, and a part resized with every offset kept right."""
import pathlib
import re
import struct

import pytest

from FF8GameData.magcine.cinescript import CineOpcodeTable
from FF8GameData.magcine.packedmag import MagResizeError, PackedMag, is_packed

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAGIC = ROOT / "extracted_files/magic"
MAG230 = "extracted_files/magic/MAG230_B.00"


def _open(path):
    effect = int(re.match(r"MAG(\d+)", path.name)[1]) + 1
    return PackedMag(path.read_bytes(), path.name, CineOpcodeTable.for_effect(effect))


def _grown(data, at, size, extra):
    track = bytearray(data[at:at + size] + bytes(extra))
    struct.pack_into("<H", track, 6, size + extra)      # the track's own size field
    return bytes(track)


@pytest.mark.ff8data(MAG230)
def test_disease_breath_pointer_map():
    mag = _open(ROOT / MAG230)
    assert mag.camera == (0x870, 192)
    owners = {p.owner: p for p in mag.pointers()}
    assert owners["header +0x20 (stage camera)"].target == 0x870
    assert owners["header +0x10 (sound table)"].target == 0x930
    assert owners["header +0x0C (object table)"].target == 0xA84
    clut = owners["CLUT table entry 4"]
    assert (clut.base, clut.target, clut.mask) == (0x44, 0x44 + 0x21F0, 0xFFFFFF)
    assert mag.room_end(0x870) == 0x930 and not mag.fixed_references()
    assert not mag.resize_problem(0x870, 0x930)


@pytest.mark.ff8data(MAG230)
def test_every_camera_grows_and_shrinks_back_byte_exact():
    """44 of the 46 vanilla MAG cameras can change size; MAG218 and MAG222 keep theirs (their
    work buffer already reuses the memory of the .01, which a bigger .00 would move)."""
    grown = refused = 0
    for path in sorted(MAGIC.glob("MAG*_B.00")):
        data = path.read_bytes()
        if not is_packed(data):
            continue
        mag = _open(path)
        if mag.camera is None:
            continue
        companion = path.with_suffix(".01")
        after = companion.stat().st_size if companion.exists() else 0
        at, size = mag.camera
        try:
            new = mag.with_camera(_grown(data, at, size, 25), after)
        except MagResizeError as error:
            assert path.name in ("MAG218_B.00", "MAG222_B.00") and "work buffer" in str(error)
            refused += 1
            continue
        bigger = PackedMag(new, path.name, mag.table)
        assert bigger.camera == (at, size + 25) and len(new) == len(data) + 28
        # every part the game reaches is where its offsets now say, with the same bytes
        assert [e.sound_id for e in mag.sound_entries()] == [e.sound_id for e in bigger.sound_entries()]
        assert [v.left_points for v in mag.vibration_patterns()] == [v.left_points for v in bigger.vibration_patterns()]
        for old, moved in ((mag.container.texture_entries(), bigger.container.texture_entries()),
                           (mag.container.clut_entries(), bigger.container.clut_entries())):
            assert [(i, data[o:o + 64]) for i, o in old] == [(i, new[o:o + 64]) for i, o in moved]
        assert ([(o.index, o.kind, data[o.offset:o.offset + 64]) for o in mag.container.objects]
                == [(o.index, o.kind, new[o.offset:o.offset + 64]) for o in bigger.container.objects])
        assert len(bigger.program.instructions) == len(mag.program.instructions)
        assert bigger.with_camera(data[at:at + size], after) == data, path.name
        grown += 1
    assert (grown, refused) == (44, 2)


@pytest.mark.ff8data(MAG230)
def test_resize_refusals():
    mag = _open(ROOT / MAG230)
    # a part holding offsets cannot change size: the CLUT table (entry 4 at 0x54)
    assert "CLUT table entry 4 points inside the part" in mag.resize_problem(0x44)
    # the files loaded after this one are unknown while its script has fixed work buffers
    assert "the files loaded after" in _open(MAGIC / "MAG222_B.00").resize_problem(0x1398, loaded_after=None)
    assert not mag.resize_problem(0x870, loaded_after=None)     # MAG230 has none
    # the .01 has no script: the raw file positions it would need are unknown
    companion = PackedMag((ROOT / "extracted_files/magic/MAG230_B.01").read_bytes())
    assert "only a file with the script" in companion.resize_problem(0x30)
    # the files must fit the 1 MB magic buffer
    assert "1 MB" in mag.resize_problem(0x870, 0x930, delta=4, loaded_after=0x100000)
    with pytest.raises(MagResizeError):
        mag.resized(0x870, bytes(400), 0x930, loaded_after=0x100000)
