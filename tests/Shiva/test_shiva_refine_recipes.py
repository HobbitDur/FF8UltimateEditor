"""Shiva adds and removes refine recipes; kernel.bin, which holds the ranges, is written only by
the Refine ranges dialog.

A refine table (m000-m004) is a flat list of entries; each menu ability of kernel.bin gives the
first and last entry it offers (Menu_Prog19_RefineMenu_Init: count = last - first + 1, a u8, list =
Menu_RefineEntryBuffer + 8 * first, a 0x800-byte buffer). Adding a recipe inserts an entry and its
text, every later entry of the table moving down: the abilities keep kernel.bin's ranges, so the tab
shows what the game would, and a warning lists the abilities whose range kernel.bin must change.
Saving writes mngrp.bin alone; the Refine ranges dialog suggests the new ranges and writes them
(bytes 6-7 only) when asked. Abilities offering the same entries are refused.
"""
import csv
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.m00x.refineabilities import (MAX_TABLE_ENTRIES, RefineKernelError,
                                                         read_refine_abilities)
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from Shiva.ShivaRefine.refinecsv import read_refine_csv, write_refine_csv
from Shiva.ShivaRefine.refineview import RefineLayout

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
EXTRACTED = PROJECT_ROOT / "extracted_files"
FILES = ("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin", "extracted_files/main/kernel.bin")
MENU_ABILITIES = 0x43C0  # offset of the menu ability section in the vanilla kernel.bin


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


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _load(game_data, folder, with_kernel=True):
    manager = MngrpManager(game_data=game_data)
    manager.load_file(str(folder / "mngrphd.bin"), str(folder / "mngrp.bin"))
    abilities = read_refine_abilities(game_data, folder / "kernel.bin") if with_kernel else None
    return manager, RefineLayout(manager, abilities)


def _table(layout, table):
    """Everything the game reads of a table (the text offsets are recomputed when saving)."""
    bin_section, msg_section = layout.tables()[table]
    return [({name: value for name, value in vars(entry).items() if name != "text_offset"}, text.get_str())
            for entry, text in zip(bin_section.entries, msg_section.get_text_list())]


def _view(layout, name):
    return next(view for view in layout.views if view.name == name)


def _ranges(layout, bin_name):
    return [(view.name, view.first, view.last) for view in layout.views if view.bin_name == bin_name]


def _set_range(folder, ability_index, first, last):
    """What SolomonRing does: bytes 6-7 of a menu ability."""
    kernel = bytearray((folder / "kernel.bin").read_bytes())
    kernel[MENU_ABILITIES + ability_index * 8 + 6:MENU_ABILITIES + ability_index * 8 + 8] = bytes((first, last))
    (folder / "kernel.bin").write_bytes(bytes(kernel))


def _run(tool_class, argv) -> int:
    tool = tool_class()
    return tool.execute(tool.build_parser().parse_args(argv))


@pytest.mark.ff8data(*FILES)
def test_abilities_come_only_from_kernel_bin(game_data, files):
    """With a kernel.bin, one view per refine ability, named and sliced as it says (Tool-RF is the
    4th ability of kernel.bin but the last block of m001). Without one, no ability at all: each
    table is one view of all its entries."""
    manager, from_kernel = _load(game_data, files)
    assert [(v.bin_name, v.name, v.ability.index, v.first, v.last) for v in from_kernel.views if v.bin_name == "m001"] == [
        ("m001", "Recov Med-RF", 13, 0, 8), ("m001", "ST Med-RF", 14, 9, 20), ("m001", "Ammo-RF", 15, 21, 36),
        ("m001", "Forbid Med-RF", 17, 37, 56), ("m001", "GFRecov Med-RF", 18, 57, 68),
        ("m001", "GFAbl Med-RF", 19, 69, 110), ("m001", "Tool-RF", 16, 111, 142)]
    assert len(from_kernel.views) == 19 and all(v.kind == "ability" for v in from_kernel.views)
    assert sum(len(v.entries) for v in from_kernel.views) == 377 and not from_kernel.warnings

    without = RefineLayout(manager)
    assert [(v.bin_name, v.kind, v.first, v.last) for v in without.views] == [
        ("m000", "table", 0, 101), ("m001", "table", 0, 142), ("m002", "table", 0, 9),
        ("m003", "table", 0, 11), ("m004", "table", 0, 109)]
    assert without.abilities == [] and not without.warnings


