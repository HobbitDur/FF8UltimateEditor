import struct
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings
from Common.fileregistry import FileRegistry
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QStackedWidget

from Julia.actorsoundtable import ActorSoundTable, world_sound_to_archive_id
from Julia.juliawidget import JuliaWidget
from Julia.juliamanager import FF8Sound, FORMAT_STRUCT, WAVEFMT_STRUCT
from Common.filetoolbarwidget import FileToolbarWidget


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("world_id,archive_id", [
    (400000, 1230), (400001, 1231), (210008, 158), (10000, 2150),
    (500000, 2784), (690000, 2060), (690001, 1961), (31, 31), (990123, 123),
])
def test_world_id_conversion(world_id, archive_id):
    assert world_sound_to_archive_id(world_id) == archive_id


def test_conversion_matches_existing_decoded_actor_slots():
    resource = json.loads((ROOT / "FF8GameData/Resources/json/battle_actor_sound.json").read_text())
    for row, values in resource["actor_world_sound_slots"].items():
        decoded = resource["actor_sound_slots"].get(row, [None] * 7)
        for slot, value in enumerate(values):
            if value:
                assert world_sound_to_archive_id(value) == decoded[slot]


@pytest.fixture
def table():
    return ActorSoundTable(ROOT / "FF8GameData/Resources/json")


def test_new_file_keeps_original_sounds_and_copies_new_monster(table, tmp_path):
    assert table.rows[87][0] == 400000
    assert all(row == [0] * 7 for row in table.rows[160:])
    table.copy_actor(87, 161)
    table.set_slot(161, 6, 0xFFFFFFFF)
    assert table.rows[87][6] != 0xFFFFFFFF
    path = tmp_path / "battle_actor_sounds.bin"
    table.save(path)
    data = path.read_bytes()
    assert len(data) == 6048
    assert struct.unpack_from("<I", data, (161 * 7) * 4)[0] == 400000
    assert data[(161 * 7 + 6) * 4:(161 * 7 + 7) * 4] == b"\xff" * 4
    other = ActorSoundTable(table.resource_folder)
    other.load(path)
    assert other.rows == table.rows


@pytest.mark.parametrize("length", [0, 4480, 6047, 6049])
def test_wrong_size_keeps_current_table(table, tmp_path, length):
    before = [row.copy() for row in table.rows]
    path = tmp_path / "wrong.bin"
    path.write_bytes(bytes(length))
    with pytest.raises(ValueError):
        table.load(path)
    assert table.rows == before


@pytest.mark.parametrize("value", [-1, 0x100000000])
def test_invalid_id_keeps_slot(table, value):
    before = table.rows[87][0]
    with pytest.raises(ValueError):
        table.set_slot(87, 0, value)
    assert table.rows[87][0] == before


