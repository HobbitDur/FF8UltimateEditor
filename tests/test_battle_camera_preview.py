"""Battle-coordinate regressions, including the disappearing Squall F3/F4 blocks."""
from pathlib import Path
from types import SimpleNamespace
import math
import struct

import numpy as np
import pytest

from FF8GameData.dat.battlecamera import (BattleCameraContext, CameraActor, CameraPose,
                                         play_camera_animation, projection_frustum)
from FF8GameData.dat.cameracollection import CameraCollection


class Field:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def frame(duration, eye, target, pos_mode=0xFB, look_mode=0xFB):
    result = SimpleNamespace(duration=Field(duration), pos_interp_mode=Field(pos_mode),
                             look_interp_mode=Field(look_mode))
    for prefix, xyz in [('pos_', eye), ('look_', target)]:
        for axis, value in zip(('z', 'x', 'y'), xyz):
            setattr(result, prefix + axis, Field(value))
    return result


def block(frames, cw=0x3C1, fov=(512, 512), roll=(0, 0)):
    return SimpleNamespace(frames=frames, control_word=cw,
                           fov_start=Field(fov[0]), fov_end=Field(fov[1]),
                           roll_start=Field(roll[0]), roll_end=Field(roll[1]))


def test_previous_view_block_holds_position_instead_of_camera_at_origin():
    first = block([frame(3, (100, -500, -2000), (0, -300, 100))])
    hold = block([frame(4, (0, 0, 0), (0, 0, 0), 0xF3, 0xF4)])
    poses = play_camera_animation(SimpleNamespace(blocks=[first, hold]), BattleCameraContext())
    assert len(poses) == 7
    assert all(p.eye == poses[2].eye and p.target == poses[2].target for p in poses[3:])
    assert all(np.linalg.norm(np.array(p.eye) - p.target) > 100 for p in poses)


def test_layout_one_resolves_previous_view_once_for_all_keyframes():
    start = CameraPose((100, -500, -1000), (0, 0, 0))
    animation = SimpleNamespace(blocks=[block([
        frame(2, (0, 0, 0), (0, 0, 0), 0xF3, 0xF4),
        frame(1, (100, 0, 0), (0, 0, 0), 0xF3, 0xF4)])])
    poses = play_camera_animation(animation, BattleCameraContext(initial=start))
    assert [p.eye[0] for p in poses] == [100, 150, 200]


def test_live_modes_follow_actor_but_snapshot_layout_does_not():
    actor = CameraActor(anchor=lambda selector, tick: (tick * 100, 0, 0))
    context = BattleCameraContext(caster=actor)
    f = frame(3, (0, 0, -1000), (0, 0, 0), 0x90, 0x90)
    live = play_camera_animation(SimpleNamespace(blocks=[block([f], cw=0x3C0)]), context)
    frozen = play_camera_animation(SimpleNamespace(blocks=[block([f])]), context)
    assert [p.eye[0] for p in live] == [0, 100, 200]
    assert [p.eye[0] for p in frozen] == [0, 0, 0]


def test_target_and_midpoint_modes_use_actual_opponent_placement():
    caster = CameraActor(position=(100, 0, 0), scale=.5)
    target = CameraActor(position=(100, 0, 5000), yaw=math.pi, scale=.25)
    context = BattleCameraContext(caster, target)
    np.testing.assert_allclose(context.resolve((0, 0, 0), 0xA0, context.initial, 0), target.position)
    np.testing.assert_allclose(context.resolve((0, 0, 0), 0xF5, context.initial, 0), (100, 0, 2500))
    np.testing.assert_allclose(context.resolve((1000, 0, 0), 0xF5, context.initial, 0), (1100, 0, 2500))
    target.position = (100, 0, 10000)
    np.testing.assert_allclose(context.resolve((1000, 0, 0), 0xF5, context.initial, 0), (2100, 0, 5000))


def test_lens_roll_and_last_keyframe_hold_are_preserved():
    animation = SimpleNamespace(blocks=[block([
        frame(4, (0, 0, -1000), (0, 0, 0)), frame(2, (400, 0, -1000), (0, 0, 0))],
        fov=(256, 512), roll=(0, 1024))])
    poses = play_camera_animation(animation, BattleCameraContext())
    assert [p.eye[0] for p in poses] == [0, 100, 200, 300, 400, 400]
    assert poses[-1].projection == 512 and poses[-1].roll == 1024
    assert poses[0].projection == pytest.approx(256 + 256 / 6)
    # Higher projection H narrows the viewing frustum (the old tooltip said the reverse).
    assert projection_frustum(512)[1] < projection_frustum(256)[1]