@pytest.mark.ff8data(*FILES)
def test_added_recipe_shifts_the_table_and_keeps_kernel_ranges(game_data, files):
    """The new recipe pushes every later one down; each ability still offers what kernel.bin says,
    so ST Med-RF now starts on Recov Med-RF's old last recipe, until kernel.bin is edited."""
    manager, layout = _load(game_data, files)
    recov = _view(layout, "Recov Med-RF")
    old_last = _table(layout, 1)[8]
    assert layout.insert_entry(recov, 0) == 1
    assert _ranges(layout, "m001")[:2] == [("Recov Med-RF", 0, 8), ("ST Med-RF", 9, 20)]
    assert len(recov.bin_section.entries) == 144 and vars(recov.entries[1]) == vars(recov.entries[0])
    assert _table(layout, 1)[9] == old_last
    assert layout.kernel_update_needed
    assert layout.warnings == [layout.kernel_warnings()[0]]
    assert "m001: 1 recipe(s) added" in layout.warnings[0] and "kernel.bin must be modified" in layout.warnings[0]
    assert "Recov Med-RF (0-8)" in layout.warnings[0] and "Tool-RF (111-142)" in layout.warnings[0]

    recov.entries[1].element_in_id = 50
    recov.texts[1].set_str("Test:\\n1 will refine \\ninto 1 Potion")
    expected = _table(layout, 1)
    kernel = (files / "kernel.bin").read_bytes()
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))
    assert (files / "kernel.bin").read_bytes() == kernel
    _, reloaded = _load(game_data, files)
    assert _table(reloaded, 1) == expected


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
    expected = _table(layout, 1)
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))

    reloaded_manager, reloaded = _load(game_data, files)
    assert _table(reloaded, 1) == expected and len(expected) == 183
    assert sum(len(text) for text in reloaded_manager.m00_manager.get_msg_list()[1].get_text_list()) > 8192
    others_after = {section.id: bytes(section.get_data_hex()) for section in reloaded_manager.mngrp.get_section_list()
                    if section not in reloaded_manager.m00_manager.get_bin_list()
                    + reloaded_manager.m00_manager.get_msg_list()}
    assert others_after == others_before


@pytest.mark.ff8data(*FILES)
def test_removed_recipe_shifts_the_table_back(game_data, files):
    manager, layout = _load(game_data, files)
    t_mag = _view(layout, "T Mag-RF")
    removed_text = t_mag.texts[2].get_str()
    i_first = _view(layout, "I Mag-RF").texts[0].get_str()
    layout.remove_entry(t_mag, 2)
    assert (t_mag.first, t_mag.last) == (0, 6) and _view(layout, "I Mag-RF").first == 7
    assert removed_text not in [text.get_str() for text in t_mag.texts] and t_mag.texts[6].get_str() == i_first
    assert layout.warnings[0] == ("Forbid Mag-RF offers recipes 96-101 of m000, which only has 101: "
                                  "the extra ones are empty.")
    assert "m000: 1 removed, the recipes from entry 2 on moved" in layout.warnings[1]
    assert "T Mag-RF (0-6)" in layout.warnings[1]
    expected = _table(layout, 0)
    manager.save_file(str(files / "mngrp.bin"), str(files / "mngrphd.bin"))
    _, reloaded = _load(game_data, files)
    assert _table(reloaded, 0) == expected


