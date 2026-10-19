"""Draw-editor interaction, file ownership and terrain regression tests."""
from pathlib import Path
import struct

import pytest
from PyQt6.QtCore import Qt, QPointF, QPoint, QEvent
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QWidget, QStackedWidget, QVBoxLayout

from Cid.cidwidget import CidWidget
from Cid.draw import Draw
from Cid.drawmapwidget import DrawMapWidget
from Cid.worlddrawgeometry import WorldDrawGeometry
from Cid.worlddrawsection import WorldDrawSection
from FF8GameData.gamedata import GameData
from Common.dirtytracking import install_dirty_tracking

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app):
    result = CidWidget(str(ROOT / 'Resources'), str(ROOT / 'FF8GameData'))
    yield result
    result.close()
    result.deleteLater()


def test_names_are_only_from_complementary_kernel_and_never_change_ids(widget, monkeypatch):
    draw = widget._draw_list[135]
    draw.magic_index = 1
    widget._draw_widget.set_draw(widget._draw_list)
    assert draw.get_magic_name() == ''
    assert widget._draw_widget.cellWidget(135, 1).currentText() == '1'
    assert not widget.kernel_binding._save_callback and widget.kernel_binding.read_only
    assert not widget.can_save_folder()
    monkeypatch.setattr('FF8GameData.kernelnames.read_names',
                        lambda *a, **k: {'magic': {1: 'Modded flame', 100: 'Beyond six bits'}})
    widget.load_kernel('test/kernel.bin')
    assert draw.get_magic_name() == 'Modded flame'
    assert widget._draw_widget.cellWidget(135, 1).currentText() == '1: Modded flame'
    assert widget._draw_widget.cellWidget(135, 1).count() == 64
    assert not widget._exe_dirty and not widget._wmset_dirty
    widget._exe_dirty = True
    widget._on_kernel_closed('test/kernel.bin')
    assert draw.magic_index == 1 and draw.get_magic_name() == ''
    assert widget._exe_dirty  # closing a reference file cannot discard edited draw data


def _mouse(view, kind, point, button=Qt.MouseButton.LeftButton, buttons=None):
    if buttons is None:
        buttons = button if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    event = QMouseEvent(kind, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, event)


def test_map_click_never_moves_and_any_marker_can_be_dragged_directly(app):
    view = DrawMapWidget('')
    view.resize(1280, 960)
    draw = Draw(GameData(str(ROOT / 'FF8GameData')), 136, bytearray())
    draw.set_block_xy(50, 35)
    draw.position_loaded = True
    draw.world_phases = (0, 1, 2, 3, 4)
    view.set_draw_list([draw])
    view.selection_picked.connect(view.set_selected)
    picked = QSignalSpy(view.position_picked)
    start = view._marker(draw, view._image_rect())
    target = view._block_to_point(60.5, 40.5, view._image_rect())
    for point in (start, target):
        _mouse(view, QEvent.Type.MouseButtonPress, point)
        _mouse(view, QEvent.Type.MouseButtonRelease, point)
    assert len(picked) == 0
    # Dragging empty map does not relocate the selected marker.
    _mouse(view, QEvent.Type.MouseButtonPress, target)
    _mouse(view, QEvent.Type.MouseMove, start, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, start)
    assert len(picked) == 0
    _mouse(view, QEvent.Type.MouseButtonPress, start)
    _mouse(view, QEvent.Type.MouseMove, target, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, target)
    assert list(picked) == [[60, 20, -1]]
    view.close()


def test_first_click_on_overlapping_markers_selects_then_later_clicks_cycle(app):
    view = DrawMapWidget('')
    draws = [Draw(GameData(str(ROOT / 'FF8GameData')), id, bytearray()) for id in (136, 137)]
    for draw in draws:
        draw.position_loaded, draw.world_phases = True, (0,)
        draw.set_block_xy(50, 35)
    view.set_draw_list(draws)
    view.selection_picked.connect(view.set_selected)
    picked = QSignalSpy(view.position_picked)
    point = view._marker(draws[0], view._image_rect())
    for expected in (0, 1, 0):
        _mouse(view, QEvent.Type.MouseButtonPress, point)
        _mouse(view, QEvent.Type.MouseButtonRelease, point)
        assert view._selected_index == expected
    assert not picked
    view.close()


