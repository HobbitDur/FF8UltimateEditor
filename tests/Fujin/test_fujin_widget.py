"""Effect workspace entry point and reusable executable camera editor."""
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
           ["Overview", "Camera", "Choreography", "Models / animation", "Textures / palettes",
            "Sound", "Files / sections", "Pending changes"]
    assert fujin.effect_list.count() == 400
    editor = fujin.camera_editor
    assert not editor.manager.loaded and not fujin.can_save_folder()
    assert editor.effect_list.count() == 345                  # every effect, with or without a track
    assert [label for label, _callback in fujin.import_entries()][0].startswith("FF8 exe")


def test_files_open_from_the_header_toolbar_only(fujin):
    """No Import / Open / Load / Reload button inside the tool: the header toolbar's Import,
    Import complementary and Reload do it (import_entries / complementary_entries / bindings)."""
    import re
    from PyQt6.QtWidgets import QPushButton
    buttons = [button.text() for button in fujin.findChildren(QPushButton) if not button.isHidden()]
    assert not [text for text in buttons if re.match(r"(Import|Open|Load|Reload)", text)], buttons
    assert len(fujin.import_entries()) == 3 and len(fujin.complementary_entries()) == 3
    fujin.select_effect(LIFE)                                     # mag004-034.tim, not imported
    fujin.files.activate()
    assert "header's Import" in fujin.files.status.text()       # what to do with a missing file


@pytest.mark.ff8data(EXE)
def test_effect_list_marks_unsaved_effects(fujin, tmp_path):
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    fujin.select_effect(LIFE)
    item = fujin.effect_list.currentItem()
    assert not item.text().startswith("* ") and not fujin.modified_effects()
    frame = editor.manager.track(LIFE).collection.sets[0].animations[0].blocks[0].frames[0]
    editor._collection_widget._on_field_changed(frame.pos_x, frame.pos_x.get() + 50)
    assert fujin.modified_effects() == {LIFE} and item.text().startswith("* 035")
    assert fujin.save_files(tmp_path)
    assert not fujin.modified_effects() and item.text().startswith("035")
    editor._reset_selected()                                      # back to the exe bytes: unsaved again
    assert item.text().startswith("* 035")


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
def test_script_apply_grows_a_longer_script(fujin):
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    editor.select_effect(LIFE)
    track = editor.manager.track(LIFE)
    room = track.script_room
    assert editor.script_size_label.text() == f"{room} / {room} bytes"
    editor.script_editor.setPlainText(editor.script_editor.toPlainText() + "\nend()")
    assert "1 more than the exe has" in editor.script_size_label.text()
    assert editor.apply_script_button.isEnabled()              # a .bcam can take it
    editor._apply_script()
    assert track.modified and not track.fits_exe and not editor.size_warning.isHidden()
