"""SolomonRing > Cronos extension > Elemental defense table (NegativeElemDef.dll's file)."""
import os

import pytest

from SolomonRing.cronos_elemdef import (read_table, write_table, rows_from_kernel, ELEMENTS, GF_PAGE, MAGIC_PAGE,
                                        CHARACTER_PAGE)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KERNEL = os.path.join(PROJECT_ROOT, "extracted_files", "main", "kernel.bin")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Entry:
    def __init__(self, mask, value):
        self._values = {"j_elem_defense": mask, "j_elem_defense_value": value}

    def get(self, name):
        return self._values[name]


def test_round_trip(tmp_path):
    spells = {1: [50, -50, 0, 0, 0, 0, 0, 0], 7: [0] * 8, 56: [-275, 999, -999, 1, 2, 3, 4, 5]}
    gfs = {2: [30, -30, 0, 0, 0, 0, 0, 0], 15: [0, 0, 0, 0, 0, 0, 0, 100]}
    characters = {0: [10, -10, 0, 0, 0, 0, 0, 0], 7: [0, 0, 0, 0, 0, 0, 0, -20]}
    path = tmp_path / "elemdef.csv"
    write_table(path, spells, gfs, characters, {1: "Fire", 56: "Ultima # with a hash"}, {2: "Ifrit"}, {0: "Squall"})
    assert read_table(path) == (spells, gfs, characters)
    text = path.read_text(encoding="utf-8")
    assert "# id;" + ";".join(ELEMENTS) in text
    assert "1;50;-50;0;0;0;0;0;0    # Fire" in text
    assert "GF2;30;-30;0;0;0;0;0;0    # Ifrit" in text
    assert "CH0;10;-10;0;0;0;0;0;0    # Squall" in text


def test_spells_only_file_has_no_gf_section(tmp_path):
    path = tmp_path / "elemdef.csv"
    write_table(path, {1: [20] + [0] * 7})
    data = "".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#"))
    assert "GF" not in data and "CH" not in data
    assert read_table(path) == ({1: [20] + [0] * 7}, {}, {})


def test_parser_rules_match_the_dll(tmp_path):
    # Same rules as NegativeElemDef.dll: '#' lines, ; , or tab, 9 numbers, spell id 0-255,
    # GF id 0-15 after "GF", character id 0-7 after "CH" (any case), the rest ignored
    path = tmp_path / "elemdef.csv"
    path.write_text("# comment\n\n"
                    "2,10,20,30,40,50,60,70,80\n"
                    "3\t-1\t-2\t-3\t-4\t-5\t-6\t-7\t-8\r\n"
                    "4;1;2;3;4;5;6;7;8;99 trailing\n"
                    "  gf2;30;-30;0;0;0;0;0;0    # Ifrit\n"
                    "GF15;1;1;1;1;1;1;1;1\n"
                    "GF16;1;2;3;4;5;6;7;8\n"         # GF id out of range
                    "ch3;5;5;5;5;5;5;5;5    # Quistis\n"
                    "CH8;1;2;3;4;5;6;7;8\n"          # character id out of range
                    "5;1;2;3\n"                      # too short
                    "300;1;2;3;4;5;6;7;8\n"          # spell id out of range
                    "not;a;line\n", encoding="utf-8")
    spells, gfs, characters = read_table(path)
    assert spells == {2: [10, 20, 30, 40, 50, 60, 70, 80],
                      3: [-1, -2, -3, -4, -5, -6, -7, -8],
                      4: [1, 2, 3, 4, 5, 6, 7, 8]}
    assert gfs == {2: [30, -30, 0, 0, 0, 0, 0, 0], 15: [1] * 8}
    assert characters == {3: [5] * 8}


def test_rows_from_kernel_change_nothing():
    rows = rows_from_kernel({1: _Entry(0x01, 20), 15: _Entry(0x07, 40), 20: _Entry(0xFF, 60), 30: _Entry(0, 0)})
    assert rows[1] == [20, 0, 0, 0, 0, 0, 0, 0]
    assert rows[15] == [40, 40, 40, 0, 0, 0, 0, 0]
    assert rows[20] == [60] * 8
    assert rows[30] == [0] * 8


def _group_names_above(widget):
    names, parent = [], widget.parentWidget()
    while parent is not None:
        names.append(parent.property("group_name"))
        parent = parent.parentWidget()
    return names


