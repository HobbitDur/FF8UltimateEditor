"""Real format and GUI coverage for CID's group ranges and ordered phase searches."""
from pathlib import Path
import struct

import pytest
from PyQt6.QtWidgets import QApplication, QStackedWidget, QPushButton
from PyQt6.QtTest import QSignalSpy

from Cid.cidwidget import CidWidget
from Cid.worlddrawphases import WorldDrawPhases
from Cid.worlddrawsection import WorldDrawSection
from Cid.phasestory import PhaseStoryDialog, STORY_PHASES
from Common.filetoolbarwidget import FileToolbarWidget

ROOT = Path(__file__).resolve().parents[2]


def _exe_bytes(rows=WorldDrawPhases.DEFAULT_DATA):
    data = bytearray(WorldDrawPhases.FILE_OFFSET + 20)
    data[WorldDrawPhases.FILE_OFFSET:] = rows
    return data


def _wmset(tmp_path):
    data = bytearray(192 + 44 + 128 * 4 + 32)
    end = 192 + 44 + 128 * 4
    struct.pack_into('<48I', data, 0, *([192] * 35 + [end] * 13))
    struct.pack_into('<11I', data, 192, 44, 512, 512, 516, 516, 520, 520, 528, 528, 552, 44)
    # Distinct triggers, except the intentional Alcauld pair 246/247.
    for index in range(128):
        struct.pack_into('BBBB', data, 192 + 44 + index * 4, index, 12, 9, 0xA5)
    data[192 + 44 + 118 * 4:192 + 44 + 118 * 4 + 3] = bytes((117, 12, 9))
    data[end:] = b'X' * 32
    source = tmp_path / 'wmsetus.obj'
    source.write_bytes(data)
    return source


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, tmp_path):
    widget = CidWidget(str(ROOT / 'Resources'), str(ROOT / 'FF8GameData'))
    source = _wmset(tmp_path)
    exe = tmp_path / 'FF8_EN.exe'
    exe.write_bytes(_exe_bytes())
    widget.load_exe(str(exe))
    widget.load_wmset(str(source))
    yield widget, source, exe
    widget.close()
    widget.deleteLater()


def test_phase_table_preserves_custom_rules_and_ignored_bytes():
    raw = bytearray(WorldDrawPhases.DEFAULT_DATA)
    raw[:4] = bytes((2, 0x80, 0xFA, 3))
    rules = WorldDrawPhases()
    rules.load_exe_bytes(_exe_bytes(raw))
    assert rules.groups_for_phase(0) == (2,)
    assert rules.set_groups(0, (2,)) is False
    patch = rules.hext_lines()
    assert patch[:4] == [' 876770 = 02', ' 876771 = 80', ' 876772 = FA', ' 876773 = 03']
    assert len(patch) == 20
    assert rules.set_groups(0, (4, 0, 2, 1))
    assert rules.groups_for_phase(0) == (4, 0, 2, 1)
    assert rules.set_groups(1, ())
    assert rules.groups_for_phase(1) == ()
    assert rules.hext_lines()[4:8] == [f' {0x876774+i:X} = FF' for i in range(4)]
    with pytest.raises(ValueError):
        rules.set_groups(0, (0, 1, 2, 3, 4))
    with pytest.raises(ValueError):
        rules.set_groups(0, (5,))
    with pytest.raises(ValueError):
        rules.set_groups(5, ())
    with pytest.raises(ValueError):
        rules.load_exe_bytes(b'not an exe')
    assert rules.groups_for_phase(0) == (4, 0, 2, 1)
    broken = bytearray(WorldDrawPhases.DEFAULT_DATA)
    broken[0] = 5
    with pytest.raises(ValueError):
        rules.load_exe_bytes(_exe_bytes(broken))
    assert WorldDrawPhases().hext_lines() == []


def test_group_ranges_change_only_the_selected_header_bytes(tmp_path):
    source = _wmset(tmp_path)
    section = WorldDrawSection()
    section.load(source)
    assert section.group_range(0) == (0, 117)
    assert section.set_group_range(0, 5, 118)
    out = tmp_path / 'edited.obj'
    section.save(out)
    expected = bytearray(source.read_bytes())
    struct.pack_into('<II', expected, 192, 44 + 5 * 4, 44 + 118 * 4)
    assert out.read_bytes() == expected
    section.load(out)
    assert section.group_range(0) == (5, 118)
    section.set_group_range(0, 7, 7)
    assert section.phases_for_record(7, ((), (), (), (), ())) == ()
    assert section.group_range(0) == (7, 7)
    with pytest.raises(ValueError):
        section.set_group_range(0, 4, 129)
    with pytest.raises(ValueError):
        section.set_group_range(0, 4, 3)
    with pytest.raises(ValueError):
        section.set_group_range(5, 0, 1)


