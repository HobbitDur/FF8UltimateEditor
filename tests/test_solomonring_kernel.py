"""Tests for the SolomonRing kernel.bin editor (data-driven field editing).

These need the original kernel.bin next to the project root and are skipped
otherwise (see conftest.py / the ff8data marker).
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
KERNEL = PROJECT_ROOT / "kernel.bin"
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


@pytest.mark.ff8data("kernel.bin")
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


@pytest.mark.ff8data("kernel.bin")
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


@pytest.mark.ff8data("kernel.bin")
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
