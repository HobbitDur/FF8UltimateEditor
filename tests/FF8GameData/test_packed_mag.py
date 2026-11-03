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
MAG218 = "extracted_files/magic/MAG218_B.00"   # effect 219: its work buffer already covers its .01
MAG222 = "extracted_files/magic/MAG222_B.00"


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
    """45 of the 46 vanilla MAG cameras can change size. MAG222 keeps its size: its work buffer
    already reuses the memory of the .01, and its script copies .01 textures into the magic buffer,
    which a moved .01 would change."""
    grown = refused = 0
    for path in sorted(MAGIC.glob("MAG*_B.00")):
        data = path.read_bytes()
        if not is_packed(data):
            continue
        mag = _open(path)
        if mag.camera is None:
            continue
        companion = path.with_suffix(".01")
        after = companion.read_bytes() if companion.exists() else 0
        at, size = mag.camera
        try:
            new = mag.with_camera(_grown(data, at, size, 25), after)
        except MagResizeError as error:
            assert path.name == "MAG222_B.00" and "CopyAlternativeTexture" in str(error)
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
    assert (grown, refused) == (45, 1)


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
    assert mag.growth_room(0x20000) == (0x100000 - len(mag.data) - 0x20000,
                                       "the effect's files must fit the 1 MB magic buffer")
    with pytest.raises(MagResizeError):
        mag.resized(0x870, bytes(400), 0x930, loaded_after=0x100000)


@pytest.mark.ff8data(MAG218, MAG218[:-1] + "1")
def test_mag218_grows_up_to_its_bone_slots_and_back():
    """MAG218's work buffer (0x32000) already covers its .01. Its script uploads every .01 texture
    on ticks 1-3, before the first write to a work buffer, so only the .01 header and its 96 bone
    slots (from .01 + 0xA8, 0x100 bytes each) must stay before 0x32000."""
    data, companion = (ROOT / MAG218).read_bytes(), (ROOT / MAG218).with_suffix(".01").read_bytes()
    mag = _open(ROOT / MAG218)
    assert mag.work_buffer_floor() == 0x32000 and mag.bone_count() == 96
    room = 0x32000 - (0xA8 + 96 * 0x100) - len(data)
    assert room == 0x157B0 and mag.growth_room(companion)[0] == room
    assert "bone slots" in mag.growth_room(companion)[1]
    at, size = mag.camera
    track = data[at:at + size]
    # up to the limit, and back: the original bytes
    bigger = mag.resized(at, track + bytes(room), at + size, companion)
    assert len(bigger) == len(data) + room
    grown = PackedMag(bigger, mag.name, mag.table)
    assert grown.camera == (at, size) and grown.growth_room(companion)[0] == 0
    assert grown.resized(at, track, at + size + room, companion) == data
    # one byte past it is refused (the part keeps its 4-byte alignment: 4 bytes too many)
    assert "0x157B0 bytes free" in mag.resize_problem(at, at + size, room + 4, companion)
    with pytest.raises(MagResizeError, match="bone slots must end before the script's work buffer at 0x32000"):
        mag.resized(at, track + bytes(room + 1), at + size, companion)
    # a grown camera through the camera API too, and shrinking is always fine
    bigger = mag.with_camera(_grown(data, at, size, 400), companion)
    assert PackedMag(bigger, mag.name, mag.table).with_camera(track, companion) == data
    assert not mag.resize_problem(at, at + size, -4, companion)


@pytest.mark.ff8data(MAG218, MAG218[:-1] + "1", MAG222, MAG222[:-1] + "1")
def test_work_buffer_reuse_refusals():
    data, companion = (ROOT / MAG218).read_bytes(), (ROOT / MAG218).with_suffix(".01").read_bytes()
    mag = _open(ROOT / MAG218)
    at, size = mag.camera
    # the .01 size alone cannot place the bone slots
    assert "the .01 itself is needed" in mag.resize_problem(at, at + size, 4, len(companion))
    # an edited script is not the proven one: a longer wait could upload a texture after the
    # first packet write
    edited = bytearray(data)
    assert struct.unpack_from("<H", data, 0xD2)[0] == 0x0609            # Wait 3
    struct.pack_into("<H", edited, 0xD2, 0x0809)                        # Wait 4
    problem = PackedMag(bytes(edited), mag.name, mag.table).resize_problem(at, at + size, 4, companion)
    assert "only a script proven" in problem and "MAG218" in problem
    # a .01 with more than textures (an object table) is not covered by the proof
    other = bytearray(companion)
    struct.pack_into("<I", other, 0x0C, 0x30)
    assert "more than textures" in mag.resize_problem(at, at + size, 4, bytes(other))
    # MAG222 copies .01 textures into the magic buffer: a moved .01 changes what is copied
    meteor = _open(ROOT / MAG222)
    meteor_01 = (ROOT / MAG222).with_suffix(".01").read_bytes()
    assert meteor.work_buffer_floor() == 0x28000
    assert [(c.offset, 16 * c.words[1]) for c in meteor.texture_copies()] == [(0x76, 0x3E000), (0x7C, 0x4E000)]
    problem = meteor.resize_problem(0x1398, 0x1398 + 2348, 4, meteor_01)
    assert "work buffer at 0x28000" in problem and "CopyAlternativeTexture" in problem
    assert meteor.growth_room(meteor_01) == (0, problem)
    assert not meteor.resize_problem(0x1398, 0x1398 + 2348, 0, meteor_01)   # same size: fine