def test_encounter_picker_filters_monsters_and_shares_read_only_scene(tmp_path):
    from Common.fileregistry import FileRegistry
    from Ifrit.IfritCameraSeq.encounterpreview import EncounterPicker
    raw = bytearray(256)
    for i, com_id in enumerate((71, 145)):
        raw[i * 128 + 7] = 0x80
        raw[i * 128 + 0x38] = com_id + 16
    path = tmp_path / 'scene.out'
    path.write_bytes(raw)
    registry = FileRegistry()
    registry.open_file('scene.out', str(path))
    enemy = SimpleNamespace(entity_type=SimpleNamespace(name='MONSTER'), id=71, origin_path='c0m071.dat')
    picker = EncounterPicker(SimpleNamespace(enemy=enemy), registry)
    assert picker.binding.read_only and picker.encounter.count() == 2
    picker.encounter.setCurrentIndex(1)
    assert picker.selected.index == 0 and picker.selected_slot.com_file_id == 71
    enemy.id = 145
    enemy.origin_path = 'c0m145.dat'
    picker.refresh_model()
    assert picker.selected is None
    picker.encounter.setCurrentIndex(1)
    assert picker.selected.index == 1
    enemy.entity_type.name = 'CHARACTER'
    picker.refresh_model()
    assert picker.encounter.count() == 3
    registry.close_file('scene.out')
    assert picker.encounter.count() == 1 and picker.path is None
    assert path.read_bytes() == raw
    picker.close()


def test_encounter_labels_never_read_dats_beside_scene_out(tmp_path):
    """Names: the loaded model's, else the catalog's. A c0mNNN.dat beside scene.out was not
    opened by the user, so it is not read (not even its name)."""
    from Ifrit.IfritCameraSeq.encounterpreview import EncounterPicker
    model = bytearray(88)
    struct.pack_into('<I', model, 0, 8)
    struct.pack_into('<I', model, 7 * 4, 40)  # section 7 is DWORD 7 (header is section 0)
    struct.pack_into('<I', model, 8 * 4, 64)
    model[40:46] = b'Medic\0'
    model[64:70] = b'Wrong\0'
    (tmp_path / 'c0m145.dat').write_bytes(model)
    raw = bytearray(128)
    raw[7], raw[0x38] = 0x80, 145 + 16
    scene = tmp_path / 'scene.out'
    scene.write_bytes(raw)
    game_data = SimpleNamespace(translate_hex_to_str=lambda raw: raw.decode('ascii'),
                                monster_data_json={'monster': [{'com_id': 145, 'name': 'Catalog name'}]})
    enemy = SimpleNamespace(entity_type=SimpleNamespace(name='CHARACTER'), id=0, origin_path='')
    picker = EncounterPicker(SimpleNamespace(enemy=enemy, game_data=game_data))
    assert picker.load(scene)
    assert 'Catalog name' in picker.encounter.itemText(1)
    assert 'Medic' not in picker.encounter.itemText(1)
    picker.encounter.setCurrentIndex(1)
    assert 'Catalog name' in picker.enemy_slot.currentText()
    picker.close()
    # the loaded (edited) monster's own name comes first
    enemy = SimpleNamespace(entity_type=SimpleNamespace(name='MONSTER'), id=145, origin_path='',
                            info_stat_data={'monster_name': 'Edited'})
    picker = EncounterPicker(SimpleNamespace(enemy=enemy, game_data=game_data))
    assert picker.load(scene) and 'Edited' in picker.encounter.itemText(1)
    picker.close()


def test_playback_clock_catches_up_after_delayed_redraw_and_resumes_from_seek(monkeypatch):
    from Ifrit.IfritCameraSeq import camerapreview
    clock = [10.]
    monkeypatch.setattr(camerapreview, 'perf_counter', lambda: clock[0])
    manager = SimpleNamespace(enemy=SimpleNamespace(entity_type=SimpleNamespace(name='CHARACTER')))
    panel = camerapreview.CameraPreviewPanel(manager)
    panel._total = 50
    panel._slider.setRange(0, 50)
    panel._start_playback()
    clock[0] = 10.8  # a busy event loop coalesced several native frame deadlines
    panel._advance()
    assert panel._slider.value() == 12
    clock[0] = 11.5
    panel._advance()
    assert panel._slider.value() == 22
    panel._toggle_play()  # pause time must not count toward playback
    clock[0] = 20.
    panel._toggle_play()
    clock[0] = 21.
    panel._advance()
    assert panel._slider.value() == 37
    panel._slider.setValue(10)  # manual seek while playing starts a new clock anchor
    clock[0] = 22.
    panel._advance()
    assert panel._slider.value() == 25
    clock[0] = 30.
    panel._advance()
    assert panel._slider.value() == 50 and not panel._timer.isActive()
    panel.close()


