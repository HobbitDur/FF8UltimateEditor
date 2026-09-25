"""Bulk edits of NPC card players (cardgamebulk.py) and the table view, on the real bghall_1 and
bgmon_4 field scripts (copied to tmp_path, so saves never touch extracted_files)."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from CCGroup import cardgamebulk as bulk
from CCGroup.jsmcardgame import (CardGameFolderManager, JsmCardGameFile, OPCODE_PSHN_L, OPCODE_PSHM_B,
                                 VAR_CURRENT_REGION_GAME_RULES, PARAM_GAME_RULES, PARAM_RARE_CHANCE,
                                 PARAM_AI_SEARCH, PARAM_LEVEL_MASK)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg"

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in ("bghall_1", "bgmon_4") for extension in ("jsm", "sym")])


@pytest.fixture
def folder(tmp_path):
    for name in ("bghall_1", "bgmon_4"):
        (tmp_path / name).mkdir()
        for extension in ("jsm", "sym"):
            shutil.copy(FIELD / name / f"{name}.{extension}", tmp_path / name / f"{name}.{extension}")
    return tmp_path


@pytest.fixture
def manager(folder):
    manager = CardGameFolderManager()
    manager.load_folder(str(folder))
    return manager


def players_of(manager, map_name):
    return [player for jsm_file in manager.jsm_files if jsm_file.map_name == map_name for player in jsm_file.players]


def test_rare_chance_operations_clamp(manager):
    jokers = players_of(manager, "bgmon_4")
    assert [player.params[PARAM_RARE_CHANCE].value for player in jokers] == [10, 30, 60]
    assert bulk.apply_to_players(jokers, bulk.multiply_rare_chance, 200) == (3, 0)
    assert [player.params[PARAM_RARE_CHANCE].value for player in jokers] == [20, 60, 100]
    bulk.apply_to_players(jokers, bulk.add_rare_chance, 50)
    assert [player.params[PARAM_RARE_CHANCE].value for player in jokers] == [70, 100, 100]


def test_ai_depth_keeps_the_no_guess_bit(manager):
    joker = players_of(manager, "bgmon_4")[0]
    assert joker.params[PARAM_AI_SEARCH].value == 0x11  # depth 1, does not guess
    bulk.add_ai_depth(joker, 10)
    assert joker.params[PARAM_AI_SEARCH].value == 0x17
    bulk.set_ai_no_guess(joker, False)
    assert joker.params[PARAM_AI_SEARCH].value == 0x07


def test_level_operations_skip_script_rolled_masks(manager):
    seito6, seito7, seito8, _ = players_of(manager, "bghall_1")
    assert seito6.params[PARAM_LEVEL_MASK].value == 3  # Lv1-2
    assert bulk.shift_levels(seito6, 2)
    assert seito6.params[PARAM_LEVEL_MASK].value == 0b1100  # Lv3-4
    assert bulk.shift_levels(seito6, 10) and seito6.params[PARAM_LEVEL_MASK].value == 0b1000000  # both at Lv7
    assert not bulk.remove_levels(seito6, 0x7F)  # would empty the mask: unchanged
    # seito8's mask is rolled by the script (var 1041): kept unless the override is on
    assert not bulk.shift_levels(seito8, 1)
    assert not bulk.set_levels(seito8, 0x0F)
    assert bulk.set_levels(seito8, 0x0F, override_game_state=True)
    assert seito8.params[PARAM_LEVEL_MASK].opcode == OPCODE_PSHN_L


def test_game_rules_fixed_and_back_to_region(manager):
    seito6 = players_of(manager, "bghall_1")[0]
    rules = seito6.params[PARAM_GAME_RULES]
    assert not bulk.add_game_rules(seito6, 0x01)  # region rules: nothing to add to
    assert bulk.set_game_rules(seito6, 0x03, override_game_state=True)
    assert rules.is_literal() and rules.value == 0x03
    assert bulk.add_game_rules(seito6, 0x80) and rules.value == 0x83
    assert bulk.use_region_rules(seito6)
    assert rules.opcode == OPCODE_PSHM_B and rules.value == VAR_CURRENT_REGION_GAME_RULES
    assert not seito6.is_modified()


def test_bulk_edits_are_saved_and_restore_undoes_them(manager, folder):
    jokers = players_of(manager, "bgmon_4")
    bulk.apply_to_players(jokers, bulk.set_ai_depth, 7)
    assert manager.save_all() == 1
    reloaded = JsmCardGameFile(str(folder / "bgmon_4" / "bgmon_4.jsm"), str(folder / "bgmon_4" / "bgmon_4.sym"))
    assert all(player.params[PARAM_AI_SEARCH].value & 7 == 7 for player in reloaded.players)
    seito = players_of(manager, "bghall_1")[0]
    bulk.set_rare_chance(seito, 0)
    assert bulk.restore_original(seito) and not seito.is_modified()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_table_applies_to_selection_or_visible_rows(qapp, manager):
    from CCGroup.npccardtablewidget import NpcCardTableWidget
    table = NpcCardTableWidget(["card"] * 110)
    table.set_manager(manager)
    assert table.table.rowCount() == 7
    table.filter_edit.setText("joker")
    assert len(table.target_players()) == 3  # nothing selected: every visible row
    table.table.selectRow([row for row in range(table.table.rowCount())
                           if not table.table.isRowHidden(row)][0])
    assert len(table.target_players()) == 1
    table.parameter_combobox.setCurrentText("Rare card chance")
    table.operation_combobox.setCurrentIndex(0)  # Set to
    table.value_editor.spinbox.setValue(99)
    table.apply_bulk()
    assert sorted(player.params[PARAM_RARE_CHANCE].value for player in players_of(manager, "bgmon_4")) == [30, 60, 99]
    table.modified_only_checkbox.setChecked(True)
    table.filter_edit.clear()
    assert table.count_label.text().startswith("1 /")
    table.deleteLater()