def test_group_tab_edits_ranges_and_refreshes_main_table(editor, monkeypatch, tmp_path):
    widget, source, _exe = editor
    groups = widget._groups_widget
    assert widget.tabs.tabText(1) == 'Groups and phases'
    assert groups.groups.isEnabled() and groups.phases.isEnabled()
    assert groups.members.rowCount() == 117
    assert not widget._exe_dirty and not widget._wmset_dirty
    groups._first[0].setValue(130)
    assert widget._section.group_range(0) == (1, 117)
    assert widget._draw_list[128].world_phases == ()
    assert widget._draw_widget.item(128, 8).text() == 'Not scanned'
    assert widget._wmset_dirty and not widget._exe_dirty
    groups._last[0].setValue(129)  # bounds stay valid when the two handles cross
    assert widget._section.group_range(0) == (0, 1)
    groups._enabled[0].setChecked(False)
    assert widget._section.group_range(0) == (0, 0)
    groups._enabled[0].setChecked(True)
    assert widget._section.group_range(0) == (0, 1)
    out = tmp_path / 'saved.obj'
    monkeypatch.setattr(widget._save_wmset_dialog, 'getSaveFileName', lambda **kw: (str(out), ''))
    widget.save_folder()
    reloaded = WorldDrawSection()
    reloaded.load(out)
    assert reloaded.group_range(0) == (0, 1)
    assert out.read_bytes()[192+44:] == source.read_bytes()[192+44:]
    assert not widget._wmset_dirty


def test_phase_tab_changes_search_order_exports_hext_and_reports_shadowing(editor, monkeypatch, tmp_path):
    widget, _source, exe = editor
    groups = widget._groups_widget
    # Enable Cure instead of Blizzard in the first phase.
    combo = groups._searches[0][1]
    combo.setCurrentIndex(combo.findData(2))
    assert widget._phase_rules.groups_for_phase(0) == (0, 2)
    assert widget._exe_dirty and not widget._wmset_dirty
    assert widget._draw_list[245].world_phases == ()
    assert widget._draw_list[246].world_phases == (0, 1, 2, 3, 4)
    assert widget._draw_widget.item(246, 8).text() == '0, 1, 2, 3, 4'
    patch = tmp_path / 'draw.hext'
    monkeypatch.setattr(widget._save_hext_dialog, 'getSaveFileName', lambda **kw: (str(patch), ''))
    widget.save_folder()
    text = patch.read_text(encoding='utf8')
    assert ' 876771 = 02' in text
    assert ' 876783 = 04' in text
    assert '876784 =' not in text
    assert not widget._exe_dirty
    # Apply only the phase lines, load the patched EXE again, and retain its rules in the next export.
    data = bytearray(exe.read_bytes())
    for line in widget._phase_rules.hext_lines():
        offset, value = line.strip().split(' = ')
        data[int(offset, 16)] = int(value, 16)
    exe.write_bytes(data)
    widget.load_exe(str(exe))
    assert widget._phase_rules.groups_for_phase(0) == (0, 2)
    assert not widget._exe_dirty and not widget._wmset_dirty
    assert ' 876771 = 02' in widget._phase_rules.hext_lines()
    # Simultaneously enabling both variants surfaces the actual first-match priority.
    third = groups._searches[0][2]
    third.setCurrentIndex(third.findData(1))
    assert 'ID 247 matches before ID 246' in groups.diagnostics.text()
    groups._searches[0][0].setCurrentIndex(0)  # None compacts later searches, it never inserts a stop hole
    assert widget._phase_rules.groups_for_phase(0) == (2, 1)
    assert groups._searches[0][0].currentData() == 2
    widget._on_wmset_closed('wmsetus.obj')
    assert widget._phase_rules.groups_for_phase(0) == (2, 1)
    assert widget._exe_dirty and not groups.groups.isEnabled()


