"""A camera stored in a MAG file edits like an exe track (Keyframes + Script tabs, Meaning pane,
size counter, keyframes added/removed, the script's chosen slot marked). It grows or shrinks in
the MAG file (PackedMag moves what follows and updates every offset); where the file cannot move
(MAG222's work buffer), the script and the keyframes share its fixed room."""
import pathlib
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.dat.cameracollection import insert_keyframe, remove_keyframe

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAG230 = "extracted_files/magic/MAG230_B.00"  # effect 231 Disease Breath: a 192-byte camera section
MAG222 = "extracted_files/magic/MAG222_B.00"  # effect 223: its work buffer already reuses the .01


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _camera_editor(qapp, path, preview=None):
    from Fujin.magdocument import MagDocument
    from Fujin.magsectionwidget import MagSectionEditor
    manager = MagDocument()
    manager.load_file(str(path))
    section = next(s for s in manager.document.sections if s.kind == "camera")
    return manager, section, MagSectionEditor(manager, section, camera_preview=preview)


@pytest.mark.ff8data(MAG230)
def test_mag_camera_has_the_exe_editor_tabs_and_counter(qapp, monkeypatch):
    manager, section, editor = _camera_editor(qapp, ROOT / MAG230)
    camera = editor.camera_editor
    # One tab level for the camera: the section's Fields / Bytes sit beside Keyframes / Script
    tabs = [camera.tabs.tabText(i) for i in range(camera.tabs.count())]
    assert tabs[:2] == ["Keyframes", "Script"] and tabs[-1] == "Bytes (hex)" and "Camera" not in tabs
    assert editor.views is camera.tabs and editor.camera_page is not None
    assert camera._collection_widget._structure_edits
    assert camera.script_description.toPlainText()                  # the Meaning pane
    assert "192 bytes" in editor.camera_info.text() and "no .bcam" in editor.camera_info.text()
    assert "can grow" in editor.camera_info.text() and not editor.camera_fixed_reason
    assert camera.script_size_label.text() == "15 / 15 bytes"
    original = bytes(manager.data)
    camera._apply_script()                                          # unchanged: same bytes
    assert bytes(manager.data) == original

    # A longer script grows the camera: the file moves what follows it and keeps every offset right
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    camera.script_editor.setPlainText(camera.script_editor.toPlainText() + "\nend()\nend()")
    assert "the track grows" in camera.script_size_label.text() and camera.apply_script_button.isEnabled()
    camera._apply_script()
    assert not messages and not editor.error.text()
    grown = bytes(manager.data)
    delta = len(grown) - len(original)
    assert delta > 0 and delta % 4 == 0 and editor.section.size > 192
    objects, sound = struct.unpack_from("<2I", original, 0x0C)      # header +0x0C, +0x10
    assert struct.unpack_from("<I", grown, 0x10)[0] == sound + delta
    assert struct.unpack_from("<I", grown, 0x0C)[0] == objects + delta
    # the script is untouched, everything after the camera moved as is
    assert grown[sound + delta:] == original[sound:] and grown[0x58:0x870] == original[0x58:0x870]
    assert manager.undo() and bytes(manager.data) == original


@pytest.mark.ff8data(MAG230)
def test_mag_camera_keyframes_grow_the_file(qapp, tmp_path, monkeypatch):
    path = tmp_path / "MAG230_B.00"
    original = (ROOT / MAG230).read_bytes()
    path.write_bytes(original)
    manager, section, editor = _camera_editor(qapp, path)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    track = editor.camera_track
    frames = track.keyframe_count()

    # A keyframe added: the camera and the file grow, the sound table and the objects follow
    editor.camera_editor._collection_widget._rebuild(insert_keyframe, 0, 0, 0, 0)
    assert not messages and track.keyframe_count() == frames + 1
    assert len(manager.data) > len(original) and editor.section.size == len(track.to_bytes())
    sounds = [entry.sound_id for entry in manager.packed().sound_entries()]
    from FF8GameData.magcine.packedmag import PackedMag
    assert sounds == [entry.sound_id for entry in PackedMag(original).sound_entries()]

    # Saved and reopened, the MAG camera decodes with every keyframe
    manager.save_file(str(path))
    _manager, reopened_section, reopened = _camera_editor(qapp, path)
    assert reopened.camera_track.keyframe_count() == frames + 1
    assert reopened.camera_track.to_bytes() == bytes(manager.data[reopened_section.start:reopened_section.end])

    # Removed again, the camera shrinks: what follows it is the vanilla bytes again
    reopened.camera_editor._collection_widget._rebuild(remove_keyframe, 0, 0, 0, 0)
    assert reopened.camera_track.keyframe_count() == frames
    shrunk = bytes(_manager.data)
    assert len(shrunk) < len(manager.data) and shrunk.endswith(original[0x930:])
    assert struct.unpack_from("<I", shrunk, 0x10)[0] == len(shrunk) - len(original) + 0x930


@pytest.mark.ff8data(MAG222, MAG222[:-1] + "1")
def test_mag_camera_keeps_its_room_where_the_file_cannot_move(qapp, tmp_path, monkeypatch):
    path = tmp_path / "MAG222_B.00"
    original = (ROOT / MAG222).read_bytes()
    path.write_bytes(original)
    # without its .01 the work buffer cannot be checked: the camera keeps its room too
    assert "MAG222_B.01" in _camera_editor(qapp, path)[2].camera_fixed_reason
    path.with_suffix(".01").write_bytes((ROOT / MAG222).with_suffix(".01").read_bytes())
    manager, section, editor = _camera_editor(qapp, path)
    assert "work buffer at 0x28000" in editor.camera_fixed_reason
    assert f"keeps its {section.size} bytes" in editor.camera_info.text()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    track = editor.camera_track
    frames = track.keyframe_count()

    # No room: a keyframe added is refused, nothing changes
    widget = editor.camera_editor._collection_widget
    widget._rebuild(insert_keyframe, 0, 0, 0, 0)
    assert messages and f"keeps its {section.size} bytes in the MAG file" in messages[-1]
    assert bytes(manager.data) == original and track.keyframe_count() == frames
    # the size counter says so before Apply
    editor.camera_editor.script_editor.setPlainText(editor.camera_editor.script_editor.toPlainText() + "\nend()")
    assert "keeps its" in editor.camera_editor.script_size_label.text()
    assert not editor.camera_editor.apply_script_button.isEnabled()


@pytest.mark.ff8data(MAG230)
def test_mag_camera_marks_the_slot_the_script_plays(qapp):
    from Common.fileregistry import FileRegistry
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    from Fujin.cameraeffectpreview import CameraEffectPreview
    preview = CameraEffectPreview(CameraEffectManager(GameData("FF8GameData")), FileRegistry())
    _manager, _section, editor = _camera_editor(qapp, ROOT / MAG230, preview=preview)
    widget = editor.camera_editor._collection_widget
    assert preview.track is editor.camera_track and preview.last_run.chosen is not None
    assert widget._highlighted is not None
    assert "played by the script" in widget._slot_groups[widget._highlighted].title()