@pytest.mark.ff8data(*FILES)
def test_limits_and_layout_without_kernel(game_data, files):
    _, layout = _load(game_data, files)
    mid, high = _view(layout, "Mid Mag-RF"), _view(layout, "High Mag-RF")  # the 0x800 buffer
    while len(mid.bin_section.entries) < MAX_TABLE_ENTRIES:
        layout.insert_entry(mid, 0)
    with pytest.raises(ValueError, match="256"):
        layout.insert_entry(high, 0)
    assert layout.check_game_limits() == []

    with pytest.raises(ValueError, match="entry 0 to 12, not 13"):
        layout.insert_at(3, 13, 0)
    with pytest.raises(ValueError, match="entries 0 to 11, not 12"):
        layout.remove_at(3, 12)


@pytest.mark.ff8data(*FILES)
def test_recipes_at_any_index_of_the_table(game_data, files):
    """A recipe goes at any entry 0 to the table's count: added at the end it moves no range, so
    no ability offers it until kernel.bin points one at it. Without a kernel.bin, the same."""
    _, layout = _load(game_data, files)
    layout.insert_at(0, 102, 0)
    assert _ranges(layout, "m000")[-2:] == [("Forbid Mag-RF", 96, 101), ("(no ability) 102-102", 102, 102)]
    assert _table(layout, 0)[102] == _table(layout, 0)[0]
    assert layout.warnings == ["m000: 1 recipe(s) added, the recipes from entry 102 on moved. no refine ability's "
                               "range moved: a recipe past them is offered by none until an ability points at it "
                               "in kernel.bin (\"Refine ranges...\" button)"]
    assert layout.suggested_ranges()[12] == [96, 102]  # added after Forbid Mag-RF's last: suggested to it
    layout.remove_at(0, 102)
    assert len(layout.tables()[0][0].entries) == 102

    _, without = _load(game_data, files, with_kernel=False)
    without.insert_at(3, 0, 11)
    assert without.views[3].last == 12 and "open it to see which" in without.warnings[0]


@pytest.mark.ff8data(*FILES)
def test_csv_new_rows_go_after_their_ability_in_csv_order(game_data, files):
    """A row with an empty Entry goes right after the last entry kernel.bin gives its ability, the
    rows of one ability in CSV order, whatever order the abilities come in."""
    _, layout = _load(game_data, files)
    csv_path = files / "refine.csv"
    write_refine_csv(csv_path, layout)
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        lines = list(csv.reader(csv_file, delimiter="|"))
    new_rows = [["m002", "", "Mid Mag-RF", "Mid one", "1", "1", "16", "1", "1"],
                ["m002", "", "High Mag-RF", "High one", "1", "1", "17", "1", "1"],
                ["m002", "", "Mid Mag-RF", "Mid two", "1", "1", "18", "1", "1"],
                ["m003", "", "Med LV Up", "New:\\n1 will refine \\ninto 1 Elixir", "1", "1", "16", "1", "1"]]
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file, delimiter="|").writerows(new_rows)
    assert read_refine_csv(csv_path, layout) == len(lines) - 1 + 4
    m002 = [text for _, text in _table(layout, 2)]
    assert len(m002) == 13 and (m002[4], m002[5], m002[12]) == ("Mid one", "Mid two", "High one")
    # kernel.bin's ranges: the last 3 recipes of the table are offered by no ability until it is edited
    assert _ranges(layout, "m002") == [("Mid Mag-RF", 0, 3), ("High Mag-RF", 4, 9), ("(no ability) 10-12", 10, 12)]
    m003 = _table(layout, 3)
    assert len(m003) == 13 and m003[12][0]["element_out_id"] == 16 and m003[12][1] == new_rows[3][3]
    assert any(line.startswith("m002: 3 recipe(s) added") for line in layout.warnings)

    _, vanilla = _load(game_data, files, with_kernel=False)
    with pytest.raises(ValueError, match="needs kernel.bin"):
        read_refine_csv(csv_path, vanilla)


