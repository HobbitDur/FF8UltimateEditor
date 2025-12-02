# conftest.py
import pytest
from lark import Lark

from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AICompiler import AICompiler


@pytest.fixture
def ai_compiler():
    """Create an AICompiler instance for testing"""
    # Create a mock game_data object
    game_data = GameData("..\\..\\..\\FF8GameData")
    game_data.load_all()
    return AICompiler(game_data)


@pytest.fixture
def parser(ai_compiler):
    """Create a Lark parser instance using the grammar from AICompiler"""
    return Lark(ai_compiler.grammar, start='start', parser='lalr')