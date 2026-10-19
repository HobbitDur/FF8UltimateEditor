"""Xu GUI: editing rows through the widget and saving them via the shared file binding."""
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from tests.Xu.test_xumanager import synthetic_bin

EXE = "extracted_files/FF8_EN.exe"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp, tmp_path):
    from Xu.xuwidget import XuWidget
    path = tmp_path / "battle_scan_cameras.bin"
    path.write_bytes(synthetic_bin())
    w = XuWidget()
    w.binding.open_path(str(path))
    return w, path


def test_nothing_to_edit_without_a_source(qapp):
    """No exe and no .bin: the rows have no values to show (nothing is stored in the tool)."""
    from Xu.xuwidget import XuWidget
    w = XuWidget()
    assert not w.manager.loaded and not w.editor_group.isEnabled()
    assert not w.can_save_folder()


def test_edit_and_save(widget):
    w, path = widget
    assert w.editor_group.isEnabled()
    w.row_list.setCurrentRow(168)
    w._spinboxes["distance"].setValue(-5000)
    w._checkboxes["can_yaw"].setChecked(False)
    assert w.row_list.item(168).text().startswith("* ")  # differs from the file as opened
    w.binding.save()

    from Xu.xumanager import XuManager
    saved = XuManager()
    saved.load_file(str(path))
    assert saved.rows[168].distance == -5000 and saved.rows[168].can_yaw == 0


def test_copy_reset_and_filter(widget):
    w, _path = widget
    w.row_list.setCurrentRow(170)
    w.copy_source.setCurrentIndex(w.copy_source.findData(162))
    w._copy_row()
    assert w.manager.rows[170] == w.manager.rows[162]
    assert w._spinboxes["distance"].value() == -162
    w._reset_row()
    assert w.manager.is_reference(170) and w._spinboxes["distance"].value() == -170

    w.changed_only.setChecked(True)
    assert all(w.row_list.item(row).isHidden() for row in range(w.row_list.count()))
    w.changed_only.setChecked(False)
    w.filter_edit.setText("G-Soldier")
    visible = [row for row in range(w.row_list.count()) if not w.row_list.item(row).isHidden()]
    assert 87 in visible and len(visible) < 10


def test_models_follow_the_row(widget, tmp_path):
    """Opened c0m files are matched to rows by their c0m number; other names are ignored."""
    w, _path = widget
    w.add_models([str(tmp_path / name) for name in ("c0m071.dat", "notes.txt", "d4c004.dat", "d4c005.dat")])
    # keyed by com_id: c0m071 = 87, Rinoa d4c = 4 (the first costume opened is kept)
    assert w._model_paths == {87: str(tmp_path / "c0m071.dat"), 4: str(tmp_path / "d4c004.dat")}
    assert w._model_com_id_for_row(162) == 119  # Abadon's alternate form shows Abadon


def test_scan_text_tab(widget, tmp_path):
    from Xu.xutext import XuTextManager
    w, _path = widget
    game_data = w.game_data
    texts = [bytes(game_data.translate_str_to_hex(f"Text {i}")) + b"\x00" for i in range(166)]
    offsets, position = [], 4 * len(texts)
    for blob in texts:
        offsets.append(position)
        position += len(blob)
    msd = tmp_path / "battle_scans.msd"
    msd.write_bytes(struct.pack("<166I", *offsets) + b"".join(texts))
    w.text_binding.open_path(str(msd))

    w.row_list.setCurrentRow(87)  # G-Soldier, entry 87
    assert w._translation_widget is not None and "Entry 87" in w.text_entry_label.text()
    w.row_list.setCurrentRow(162)  # Abadon's alternate form shows Abadon's text (com_id 119)
    assert "Entry 119" in w.text_entry_label.text()
    w.row_list.setCurrentRow(172)  # c0m150 = com_id 166: past the end of a 166-text file
    assert w._translation_widget is None and not w.text_create_button.isHidden()
    w._create_text_entry()
    assert len(w.text_manager.texts) == 216 and w._translation_widget is not None
    w.text_manager.set_str(166, "New monster")
    w.text_binding.save()
    saved = XuTextManager(game_data)
    saved.load_file(str(msd))
    assert saved.get_str(166) == "New monster" and saved.get_str(87) == "Text 87"