def test_loading_sources_in_either_order_and_closing_exe_preserves_groups(app, tmp_path):
    widget = CidWidget(str(ROOT / 'Resources'), str(ROOT / 'FF8GameData'))
    widget.load_wmset(str(_wmset(tmp_path)))
    assert not widget._groups_widget.phases.isEnabled()
    raw = bytearray(WorldDrawPhases.DEFAULT_DATA)
    raw[:4] = bytes((0, 2, 255, 255))
    exe = tmp_path / 'FF8_EN.exe'
    exe.write_bytes(_exe_bytes(raw))
    widget.load_exe(str(exe))
    assert widget._draw_list[246].world_phases == (0, 1, 2, 3, 4)
    widget._groups_widget._last[0].setValue(244)
    assert widget._wmset_dirty
    widget._on_exe_closed(str(exe))
    assert widget._wmset_dirty and widget._section.group_range(0) == (0, 116)
    assert not widget._groups_widget.phases.isEnabled()
    widget.close()
    widget.deleteLater()


def test_shared_save_button_writes_both_outputs_without_extra_cid_save_buttons(editor, monkeypatch, tmp_path):
    widget, _source, _exe = editor
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, widget.exe_binding.registry, str(ROOT / 'Resources'))
    widget.tabs.setCurrentIndex(1)
    widget._groups_widget._first[0].setValue(130)
    combo = widget._groups_widget._searches[0][1]
    combo.setCurrentIndex(combo.findData(2))
    assert widget._exe_dirty and widget._wmset_dirty
    assert not hasattr(widget, '_save_hext_button')
    assert not hasattr(widget, '_save_positions_button')
    assert not any('Export magic' in button.text() or 'Save positions' in button.text()
                   for button in widget.findChildren(QPushButton))
    hext, wmset = tmp_path / 'draw.hext', tmp_path / 'saved.obj'
    monkeypatch.setattr(widget._save_hext_dialog, 'getSaveFileName', lambda **kw: (str(hext), ''))
    monkeypatch.setattr(widget._save_wmset_dialog, 'getSaveFileName', lambda **kw: (str(wmset), ''))
    assert toolbar.save_button.isEnabled()
    toolbar.save_button.click()
    assert ' 876771 = 02' in hext.read_text(encoding='utf8')
    section = WorldDrawSection()
    section.load(wmset)
    assert section.group_range(0) == (1, 117)
    assert not widget._exe_dirty and not widget._wmset_dirty
    toolbar.close()
    stack.removeWidget(widget)
    widget.setParent(None)
    stack.close()


def test_phase_info_button_explains_story_and_script_sources_without_editing(editor, monkeypatch):
    widget, _source, _exe = editor
    opened = []
    monkeypatch.setattr(PhaseStoryDialog, 'exec', lambda dialog: opened.append(dialog.browser.toPlainText()))
    groups = widget._groups_widget
    exe_changes, world_changes = QSignalSpy(groups.exe_changed), QSignalSpy(groups.world_changed)
    widget._phase_info_button.click()
    assert len(opened) == 1
    text = opened[0]
    assert 'not disc numbers' in text
    assert 'Missile Base' in text and 'Balamb Garden' in text and 'Esthar' in text and 'Rinoa' in text
    assert 'during Disc 3' in text and 'variable 266' in text
    assert 'ssspace2.jsm' in text and '0xDBC' in text
    assert 'dic::defalut' in text
    assert not exe_changes and not world_changes
    assert [phase.phase for phase in STORY_PHASES] == list(range(5))
    widget.close()


def test_undo_keeps_separate_save_states_and_exact_phase_table_bytes(editor, monkeypatch, tmp_path):
    widget, _source, exe = editor
    raw = bytearray(exe.read_bytes())
    raw[WorldDrawPhases.FILE_OFFSET + 2:WorldDrawPhases.FILE_OFFSET + 4] = bytes((0x80, 0xFA))
    exe.write_bytes(raw)
    widget.load_exe(str(exe))
    original = widget._undo_capture()
    widget._draw_widget.cellWidget(135, 1).setCurrentIndex(5)
    widget.tabs.setCurrentIndex(1)
    widget._groups_widget._last[4].setValue(256)
    combo = widget._groups_widget._searches[0][1]
    combo.setCurrentIndex(combo.findData(2))
    widget.tabs.setCurrentIndex(0)
    widget._draw_widget.setCurrentCell(135, 0)
    widget._draw_widget.set_row_position(135, 42, 12, 7)
    edited = widget._undo_capture()
    patch = tmp_path / 'saved.hext'
    monkeypatch.setattr(widget._save_hext_dialog, 'getSaveFileName', lambda **kw: (str(patch), ''))
    monkeypatch.setattr(widget._save_wmset_dialog, 'getSaveFileName', lambda **kw: ('', ''))
    widget.save_folder()
    assert not widget._exe_dirty and widget._wmset_dirty
    assert widget.undo()  # position
    assert not widget._exe_dirty and widget._wmset_dirty
    assert widget.undo()  # phase search order
    assert widget._phase_rules.table_bytes() == original[0][1]  # includes ignored tail bytes
    assert widget._exe_dirty and widget._wmset_dirty
    assert widget.undo()  # group range
    assert widget._exe_dirty and not widget._wmset_dirty
    assert widget.undo()  # magic
    assert widget._undo_capture() == original
    assert widget._exe_dirty and not widget._wmset_dirty  # Hext had been saved after the edits
    for _ in range(4):
        assert widget.redo()
    assert widget._undo_capture() == edited
    assert not widget._exe_dirty and widget._wmset_dirty
    assert widget.undo()
    widget._draw_widget.set_row_position(135, 43, 12, 7)
    assert not widget._undo_stack.can_redo()  # a new edit replaces the discarded future
    widget.load_wmset(str(_source))
    assert not widget.undo()  # history never restores a replaced file


