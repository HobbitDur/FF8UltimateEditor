"""Landscape data, real palette mapping, and read-only map interactions."""
from pathlib import Path
import struct
import time

import pytest
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, QThreadPool, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QMouseEvent, QPixmap
from PyQt6.QtTest import QTest, QSignalSpy
from PyQt6.QtWidgets import QApplication

from Cid.cidwidget import CidWidget
from Cid.drawmapwidget import DrawMapWidget
from Cid.worlddrawgeometry import WorldDrawGeometry
from Cid.worldlandscape import WorldLandscape, WorldTextures, section_bytes
from Cid.terrainrender import render_textured_png
from Common.dirtytracking import install_dirty_tracking
from FF8GameData.gamedata import GameData
from FF8GameData.tim.timfile import PalettedTim

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _wmset(sections):
    data = bytearray(192)
    for index in range(48):
        struct.pack_into('<I', data, index * 4, len(data))
        data += sections.get(index, bytes(4))
    return bytes(data)


def _archive(entries):
    offset = 4 * (len(entries) + 1)
    table = bytearray()
    for entry in entries:
        table += struct.pack('<I', offset)
        offset += len(entry)
    return bytes(table) + bytes(4) + b''.join(entries)


def _textures():
    rows = [[0, 0x001F, 0x8000] + [0] * 13 for _ in range(32)]
    rows[16][1] = 0x03E0  # other half of the same low-res page uses another CLUT row
    pixels = bytes([2] + [1] * 255) * 128
    land = PalettedTim(0, 0, 224, rows, 0, 256, 256, 128, pixels).to_bytes()
    sea = PalettedTim(1, 0, 0, [[0, 0x7C00] + [0] * 254], 768, 384, 64, 64, bytes([1]) * 4096).to_bytes()
    road = PalettedTim(0, 0, 0, [[0, 0x03FF] + [0] * 14], 832, 256, 4, 4, bytes([1]) * 16).to_bytes()
    return WorldTextures(_wmset({37: _archive([land] * 16 + [sea] * 8), 38: _archive([road])}))


def test_terrain_inspection_interpolates_height_and_slope_and_preserves_unknown_ground(tmp_path):
    data = bytearray(768 * 0x9000)
    struct.pack_into('<I', data, 4, 68)
    struct.pack_into('BBB', data, 68, 1, 3, 0)
    data[72:75] = bytes((0, 1, 2))
    data[85] = 199  # unknown IDs must remain numeric, not assigned a guessed terrain name
    for index, vertex in enumerate(((0, 0, 0), (2048, -2048, 0), (0, 0, -2048))):
        struct.pack_into('<hhhh', data, 88 + index * 8, *vertex, 0)
    path = tmp_path / 'wmx.obj'
    path.write_bytes(data)
    geometry = WorldDrawGeometry(path)
    info = geometry.terrain_at(.25, .25)
    assert info['ground'] == 199 and info['triangle'] == 0
    assert info['height'] == pytest.approx(512)
    assert info['slope'] == pytest.approx(45)
    assert geometry.terrain_at(.9, .9) is None
    assert geometry.terrain_at(-1, 0) is None
    assert geometry.terrain_at(.25, .25, 12) is None
    assert path.read_bytes() == data


def test_optional_region_grids_and_bad_textures_do_not_block_metadata():
    game = GameData(str(ROOT / 'FF8GameData'))
    game.load_field_data()
    regions, locations = bytearray([255] * 768), bytearray(768)
    index = 35 // 4 * 32 + 50 // 4
    regions[index], locations[index] = 2, 10
    source = _wmset({1: regions, 18: locations})
    landscape = WorldLandscape(source, game)
    info = landscape.location_at(50.3, 35.4)
    assert info['region_name'] == 'Timber' and info['region'] == 2
    assert info['location_name'] == 'Timber- Yaulny Canyon'
    assert landscape.location_at(128, 96) == {}
    assert landscape.textures is None and landscape.texture_error
    empty = WorldLandscape(bytes(192), game)
    assert empty.location_at(0, 0)['region'] is None
    with pytest.raises(ValueError):
        section_bytes(bytes(192), 37)


def test_low_res_texture_pages_select_the_correct_palette_and_keep_stp_black_opaque(app):
    land, sea, roads = _textures().images()
    assert land[0, 0].pixelColor(20, 20).getRgb() == (255, 0, 0, 255)
    assert land[1, 0].pixelColor(20, 20).getRgb() == (0, 255, 0, 255)
    assert land[0, 0].pixelColor(0, 20).getRgb() == (0, 0, 0, 255)
    assert sea.pixelColor(20, 20).getRgb() == (0, 0, 255, 255)
    assert roads.pixelColor(1, 1).getRgb() == (255, 255, 0, 255)