@pytest.mark.ff8data(EXE)
def test_exe_import_then_save_writes_both_files(qapp, tmp_path, monkeypatch):
    """Importing only the exe gives its vanilla rows and texts; Save writes both FFNx files
    to a folder asked once, and they become the opened files."""
    from PyQt6.QtWidgets import QFileDialog
    from Xu.xumanager import XuManager
    from Xu.xutext import XuTextManager
    from Xu.xuwidget import XuWidget
    w = XuWidget()
    w.import_paths([EXE])
    assert w.manager.loaded and w.editor_group.isEnabled() and w.text_manager.loaded
    assert w.can_save_folder()
    w.row_list.setCurrentRow(168)
    assert w._spinboxes["distance"].value() == -0x1200  # FFNx's G-Soldier copy
    w._spinboxes["distance"].setValue(-5000)
    w.text_manager.set_str(87, "Edited")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(tmp_path))
    w.save_files()
    saved = XuManager()
    saved.load_file(str(tmp_path / "battle_scan_cameras.bin"))
    assert saved.rows[168].distance == -5000 and saved.rows[87].distance == -0x1200
    texts = XuTextManager(w.game_data)
    texts.load_file(str(tmp_path / "battle_scans.msd"))
    assert len(texts.texts) == 160 and texts.get_str(87) == "Edited"
    assert w.binding.is_loaded and w.text_binding.is_loaded
    w._reset_row()
    assert w._spinboxes["distance"].value() == -0x1200  # reset = the exe's value


def test_import_routes_by_type(widget, tmp_path):
    w, path = widget
    w.import_paths([str(path)])
    assert w.binding.current_path == str(path)


@pytest.mark.ff8data(EXE)
def test_default_msd_from_the_exe(qapp):
    """The default battle_scans.msd holds the exe's 160 texts, in com_id order."""
    from FF8GameData.gamedata import GameData
    from Xu.xutext import XuTextManager
    from Xu.xuwidget import build_msd_from_exe
    game_data = GameData("FF8GameData")
    manager = XuTextManager(game_data)
    manager.load_bytes(build_msd_from_exe(game_data, EXE))
    assert len(manager.texts) == 160
    assert manager.get_str(87).startswith("Galbadian soldier")  # G-Soldier


def test_header_toolbar_lines(qapp, tmp_path, monkeypatch):
    """Import and Import read-only both show their lines; each dialog reopens where its
    files were last picked from."""
    from PyQt6.QtWidgets import QFileDialog, QStackedWidget
    from Common.fileregistry import FileRegistry
    from Common.filetoolbarwidget import FileToolbarWidget
    from Xu.xuwidget import XuWidget
    registry = FileRegistry()
    stack = QStackedWidget()
    w = XuWidget(file_registry=registry)
    stack.addWidget(w)
    toolbar = FileToolbarWidget(stack, registry)
    labels = [label for label, _callback in toolbar._import_entries()]
    assert labels == ["Scan camera rows: battle_scan_cameras.bin or FF8 exe", "Scan text: battle_scans.msd"]
    toolbar._refresh()
    assert toolbar.import_complementary_button.isEnabled()
    side = [label for label, _callback in w.complementary_entries()]
    assert side[0].startswith("Game font: mngrp.bin") and side[1].startswith("Battle models:")
    assert side[2].startswith("Info bar texts: kernel.bin") and side[3].startswith("Info bar icons: icon.sp1")
    assert side[4].startswith("Stat board texture: mag039-067.tim")
    assert w.kernel_binding.read_only and w.icon_binding.read_only and w.scan_texture_binding.read_only

    models = tmp_path / "battle"
    models.mkdir()
    picked = [str(models / "c0m071.dat"), str(models / "d0c000.dat")]
    starts = []

    def fake_open_names(_parent, _caption, directory, _filter):
        starts.append(directory)
        return picked, ""
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", fake_open_names)
    w._import_models()
    w._import_models()
    assert set(w._model_paths) == {87, 0}
    assert starts[1] == str(models)  # the second dialog reopens in the models' folder

    exe_folder = tmp_path / "game"
    exe_folder.mkdir()
    (exe_folder / "FF8_EN.exe").write_bytes(b"MZ")
    camera_starts = []

    def fake_open_name(_parent, _caption, directory, _filter):
        camera_starts.append(directory)
        return str(exe_folder / "FF8_EN.exe"), ""
    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_open_name)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", lambda *args, **kwargs: None)  # not a real exe
    w._import_camera()
    w._import_camera()
    assert camera_starts[1] == str(exe_folder)
    assert registry.last_folder("FF8 exe") == str(exe_folder)  # shared with Cid/ShumiTranslator


def test_character_weapons_listed(widget, tmp_path):
    """Imported weapons (d?w###.dat) are listed for their character, first one selected; a
    monster row (or a character without imported weapons) hides the list."""
    w, _path = widget
    w.add_models([str(tmp_path / name) for name in ("d0w001.dat", "d0w000.dat", "d4w000.dat")])
    assert w._weapon_paths == {0: [str(tmp_path / "d0w000.dat"), str(tmp_path / "d0w001.dat")],
                               4: [str(tmp_path / "d4w000.dat")]}
    w.show()
    w.row_list.setCurrentRow(0)  # Squall
    combo = w.preview.weapon_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["No weapon", "d0w000.dat", "d0w001.dat"]
    assert combo.currentText() == "d0w000.dat" and not combo.isHidden()
    w.row_list.setCurrentRow(87)  # a monster
    assert combo.count() == 0 and combo.isHidden()
    w.hide()


