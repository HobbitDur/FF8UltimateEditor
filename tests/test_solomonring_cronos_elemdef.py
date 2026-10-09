"""SolomonRing > Cronos extension > Elemental defense table (NegativeElemDef.dll's file)."""
import os

import pytest

from SolomonRing.cronos_elemdef import read_table, write_table, rows_from_kernel, ELEMENTS

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
    rows = {1: [50, -50, 0, 0, 0, 0, 0, 0], 7: [0] * 8, 56: [-275, 999, -999, 1, 2, 3, 4, 5]}
    path = tmp_path / "elemdef.csv"
    write_table(path, rows, {1: "Fire", 56: "Ultima # with a hash"})
    assert read_table(path) == rows
    text = path.read_text(encoding="utf-8")
    assert "# id;" + ";".join(ELEMENTS) in text
    assert "1;50;-50;0;0;0;0;0;0    # Fire" in text


def test_parser_rules_match_the_dll(tmp_path):
    # Same rules as NegativeElemDef.dll: '#' lines, ; , or tab, 9 numbers, id 0-255, rest ignored
    path = tmp_path / "elemdef.csv"
    path.write_text("# comment\n\n"
                    "2,10,20,30,40,50,60,70,80\n"
                    "3\t-1\t-2\t-3\t-4\t-5\t-6\t-7\t-8\r\n"
                    "4;1;2;3;4;5;6;7;8;99 trailing\n"
                    "5;1;2;3\n"                      # too short
                    "300;1;2;3;4;5;6;7;8\n"          # id out of range
                    "not;a;line\n", encoding="utf-8")
    assert read_table(path) == {2: [10, 20, 30, 40, 50, 60, 70, 80],
                                3: [-1, -2, -3, -4, -5, -6, -7, -8],
                                4: [1, 2, 3, 4, 5, 6, 7, 8]}


def test_rows_from_kernel_change_nothing():
    rows = rows_from_kernel({1: _Entry(0x01, 20), 15: _Entry(0x07, 40), 20: _Entry(0xFF, 60), 30: _Entry(0, 0)})
    assert rows[1] == [20, 0, 0, 0, 0, 0, 0, 0]
    assert rows[15] == [40, 40, 40, 0, 0, 0, 0, 0]
    assert rows[20] == [60] * 8
    assert rows[30] == [0] * 8


@pytest.mark.skipif(not os.path.isfile(KERNEL), reason="needs extracted_files/main/kernel.bin")
def test_dialog_on_a_real_kernel(qapp, tmp_path):
    from SolomonRing.solomonringwidget import SolomonRingWidget
    from SolomonRing.cronos_elemdef import CronosElemDefDialog

    widget = SolomonRingWidget(game_data_folder=os.path.join(PROJECT_ROOT, "FF8GameData"))
    assert not widget.elemdef_button.isEnabled()
    # The button lives in Magic > Junction (stats), under the J-Elem defense fields it replaces
    parent, groups = widget.elemdef_button.parentWidget(), []
    while parent is not None:
        groups.append(parent.property("group_name"))
        parent = parent.parentWidget()
    assert "Junction (stats)" in groups
    assert widget.elemdef_button.window() is widget
    widget.load_file(KERNEL)
    assert widget.elemdef_button.isEnabled()

    tab = widget._section_tabs[2]
    entries = {i: tab._entries[i] for i in tab._visible_indices}
    names = {i: entry.get_text(0).strip() for i, entry in entries.items()}
    dialog = CronosElemDefDialog(widget, entries, names)
    assert dialog.rows() == {}                       # nothing used until filled or imported
    dialog._load_rows(rows_from_kernel(entries))
    rows = dialog.rows()
    assert set(rows) == set(entries)
    fire_id = next(i for i, name in names.items() if name == "Fire")
    assert rows[fire_id][0] > 0 and rows[fire_id][1:] == [0] * 7   # Fire defends Fire only

    # Editing a value of an unused spell puts it in the table; unticking takes it out.
    dialog._load_rows({})
    dialog._spins[fire_id][1].setValue(-50)
    assert dialog.rows() == {fire_id: [0, -50, 0, 0, 0, 0, 0, 0]}
    dialog._use[fire_id].setChecked(False)
    assert dialog.rows() == {}

    dialog._spins[fire_id][0].setValue(50)
    dialog._spins[fire_id][1].setValue(-50)
    dialog._path = str(tmp_path / "elemdef.csv")
    assert dialog._save()
    assert read_table(tmp_path / "elemdef.csv") == {fire_id: [50, -50, 0, 0, 0, 0, 0, 0]}
    dialog._dirty = False
    dialog.close()
