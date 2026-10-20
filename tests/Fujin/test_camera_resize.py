"""Resizing an effect camera: keyframes and slots added or removed, longer scripts. A resized track
no longer fits the exe (.hext) and says so; it still exports as an FFNx .cam file."""
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.cameracollection import (FRAME_SIZE, build_default_animation, clear_slot, insert_keyframe,
                                              parse_camera_collection, rebuild_collection, remove_keyframe,
                                              set_slot_animation)
from Fujin.cameraeffectmanager import cam_track_error

EXE = "extracted_files/FF8_EN.exe"
LIFE = 35


def empty_collection(nb_set=1):
    """nb_set sets of 8 empty slots (each set's slots share one 0xFFFF word)."""
    table = 2 + 2 * nb_set + 2
    data = bytearray(table)
    for index in range(nb_set):
        set_start = len(data)
        struct.pack_into("<H", data, 2 + 2 * index, set_start)
        data += struct.pack("<8h", *([8] * 8)) + b"\xFF\xFF"
    struct.pack_into("<H", data, 0, nb_set)
    struct.pack_into("<H", data, table - 2, len(data))
    return bytes(data)


def slot_frames(data, set_index, slot):
    animation = parse_camera_collection(data).sets[set_index].animations[slot]
    return None if animation.empty else [len(block.frames) for block in animation.blocks]


def test_structural_edits_rebuild_a_valid_collection():
    data = empty_collection(2)
    assert slot_frames(data, 0, 3) is None
    data = set_slot_animation(data, 0, 3, build_default_animation())
    assert slot_frames(data, 0, 3) == [2] and slot_frames(data, 1, 3) is None
    grown = insert_keyframe(data, 0, 3, 0, 0)
    assert len(grown) == len(data) + FRAME_SIZE and slot_frames(grown, 0, 3) == [3]
    first, copy = parse_camera_collection(grown).sets[0].animations[3].blocks[0].frames[:2]
    assert [field.get() for _label, field in first.fields()] == [field.get() for _label, field in copy.fields()]
    assert remove_keyframe(grown, 0, 3, 0, 1) == data           # the copy removed: the same bytes
    with pytest.raises(ValueError, match="at least one"):
        remove_keyframe(remove_keyframe(data, 0, 3, 0, 0), 0, 3, 0, 0)
    with pytest.raises(ValueError, match="does not exist"):
        insert_keyframe(data, 0, 4, 0, 0)                       # an empty slot has no keyframe
    assert clear_slot(data, 0, 3) == bytes(rebuild_collection(empty_collection(2)))
    for collection in (data, grown):                            # EOF word == length, every time
        assert struct.unpack_from("<H", collection, 2 + 2 * 2)[0] == len(collection)


@pytest.mark.ff8data(EXE)
def test_exe_tracks_survive_a_rebuild_and_grow_as_cam():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    manager = CameraEffectManager(GameData("FF8GameData"))
    manager.load_exe(EXE)
    for track in manager.tracks.values():
        before = parse_camera_collection(track.collection.get_bytes())
        after = parse_camera_collection(rebuild_collection(track.collection.get_bytes()))
        for set_before, set_after in zip(before.sets, after.sets):
            for slot_before, slot_after in zip(set_before.animations, set_after.animations):
                assert slot_before.empty == slot_after.empty
                assert ([[f.offset - slot_before.offset for f in b.frames] for b in slot_before.blocks]
                        == [[f.offset - slot_after.offset for f in b.frames] for b in slot_after.blocks])
    life = manager.track(LIFE)
    life.set_collection(insert_keyframe(life.collection.get_bytes(), 0, 0, 0, 0))
    assert not life.fits_exe and life.current_size > life.size
    assert cam_track_error(manager.cam_bytes(life)) is None
    assert manager.resized_tracks() == [life]
    manager.reset_track(LIFE)
    assert life.fits_exe and life.to_bytes() == life.original


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data(EXE)
def test_resize_in_the_editor_warns_and_exports(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from Fujin.fujinwidget import FujinWidget
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    fujin = FujinWidget()
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    editor.select_effect(LIFE)
    track = editor.manager.track(LIFE)
    assert editor.size_warning.isHidden()

    # "+" on keyframe #0 of set 0 / slot 0 / block 0: the track grows
    widget = editor._collection_widget
    widget._rebuild(insert_keyframe, 0, 0, 0, 0)
    assert not track.fits_exe and editor._collection_widget is not widget
    assert not editor.size_warning.isHidden() and ".cam" in editor.size_warning.text()
    assert "exe" in editor.size_warning.text() and "PR" not in editor.size_warning.text()
    assert editor.effect_list.currentItem().text().endswith("(.cam only)")
    assert editor.preview.track is track

    # The .hext has nothing for it, the .cam has it all
    assert not editor.save_hext(str(tmp_path / "camera.hext")) and "Export .cam" in messages[-1]
    path = tmp_path / "effect_035.cam"
    assert editor.export_cam(str(path)) and path.read_bytes() == track.to_bytes()
    assert cam_track_error(path.read_bytes()) is None

    # A longer script is applied too, with the same warning
    editor._reset_selected()
    assert track.fits_exe and editor.size_warning.isHidden()
    editor.script_editor.setPlainText(editor.script_editor.toPlainText() + "\nplay(1)\nend_clear()")
    assert editor.apply_script_button.isEnabled() and ".cam" in editor.script_size_label.text()
    editor._apply_script()
    assert not track.fits_exe and not editor.size_warning.isHidden()