def test_direct_drag_picks_the_nearest_marker_even_with_a_selected_neighbour(app):
    view = DrawMapWidget('')
    view.resize(1280, 960)
    draws = [Draw(GameData(str(ROOT / 'FF8GameData')), id, bytearray()) for id in (136, 137)]
    for bx, draw in zip((49, 50), draws):
        draw.position_loaded, draw.world_phases = True, (0,)
        draw.set_block_xy(bx, 35)
    view.set_draw_list(draws)
    view.set_selected(0)
    view.selection_picked.connect(view.set_selected)
    picked = QSignalSpy(view.position_picked)
    point = view._marker(draws[1], view._image_rect())
    target = view._block_to_point(60.5, 40.5, view._image_rect())
    _mouse(view, QEvent.Type.MouseButtonPress, point)
    _mouse(view, QEvent.Type.MouseMove, target, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, target)
    assert view._selected_index == 1
    assert list(picked) == [[60, 20, -1]]
    view.close()


def test_right_drag_pans_middle_click_resets_and_zoom_keeps_pointer_anchored(app):
    view = DrawMapWidget('')
    view.resize(1280, 960)
    draw = Draw(GameData(str(ROOT / 'FF8GameData')), 136, bytearray())
    draw.position_loaded, draw.world_phases = True, (0,)
    draw.set_block_xy(50, 35)
    view.set_draw_list([draw])
    view.set_selected(0)
    view.show()
    app.processEvents()
    original = (draw.x, draw.y, draw.sub_id)
    picked, selected = QSignalSpy(view.position_picked), QSignalSpy(view.selection_picked)
    point = view._marker(draw, view._image_rect())
    anchor = view._map_position(point, view._image_rect())
    guide_rect = view._guide.geometry()
    assert guide_rect.left() == int(view._map_viewport().right())
    wheel = QWheelEvent(point, point, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, wheel)
    assert view._zoom > 1
    assert view._map_position(point, view._image_rect()) == pytest.approx(anchor)
    before_pan = view._image_rect()
    delta = QPointF(40, -25)
    _mouse(view, QEvent.Type.MouseButtonPress, point, Qt.MouseButton.RightButton)
    _mouse(view, QEvent.Type.MouseMove, point + delta, Qt.MouseButton.NoButton, Qt.MouseButton.RightButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, point + delta, Qt.MouseButton.RightButton)
    assert view._image_rect().center() == before_pan.center() + delta
    assert view._hits(point + delta) == [0]
    assert not picked and not selected
    assert (draw.x, draw.y, draw.sub_id) == original
    assert view._guide.geometry() == guide_rect
    # The image can pan behind the guide, but its hidden markers cannot be hit there.
    guide_point = QPointF(guide_rect.center())
    _mouse(view, QEvent.Type.MouseButtonPress, point + delta, Qt.MouseButton.RightButton)
    _mouse(view, QEvent.Type.MouseMove, guide_point, Qt.MouseButton.NoButton, Qt.MouseButton.RightButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, guide_point, Qt.MouseButton.RightButton)
    assert (view._marker(draw, view._image_rect()) - guide_point).manhattanLength() == pytest.approx(0)
    assert view._hits(guide_point) == []
    assert not picked and not selected
    _mouse(view, QEvent.Type.MouseButtonPress, point, Qt.MouseButton.MiddleButton)
    _mouse(view, QEvent.Type.MouseButtonRelease, point, Qt.MouseButton.MiddleButton)
    assert view._zoom == 1 and view._pan == QPointF()
    assert view._image_rect().center() == view._map_viewport().center()
    assert not picked and not selected
    assert view._guide.geometry() == guide_rect
    view.close()


def test_only_loaded_positions_can_be_moved(widget):
    draw = widget._draw_list[135]
    widget._draw_widget.set_row_position(135, 10, 20, 5)
    assert (draw.x, draw.y, draw.sub_id) == (0, 0, 0)
    assert not widget._wmset_dirty


def test_closing_one_backing_file_preserves_edits_in_the_other(widget):
    world = widget._draw_list[135]
    world.position_loaded = True
    world.world_phases = (0, 1)
    world.x, world.y, world.sub_id = 50, 20, 7
    widget._wmset_dirty = True
    widget._on_exe_closed('FF8_EN.exe')
    assert (world.x, world.y, world.sub_id) == (50, 20, 7)
    assert world.position_loaded and widget._wmset_dirty
    world.magic_index = 5
    widget._exe_dirty = True
    widget._on_wmset_closed('wmsetus.obj')
    assert world.magic_index == 5 and widget._exe_dirty
    assert not world.position_loaded and not widget._wmset_dirty


