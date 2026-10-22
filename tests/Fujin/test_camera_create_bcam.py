"""Fujin cameras for FFNx (#1047): a camera created for an effect that starts none (items,
commands), saved as direct/exe/effect_NNN.bcam, and .bcam files read back - as a created camera or
as an override of the exe track - byte for byte."""
import struct
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from Fujin.cameraeffectmanager import (CAM_FFNX_FOLDER, CameraEffectManager, cam_file_name, cam_track_error)

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"
PHOENIX_DOWN, MEGA_PHOENIX, LIFE, CLASH = 5, 7, 35, 26


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(ROOT / "FF8GameData"))


def manager(game_data, exe=True):
    result = CameraEffectManager(game_data)
    if exe:
        result.load_exe(str(ROOT / EXE))
    return result


def test_minimal_camera_without_the_exe(game_data):
    cameras = manager(game_data, exe=False)
    assert not cameras.loaded and cameras.can_create(PHOENIX_DOWN) and not cameras.can_create(CLASH)
    track = cameras.create_track(MEGA_PHOENIX)
    data = cameras.cam_bytes(track)
    assert cam_track_error(data) is None and track.created and track.modified and not track.fits_exe
    assert cameras.script_code(track).split() == ["play(0)", "end_clear()"] and track.keyframe_count() == 2
    assert cameras.camera_kind(MEGA_PHOENIX) == "created" and not cameras.loaded
    assert "created camera" in cameras.hext_text()
    again = manager(game_data, exe=False)
    again.load_bcam(MEGA_PHOENIX, data)
    assert again.track(MEGA_PHOENIX).created and again.track(MEGA_PHOENIX).to_bytes() == data
    with pytest.raises(ValueError, match="cannot get a created camera"):
        cameras.create_track(CLASH)
    cameras.reset_track(MEGA_PHOENIX)                     # "Remove this camera"
    assert cameras.track(MEGA_PHOENIX) is None


@pytest.mark.ff8data(EXE)
def test_created_from_life_and_exe_override_round_trip(game_data):
    cameras = manager(game_data)
    track = cameras.create_track(PHOENIX_DOWN, LIFE)
    assert track.to_bytes() == cameras.track(LIFE).to_bytes()
    track.collection.sets[0].animations[0].blocks[0].frames[0].pos_x.set(1234)      # an edit
    created = cameras.cam_bytes(track)
    life = cameras.track(LIFE)
    frame = life.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.duration.set(frame.duration.get() + 3)
    cameras.set_script_code(life, cameras.script_code(life) + "\nend_clear()")       # grows: .bcam only
    override = cameras.cam_bytes(life)
    assert not life.fits_exe
    cameras.close()
    assert sorted(cameras.tracks) == [PHOENIX_DOWN]       # a created camera does not depend on the exe

    reread = manager(game_data)
    assert reread.load_bcam(PHOENIX_DOWN, created).to_bytes() == created
    overridden = reread.load_bcam(LIFE, override)
    assert overridden.to_bytes() == override and not overridden.created and not overridden.fits_exe
    same = manager(game_data)
    exe_bytes = same.track(LIFE).to_bytes()
    same.load_bcam(LIFE, exe_bytes)                       # the exe's own bytes: no change at all
    assert not same.track(LIFE).modified and same.track(LIFE).fits_exe


def test_bad_files_are_refused_with_the_reason(game_data, tmp_path):
    cameras = manager(game_data, exe=False)
    good = cameras.minimal_track_bytes()
    (tmp_path / cam_file_name(PHOENIX_DOWN)).write_bytes(good)
    (tmp_path / cam_file_name(MEGA_PHOENIX)).write_bytes(good + b"\0\0")              # size field != file
    (tmp_path / "effect_040.bcam").write_bytes(struct.pack("<4H", 3, 8, 12, len(good)) + good[8:])
    (tmp_path / "phoenix.bcam").write_bytes(good)
    loaded, refused = cameras.load_bcam_files(sorted(str(path) for path in tmp_path.iterdir()))
    reasons = {Path(path).name: reason for path, reason in refused}
    assert loaded == [PHOENIX_DOWN]
    assert "size does not match" in reasons[cam_file_name(MEGA_PHOENIX)]
    assert "bad header" in reasons["effect_040.bcam"]
    assert "not named effect_NNN.bcam" in reasons["phoenix.bcam"]
    assert cameras.track(MEGA_PHOENIX) is None


@pytest.mark.ff8data(EXE)
def test_fujin_creates_saves_and_reimports_a_camera(qapp, tmp_path, monkeypatch):
    from Fujin.fujinwidget import FujinWidget
    monkeypatch.setattr("Fujin.cameraeffectwidget.QMessageBox.warning", lambda *args: None)
    fujin = FujinWidget()
    fujin.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    fujin.select_effect(CLASH)
    assert not fujin.camera_editor.create_box.isVisibleTo(fujin.camera_editor)
    assert "No camera can be created here" in fujin.camera_editor.info_label.text()
    fujin.select_effect(PHOENIX_DOWN)
    editor = fujin.camera_editor
    assert fujin.tabs.isTabEnabled(1) and editor.create_box.isVisibleTo(editor)
    assert editor.create_source.currentData() == LIFE                   # suggested for Phoenix Down
    track = editor.create_camera()
    assert track is not None and editor.manager.camera_kind(PHOENIX_DOWN) == "created"
    assert "(.bcam camera)" in fujin.effect_list.currentItem().text() and "Created camera" in fujin.camera_note.text()
    assert fujin.can_save_folder() and "Camera 5 (created)" in fujin.changes.toPlainText()
    assert fujin.save_files(str(tmp_path))
    written = tmp_path / CAM_FFNX_FOLDER / cam_file_name(PHOENIX_DOWN)
    assert written.read_bytes() == track.to_bytes()

    other = FujinWidget()
    assert all("folder" not in label for label, _callback in other.import_entries())   # files one by one
    loaded, refused = other._import_bcam([str(written)])
    assert loaded == [PHOENIX_DOWN] and not refused
    assert other.camera_editor.manager.track(PHOENIX_DOWN).to_bytes() == written.read_bytes()
    assert other.current_effect == PHOENIX_DOWN and other.tabs.currentIndex() == 1

    # Import previous reloads the imported .bcam files, without changing the selected effect
    from Fujin.cameraeffectwidget import CAM_FOLDER_KEY
    again = FujinWidget(file_registry=other.file_registry)
    again.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    source = next(source for source in again.auto_import_sources() if source.key == CAM_FOLDER_KEY)
    assert source.find_paths(again.file_registry) == [str(written)]
    source.loader(source.find_paths(again.file_registry))
    assert again.camera_editor.manager.track(PHOENIX_DOWN).to_bytes() == written.read_bytes()
