# test_code_byte_generator.py
"""
Tests for AI Code Generator.
Tests that AST nodes are correctly converted to FF8 bytecode.
"""
import pytest

from FF8GameData.dat.daterrors import ParamBattleTextError, ParamAptitudeError, ParamMagicIdError, ParamTargetBasicError, ParamIntError, \
    ParamMonsterAbilityError, ParamMonsterLineAbilityError, ParamLocalVarError, ParamBattleVarError, ParamGlobalVarError
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
        info_stat_data = {}  # TODO
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

    def test_usePrepared(self, compiler: AICompiler):
        source_code_raw = \
            """
            usePrepared;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [6]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_prepareMonsterAbility(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            prepareMonsterAbility(3);
            """
        ## Type data
        source_code_type = \
            """
            prepareMonsterAbility("Attack (Cronos)");
            """
        ## Error data
        source_code_error = \
            """
            prepareMonsterAbility(Tutu);
            """
        # The expected output
        expected = [7, 3]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamMonsterAbilityError):
            compiler.compile(source_code_error)


    def test_die(self, compiler: AICompiler):
        source_code_raw = \
            """
            die;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [8]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"



    def test_anim(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            anim(1);
            """
        ## Type data
        source_code_type = \
            """
            anim(1);
            """
        ## Error data
        source_code_error = \
            """
            anim(-10);
            """
        # The expected output
        expected = [9, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)


    def test_useRandom(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            useRandom(1,2,3);
            """
        ## Type data
        source_code_type = \
            """
            useRandom(1,2,3);
            """
        ## Error data
        source_code_error = \
            """
            useRandom(tutu, tata, toto);
            """
        # The expected output
        expected = [11, 1, 2, 3]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)

    def test_use(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            use(1);
            """
        ## Type data
        source_code_type = \
            """
            use(1);
            """
        ## Error data
        source_code_error = \
            """
            use(tutu);
            """
        # The expected output
        expected = [12, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)

    def test_unknown13(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            unknown13(1);
            """
        ## Type data
        source_code_type = \
            """
            unknown13(1);
            """
        ## Error data
        source_code_error = \
            """
            unknown13(tutu);
            """
        # The expected output
        expected = [13, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)

    def test_var(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            var(221, 10);
            """
        ## Type data
        source_code_type = \
            """
             var(varB, 10);
            """
        ## Error data
        source_code_error = \
            """
            var(GlobalVar80, 10);
            """
        # The expected output
        expected = [14, 221, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamLocalVarError):
            compiler.compile(source_code_error)

    def test_var_specialCases(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            var(221, 203);
            """
        ## Type data
        source_code_type = \
            """
             var(varB, "LAST ATTACKER SLOT ID");
            """
        # The expected output
        expected = [14, 221, 203]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"


    def test_bvar(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            bvar(96, 10);
            """
        ## Type data
        source_code_type = \
            """
             bvar(BattleVar96, 10);
            """
        ## Error data
        source_code_error = \
            """
            bvar(GlobalVar80, 10);
            """
        # The expected output
        expected = [15, 96, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleVarError):
            compiler.compile(source_code_error)



    def test_gvar(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            gvar(80, 10);
            """
        ## Type data
        source_code_type = \
            """
             gvar(GlobalVar80, 10);
            """
        ## Error data
        source_code_error = \
            """
            gvar(BattleVar96, 10);
            """
        # The expected output
        expected = [17, 80, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamGlobalVarError):
            compiler.compile(source_code_error)



    def test_add(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            add(221, 10);
            """
        ## Type data
        source_code_type = \
            """
             add(varB, 10);
            """
        ## Error data
        source_code_error = \
            """
            add(GlobalVar80, 10);
            """
        # The expected output
        expected = [18, 221, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamLocalVarError):
            compiler.compile(source_code_error)



    def test_add_specialCases(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            add(221, 203);
            """
        ## Type data
        source_code_type = \
            """
             add(varB, "LAST ATTACKER SLOT ID");
            """
        # The expected output
        expected = [18, 221, 203]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"


    def test_badd(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            badd(96, 10);
            """
        ## Type data
        source_code_type = \
            """
             badd(BattleVar96, 10);
            """
        ## Error data
        source_code_error = \
            """
            badd(GlobalVar80, 10);
            """
        # The expected output
        expected = [19, 96, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleVarError):
            compiler.compile(source_code_error)



    def test_gadd(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            gadd(80, 10);
            """
        ## Type data
        source_code_type = \
            """
             gadd(GlobalVar80, 10);
            """
        ## Error data
        source_code_error = \
            """
            gadd(BattleVar96, 10);
            """
        # The expected output
        expected = [21, 80, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamGlobalVarError):
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
    pytest.main([__file__, "-v", "-x", "--tb=short"])  # Capture all print
    # pytest.main([__file__, "-v", "-x", "--tb=short", "-s"])
