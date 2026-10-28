"""Fujin: battle effect cameras converted for FFNx True30FPS - the 221 exe tracks (Save's .hext and
Export all .bcam), .bcam files read back, the camera of a GF cinematic MAG file, and the CLI."""
import struct
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.dat import camera30
from FF8GameData.dat.cameratrack import read_track_parts
from FF8GameData.gamedata import GameData
from Fujin.cameraeffectmanager import CameraEffectManager, cam_file_name, cam_track_error

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"
MAG230 = "extracted_files/magic/MAG230_B.00"
CURE = 1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(ROOT / "FF8GameData"))


def _durations(collection):
    return [frame.duration.get() for camera_set in collection.sets for animation in camera_set.animations
            for block in animation.blocks for frame in block.frames]


@pytest.mark.ff8data(EXE)
def test_every_exe_track_converts_in_its_room(game_data):
    manager = CameraEffectManager(game_data)
    manager.load_exe(str(ROOT / EXE))
    result = manager.convert_tracks_to_real30()
    assert len(result) == 221 and all(report is not None for _e, report, _m in result)
    assert len(manager.modified_tracks()) == 221 and manager.resized_tracks() == []
    for track in manager.tracks.values():
        assert _durations(track.collection) == [2 * d for d in _durations(read_track_parts(manager.vm, track.original)[3])]
    assert "#Effect 1 " in manager.hext_text()
    files = manager.all_cam_files()
    assert len(files) == 221 and all(cam_track_error(data) is None for _name, data in files)
    # converting again is warned about
    assert all("already converted" in message for _e, _r, message in manager.convert_tracks_to_real30([CURE]))


@pytest.mark.ff8data(EXE)
def test_a_bcam_read_back_converts_too(game_data, tmp_path):
    manager = CameraEffectManager(game_data)
    manager.load_exe(str(ROOT / EXE))
    path = tmp_path / cam_file_name(CURE)
    path.write_bytes(manager.track(CURE).to_bytes())
    other = CameraEffectManager(game_data)
    assert other.load_bcam_files([str(path)]) == ([CURE], [])
    (effect_id, report, _message), = other.convert_tracks_to_real30()
    assert effect_id == CURE and report.nb_keyframe
    assert cam_track_error(other.cam_bytes(other.track(CURE))) is None


@pytest.mark.ff8data(EXE)
def test_widget_buttons(qapp, tmp_path, monkeypatch):
    from Fujin.fujinwidget import FujinWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    fujin = FujinWidget()
    editor = fujin.camera_editor
    editor.exe_binding.open_path(str(ROOT / EXE))
    result = editor.convert_all_to_30fps(confirm=False)
    assert len(result) == 221 and editor.has_changes() and fujin.can_save_folder()
    written = editor.export_all_cam(str(tmp_path))
    assert len(written) == 221 and (tmp_path / cam_file_name(CURE)).exists()


@pytest.mark.ff8data(MAG230)
def test_mag_camera_converts_in_its_room(game_data, tmp_path):
    game_data.load_camera_sequence_data()
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    vm = camera_sequence_vm(game_data)
    data = (ROOT / MAG230).read_bytes()
    offset = camera30.mag_camera_offset(data)
    size = struct.unpack_from("<H", data, offset + 6)[0]
    converted = camera30.convert_mag_camera(vm, data, 2)
    assert len(converted) == len(data)
    assert converted[:offset] == data[:offset] and converted[offset + size:] == data[offset + size:]
    before = read_track_parts(vm, data[offset:offset + size])[3]
    after = read_track_parts(vm, converted[offset:offset + size])[3]
    assert _durations(after) == [2 * d for d in _durations(before)]


@pytest.mark.ff8data(MAG230)
def test_mag_camera_button(qapp, tmp_path):
    from Fujin.magdocument import MagDocument
    from Fujin.magsectionwidget import MagSectionEditor
    path = tmp_path / "MAG230_B.00"
    path.write_bytes((ROOT / MAG230).read_bytes())
    manager = MagDocument()
    manager.load_file(str(path))
    section = next(s for s in manager.document.sections if s.kind == "camera")
    editor = MagSectionEditor(manager, section)
    assert editor.convert_camera_to_30fps()
    assert manager.modified and len(manager.data) == len((ROOT / MAG230).read_bytes())


@pytest.mark.ff8data(EXE, MAG230)
def test_cli_camera_30fps(tmp_path):
    from Cli.fujin import FujinCliTool
    tool = FujinCliTool()
    args = tool.build_parser().parse_args([
        "camera-30fps", "--exe", str(ROOT / EXE), "--bcam-dir", str(tmp_path / "bcam"),
        "--hext", str(tmp_path / "cam.hext"), "--mag", str(ROOT / MAG230), "--mag-output-dir", str(tmp_path / "mag")])
    assert tool.execute(args) == 0
    assert len(list((tmp_path / "bcam").glob("effect_*.bcam"))) == 221
    assert (tmp_path / "cam.hext").read_text(encoding="utf-8").startswith("#Fujin camera effect patch")
    assert (tmp_path / "mag" / "MAG230_B.00").read_bytes() != (ROOT / MAG230).read_bytes()
