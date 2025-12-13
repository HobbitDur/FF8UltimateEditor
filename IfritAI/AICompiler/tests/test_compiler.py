# test_code_byte_generator.py
"""
Tests for AI Code Generator.
Tests that AST nodes are correctly converted to FF8 bytecode.
"""
import pytest

from FF8GameData.dat.daterrors import ParamBattleTextError, ParamAptitudeError, ParamMagicIdError, ParamTargetBasicError, ParamIntError
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


    def test_print(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        print(1);
        """
        ## Type data
        source_code_type = \
        """
        print("Second battle text");
        """
        ## Error data
        source_code_error = \
        """
        print("Text not existing");
        """
        # The expected output
        expected = [0x01, 0x01]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)


    def test_prepareMagic(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        prepareMagic(1);
        """
        ## Type data
        source_code_type = \
        """
        prepareMagic(Fire);
        """
        ## Error data
        source_code_error = \
        """
        prepareMagic(Tutu);
        """
        # The expected output
        expected = [3, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamMagicIdError):
            compiler.compile(source_code_error)

    def test_target(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        target(1);
        """
        ## Type data
        source_code_type = \
        """
        target(Zell);
        """
        ## Error data
        source_code_error = \
        """
        target(Tutu);
        """
        # The expected output
        expected = [4, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamTargetBasicError):
            compiler.compile(source_code_error)


    def test_prepareAnim(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        prepareAnim(1);
        """
        ## Type data
        source_code_type = \
        """
        prepareAnim(1);
        """
        ## Error data
        source_code_error = \
        """
        prepareAnim(-10);
        """
        # The expected output
        expected = [5, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)

    def test_statChange(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        statChange(5,6);
        """
        ## Type data
        source_code_type = \
        """
        statChange(Evade,60%);
        """
        ## Error data
        source_code_error = \
        """
        statChange(Evadeu,60%);
        """
        # The expected output
        expected = [40, 5, 6]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamAptitudeError):
            compiler.compile(source_code_error)

    def test_if(self, compiler: AICompiler):
        source_code_raw = \
        """
        if(0,200, 3, 5)
        {
            stop;
        }
        """
        source_code_type = \
        """
        if(HP_OF_SPECIFIC_TARGET,Self, !=, 50%)
        {
            stop;
        }
        """

        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)
        expected = [2, 0, 200, 3, 5, 0, 4, 0, 0, 35, 0, 0]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"

    def test_if_else(self, compiler: AICompiler):
        source_code_raw = \
        """
        if (1,200,3,4) { die(); } else { statChange(5,6); } 
        """
        source_code_type = \
        """
        if(HP_OF_GENERIC_TARGET,ENEMY_TEAM, !=, 40%)
        {
            die;
        }
        else
        {
           statChange(Evade,60%); 
        }
        """

        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)
        expected = [2, 1, 200, 3, 4, 0, 4, 0, 8, 35, 3, 0, 40, 5, 6]
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"



if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x", "--tb=short"]) # Capture all print
    #pytest.main([__file__, "-v", "-x", "--tb=short", "-s"])