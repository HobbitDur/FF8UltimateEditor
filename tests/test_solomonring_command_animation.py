"""Original direct-command animation references and read-only imported battle files."""
from pathlib import Path

import pytest
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase

from Common.dirtytracking import install_dirty_tracking
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from FF8GameData.dat.sequencecodec import sequence_to_code, code_to_sequence
from FF8GameData.dat.animloopdetector import find_character_weapon_file_list
from SolomonRing.commandanimationpanel import CommandAnimationPanel
from SolomonRing.solomonringwidget import SolomonRingWidget


ROOT = Path(__file__).parent.parent
BODY = ROOT / 'extracted_files/battle/d0c000.dat'
WEAPON = ROOT / 'extracted_files/battle/d0w000.dat'
MONSTER = ROOT / 'extracted_files/battle/c0m000.dat'
KERNEL = ROOT / 'extracted_files/main/kernel.bin'
pytestmark = pytest.mark.ff8data(*(str(p.relative_to(ROOT)) for p in (BODY, WEAPON, MONSTER, KERNEL)))


@pytest.fixture(scope='module')
def app():
    application = QApplication.instance() or QApplication([])
    old_font = application.font()
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
        application.setFont(QFont('Segoe UI', 9))
    yield application
    application.setFont(old_font)


@pytest.fixture(scope='module')
def game_data():
    data = GameData(str(ROOT / 'FF8GameData'))
    data.load_all()
    return data


def test_original_profiles_and_missing_sections(app, game_data):
    panel = CommandAnimationPanel(game_data, FileRegistry())
    panel.set_command(25)
    assert not panel.isHidden()
    assert panel.seq_value.text() == '11'
    assert panel.cam_value.text() == '0–5 (random)'
    assert '(previous + 2 + random(0–3)) % 6' in panel.cam_algorithm.text()
    assert '0, 2 or 4' in panel.cam_algorithm.text()
    assert 'low-HP, Poison, Sleep or Curse' in panel.cam_algorithm.text()
    assert 'on-model target selection' in panel.cam_algorithm.text()
    assert [panel.cam_choice.itemData(i) for i in range(panel.cam_choice.count())] == list(range(6))
    assert panel.seq_code.isReadOnly()
    assert not panel.preview_button.isEnabled()
    panel.set_command(23)
    assert panel.seq_value.text() == '23' and panel.cam_value.text() == 'None'
    assert 'does not select' in panel.cam_algorithm.text()
    assert panel.cam_choice.count() == 0 and not panel.preview_button.isEnabled()
    panel.set_command(31)
    assert panel.seq_value.text() == '24'
    assert '6 + random(0–1)' in panel.cam_algorithm.text()
    assert 'can also start' in panel.cam_algorithm.text()
    assert [panel.cam_choice.itemData(i) for i in range(panel.cam_choice.count())] == [6, 7]
    for command in (2, 7, 29, 39, None):
        panel.set_command(command)
        assert panel.isHidden()
    for execution_type, seq in ((0, 11), (24, 11), (25, 11), (23, 23), (31, 24)):
        panel.set_command(39, execution_type)
        assert not panel.isHidden()
        assert panel.seq_value.text() == str(seq)
    panel.set_command(39, 39)
    assert panel.isHidden()


