"""Alexander's Camera tab: a stage's camera section edited in the shared camera track editor, saved
back with the geometry moved after a grown camera, and the .hext FF8_EN.exe then needs."""
import shutil
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.battlestage.battlestageanalyser import STAGE_GEOMETRY_OFFSET, build_stage_model
from FF8GameData.battlestage.stagecamera import (STAGE_CAMERA_OFFSET, camera_section, stage_camera_track,
                                                 with_camera_section)
from FF8GameData.battlestage.stagehext import GEOMETRY_OFFSET_OPERAND, IMAGE_BASE, stage_hext_text
from FF8GameData.dat.cameracollection import insert_keyframe
from FF8GameData.dat.cameratrack import CameraTrack

STAGE = "extracted_files/battle/a0stg006.x"


@pytest.fixture(scope="module")
def vm():
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    game_data = GameData("FF8GameData")
    game_data.load_camera_sequence_data()
    return camera_sequence_vm(game_data)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _vertex_count(model):
    return sum(len(group.vertices) for obj in model.geometry_data.object_data for group in obj.vertices_data)


def _first_animation(track):
    return next((camera_set.index, animation.slot) for camera_set in track.collection.sets
                for animation in camera_set.animations if not animation.empty)


def test_section_offsets_are_aligned_tables():
    assert set(STAGE_CAMERA_OFFSET) == set(STAGE_GEOMETRY_OFFSET) == set(GEOMETRY_OFFSET_OPERAND)
    assert all(offset % 4 == 0 for offset in STAGE_GEOMETRY_OFFSET.values())


@pytest.mark.ff8data("extracted_files/battle/a0stg162.x")
def test_every_stage_camera_is_a_track(vm):
    for stage_id in STAGE_CAMERA_OFFSET:
        data = open(f"extracted_files/battle/a0stg{stage_id:03d}.x", "rb").read()
        track = stage_camera_track(data, stage_id, vm)
        assert track.to_bytes() == camera_section(data, stage_id)
        assert with_camera_section(data, stage_id, track.to_bytes()) == (data, STAGE_GEOMETRY_OFFSET[stage_id])


@pytest.mark.ff8data(STAGE)
def test_grown_camera_moves_the_geometry(vm):
    data = open(STAGE, "rb").read()
    track = stage_camera_track(data, 6, vm)
    for _ in range(3):   # 3 keyframes of 18 bytes
        track.set_collection(insert_keyframe(track.collection.get_bytes(), *_first_animation(track), 0, 0))
    grown, geometry = with_camera_section(data, 6, track.to_bytes())
    assert geometry > STAGE_GEOMETRY_OFFSET[6] and geometry % 4 == 0
    assert camera_section(grown, 6) == track.to_bytes()
    before, after = build_stage_model(data, stage_id=6), build_stage_model(grown, stage_id=6)
    assert after.geometry_offset == geometry          # found after the camera, not at the exe's offset
    assert _vertex_count(after) == _vertex_count(before) and len(after.textures) == len(before.textures)
    assert grown[geometry:] == data[STAGE_GEOMETRY_OFFSET[6]:]   # the geometry moved as it is
    # the camera shrinks back: the geometry goes back where the exe reads it
    reread = CameraTrack.from_bytes(vm, camera_section(data, 6))
    assert with_camera_section(grown, 6, reread.to_bytes()) == (data, STAGE_GEOMETRY_OFFSET[6])


def test_hext_writes_the_geometry_offset_immediate():
    text = stage_hext_text(28, 3188)
    assert "+400000" in text and "EN FF8 exe" in text
    address = GEOMETRY_OFFSET_OPERAND[28] - IMAGE_BASE
    assert f"{address:X} = {struct.pack('<I', 3188).hex(' ').upper()}" in text


@pytest.mark.ff8data("I:/Jeux/SteamLibrary/steamapps/common/FINAL FANTASY VIII/FF8_EN.exe")
def test_operands_hold_the_vanilla_offsets():
    exe = open("I:/Jeux/SteamLibrary/steamapps/common/FINAL FANTASY VIII/FF8_EN.exe", "rb").read()
    for stage_id, operand in GEOMETRY_OFFSET_OPERAND.items():
        at = operand - IMAGE_BASE       # .text: file offset = address - image base
        assert exe[at - 1] == 0x05 and struct.unpack_from("<I", exe, at)[0] == STAGE_GEOMETRY_OFFSET[stage_id]


@pytest.mark.ff8data(STAGE, "extracted_files/battle/scene.out")
def test_camera_tab_edit_save_and_hext(qapp, tmp_path, monkeypatch):
    from Alexander.alexanderwidget import AlexanderWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    stage = tmp_path / "a0stg006.x"
    shutil.copy(STAGE, stage)
    widget = AlexanderWidget()
    widget.open_files([str(stage)])
    editor, preview = widget.camera_editor, widget.preview
    assert editor.track is widget.manager.camera_track is preview.track
    assert not widget.has_unsaved_changes()

    widget.sceneout_binding.open_path("extracted_files/battle/scene.out")
    encounters = [widget.encounter_combo.itemData(row) for row in range(widget.encounter_combo.count())]
    assert 1 in encounters      # Dollet's two soldiers fight on stage 6
    assert any("intro of encounter" in note for note in editor.slot_notes.values())

    # a value edited in place: same size, the geometry stays
    frame = editor.track.collection.sets[0].animations[_first_animation(editor.track)[1]].blocks[0].frames[0]
    frame.duration.set(frame.duration.get() + 1)
    editor._on_keyframes_changed()
    assert widget.has_unsaved_changes() and widget.stage_list.item(0).text().startswith("* ")
    widget.save_folder()
    assert not widget.has_unsaved_changes() and not (tmp_path / "a0stg006.hext").exists()
    saved = stage.read_bytes()
    assert build_stage_model(saved, stage_id=6).geometry_offset == STAGE_GEOMETRY_OFFSET[6]

    # keyframes added with the editor's + button: the camera grows, Save moves the geometry
    for _ in range(3):
        editor._collection_widget._rebuild(insert_keyframe, *_first_animation(editor.track), 0, 0)
    assert "It grew" in widget.camera_info.text()
    preview.preview_animation(editor.track.collection.sets[0].animations[_first_animation(editor.track)[1]])
    preview._timer.stop()
    assert preview._poses
    widget.save_folder()
    hext = (tmp_path / "a0stg006.hext").read_text(encoding="utf-8")
    geometry = build_stage_model(stage.read_bytes(), stage_id=6).geometry_offset
    assert geometry > STAGE_GEOMETRY_OFFSET[6]
    assert f"= {struct.pack('<I', geometry).hex(' ').upper()}" in hext

    # reopened: the grown file reads back with its camera
    widget.open_files([str(stage)])
    assert widget.manager.camera_track.to_bytes() == camera_section(stage.read_bytes(), 6)