@pytest.mark.ff8data(*FILES)
def test_cli_import_adds_recipes_and_only_reads_the_kernel(files, capsys):
    from Cli.shiva import ShivaCliTool
    csv_path = files / "refine.csv"
    args_export = ["export-refine-csv", "--input", str(files / "mngrp.bin"), "--output", str(csv_path),
                   "--kernel", str(files / "kernel.bin")]
    assert _run(ShivaCliTool, args_export) == 0
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        csv.writer(csv_file, delimiter="|").writerow(
            ["m002", "", "High Mag-RF", "Blizzara:\\n5 will refine \\ninto 1 Blizzaga", "5", "5", "6", "1", "1"])
    out_mngrp = files / "mngrp_out.bin"
    assert _run(ShivaCliTool, ["import-refine-csv", "--input", str(files / "mngrp.bin"), "--csv", str(csv_path),
                               "--kernel", str(files / "kernel.bin"), "--output", str(out_mngrp),
                               "--output-mngrphd", str(files / "mngrphd_out.bin")]) == 0
    assert (files / "kernel.bin").read_bytes() == (EXTRACTED / "main" / "kernel.bin").read_bytes()
    assert "[warning] m002: 1 recipe(s) added" in capsys.readouterr().out
    manager = MngrpManager(game_data=GameData(str(PROJECT_ROOT / "FF8GameData")))
    manager.game_data.load_all()
    manager.load_file(str(files / "mngrphd_out.bin"), str(out_mngrp))
    assert len(manager.m00_manager.get_bin_list()[2].entries) == 11


def _overlapping_kernel(folder):
    """The vanilla kernel.bin with I Mag-RF starting on T Mag-RF's last entry (6): two abilities
    offering the same recipe, as older Shiva versions could leave it."""
    _set_range(folder, 6, 6, 13)


@pytest.mark.ff8data(*FILES)
def test_overlapping_ranges_are_refused(game_data, files):
    """Nihil's report: E Mag-RF offered T Mag-RF's first entries, so editing one edited the other.
    Each ability owns its block: a kernel.bin where two overlap is refused, naming them."""
    _overlapping_kernel(files)
    with pytest.raises(RefineKernelError, match=r"T Mag-RF \(menu ability 5, entries 0-6\) and I Mag-RF "
                                                r"\(menu ability 6, entries 6-13\)"):
        read_refine_abilities(game_data, files / "kernel.bin")

    from Cli.shiva import ShivaCliTool
    assert _run(ShivaCliTool, ["export-refine-csv", "--input", str(files / "mngrp.bin"),
                               "--output", str(files / "refine.csv"), "--kernel", str(files / "kernel.bin")]) != 0
    assert not (files / "refine.csv").exists()


def _shiva(files, monkeypatch, index=None, errors=None):
    """A Shiva with the test files open; index answers the add / remove recipe popups (None: the
    index they propose). Error popups fail the test, unless an `errors` list collects them."""
    from Shiva.shivawidget import ShivaWidget
    monkeypatch.setattr(QInputDialog, "getInt",
                        lambda parent, title, label, value, low, high: (value if index is None else index, True))
    collect = (lambda *args: errors.append(args[2])) if errors is not None else (lambda *args: pytest.fail(args[2]))
    monkeypatch.setattr(QMessageBox, "critical", collect)
    monkeypatch.setattr(QMessageBox, "warning", collect)
    widget = ShivaWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.mngrp_binding.open_path(str(files / "mngrp.bin"))
    widget.kernel_binding.open_path(str(files / "kernel.bin"))
    return widget


def _select(refine, name):
    refine.section_list.setCurrentRow(next(i for i, view in enumerate(refine.refine_views) if view.name == name))


