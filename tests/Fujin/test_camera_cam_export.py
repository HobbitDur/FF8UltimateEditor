"""Fujin's .cam export: one effect's camera track as the FFNx effect_NNN.cam file
(julianxhokaxhiu/FFNx#1047, docs/ff8/mods/effect_camera.md)."""
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Fujin.cameraeffectmanager import cam_file_name, cam_track_error

EXE = "extracted_files/FF8_EN.exe"
LIFE, PHOENIX_DOWN = 35, 5


def minimal_track():
    """Header, an end_clear script with its padding byte, a 1-set collection of 8 empty slots."""
    collection = struct.pack("<3H", 1, 6, 6 + 16) + b"\xFF\xFF" * 8
    script = b"\x02\x00"
    size = 8 + len(script) + len(collection)
    return struct.pack("<4H", 2, 8, 8 + len(script), size) + script + collection


def test_cam_name_and_ffnx_checks():
    assert cam_file_name(1) == "effect_001.cam" and cam_file_name(345) == "effect_345.cam"
    track = minimal_track()
    assert cam_track_error(track) is None
    assert cam_track_error(b"") == "file too small"
    assert cam_track_error(track[:6]) == "file too small"
    assert cam_track_error(b"\x03" + track[1:]) == "bad header"                    # pointer count
    assert cam_track_error(track + b"\0") == "header size does not match the file size"
    bad = bytearray(track)
    struct.pack_into("<H", bad, 4, 8)
    assert cam_track_error(bytes(bad)) == "keyframe offset out of range"
    bad = bytearray(track)
    struct.pack_into("<H", bad, 10, 0)
    assert cam_track_error(bytes(bad)) == "bad keyframe set count"
    bad = bytearray(track)
    struct.pack_into("<H", bad, 14, 20)
    assert cam_track_error(bytes(bad)) == "keyframe collection size does not match the file size"
    bad = bytearray(track)
    struct.pack_into("<H", bad, 12, 2)
    assert cam_track_error(bytes(bad)) == "keyframe set offset out of range"


@pytest.mark.ff8data(EXE)
def test_every_track_exports_as_a_valid_cam():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    manager = CameraEffectManager(GameData("FF8GameData"))
    manager.load_exe(EXE)
    for track in manager.tracks.values():
        assert manager.cam_bytes(track) == track.original   # the exe's bytes, as they are
    life = manager.track(LIFE)
    frame = life.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.pos_x.set(frame.pos_x.get() + 100)
    edited = manager.cam_bytes(life)
    assert edited != life.original and cam_track_error(edited) is None   # edits go into the file


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data(EXE)
def test_export_button_writes_the_selected_effect(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    editor = fujin.camera_editor
    assert not editor.export_cam_button.isEnabled() or editor.manager.track(1) is None
    editor.exe_binding.open_path(EXE)
    editor.select_effect(LIFE)
    assert editor.export_cam_button.isEnabled()
    path = tmp_path / cam_file_name(LIFE)
    assert editor.export_cam(str(path))
    assert path.read_bytes() == editor.manager.cam_bytes(editor.manager.track(LIFE))
    assert fujin.file_registry.last_folder("camera effect .cam") == str(tmp_path)
    editor.select_effect(PHOENIX_DOWN)                       # no camera track to export
    assert not editor.export_cam_button.isEnabled()
    assert not editor.export_cam(str(tmp_path / cam_file_name(PHOENIX_DOWN)))
    assert not (tmp_path / cam_file_name(PHOENIX_DOWN)).exists()
