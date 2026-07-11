"""
Tests for the CCGroup NPC card game model (CARDGAME calls in .jsm field scripts).
Uses bghall_1.jsm/.sym (Balamb Garden hall, 4 card players) as reference data.
"""
import pathlib
import shutil

import pytest

from CCGroup.jsmcardgame import (JsmCardGameFile, CardGameFolderManager, OPCODE_PSHN_L,
                                 OPCODE_PSHM_B, VAR_CURRENT_REGION_GAME_RULES,
                                 PARAM_DECK_ID, PARAM_GAME_RULES,
                                 PARAM_TRADE_RULES, PARAM_RARE_CHANCE, PARAM_AI_SEARCH,
                                 PARAM_AI_STRATEGY, PARAM_LEVEL_MASK)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture
def bghall_folder(tmp_path):
    """Copy the reference bghall_1 files into a folder with a subfolder to test recursion."""
    sub_folder = tmp_path / "field" / "bg"
    sub_folder.mkdir(parents=True)
    shutil.copy(PROJECT_ROOT / "bghall_1.jsm", sub_folder / "bghall_1.jsm")
    shutil.copy(PROJECT_ROOT / "bghall_1.sym", sub_folder / "bghall_1.sym")
    return tmp_path


@pytest.fixture
def bghall_jsm(bghall_folder):
    jsm_path = bghall_folder / "field" / "bg" / "bghall_1.jsm"
    return JsmCardGameFile(str(jsm_path), str(jsm_path.with_suffix(".sym")))


class TestParsing:

    def test_players_found_with_names(self, bghall_jsm):
        names = [(player.entity_name, player.script_name) for player in bghall_jsm.players]
        assert names == [("seito6", "talk"), ("seito7", "talk"),
                         ("seito8", "talk"), ("seito10", "talk")]

    def test_seito6_params(self, bghall_jsm):
        params = bghall_jsm.players[0].params
        assert params[PARAM_DECK_ID].is_literal() and params[PARAM_DECK_ID].value == 31
        # Game and trade rules come from the regional savemap state (vars 292/293)
        assert params[PARAM_GAME_RULES].is_variable() and params[PARAM_GAME_RULES].value == 292
        assert params[PARAM_TRADE_RULES].is_variable() and params[PARAM_TRADE_RULES].value == 293
        assert params[PARAM_RARE_CHANCE].value == 80
        assert params[PARAM_AI_SEARCH].value == 0
        assert params[PARAM_AI_STRATEGY].value == 0
        assert params[PARAM_LEVEL_MASK].value == 3

    def test_level_mask_from_variable(self, bghall_jsm):
        # seito8 and seito10 push their level mask from savemap var 1041
        for player in (bghall_jsm.players[2], bghall_jsm.players[3]):
            assert player.params[PARAM_LEVEL_MASK].is_variable()
            assert player.params[PARAM_LEVEL_MASK].value == 1041

    def test_missing_sym_gives_fallback_names(self, bghall_folder):
        jsm_path = bghall_folder / "field" / "bg" / "bghall_1.jsm"
        jsm_file = JsmCardGameFile(str(jsm_path), str(jsm_path) + ".does_not_exist")
        assert len(jsm_file.players) == 4
        assert all(player.entity_name == "entity?" for player in jsm_file.players)


class TestFolderManager:

    def test_recursive_scan(self, bghall_folder):
        manager = CardGameFolderManager()
        manager.load_folder(str(bghall_folder))
        assert len(manager.jsm_files) == 1
        assert manager.nb_players() == 4

    def test_save_all_only_writes_modified(self, bghall_folder):
        manager = CardGameFolderManager()
        manager.load_folder(str(bghall_folder))
        assert manager.save_all() == 0
        manager.jsm_files[0].players[0].params[PARAM_RARE_CHANCE].set_literal(100)
        assert manager.save_all() == 1
        assert manager.save_all() == 0  # originals refreshed after save


class TestPatching:

    def test_roundtrip_edit_literal(self, bghall_jsm):
        player = bghall_jsm.players[0]
        player.params[PARAM_RARE_CHANCE].set_literal(42)
        player.params[PARAM_LEVEL_MASK].set_literal(0x7F)
        assert bghall_jsm.is_modified()
        bghall_jsm.save()

        reloaded = JsmCardGameFile(bghall_jsm.jsm_path, bghall_jsm.sym_path)
        params = reloaded.players[0].params
        assert params[PARAM_RARE_CHANCE].value == 42
        assert params[PARAM_LEVEL_MASK].value == 0x7F
        # Untouched players/params unaffected
        assert reloaded.players[1].params[PARAM_RARE_CHANCE].value == 20
        assert reloaded.players[0].params[PARAM_DECK_ID].value == 31

    def test_override_variable_and_restore(self, bghall_jsm):
        rules = bghall_jsm.players[0].params[PARAM_GAME_RULES]
        rules.set_literal(0x81)  # force Open + Elemental
        assert rules.opcode == OPCODE_PSHN_L
        bghall_jsm.save()

        reloaded = JsmCardGameFile(bghall_jsm.jsm_path, bghall_jsm.sym_path)
        rules = reloaded.players[0].params[PARAM_GAME_RULES]
        assert rules.is_literal() and rules.value == 0x81

        # Restore the variable push (back to the current region rules)
        rules.set_variable(VAR_CURRENT_REGION_GAME_RULES)
        reloaded.save()
        reloaded2 = JsmCardGameFile(bghall_jsm.jsm_path, bghall_jsm.sym_path)
        rules = reloaded2.players[0].params[PARAM_GAME_RULES]
        assert rules.opcode == OPCODE_PSHM_B
        assert rules.is_variable() and rules.value == VAR_CURRENT_REGION_GAME_RULES

    def test_literal_param_switched_to_region_variable(self, bghall_jsm):
        # seito6's level mask is a literal; make it follow a savemap variable instead
        level_mask = bghall_jsm.players[0].params[PARAM_LEVEL_MASK]
        assert level_mask.is_literal()
        level_mask.set_variable(1041)
        bghall_jsm.save()
        reloaded = JsmCardGameFile(bghall_jsm.jsm_path, bghall_jsm.sym_path)
        level_mask = reloaded.players[0].params[PARAM_LEVEL_MASK]
        assert level_mask.is_variable() and level_mask.value == 1041

    def test_save_does_not_change_size_or_other_bytes(self, bghall_jsm):
        original = bytes(bghall_jsm.data)
        param = bghall_jsm.players[1].params[PARAM_DECK_ID]
        param.set_literal(0xF0)
        bghall_jsm.save()
        patched = pathlib.Path(bghall_jsm.jsm_path).read_bytes()
        assert len(patched) == len(original)
        diff = [i for i in range(len(original)) if patched[i] != original[i]]
        # Only the 3 param bytes of that single push instruction may differ
        assert all(param.file_offset <= i < param.file_offset + 3 for i in diff)