@pytest.mark.ff8data(*FILES)
def test_shiva_tab_adds_a_recipe_and_saves_only_mngrp(qapp, game_data, files, monkeypatch):
    widget = _shiva(files, monkeypatch)
    refine = widget.refine_tab
    assert widget.kernel_binding.read_only
    assert refine.section_list.count() == 19 and not refine.warning_label.isVisibleTo(refine)
    _select(refine, "Ammo-RF")
    refine.entry_table.setCurrentCell(15, 0)
    refine.add_recipe_button.click()  # the popup proposes entry 37, right after the selected recipe
    # Added after Ammo-RF's last recipe: it is Forbid Med-RF's first until kernel.bin is edited
    assert refine.entry_table.rowCount() == 16
    assert refine.warning_label.isVisibleTo(refine) and "kernel.bin must be modified" in refine.warning_label.text()
    assert "Forbid Med-RF (37-56)" in refine.warning_label.text() and "Ammo-RF" not in refine.warning_label.text()

    kernel = (files / "kernel.bin").read_bytes()
    assert widget.save_files() is True
    assert (files / "kernel.bin").read_bytes() == kernel
    _, reloaded = _load(game_data, files)
    assert len(reloaded.tables()[1][0].entries) == 144

    # The same kernel.bin opened again: still to edit. Once edited (SolomonRing), the warning goes
    refine.set_kernel_abilities(read_refine_abilities(game_data, files / "kernel.bin"))
    assert "kernel.bin must be modified" in refine.warning_label.text()
    _set_range(files, 15, 21, 37)
    for index, (first, last) in ((17, (38, 57)), (18, (58, 69)), (19, (70, 111)), (16, (112, 143))):
        _set_range(files, index, first, last)
    refine.set_kernel_abilities(read_refine_abilities(game_data, files / "kernel.bin"))
    assert "kernel.bin must be modified" not in refine.warning_label.text()
    _select(refine, "Ammo-RF")
    assert refine.entry_table.rowCount() == 17


@pytest.mark.ff8data(*FILES)
def test_shiva_saves_twice_in_one_session_and_removes_the_added_recipe(qapp, files, monkeypatch):
    """The Sprite and Tutorial tabs swap their sections in unpadded on every save: from the second
    save on, mngrphd.bin got every later section's offset 496 bytes short (no menu images in game)."""
    originals = {name: (files / name).read_bytes() for name in ("mngrp.bin", "mngrphd.bin", "kernel.bin")}
    widget = _shiva(files, monkeypatch)
    refine = widget.refine_tab
    _select(refine, "Ammo-RF")
    refine.entry_table.setCurrentCell(14, 0)
    refine.add_recipe_button.click()
    assert widget.save_files() is True
    refine.entry_table.setCurrentCell(15, 0)
    refine.remove_recipe_button.click()
    assert widget.save_files() is True and widget.save_files() is True
    assert {name: (files / name).read_bytes() for name in originals} == originals


@pytest.mark.ff8data(*FILES)
def test_shiva_tab_refuses_an_overlapping_kernel(qapp, files, monkeypatch):
    """An explicit error naming the abilities, and the tables shown whole as without a kernel.bin."""
    _overlapping_kernel(files)
    errors = []
    widget = _shiva(files, monkeypatch, errors=errors)
    refine = widget.refine_tab
    assert len(errors) == 1 and "T Mag-RF (menu ability 5, entries 0-6) and I Mag-RF" in errors[0]
    assert refine.kernel_notice.isVisibleTo(refine) and refine.section_list.count() == 5
    assert widget.kernel_path == ""


@pytest.mark.ff8data(*FILES)
def test_shiva_tab_names_magic_as_the_kernel_does(qapp, game_data, files):
    """A mod's kernel.bin renames spells: the refine combos show its names, not magic.json's."""
    from Shiva.ShivaRefine.shivarefinewidget import ShivaRefineWidget
    manager, layout = _load(game_data, files)
    refine = ShivaRefineWidget(game_data)
    refine.load_from_mngrp(manager)
    refine.set_kernel_abilities(layout.abilities)
    _select(refine, "T Mag-RF")
    assert refine.entry_table.cellWidget(0, refine.COLUMN_OUTPUT).currentText() == "Thundara"
    refine.set_kernel_names(refine._item_entries, {8: "Bolt 2"})
    assert refine.entry_table.cellWidget(0, refine.COLUMN_OUTPUT).currentText() == "Bolt 2"


