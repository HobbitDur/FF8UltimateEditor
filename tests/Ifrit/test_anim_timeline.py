"""Ifrit3D timeline: the dope sheet widget, and the whole loop on a real file (edit -> dot ->
click -> revert -> saved file identical to the original)."""
import pathlib
import sys

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.animdiff import ROW_POSITION, diff_animation, diff_animations, snapshot_animations
from Ifrit.Ifrit3D.animtimelinewidget import (AnimTimelinePanel, DopeSheetView, describe_cell,
                                             dot_radius)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _frame(rx=0):
    return (0, 0, 0), ((0, 0, 0), (rx, 0, 0)), None


def test_dot_grows_with_the_change():
    assert dot_radius(1.0) < dot_radius(10.0) < dot_radius(90.0)


def test_sheet_hit_testing_and_clicks(qapp):
    sheet = DopeSheetView()
    sheet.resize(600, 200)
    sheet.set_rows([(0, "0 · Root", 0, "Root"), (1, "1 · Head", 1, "Head")])
    diff = diff_animation(0, [_frame(), _frame(200)], [_frame(), _frame()])
    sheet.set_animation(2, diff, can_revert=True)
    # rows: summary, position, bone 0, bone 1 -> bone 1 is the 4th row
    pos = QPoint(sheet.NAME_WIDTH + 18 + 5, sheet.HEADER_HEIGHT + 3 * sheet.ROW_HEIGHT + 5)
    assert sheet.hit(pos) == (1, 3)
    assert sheet.hit(QPoint(10, sheet.HEADER_HEIGHT + 5)) == (-1, 0)       # name column
    assert sheet.row_label(1) == "1 · Head"
    assert "rotation X +17.6°" in describe_cell(diff, 1, 1, "1 · Head")
    assert "same as the reference" in describe_cell(diff, 0, 1, "0 · Root")
    sheet.grab()                                                           # paints without error


def test_double_click_a_name_renames_the_bone(qapp):
    sheet = DopeSheetView()
    sheet.resize(600, 200)
    sheet.set_rows([(0, "0 · Root", 0, "Root"), (1, "1 · Head", 1, "Head")])
    renamed = []
    sheet.bone_renamed.connect(lambda bone, name: renamed.append((bone, name)))
    sheet.start_rename(1)
    assert sheet._rename_edit.text() == "Head"
    sheet._rename_edit.setText("Lion head")
    sheet._rename_edit.editingFinished.emit()
    assert renamed == [(1, "Lion head")]
    # Escape cancels: nothing renamed
    sheet.start_rename(0)
    from PyQt6.QtCore import Qt as _Qt
    from PyQt6.QtGui import QKeyEvent
    sheet._rename_edit.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, _Qt.Key.Key_Escape,
                                               _Qt.KeyboardModifier.NoModifier))
    assert renamed == [(1, "Lion head")] and sheet._rename_edit is None


def test_panel_overview_texts(qapp):
    panel = AnimTimelinePanel()
    diffs = diff_animations([[_frame()], [_frame(5)], [_frame()]], [[_frame()], [_frame()]])
    panel.set_overview(3, diffs, 1, "File as opened")
    assert panel.summary_label.text() == "1 of 3 animations changed, 1 new vs File as opened"
    panel.set_animation_status(diffs[1])
    assert panel.status_label.text() == "1 frames, 1 rows changed"
    panel.set_animation_status(diffs[2])
    assert panel.status_label.text() == "This animation is not in the reference"


@pytest.mark.ff8data("extracted_files/battle/c0m012.dat")
def test_edit_click_revert_on_a_real_file(qapp, tmp_path):
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

    source = BATTLE_DIR / "c0m012.dat"
    manager = IfritManager()
    manager.init_from_file(str(source))
    widget = Ifrit3DWidget(manager)
    widget.load_file()
    panel = widget.timeline_panel
    panel.set_expanded(True)
    assert panel.summary_label.text().startswith("0 of ")

    # An edit through the bone editor shows on that bone, from that frame
    widget.bone_editor.propagate_rotation_cb.setChecked(False)
    widget._on_animation_rotation_changed(0, 2, 5, 30.0, 0.0, 0.0)
    widget.bone_editor.animation_rotation_changed.emit(0, 2, 5, 30.0, 0.0, 0.0)
    diff = widget._timeline_diffs[0]
    assert set(diff.cells) == {(5, 2)}
    assert panel.strip._status(0) == "changed"

    # Clicking the cell shows that frame with that bone selected
    widget._on_timeline_cell_clicked(2, 5, False)
    assert widget.current_frame == 2 and widget._selected_bone_ids == [5]

    # A model position edit too, then revert everything: back to the original, also once saved
    manager.enemy.animation_data.animations[0].frames[1].position[0].move_raw(7)
    widget.model_edited.emit()
    assert (ROW_POSITION, 1) in widget._timeline_diffs[0].cells
    widget._timeline_revert(list(widget._timeline_diffs[0].cells))
    assert not widget._timeline_diffs[0].cells
    saved = tmp_path / "c0m012.dat"
    manager.save_enemy(manager.enemy, str(saved))
    reloaded = snapshot_animations(IfritManager().parse_file(str(saved)).animation_data)
    original = snapshot_animations(IfritManager().parse_file(str(source)).animation_data)
    assert all(d.status == "same" for d in diff_animations(reloaded, original))

    # A vanilla reference picked by hand
    widget._timeline_add_vanilla(str(source))
    assert panel.reference_combo.currentText() == "Vanilla: c0m012.dat"


@pytest.mark.ff8data("extracted_files/battle/c0m012.dat")
def test_full_view_hides_the_ifrit_surroundings(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from Ifrit import ifritmonsterwidget as imw

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = imw.IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    widget._ask_ram_budget = lambda *a: True
    widget.load_file(str(BATTLE_DIR / "c0m012.dat"))
    pane = widget._files[widget._active_index]['pane']
    view = pane._3d_widget
    view.full_view_btn.setChecked(True)
    assert widget._left_panel.isHidden() and widget._toolbar.isHidden()
    assert pane._tabs.tabBar().isHidden()
    assert view.full_view_btn.text() == "⛶ Restore"
    view.full_view_btn.setChecked(False)
    assert not widget._left_panel.isHidden() and not widget._toolbar.isHidden()
    assert not pane._tabs.tabBar().isHidden()
    # A file closed (pane torn down) while in full view gives the surroundings back
    view.full_view_btn.setChecked(True)
    widget._destroy_current_pane()
    assert not widget._left_panel.isHidden() and not widget._toolbar.isHidden()
    widget.close()
