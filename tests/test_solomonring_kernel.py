"""Tests for the SolomonRing kernel.bin editor (data-driven field editing).

These use the extracted kernel.bin at ``extracted_files/main/kernel.bin`` (present
locally, gitignored for copyright) and are skipped automatically when it is missing
(e.g. in CI) via the ff8data marker (see conftest.py).
"""
import json
import pathlib

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton

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


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_add_entry_button_actually_adds(qapp, tmp_path):
    """Clicking the Magic tab's "+ Add entry" button must add an entry, not merely calling
    _add_growable_entry directly. QPushButton.clicked emits a checked bool and the callback
    took the section id as a plain positional parameter, so Qt passed False into it: the
    handler looked for a section whose id was False, found none, and returned silently - the
    button did nothing at all, with no error. Crossing id 64 must also insert the 32 GF
    placeholder rows, so the new entry lands on 96, the first id FFNx treats as extended
    magic (ids 64-95 stay reserved for the GFs)."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    magic = widget._section_tabs[2]
    button = next(b for b in magic.findChildren(QPushButton) if "Add entry" in b.text())
    section = next(s for s in widget.kernel_manager.section_list if s and s.id == 2)

    assert len(section.get_subsection_list()) == 57
    button.click()
    assert len(section.get_subsection_list()) == 58, "the + Add entry button did nothing"
    assert magic._visible_indices[-1] == 57

    # Fill 58..63, then one more click crosses into the GF-reserved block.
    while len(section.get_subsection_list()) < 64:
        button.click()
    button.click()
    assert len(section.get_subsection_list()) == 97  # 64 + 32 placeholders + 1 real entry
    assert magic._visible_indices[-1] == 96


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_remove_entry_button_only_touches_added_entries(qapp, tmp_path):
    """"- Remove entry" deletes the selected entry together with its name and description,
    but only for entries a mod added on top: ids 0-56 are the spells the unmodded engine
    indexes by id, so the button is greyed while one of those is selected. Removing the last
    entry left above the GF-reserved block also drops the 32 placeholder rows, so the file
    never keeps a tail of entries that exist only to pad the GF id range."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    magic = widget._section_tabs[2]
    section = next(s for s in widget.kernel_manager.section_list if s and s.id == 2)
    texts = section.section_text_linked
    add = next(b for b in magic.findChildren(QPushButton) if "Add entry" in b.text())
    remove = next(b for b in magic.findChildren(QPushButton) if "Remove entry" in b.text())

    def select(entry_id):
        magic.list_widget.setCurrentRow(magic._visible_indices.index(entry_id))

    # Vanilla entries are not removable, wherever in the list they sit.
    for vanilla_id in (0, 30, 56):
        select(vanilla_id)
        assert not remove.isEnabled(), f"id {vanilla_id} is vanilla and must not be removable"

    # An added one is, and it takes its two strings with it.
    add.click()
    select(57)
    assert remove.isEnabled()
    entries_before, texts_before = len(section.get_subsection_list()), len(texts.get_text_list())
    remove.click()
    assert len(section.get_subsection_list()) == entries_before - 1
    assert len(texts.get_text_list()) == texts_before - len(magic.text_labels)
    select(56)
    assert not remove.isEnabled()

    # Removing the only entry above the reserved block takes the placeholders as well.
    while len(section.get_subsection_list()) < 64:
        add.click()
    add.click()
    assert len(section.get_subsection_list()) == 97
    select(96)
    remove.click()
    assert len(section.get_subsection_list()) == 64
    assert magic._visible_indices[-1] == 63


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_added_entry_survives_save_and_reload(qapp, tmp_path):
    """A spell added past the GF block keeps its id and its name across save + reload, which
    is what a modded kernel.bin has to do for FFNx's extended magic to resolve id 96."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    magic = widget._section_tabs[2]
    section = next(s for s in widget.kernel_manager.section_list if s and s.id == 2)
    add = next(b for b in magic.findChildren(QPushButton) if "Add entry" in b.text())

    while len(section.get_subsection_list()) < 64:
        add.click()
    add.click()                                   # crosses into id 96
    magic.list_widget.setCurrentRow(len(magic._visible_indices) - 1)
    magic._text_widgets[0].setText("Testaga")
    widget._save_kernel()

    reloaded = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    reloaded.load_file(str(work))
    tab = reloaded._section_tabs[2]
    assert tab._visible_indices[-1] == 96
    assert tab._entries[96].get_text(0) == "Testaga"


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_remove_refuses_to_shift_the_reserved_gf_block(qapp, tmp_path):
    """Deleting an entry shifts every later one down one id, so an entry below the
    GF-reserved block may not go while the block exists: the 32 placeholders would slide
    from 64-95 onto 63-94 - the engine still reads 64-79 as GFs, so a placeholder would
    become a real id and a real spell above them would land inside the hidden block. It
    used to be allowed, and the placeholder cleanup then fired on the entry count alone
    and deleted the 32 rows plus the spell above them."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(work))
    magic = widget._section_tabs[2]
    section = next(s for s in widget.kernel_manager.section_list if s and s.id == 2)
    texts = section.section_text_linked
    add = next(b for b in magic.findChildren(QPushButton) if "Add entry" in b.text())
    remove = next(b for b in magic.findChildren(QPushButton) if "Remove entry" in b.text())

    def select(entry_id):
        magic.list_widget.setCurrentRow(magic._visible_indices.index(entry_id))

    # Fill 57..63, then cross the block so there is a real entry at 96.
    while len(section.get_subsection_list()) < 64:
        add.click()
    add.click()
    assert len(section.get_subsection_list()) == 97
    select(57)
    magic._text_widgets[0].setText("Keepme")
    select(96)                                   # commits the name above
    assert texts.get_text_list()[57 * len(magic.text_labels)].get_str() == "Keepme"

    # While the block is there, only the entry above it may go.
    for below in (57, 60, 63):
        select(below)
        assert not remove.isEnabled(), f"id {below} would shift the reserved block"
    select(96)
    assert remove.isEnabled()

    remove.click()
    # The placeholders went with it, and nothing below was touched.
    assert len(section.get_subsection_list()) == 64
    assert magic._visible_indices[-1] == 63
    assert texts.get_text_list()[57 * len(magic.text_labels)].get_str() == "Keepme"

    # With no block left, the entries below become removable again.
    select(57)
    assert remove.isEnabled()
    remove.click()
    assert len(section.get_subsection_list()) == 63


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_a_field_group_copies_between_entries(qapp, tmp_path, monkeypatch):
    """Copy / Paste / Apply to... move a whole field group (Magic's junction stats) between
    entries: pasting onto one entry, "Apply to..." onto several ticked in a list. Other groups
    and read-only fields are untouched, the edit is flagged unsaved, and it saves."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QMessageBox
    from Common.dirtytracking import DirtyState
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.dirty_state = DirtyState(widget)
    widget.load_file(str(work))
    tab = widget._section_tabs[2]
    group = "Junction (stats)"
    fields = [f for f in tab.fields if f.get("group") == group]
    names = tab._group_field_names(fields)
    assert "j_str" in names and "j_status_defend" in names and "compat_ifrit" not in names

    tab.list_widget.setCurrentRow(1)                          # Fire
    tab._field_widgets["j_str"][2].setValue(77)               # an unsaved form edit is copied too
    tab.copy_group(group, fields)
    assert tab._group_paste_buttons[group].isEnabled()
    fire = {name: tab._entries[1].get(name) for name in names}
    assert fire["j_str"] == 77

    tab.list_widget.setCurrentRow(2)                          # Blizzard
    blizzard_power = tab._entries[2].get("spell_power")
    blizzard_compat = tab._entries[2].get("compat_shiva")
    tab.paste_group(group)
    assert {name: tab._entries[2].get(name) for name in names} == fire
    assert tab._field_widgets["j_str"][2].value() == 77       # the form shows it at once
    assert tab._entries[2].get("spell_power") == blizzard_power
    assert tab._entries[2].get("compat_shiva") == blizzard_compat
    assert widget.dirty_state.dirty

    # "Apply to...": tick Thunder (4) and Water (7) in the list, apply.
    def fake_exec(dialog):
        entry_list = dialog.findChild(type(tab.list_widget))
        for row in range(entry_list.count()):
            if entry_list.item(row).data(Qt.ItemDataRole.UserRole) in (4, 7):
                entry_list.item(row).setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    tab._apply_group_dialog(group, fields)
    for index in (4, 7):
        assert {name: tab._entries[index].get(name) for name in names} == fire
    assert tab._entries[3].get("j_str") != 77                 # not ticked: untouched

    widget._save_kernel()
    reloaded = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    reloaded.load_file(str(work))
    for index in (2, 4, 7):
        assert {name: reloaded._section_tabs[2]._entries[index].get(name) for name in names} == fire


def test_the_last_section_tab_is_remembered(qapp, tmp_path):
    """Re-opening SolomonRing lands on the section tab used last (kept in the app settings).
    A temporary ini file stands in for the app's QSettings - never the real registry."""
    from PyQt6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER,
                              settings=settings)
    assert first.tabs.currentIndex() == 0
    first.tabs.setCurrentIndex(5)
    second = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER,
                               settings=settings)
    assert second.tabs.currentIndex() == 5
    # Used alone (no settings), nothing is remembered.
    alone = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    assert alone.tabs.currentIndex() == 0