def test_save_routes_to_the_edited_file_and_cancel_keeps_it_dirty(widget, monkeypatch):
    widget.exe_loaded = True
    monkeypatch.setattr(widget._section, 'is_loaded', lambda: True)
    calls = []
    monkeypatch.setattr(widget, '_save_hext', lambda: calls.append('hext') or True)
    monkeypatch.setattr(widget, '_save_wmset', lambda: calls.append('wmset') or False)
    widget._exe_dirty, widget._wmset_dirty = False, True
    widget._save()
    assert calls == ['wmset'] and widget._wmset_dirty
    calls.clear()
    widget._exe_dirty, widget._wmset_dirty = True, False
    widget._save()
    assert calls == ['hext'] and not widget._exe_dirty


def _wmset(tmp_path):
    data = bytearray(192 + 44 + 128 * 4)
    struct.pack_into('<48I', data, 0, *([192] * 35 + [len(data)] * 13))
    struct.pack_into('<11I', data, 192, 44, 512, 512, 516, 516, 520, 520, 528, 528, 552, 44)
    source = tmp_path / 'wmsetus.obj'
    source.write_bytes(data)
    return source


def test_world_phases_use_the_header_and_final_unused_slot_is_distinct(tmp_path):
    source = _wmset(tmp_path)
    section = WorldDrawSection()
    section.load(source)
    assert section.phases_for_record(7) == (0, 1, 2, 3, 4)  # 136 really is scanned
    assert section.phases_for_record(117) == (0,)  # 246
    assert section.phases_for_record(118) == (1, 2, 3, 4)  # 247, same location
    assert section.phases_for_record(127) == ()  # 256
    damaged = tmp_path / 'broken.obj'
    damaged.write_bytes(source.read_bytes()[:200])
    with pytest.raises(ValueError):
        section.load(damaged)
    out = tmp_path / 'roundtrip.obj'
    section.save(out)
    assert out.read_bytes() == source.read_bytes()


def test_phase_checkboxes_combine_variants_and_unused_without_recording_edits(widget, tmp_path):
    widget.load_wmset(str(_wmset(tmp_path)))
    checks, view = widget._phase_checks, widget._illustration.map
    dirty = install_dirty_tracking(widget)
    positions = [(d.x, d.y, d.sub_id) for d in widget._draw_list]
    for phase, count in enumerate((118, 118, 120, 126, 126)):
        for value, check in checks.items():
            if check.isChecked() != (value == phase):
                check.click()
        assert sum(view._visible(d) for d in widget._draw_list) == count
        assert f'{count} records' in checks[phase].toolTip()
        assert view._visible(widget._draw_list[245]) == (phase == 0)
        assert view._visible(widget._draw_list[246]) == (phase != 0)
    checks[4].click()
    checks[1].click()
    checks[2].click()
    assert sum(view._visible(d) for d in widget._draw_list) == 120  # union, without duplicate markers
    checks[DrawMapWidget.NO_PHASE].click()
    assert sum(view._visible(d) for d in widget._draw_list) == 121
    checks[1].click()
    checks[2].click()
    assert [d.get_id() for d in widget._draw_list if view._visible(d)] == [256]
    assert widget._draw_widget.currentRow() == 255
    assert widget._illustration._stack.currentWidget() is view
    assert view._hits(view._marker(widget._draw_list[255], view._image_rect())) == [255]
    assert '1 record' in checks[DrawMapWidget.NO_PHASE].toolTip()
    assert positions == [(d.x, d.y, d.sub_id) for d in widget._draw_list]
    assert not widget._exe_dirty and not widget._wmset_dirty
    assert not dirty.dirty and not widget._undo_stack.can_undo()
    checks[DrawMapWidget.NO_PHASE].click()
    assert not any(view._visible(d) for d in widget._draw_list)
    checks[DrawMapWidget.NO_PHASE].click()
    # Removing the slot from No phase updates the filter immediately, using the edited ranges.
    widget._groups_widget._last[4].setValue(256)
    assert not any(view._visible(d) for d in widget._draw_list)
    assert '0 records' in checks[DrawMapWidget.NO_PHASE].toolTip()
    widget._on_wmset_closed('wmsetus.obj')
    assert not any(view._visible(d) for d in widget._draw_list)
    assert checks[DrawMapWidget.NO_PHASE].toolTip() == 'No phase (unused)'


