"""WattsManager (r0win.dat) tests.

Synthetic tests build a minimal well-formed file in memory and run without game data.
Real-file tests are marked ff8data and are byte-exact against extracted_files.
"""
import pathlib
import shutil
import struct

import pytest

from Watts.wattsmanager import WattsManager, R0winPose, R0WIN_CHARACTERS, _build_offset_table

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"
R0WIN = BATTLE_DIR / "r0win.dat"

R0WIN_MARK = "extracted_files/battle/r0win.dat"


# --------------------------------------------------------------------- synthetic
def _synthetic_anim_block() -> bytes:
    # A single 0-frame animation: {u32 1; u32 8; u8 nb_frames=0} padded to 4
    return struct.pack("<II", 1, 8) + b"\x00\x00\x00\x00"


def _synthetic_seq_block() -> bytes:
    # {u16 1; u16 4} + byte-code "00 A9 E6 FF" (play anim 0, end, hold)
    return struct.pack("<HH", 1, 4) + bytes.fromhex("00a9e6ff")


def _build_synthetic() -> bytes:
    fanfare = _build_offset_table([b"AKAO" + b"\x00" * 12, b"AKAO" + b"\x11" * 12])
    camera = struct.pack("<4H", 2, 8, 12, 16) + b"\x01\x02\x00\x00" + struct.pack("<HH", 1, 4)
    pose_with_weapon = _build_offset_table(
        [_synthetic_anim_block(), _synthetic_seq_block(), _synthetic_anim_block()])
    pose_without_weapon = _build_offset_table(
        [_synthetic_anim_block(), _synthetic_seq_block()])
    sections = [fanfare, camera] + [pose_with_weapon] * 3 + [pose_without_weapon] \
        + [pose_with_weapon] + [pose_without_weapon]
    data = bytearray(struct.pack("<I", 8))
    position = 4 + 8 * 4 + 4
    for section in sections:
        data.extend(struct.pack("<I", position))
        position += len(section)
    data.extend(struct.pack("<I", position))
    for section in sections:
        data.extend(section)
    return bytes(data)


def test_synthetic_round_trip(tmp_path):
    original = _build_synthetic()
    source = tmp_path / "r0win.dat"
    source.write_bytes(original)
    manager = WattsManager()
    manager.load_file(str(source))
    assert manager.to_bytes() == original
    output = tmp_path / "out.dat"
    manager.save_file(str(output))
    assert output.read_bytes() == original


def test_synthetic_structure(tmp_path):
    source = tmp_path / "r0win.dat"
    source.write_bytes(_build_synthetic())
    manager = WattsManager()
    manager.load_file(str(source))
    assert len(manager.poses) == 6
    assert manager.poses[0].weapon_anim is not None
    assert manager.poses[3].weapon_anim is None  # Edea slot
    assert manager.poses[5].weapon_anim is None  # Kiros slot
    assert manager.poses[0].get_seq_bytecode() == bytes.fromhex("00a9e6ff")
    assert R0winPose.anim_frame_count(manager.poses[0].body_anim) == 0
    summary = manager.get_summary()
    assert [pose["name"] for pose in summary["poses"]] == \
        [character.name for character in R0WIN_CHARACTERS]


def test_synthetic_part_round_trip(tmp_path):
    source = tmp_path / "r0win.dat"
    source.write_bytes(_build_synthetic())
    manager = WattsManager()
    manager.load_file(str(source))
    original = manager.to_bytes()
    for part_key in manager.part_keys():
        manager.import_part(part_key, manager.export_part(part_key))
    assert manager.to_bytes() == original


def test_synthetic_import_validation(tmp_path):
    source = tmp_path / "r0win.dat"
    source.write_bytes(_build_synthetic())
    manager = WattsManager()
    manager.load_file(str(source))
    with pytest.raises(ValueError):
        manager.import_part("fanfare-seq", b"NOTAKAO!")
    with pytest.raises(ValueError):
        manager.import_part("camera", b"\x00" * 4)
    with pytest.raises(ValueError):
        manager.import_part("rinoa-seq", struct.pack("<HH", 2, 6) + b"\x00\x00")
    with pytest.raises(ValueError):
        manager.import_part("edea-weapon", _synthetic_anim_block())
    with pytest.raises(ValueError):
        manager.get_pose("Squall")  # no dedicated win pose in r0win.dat