def test_prepared_quad_halves_share_face_normal_and_keep_uvs_and_texture_rank():
    from Ifrit.Ifrit3D.previewmesh import prepare_batches
    uv = ((0., 0.), (1., 0.), (0., 1.), (1., 1.))
    geometry = SimpleNamespace(
        get_triangles_with_uv=lambda: [((4, 5, 6), uv[:3], 48, 0)],
        get_quads_with_uv=lambda: [((0, 1, 2, 3), uv, 16, -2)],
        get_colored_triangles_with_color=lambda: [], get_colored_quads_with_color=lambda: [])
    images = [object(), object()]
    batches = prepare_batches(geometry, [SimpleNamespace(texture_image=p) for p in images], offset=10)
    quad = next(b for b in batches if b.depth_bias == -2)
    triangle = next(b for b in batches if b.depth_bias == 0)
    np.testing.assert_array_equal(quad.indices, ((10, 11, 13), (10, 12, 13)))
    np.testing.assert_array_equal(quad.normal_indices, ((10, 11, 12), (10, 11, 12)))
    np.testing.assert_array_equal(quad.uvs, ((uv[0], uv[1], uv[3]), (uv[0], uv[2], uv[3])))
    assert quad.pixmap is images[0] and triangle.pixmap is images[1]


ROOT = Path(__file__).resolve().parents[1]
BODY = ROOT / 'extracted_files/battle/d0c000.dat'


@pytest.mark.ff8data('extracted_files/battle/d0c000.dat')
def test_all_squall_opening_cameras_have_non_degenerate_hold_frames_and_do_not_edit_dat():
    raw = BODY.read_bytes()
    offsets = struct.unpack_from('<7I', raw, 4)
    collection = CameraCollection(bytearray(raw[offsets[4]:offsets[5]]))
    for animation in collection.sets[0].animations[:6]:
        poses = play_camera_animation(animation, BattleCameraContext())
        assert len(poses) == sum(f.duration.get() for b in animation.blocks for f in b.frames)
        assert all(np.linalg.norm(np.array(p.eye) - p.target) > 1 for p in poses)
        assert all(np.isfinite((*p.eye, *p.target, p.projection, p.roll)).all() for p in poses)
    assert BODY.read_bytes() == raw
    assert bytes(collection.get_bytes()) == raw[offsets[4]:offsets[5]]


@pytest.mark.ff8data('extracted_files/battle/d0c000.dat', 'extracted_files/battle/c0m071.dat')
def test_shared_preview_battle_setup_and_read_only_opponent():
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
    from Ifrit.IfritCameraSeq.battlepreview import model_root
    manager = IfritManager(str(ROOT / 'FF8GameData'))
    manager.init_from_file(str(BODY))
    before = BODY.read_bytes()
    raw = manager.enemy.section_raw_data[5]
    animation = CameraCollection(bytearray(raw)).sets[0].animations[0]
    panel = CameraPreviewPanel(manager)
    panel.preview(animation)
    panel._timer.stop()
    assert panel._animation is animation, panel._placeholder.text()
    assert len(panel._poses) == 40 and panel._slider.maximum() == 39
    # A raw/128 root places Squall's idle feet at the battle ground, not at the model centre.
    vertices = np.asarray(manager.get_animated_vertices(0, 0)) + model_root(manager, 0, 0)
    assert abs(vertices[:, 1].min()) < 1
    assert panel._gl._explicit_projection == pytest.approx(panel._poses[0].projection)
    panel._slider.setValue(10)
    np.testing.assert_allclose(panel._gl._explicit_eye,
                               panel._battle_setup.to_viewer(panel._poses[9].eye))
    assert panel._battle_setup.load_opponent(ROOT / 'extracted_files/battle/c0m071.dat')
    assert panel._gl._preview_actor is not None
    assert panel._gl._preview_actor.vertices.shape[1] == 3
    assert any(batch.pixmap is not None for batch in panel._gl._preview_actor.batches)
    panel._battle_setup.role.setCurrentIndex(1)
    assert panel._battle_setup.context.target.position == (0., 0., 0.)
    panel._battle_setup.view_mode.setCurrentIndex(1)
    assert panel._gl._explicit_view is None
    panel.invalidate()
    assert not panel._timer.isActive() and not panel._poses
    assert BODY.read_bytes() == before


