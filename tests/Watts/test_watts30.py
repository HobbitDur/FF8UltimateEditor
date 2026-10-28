"""Watts: r0win.dat converted for FFNx True30FPS (WattsManager.convert_to_real30, the GUI button
and the CLI convert-30fps command)."""
import pathlib
import shutil

import pytest

from FF8GameData.dat.sequencecommand import iter_command
from FF8GameData.dat.sequencevm import entity_sequence_vm
from FF8GameData.gamedata import GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
R0WIN = PROJECT_ROOT / "extracted_files" / "battle" / "r0win.dat"
R0WIN_MARK = "extracted_files/battle/r0win.dat"


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_anim_sequence_data()
    data.load_camera_sequence_data()
    return data


def _manager(game_data, path=R0WIN):
    from Watts.wattsmanager import WattsManager
    manager = WattsManager(game_data)
    manager.load_file(str(path))
    return manager


def _durations(collection):
    return [frame.duration.get() for camera_set in collection.sets for animation in camera_set.animations
            for block in animation.blocks for frame in block.frames]


def _stamps(vm, bytecode):
    for _address, op_code, parameters in iter_command(vm, bytecode):
        if op_code == 0x9F:
            return list(parameters[:-1])
    return []


@pytest.mark.ff8data(R0WIN_MARK)
def test_poses_sequences_and_camera_are_converted(game_data):
    vanilla, manager = _manager(game_data), _manager(game_data)
    report = manager.convert_to_real30()
    vm = entity_sequence_vm(game_data)
    for before, after in zip(vanilla.poses, manager.poses):
        assert after.anim_frame_count(after.body_anim) == 2 * before.anim_frame_count(before.body_anim) == 120
        if before.weapon_anim is not None:
            assert after.anim_frame_count(after.weapon_anim) == 120
        assert _stamps(vm, after.get_seq_bytecode()) == [2 * s for s in _stamps(vm, before.get_seq_bytecode())]
    assert _durations(manager.camera_collection) == [2 * d for d in _durations(vanilla.camera_collection)]
    assert manager.camera_setting == vanilla.camera_setting      # no tick in the r0win camera script
    assert report['camera_report'].nb_keyframe == 110
    assert report['warning_list'] == []                           # 187 KB: fits the staging buffer
    # the converted file reads back, and looks converted
    from Watts.wattsmanager import WattsManager
    again = WattsManager(game_data)
    again._parse(manager.to_bytes())
    assert again.looks_converted_to_real30() and not vanilla.looks_converted_to_real30()


@pytest.mark.ff8data(R0WIN_MARK)
def test_not_converting_stays_byte_exact(game_data):
    assert _manager(game_data).to_bytes() == R0WIN.read_bytes()


@pytest.mark.ff8data(R0WIN_MARK)
def test_a_refused_conversion_changes_nothing(game_data, monkeypatch):
    from FF8GameData.dat import camera30
    manager = _manager(game_data)
    before = manager.to_bytes()

    def refuse(*_args, **_kwargs):
        raise camera30.CameraConversionError("refused for the test")
    monkeypatch.setattr(camera30, "convert_track_bytes", refuse)
    with pytest.raises(ValueError, match="refused for the test"):
        manager.convert_to_real30()
    assert manager.to_bytes() == before


@pytest.mark.ff8data(R0WIN_MARK)
def test_cli_convert_30fps(tmp_path, capsys):
    from Cli.watts import WattsCliTool
    path = tmp_path / "r0win.dat"
    shutil.copy(R0WIN, path)
    tool = WattsCliTool()
    assert tool.execute(tool.build_parser().parse_args(["convert-30fps", "-i", str(path)])) == 0
    out = capsys.readouterr().out
    assert "Rinoa: body 120 frames" in out and "camera: 110 keyframe(s)" in out
    assert path.read_bytes() != R0WIN.read_bytes()


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.ff8data(R0WIN_MARK)
def test_widget_button(qapp, tmp_path):
    from Watts.wattswidget import WattsWidget
    path = tmp_path / "r0win.dat"
    shutil.copy(R0WIN, path)
    widget = WattsWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    assert not widget.convert_30fps_button.isEnabled()
    widget.load_file(str(path))
    assert widget.convert_30fps_button.isEnabled()
    report = widget.convert_to_30fps(confirm=False)
    assert report['poses'][0][1] == 120
    widget.save_file()
    assert path.read_bytes() != R0WIN.read_bytes()
    widget.deleteLater()
