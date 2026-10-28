"""Tests for the 30 fps conversion of the battle cameras (FF8GameData/dat/camera30.py): keyframe
collections (monster section 6, character section 5) and camera tracks (stage, r0win, exe effect
tracks, .bcam, MAG). FFNx plays every camera at 30 Hz: every keyframe duration doubles, a one-tick
script wait is repeated, a shot-flag wait is kept, a 04 ease duration doubles."""
import pathlib
import struct

import pytest

from FF8GameData.dat import camera30
from FF8GameData.dat.cameracollection import _serialize, build_default_animation, parse_camera_collection
from FF8GameData.dat.camerascript import run_camera_script_frames
from FF8GameData.dat.cameratrack import HEADER, CameraTrack, read_track_parts
from FF8GameData.dat.sequencevm import camera_sequence_vm
from FF8GameData.gamedata import GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"
needs_files = pytest.mark.skipif(not (BATTLE_PATH / "c0m001.dat").exists(),
                                 reason="extracted battle files not available")

STAGE_SCRIPT = bytes.fromhex("0500c310e57fc100cb7fea06e607e60201e6f10302")


@pytest.fixture(scope="module")
def vm():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_camera_sequence_data()
    return camera_sequence_vm(game_data)


def _durations(collection):
    return [frame.duration.get() for camera_set in collection.sets for animation in camera_set.animations
            for block in animation.blocks for frame in block.frames]


def _collection(*animations):
    """A one-set collection; each slot holds the given animation bytes (None = empty)."""
    slots = [(object(), animation) if animation is not None else (None, None) for animation in animations]
    slots += [(None, None)] * (8 - len(slots))
    return bytes(_serialize([slots]))


def _animation(*durations):
    """One block (default FOV/roll) with a keyframe per duration."""
    data = bytearray(struct.pack("<H", (1 << 6) | (1 << 8)))
    for duration in durations:
        data += struct.pack("<HBBhhhBBhhh", duration, 0, 0, 1, 2, 3, 0, 0, 4, 5, 6)
    return bytes(data + struct.pack("<HH", 0xFFFF, 0xFFFF))


def _track(script: bytes, collection: bytes) -> bytes:
    script = script + b"\0" * (len(script) % 2)
    keyframe_offset = 8 + len(script)
    return HEADER.pack(2, 8, keyframe_offset, keyframe_offset + len(collection)) + script + collection


class TestCollection:

    def test_every_duration_doubles_and_nothing_else_changes(self):
        data = _collection(_animation(15, 7, 0), _animation(3))
        converted = camera30.convert_collection_bytes(data, 2)
        assert len(converted) == len(data)
        assert _durations(parse_camera_collection(converted)) == [30, 14, 0, 6]
        changed = [index for index in range(len(data)) if data[index] != converted[index]]
        frame_offsets = [frame.duration.offset for camera_set in parse_camera_collection(data).sets
                         for animation in camera_set.animations for block in animation.blocks
                         for frame in block.frames]
        assert all(any(offset <= index < offset + 2 for offset in frame_offsets) for index in changed)

    def test_factor_4_for_60_fps(self):
        converted = camera30.convert_collection_bytes(_collection(_animation(15, 7)), 4)
        assert _durations(parse_camera_collection(converted)) == [60, 28]

    def test_a_shared_animation_is_converted_once(self):
        data = bytearray(_collection(_animation(10, 5)))
        collection = parse_camera_collection(data)
        # point slot 1 at slot 0's animation, as vanilla idle monsters share one
        set_start = collection.set_pointers[0]
        struct.pack_into("<h", data, set_start + 2, struct.unpack_from("<h", data, set_start)[0])
        report = camera30.CameraConversionReport()
        converted = parse_camera_collection(camera30.convert_collection_bytes(bytes(data), 2, report))
        assert [frame.duration.get() for frame in converted.sets[0].animations[1].blocks[0].frames] == [20, 10]
        assert report.nb_keyframe == 2

    def test_a_block_over_2047_ticks_is_refused_and_nothing_changes(self):
        data = _collection(_animation(600, 500))
        collection = parse_camera_collection(data)
        with pytest.raises(camera30.CameraConversionError, match="2047"):
            camera30.convert_collection(collection, 2)
        assert bytes(collection.get_bytes()) == data

    def test_not_converting_is_byte_exact(self):
        data = _collection(_animation(15, 7), None, _animation(1))
        assert bytes(parse_camera_collection(data).get_bytes()) == data

    def test_idempotency_warning_heuristic(self):
        vanilla = parse_camera_collection(_collection(_animation(15, 7, 3, 9)))
        assert not camera30.collection_looks_converted(vanilla)
        converted = parse_camera_collection(camera30.convert_collection_bytes(vanilla.get_bytes(), 2))
        assert camera30.collection_looks_converted(converted)


