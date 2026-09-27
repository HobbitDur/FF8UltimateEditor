"""AI targets for c0m144-c0m199 (FFNx AllMonsterFilesUsable): Cronos only, and never on a special target.

The game decodes a target byte's special values before looking for a monster with that id, and
each opcode family has its own specials (MonsterAI @0x487DF0 / GetNbMemberTargetGeneric @0x487590):
opcode 04 target = 200-209 and 220-227 (228-248 = TargetTwoSlot pairs), if-subject specific target =
200, 203, 220-227, generic target = 200, 201. c0m + 16 = 160-215 only meets them on 200-209.
"""
import pathlib

import pytest

from FF8GameData.dat.daterrors import ParamTargetBasicError
from FF8GameData.gamedata import GameData
from Ifrit.IfritAI.AICompiler.AICompiler import AICompiler
from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


@pytest.fixture
def cronos(game_data):
    game_data.load_ai_data("ai_cronos.json")
    yield game_data
    game_data.load_ai_data("ai_vanilla.json")


def _ids(game_data, key):
    return {m["id"] for m in game_data.get_ai_monster_targets(key)}


def test_vanilla_keeps_the_144_game_monsters(game_data):
    game_data.load_ai_data("ai_vanilla.json")
    for key in ("target_basic", "target_advanced_specific", "target_advanced_generic"):
        assert _ids(game_data, key) == set(range(16, 160))


def test_cronos_adds_c0m144_to_c0m199_except_special_targets(cronos):
    extra = set(range(160, 216))
    assert _ids(cronos, "target_basic") == set(range(16, 160)) | (extra - set(range(200, 210)))
    assert _ids(cronos, "target_advanced_specific") == set(range(16, 160)) | (extra - {200, 203})
    assert _ids(cronos, "target_advanced_generic") == set(range(16, 160)) | (extra - {200, 201})
    # no collision with the TargetTwoSlot pair values
    assert not _ids(cronos, "target_basic") & set(range(228, 249))


def test_cronos_compiles_and_decompiles_a_new_monster_target(cronos):
    compiler = AICompiler(cronos, [], {})
    compiler.reset_ai_data()
    assert compiler.compile("target(c0m150);") == [4, 166, 0, 0]
    assert compiler.compile("target(c0m199);") == [4, 215, 0, 0]
    # c0m185 = 201 = "random enemy" for opcode 04: the game never reads it as that monster
    with pytest.raises(ParamTargetBasicError):
        compiler.compile("target(c0m185);")

    decompiler = AIDecompiler(cronos, [], {})
    decompiler.reset_ai_data()
    code = decompiler.decompile([4, 166])
    assert "C0M150" in code.upper()
    assert compiler.compile(code) == [4, 166, 0, 0]


def test_vanilla_refuses_a_new_monster_target(game_data):
    game_data.load_ai_data("ai_vanilla.json")
    compiler = AICompiler(game_data, [], {})
    compiler.reset_ai_data()
    with pytest.raises(ParamTargetBasicError):
        compiler.compile("target(c0m150);")