def test_body_camera_and_weapon_seq_code_are_read_only(app, game_data, monkeypatch):
    from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel

    registry = FileRegistry()
    panel = CommandAnimationPanel(game_data, registry)
    panel.set_command(25)
    before = {path: path.read_bytes() for path in (BODY, WEAPON)}
    panel.import_character(BODY)
    assert not hasattr(panel, 'cam_source')
    assert panel._character['path'] == str(BODY)
    weapons = [p for p in find_character_weapon_file_list(BODY) if p.stat().st_size]
    assert [panel.seq_source.itemData(i) for i in range(panel.seq_source.count())] == [p.name for p in weapons]
    assert panel.seq_source.currentData() == WEAPON.name
    enemy = panel._sources[WEAPON.name]['manager'].enemy
    sequence = next(seq for seq in enemy.seq_animation_data['seq_animation_data'] if seq['id'] == 11)
    expected = sequence_to_code(game_data, sequence['data'])
    assert panel.seq_code.toPlainText() == expected
    assert code_to_sequence(game_data, expected) == sequence['data']
    assert all(binding.read_only for binding in panel.file_bindings())
    assert registry.get_path(panel.character_binding.file_name) == str(BODY)
    assert len(panel.file_bindings()) == 1
    seen = []
    monkeypatch.setattr(CameraPreviewPanel, 'preview', lambda self, animation: seen.append(animation))
    # The real shared preview panel is used; GPU rendering and texture extraction are not needed here.
    panel._sources[BODY.name]['textures_ready'] = True
    panel.cam_choice.setCurrentIndex(panel.cam_choice.findData(3))
    assert panel.preview_button.isEnabled()
    panel.preview_button.click()
    assert isinstance(panel._preview, CameraPreviewPanel)
    assert seen[-1] is panel._sources[BODY.name]['camera'].sets[0].animations[3]
    assert not panel._preview._animate_model.isChecked()
    panel.set_command(23)
    defend = next(seq for seq in enemy.seq_animation_data['seq_animation_data'] if seq['id'] == 23)
    assert panel.seq_code.toPlainText() == sequence_to_code(game_data, defend['data'])
    assert not panel.preview_button.isEnabled()
    for binding in panel.file_bindings():
        binding.save()
    assert all(path.read_bytes() == raw for path, raw in before.items())
    panel.character_binding.reload_from_disk()
    assert panel._preview is None
    assert panel._character['path'] == str(BODY)
    registry.close_file(panel.character_binding.file_name)
    assert panel._character is None and not panel.preview_button.isEnabled()
    assert not panel._sources and panel._preview is None


def test_character_replacement_missing_and_broken_weapons(app, game_data, tmp_path):
    panel = CommandAnimationPanel(game_data, FileRegistry())
    panel.set_command(25)
    body = tmp_path / BODY.name
    body.write_bytes(BODY.read_bytes())
    panel.import_character(body)
    assert panel.seq_source.currentData() is None
    assert not panel.seq_source.isEnabled()
    assert panel.preview_button.isEnabled()
    assert 'linked weapon files' in panel.seq_code.toPlainText()
    (tmp_path / WEAPON.name).write_bytes(WEAPON.read_bytes())
    (tmp_path / 'd0w001.dat').write_bytes(b'')
    (tmp_path / 'd0w002.dat').write_bytes(b'not a battle model')
    # Reloading the same body discovers new linked weapons and reports only bad nonempty files.
    panel.character_binding.reload_from_disk()
    assert panel.seq_source.currentData() == WEAPON.name
    assert panel.seq_source.count() == 1
    assert 'd0w002.dat' in panel.status.text()
    assert 'd0w001.dat' not in panel.status.text()
    # A replacement with no linked files cannot keep the previous character's weapon list.
    other = tmp_path / 'replacement.dat'
    other.write_bytes(BODY.read_bytes())
    panel.import_character(other)
    assert panel._character['path'] == str(other)
    assert list(panel._sources) == ['replacement.dat']
    assert panel.seq_source.currentData() is None
    panel.import_character(MONSTER)
    assert 'select a character body' in panel.status.text()
    assert panel._character is None
    broken = tmp_path / 'bad.dat'
    broken.write_bytes(b'not a battle model')
    panel.import_character(broken)
    assert 'Cannot import bad.dat' in panel.status.text()
    assert broken.name not in panel._sources
    assert not panel.character_binding.current_path


