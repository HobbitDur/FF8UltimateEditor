"""The shared battle preview of an encounter, and the stage camera section it films with."""
import struct
import sys

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.battlestage.stagecamera import STAGE_CAMERA_OFFSET, StageCamera, read_stage_camera
from FF8GameData.dat.battlecamera import BattleCameraContext, play_camera_animation
from FF8GameData.dat.cameracollection import add_animation_to_slot
from FF8GameData.sceneout import EncounterRecord

CAMERA_SETTINGS = bytes.fromhex("0500c310e57fc100cb7fea06e607e60201e6f10302000000")  # every vanilla stage's


def synthetic_stage(stage_id=0, filled_slot=2):
    """A stage file holding only its camera section: one set, one animation (in filled_slot)."""
    empty_set = struct.pack("<8h", *[8] * 8) + b"\xff\xff"   # 8 slots on one 0xFFFF word
    collection = struct.pack("<3H", 1, 6, 6 + len(empty_set)) + empty_set
    collection = add_animation_to_slot(collection, 0, filled_slot)
    header = struct.pack("<4H", 2, 8, 8 + len(CAMERA_SETTINGS), 8 + len(CAMERA_SETTINGS) + len(collection))
    return bytes(STAGE_CAMERA_OFFSET[stage_id]) + header + CAMERA_SETTINGS + bytes(collection)


def test_intro_camera_byte_picks_set_and_animation():
    camera = StageCamera(synthetic_stage(), 0)
    assert camera.settings == CAMERA_SETTINGS and camera.set_count == 1
    animation = camera.intro_animation(0x02)
    assert animation is not None
    assert camera.intro_animation(0x0A) is animation      # bit 3 is not part of the animation id
    assert camera.intro_animation(0x12) is None            # set 1: the stage has none
    assert len(play_camera_animation(animation, BattleCameraContext())) == 30   # two keyframes of 15 ticks


@pytest.mark.ff8data("extracted_files/battle/a0stg103.x")
def test_every_vanilla_stage_camera_reads():
    for stage_id in STAGE_CAMERA_OFFSET:
        camera = read_stage_camera(f"extracted_files/battle/a0stg{stage_id:03d}.x", stage_id)
        assert camera.settings == CAMERA_SETTINGS and camera.set_count >= 1
    # Jumbo Cactuar's encounter (712): camera 0x36 = stage 103, set 3, animation 6
    assert read_stage_camera("extracted_files/battle/a0stg103.x", 103).intro_animation(0x36) is not None


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _record(stage_id=1, enemies=((84, (0, 0, -4000)), (2, (1000, 0, -5000))), camera=0x02):
    record = EncounterRecord()
    record.stage_id = stage_id
    record.set_camera_byte(0, camera)
    for slot, (com_id, position) in enumerate(enemies):
        record.set_enemy_byte(slot, 0x10 + com_id)
        record.set_position(slot, position)
        record.set_slot_flag("enabled", slot, True)
    return record


def test_without_files_every_place_is_a_post(qapp):
    from Common.battlescenepreview import BattleScenePreview, to_viewer, MARKER_HEIGHT, UNIT
    preview = BattleScenePreview()
    preview.show_encounter(_record(), 7)
    preview._rebuild()
    points, height, grid, _step = preview.gl._preview_slots
    assert len(points) == 2 + 3                                # both enemies and the party
    assert np.allclose(points[0], to_viewer((0, 0, -4000))) and height == MARKER_HEIGHT * UNIT
    assert grid is not None                                    # no stage: a ground grid
    status = preview.status.text()
    assert "Encounter 7" in status and "a0stg001.x not opened" in status and "c0m084.dat" in status
    preview.play_intro(0)
    assert not preview._poses and "needs the stage file" in preview.status.text()


def test_intro_camera_plays_from_the_stage_file(qapp, tmp_path):
    from Common.battlescenepreview import BattleScenePreview
    stage = tmp_path / "a0stg000.x"
    stage.write_bytes(synthetic_stage())
    preview = BattleScenePreview()
    preview._stages[str(stage)] = type("Stage", (), {"vertices": np.zeros((0, 3), np.float32), "batches": [],
                                                     "camera": StageCamera(stage.read_bytes(), 0)})()
    preview.file_source = lambda name: str(stage) if name == "a0stg000.x" else None
    preview.show_encounter(_record(stage_id=0, camera=0x02))
    preview.play_intro(0)
    preview._timer.stop()
    assert len(preview._poses) == 30 and preview.slider.maximum() == 29
    preview.slider.setValue(29)
    assert preview.gl._explicit_view is not None and preview.gl.letterbox_color is not None
    preview.show_encounter(_record(stage_id=0, camera=0x12))   # set 1: the stage has none
    preview._rebuild()
    assert not preview._poses and preview.gl._explicit_view is None
    assert "plays nothing" in preview.status.text()


@pytest.mark.ff8data("extracted_files/battle/scene.out", "extracted_files/battle/a0stg006.x",
                     "extracted_files/battle/c0m071.dat")
