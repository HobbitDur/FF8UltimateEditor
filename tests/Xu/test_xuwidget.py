"""Xu GUI: editing rows through the widget and saving them via the shared file binding."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp, tmp_path):
    from Xu.xumanager import XuManager
    from Xu.xuwidget import XuWidget
    path = tmp_path / "battle_scan_cameras.bin"
    XuManager().save_file(str(path))
    w = XuWidget()
    w.binding.open_path(str(path))
    return w, path


def test_edit_and_save(widget):
    w, path = widget
    assert w.editor_group.isEnabled()
    w.row_list.setCurrentRow(168)
    w._spinboxes["distance"].setValue(-5000)
    w._checkboxes["can_yaw"].setChecked(False)
    assert w.row_list.item(168).text().startswith("* ")
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
    assert w._spinboxes["distance"].value() == -18496
    w._reset_row()
    assert w.manager.is_vanilla(170)

    w.changed_only.setChecked(True)
    assert all(w.row_list.item(row).isHidden() for row in range(w.row_list.count()))
    w.changed_only.setChecked(False)
    w.filter_edit.setText("G-Soldier")
    visible = [row for row in range(w.row_list.count()) if not w.row_list.item(row).isHidden()]
    assert 87 in visible and len(visible) < 10


def test_scan_text_tab(widget, tmp_path):
    from Xu.xutext import XuTextManager
    w, _path = widget
    game_data = w.game_data
    texts = [bytes(game_data.translate_str_to_hex(f"Text {i}")) + b"\x00" for i in range(166)]
    import struct
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


def test_camera_edits_without_a_file_save_as(qapp, tmp_path, monkeypatch):
    """No camera file opened: the rows stay editable and Save asks where to write them."""
    from PyQt6.QtWidgets import QFileDialog
    from Xu.xumanager import XuManager
    from Xu.xuwidget import XuWidget
    w = XuWidget()
    assert w.editor_group.isEnabled() and not w.can_save_folder()
    w.row_list.setCurrentRow(168)
    w._spinboxes["distance"].setValue(-5000)
    assert w.can_save_folder()
    target = tmp_path / "battle_scan_cameras.bin"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    w.save_files()
    saved = XuManager()
    saved.load_file(str(target))
    assert saved.rows[168].distance == -5000
    assert w.binding.is_loaded and not w.can_save_folder()  # now saved into the opened file


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_default_msd_from_the_exe(qapp):
    """The default battle_scans.msd holds the exe's 160 texts, in com_id order."""
    from FF8GameData.gamedata import GameData
    from Xu.xutext import XuTextManager
    from Xu.xuwidget import build_msd_from_exe
    game_data = GameData("FF8GameData")
    manager = XuTextManager(game_data)
    manager.load_bytes(build_msd_from_exe(game_data, "extracted_files/FF8_EN.exe"))
    assert len(manager.texts) == 160
    assert manager.get_str(87).startswith("Galbadian soldier")  # G-Soldier