@pytest.mark.parametrize('body_name', ['d0c000.dat', 'd1c003.dat', 'd7c016.dat'])
def test_camera_preview_poses_lean_character_and_includes_selected_weapon(app, game_data, body_name):
    body = BODY.with_name(body_name)
    if not body.exists():
        pytest.skip(f'{body_name} not available')
    panel = CommandAnimationPanel(game_data, FileRegistry())
    panel.set_command(25)
    panel.import_character(body)
    manager = panel._character['manager']
    assert not manager.enemy.animation_data.animations  # lean import, not yet expanded
    panel._preview_camera()
    preview = panel._preview
    view = preview._view
    assert preview._animation is panel._selected_camera(), preview._placeholder.text()
    body_count = len(manager.enemy.geometry_data.get_vertices())
    expected = manager.get_animated_vertices(0, 0)
    np.testing.assert_allclose(view.gl_widget.vertices[:body_count], expected)
    selected = panel._sources[panel.seq_source.currentData()]['manager']
    weapon = selected if selected is not manager else None
    assert view._weapon_manager is weapon
    vertex_count = body_count + (len(weapon.enemy.geometry_data.get_vertices()) if weapon else 0)
    assert len(view.gl_widget.vertices) == vertex_count
    assert view.gl_widget._pending_qpixmaps
    if weapon:
        assert len(view.gl_widget._pending_qpixmaps) >= 2
    # Model-frame playback must keep the composite weapon and update the body's pose too.
    preview._animate_model.setChecked(True)
    preview._apply(1)
    frame = 1 % len(manager.enemy.animation_data.animations[0].frames)
    np.testing.assert_allclose(view.gl_widget.vertices[:body_count], manager.get_animated_vertices(0, frame))
    assert len(view.gl_widget.vertices) == vertex_count
    if panel.seq_source.count() > 1:
        panel.seq_source.setCurrentIndex(1)
        assert not preview._timer.isActive()
        panel._preview_camera()
        assert preview._view._weapon_manager is panel._sources[panel.seq_source.currentData()]['manager']
    panel._discard_preview()


def test_kernel_navigation_and_preview_do_not_mark_edits(app, tmp_path):
    work = tmp_path / 'kernel.bin'
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path=str(ROOT / 'Resources'), game_data_folder=str(ROOT / 'FF8GameData'))
    state = install_dirty_tracking(widget)
    widget.load_file(str(work))
    state.clear()
    tab = widget._section_tabs[1]
    panel = widget.command_animation_panel
    tab.list_widget.setCurrentRow(tab._visible_indices.index(25))
    assert not panel.isHidden()
    # A private copy keeps this integration check small; the discovery check above loads all weapons.
    body = tmp_path / BODY.name
    body.write_bytes(BODY.read_bytes())
    (tmp_path / WEAPON.name).write_bytes(WEAPON.read_bytes())
    panel.import_character(body)
    panel.cam_choice.activated.emit(1)
    panel.cam_choice.setCurrentIndex(1)
    panel.seq_source.activated.emit(1)
    assert not state.dirty
    # Importing or changing the preview also preserves an existing unsaved edit.
    tab._text_widgets[0].setText('Treatment renamed')
    tab._text_widgets[0].textEdited.emit('Treatment renamed')
    assert state.dirty
    panel.import_character(body)
    assert state.dirty
    tab.list_widget.setCurrentRow(tab._visible_indices.index(2))
    assert panel.isHidden()
    widget._save_kernel()
    assert all(binding.read_only for binding in widget.file_bindings()[1:])

    # No animation panel: the form fills the row. A supported panel receives spare width
    # immediately, even before importing a character or starting 3D playback.
    tab.list_widget.setCurrentRow(tab._visible_indices.index(2))
    widget.tabs.setCurrentIndex(0)
    widget.resize(1500, 950)
    widget.show()
    app.processEvents()
    row = tab.parentWidget()
    assert tab.width() == row.width()
    tab.list_widget.setCurrentRow(tab._visible_indices.index(25))
    app.processEvents()
    scroll = tab.layout().itemAt(1).widget()
    assert panel.width() > scroll.width()
    form_width, preview_width = tab.width(), panel.width()
    widget.resize(widget.width() + 250, widget.height())
    app.processEvents()
    assert abs(tab.width() - form_width) <= 2
    assert panel.width() > preview_width + 200
    # Playing or stopping the camera keeps the animation panel's width allocation.
    preview_width = panel.width()
    panel.preview_button.click()
    app.processEvents()
    assert panel._render_active
    assert abs(panel.width() - preview_width) <= 2
    form_width, preview_width = tab.width(), panel.width()
    widget.resize(widget.width() + 250, widget.height())
    app.processEvents()
    assert abs(tab.width() - form_width) <= 2
    assert panel.width() > preview_width + 200
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.width() <= scroll.sizeHint().width() + 2
    assert tab.width() <= tab.sizeHint().width() + 2
    assert abs(tab.width() + panel.width() + row.layout().spacing() - row.width()) <= 2
    panel._stop_preview()
    app.processEvents()
    assert abs(tab.width() - form_width) <= 2
    # With no animation panel the form fills the entire row, starting at the left edge.
    tab.list_widget.setCurrentRow(tab._visible_indices.index(2))
    app.processEvents()
    assert panel.isHidden()
    assert tab.x() == row.layout().contentsMargins().left()
    assert tab.width() == row.width()
    widget.close()