def test_csv_import_is_one_undo_step_and_reference_reload_preserves_history(editor, monkeypatch, tmp_path):
    widget, _source, _exe = editor
    original = widget._undo_capture()
    csv = tmp_path / 'draws.csv'
    rows = ['Draw ID,Magic ID,High Yield,Refill,X,Y,Sub ID']
    for draw in widget._draw_list:
        magic = 5 if draw.get_id() == 1 else draw.magic_index
        position = (42, 12, 7) if draw.get_id() == 136 else (draw.x, draw.y, draw.sub_id)
        rows.append(','.join(map(str, (draw.get_id(), magic, int(draw.high_yield), int(draw.refill), *position))))
    csv.write_text('\n'.join(rows), encoding='utf8')
    monkeypatch.setattr(widget.csv_dialog, 'getOpenFileName', lambda **kw: (str(csv), ''))
    widget._open_csv()
    imported = widget._undo_capture()
    assert imported != original and widget._exe_dirty and widget._wmset_dirty
    monkeypatch.setattr('FF8GameData.kernelnames.read_names', lambda *a, **k: {'magic': {5: 'New name'}})
    widget.load_kernel('reference/kernel.bin')
    widget._field_check.setChecked(False)
    assert widget.undo()
    assert widget._field_check.isChecked()  # undo reveals the affected field draw
    assert widget._undo_capture() == original
    assert not widget._exe_dirty and not widget._wmset_dirty
    assert not widget._undo_stack.can_undo()
    assert widget.redo()
    assert widget._undo_capture() == imported
    assert widget._draw_list[0].get_magic_name() == 'New name'


@pytest.mark.ff8data(*[f'extracted_files/field/mapdata/{name[:2]}/{name}/{name}.jsm'
                      for name in ('gmpark2', 'bgsido_8', 'ewbrdg1', 'ssspace2', 'eaplane1')])
def test_story_info_references_match_all_original_non_debug_phase_writes():
    from CCGroup.jsmvariant import decode_instructions
    from CCGroup.jsmcardgame import JsmCardGameFile

    base = ROOT / 'extracted_files/field/mapdata'
    expected = set()
    for phase in STORY_PHASES:
        for source in phase.sources:
            path = base / source.field[:2] / source.field / f'{source.field}.jsm'
            data = path.read_bytes()
            assert struct.unpack_from('<II', data, source.offset - 4) == (0x07000000 | phase.phase, 0x0B00010A)
            model = JsmCardGameFile(str(path), str(path.with_suffix('.sym')))
            position = source.offset - model.offset_script
            entry = max((i for i, start in enumerate(model.script_positions) if start <= position),
                        key=lambda i: model.script_positions[i])
            assert model.script_names[entry] == (source.entity, source.script)
            expected.add((source.field, source.offset))
    observed = set()
    for path in base.rglob('*.jsm'):
        if path.stem.startswith('test') or path.stem == 'bgmast_6':
            continue
        data = path.read_bytes()
        if len(data) < 8:
            continue
        start = struct.unpack_from('<H', data, 6)[0]
        for index, (opcode, arg) in enumerate(decode_instructions(data, start)):
            if opcode in (0x0B, 0x0D, 0x0F) and arg is not None and arg <= 266 < arg + {0x0B: 1, 0x0D: 2, 0x0F: 4}[opcode]:
                observed.add((path.stem, start + index * 4))
    assert observed == expected
