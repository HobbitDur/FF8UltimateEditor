"""Shiva adds and removes refine recipes, the ranges of kernel.bin moving with them.

A refine table (m000-m004) is a flat list of entries; each menu ability of kernel.bin gives the
first and last entry it offers (Menu_Prog19_RefineMenu_Init: count = last - first + 1, a u8, list =
Menu_RefineEntryBuffer + 8 * first, a 0x800-byte buffer). Adding a recipe means inserting an entry
and its text, and moving every range of the table it pushes: kernel.bin and mngrp.bin are saved
together or not at all.
"""
import csv
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.m00x.refineabilities import (MAX_TABLE_ENTRIES, RefineKernelError,
                                                         read_refine_abilities, verify_refine_ranges,
                                                         write_refine_ranges)
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from Shiva.ShivaRefine.refinecsv import read_refine_csv, write_refine_csv
from Shiva.ShivaRefine.refineview import RefineLayout

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
EXTRACTED = PROJECT_ROOT / "extracted_files"
FILES = ("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin", "extracted_files/main/kernel.bin")


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


@pytest.fixture
def files(tmp_path):
    for name in ("mngrp.bin", "mngrphd.bin"):
        shutil.copy(EXTRACTED / "menu" / name, tmp_path / name)
    shutil.copy(EXTRACTED / "main" / "kernel.bin", tmp_path / "kernel.bin")
    return tmp_path


def _load(game_data, folder, with_kernel=True):
    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(folder / "mngrphd.bin"), str(folder / "mngrp.bin"))
    abilities = read_refine_abilities(game_data, folder / "kernel.bin") if with_kernel else None
    return manager, RefineLayout(manager, abilities)


def _snapshot(layout):
    """Everything the game reads of each ability (the text offsets are recomputed when saving)."""
    return [(view.key, view.first, view.last, [t.get_str() for t in view.texts],
             [{name: value for name, value in vars(entry).items() if name != "text_offset"}
              for entry in view.entries]) for view in layout.views]


def _view(layout, name):
    return next(view for view in layout.views if view.name == name)


@pytest.mark.ff8data(*FILES)
def test_abilities_come_only_from_kernel_bin(game_data, files):
    """With a kernel.bin, one view per refine ability, named and sliced as it says (Tool-RF is the
    4th ability of kernel.bin but the last block of m001). Without one, no ability at all: each
    table is one view of all its entries, with a fixed count."""
    manager, from_kernel = _load(game_data, files)
    assert [(v.bin_name, v.name, v.ability.index, v.first, v.last) for v in from_kernel.views if v.bin_name == "m001"] == [
        ("m001", "Recov Med-RF", 13, 0, 8), ("m001", "ST Med-RF", 14, 9, 20), ("m001", "Ammo-RF", 15, 21, 36),
        ("m001", "Forbid Med-RF", 17, 37, 56), ("m001", "GFRecov Med-RF", 18, 57, 68),
        ("m001", "GFAbl Med-RF", 19, 69, 110), ("m001", "Tool-RF", 16, 111, 142)]
    assert len(from_kernel.views) == 19 and all(v.kind == "ability" and v.editable_range for v in from_kernel.views)
    assert sum(len(v.entries) for v in from_kernel.views) == 377 and not from_kernel.warnings

    without = RefineLayout(manager)
    assert [(v.bin_name, v.kind, v.first, v.last, v.editable_range) for v in without.views] == [
        ("m000", "table", 0, 101, False), ("m001", "table", 0, 142, False), ("m002", "table", 0, 9, False),
        ("m003", "table", 0, 11, False), ("m004", "table", 0, 109, False)]
    assert without.abilities == [] and not without.warnings


