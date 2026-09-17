"""Tests for the Chocoboy widget (world-map scripts of wmsetxx.obj).

Every test loads the real ``wmsetus.obj`` through the same load callback the shared header
toolbar's binding dispatches to, so they are all ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtCore import Qt
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


def test_the_value_column_says_what_the_numbers_mean(widget):
    """The point of the column: 64, 90 and 60, 2 say nothing on their own."""
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(1)
    values = {widget.instruction_table.cellWidget(row, 1).currentText():
              widget.instruction_table.item(row, 4).text()
              for row in range(widget.instruction_table.rowCount())}
    assert values["CHECK_BUTTON_INPUT"] in ("Cross", "any button, or the stick pushed past 45")
    assert values["CHECK_WORLD_MAP_STATE"] == "player cannot move (a dialog is up)"
    assert values["GOTO"].startswith("lands on CONSUME_INPUT, in script #")


def test_an_add_item_is_named_and_an_add_entity_is_placed(widget):
    widget.script_section_combo.setCurrentIndex(1)  # section 9, the spawn scripts
    widget.script_list.setCurrentRow(19)
    spawns = [widget.instruction_table.item(row, 4).text()
              for row in range(widget.instruction_table.rowCount())
              if widget.instruction_table.cellWidget(row, 1).currentText() == "ADD_ENTITY"]
    assert spawns, "expected ADD_ENTITY instructions in section 9"
    assert any(text.startswith("position record") for text in spawns)


def test_selecting_a_flag_shows_everywhere_else_it_is_touched(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(1)
    flag_row = next(row for row in range(widget.instruction_table.rowCount())
                    if widget.instruction_table.cellWidget(row, 1).currentText() == "CHECK_BIT_FLAG")
    widget.instruction_table.setCurrentCell(flag_row, 0)

    flag = widget.instruction_table.cellWidget(flag_row, 2).value()
    assert widget.usage_group.title() == f"What else touches save flag {flag}"
    users = [widget.usage_view.item(row) for row in range(widget.usage_view.count())]
    assert len(users) > 1, "flag 63 is set by several scripts, not just checked by this one"
    assert all(item.text().startswith("Section ") for item in users)
    # Each line carries where it is, so double-clicking one goes there
    assert all(item.data(Qt.ItemDataRole.UserRole) is not None for item in users)


def test_following_a_jump_lands_on_the_instruction_it_points_at(widget):
    """A jump's target is a byte offset, so the only way to read one is to be taken there."""
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(1)
    goto_row = next(row for row in range(widget.instruction_table.rowCount())
                    if widget.instruction_table.cellWidget(row, 1).currentText() == "GOTO")
    target_offset = widget.instruction_table.cellWidget(goto_row, 2).value()

    widget._on_instruction_double_clicked(goto_row, 0)

    selected = widget.instruction_table.currentRow()
    assert widget.instruction_table.item(selected, 0).text() == str(target_offset)
    assert widget.instruction_table.cellWidget(selected, 1).currentText() == "CONSUME_INPUT"


