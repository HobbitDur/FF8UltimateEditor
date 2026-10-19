"""Draw-editor interaction, file ownership and terrain regression tests."""
from pathlib import Path
import struct

import pytest
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

from Cid.cidwidget import CidWidget
from Cid.draw import Draw
from Cid.drawmapwidget import DrawMapWidget
from Cid.worlddrawgeometry import WorldDrawGeometry
from Cid.worlddrawsection import WorldDrawSection
from FF8GameData.gamedata import GameData

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


def test_map_click_never_moves_and_drag_must_start_on_selected_marker(app):
    view = DrawMapWidget('')
    view.resize(1280, 960)
    draw = Draw(GameData(str(ROOT / 'FF8GameData')), 136, bytearray())
    draw.set_block_xy(50, 35)
    draw.position_loaded = True
    draw.world_phases = (0, 1, 2, 3, 4)
    view.set_draw_list([draw])
    view.set_selected(0)
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
    widget.load_wmset(str(ROOT / 'extracted_files/world/dat/wmsetus.obj'))
    widget.load_wmx(str(ROOT / 'extracted_files/world/dat/wmx.obj'))
    world = widget._draw_list[128:]
    assert len(world) == 128
    assert sum(bool(draw.world_phases) for draw in world) == 127
    assert len({(draw.x, draw.y, draw.sub_id) for draw in world if draw.world_phases}) == 126
    assert sum(draw.get_location() == 'Island Closest to Heaven' for draw in world) == 28
    assert sum(draw.get_location() == 'Island Closest to Hell' for draw in world) == 33
    assert 'Yaulny' in widget._draw_list[135].get_location()
    assert all(widget._illustration.map.geometry.triangle(draw) is not None for draw in world)
    assert widget._illustration.map._pixmap.size().width() == 1024  # terrain-derived overview


@pytest.mark.ff8data('kernel.bin')
def test_real_kernel_names_are_read_only(widget):
    source = ROOT / 'kernel.bin'
    before = source.read_bytes()
    widget.load_kernel(str(source))
    assert widget.game_data.kernel_names['magic'][1] == 'Fire'
    assert not widget.can_save_folder()
    assert source.read_bytes() == before