def test_field_and_phase_filters_hide_rows_without_changing_data_or_history(widget, tmp_path):
    widget.load_wmset(str(_wmset(tmp_path)))
    dirty = install_dirty_tracking(widget)
    before = widget._undo_capture()
    table = widget._draw_widget
    assert sum(not table.isRowHidden(row) for row in range(table.rowCount())) == 128 + 118
    widget._field_check.click()
    assert all(table.isRowHidden(row) for row in range(128))
    assert sum(not table.isRowHidden(row) for row in range(table.rowCount())) == 118
    widget._phase_checks[DrawMapWidget.NO_PHASE].click()
    widget._phase_checks[0].click()
    assert [row + 1 for row in range(table.rowCount()) if not table.isRowHidden(row)] == [256]
    widget._phase_checks[DrawMapWidget.NO_PHASE].click()
    assert all(table.isRowHidden(row) for row in range(table.rowCount()))
    assert table.currentRow() == -1 and widget._selected_row == -1
    widget._field_check.click()
    assert [row + 1 for row in range(table.rowCount()) if not table.isRowHidden(row)] == list(range(1, 129))
    widget._phase_checks[1].click()
    widget._phase_checks[2].click()
    assert sum(not table.isRowHidden(row) for row in range(table.rowCount())) == 128 + 120
    assert widget._undo_capture() == before and not widget._undo_stack.can_undo()
    assert not dirty.dirty and not widget._exe_dirty and not widget._wmset_dirty
    widget._on_wmset_closed('wmsetus.obj')
    # EXE-only editing still exposes world slots, whose phase membership is unknown.
    assert sum(not table.isRowHidden(row) for row in range(table.rowCount())) == 256


