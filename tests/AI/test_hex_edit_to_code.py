"""A command edited in the Hex-editor (raw bytes, CommandAnalyser.set_op_code) shows and compiles
with its new value once back in the IfritAI-code view - it used to come back as the old target."""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Ifrit.IfritAI.AICompiler.AICompiler import AICompiler
from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    yield game_data
    game_data.load_ai_data("ai_vanilla.json")


def _hex_edit_then_compile(game_data, ai_file, bytecode, byte_index, new_value):
    game_data.load_ai_data(ai_file)
    compiler = AICompiler(game_data, [], {})
    compiler.reset_ai_data()
    decompiler = AIDecompiler(game_data, [], {})
    decompiler.reset_ai_data()
    commands = decompiler.decompile_bytecode_to_command_list(bytecode)
    op_code = list(commands[0].get_op_code())
    op_code[byte_index] = new_value
    commands[0].set_op_code(op_code)  # what a Hex-editor spin box does
    return compiler.compile(decompiler.decompile_from_command_list(commands))


@pytest.mark.parametrize("ai_file, new_value", [("ai_vanilla.json", 3),     # Quistis
                                                ("ai_cronos.json", 3),
                                                ("ai_cronos.json", 161)])  # c0m145
def test_if_alive_right_target(game_data, ai_file, new_value):
    compiled = _hex_edit_then_compile(game_data, ai_file, [2, 9, 0, 0, 0, 0, 4, 0, 0, 35, 0, 0], 3, new_value)
    assert compiled[:6] == [2, 9, 0, 0, new_value, 0]


def test_target_opcode(game_data):
    compiled = _hex_edit_then_compile(game_data, "ai_vanilla.json", [4, 0], 0, 3)
    assert compiled[:2] == [4, 3]
