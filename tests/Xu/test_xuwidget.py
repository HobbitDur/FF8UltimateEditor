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