@pytest.mark.ff8data('extracted_files/battle/d0c000.dat', 'extracted_files/battle/c0m071.dat')
def test_scene_picker_places_world_actors_without_environment_or_file_edits(tmp_path):
    from PyQt6.QtCore import Qt
    from Common.fileregistry import FileRegistry
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
    from Ifrit.IfritCameraSeq.battlepreview import actor_from_model

    # Distinct XYZ and a second instance catch axis swaps, origin rebasing, and
    # accidentally using the first matching monster rather than the chosen slot.
    raw = bytearray(128)
    raw[7] = 0xC0
    raw[0x38:0x3A] = bytes((71 + 16, 71 + 16))
    struct.pack_into('<3h', raw, 8, -1100, 77, -2900)
    struct.pack_into('<3h', raw, 14, 1300, 0, -4200)
    scene = tmp_path / 'scene.out'
    scene.write_bytes(raw)
    registry = FileRegistry()
    registry.open_file('scene.out', str(scene))
    manager = IfritManager(str(ROOT / 'FF8GameData'))
    manager.init_from_file(str(BODY))
    animation = CameraCollection(bytearray(manager.enemy.section_raw_data[5])).sets[0].animations[0]
    panel = CameraPreviewPanel(manager, file_registry=registry)
    panel.preview(animation)
    panel._timer.stop()
    setup = panel._battle_setup
    # the host's opened models (Ifrit's file list): nothing is read from scene.out's folder
    opened = {'c0m071.dat': str(ROOT / 'extracted_files/battle/c0m071.dat'), 'd0c000.dat': str(BODY)}
    setup.model_source = opened.get
    assert setup.group._toggle.arrowType() == Qt.ArrowType.RightArrow
    assert setup.options.isAncestorOf(setup.encounters)
    assert setup.options.isEnabled()  # folding hides; it never disables controls
    setup.group.set_expanded(True)
    picker = setup.encounters
    assert picker.encounter.count() == 2
    assert 'G-Soldier' in picker.encounter.itemText(1)
    assert 'c0m071' not in picker.encounter.itemText(1)
    picker.encounter.setCurrentIndex(1)
    assert setup.context.caster.position == (-1200, 0, 2100)
    assert setup.main_yaw == 0.
    assert setup.context.target.yaw == math.pi
    assert setup.context.target.position == (-1100, 77, -2900)
    assert setup.context.slots[4].position == (1300, 0, -4200)
    assert not setup.position[0].isEnabled()
    assert len(setup._scene_mesh_actors) == 2  # only the two enemies
    assert all(actor is not None for _manager, actor in setup._scene_mesh_actors)
    assert panel._gl._preview_markers == (None, None)
    assert not panel._gl.show_axis
    setup.party_size.setValue(1)
    assert setup.context.caster.position == (0, 0, 1800)
    setup.party_size.setValue(2)
    setup.party_slot.setValue(1)
    assert setup.context.caster.position == (1000, 0, 1800)
    assert setup.caster_slot.value() == 1
    setup.party_size.setValue(3)
    setup.party_slot.setValue(0)
    picker.enemy_slot.setCurrentIndex(1)
    assert setup.context.target.position == (1300, 0, -4200)
    assert setup.target_slot.value() == 4
    assert panel._gl._preview_model_transform[1] == pytest.approx(0)
    mesh = setup.opponent_mesh()
    assert np.isfinite(mesh.vertices).all()
    assert all(batch.indices.max() < len(mesh.vertices) for batch in mesh.batches)
    assert any(batch.pixmap is not None for batch in mesh.batches)
    assert setup.opponent_mesh(1, True) is mesh  # pose changes retain topology/materials
    assert not picker.load(tmp_path / 'absent.out')
    assert picker.selected.index == 0  # failed import keeps current placement
    bad = tmp_path / 'truncated.out'
    bad.write_bytes(b'\0' * 127)
    assert not picker.load(bad)

    # Switch the active DAT in the same shared panel: the selected duplicate
    # monster must be rendered at precisely its own scene slot.
    manager.init_from_file(str(ROOT / 'extracted_files/battle/c0m071.dat'))
    panel.invalidate()
    panel.preview(animation)
    panel._timer.stop()
    picker.encounter.setCurrentIndex(1)
    picker.enemy_slot.setCurrentIndex(1)
    assert setup.context.caster.position == (1300, 0, -4200)
    assert setup.context.target.position == (-1200, 0, 2100)
    assert setup.main_yaw == math.pi and setup.context.target.yaw == 0
    assert setup.caster_slot.value() == 4 and setup.target_slot.value() == 0
    np.testing.assert_allclose(panel._gl._preview_model_transform[0],
                               setup.to_viewer((1300, 0, -4200)))
    local = actor_from_model(manager, yaw=math.pi).point(0, 0)
    np.testing.assert_allclose(setup.context.caster.point(0, 0), local + (1300, 0, -4200))
    assert len(setup._scene_mesh_actors) == 2  # other monster + player, no stage or duplicate loaded model
    panel.preview(SimpleNamespace(blocks=[]))
    assert panel._total == 0 and panel._poses == [setup.context.initial]
    assert 'Empty camera' in panel._readout.text()
    assert panel._gl._preview_actor is not None
    registry.close_file('scene.out')
    assert picker.selected is None and not picker.encounters
    assert setup.position[0].isEnabled()
    assert setup.main_position == (0., 0., 0.)
    assert scene.read_bytes() == raw
    panel.close()
