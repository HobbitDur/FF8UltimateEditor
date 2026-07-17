"""Tests for the camera animation collection model (FF8GameData/dat/cameracollection.py).

Section 6 of a monster .dat is a key-framed camera animation collection, not a byte-code
program. Two properties matter and are pinned here:

- the walk reads the same structure the engine does, on real data (every vanilla monster
  camera section parses, with the 18-byte frame alignment confirmed by the always-zero
  padding bytes);
- editing a field patches exactly that field's bytes, so opening a file and saving it back
  is byte-for-byte identical except for what was changed - the section cannot be corrupted.
"""
import pathlib
import struct

import pytest

from FF8GameData.dat.cameracollection import (parse_camera_collection, CameraParseError,
                                             CameraCollection, FRAME_SIZE,
                                             add_animation_to_slot)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"


def _build_synthetic_collection() -> bytes:
    """A minimal but complete collection: 1 set, slot 0 = one block with one keyframe, the
    other 7 slots empty. Independent of the extracted files, for deterministic unit tests."""
    data = bytearray()
    data += struct.pack("<H", 1)      # nbOfSet
    data += struct.pack("<H", 8)      # setPointer[0] (set starts at offset 8)
    eof_offset = len(data)
    data += struct.pack("<H", 0)      # eof placeholder
    data += struct.pack("<H", 0)      # 2 bytes padding so the set lands on offset 8
    # set 0 at offset 8: slot0 points at the animation (rel to set start, x2), rest empty
    set_start = len(data)
    data += struct.pack("<h", 8)      # slot0: 8*2 = 16 bytes past set start -> offset 24
    for _ in range(7):
        data += struct.pack("<h", -1)  # 0xFFFF: empty slot
    assert len(data) == set_start + 16
    # animation at offset 24: one block
    data += struct.pack("<H", 0x03C1)          # ctrl: FOV mode3, ROLL mode3, layout1
    data += struct.pack("<HH", 0x200, 0x210)   # FOV start, end
    data += struct.pack("<HH", 0, 5)           # ROLL start, end
    data += struct.pack("<H", 13)              # frame duration
    data += struct.pack("<BB", 0x90, 0)        # pos interp mode, pad
    data += struct.pack("<hhh", -4001, 1739, 2985)   # pos Z, X, Y
    data += struct.pack("<BB", 0x90, 0)        # look interp mode, pad
    data += struct.pack("<hhh", 316, 355, 236)       # look Z, X, Y
    data += struct.pack("<H", 0xFFFF)          # frame terminator
    data += struct.pack("<H", 0xFFFF)          # end-of-animation control word
    struct.pack_into("<H", data, eof_offset, len(data))  # eof == total length
    return bytes(data)


class TestSynthetic:
    def test_a_known_collection_reads_back_its_values(self):
        collection = parse_camera_collection(_build_synthetic_collection())
        assert collection.nb_set == 1
        camera_set = collection.sets[0]
        assert sum(1 for anim in camera_set.animations if not anim.empty) == 1
        animation = camera_set.animations[0]
        assert not animation.empty
        assert [anim.empty for anim in camera_set.animations[1:]] == [True] * 7
        block, = animation.blocks
        assert (block.fov_mode, block.roll_mode, block.layout) == (3, 3, 1)
        assert block.fov_start.get() == 0x200 and block.fov_end.get() == 0x210
        assert block.roll_start.get() == 0 and block.roll_end.get() == 5
        frame, = block.frames
        assert frame.duration.get() == 13
        assert (frame.pos_z.get(), frame.pos_x.get(), frame.pos_y.get()) == (-4001, 1739, 2985)
        assert (frame.look_z.get(), frame.look_x.get(), frame.look_y.get()) == (316, 355, 236)
        assert frame.pos_interp_mode.get() == 0x90 and frame.look_interp_mode.get() == 0x90

    def test_editing_a_field_patches_only_its_bytes(self):
        data = bytearray(_build_synthetic_collection())
        collection = parse_camera_collection(data)
        frame = collection.sets[0].animations[0].blocks[0].frames[0]
        before = bytes(collection.get_bytes())
        frame.pos_x.set(-1000)
        after = bytes(collection.get_bytes())
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        assert changed == [frame.pos_x.offset, frame.pos_x.offset + 1]
        assert frame.pos_x.get() == -1000

    def test_a_value_out_of_range_is_refused(self):
        collection = parse_camera_collection(_build_synthetic_collection())
        frame = collection.sets[0].animations[0].blocks[0].frames[0]
        with pytest.raises(ValueError):
            frame.pos_x.set(40000)      # > 32767 for a signed 16-bit field
        with pytest.raises(ValueError):
            frame.pos_interp_mode.set(300)  # > 255 for a byte

    def test_an_empty_section_is_empty(self):
        assert parse_camera_collection(b"").is_empty()
        assert parse_camera_collection(b"\x00\x00").is_empty()

    def test_a_non_collection_section_is_rejected(self):
        # eof word that does not equal the section length: not a collection
        junk = struct.pack("<HHH", 1, 8, 999) + b"\x00" * 20
        with pytest.raises(CameraParseError):
            parse_camera_collection(junk)

    def test_add_animation_fills_an_empty_slot_and_round_trips(self):
        collection = parse_camera_collection(_build_synthetic_collection())
        empty_slot = next(a.slot for a in collection.sets[0].animations if a.empty)
        new_data = add_animation_to_slot(collection.get_bytes(), 0, empty_slot)

        rebuilt = parse_camera_collection(new_data)  # must still parse (eof == length, etc.)
        assert bytes(rebuilt.get_bytes()) == new_data
        assert len(new_data) % 4 == 0
        animation = rebuilt.sets[0].animations[empty_slot]
        assert not animation.empty
        assert len(animation.blocks) == 1
        assert len(animation.blocks[0].frames) == 2
        # the previously-present animation (slot 0) is untouched
        assert not rebuilt.sets[0].animations[0].empty

    def test_add_animation_rejects_a_bad_target(self):
        collection = parse_camera_collection(_build_synthetic_collection())
        with pytest.raises(ValueError):
            add_animation_to_slot(collection.get_bytes(), 5, 0)   # no such set
        with pytest.raises(ValueError):
            add_animation_to_slot(collection.get_bytes(), 0, 99)  # no such slot