@pytest.mark.parametrize('texture_id,flags,expected', [
    (0x00, 0x80, (255, 0, 0)), (0x10, 0x80, (0, 255, 0)),
    (0x00, 0x40, (0, 0, 255)), (0x00, 0x20, (255, 255, 0)),
])
def test_raster_uses_triangle_uvs_and_distinguishes_land_water_and_roads(app, texture_id, flags, expected):
    class Geometry:
        data = bytes(4) + bytes((0, 1, 2, 0, 0, 0, 0, 0, 32, 0, 0, 32, texture_id, 6, flags, 0))

        def read_block(self, x, y):
            return 0, [(0, 0, 0), (2048, 0, 0), (0, 0, -2048)], int(x == 0 and y == 0)

    data = render_textured_png(Geometry(), _textures(), scale=8)
    image = QImage.fromData(data)
    assert image.size().width() == 1024
    assert image.pixelColor(2, 2).getRgb()[:3] == expected
    assert image.pixelColor(6, 6).getRgb()[:3] == (28, 55, 120)  # outside triangle stays untouched
    assert render_textured_png(Geometry(), _textures(), cancelled=lambda: True, scale=8) == b''


@pytest.mark.ff8data('extracted_files/world/dat/wmsetus.obj', 'extracted_files/world/dat/wmx.obj')
def test_real_landscape_hover_texture_render_and_source_lifecycle_stay_read_only(app):
    widget = CidWidget(str(ROOT / 'Resources'), str(ROOT / 'FF8GameData'))
    source = ROOT / 'extracted_files/world/dat/wmsetus.obj'
    before_source = source.read_bytes()
    try:
        widget.wmset_binding.open_path(str(source))
        widget.resize(1450, 950)
        widget.show()
        app.processEvents()
        view = widget._illustration.map
        dirty = install_dirty_tracking(widget)
        before = widget._undo_capture()
        positions = [(draw.x, draw.y, draw.sub_id) for draw in widget._draw_list]
        assert view.textures_check.isChecked() and view.textures_check.isEnabled()
        assert view._texture_tasks  # the default view starts rendering as soon as both sources exist
        assert not widget._fullscreen_button.isChecked() and widget._selected_row == -1
        geometry = view.geometry
        draw = widget._draw_list[135]
        triangle = geometry.triangle(draw)
        x, y = (sum(vertex[axis] for vertex in triangle) / 3 for axis in range(2))
        info = geometry.terrain_at(x, y, draw.sub_id)
        assert info['ground'] == 27 and info['height'] > 0 and info['slope'] > 0
        assert view.landscape.location_at(x, y)['location_name'] == 'Timber- Yaulny Canyon'
        point = view._block_to_point(x, y, view._image_rect())
        event = QMouseEvent(QEvent.Type.MouseMove, point, view.mapToGlobal(point.toPoint()).toPointF(),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        selected, moved = QSignalSpy(view.selection_picked), QSignalSpy(view.position_picked)
        QApplication.sendEvent(view, event)
        assert 'Railway (27)' in view.terrain_info.text() and 'Yaulny' in view.terrain_info.text()
        assert not selected and not moved and widget._selected_row == -1
        beats = []
        timer = QTimer()
        timer.timeout.connect(lambda: beats.append(True))
        timer.start(20)
        view._zoom, view._pan = 2., QPointF(40, -20)
        rect = view._image_rect()
        deadline = time.monotonic() + 40
        while view._texture_tasks and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        timer.stop()
        app.processEvents()
        assert not view._texture_tasks and not view._textured_pixmap.isNull(), view._texture_status.toolTip()
        assert len(beats) > 2  # event loop stayed live while rendering
        assert view._pixmap.width() == 4096 and view._image_rect() == rect
        view.grab()
        QTest.mouseClick(view.textures_check, Qt.MouseButton.LeftButton)
        assert view._pixmap.width() == 1024 and view._image_rect() == rect
        QTest.mouseClick(view.textures_check, Qt.MouseButton.LeftButton)
        assert view._pixmap.width() == 4096 and not view._texture_tasks  # cached
        assert not dirty.dirty and not widget._undo_stack.can_undo()
        assert widget._undo_capture() == before
        assert positions == [(draw.x, draw.y, draw.sub_id) for draw in widget._draw_list]
        widget.wmx_binding.registry.close_file('wmx.obj')
        assert not view.textures_check.isEnabled() and not view.textures_check.isChecked()
        assert view._textured_pixmap.isNull() and 'Load wmx' in view.terrain_info.text()
        assert view.landscape is not None  # wmset metadata survives terrain closing
        widget._on_wmset_closed(str(source))
        assert view.landscape is None and source.read_bytes() == before_source
    finally:
        for task in widget._illustration.map._texture_tasks.values():
            task.cancelled.set()
        QThreadPool.globalInstance().waitForDone(5000)
        widget.close()
        widget.deleteLater()


def test_stale_texture_results_cannot_replace_a_new_source(app):
    view = DrawMapWidget('')
    view.set_landscape(None)
    generation = view._render_generation
    view.set_geometry(None)
    assert view._render_generation != generation
    original = QPixmap(view._pixmap)
    old_image = QImage(4, 4, QImage.Format.Format_RGB32)
    old_image.fill(Qt.GlobalColor.red)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert old_image.save(buffer, 'PNG')
    view._on_textures_ready(generation, bytes(buffer.data()), '')
    assert view._pixmap.cacheKey() == original.cacheKey()
    assert view._textured_pixmap.isNull() and not view.textures_check.isChecked()
    view.close()