def test_added_command_preview_follows_execution_type(app, tmp_path):
    work = tmp_path / 'kernel.bin'
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget()
    widget.load_file(str(work))
    tab = widget._section_tabs[1]
    panel = widget.command_animation_panel
    tab.list_widget.setCurrentRow(25)
    widget._add_growable_entry(1)
    assert tab.current_entry_index() == 39
    assert not panel.isHidden() and panel.seq_value.text() == '11'
    panel.import_character(BODY)
    widget.resize(1500, 950)
    widget.show()
    app.processEvents()
    combo = tab._field_widgets['behaves_like'][2]
    for code, seq, cameras in ((24, 11, list(range(6))), (23, 23, []), (31, 24, [6, 7])):
        combo.setCurrentIndex(combo.findData(code))
        app.processEvents()
        assert not panel.isHidden()
        assert panel.seq_value.text() == str(seq)
        assert [panel.cam_choice.itemData(i) for i in range(panel.cam_choice.count())] == cameras
        enemy = panel._sources[panel.seq_source.currentData()]['manager'].enemy
        data = next(item['data'] for item in enemy.seq_animation_data['seq_animation_data'] if item['id'] == seq)
        assert panel.seq_code.toPlainText() == sequence_to_code(widget.game_data, data)
        assert panel.width() > tab._form_scroll.width()
    panel.preview_button.click()
    assert panel._preview._animation is panel._selected_camera()
    combo.add_id_button.click()
    app.processEvents()
    assert combo.currentData() == 39 and panel.isHidden()
    assert tab.width() == tab.parentWidget().width()
    combo.setCurrentIndex(combo.findData(24))
    app.processEvents()
    assert not panel.isHidden() and panel.seq_value.text() == '11'
    assert panel.width() > tab._form_scroll.width()
    widget.close()


def test_execution_types_and_independent_dll_ids_round_trip(app, game_data, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    work = tmp_path / 'kernel.bin'
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget()
    widget.load_file(str(work))
    state = install_dirty_tracking(widget)
    tab = widget._section_tabs[1]
    widget._add_growable_entry(1)
    combo = tab._field_widgets['behaves_like'][2]
    assert [combo.itemData(i) for i in range(combo.count())] == [24, 23, 31]
    assert 'Seq 11 / Cam 0–5' in combo.itemText(0)
    state.clear()
    combo.add_id_button.click()
    assert combo.currentData() == 39 and 'DLL-defined' in combo.currentText()
    assert state.dirty
    widget._add_growable_entry(1)  # copying this added command also keeps its DLL execution type
    assert tab._entries[40].get('behaves_like') == 39
    combo.add_id_button.click()
    assert combo.currentData() == 40
    widget._save_kernel()
    assert any('loader compatibility' in warning for warning in warnings)
    loaded = SolomonRingWidget()
    loaded.load_file(str(work))
    assert [loaded._section_entries(1)[i].get('behaves_like') for i in (39, 40)] == [39, 40]
    options = loaded.registry.resolve('command_family')['entries']
    assert [item['value'] for item in options] == [24, 23, 31, 39, 40]
    # Legacy aliases retain both their byte values and readable Seq/Cam labels.
    loaded._section_entries(1)[39].set('behaves_like', 25)
    loaded._section_entries(1)[40].set('behaves_like', 0)
    loaded._refresh_command_lookups()
    options = loaded.registry.resolve('command_family')['entries']
    assert any(item['value'] == 25 and 'Seq 11 / Cam 0–5' in item['name'] for item in options)
    assert any(item['value'] == 0 and 'default alias' in item['name'] for item in options)
