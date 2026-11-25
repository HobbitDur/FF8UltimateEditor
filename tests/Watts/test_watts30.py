"""Watts: r0win.dat converted for FFNx True30FPS (WattsManager.convert_to_real30, the GUI button
and the CLI convert-30fps command)."""
import pathlib
import shutil

import pytest

from FF8GameData.dat.sequencecommand import iter_command
from FF8GameData.dat.sequencevm import entity_sequence_vm
from FF8GameData.gamedata import GameData
from FF8GameData.monsterdata import AnimationSection

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
def test_weapons_stay_in_the_hand_on_the_in_betweens(game_data):
    """Selphie's nunchaku left her hand by 0.56 vertex units on in-betweens of her victory pose
    (the weapon blended on its own): pinned, only the weapon roots of in-betweens move."""
    import numpy as np
    from FF8GameData.dat import weapongrip
    blended, pinned = _manager(game_data), _manager(game_data)
    blended.convert_to_real30()
    pinned.convert_to_real30()
    report_list = pinned.pin_weapon_grips(R0WIN.parent)
    by_name = {report['name']: report for report in report_list}
    assert set(by_name) == {"Rinoa", "Quistis", "Irvine", "Selphie"}
    selphie = by_name["Selphie"]
    assert selphie['worst_before'] > 0.5 and selphie['nb_pinned'] > 20
    assert max(selphie['worst_after'].values()) < 0.05
    for report in report_list:
        assert report['skipped'] is None and max(report['worst_after'].values()) < 0.06
    for before, after in zip(blended.poses, pinned.poses):
        assert after.body_anim == before.body_anim and after.seq_block == before.seq_block
        if before.weapon_anim is None:
            continue
        frames = []
        for block in (before.weapon_anim, after.weapon_anim):
            section = AnimationSection()
            section.analyze(bytes(block), pinned.synthetic_bone_section(before.character.weapon_bones))
            frames.append(section.animations[0].frames)
        for index, (old, new) in enumerate(zip(*frames)):
            rotation = [[angle.get_rotate_raw() for angle in bone] for bone in old.rotation_vector_data]
            assert rotation == [[angle.get_rotate_raw() for angle in bone] for bone in new.rotation_vector_data]
            root_old = np.array([position.get_pos_world() for position in old.position[:3]])
            root_new = np.array([position.get_pos_world() for position in new.position[:3]])
            if index % 2 == 0:
                assert np.allclose(root_old, root_new)       # original frames untouched
    assert weapongrip.MAX_GRIP_SPREAD >= by_name["Quistis"]['grip'].spread


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
