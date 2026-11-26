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
    (the weapon blended on its own): pinned, only the in-betweens move, the original frames stay."""
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
        for old, new in list(zip(*frames))[0::2]:            # original frames untouched
            # (an angle may come back whole turns away: the file stores each frame's angles as
            # steps from the frame before, and a re-posed in-between steps another way round)
            rotation = [[int(angle.get_rotate_raw()) % 4096 for angle in bone] for bone in old.rotation_vector_data]
            assert rotation == [[int(angle.get_rotate_raw()) % 4096 for angle in bone]
                                for bone in new.rotation_vector_data]
            root_old = np.array([position.get_pos_world() for position in old.position[:3]])
            root_new = np.array([position.get_pos_world() for position in new.position[:3]])
            assert np.allclose(root_old, root_new)
    assert weapongrip.MAX_GRIP_SPREAD >= by_name["Quistis"]['grip'].spread


def _nunchaku_in_hand_space(game_data, manager, folder):
    """Selphie's nunchaku vertices on every frame of her pose, seen from her hand (the body bone
    of the grip): (F, V, 3)."""
    import numpy as np
    from FF8GameData.dat import weapongrip
    pose = manager.get_pose("Selphie")
    models = manager._pose_models(pose, folder)
    body, weapon, grip = models['body'], models['weapon'], models['grip']
    vertex_list = [(vertex_data.bone_id, vertex.get_list()) for obj in weapon.geometry_data.object_data
                   for vertex_data in obj.vertices_data for vertex in vertex_data.vertices]
    bone_ids = np.array([bone for bone, _ in vertex_list])
    points = np.array([point for _, point in vertex_list], dtype=float) * weapongrip._FLIP

    def frames(block, model):
        section = AnimationSection()
        section.analyze(bytes(block), model.bone_data)
        return section.animations[0].frames
    result = []
    for body_frame, weapon_frame in zip(frames(pose.body_anim, body), frames(pose.weapon_anim, weapon)):
        rotation_w, translation_w = weapongrip._bone_frames(weapon_frame, weapon.bone_data.bones)
        rotation_b, translation_b = weapongrip._bone_frames(body_frame, body.bone_data.bones)
        world = (np.einsum('nij,nj->ni', rotation_w[bone_ids], points) + translation_w[bone_ids]
                 + weapongrip.ROOT_TO_VERTEX * (weapongrip._root(weapon_frame) - weapongrip._root(body_frame)))
        result.append((world - translation_b[grip.body_bone]) @ rotation_b[grip.body_bone])
    return np.array(result)


@pytest.mark.ff8data(R0WIN_MARK, "extracted_files/battle/d5c011.dat", "extracted_files/battle/d5w028.dat",
                     "extracted_files/battle/d7c016.dat", "extracted_files/battle/d9c019.dat")
def test_in_betweens_blended_on_the_real_skeletons(game_data):
    """On neutral bones each bone blended on its own: Selphie's nunchaku chain turns undone by
    the next bone were drawn half-way round, the free stick flung out straight or hanging down for
    1/30 s, 14.8 vertex units from the vanilla mid-point (filmed). On her real skeleton, with her
    snaps held whole as the battle models do, it stays near the vanilla path; still two in-betweens
    jumped for 1/30 s seen from her hand (filmed: a link sent the long way round, a snap held still
    while the hand moved on), each now takes the pose between its neighbours
    (weapongrip.smooth_in_betweens): no in-between jumps more than vanilla's own frames do."""
    import numpy as np
    folder = R0WIN.parent
    vanilla, neutral, real = _manager(game_data), _manager(game_data), _manager(game_data)
    neutral.convert_to_real30()
    report = real.convert_to_real30(models_folder=folder)
    assert report['warning_list'] == []                          # every character's models found
    real.pin_weapon_grips(folder)

    def worst_in_between(manager):
        before, after = _nunchaku_in_hand_space(game_data, vanilla, folder), \
            _nunchaku_in_hand_space(game_data, manager, folder)
        assert np.allclose(after[0::2][:len(before)], before[:len(after[0::2])], atol=1e-3)
        middle = (before[:-1] + before[1:]) / 2
        return float(np.linalg.norm(after[1::2][:len(middle)] - middle, axis=2).max())
    assert worst_in_between(neutral) > 10
    assert worst_in_between(real) < 2.5
    # a jump for one frame: the frame off the middle of its two neighbours (vertex units)
    poses = _nunchaku_in_hand_space(game_data, real, folder)
    jump = np.linalg.norm(poses[2:] - 2 * poses[1:-1] + poses[:-2], axis=2).max(axis=1)
    in_between_jump, original_jump = jump[0::2].max(), jump[1::2].max()     # jump[i] is frame i + 1
    assert in_between_jump < original_jump and in_between_jump < 5


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
