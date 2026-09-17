"""Tests for the Chocoboy widget (world-map scripts of wmsetxx.obj).

Every test loads the real ``wmsetus.obj`` through the same load callback the shared header
toolbar's binding dispatches to, so they are all ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
WMSET_REL = "extracted_files/world/dat/wmsetus.obj"
WMSET = PROJECT_ROOT / WMSET_REL

pytestmark = pytest.mark.ff8data(WMSET_REL)


@pytest.fixture(scope="module")
def qapp():
    # ChocoboyWidget builds real Qt widgets, so a QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp):
    from Chocoboy.chocoboywidget import ChocoboyWidget

    tool = ChocoboyWidget(icon_path=str(PROJECT_ROOT / "Resources"),
                          game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    tool.load_file(str(WMSET))
    return tool


def test_loading_fills_the_first_script_of_the_first_section(widget):
    assert widget.tabs.isEnabled()
    assert widget.script_section_combo.currentData() == 7
    assert widget.script_list.count() == 38
    assert widget.script_list.currentRow() == 0
    assert widget.instruction_table.rowCount() > 0
    assert widget.pseudo_code_view.toPlainText().strip().endswith("RETURN")


def test_switching_section_reloads_the_script_list(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36, the global events
    assert widget.script_section_combo.currentData() == 36
    assert widget.script_list.count() == 92
    assert widget.instruction_table.rowCount() > 0


def test_a_word_opcode_shows_one_parameter_and_a_byte_pair_shows_two(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(0)
    # Script 0 starts with IF, then CHECK_BIT_FLAG 61, 1 (two bytes), then
    # CHECK_WORLD_MAP_STATE 14 (one word).
    bit_flag_row, world_state_row = 1, 2
    assert widget.instruction_table.cellWidget(bit_flag_row, 1).currentText() == "CHECK_BIT_FLAG"
    assert widget.instruction_table.cellWidget(bit_flag_row, 2).value() == 61
    assert widget.instruction_table.cellWidget(bit_flag_row, 3).isEnabled()
    assert widget.instruction_table.cellWidget(bit_flag_row, 3).value() == 1

    assert widget.instruction_table.cellWidget(world_state_row, 1).currentText() == "CHECK_WORLD_MAP_STATE"
    assert widget.instruction_table.cellWidget(world_state_row, 2).value() == 14
    assert not widget.instruction_table.cellWidget(world_state_row, 3).isEnabled()


def test_editing_a_parameter_reaches_the_bytes_and_the_pseudo_code(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(0)
    widget.instruction_table.cellWidget(1, 2).setValue(7)  # CHECK_BIT_FLAG 61, 1 -> 7, 1

    assert widget.manager.script_sections[36].instructions[1].param1 == 7
    assert "CHECK_BIT_FLAG 7, 1" in widget.pseudo_code_view.toPlainText()


def test_adding_and_removing_an_instruction_keeps_the_file_readable(widget, tmp_path):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(5)
    before = widget.instruction_table.rowCount()

    widget.instruction_table.setCurrentCell(2, 0)
    widget._on_add_instruction()
    assert widget.instruction_table.rowCount() == before + 1

    destination = tmp_path / "wmsetus.obj"
    widget.manager.save_file(str(destination))

    from Chocoboy.chocoboymanager import ChocoboyManager
    reloaded = ChocoboyManager(widget.game_data)
    reloaded.load_file(str(destination))
    assert reloaded.script_sections[36].dangling_gotos() == []
    assert len(reloaded.script_sections[36].entry_offsets) == 92

    widget.instruction_table.setCurrentCell(2, 0)
    widget._on_remove_instruction()
    assert widget.instruction_table.rowCount() == before


def test_a_dialog_opcode_shows_the_text_it_opens(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    lookup = widget.manager.dialog_lookup()
    for entry in range(widget.script_list.count()):
        widget.script_list.setCurrentRow(entry)
        for row in range(widget.instruction_table.rowCount()):
            combo = widget.instruction_table.cellWidget(row, 1)
            if combo.currentText() == "SHOW_TEXT_BOX":
                text_id = widget.instruction_table.cellWidget(row, 3).value()
                assert lookup[text_id] in widget.instruction_table.item(row, 4).text()
                return
    pytest.fail("no SHOW_TEXT_BOX found in section 36")


def test_the_text_tab_lists_the_dialogs_and_says_which_script_opens_them(widget):
    widget.text_section_combo.setCurrentIndex(0)  # section 13
    assert widget.text_list.count() == 151
    widget.text_list.setCurrentRow(61)
    assert widget.text_edit.toPlainText() == widget.manager.dialog_lookup()[61]
    assert "Section 36" in widget.text_users_view.toPlainText()


def test_editing_a_text_reaches_the_saved_file(widget, tmp_path):
    widget.text_section_combo.setCurrentIndex(0)  # section 13
    widget.text_list.setCurrentRow(61)
    widget.text_edit.setPlainText("Chocoboy was here")

    destination = tmp_path / "wmsetus.obj"
    widget.manager.save_file(str(destination))

    from Chocoboy.chocoboymanager import ChocoboyManager
    reloaded = ChocoboyManager(widget.game_data)
    reloaded.load_file(str(destination))
    assert reloaded.dialog_lookup()[61] == "Chocoboy was here"
    assert reloaded.dialog_lookup()[60] == widget.manager.dialog_lookup()[60]