@pytest.mark.skipif(not os.path.isfile(KERNEL), reason="needs extracted_files/main/kernel.bin")
def test_dialog_on_a_real_kernel(qapp, tmp_path):
    from SolomonRing.solomonringwidget import SolomonRingWidget
    from SolomonRing.cronos_elemdef import CronosElemDefDialog

    widget = SolomonRingWidget(game_data_folder=os.path.join(PROJECT_ROOT, "FF8GameData"))
    buttons = widget.elemdef_buttons
    assert set(buttons) == {2, 3, 7}
    assert not any(button.isEnabled() for button in buttons.values())
    # Magic > Junction (stats), under the J-Elem defense fields; G-Forces > General
    assert "Junction (stats)" in _group_names_above(buttons[2])
    assert "General" in _group_names_above(buttons[3])
    assert "General" in _group_names_above(buttons[7])   # Characters > General
    widget.load_file(KERNEL)
    assert all(button.isEnabled() for button in buttons.values())

    magic_tab = widget._section_tabs[2]
    entries = {i: magic_tab._entries[i] for i in magic_tab._visible_indices}
    names = {i: entry.get_text(0).strip() for i, entry in entries.items()}
    gf_names = {gf["id"]: gf["name"] for gf in widget.game_data.gforce_data_json["gforce"] if gf["id"] < 16}
    assert gf_names[0] == "Quezacotl" and gf_names[2] == "Ifrit"
    # Default names: Squall's and Rinoa's are empty in kernel.bin (the player names them)
    character_names = widget.default_character_names()
    assert list(character_names.values()) == ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie",
                                              "Seifer", "Edea"]

    dialog = CronosElemDefDialog(widget, entries, names, gf_names, character_names, page=GF_PAGE)
    assert dialog.pages.currentIndex() == GF_PAGE
    assert dialog.rows() == {} and dialog.gf_rows() == {} and dialog.character_rows() == {}
    dialog._fill_from_kernel()
    assert set(dialog.rows()) == set(entries)
    assert dialog.gf_rows() == {} and dialog.character_rows() == {}   # GFs and characters not touched
    fire_id = next(i for i, name in names.items() if name == "Fire")
    assert dialog.rows()[fire_id][0] > 0 and dialog.rows()[fire_id][1:] == [0] * 7

    # Editing a value of an unused row puts it in the table; unticking takes it out.
    dialog.magic_grid.load({})
    dialog.magic_grid.spins[fire_id][1].setValue(-50)
    assert dialog.rows() == {fire_id: [0, -50, 0, 0, 0, 0, 0, 0]}
    dialog.magic_grid.use[fire_id].setChecked(False)
    assert dialog.rows() == {}

    dialog.magic_grid.spins[fire_id][0].setValue(50)
    dialog.magic_grid.spins[fire_id][1].setValue(-50)
    dialog.gf_grid.spins[2][0].setValue(30)    # Ifrit Fire +30 / Ice -30
    dialog.gf_grid.spins[2][1].setValue(-30)
    dialog.character_grid.spins[4][7].setValue(20)   # Rinoa Holy +20
    dialog._path = str(tmp_path / "elemdef.csv")
    assert dialog._save()
    assert read_table(tmp_path / "elemdef.csv") == ({fire_id: [50, -50, 0, 0, 0, 0, 0, 0]},
                                                    {2: [30, -30, 0, 0, 0, 0, 0, 0]},
                                                    {4: [0, 0, 0, 0, 0, 0, 0, 20]})
    assert "CH4;0;0;0;0;0;0;0;20    # Rinoa" in (tmp_path / "elemdef.csv").read_text(encoding="utf-8")
    assert "GF2;30;-30;0;0;0;0;0;0    # Ifrit" in (tmp_path / "elemdef.csv").read_text(encoding="utf-8")

    # Import puts every row back, on every page
    other = CronosElemDefDialog(widget, entries, names, gf_names, character_names, page=CHARACTER_PAGE)
    assert other.pages.currentIndex() == CHARACTER_PAGE
    other._load(*read_table(tmp_path / "elemdef.csv"))
    assert (other.rows(), other.gf_rows(), other.character_rows()) == \
        (dialog.rows(), dialog.gf_rows(), dialog.character_rows())
    for opened in (dialog, other):
        opened._dirty = False
        opened.close()
