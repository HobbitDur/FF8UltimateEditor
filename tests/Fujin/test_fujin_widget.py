"""Effect workspace entry point and reusable executable camera editor."""
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

EXE = "extracted_files/FF8_EN.exe"
LIFE = 35
CURE, PHOENIX_DOWN = 1, 5
CLASH = 26                       # no camera track, and none can be created (not an item/command)
TIM = "extracted_files/magic/mag000-049.tim"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def fujin(qapp):
    from Fujin.fujinwidget import FujinWidget
    return FujinWidget()


def test_tabs_and_empty_camera_editor(fujin):
    assert [fujin.tabs.tabText(index) for index in range(fujin.tabs.count())] == \
           ["Overview", "Camera", "Choreography", "Models / animation", "Textures",
            "Sound", "Pending changes"]
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
    assert len(fujin.import_entries()) == 4 and len(fujin.complementary_entries()) == 5   # + .bcam files
    fujin.select_effect(LIFE)                                     # mag004-034.tim, not imported
    fujin.textures.activate()
    assert "header's Import" in fujin.textures.status.text()    # what to do with a missing file


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


def test_effect_rows_tell_what_each_effect_has(fujin):
    assert "exe camera track" in fujin.effect_tags(LIFE)
    fujin.select_effect(LIFE)
    tooltip = fujin.effect_list.currentItem().toolTip()
    assert tooltip.startswith("035") and "Has: exe camera track" in tooltip and "open kernel.bin" in tooltip
    fujin.effect_search.search_field.setText("unused slot")      # tags are searchable
    shown = [fujin.effect_list.item(row).data(256) for row in range(fujin.effect_list.count())
             if not fujin.effect_list.item(row).isHidden()]
    assert shown and all(fujin.catalog.info(effect).get("free") for effect in shown)
    fujin.effect_search.clear_search()


def test_an_effect_without_camera_says_so(fujin):
    fujin.tabs.setCurrentIndex(1)
    fujin.select_effect(CLASH)                                   # no camera, and none can be created
    assert fujin.camera_sources.isHidden() and fujin.camera_editor.preview.isHidden()
    assert "plays no camera track" in fujin.camera_note.text()
    fujin.select_effect(PHOENIX_DOWN)                            # no camera, but one can be created
    assert not fujin.camera_sources.isHidden() and "can be given one" in fujin.camera_note.text()
    assert fujin.camera_editor.create_box.isVisibleTo(fujin.camera_editor)
    fujin.select_effect(LIFE)
    assert not fujin.camera_sources.isHidden() and not fujin.camera_editor.preview.isHidden()


@pytest.mark.ff8data(EXE)
def test_the_chosen_animation_is_marked_in_the_keyframes(fujin):
    editor = fujin.camera_editor
    editor.exe_binding.open_path(EXE)
    fujin.tabs.setCurrentIndex(1)
    fujin.select_effect(LIFE)
    widget = editor._collection_widget
    assert editor.preview.last_run.chosen == 23                  # set 1, slot 7 with the default inputs
    assert widget._highlighted == (1, 7) and 1 in widget.expanded_set_indices()
    assert "played by the script" in widget._slot_groups[(1, 7)].title()
    assert "Opening shot = " in editor.preview.result_label.text()   # the form's names, not the VM's


@pytest.mark.ff8data(TIM)
def test_textures_are_pictures_then_their_sections(fujin):
    fujin.import_paths([TIM])
    fujin.select_effect(CURE)
    fujin.tabs.setCurrentIndex(4)
    fujin.textures.activate()
    pictures = fujin.textures.panel
    assert fujin.textures.display.widget(0) is pictures and pictures.cards   # the pictures first
    assert fujin.textures.display.tabText(1) == "Sections (read only)"      # then every TIM section
    card = pictures.cards[0]
    assert card.picture.pixmap() is not None and "texels" in card.info.text()
    if card.rows:                                              # palette rows change the drawing
        card.palette.setCurrentIndex(card.palette.count() - 1)
    assert fujin.models.sources.count() == 0                   # a TIM is all Textures'


@pytest.mark.ff8data(TIM)
def test_empty_tabs_say_why(fujin):
    fujin.select_effect(CURE)
    assert "mag000-049.tim" in fujin.models.empty_text            # its file is not imported yet
    fujin.import_paths([TIM])
    fujin.select_effect(CURE)
    assert fujin.models.empty_text.startswith("This effect stores no model of its own")
    assert "MAG_001_CURE_DrawTargetModelWithOverlay" in fujin.models.empty_text   # named in the snapshot
    assert "ComputeModelBounds" not in fujin.models.empty_text                     # draws nothing
    assert fujin.sound.empty_text.startswith("No sound data in this effect's files")
    fujin.tabs.setCurrentIndex(3)
    fujin.models.activate()
    assert fujin.models.status.text() == fujin.models.empty_text
    assert not fujin.choreography.isTabEnabled(0) and "run by the exe's own code" in fujin.choreography.tabToolTip(0)
    assert "No MAG script" in fujin.choreography_note.text()


