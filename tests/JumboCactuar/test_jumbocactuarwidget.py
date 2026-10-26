"""JumboCactuar GUI: editing an encounter through its widgets, copy/paste, undo, save."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.sceneout import EncounterRecord
from tests.JumboCactuar.test_jumbocactuarmanager import synthetic_scene_out


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp, tmp_path):
    from JumboCactuar.jumbocactuarwidget import JumboCactuarWidget
    path = tmp_path / "scene.out"
    path.write_bytes(synthetic_scene_out())
    w = JumboCactuarWidget()
    w.binding.open_path(str(path))
    return w, path


def _saved(path, index):
    return EncounterRecord(path.read_bytes()[index * 128:(index + 1) * 128])


def test_nothing_to_edit_without_a_file(qapp):
    from JumboCactuar.jumbocactuarwidget import JumboCactuarWidget
    w = JumboCactuarWidget()
    assert not w.editor.isEnabled() and w.encounter_list.count() == 0
    assert w.file_bindings() == [w.binding]


def test_shows_the_selected_encounter(widget):
    w, path = widget
    assert w.editor.isEnabled() and w.encounter_list.count() == 1024
    w.encounter_list.setCurrentRow(5)
    record = _saved(path, 5)
    assert w.stage_combo.currentIndex() == record.stage_id
    assert [box.isChecked() for box in w.flag_boxes] == [record.flag(bit) for bit in range(8)]
    assert w.camera_spins[1][0].value() == record.camera(1)[0]
    panel = w.slot_panels[3]
    assert panel.enemy_combo.currentIndex() == record.enemy_byte(3)
    assert [spin.value() for spin in panel.position_spins] == list(record.position(3))
    assert w.unknown_edits[3].text() == " ".join(f"{b:02X}" for b in record.unknown[48:56])
    assert not w.has_unsaved_changes()


def test_edit_every_section_and_save(widget):
    w, path = widget
    w.encounter_list.setCurrentRow(10)
    w.stage_combo.setCurrentIndex(1)
    w.flag_boxes[0].setChecked(not w.flag_boxes[0].isChecked())
    w.camera_spins[0][0].setValue(4)
    w.camera_spins[0][1].setValue(6)
    panel = w.slot_panels[2]
    panel.enemy_combo.setCurrentIndex(0x10 + 84)
    panel.level_spin.setValue(77)
    panel.flag_boxes["not_visible"].setChecked(not panel.flag_boxes["not_visible"].isChecked())
    panel.position_spins[2].setValue(-4321)
    w.unknown_edits[3].setText("01 02 03 04 05 06 07 08")
    w.unknown_edits[3].editingFinished.emit()
    assert w.encounter_list.item(10).text().startswith("* ")
    assert w.has_unsaved_changes()

    before = _saved(path, 10)
    w.binding.save()
    record = _saved(path, 10)
    assert record.stage_id == 1 and record.flag(0) != before.flag(0)
    assert record.camera(0) == (4, 6)
    assert record.enemy_byte(2) == 0x10 + 84 and record.level(2) == 77
    assert record.slot_flag("not_visible", 2) != before.slot_flag("not_visible", 2)
    assert record.position(2)[2] == -4321
    assert record.unknown[48:] == bytes(range(1, 9))
    assert not w.encounter_list.item(10).text().startswith("* ") and not w.has_unsaved_changes()
    # every other encounter is untouched
    assert path.read_bytes()[:10 * 128] == synthetic_scene_out()[:10 * 128]


def test_incomplete_unknown_field_is_not_applied(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(0)
    before = w.manager.records[0].unknown
    w.unknown_edits[0].setText("AB CD")
    w.unknown_edits[0].editingFinished.emit()
    assert w.manager.records[0].unknown == before
    assert w.unknown_edits[0].text() == " ".join(f"{b:02X}" for b in before[:16])


def test_copy_paste_sections_between_encounters(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(20)
    source = w.manager.records[20]
    assert not w._paste_buttons["stage"][0].isEnabled()
    w._copy_stage()
    w._copy_flags()
    w._copy_camera(1)
    w._copy_slot(0)
    w.encounter_list.setCurrentRow(30)
    w._paste_stage()
    w._paste_flags()
    w._paste_camera(0)          # copied from the secondary, pasted into the main one
    w._paste_slot(7)
    target = w.manager.records[30]
    assert target.stage_id == source.stage_id and target.flags == source.flags
    assert target.camera_byte(0) == source.camera_byte(1)
    assert target.slot(7) == source.slot(0)
    assert w.stage_combo.currentIndex() == source.stage_id  # shown again after the paste

    w._copy_encounter()
    w.encounter_list.setCurrentRow(31)
    w._paste_encounter()
    assert w.manager.records[31].to_bytes() == target.to_bytes()


def test_selected_slots_copy_and_paste(widget, monkeypatch):
    w, _path = widget
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    w.encounter_list.setCurrentRow(40)
    copied = [w.manager.records[40].slot(1), w.manager.records[40].slot(4)]
    w.slot_panels[1].select_box.setChecked(True)
    w.slot_panels[4].select_box.setChecked(True)
    w._copy_selected_slots()
    assert not any(panel.select_box.isChecked() for panel in w.slot_panels)

    w.encounter_list.setCurrentRow(41)
    w.slot_panels[0].select_box.setChecked(True)
    w._paste_selected_slots()      # 2 copied, 1 selected: refused
    assert warnings and w.manager.records[41].to_bytes() == synthetic_scene_out()[41 * 128:42 * 128]
    w.slot_panels[6].select_box.setChecked(True)
    w._paste_selected_slots()
    assert [w.manager.records[41].slot(0), w.manager.records[41].slot(6)] == copied


def test_undo_redo_and_revert(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(50)
    original = w.manager.records[50].to_bytes()
    w.slot_panels[0].level_spin.setValue(3)
    w.slot_panels[0].level_spin.setValue(33)   # same field: one undo step
    w.encounter_list.setCurrentRow(51)
    w.undo()
    assert w.encounter_list.currentRow() == 50   # undo goes back to the encounter it changed
    assert w.manager.records[50].to_bytes() == original
    assert w.slot_panels[0].level_spin.value() == original[0x78]
    w.redo()
    assert w.slot_panels[0].level_spin.value() == 33
    w._revert_encounter()
    assert w.manager.records[50].to_bytes() == original
    assert not w.encounter_list.item(50).text().startswith("* ")


def test_search_finds_encounters_by_monster(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(0)
    w.slot_panels[0].enemy_combo.setCurrentIndex(0x10 + 84)
    w.slot_panels[0].flag_boxes["enabled"].setChecked(True)
    w.encounter_search.search_field.setText("jumbo cactuar")
    visible = [row for row in range(w.encounter_list.count()) if not w.encounter_list.item(row).isHidden()]
    assert 0 in visible


def test_closing_the_file_drops_its_edits(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(70)
    w.slot_panels[0].level_spin.setValue(9)
    assert w.has_unsaved_changes()
    w.file_registry.close_file("scene.out")
    assert not w.has_unsaved_changes() and not w.editor.isEnabled() and w.encounter_list.count() == 0


def test_save_as_moves_the_shared_file(widget, monkeypatch, tmp_path):
    w, _path = widget
    new_path = tmp_path / "mod" / "scene_copy"
    new_path.parent.mkdir()
    w.encounter_list.setCurrentRow(60)
    w.slot_panels[0].level_spin.setValue(12)
    from JumboCactuar import jumbocactuarwidget
    monkeypatch.setattr(jumbocactuarwidget.QFileDialog, "getSaveFileName", lambda *args: (str(new_path), ""))
    w._save_as()
    saved = str(new_path) + ".out"
    assert w.binding.current_path == saved
    assert _saved(type(tmp_path)(saved), 60).level(0) == 12
    assert w.encounter_list.currentRow() == 60 and not w.has_unsaved_changes()


def test_battle_files_feed_the_preview(widget, tmp_path):
    from JumboCactuar.jumbocactuarwidget import BATTLE_FILES_KEY
    w, _path = widget
    files = [tmp_path / name for name in ("a0stg001.x", "C0M084.DAT", "notes.txt")]
    for file in files:
        file.write_bytes(b"")
    w._add_battle_files([str(file) for file in files])
    assert w.preview.file_source("a0stg001.x") == str(files[0])
    assert w.preview.file_source("c0m084.dat") == str(files[1])     # names match whatever their case
    assert w.preview.file_source("notes.txt") is None
    assert w.file_registry.get_path(BATTLE_FILES_KEY)               # listed in the Opened files panel
    w.file_registry.close_file(BATTLE_FILES_KEY)
    assert w.preview.file_source("a0stg001.x") is None


def test_open_folder_finds_the_battle_files(widget, tmp_path):
    w, _path = widget
    battle = tmp_path / "data" / "battle"
    battle.mkdir(parents=True)
    for name in ("a0stg005.x", "c0m071.dat", "d0c000.dat"):
        (battle / name).write_bytes(b"")
    w.load_folder(str(tmp_path / "data"))
    assert set(w._battle_files) == {"a0stg005.x", "c0m071.dat"}


def test_preview_follows_the_shown_encounter(widget):
    w, _path = widget
    w.encounter_list.setCurrentRow(80)
    assert w.preview._record is w.manager.records[80] and w.preview._encounter_index == 80
    w.slot_panels[0].position_spins[0].setValue(1234)
    assert w.preview._record.position(0)[0] == 1234
    w.undo()
    assert w.preview._record is w.manager.records[80]    # undo puts a new record in place: shown too


def test_monsters_and_stages_are_side_files(widget, monkeypatch, tmp_path):
    """Import goes straight to scene.out; the monsters and stages come from Import read-only."""
    from JumboCactuar import jumbocactuarwidget
    w, _path = widget
    assert not callable(getattr(w, "open_files", None))
    labels = [label for label, _callback in w.complementary_entries()]
    assert any("c0m###.dat" in label for label in labels) and any("a0stg###.x" in label for label in labels)
    monster = tmp_path / "c0m071.dat"
    monster.write_bytes(b"")
    monkeypatch.setattr(jumbocactuarwidget.QFileDialog, "getOpenFileNames", lambda *args: ([str(monster)], ""))
    w._import_monsters()
    assert w.preview.file_source("c0m071.dat") == str(monster)
    assert w.file_registry.last_folder(jumbocactuarwidget.MODEL_FOLDER_KEY) == str(tmp_path)
