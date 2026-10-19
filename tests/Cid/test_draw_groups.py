"""Real format and GUI coverage for CID's group ranges and ordered phase searches."""
from pathlib import Path
import struct

import pytest
from PyQt6.QtWidgets import QApplication

from Cid.cidwidget import CidWidget
from Cid.worlddrawphases import WorldDrawPhases
from Cid.worlddrawsection import WorldDrawSection

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
    widget._save_positions_only()
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
    widget._save_hext_only()
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
