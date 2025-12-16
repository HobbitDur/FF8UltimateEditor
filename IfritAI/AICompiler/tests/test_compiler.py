# test_code_byte_generator.py
"""
Tests for AI Code Generator.
Tests that AST nodes are correctly converted to FF8 bytecode.
"""
import pytest

from FF8GameData.dat.daterrors import ParamBattleTextError, ParamAptitudeError, ParamMagicIdError, ParamTargetBasicError, ParamIntError, \
    ParamMonsterAbilityError, ParamMonsterLineAbilityError, ParamLocalVarError, ParamBattleVarError, ParamGlobalVarError, ParamTargetSlotError, ParamBoolError, \
    ParamSpecialActionError, ParamInt16Error, ParamTargetGenericError, ParamActivateError, ParamSceneOutSlotIdError, ParamMagicTypeError, ParamGfError, ParamSlotIdEnableError, \
    ParamCardError, ParamAssignSlotIdError, ParamItemError, ParamSlotIdError
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


    def test_recover(self, compiler: AICompiler):
        source_code_raw = \
            """
            recover;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [0x16]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_setEscape(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            setEscape(1);
            setEscape(0);
            """
        ## Type data
        source_code_type = \
            """
            setEscape(true);
            setEscape(false);
            """
        ## Error data
        source_code_error = \
            """
            setEscape(lux_is_op);
            """
        # The expected output
        expected = [23, 1, 23, 0]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBoolError):
            compiler.compile(source_code_error)


    def test_printSpeed(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        printSpeed(1);
        """
        ## Type data
        source_code_type = \
        """
        printSpeed("Second battle text");
        """
        ## Error data
        source_code_error = \
        """
        printSpeed("Text not existing");
        """
        # The expected output
        expected = [24, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)


    def test_doNothing(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        doNothing(1);
        """

        # The expected output
        expected = [25, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_printAndLock(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        printAndLock(1);
        """
        ## Type data
        source_code_type = \
        """
        printAndLock("Second battle text");
        """
        ## Error data
        source_code_error = \
        """
        printAndLock("Text not existing");
        """
        # The expected output
        expected = [26, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)


    def test_enterAlt(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        enterAlt(1, 0);
        """
        
        # The expected output
        expected = [27, 1, 0]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_waitText(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        waitText(2);
        """
        
        # The expected output
        expected = [28, 2]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_leave(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        leave(200);
        """
        ## Type data
        source_code_type = \
        """
        leave(SELF);
        """
        source_code_error = \
        """
        leave(8);
        """
        # The expected output
        expected = [29, 200]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamTargetSlotError):
            compiler.compile(source_code_error)


    def test_specialAction(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        specialAction(17);
        """
        ## Type data
        source_code_type = \
        """
        specialAction("Elvoret Entrance");
        """
        source_code_error = \
        """
        specialAction("nerf lux op champ");
        """
        # The expected output
        expected = [30, 17]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSpecialActionError):
            compiler.compile(source_code_error)  


    def test_enter(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        enter(3);
        """
        # The expected output
        expected = [31, 3]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_waitTextFast(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        waitTextFast(2);
        """
        # The expected output
        expected = [32, 2]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_printAlt(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        printAlt(1);
        """
        ## Type data
        source_code_type = \
        """
        printAlt("Second battle text");
        """
        ## Error data
        source_code_error = \
        """
        printAlt("Text not existing");
        """
        # The expected output
        expected = [34, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)



    def test_jump(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        jump(10);
        """
        ## Error data
        source_code_error = \
        """
        jump(10000000000);
        """
        # The expected output
        expected = [35, 10, 0]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        with pytest.raises(ParamInt16Error):
            compiler.compile(source_code_error)


    def test_jump_negative(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        jump(-10);
        """
        ## Error data
        source_code_error = \
        """
        jump(-10000000000);
        """
        # The expected output
        expected = [35, 246, 255]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        with pytest.raises(ParamInt16Error):
            compiler.compile(source_code_error)


    def test_fillAtb(self, compiler: AICompiler):
        source_code_raw = \
            """
            fillAtb;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [36]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"



    def test_setScanText(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        setScanText(1);
        """
        ## Type data
        source_code_type = \
        """
        setScanText("Second battle text");
        """
        ## Error data
        source_code_error = \
        """
        setScanText("Text not existing");
        """
        # The expected output
        expected = [37, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamBattleTextError):
            compiler.compile(source_code_error)



    def test_targetStatus(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        targetStatus(200, 3, 1, 0);
        """
        ## Type data
        source_code_type = \
        """
        targetStatus("ENEMY TEAM", !=, Poison, False);
        """
        ## Error data
        source_code_error = \
        """
        targetStatus(250, 3, 1, 0);
        """
        # The expected output
        expected = [38, 0, 200, 3, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamTargetGenericError):
            compiler.compile(source_code_error)



    def test_autoStatus(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
        """
        autoStatus(1, 2);
        """
        ## Type data
        source_code_type = \
        """
        autoStatus(ACTIVATE, Petrify);
        """
        ## Error data
        source_code_error = \
        """
        autoStatus(2, 2);
        """
        # The expected output
        expected = [39, 2, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamActivateError):
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

    def test_draw(self, compiler: AICompiler):
        source_code_raw = \
            """
            draw;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [41]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_cast(self, compiler: AICompiler):
        source_code_raw = \
            """
            cast;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [42]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_targetAllySlot(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            targetAllySlot(1);
            """
        ## Type data
        source_code_type = \
            """
            targetAllySlot(1);
            """
        ## Error data
        source_code_error = \
            """
            targetAllySlot(8);
            """
        # The expected output
        expected = [43, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSceneOutSlotIdError):
            compiler.compile(source_code_error)

    def test_remain(self, compiler: AICompiler):
        source_code_raw = \
            """
            remain;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [44]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_elemDmgMod(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            elemDmgMod(2, 80);
            """
        ## Type data
        source_code_type = \
            """
            elemDmgMod(Thunder, 80);
            """
        ## Error data
        source_code_error = \
            """
            elemDmgMod(Turlututu, 80);
            """
        # The expected output
        expected = [45, 2, 100, 0]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamMagicTypeError):
            compiler.compile(source_code_error)

    def test_blowAway(self, compiler: AICompiler):
        source_code_raw = \
            """
            blowAway;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [46]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_targetable(self, compiler: AICompiler):
        source_code_raw = \
            """
            targetable;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [47]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_untargetable(self, compiler: AICompiler):
        source_code_raw = \
            """
            untargetable;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [48]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_giveGF(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            giveGF(1);
            """
        ## Type data
        source_code_type = \
            """
            giveGF(Shiva);
            """
        ## Error data
        source_code_error = \
            """
            giveGF(50);
            """
        # The expected output
        expected = [49, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamGfError):
            compiler.compile(source_code_error)

    def test_prepareSummon(self, compiler: AICompiler):
        source_code_raw = \
            """
            prepareSummon;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [50]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_activate(self, compiler: AICompiler):
        source_code_raw = \
            """
            activate;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [51]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_enable(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            enable(1);
            """
        ## Type data
        source_code_type = \
            """
            enable(1);
            """
        ## Error data
        source_code_error = \
            """
            enable(8);
            """
        # The expected output
        expected = [52, 1]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSceneOutSlotIdError):
            compiler.compile(source_code_error)


    def test_loadAndTargetable(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            loadAndTargetable(209);
            """
        ## Type data
        source_code_type = \
            """
            loadAndTargetable("LAST ENABLED MONSTER");
            """
        ## Error data
        source_code_error = \
            """
            loadAndTargetable(8);
            """
        # The expected output
        expected = [53, 209]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSlotIdEnableError):
            compiler.compile(source_code_error)

    def test_gilgamesh(self, compiler: AICompiler):
        source_code_raw = \
            """
            gilgamesh;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [54]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_giveCard(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            giveCard(2);
            """
        ## Type data
        source_code_type = \
            """
            giveCard("Bite Bug");
            """
        ## Error data
        source_code_error = \
            """
            giveCard(120);
            """
        # The expected output
        expected = [55, 2]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamCardError):
            compiler.compile(source_code_error)


    def test_giveItem(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            giveItem(2);
            """
        ## Type data
        source_code_type = \
            """
            giveItem("Potion+");
            """
        ## Error data
        source_code_error = \
            """
            giveItem(220);
            """
        # The expected output
        expected = [56, 2]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamItemError):
            compiler.compile(source_code_error)


    def test_gameOver(self, compiler: AICompiler):
        source_code_raw = \
            """
            gameOver;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [57]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"

    def test_targetableSlot(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            targetableSlot(2);
            """
        ## Type data
        source_code_type = \
            """
            targetableSlot(2);
            """
        ## Error data
        source_code_error = \
            """
            targetableSlot(8);
            """
        # The expected output
        expected = [58, 2]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSlotIdError):
            compiler.compile(source_code_error)

    def test_assignSlot(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            assignSlot(2, 0);
            """
        ## Type data
        source_code_type = \
            """
            assignSlot(2, "FIRST SLOT AVAILABLE");
            """
        ## Error data
        source_code_error = \
            """
            assignSlot(8, "FIRST SLOT AVAILABLE");
            """
        # The expected output
        expected = [59, 2, 0]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamSceneOutSlotIdError):
            compiler.compile(source_code_error)


    def test_addMaxHP(self, compiler: AICompiler):
        # First declare different source code case
        ## Raw data (already int)
        source_code_raw = \
            """
            addMaxHP(10);
            """
        ## Type data
        source_code_type = \
            """
            addMaxHP(10);
            """
        ## Error data
        source_code_error = \
            """
            addMaxHP(-10);
            """
        # The expected output
        expected = [60, 10]

        # The work
        code_raw_compiled = compiler.compile(source_code_raw)
        code_type_compiled = compiler.compile(source_code_type)

        # Assert the expected result
        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"
        assert code_type_compiled == expected, f"Expected {expected}, got {code_type_compiled}"
        with pytest.raises(ParamIntError):
            compiler.compile(source_code_error)


    def test_proofOfOmega(self, compiler: AICompiler):
        source_code_raw = \
            """
            proofOfOmega;
            """

        code_raw_compiled = compiler.compile(source_code_raw)
        expected = [61]

        assert code_raw_compiled == expected, f"Expected {expected}, got {code_raw_compiled}"


    def test_if_hp_specific_target(self, compiler: AICompiler):
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