def test_a_cross_reference_line_takes_you_to_that_script(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(1)
    flag_row = next(row for row in range(widget.instruction_table.rowCount())
                    if widget.instruction_table.cellWidget(row, 1).currentText() == "CHECK_BIT_FLAG")
    widget.instruction_table.setCurrentCell(flag_row, 0)

    # The last line of the list is in some other script: going there must show that script
    last = widget.usage_view.item(widget.usage_view.count() - 1)
    section_index, offset = last.data(Qt.ItemDataRole.UserRole)
    widget._on_usage_double_clicked(last)

    assert widget.script_section_combo.currentData() == section_index
    selected = widget.instruction_table.currentRow()
    assert widget.instruction_table.item(selected, 0).text() == str(offset)


def test_the_check_finds_nothing_wrong_with_the_shipped_scripts(widget):
    """The strongest thing the check can be held to: it must not cry wolf over the real file."""
    for section_index, section in widget.manager.script_sections.items():
        problems = section.problems(must_return=section_index != 9)
        assert problems == [], f"section {section_index}: {problems[:3]}"


def test_an_edit_can_be_undone_and_redone(widget):
    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(0)
    before = widget.manager.script_sections[36].instructions[1].param1

    widget.instruction_table.cellWidget(1, 2).setValue(7)
    assert widget.manager.script_sections[36].instructions[1].param1 == 7

    widget.undo()
    assert widget.manager.script_sections[36].instructions[1].param1 == before
    widget.redo()
    assert widget.manager.script_sections[36].instructions[1].param1 == 7


def test_undo_brings_back_what_a_text_import_replaced(widget, tmp_path):
    """The hardest thing to undo: an import rewrites every script of the section at once, and
    the names and comments it brought in exist nowhere in the .obj."""
    from Chocoboy.scripttext import section_to_text, text_to_section
    from Chocoboy.chocoboymanager import SECTION_NAME

    widget.script_section_combo.setCurrentIndex(3)  # section 36
    section = widget.manager.script_sections[36]
    before = section.snapshot()

    text = section_to_text(section, SECTION_NAME[36]).replace(
        "=== Script #0 ===", "=== Script #0 (named by hand) ===")
    result = text_to_section(text)
    assert result.ok, result.errors
    section.replace_scripts(result.scripts, result.names, result.trailing_comments)
    widget._mark_dirty()
    assert section.script_names[0] == "named by hand"

    widget.undo()
    assert widget.manager.script_sections[36].snapshot() == before
    widget.redo()
    assert widget.manager.script_sections[36].script_names[0] == "named by hand"


def test_a_section_goes_out_to_text_and_comes_back(widget, tmp_path):
    from Chocoboy.scripttext import section_to_text, text_to_section
    from Chocoboy.chocoboymanager import SECTION_NAME

    widget.script_section_combo.setCurrentIndex(3)  # section 36
    section = widget.manager.script_sections[36]
    path = tmp_path / "section36.txt"
    path.write_text(section_to_text(section, SECTION_NAME[36]), encoding="utf8")

    # Name a script and give it a comment, the way a modder annotates one
    text = path.read_text(encoding="utf8").replace(
        "=== Script #0 ===", "=== Script #0 (Closes the dialog on flag 61) ===\n; worked out by hand")
    result = text_to_section(text)
    assert result.ok, result.errors
    section.replace_scripts(result.scripts, result.names, result.trailing_comments)

    widget._reload_script_section()
    assert widget.script_list.count() == 92
    assert section.script_names[0] == "Closes the dialog on flag 61"
    assert section.instructions[0].comments == ["; worked out by hand"]


def test_the_columns_fit_what_is_in_them_and_stay_draggable(widget):
    """Left to themselves the opcode column asks for the width of its whole drop-down list and
    the value column for the longest dialog in the game, and between them they push the
    description out of the table."""
    from PyQt6.QtWidgets import QHeaderView

    widget.script_section_combo.setCurrentIndex(3)  # section 36
    widget.script_list.setCurrentRow(1)
    header = widget.instruction_table.horizontalHeader()

    assert all(header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
               for column in range(6)), "every column must be draggable"
    assert header.stretchLastSection()
    assert widget.instruction_table.columnWidth(4) <= widget.VALUE_COLUMN_MAX_WIDTH

    # The opcode column follows what is on screen, not the longest name in the whole set
    shown = [widget.instruction_table.cellWidget(row, 1).currentText()
             for row in range(widget.instruction_table.rowCount())]
    with_a_long_name = widget.instruction_table.columnWidth(1)
    widget.script_list.setCurrentRow(19)  # a script of short opcodes
    assert widget.instruction_table.columnWidth(1) != with_a_long_name or \
           max(shown, key=len) == max((widget.instruction_table.cellWidget(row, 1).currentText()
                                       for row in range(widget.instruction_table.rowCount())),
                                      key=len)