@pytest.mark.ff8data(*FILES)
def test_shiva_popups_add_at_the_end_and_remove_any_entry(qapp, game_data, files, monkeypatch):
    """The index typed in the popup is an entry of the whole table, 0 to the count when adding."""
    widget = _shiva(files, monkeypatch, index=102)
    refine = widget.refine_tab
    _select(refine, "T Mag-RF")
    refine.entry_table.setCurrentCell(1, 0)
    refine.add_recipe_button.click()
    entries = refine.layout.tables()[0][0].entries
    assert len(entries) == 103 and vars(entries[102]) == vars(entries[1])
    assert any(view.name == "(no ability) 102-102" for view in refine.refine_views)

    monkeypatch.setattr(QInputDialog, "getInt", lambda *args: (0, True))
    first_text = refine.layout.tables()[0][1].get_text_list()[1].get_str()
    refine.remove_recipe_button.click()
    assert len(entries) == 102 and refine.layout.tables()[0][1].get_text_list()[0].get_str() == first_text

    monkeypatch.setattr(QInputDialog, "getInt", lambda *args: (0, False))  # Cancel: nothing changes
    refine.add_recipe_button.click()
    refine.remove_recipe_button.click()
    assert len(entries) == 102


@pytest.mark.ff8data(*FILES)
def test_suggested_ranges_follow_the_recipes(game_data, files):
    """A recipe added at entry p goes to the ability holding p - 1, the later ranges move; a removed
    one shrinks the ability holding it. Nothing is applied: the views keep kernel.bin's ranges."""
    _, layout = _load(game_data, files)
    assert layout.suggested_ranges()[13] == [0, 8]  # nothing moved yet: kernel.bin's
    layout.insert_at(1, 1, 0)       # inside Recov Med-RF (0-8)
    layout.insert_at(1, 38, 37)     # right after Ammo-RF, now 22-37
    layout.remove_at(0, 2)          # inside T Mag-RF (0-6)
    suggested = layout.suggested_ranges()
    assert [suggested[index] for index in (13, 14, 15, 17, 18, 19, 16)] == [
        [0, 9], [10, 21], [22, 38], [39, 58], [59, 70], [71, 112], [113, 144]]
    assert [suggested[index] for index in (5, 6, 12)] == [[0, 5], [6, 12], [95, 100]]
    assert _ranges(layout, "m001")[0] == ("Recov Med-RF", 0, 8)


def test_range_problems_name_each_ability():
    from FF8GameData.menu.mngrp.m00x.refineabilities import RefineAbility, range_problems
    abilities = [RefineAbility(index=5, table=0, first=0, last=7, name="T Mag-RF"),
                 RefineAbility(index=6, table=0, first=7, last=13, name="I Mag-RF"),
                 RefineAbility(index=24, table=0, first=104, last=105, name="E Mag-RF"),
                 RefineAbility(index=20, table=2, first=4, last=3, name="Mid Mag-RF")]
    problems = [(ability.name, reason) for ability, reason in range_problems(abilities, [103, 0, 10, 0, 0])]
    assert problems == [("E Mag-RF", "last 105 is past the table's end (entries 0-102)"),
                        ("Mid Mag-RF", "first 4 is after last 3: no recipe"),
                        ("T Mag-RF", "offers the same entries as I Mag-RF"),
                        ("I Mag-RF", "offers the same entries as T Mag-RF")]