def test_real_encounter_stands_the_enemies_on_the_stage(qapp):
    import os
    from Common.battlescenepreview import BattleScenePreview, UNIT
    from JumboCactuar.jumbocactuarmanager import JumboCactuarManager
    manager = JumboCactuarManager()
    manager.load_file("extracted_files/battle/scene.out")
    preview = BattleScenePreview()
    preview.file_source = lambda name: (os.path.join("extracted_files/battle", name)
                                        if os.path.exists(os.path.join("extracted_files/battle", name)) else None)
    preview.show_encounter(manager.records[1], 1)    # Dollet: two G-Soldiers on stage 6
    preview._rebuild()
    assert len(preview._actors) == 2 and len(preview.gl._preview_slots[0]) == 3   # party posts only
    assert preview.gl._preview_slots[2] is None                                    # the stage, no grid
    stage = preview._stage.vertices
    for _model, actor, dest, _body in preview._actors:
        x, z = -actor.position[0] * UNIT, actor.position[2] * UNIT
        floor = stage[(np.abs(stage[:, 0] - x) < 600 * UNIT) & (np.abs(stage[:, 2] - z) < 600 * UNIT)]
        foot = preview._mesh.vertices[dest][:, 1].min()
        assert abs(foot - np.median(floor[:, 1])) < 50 * UNIT   # on the cobbles, not floating above them
    preview.play_intro(0)
    preview._timer.stop()
    assert len(preview._poses) > 1


def test_party_picks_among_the_opened_characters(qapp, tmp_path):
    from Common.battlescenepreview import BattleScenePreview
    paths = [str(tmp_path / name) for name in ("d1c003.dat", "d0c000.dat", "d0w000.dat", "d0w001.dat", "d1w008.dat")]
    preview = BattleScenePreview()
    preview.set_party_files(paths)
    characters = [combo.currentData() for combo in preview.party_combos]
    assert characters == [paths[1], paths[0], None]                 # Squall then Zell, the third slot empty
    assert preview.party_combos[0].currentText() == "Squall (d0c000.dat)"
    assert preview.weapon_combos[0].currentData() == paths[2]        # his first weapon
    assert [preview.weapon_combos[0].itemData(i) for i in range(preview.weapon_combos[0].count())] == \
           [None, paths[2], paths[3]]                                # only Squall's weapons
    preview.party_combos[1].setCurrentIndex(0)                       # the user empties slot 2...
    preview.set_party_files(paths + [str(tmp_path / "d2c006.dat")])
    assert preview.party_combos[1].currentData() is None             # ...it stays as they set it
    assert preview.party_combos[2].currentData() == str(tmp_path / "d2c006.dat")


@pytest.mark.ff8data("extracted_files/battle/scene.out", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/d1c003.dat",
                     "extracted_files/battle/d1w008.dat")
def test_real_party_stands_in_formation(qapp):
    import glob
    from Common.battlescenepreview import BattleScenePreview, UNIT
    from FF8GameData.sceneout import EncounterRecord
    preview = BattleScenePreview()
    preview.set_party_files(glob.glob("extracted_files/battle/d0c000.dat") + glob.glob("extracted_files/battle/d0w000.dat")
                            + glob.glob("extracted_files/battle/d1c003.dat") + glob.glob("extracted_files/battle/d1w008.dat"))
    preview.show_encounter(EncounterRecord(), 0)
    preview._rebuild()
    drawn = [(model, body) for model, _actor, _dest, body in preview._actors]
    assert len(drawn) == 4 and sum(body is not None for _model, body in drawn) == 2   # 2 bodies, 2 weapons
    assert any(model.reduced for model, _body in drawn)                 # Zell's gloves: posed by his bones
    assert "2 of 3 member(s) drawn" in preview.status.text()
    assert len(preview.gl._preview_slots[0]) == 1                       # the empty third place is a post
    for model, actor, dest, body in preview._actors:
        if body is None:
            assert abs(preview._mesh.vertices[dest][:, 1].min()) < 50 * UNIT   # feet on y = 0


def test_party_prefers_other_characters_to_other_costumes(qapp, tmp_path):
    from Common.battlescenepreview import BattleScenePreview
    names = ("d0c000.dat", "d0c001.dat", "d1c003.dat", "d5c011.dat")
    preview = BattleScenePreview()
    preview.set_party_files([str(tmp_path / name) for name in names])
    assert [combo.currentText() for combo in preview.party_combos] == \
           ["Squall (d0c000.dat)", "Zell (d1c003.dat)", "Selphie (d5c011.dat)"]


def test_free_camera_wheel_zoom_and_right_drag_pan(qapp):
    """The wheel zooms by steps around the framed distance (it used to snap to the size of a model
    the preview does not have), and a right drag moves the view, as in the model viewers."""
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent, QWheelEvent
    from Common.battlescenepreview import BattleScenePreview
    preview = BattleScenePreview()
    preview.resize(640, 480)
    preview.show_encounter(_record(enemies=((84, (0, 0, -9000)), (2, (6000, 0, -12000)))), 0)
    preview._rebuild()
    gl = preview.gl
    framed = gl.zoom
    assert framed > 10                                         # a wide field: further than 10 units

    def wheel(steps):
        gl.wheelEvent(QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120 * steps),
                                  Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                  Qt.ScrollPhase.NoScrollPhase, False))
    wheel(-1)
    assert abs(gl.zoom - framed * 1.1) < 1e-6                  # one step out, not snapped back in
    wheel(2)
    assert gl.zoom < framed

    def mouse(kind, x, buttons):
        return QMouseEvent(kind, QPointF(x, 100), QPointF(x, 100), Qt.MouseButton.RightButton, buttons,
                           Qt.KeyboardModifier.NoModifier)
    pan = gl.pan_x
    gl.mousePressEvent(mouse(QMouseEvent.Type.MouseButtonPress, 100, Qt.MouseButton.RightButton))
    gl.mouseMoveEvent(mouse(QMouseEvent.Type.MouseMove, 160, Qt.MouseButton.RightButton))
    gl.mouseReleaseEvent(mouse(QMouseEvent.Type.MouseButtonRelease, 160, Qt.MouseButton.NoButton))
    assert gl.pan_x > pan