def _monster_camera_sections():
    """(file name, section-6 bytes) for every monster file that has a camera section."""
    for path in sorted(BATTLE_PATH.glob("c0m*.dat")):
        raw = path.read_bytes()
        nb_section = struct.unpack_from("<I", raw, 0)[0]
        if nb_section <= 6:
            continue
        position = [struct.unpack_from("<I", raw, 4 + 4 * i)[0] for i in range(nb_section)]
        section = raw[position[5]:position[6]]  # monster camera = 6th section
        if len(section) >= 6:
            yield path.name, section


@pytest.mark.skipif(not BATTLE_PATH.is_dir(), reason="extracted battle files not available")
class TestRealFiles:
    def test_every_monster_camera_section_parses_and_round_trips(self):
        broken = []
        nb = 0
        for name, section in _monster_camera_sections():
            nb += 1
            try:
                collection = parse_camera_collection(section)
            except CameraParseError as error:
                broken.append(f"{name}: {error}")
                continue
            if bytes(collection.get_bytes()) != section:
                broken.append(f"{name}: section not preserved")
        assert nb > 100, f"corpus looks too small ({nb} camera sections)"
        assert not broken, f"{len(broken)} camera sections do not round trip: {broken[:20]}"

    def test_every_keyframe_is_correctly_aligned(self):
        """The 18-byte frame layout is right iff the two padding bytes are always zero: a
        mis-sized frame would land those offsets on real data."""
        misaligned = []
        for name, section in _monster_camera_sections():
            try:
                collection = parse_camera_collection(section)
            except CameraParseError:
                continue
            for camera_set in collection.sets:
                for animation in camera_set.animations:
                    for block in animation.blocks:
                        for frame in block.frames:
                            if section[frame.offset + 3] != 0 or section[frame.offset + 11] != 0:
                                misaligned.append(f"{name} @0x{frame.offset:X}")
        assert not misaligned, f"non-zero padding (misalignment): {misaligned[:20]}"

    def test_editing_a_real_section_changes_only_the_edited_bytes(self):
        for name, section in _monster_camera_sections():
            collection = parse_camera_collection(section)
            frame = next((block.frames[0]
                          for camera_set in collection.sets
                          for animation in camera_set.animations if not animation.empty
                          for block in animation.blocks if block.frames), None)
            if frame is None:
                continue
            before = bytes(collection.get_bytes())
            frame.pos_y.set((frame.pos_y.get() + 123) if frame.pos_y.get() < 32000 else 0)
            after = bytes(collection.get_bytes())
            changed = [i for i in range(len(before)) if before[i] != after[i]]
            assert changed == [frame.pos_y.offset, frame.pos_y.offset + 1], name
            return  # one real file is enough for this property