def test_info_bar_needs_kernel_bin(widget):
    """No kernel.bin: no info bar line, a hint says which file to open."""
    w, _path = widget
    preview = w.preview
    assert preview.info_line() == b"" and not preview.info_combo.isEnabled()
    assert "kernel.bin" in preview.info_hint.text()


def test_info_bar_character_row(widget):
    """A character's row has only the level/HP line, with the level and HP picked by the user."""
    from tests.Xu.test_xuinfobar import synthetic_misc
    w, _path = widget
    preview = w.preview
    preview.set_info_texts(synthetic_misc(w.game_data))
    w.row_list.setCurrentRow(0)  # Squall
    assert preview.hp_spin.isVisibleTo(preview)
    preview.level_spin.setValue(9)
    preview.hp_spin.setValue(456)
    assert w.game_data.translate_hex_to_str(preview.info_line()) == "LV 9 PV 456/456"
    assert preview.info_combo.count() == 1
    w.row_list.setCurrentRow(87)  # a monster with no model open: no line, a hint
    assert preview.info_line() == b"" and ".dat" in preview.info_hint.text()


@pytest.mark.ff8data("extracted_files/main/kernel.bin", "extracted_files/battle/c0m005.dat", EXE,
                     "extracted_files/menu/icon.sp1")
def test_info_bar_pages_like_the_game(widget):
    """Belhelmel (c0m005): level/HP, Fly, its element lines and the AI's scan text; a line stays
    45 ticks, then the next one, wrapping."""
    import contextlib
    import io
    w, _path = widget
    w.exe_binding.open_path(EXE)
    w.kernel_binding.open_path("extracted_files/main/kernel.bin")
    w.icon_binding.open_path("extracted_files/menu/icon.sp1")
    w.row_list.setCurrentRow(5 + 16)
    preview = w.preview
    with contextlib.redirect_stdout(io.StringIO()):
        preview._manager = preview._new_manager("extracted_files/battle/c0m005.dat")
    preview._on_new_subject()
    labels = [preview.info_combo.itemText(i).split(" ", 1)[1] for i in range(preview.info_combo.count())]
    assert labels == ["Level and HP", "Fly monster", "Weak against (1)", "Strong against (1)",
                      "AI scan text (setScanText)"]
    assert preview.scan_text_combo.count() == 3  # none + the 2 texts its AI can set
    assert preview.info_hint.text() == ""        # texts, exe icon codes and icons all there
    medium = preview._manager.enemy.info_stat_data['med_lvl']
    assert preview.level_spin.value() == medium
    hp = w.game_data.translate_hex_to_str(preview.info_line())
    assert hp.startswith(f"LEVEL {medium} HP ")
    preview.animate_check.setChecked(True)
    for _tick in range(44):
        preview._advance_info_bar()
    assert preview.info_combo.currentIndex() == 0
    preview._advance_info_bar()
    assert preview.info_combo.currentIndex() == 1
    preview.info_combo.setCurrentIndex(4)
    for _tick in range(45):
        preview._advance_info_bar()
    assert preview.info_combo.currentIndex() == 0  # back to the first line


def test_background_needs_the_exe(widget):
    """No exe: no Scan screen models, a hint says so (a plain blue stands in)."""
    w, _path = widget
    assert w.preview._background is None
    assert "FF8 exe" in w.preview.background_hint.text()


@pytest.mark.ff8data(EXE, "extracted_files/magic/mag039-067.tim")
def test_background_from_the_opened_files(widget):
    """The exe gives the models, mag039-067.tim the stat board labels; the bars read the monster's
    stats at the level picked."""
    import contextlib
    import io
    w, _path = widget
    w.exe_binding.open_path(EXE)
    assert w.preview._background is not None and "mag039-067.tim" in w.preview.background_hint.text()
    w.scan_texture_binding.open_path("extracted_files/magic/mag039-067.tim")
    assert w.preview._background.texture is not None and not w.preview.background_hint.isVisibleTo(w.preview)
    w.row_list.setCurrentRow(43 + 16)  # Bomb
    preview = w.preview
    with contextlib.redirect_stdout(io.StringIO()):
        preview._manager = preview._new_manager("extracted_files/battle/c0m043.dat")
    preview._on_new_subject()
    values = preview._bar_values()
    stats = preview._manager.enemy.info_stat_data
    from FF8GameData.dat.monsterstatcurve import monster_hp, monster_stat
    level = preview.level_spin.value()
    assert values.hp == monster_hp(list(stats['hp'][:4]), level)
    assert values.spd == monster_stat('spd', list(stats['spd'][:4]), level)
    w.file_registry.close_file("mag039-067.tim")  # removed from the opened files: no board labels
    assert w.preview._background.texture is None