@pytest.mark.ff8data(*FILES)
def test_write_refine_ranges_patches_only_the_changed_bytes(game_data, files):
    from FF8GameData.menu.mngrp.m00x.refineabilities import write_refine_ranges
    abilities = read_refine_abilities(game_data, files / "kernel.bin")
    before = (files / "kernel.bin").read_bytes()
    assert write_refine_ranges(game_data, files / "kernel.bin", abilities, {5: (0, 7), 6: (8, 13), 7: (14, 23)}) == 2
    after = (files / "kernel.bin").read_bytes()
    assert [index for index in range(len(before)) if before[index] != after[index]] == [
        MENU_ABILITIES + 5 * 8 + 7, MENU_ABILITIES + 6 * 8 + 6]
    # What was read is not what the file holds anymore: refused, nothing written
    with pytest.raises(RefineKernelError, match="changed since it was read"):
        write_refine_ranges(game_data, files / "kernel.bin", abilities, {5: (0, 8)})
    assert (files / "kernel.bin").read_bytes() == after


@pytest.mark.ff8data(*FILES)
def test_ranges_dialog_checks_before_writing(qapp, game_data, files):
    from Shiva.ShivaRefine.refinerangesdialog import RefineRangesDialog
    _, layout = _load(game_data, files)
    layout.insert_at(2, 4, 3)  # after Mid Mag-RF's last recipe
    tables = layout.tables()
    dialog = RefineRangesDialog(None, layout.abilities, layout.suggested_ranges(),
                                [len(b.entries) for b, _ in tables], [b.m00bin.name for b, _ in tables])
    assert dialog.changed() == [21, 20] or sorted(dialog.changed()) == [20, 21]
    assert dialog.write_button.isEnabled() and not dialog.problem_label.text()
    row = next(row for row, ability in enumerate(dialog.abilities) if ability.name == "Mid Mag-RF")
    assert (dialog.first_spins[row].value(), dialog.last_spins[row].value()) == (0, 4)
    assert dialog.first_spins[row].font().bold() is False and dialog.last_spins[row].font().bold() is True
    dialog.last_spins[row].setValue(5)  # now overlaps High Mag-RF (5-10)
    assert not dialog.write_button.isEnabled() and "Mid Mag-RF: offers the same entries as High Mag-RF" \
        in dialog.problem_label.text()
    dialog.last_spins[row].setValue(4)
    assert dialog.write_button.isEnabled()