class TestScript:

    def test_the_stage_script_waits_on_the_shot_and_is_unchanged(self, vm):
        timing = {command.address: command.timing for command in camera30.classify_script(vm, STAGE_SCRIPT)}
        assert timing[16] == "wait: shot"
        assert camera30.convert_script(vm, STAGE_SCRIPT, 2) == STAGE_SCRIPT
        original = run_camera_script_frames(vm, STAGE_SCRIPT, shot_length=lambda _i: 40)
        converted = run_camera_script_frames(vm, STAGE_SCRIPT, shot_length=lambda _i: 80)
        assert (original.frames, converted.frames) == (41, 81)

    def test_a_one_tick_wait_is_repeated_and_jumps_follow(self, vm):
        # var1 = 5; loop: wait; var1 -= 1; if var1 > 0 back to the wait; play 1; end
        script = bytes.fromhex("c105e501" "01" "c301c901e501" "c301e7f7" "0001" "02")
        assert [c.timing for c in camera30.classify_script(vm, script) if c.op_code == 1] == ["wait: tick"]
        report = camera30.CameraConversionReport()
        converted = camera30.convert_script(vm, script, 2, report)
        assert report.nb_wait_doubled == 1 and len(converted) == len(script) + 1
        original = run_camera_script_frames(vm, script)
        doubled = run_camera_script_frames(vm, converted)
        assert original.shots[0][0] * 2 == doubled.shots[0][0] == 10

    def test_a_straight_line_wait_is_repeated(self, vm):
        script = bytes.fromhex("0000" "01" "0001" "02")
        converted = camera30.convert_script(vm, script, 4)
        assert converted == bytes.fromhex("0000" "01010101" "0001" "02")

    def test_the_ease_duration_doubles_and_is_capped(self, vm):
        assert camera30.convert_script(vm, bytes.fromhex("040a02"), 2) == bytes.fromhex("041402")
        with pytest.raises(camera30.CameraConversionError, match="255"):
            camera30.convert_script(vm, bytes.fromhex("048002"), 2)


class TestTrack:

    def test_a_track_keeps_its_size_and_its_script(self, vm):
        data = _track(STAGE_SCRIPT, _collection(_animation(12, 4)))
        report = camera30.CameraConversionReport()
        converted = camera30.convert_track_bytes(vm, data, 2, report)
        assert len(converted) == len(data) and report.size_before == report.size_after
        _header, script, _padding, collection = read_track_parts(vm, converted)
        assert script == STAGE_SCRIPT and _durations(collection) == [24, 8]

    def test_a_refused_track_is_left_as_it_was(self, vm):
        track = CameraTrack.from_bytes(vm, _track(bytes.fromhex("048002"), _collection(_animation(12))))
        before = track.to_bytes()
        with pytest.raises(camera30.CameraConversionError):
            camera30.convert_track(vm, track, 2)
        assert track.to_bytes() == before

    def test_a_grown_script_grows_the_track(self, vm):
        data = _track(bytes.fromhex("0000" "01" "0001" "02"), _collection(_animation(12)))
        converted = camera30.convert_track_bytes(vm, data, 2)
        _header, script, _padding, _collection_part = read_track_parts(vm, converted)
        assert script == bytes.fromhex("0000" "0101" "0001" "02")
        assert struct.unpack_from("<H", converted, 6)[0] == len(converted)


@needs_files
class TestVanillaFiles:

    def test_every_stage_camera_converts_with_its_size(self, vm):
        from FF8GameData.battlestage.stagecamera import STAGE_CAMERA_OFFSET, camera_section
        for stage_id in STAGE_CAMERA_OFFSET:
            data = camera_section((BATTLE_PATH / f"a0stg{stage_id:03d}.x").read_bytes(), stage_id)
            converted = camera30.convert_track_bytes(vm, data, 2)
            assert len(converted) == len(data)
            before = _durations(read_track_parts(vm, data)[3])
            assert _durations(read_track_parts(vm, converted)[3]) == [2 * d for d in before]

    def test_every_model_camera_converts(self):
        from FF8GameData.dat.battlememory import section_offsets
        for path in sorted(BATTLE_PATH.glob("c0m*.dat")) + sorted(BATTLE_PATH.glob("d?c*.dat")):
            data = path.read_bytes()
            offsets = section_offsets(data)
            index = 6 if path.name.startswith("c0m") else 5
            if len(offsets) - 1 < index:
                continue
            section = data[offsets[index - 1]:offsets[index]]
            if len(section) < 6:
                continue
            converted = camera30.convert_collection_bytes(section, 2)
            assert _durations(parse_camera_collection(converted)) == [
                2 * d for d in _durations(parse_camera_collection(section))], path.name
