"""Fujin's Camera effect editor, data side: the effect camera tracks inside the FF8 exe."""
import json
import struct

import pytest

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

EXE = "extracted_files/FF8_EN.exe"
CURE, LIFE, POTION, PHOENIX_DOWN, LEVIATHAN = 1, 35, 50, 5, 6


@pytest.fixture(scope="module")
def manager():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    loaded = CameraEffectManager(GameData("FF8GameData"))
    loaded.load_exe(EXE)
    return loaded


@pytest.fixture
def fresh_manager():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    loaded = CameraEffectManager(GameData("FF8GameData"))
    loaded.load_exe(EXE)
    return loaded


def test_track_table():
    """effect_camera.json: one track per effect, every language located."""
    with open(RESOURCES_JSON_FOLDER / "effect_camera.json", encoding="utf-8") as file:
        data = json.load(file)
    tracks = data["tracks"]
    assert len(tracks) == 221
    assert len({entry["effect_id"] for entry in tracks}) == 221
    assert len({entry["eng_address"] for entry in tracks}) == 221  # no two effects share a track
    cure = next(entry for entry in tracks if entry["effect_id"] == CURE)
    assert (cure["label"], cure["eng_address"], cure["size"]) == ("MAG001_CURE_cameraAnim", "0x16417C8", "0x7B0")
    for entry in tracks:
        assert all(f"{language}_offset" in entry and f"{language}_push_offset" in entry
                   for language in ("fr", "de", "it", "es"))
        assert entry["label"].startswith(f"MAG{entry['effect_id']:03d}_") and entry["label"].endswith("_cameraAnim")
    assert PHOENIX_DOWN not in {entry["effect_id"] for entry in tracks}  # the item effect has no camera
    assert LEVIATHAN in data["file_camera_effects"]


def test_camera_script_op_codes():
    from FF8GameData.gamedata import GameData
    game_data = GameData("FF8GameData")
    game_data.load_camera_sequence_data()
    op_codes = {info["op_code"] for info in game_data.camera_sequence_data_json["op_code_info"]}
    assert set(range(0x0A)) <= op_codes                     # camera op codes 00-09
    assert set(range(0xC0, 0xF4)) <= op_codes               # the shared VM op codes


@pytest.mark.ff8data(EXE)
def test_every_track_reads_and_rebuilds(manager):
    assert manager.language_name == "EN" and len(manager.tracks) == 221
    for track in manager.tracks.values():
        assert track.to_bytes() == track.original and not track.modified
        assert "Unknown" not in manager.script_text(track)
    assert sum(track.keyframe_count() for track in manager.tracks.values()) == 8947
    assert manager.track(CURE).same_as == [POTION]           # identical copies, not shared data
    assert manager.track(PHOENIX_DOWN) is None and manager.camera_kind(PHOENIX_DOWN) == "none"
    assert manager.camera_kind(LEVIATHAN) == "file"


@pytest.mark.ff8data(EXE)
def test_script_code_round_trip(manager):
    for track in manager.tracks.values():
        script = track.script
        manager.set_script_code(track, manager.script_code(track))
        assert track.script == script


@pytest.mark.ff8data(EXE)
def test_longer_script_grows_the_track_out_of_the_exe(fresh_manager):
    from Fujin.cameraeffectmanager import cam_track_error
    track = fresh_manager.track(LIFE)
    assert track.fits_exe
    fresh_manager.set_script_code(track, fresh_manager.script_code(track) + "\nend()")
    assert track.modified and not track.fits_exe and track.current_size > track.size
    assert cam_track_error(track.to_bytes()) is None          # a .cam can use it
    assert fresh_manager.resized_tracks() == [track]
    hext = fresh_manager.hext_text()                           # the exe cannot: listed, no bytes
    assert "Effect 35 Life: resized" in hext and " = " not in hext


@pytest.mark.ff8data(EXE)
def test_shorter_script_is_filled_up(fresh_manager):
    track = fresh_manager.track(LIFE)
    room = track.script_room
    assert fresh_manager.set_script_code(track, "end()") == room - 1
    assert len(track.script) == room and len(track.to_bytes()) == track.size
    filler = track.script[1:]
    if len(filler) % 2:                                       # odd: one more end() first
        assert filler[:1] == b"\x01"
        filler = filler[1:]
    assert filler == b"\x09\x00" * (len(filler) // 2)        # then nop(0)s
    assert fresh_manager.script_code(track).splitlines()[0] == "end()"


@pytest.mark.ff8data(EXE)
def test_hext_cannot_change_a_track_size(fresh_manager):
    life, cure = fresh_manager.track(LIFE), fresh_manager.track(CURE)
    keyframe_byte = cure.address + len(cure.original) - 2 - 0x400000
    size_field = life.address + 6 - 0x400000
    # a keyframe edit on Cure plus a size change on Life: refused as a whole, nothing applied
    with pytest.raises(ValueError, match="header"):
        fresh_manager.apply_hext_text(f"+400000\n{keyframe_byte:X} = 7F\n{size_field:X} = FF 00\n")
    assert not fresh_manager.modified_tracks()
    fresh_manager.set_script_code(life, fresh_manager.script_code(life) + "\nend()")  # resized
    with pytest.raises(ValueError, match="resized"):
        fresh_manager.apply_hext_text(f"+400000\n{life.address + 8 - 0x400000:X} = 02\n")


@pytest.mark.ff8data(EXE)
def test_hext_of_an_edit_and_back(fresh_manager):
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    track = fresh_manager.track(LIFE)
    frame = track.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.pos_x.set(frame.pos_x.get() + 100)
    assert [edited.effect_id for edited in fresh_manager.modified_tracks()] == [LIFE]
    hext = fresh_manager.hext_text()
    assert "for the EN FF8 exe" in hext and "+400000" in hext
    lines = [line for line in hext.splitlines() if " = " in line]
    address = int(lines[0].split(" = ")[0], 16) + 0x400000
    assert track.address <= address < track.address + track.size

    reopened = CameraEffectManager(GameData("FF8GameData"))
    reopened.load_exe(EXE)
    assert reopened.apply_hext_text(hext) == 1
    assert reopened.track(LIFE).to_bytes() == track.to_bytes()

    with pytest.raises(ValueError, match="made for the FR exe"):
        reopened.apply_hext_text(hext.replace("for the EN FF8 exe", "for the FR FF8 exe"))
    with pytest.raises(ValueError, match="not inside a camera track"):
        reopened.apply_hext_text("+400000\n100 = 00\n")

    fresh_manager.reset_track(LIFE)
    assert not fresh_manager.modified_tracks()


@pytest.mark.ff8data(EXE)
def test_pushes_point_at_the_tracks(manager):
    with open(EXE, "rb") as file:
        exe = file.read()
    for track in manager.tracks.values():
        operand = track.push_operand - 0x400000
        assert exe[operand - 1] == 0x68                       # push imm32
        assert struct.unpack_from("<I", exe, operand)[0] == track.address
