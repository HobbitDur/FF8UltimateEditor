"""Tests for the SolomonRing kernel.bin editor (data-driven field editing).

These use the extracted kernel.bin at ``extracted_files/main/kernel.bin`` (present
locally, gitignored for copyright) and are skipped automatically when it is missing
(e.g. in CI) via the ff8data marker (see conftest.py).
"""
import json
import pathlib

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData, SectionType
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from SolomonRing.kernellookups import LookupRegistry
from SolomonRing.kernelsectiontab import KernelSectionTab
from SolomonRing.solomonringwidget import SolomonRingWidget

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
KERNEL = PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"
GAME_DATA_FOLDER = str(PROJECT_ROOT / "FF8GameData")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(GAME_DATA_FOLDER)
    gd.load_all()
    return gd


def _snapshot(game_data, path):
    km = KernelManager(game_data)
    km.load_file(str(path))
    data = {s.id: bytes(s.get_data_hex()) for s in km.section_list if s and s.type == SectionType.DATA}
    text = {s.id: [t.get_str() for t in s.get_text_list()]
            for s in km.section_list if s and s.type == SectionType.FF8_TEXT}
    return data, text


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_roundtrip_no_edit_is_lossless(game_data, tmp_path):
    """Load and re-save unchanged: every data section and every string is preserved."""
    km = KernelManager(game_data)
    km.load_file(str(KERNEL))
    out = tmp_path / "rt.bin"
    km.save_file(str(out))

    d0, t0 = _snapshot(game_data, KERNEL)
    d1, t1 = _snapshot(game_data, out)
    assert d0 == d1, "data sections changed on a no-edit round-trip"
    assert t0 == t1, "text strings changed on a no-edit round-trip"


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_all_section_tabs_roundtrip(qapp, game_data, tmp_path):
    """Building every tab and touching every field of every entry must not corrupt the file."""
    registry = LookupRegistry(game_data, GAME_DATA_FOLDER)
    cfgs = json.load(open(pathlib.Path(GAME_DATA_FOLDER) / "Resources" / "json" / "kernel_section_fields.json",
                          encoding="utf-8"))
    kd = json.load(open(pathlib.Path(GAME_DATA_FOLDER) / "Resources" / "json" / "kernel_bin_data.json",
                        encoding="utf-8"))
    text_link = {s["id"]: s["section_id_text_linked"] for s in kd["sections"] if s["type"] == "data"}

    km = KernelManager(game_data)
    km.load_file(str(KERNEL))
    by_id = {s.id: s for s in km.section_list if s}

    for sid_s, cfg in cfgs.items():
        sid = int(sid_s)
        text_id = text_link.get(sid, 0)
        tab = KernelSectionTab(game_data, registry, cfg)
        tab.load_section(by_id[sid], by_id.get(text_id) if text_id else None)
        for row in range(tab.list_widget.count()):
            tab.list_widget.setCurrentRow(row)
        tab.commit()

    out = tmp_path / "all.bin"
    km.save_file(str(out))
    d0, t0 = _snapshot(game_data, KERNEL)
    d1, t1 = _snapshot(game_data, out)
    assert d0 == d1
    assert t0 == t1


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_edit_persists(qapp, tmp_path):
    """A numeric field edit and a name edit survive save + reload."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())

    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    magic_tab = widget._section_tabs[2]
    magic_tab.list_widget.setCurrentRow(1)  # Fire
    magic_tab._field_widgets["spell_power"][2].setValue(99)
    magic_tab._text_widgets[0].setText("Fireball")
    widget._save_kernel()

    reloaded = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    reloaded.load_file(str(work))
    magic_tab2 = reloaded._section_tabs[2]
    magic_tab2.list_widget.setCurrentRow(1)
    assert magic_tab2._field_widgets["spell_power"][2].value() == 99
    assert magic_tab2._entries[1].get_text(0) == "Fireball"


def _duel_button_word(kernel_path, move_id, slot=0):
    """The raw u16 of one Duel sequence slot, straight out of the file."""
    kd = json.load(open(pathlib.Path(GAME_DATA_FOLDER) / "Resources" / "json" / "kernel_bin_data.json",
                        encoding="utf-8"))
    sec = next(s for s in kd["sections"] if s["id"] == 23)
    data = pathlib.Path(kernel_path).read_bytes()
    base = int.from_bytes(data[int(sec["section_offset"], 16):][:4], "little")
    off = base + sec["sub_section_size"] * move_id + 16 + 2 * slot
    return int.from_bytes(data[off:off + 2], "little")


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_the_duel_finisher_flag_is_its_own_checkbox(qapp, tmp_path):
    """Bit 0x100 of Duel sequence button 1 is the "this move ends the Duel" flag, not part of
    the button: the engine masks the button with 0xF0FF everywhere (BattleMenu_ZellDuel_Update
    @0x4AF840, BuildZellDuelMenu @0x4B0280) and reads 0x100 off button 1 alone to decide
    whether the move closes the Duel window. Both must be editable, and neither may disturb
    the other - before this was split, Different Beat's 0x0110 showed as a raw number."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    different_beat, punch_rush = 8, 0
    assert _duel_button_word(work, different_beat) == 0x0110
    assert _duel_button_word(work, punch_rush) == 0x0020

    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    duel = widget._section_tabs[23]

    # Different Beat reads as the button it really is, plus a ticked finisher box.
    duel.list_widget.setCurrentRow(different_beat)
    button = duel._field_widgets["button_1"][2]
    kind, _, finisher = duel._field_widgets["duel_is_finisher"]
    # A single bit renders as a plain labelled checkbox - not a flags group box.
    assert kind == "bool"
    assert button.currentData() == 0x0010
    assert "raw" not in button.currentText().lower()
    assert finisher.isChecked()

    # Untick it here, and tick it on a move that is not a finisher.
    finisher.setChecked(False)
    duel.list_widget.setCurrentRow(punch_rush)          # commits Different Beat
    assert duel._field_widgets["button_1"][2].currentData() == 0x0020
    assert not duel._field_widgets["duel_is_finisher"][2].isChecked()
    duel._field_widgets["duel_is_finisher"][2].setChecked(True)
    widget._save_kernel()

    # The flag moved; neither button did.
    assert _duel_button_word(work, different_beat) == 0x0010
    assert _duel_button_word(work, punch_rush) == 0x0120

    reloaded = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    reloaded.load_file(str(work))
    duel2 = reloaded._section_tabs[23]
    duel2.list_widget.setCurrentRow(punch_rush)
    assert duel2._field_widgets["button_1"][2].currentData() == 0x0020
    assert duel2._field_widgets["duel_is_finisher"][2].isChecked()
    duel2.list_widget.setCurrentRow(different_beat)
    assert duel2._field_widgets["button_1"][2].currentData() == 0x0010
    assert not duel2._field_widgets["duel_is_finisher"][2].isChecked()


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_browsing_entries_does_not_mark_the_file_dirty(qapp, tmp_path):
    """Clicking through the entry list is navigation, not editing: the window title must not
    gain its unsaved-changes "*". DirtyState uses user-only signals where Qt has one, but a
    QSpinBox's valueChanged fires on setValue too, so repopulating the form for the newly
    selected entry used to look exactly like the user typing in every numeric field."""
    from Common.dirtytracking import install_dirty_tracking

    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    state = install_dirty_tracking(widget)
    state.clear()

    # Battle items is where this was reported, but it is not special - walk every tab.
    for section_id, tab in widget._section_tabs.items():
        for row in range(min(tab.list_widget.count(), 8)):
            tab.list_widget.setCurrentRow(row)
        assert not state.dirty, f"selecting an entry in section {section_id} marked the file dirty"

    # The tracking itself is still live: an actual field change does mark.
    items = widget._section_tabs[8]
    items.list_widget.setCurrentRow(1)
    kind, _field, spin = items._field_widgets["attack_power"]
    assert kind == "int"
    spin.setValue(spin.value() + 1)
    assert state.dirty