@pytest.mark.ff8data(*FILES)
def test_shiva_writes_the_suggested_ranges_on_demand(qapp, game_data, files, monkeypatch):
    """Add a recipe, open Refine ranges, write: kernel.bin gets Ammo-RF one longer and the later
    abilities moved, the warning goes, and Ammo-RF shows its 17 recipes."""
    from PyQt6.QtWidgets import QDialog
    from Shiva.ShivaRefine.refinerangesdialog import RefineRangesDialog
    monkeypatch.setattr(RefineRangesDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    widget = _shiva(files, monkeypatch)
    refine = widget.refine_tab
    assert refine.ranges_button.isEnabled()
    _select(refine, "Ammo-RF")
    assert refine.entry_table.verticalHeaderItem(0).text() == "21"  # rows named by their table entry
    refine.entry_table.setCurrentCell(15, 0)
    refine.add_recipe_button.click()
    assert "kernel.bin must be modified" in refine.warning_label.text()

    refine.ranges_button.click()
    abilities = {ability.index: (ability.first, ability.last)
                 for ability in read_refine_abilities(game_data, files / "kernel.bin")}
    assert [abilities[index] for index in (13, 14, 15, 17, 18, 19, 16)] == [
        (0, 8), (9, 20), (21, 37), (38, 57), (58, 69), (70, 111), (112, 143)]
    assert "kernel.bin must be modified" not in refine.warning_label.text()
    _select(refine, "Ammo-RF")
    assert refine.entry_table.rowCount() == 17 and refine.entry_table.verticalHeaderItem(16).text() == "37"
    # mngrp.bin is saved apart, with the toolbar
    assert widget.save_files() is True
    _, reloaded = _load(game_data, files)
    assert len(_view(reloaded, "Ammo-RF").entries) == 17 and not reloaded.warnings


@pytest.mark.ff8data(*FILES)
def test_ranges_past_the_table_end_grow_the_table(qapp, game_data, files, monkeypatch):
    """Forbid Mag-RF (96-101) is the end of m000 (102 recipes): setting its last entry to 103 in
    Refine ranges is allowed, writes 96-103 into kernel.bin and appends 2 recipes to m000, copies
    of the one before, that mngrp.bin then saves."""
    from PyQt6.QtWidgets import QDialog
    from Shiva.ShivaRefine.refinerangesdialog import RefineRangesDialog

    def accept_longer_forbid(dialog):
        row = next(row for row, ability in enumerate(dialog.abilities) if ability.name == "Forbid Mag-RF")
        dialog.last_spins[row].setValue(103)
        assert dialog.write_button.isEnabled() and not dialog.problem_label.text()
        assert dialog.growth() == {0: 2} and "grows from 102 to 104" in dialog.growth_label.text()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(RefineRangesDialog, "exec", accept_longer_forbid)
    widget = _shiva(files, monkeypatch)
    refine = widget.refine_tab
    last_text = refine.layout.tables()[0][1].get_text_list()[101].get_str()
    refine.ranges_button.click()
    forbid = next(ability for ability in read_refine_abilities(game_data, files / "kernel.bin")
                  if ability.name == "Forbid Mag-RF")
    assert (forbid.first, forbid.last) == (96, 103)
    assert len(refine.layout.tables()[0][0].entries) == 104 and not refine.layout.warnings
    assert len(_view(refine.layout, "Forbid Mag-RF").entries) == 8
    assert widget.save_files() is True
    _, reloaded = _load(game_data, files)
    texts = reloaded.tables()[0][1].get_text_list()
    assert len(reloaded.tables()[0][0].entries) == 104 and [text.get_str() for text in texts[102:]] == [last_text] * 2
    assert len(_view(reloaded, "Forbid Mag-RF").entries) == 8 and not reloaded.warnings


@pytest.mark.ff8data(*FILES)
def test_recipes_appended_into_a_kernel_range_past_the_end_fill_it(game_data, files):
    """kernel.bin already gives an ability entries 102-103 of m000 (102 recipes, set in
    SolomonRing): recipes appended after the last one fill that range. No recipe moved, so no
    range changes and kernel.bin needs nothing; Forbid Mag-RF (96-101) is left alone. Appended past
    every range, a recipe makes only the ability ending right before it one longer."""
    kernel = bytearray((files / "kernel.bin").read_bytes())
    kernel[MENU_ABILITIES + 6:MENU_ABILITIES + 8] = bytes((0, 102, 103))[1:]
    kernel[MENU_ABILITIES + 5] = 0  # menu ability 0 now opens m000, entries 102-103
    (files / "kernel.bin").write_bytes(bytes(kernel))
    _, layout = _load(game_data, files)
    new = next(view for view in layout.views if view.ability.index == 0)
    assert (new.first, new.last, len(new.entries)) == (102, 103, 0)
    before = layout.suggested_ranges()
    layout.insert_at(0, 102, 101)
    layout.insert_at(0, 103, 102)
    assert layout.suggested_ranges() == before and not layout.shifts and not layout.warnings
    assert len(next(view for view in layout.views if view.ability.index == 0).entries) == 2
    layout.insert_at(0, 104, 103)  # past every range: menu ability 0 grows, nothing else moves
    suggested = layout.suggested_ranges()
    assert suggested[0] == [102, 104] and suggested[12] == [96, 101]
    assert {index: rng for index, rng in suggested.items() if index != 0} ==         {index: rng for index, rng in before.items() if index != 0}
