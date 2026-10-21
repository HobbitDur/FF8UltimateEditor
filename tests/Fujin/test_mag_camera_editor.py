"""A camera stored in a MAG file edits like an exe track (Keyframes + Script tabs, Meaning pane,
size counter, keyframes added/removed, the script's chosen slot marked), inside the fixed room of
its MAG section: the script and the keyframes share it, an edit needing more is refused."""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.dat.cameracollection import insert_keyframe, remove_keyframe

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAG230 = "extracted_files/magic/MAG230_B.00"  # effect 231 Disease Breath: a 192-byte camera section


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
    assert [camera.tabs.tabText(i) for i in range(camera.tabs.count())] == ["Keyframes", "Script"]
    assert camera._collection_widget._structure_edits
    assert camera.script_description.toPlainText()                  # the Meaning pane
    assert "192 bytes" in editor.camera_info.text() and "no .bcam" in editor.camera_info.text()
    # 15 bytes of script, 16 of room: the alignment byte before the keyframes is room too
    assert camera.script_size_label.text() == "15 / 16 bytes (Apply fills the 1 left)"
    original = bytes(manager.data)
    camera._apply_script()                                          # unchanged: same bytes
    assert bytes(manager.data) == original

    # A longer script cannot fit the section: Apply is off and the counter says why
    camera.script_editor.setPlainText(camera.script_editor.toPlainText() + "\nend()\nend()")
    assert "more than the MAG file has" in camera.script_size_label.text()
    assert not camera.apply_script_button.isEnabled()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    camera._apply_script()
    assert messages and "keeps its 192 bytes" in messages[-1] and bytes(manager.data) == original


@pytest.mark.ff8data(MAG230)
def test_mag_camera_keyframes_share_the_fixed_room(qapp, tmp_path, monkeypatch):
    path = tmp_path / "MAG230_B.00"
    original = (ROOT / MAG230).read_bytes()
    path.write_bytes(original)
    manager, section, editor = _camera_editor(qapp, path)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    track = editor.camera_track
    frames = track.keyframe_count()

    # No room yet: a keyframe added is refused, nothing changes
    widget = editor.camera_editor._collection_widget
    widget._rebuild(insert_keyframe, 0, 0, 0, 0)
    assert messages and "keeps its 192 bytes in the MAG file" in messages[-1]
    assert bytes(manager.data) == original and track.keyframe_count() == frames

    # A keyframe removed leaves filler after the script: the section keeps its size
    editor.camera_editor._collection_widget._rebuild(remove_keyframe, 0, 0, 1, 1)
    assert track.keyframe_count() == frames - 1 and len(track.to_bytes()) == section.size
    removed = bytes(manager.data)
    assert removed != original and len(removed) == len(original)
    assert removed[:section.start] == original[:section.start] and removed[section.end:] == original[section.end:]
    assert "Apply fills" in editor.camera_editor.script_size_label.text()

    # Rebuilt from the file (as after every MAG edit), the filler is room again: a keyframe fits
    from Fujin.magsectionwidget import MagSectionEditor
    editor2 = MagSectionEditor(manager, section)
    editor2.camera_editor._collection_widget._rebuild(insert_keyframe, 0, 0, 0, 0)
    assert editor2.camera_track.keyframe_count() == frames and len(manager.data) == len(original)
    assert len(messages) == 1

    # Saved and reopened, the MAG camera decodes with every keyframe
    manager.save_file(str(path))
    _manager, _section, reopened = _camera_editor(qapp, path)
    assert reopened.camera_track.keyframe_count() == frames
    assert reopened.camera_track.to_bytes() == bytes(manager.data[section.start:section.end])


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
