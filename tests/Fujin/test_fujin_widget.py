"""Fujin GUI: the Magic explorer / Camera effect editor tabs and the camera .hext save."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

EXE = "extracted_files/FF8_EN.exe"
LIFE = 35


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def fujin(qapp):
    from Fujin.fujinwidget import FujinWidget
    return FujinWidget()


def test_tabs_and_empty_camera_editor(fujin):
    assert [fujin.tabs.tabText(index) for index in range(fujin.tabs.count())] == \
           ["Magic explorer", "Camera effect editor"]
    editor = fujin.camera_editor
    assert not editor.manager.loaded and not fujin.can_save_folder()
    assert editor.effect_list.count() == 345                  # every effect, with or without a track
    assert [label for label, _callback in fujin.import_entries()][0].startswith("FF8 exe")


@pytest.mark.ff8data(EXE)
def test_edit_keyframe_and_save_hext(fujin, tmp_path):
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    assert editor.manager.loaded and not fujin.can_save_folder()
    editor.select_effect(LIFE)
    track = editor.manager.track(LIFE)
    frame = track.collection.sets[0].animations[0].blocks[0].frames[0]
    editor._collection_widget._on_field_changed(frame.pos_x, frame.pos_x.get() + 50)
    assert fujin.can_save_folder()
    assert editor.effect_list.currentItem().text().startswith("* ")
    path = tmp_path / "camera.hext"
    assert editor.save_hext(str(path))
    assert "MAG035_LIFE_cameraAnim" in path.read_text(encoding="utf-8")

    editor._reset_selected()
    assert not fujin.can_save_folder()
    editor.import_hext(str(path))                             # re-open the saved patch
    assert [edited.effect_id for edited in editor.manager.modified_tracks()] == [LIFE]


@pytest.mark.ff8data(EXE)
def test_script_apply_refuses_a_longer_script(fujin, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    editor.select_effect(LIFE)
    room = editor.manager.track(LIFE).script_room
    assert editor.script_size_label.text() == f"{room} / {room} bytes"
    editor.script_editor.setPlainText(editor.script_editor.toPlainText() + "\nend()")
    assert "1 too many" in editor.script_size_label.text()
    assert not editor.apply_script_button.isEnabled()          # Apply is off while too long
    editor._apply_script()
    assert warnings and "remove 1 byte" in warnings[0]
    assert not editor.manager.track(LIFE).modified