def test_native_snapshot_lists_named_functions(fujin):
    snapshot = fujin.catalog.snapshot()
    assert snapshot.get("idb_saved") and snapshot.get("script", "").endswith("export_effect_functions.py")
    functions = fujin.catalog.functions(CURE)
    names = [function["name"] for function in functions]
    assert "MAG_001_CURE_Init" in names and not any(name.startswith("sub_") for name in names)
    assert "pseudocode" not in functions[0]                                  # code: in the gzip, on demand
    assert "MAG_001_CURE_Init" in fujin.catalog.pseudocode(functions[0])
    assert "_snapshot" not in map(str, fujin.catalog.effect_ids())


def test_tabs_without_content_are_greyed(fujin):
    fujin.tabs.setCurrentIndex(3)
    fujin.select_effect(PHOENIX_DOWN)                             # no file imported
    assert fujin.tabs.isTabEnabled(1)                            # Camera: "Create a camera" is offered
    for index in (3, 4, 5):                                      # Models, Textures, Sound
        assert not fujin.tabs.isTabEnabled(index) and fujin.tabs.tabToolTip(index)
    assert fujin.tabs.currentIndex() == 0                       # a greyed tab hands over to Overview
    assert "Greyed tabs" in fujin.overview.toPlainText()
    fujin.select_effect(CLASH)                                   # no camera, none can be created
    assert not fujin.tabs.isTabEnabled(1) and "plays no camera track" in fujin.tabs.tabToolTip(1)
    fujin.select_effect(LIFE)
    assert fujin.tabs.isTabEnabled(1) and fujin.tabs.tabToolTip(1) == ""
    fujin.tabs.setCurrentIndex(1)                                # the user picks Camera...
    fujin.select_effect(CLASH)
    assert fujin.tabs.currentIndex() == 0
    fujin.select_effect(LIFE)
    assert fujin.tabs.currentIndex() == 1                       # ...and gets it back with a camera


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00")
def test_many_effect_files_open_in_one_batch(fujin, monkeypatch):
    import glob
    paths = sorted(glob.glob("extracted_files/magic/MAG2*"))[:20]
    shown = []
    monkeypatch.setattr(fujin.mag_editor, "_show_gf", lambda gf, real=fujin.mag_editor._show_gf: (shown.append(gf), real(gf)))
    fujin.import_paths(paths)
    assert not fujin.file_registry.batching
    assert len(fujin.mag_editor.managers) == len(paths)
    assert len([gf for gf in shown if gf]) == 1                # one file shown, once, at the end


@pytest.mark.ff8data("extracted_files/magic/MAG005_B.00", "extracted_files/magic/MAG005_B.01",
                     "extracted_files/magic/mag000-049.tim")
def test_every_section_has_a_tool_tab(fujin):
    """No Files / sections tab: a MAG file's header and object table are in Models, its undecoded
    workspace in Choreography (Workspace data), a TIM's header in Textures with its pictures."""
    magic = Path(__file__).resolve().parents[2] / "extracted_files" / "magic"
    fujin.import_paths([str(magic / name) for name in ("MAG005_B.00", "MAG005_B.01", "mag000-049.tim")])

    def kinds(view, file_name):
        resource = next(view.sources.itemData(i) for i in range(view.sources.count())
                        if view.sources.itemData(i).key.lower() == file_name.lower())
        return {section.kind for section in view._sections(resource, fujin.resolve(resource))}

    fujin.select_effect(6)                                          # Leviathan: MAG005_B.00 / .01
    assert {"header", "object_table"} <= kinds(fujin.models, "MAG005_B.00")
    assert kinds(fujin.workspace, "MAG005_B.01") == {"raw"}
    assert fujin.choreography.isTabVisible(fujin.workspace_tab)
    fujin.select_effect(1)                                          # Cure: mag000-049.tim
    assert {"header", "tim_block", "palette", "pixels"} <= kinds(fujin.textures, "mag000-049.tim")
    assert fujin.textures.display.tabText(1) == "Sections (read only)"
    assert not fujin.choreography.isTabVisible(fujin.workspace_tab)  # Cure has no workspace data