def test_widget_copy_edit_save_and_active_file_binding(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        assert widget.file_bindings()[0].file_name == "audio.fmt"
        changes = []
        widget.file_bindings_changed.connect(lambda: changes.append(True))
        widget.tabs.setCurrentIndex(1)
        editor = widget.actor_sound_widget
        assert changes and widget.file_bindings() == [widget.audio_binding, widget.dat_binding, editor.binding]
        assert editor.binding.complementary and not editor.binding.read_only
        editor.copy_source.setCurrentIndex(87)
        editor.table.setCurrentCell(161, 2)
        editor.copy_button.click()
        assert editor.model.rows[161] == editor.model.rows[87]
        editor.table.item(161, 8).setText("4294967295")
        path = tmp_path / "battle_actor_sounds.bin"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
        widget.save_files()
        assert editor.binding.is_loaded
        assert not editor.dirty
        assert len(path.read_bytes()) == 6048
        assert editor.model.rows[161][6] == 0xFFFFFFFF
        editor.table.item(161, 2).setText("400001")
        editor.binding.save()
        assert struct.unpack_from("<I", path.read_bytes(), 161 * 28)[0] == 400001
        widget.tabs.setCurrentIndex(0)
        assert widget.file_bindings()[0].file_name == "audio.fmt"
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_widget_rejects_invalid_id_and_preserves_file_on_new_cancel(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        editor = widget.actor_sound_widget
        errors = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: errors.append(a[-1]))
        editor.table.item(87, 2).setText("4294967296")
        assert errors and editor.model.rows[87][0] == 400000
        editor.table.item(87, 2).setText("400001")
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
        editor.new_button.click()
        assert editor.model.rows[87][0] == 400001
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        editor.new_button.click()
        assert editor.model.rows[87][0] == 400000
        assert not editor.dirty
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_slot_preview_uses_shared_archive_player_and_updates_after_edit():
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        widget.tabs.setCurrentIndex(1)
        editor = widget.actor_sound_widget
        editor.table.setCurrentCell(87, 2)
        assert "#1230" in editor.preview_label.text()
        assert not editor.play_button.isEnabled()
        assert editor.binding.complementary
        calls = []
        sound = FF8Sound()
        sound.data_length = 2
        widget.manager.sounds = [sound] * 1232
        widget.manager.get_wav = lambda index: calls.append(("read", index)) or b"test wav"
        widget.player = SimpleNamespace(stop=lambda: calls.append("stop"),
                                        setSourceDevice=lambda *_args: calls.append("buffer"),
                                        play=lambda: calls.append("play"))
        editor.update_preview()
        editor.play_button.click()
        assert calls == [("read", 1230), "stop", "buffer", "play"]
        editor.table.item(87, 2).setText("400001")
        assert "#1231" in editor.preview_label.text()
        editor.play_button.click()
        assert ("read", 1231) in calls
        editor.table.setCurrentCell(87, 8)
        assert "Unused" in editor.preview_label.text()
        assert not editor.play_button.isEnabled()
        editor.table.item(87, 8).setText("4294967295")
        assert "outside" in editor.preview_label.text()
        assert not editor.play_button.isEnabled()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_fmt_import_registers_pair_and_enables_slot_preview(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        fmt = struct.pack("<H", 1)
        for offset in (0, 2):
            fmt += FORMAT_STRUCT.pack(2, offset, 0, 0, 0)
            fmt += WAVEFMT_STRUCT.pack(1, 1, 8000, 16000, 2, 16, 0)
        path = tmp_path / "audio.fmt"
        path.write_bytes(fmt)
        (tmp_path / "audio.dat").write_bytes(bytes(4))
        widget.tabs.setCurrentIndex(1)
        editor = widget.actor_sound_widget
        editor.table.setCurrentCell(161, 2)
        editor.table.item(161, 2).setText("1")
        assert not editor.play_button.isEnabled()
        widget.audio_binding.open_path(str(path))
        assert widget.manager.dat_path == str(tmp_path / "audio.dat")
        assert widget.dat_binding.is_loaded
        assert widget.manager.get_wav(1).startswith(b"RIFF")
        assert editor.play_button.isEnabled()
        assert "#1" in editor.preview_label.text()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_shared_toolbar_keeps_archive_main_bin_side_and_saves_active_tab(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, widget.audio_binding.registry)
    try:
        assert [binding.file_name for binding in toolbar._main_bindings()] == ["audio.fmt", "audio.dat"]
        assert toolbar._complementary_bindings() == [widget.actor_sound_widget.binding]
        calls = []
        monkeypatch.setattr(widget, "save_file", lambda: calls.append("archive pair"))
        monkeypatch.setattr(widget.actor_sound_widget, "save_file", lambda: calls.append("bin"))
        toolbar._save()
        widget.tabs.setCurrentIndex(1)
        assert toolbar.save_button.isEnabled()
        toolbar._save()
        assert calls == ["archive pair", "bin"]
        assert [binding.file_name for binding in toolbar._main_bindings()] == ["audio.fmt", "audio.dat"]
        assert not hasattr(widget.actor_sound_widget, "open_button")
        assert not hasattr(widget.actor_sound_widget, "save_as_button")
    finally:
        toolbar.close()
        toolbar.deleteLater()
        stack.close()
        stack.deleteLater()
        app.processEvents()


def test_selected_slot_explains_category_offset_base_and_special_cases():
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        editor = widget.actor_sound_widget
        editor.table.setCurrentCell(87, 2)
        editor.table.item(87, 2).setText("400025")
        assert {key: label.text() for key, label in editor.detail_values.items()} == {
            "world": "400025", "category": "40", "offset": "25", "base": "1230", "archive": "#1255"}
        assert not hasattr(editor, "formula_label")
        assert editor.detail_table.rowCount() == 5
        assert editor.category_table.item(editor.category_rows[40], 1).text() == "1230"
        editor.table.item(87, 2).setText("690001")
        assert editor.detail_values["base"].text() == "Special rule"
        assert editor.detail_values["archive"].text() == "#1961"
        editor.table.item(87, 2).setText("990123")
        assert editor.detail_values["base"].text() == "0"
        assert editor.detail_values["archive"].text() == "#123"
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_copy_and_new_reuse_existing_cells():
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        editor = widget.actor_sound_widget
        source_cell = editor.table.item(87, 2)
        target_cell = editor.table.item(161, 2)
        editor.table.setCurrentCell(161, 2)
        editor.copy_source.setCurrentIndex(87)
        editor.copy_selected()
        assert editor.table.item(87, 2) is source_cell
        assert editor.table.item(161, 2) is target_cell
        assert target_cell.text() == "400000"
        editor.dirty = False
        editor.new_file()
        assert editor.table.item(161, 2) is target_cell
        assert target_cell.text() == "0"
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_import_requires_the_archive_pair(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    try:
        errors = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: errors.append(a[-1]))
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (["audio.fmt"], ""))
        widget.import_files()
        assert errors and "both" in errors[0]
        assert not widget.manager.sounds
        assert not widget.audio_binding.current_path
        assert not widget.dat_binding.current_path
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_shared_save_creates_bin_without_touching_archive_files(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, widget.audio_binding.registry)
    try:
        widget.tabs.setCurrentIndex(1)
        editor = widget.actor_sound_widget
        path = tmp_path / "battle_actor_sounds.bin"
        fmt, dat = tmp_path / "audio.fmt", tmp_path / "audio.dat"
        fmt.write_bytes(b"preserve format")
        dat.write_bytes(b"preserve audio")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
        editor.table.item(161, 2).setText("400025")
        toolbar.save_button.click()
        assert len(path.read_bytes()) == 6048
        assert struct.unpack_from("<I", path.read_bytes(), 161 * 28)[0] == 400025
        assert fmt.read_bytes() == b"preserve format"
        assert dat.read_bytes() == b"preserve audio"
        assert editor.path == path
        editor.table.item(161, 2).setText("400001")
        assert toolbar.save_button.isEnabled()
        toolbar.save_button.click()
        assert struct.unpack_from("<I", path.read_bytes(), 161 * 28)[0] == 400001
    finally:
        toolbar.close()
        toolbar.deleteLater()
        stack.close()
        stack.deleteLater()
        app.processEvents()


def test_secondary_button_opens_bin_on_either_tab(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"))
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, widget.audio_binding.registry)
    try:
        path = tmp_path / "battle_actor_sounds.bin"
        model = ActorSoundTable(ROOT / "FF8GameData/Resources/json")
        model.set_slot(161, 0, 400025)
        model.save(path)
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
        assert toolbar.import_complementary_button.isEnabled()
        widget.tabs.setCurrentIndex(1)
        assert toolbar.import_complementary_button.isEnabled()
        toolbar.import_complementary_button.click()
        assert widget.actor_sound_widget.path == path
        assert widget.actor_sound_widget.table.item(161, 2).text() == "400025"
    finally:
        toolbar.close()
        toolbar.deleteLater()
        stack.close()
        stack.deleteLater()
        app.processEvents()


def test_archive_import_remembers_folder_in_next_session(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings_path = str(tmp_path / "settings.ini")
    settings = QSettings(settings_path, QSettings.Format.IniFormat)
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"), file_registry=FileRegistry(settings))
    try:
        fmt = tmp_path / "audio.fmt"
        dat = tmp_path / "audio.dat"
        fmt.write_bytes(struct.pack("<H", 0) + FORMAT_STRUCT.pack(2, 0, 0, 0, 0)
                        + WAVEFMT_STRUCT.pack(1, 1, 8000, 16000, 2, 16, 0))
        dat.write_bytes(bytes(2))
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(fmt), str(dat)], ""))
        widget.import_files()
        assert widget.audio_binding.is_loaded
        settings.sync()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
    registry = FileRegistry(QSettings(settings_path, QSettings.Format.IniFormat))
    widget = JuliaWidget(game_data_folder=str(ROOT / "FF8GameData"), file_registry=registry)
    try:
        folders = []
        def pick(*args, **kwargs):
            folders.append(args[2])
            return [], ""
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", pick)
        widget.import_files()
        assert folders == [str(tmp_path)]
        assert registry.last_folder("audio.dat") == str(tmp_path)
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
