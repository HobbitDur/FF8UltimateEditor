# test_code_byte_generator.py
"""
Tests for AI Code Generator.
Tests that AST nodes are correctly converted to FF8 bytecode.
"""
import pytest

from FF8GameData.dat.daterrors import ParamBattleTextError
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import *
from IfritAI.AICompiler.AICompiler import AICompiler


class TestAICompiler:
    """Test suite for AI Code Generator"""
    @pytest.fixture
    def compiler(self):
        """Create a Lark parser using the grammar from AICompiler"""
        from IfritAI.AICompiler.AICompiler import AICompiler
        import os

        # Use the actual grammar from AICompiler
        battle_text = ["First battle text", "Second battle text", "Third battle text"]
        info_stat_data = {} # TODO
        game_data = GameData(os.path.join("..", "..", "..", "FF8GameData"))
        game_data.load_all()
        compiler = AICompiler(game_data, battle_text, info_stat_data)
        return compiler

    def test_stop(self, compiler: AICompiler):
        source_code_raw = \
        """
        stop;
        """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [0x00]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_if(self, compiler: AICompiler):
        source_code_raw = \
        """
        if(0,200, 3, 5)
        {
            stop;
        }
        """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [2, 0, 200, 3, 5, 0, 4, 0, 0, 35, 0, 0]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"



    def test_print(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        print("First battle text");
        """
        ## Type data
        source_code_type = \
        """
        print("First battle text");
        """
        ## Error data
        source_code_error = \
        """
        print("Text not existing");
        """
        # The expected output
        expected = [0x01, 0x00]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)


if __name__ == "__main__":
    #pytest.main([__file__, "-v", "-x", "--tb=short"]) Capture all print
    pytest.main([__file__, "-v", "-x", "--tb=short", "-s"])