def test_direct_drag_supports_real_undo_redo_shortcuts_and_saved_state(widget, app, tmp_path, monkeypatch):
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget

    class UndoHost(FF8UltimateEditorWidget):
        def __init__(self, tool):
            QWidget.__init__(self)
            self.tool_stack = QStackedWidget(self)
            self.tool_stack.addWidget(tool)
            QVBoxLayout(self).addWidget(self.tool_stack)

    source = _wmset(tmp_path)
    data = bytearray(source.read_bytes())
    struct.pack_into('BBB', data, 192 + 44 + 7 * 4, 178, 17, 31)
    source.write_bytes(data)
    widget.load_wmset(str(source))
    dirty = install_dirty_tracking(widget)
    host = UndoHost(widget)
    host.resize(1280, 1000)
    app.installEventFilter(host)
    host.show()
    app.processEvents()
    try:
        widget._draw_widget.setCurrentCell(128, 0)  # a different marker is selected
        view, draw = widget._illustration.map, widget._draw_list[135]
        start = view._marker(draw, view._image_rect())
        target = view._block_to_point(60.5, 40.5, view._image_rect())
        _mouse(view, QEvent.Type.MouseButtonPress, start)
        _mouse(view, QEvent.Type.MouseMove, target, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        _mouse(view, QEvent.Type.MouseButtonRelease, target)
        assert widget._draw_widget.currentRow() == 135
        assert (draw.x, draw.y, draw.sub_id) == (60, 20, 31)
        assert widget._wmset_dirty and dirty.dirty and not widget._exe_dirty
        QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert (draw.x, draw.y, draw.sub_id) == (178, 17, 31)
        assert [widget._draw_widget.cellWidget(135, col).value() for col in (4, 5, 6)] == [178, 17, 31]
        assert not widget._wmset_dirty and not dirty.dirty
        assert not widget._undo_stack.can_undo()  # a whole drag was one step
        QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        assert (draw.x, draw.y, draw.sub_id) == (60, 20, 31)
        saved = tmp_path / 'saved.obj'
        monkeypatch.setattr(widget._save_wmset_dialog, 'getSaveFileName', lambda **kw: (str(saved), ''))
        widget.save_folder()
        assert not widget._wmset_dirty
        QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert widget._wmset_dirty  # the saved state was the moved position
        QTest.keyClick(view, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        assert not widget._wmset_dirty
        reloaded = WorldDrawSection()
        reloaded.load(saved)
        assert reloaded.records[7][:3] == [60, 20, 31]
    finally:
        app.removeEventFilter(host)
        host.tool_stack.removeWidget(widget)
        widget.setParent(None)
        host.close()
        host.deleteLater()


def test_geometry_uses_polygon_index_and_resolves_drop_to_triangle(tmp_path):
    data = bytearray(768 * 0x9000)
    struct.pack_into('<I', data, 4, 68)
    struct.pack_into('BBB', data, 68, 2, 4, 0)
    data[72:75] = bytes((0, 1, 2))
    data[88:91] = bytes((1, 3, 2))
    for i, (x, z) in enumerate(((0, 0), (2048, 0), (0, -2048), (2048, -2048))):
        struct.pack_into('<hhhh', data, 104 + i * 8, x, 0, z, 0)
    source = tmp_path / 'wmx.obj'
    source.write_bytes(data)
    geometry = WorldDrawGeometry(source)
    assert geometry.pick(.1, .1) == (0, 0, 0)
    assert geometry.pick(.9, .9) == (0, 0, 1)
    assert geometry.triangles(0, 0)[1] == ((1, 0), (1, 1), (0, 1))


@pytest.mark.ff8data('extracted_files/world/dat/wmsetus.obj', 'extracted_files/world/dat/wmx.obj')
def test_real_world_inventory_and_terrain(widget):
    source = ROOT / 'extracted_files/world/dat/wmsetus.obj'
    before = source.read_bytes()
    widget.wmset_binding.open_path(str(source))
    # The sibling terrain is registered as a complementary read-only file automatically.
    assert Path(widget.wmx_binding.current_path) == ROOT / 'extracted_files/world/dat/wmx.obj'
    assert widget.wmx_binding.read_only
    world = widget._draw_list[128:]
    assert len(world) == 128
    assert sum(bool(draw.world_phases) for draw in world) == 127
    assert len({(draw.x, draw.y, draw.sub_id) for draw in world if draw.world_phases}) == 126
    assert sum(draw.get_location() == 'Island Closest to Heaven' for draw in world) == 28
    assert sum(draw.get_location() == 'Island Closest to Hell' for draw in world) == 33
    assert 'Yaulny' in widget._draw_list[135].get_location()
    assert all(widget._illustration.map.geometry.triangle(draw) is not None for draw in world)
    assert widget._illustration.map._pixmap.size().width() == 1024  # terrain-derived overview
    assert not widget._exe_dirty and not widget._wmset_dirty
    assert source.read_bytes() == before
    geometry = widget._illustration.map.geometry
    preview = widget._undo_capture()
    view = widget._illustration.map
    dirty = install_dirty_tracking(widget)
    assert view.mesh_check.isEnabled()
    view.mesh_check.click()
    assert view.mesh_check.isChecked() and view._mesh_pixmap.width() == 4096
    vertex = geometry.triangle(widget._draw_list[135])[0]
    assert view._mesh_pixmap.toImage().pixelColor(round(vertex[0] * 32), round(vertex[1] * 32)).alpha() > 0
    view.grab()  # exercise overlay painting at the map's current pan/zoom
    view.mesh_check.click()
    assert widget._undo_capture() == preview and not widget._undo_stack.can_undo()
    assert not dirty.dirty
    draw = widget._draw_list[135]  # Yaulny Canyon uses its actual triangle, not the centre of its block.
    rect = widget._illustration.map._image_rect()
    point = widget._illustration.map._marker(draw, rect)
    position = widget._illustration.map._map_position(point, rect)
    assert geometry.pick(*position) == (draw.x, draw.y, draw.sub_id)
    bx, by = draw.get_block_xy()
    assert position != (bx + .5, by + .5)
    original_position = (draw.x, draw.y, draw.sub_id)
    destination = widget._draw_list[165]
    target = widget._illustration.map._marker(destination, rect)
    _mouse(widget._illustration.map, QEvent.Type.MouseButtonPress, point)
    _mouse(widget._illustration.map, QEvent.Type.MouseMove, target,
           Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    _mouse(widget._illustration.map, QEvent.Type.MouseButtonRelease, target)
    assert (draw.x, draw.y, draw.sub_id) == (destination.x, destination.y, destination.sub_id)
    assert widget._wmset_dirty
    assert widget.undo()
    assert (draw.x, draw.y, draw.sub_id) == original_position
    assert widget._illustration.map._marker(draw, rect) == point
    assert not widget._wmset_dirty and source.read_bytes() == before
    widget.wmx_binding.registry.close_file('wmx.obj')
    assert widget._illustration.map.geometry is None
    assert not view.mesh_check.isEnabled() and not view.mesh_check.isChecked()
    assert 'approximate block centres' in widget._map_status.text()


@pytest.mark.ff8data('kernel.bin')
def test_real_kernel_names_are_read_only(widget):
    source = ROOT / 'kernel.bin'
    before = source.read_bytes()
    widget.load_kernel(str(source))
    assert widget.game_data.kernel_names['magic'][1] == 'Fire'
    assert not widget.can_save_folder()
    assert source.read_bytes() == before