@pytest.mark.ff8data(*FILES)
def test_added_recipe_moves_the_ranges_and_survives_a_save(game_data, files):
    manager, layout = _load(game_data, files)
    recov = _view(layout, "Recov Med-RF")
    assert layout.insert_entry(recov, 0) == 1
    assert (recov.first, recov.last) == (0, 9)
    assert [(v.name, v.first, v.last) for v in layout.views if v.bin_name == "m001"] == [
        ("Recov Med-RF", 0, 9), ("ST Med-RF", 10, 21), ("Ammo-RF", 22, 37), ("Forbid Med-RF", 38, 57),
        ("GFRecov Med-RF", 58, 69), ("GFAbl Med-RF", 70, 111), ("Tool-RF", 112, 143)]
    assert vars(recov.entries[1]) == vars(recov.entries[0])
    recov.entries[1].element_in_id = 50
    recov.texts[1].set_str("Test:\\n1 will refine \\ninto 1 Potion")
    expected = _snapshot(layout)

    original_kernel = (files / "kernel.bin").read_bytes()
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))
    assert write_refine_ranges(game_data, files / "kernel.bin", layout.abilities) == 7
    assert not layout.ranges_changed

    _, reloaded = _load(game_data, files)
    assert _snapshot(reloaded) == expected
    kernel = (files / "kernel.bin").read_bytes()
    changed = [index for index in range(len(kernel)) if kernel[index] != original_kernel[index]]
    section = 0x43C0  # vanilla menu ability section; bytes 6/7 of abilities 13-19 (m001) only
    assert len(kernel) == len(original_kernel)
    assert all((index - section) % 8 in (6, 7) and 13 <= (index - section) // 8 <= 19 for index in changed)


@pytest.mark.ff8data(*FILES)
def test_growing_past_the_text_padding_keeps_every_other_section(game_data, files):
    """m001.msg is 8192 bytes padded in mngrp.bin: 40 more texts push it into a new 2048 block, and
    every section after it must move by that much."""
    manager, layout = _load(game_data, files)
    others_before = {section.id: bytes(section.get_data_hex()) for section in manager.mngrp.get_section_list()
                     if section not in manager.m00_manager.get_bin_list() + manager.m00_manager.get_msg_list()}
    tool = _view(layout, "Tool-RF")
    for _ in range(40):
        layout.insert_entry(tool, len(tool.entries) - 1)
    assert layout.check_game_limits() == []
    expected = _snapshot(layout)
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))
    write_refine_ranges(game_data, files / "kernel.bin", layout.abilities)

    reloaded_manager, reloaded = _load(game_data, files)
    assert _snapshot(reloaded) == expected
    assert sum(len(text) for text in reloaded_manager.m00_manager.get_msg_list()[1].get_text_list()) > 8192
    others_after = {section.id: bytes(section.get_data_hex()) for section in reloaded_manager.mngrp.get_section_list()
                    if section not in reloaded_manager.m00_manager.get_bin_list()
                    + reloaded_manager.m00_manager.get_msg_list()}
    assert others_after == others_before


@pytest.mark.ff8data(*FILES)
def test_removed_recipe_moves_the_ranges_back(game_data, files):
    manager, layout = _load(game_data, files)
    t_mag = _view(layout, "T Mag-RF")
    removed_text = t_mag.texts[2].get_str()
    layout.remove_entry(t_mag, 2)
    assert (t_mag.first, t_mag.last) == (0, 5) and _view(layout, "I Mag-RF").first == 6
    assert removed_text not in [text.get_str() for text in t_mag.texts]
    expected = _snapshot(layout)
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))
    write_refine_ranges(game_data, files / "kernel.bin", layout.abilities)
    _, reloaded = _load(game_data, files)
    assert _snapshot(reloaded) == expected

    one = _view(layout, "Forbid Mag-RF")
    while len(one.entries) > 1:
        layout.remove_entry(one, 0)
    with pytest.raises(ValueError, match="at least one"):
        layout.remove_entry(one, 0)


@pytest.mark.ff8data(*FILES)
def test_limits_and_layout_without_kernel(game_data, files):
    manager, layout = _load(game_data, files)
    card_mod = _view(layout, "Card Mod")  # one ability: RefineMenuTask.entry_count is a u8
    while len(card_mod.entries) < 255:
        layout.insert_entry(card_mod, 0)
    with pytest.raises(ValueError, match="255"):
        layout.insert_entry(card_mod, 0)
    mid, high = _view(layout, "Mid Mag-RF"), _view(layout, "High Mag-RF")  # two: the 0x800 buffer
    while len(mid.bin_section.entries) < MAX_TABLE_ENTRIES:
        layout.insert_entry(mid, 0)
    with pytest.raises(ValueError, match="256"):
        layout.insert_entry(high, 0)
    assert (mid.first, mid.last, high.first, high.last) == (0, 249, 250, 255)
    assert layout.check_game_limits() == []

    _, vanilla = _load(game_data, files, with_kernel=False)
    with pytest.raises(ValueError, match="kernel.bin"):
        vanilla.insert_entry(vanilla.views[0], 0)


@pytest.mark.ff8data(*FILES)
def test_kernel_changed_on_disk_is_never_overwritten(game_data, files):
    _, layout = _load(game_data, files)
    layout.insert_entry(_view(layout, "Med LV Up"), 0)
    kernel = bytearray((files / "kernel.bin").read_bytes())
    kernel[0x43C0 + 22 * 8 + 7] = 13  # another tool moved Med LV Up's last entry meanwhile
    (files / "kernel.bin").write_bytes(bytes(kernel))
    with pytest.raises(RefineKernelError, match="changed since it was opened"):
        verify_refine_ranges(game_data, files / "kernel.bin", layout.abilities)
    with pytest.raises(RefineKernelError):
        write_refine_ranges(game_data, files / "kernel.bin", layout.abilities)
    assert (files / "kernel.bin").read_bytes() == bytes(kernel)


