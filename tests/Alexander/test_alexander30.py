"""Alexander: the battle stage cameras converted for FFNx True30FPS (manager, Camera tab button, CLI)."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.battlestage.stagecamera import STAGE_CAMERA_OFFSET, camera_section

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE = PROJECT_ROOT / "extracted_files" / "battle"
STAGES = ["a0stg006.x", "a0stg137.x"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def vm():
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_camera_sequence_data()
    return camera_sequence_vm(game_data)


def _durations(vm, data, stage_id):
    from FF8GameData.dat.cameratrack import read_track_parts
    collection = read_track_parts(vm, camera_section(data, stage_id))[3]
    return [frame.duration.get() for camera_set in collection.sets for animation in camera_set.animations
            for block in animation.blocks for frame in block.frames]


def _check_converted(vm, original: bytes, converted: bytes, stage_id: int):
    assert len(converted) == len(original)
    assert _durations(vm, converted, stage_id) == [2 * d for d in _durations(vm, original, stage_id)]
    start = STAGE_CAMERA_OFFSET[stage_id]
    end = start + len(camera_section(original, stage_id))
    assert converted[:start] == original[:start] and converted[end:] == original[end:]


@pytest.mark.ff8data(*[f"extracted_files/battle/{name}" for name in STAGES])
def test_manager_converts_every_opened_stage(vm, tmp_path):
    from Alexander.alexandermanager import AlexanderManager
    paths = []
    for name in STAGES:
        shutil.copy(BATTLE / name, tmp_path / name)
        paths.append(str(tmp_path / name))
    manager = AlexanderManager()
    manager.open_files(paths)
    manager.load_stage_file(paths[0])
    result = manager.convert_cameras_to_real30()
    assert [report is not None for _path, report, _message in result] == [True, True]
    assert sorted(manager.modified_camera_paths()) == sorted(paths)
    for path in paths:
        manager.save_camera(path)
    for name, path in zip(STAGES, paths):
        stage_id = int(name[5:8])
        _check_converted(vm, (BATTLE / name).read_bytes(), pathlib.Path(path).read_bytes(), stage_id)
        assert not pathlib.Path(path).with_suffix(".hext").exists()   # same size: no geometry move
    # a second conversion is warned about
    again = AlexanderManager()
    again.open_files(paths)
    assert all("already converted" in message for _p, _r, message in again.convert_cameras_to_real30())


@pytest.mark.ff8data("extracted_files/battle/a0stg006.x")
def test_cli_convert_30fps(vm, tmp_path):
    from Cli.alexander import AlexanderCliTool
    tool = AlexanderCliTool()
    args = tool.build_parser().parse_args(["convert-30fps", "-i", str(BATTLE / "a0stg006.x"),
                                           "-o", str(tmp_path)])
    assert tool.execute(args) == 0
    _check_converted(vm, (BATTLE / "a0stg006.x").read_bytes(), (tmp_path / "a0stg006.x").read_bytes(), 6)


@pytest.mark.ff8data("extracted_files/battle/a0stg006.x")
def test_camera_tab_button(qapp, vm, tmp_path, monkeypatch):
    from Alexander.alexanderwidget import AlexanderWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    stage = tmp_path / "a0stg006.x"
    shutil.copy(BATTLE / "a0stg006.x", stage)
    widget = AlexanderWidget()
    widget.open_files([str(stage)])
    assert not widget.has_unsaved_changes()
    result = widget.convert_cameras_to_30fps(confirm=False)
    assert result[0][1] is not None and widget.has_unsaved_changes()
    assert widget.camera_editor.track is widget.manager.camera_track
    widget.save_folder()
    _check_converted(vm, (BATTLE / "a0stg006.x").read_bytes(), stage.read_bytes(), 6)
    widget.deleteLater()