def test_garbage_refused(tmp_path):
    source = tmp_path / "bad.dat"
    source.write_bytes(b"\x2a" * 64)
    manager = WattsManager()
    with pytest.raises(ValueError):
        manager.load_file(str(source))


def test_seq_bytecode_round_trip(tmp_path):
    source = tmp_path / "r0win.dat"
    source.write_bytes(_build_synthetic())
    manager = WattsManager()
    manager.load_file(str(source))
    pose = manager.poses[0]
    pose.set_seq_bytecode(pose.get_seq_bytecode())
    assert manager.to_bytes() == _build_synthetic()
    pose.set_seq_bytecode(bytes.fromhex("01a9e6ff"))
    assert manager.poses[0].get_seq_bytecode() == bytes.fromhex("01a9e6ff")


# --------------------------------------------------------------------- real file
@pytest.mark.ff8data(R0WIN_MARK)
def test_real_byte_exact_round_trip(tmp_path):
    original = R0WIN.read_bytes()
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    assert manager.to_bytes() == original
    output = tmp_path / "r0win.dat"
    manager.save_file(str(output))
    assert output.read_bytes() == original


@pytest.mark.ff8data(R0WIN_MARK)
def test_real_structure():
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    summary = manager.get_summary()
    assert summary["fanfare_bank_size"] == 126144  # AKAO instrument bank (PSX upload)
    assert summary["fanfare_seq_size"] == 4280  # AKAO score played by the music driver
    assert summary["camera_size"] == 2884
    assert summary["camera_sets"] == [8, 8, 8]
    assert manager.export_part("fanfare-seq")[:4] == b"AKAO"
    assert manager.export_part("fanfare-bank")[:4] == b"AKAO"
    for pose_info in summary["poses"]:
        assert pose_info["body_frames"] == 60
        if pose_info["weapon_size"] is not None:
            assert pose_info["weapon_frames"] == 60
    assert [pose["weapon_size"] is None for pose in summary["poses"]] == \
        [False, False, False, True, False, True]  # only Edea and Kiros are body-only


@pytest.mark.ff8data(R0WIN_MARK)
def test_real_fanfare_akao_id():
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    original = manager.to_bytes()
    assert manager.get_fanfare_akao_id() == 2  # PC song id 1, the victory fanfare
    manager.set_fanfare_akao_id(80)
    changed = manager.to_bytes()
    # Only the AKAO id byte moves; on PC it is the single byte of Section 1 the
    # game reads (Music_PlayFromAKAO plays song id = AKAO id - 1)
    diffs = [i for i, (a, b) in enumerate(zip(original, changed)) if a != b]
    assert manager.get_fanfare_akao_id() == 80
    assert len(diffs) == 1
    manager.set_fanfare_akao_id(2)
    assert manager.to_bytes() == original
    with pytest.raises(ValueError):
        manager.set_fanfare_akao_id(0)


@pytest.mark.ff8data(R0WIN_MARK)
def test_real_part_reimport_byte_exact(tmp_path):
    original = R0WIN.read_bytes()
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    for part_key in manager.part_keys():
        manager.import_part(part_key, manager.export_part(part_key))
    assert manager.to_bytes() == original


@pytest.mark.ff8data(R0WIN_MARK, "extracted_files/battle/d3c007.dat")
def test_real_wrong_skeleton_refused():
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    # Quistis' pose is 27 bones, Rinoa's slot decodes against 32: must be refused
    quistis_body = manager.export_part("quistis-body")
    with pytest.raises(ValueError):
        manager.import_part("rinoa-body", quistis_body)


@pytest.mark.ff8data(R0WIN_MARK, "extracted_files/battle/d4c009.dat")
def test_real_import_anim_from_dat(tmp_path):
    original = R0WIN.read_bytes()
    manager = WattsManager()
    manager.load_file(str(R0WIN))
    saved_body = manager.export_part("rinoa-body")
    manager.import_animation_from_dat("rinoa", "body",
                                      str(BATTLE_DIR / "d4c009.dat"), 2)
    changed = manager.to_bytes()
    assert changed != original
    # The rest of the file survives an offset-shifting edit: restore -> byte-exact
    manager.import_part("rinoa-body", saved_body)
    assert manager.to_bytes() == original
    with pytest.raises(ValueError):
        manager.import_animation_from_dat("rinoa", "body",
                                          str(BATTLE_DIR / "d4c009.dat"), 999)