@pytest.mark.ff8data(*FILES)
def test_csv_rows_past_the_last_recipe_are_added_with_a_kernel(game_data, files):
    manager, layout = _load(game_data, files)
    csv_path = files / "refine.csv"
    write_refine_csv(csv_path, layout)
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        lines = list(csv.reader(csv_file, delimiter="|"))
    new_row = ["m003", "", "Med LV Up","New:\\n1 will refine \\ninto 1 Elixir", "1", "1", "16", "1", "1"]
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file, delimiter="|").writerow(new_row)
    assert read_refine_csv(csv_path, layout) == len(lines) - 1 + 1
    med = _view(layout, "Med LV Up")
    assert len(med.entries) == 13 and med.entries[12].element_out_id == 16 and med.texts[12].get_str() == new_row[3]

    _, vanilla = _load(game_data, files, with_kernel=False)
    with pytest.raises(ValueError, match="needs kernel.bin"):
        read_refine_csv(csv_path, vanilla)


@pytest.mark.ff8data(*FILES)
def test_cli_import_adds_recipes_and_writes_the_kernel(files):
    from Cli.shiva import ShivaCliTool
    csv_path = files / "refine.csv"
    args_export = ["export-refine-csv", "--input", str(files / "mngrp.bin"), "--output", str(csv_path),
                   "--kernel", str(files / "kernel.bin")]
    assert _run(ShivaCliTool, args_export) == 0
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file, delimiter="|").writerow(
            ["m002", "", "High Mag-RF", "Blizzara:\\n5 will refine \\ninto 1 Blizzaga", "5", "5", "6", "1", "1"])
    out_kernel = files / "kernel_out.bin"
    assert _run(ShivaCliTool, ["import-refine-csv", "--input", str(files / "mngrp.bin"), "--csv", str(csv_path),
                               "--kernel", str(files / "kernel.bin"), "--output-kernel", str(out_kernel)]) == 0
    assert (files / "kernel.bin").read_bytes() == (EXTRACTED / "main" / "kernel.bin").read_bytes()
    kernel = out_kernel.read_bytes()
    assert kernel[0x43C0 + 21 * 8 + 6:0x43C0 + 21 * 8 + 8] == bytes((4, 10))


def _run(tool_class, argv) -> int:
    tool = tool_class()
    return tool.execute(tool.build_parser().parse_args(argv))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data(*FILES)
def test_shiva_tab_adds_a_recipe_and_saves_both_files(qapp, game_data, files, monkeypatch):
    from Shiva.shivawidget import ShivaWidget
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    widget = ShivaWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.mngrp_binding.open_path(str(files / "mngrp.bin"))
    refine = widget.refine_tab
    assert refine.kernel_notice.isVisibleTo(refine) and not refine.add_recipe_button.isEnabled()

    assert [refine.section_list.item(i).text() for i in range(refine.section_list.count())] ==         [f"m00{n} - all recipes" for n in range(5)]
    widget.kernel_binding.open_path(str(files / "kernel.bin"))
    assert not refine.kernel_notice.isVisibleTo(refine) and refine.section_list.count() == 19
    row = next(i for i, view in enumerate(refine.refine_views) if view.name == "Ammo-RF")
    refine.section_list.setCurrentRow(row)
    assert refine.section_list.currentItem().text() == "m001 - Ammo-RF" and refine.add_recipe_button.isEnabled()
    refine.entry_table.setCurrentCell(15, 0)
    refine.add_recipe_button.click()
    assert refine.entry_table.rowCount() == 17 and refine.entry_table.currentRow() == 16
    assert "Recipe 17 takes the same input as recipe 16" in refine.warning_label.text()

    assert widget.save_files() is True and not messages
    _, reloaded = _load(game_data, files)
    assert len(_view(reloaded, "Ammo-RF").entries) == 17 and _view(reloaded, "Tool-RF").first == 112

    # An added recipe with the kernel.bin removed from the opened files: nothing is written
    refine.add_recipe_button.click()
    widget.kernel_binding.registry.close_file("kernel.bin")
    before = (files / "mngrp.bin").read_bytes()
    assert widget.save_files() is False and "no kernel.bin is open" in messages[-1]
    assert (files / "mngrp.bin").read_bytes() == before
