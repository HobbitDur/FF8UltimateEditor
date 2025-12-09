# test_type_resolution.py
"""
Tests for AST type resolution.
Focuses on verifying the type resolver converts string values to appropriate types.
"""
import pytest

from FF8GameData.dat.daterrors import ParamMagicIdError, ParamCountError
from IfritAI.AICompiler.AIAST import *
from IfritAI.AICompiler.AITypeResolver import AITypeResolver


class TestAITypeResolution:
    """Test suite for AI Type Resolution"""

    @pytest.fixture
    def type_resolver(self, ai_compiler):
        """Get the type resolver from compiler"""
        return ai_compiler.type_resolver

    def test_resolve_prepare_magic_fire(self, type_resolver):
        """Test that prepareMagic(Fire) is converted to prepareMagic(1)"""
        # Create AST for: prepareMagic(Fire);
        fire_value = Value("Fire")
        param_list = ParamList(params=[fire_value])
        command = Command(name="prepareMagic", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Check it's still a Command
        assert isinstance(resolved, Command)
        assert resolved.name == "prepareMagic"

        # Check params were resolved
        assert resolved.params is not None
        assert len(resolved.params.params) == 1

        # Fire should be converted to a number (assuming Fire has ID 1 in game data)
        resolved_value = resolved.params.params[0]
        assert isinstance(resolved_value, Value)
        assert resolved_value.value == "1"

    def test_resolve_numeric_literal_stays_number(self, type_resolver):
        """Test that numeric literals remain as numbers"""
        # Create AST for: prepareMagic(100);
        number_value = Value("50")
        param_list = ParamList(params=[number_value])
        command = Command(name="prepareMagic", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Numeric literals should remain unchanged
        resolved_value = resolved.params.params[0]
        assert isinstance(resolved_value, Value)
        assert resolved_value.value == "50"  # Should stay as number

    # def test_resolve_hex_number_stays_hex(self, type_resolver):
    #     """Test that hex numbers remain as hex strings"""
    #     # Create AST for: prepareMagic(0xFF);
    #     hex_value = Value("0xFF")
    #     param_list = ParamList(params=[hex_value])
    #     command = Command(name="prepareMagic", params=param_list)
    #
    #     # Resolve the command
    #     resolved = type_resolver.resolve(command)
    #
    #     # Hex numbers should remain unchanged
    #     resolved_value = resolved.params.params[0]
    #     assert isinstance(resolved_value, Value)
    #     assert resolved_value.value == "0xFF"  # Should stay as hex

    def test_resolve_command_without_params(self, type_resolver):
        """Test resolution of command without parameters"""
        # Create AST for: die();
        command = Command(name="die", params=None)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should still be a command without params
        assert isinstance(resolved, Command)
        assert resolved.name == "die"
        assert resolved.params is None

    def test_resolve_block_of_statements(self, type_resolver):
        """Test resolution of a block containing multiple statements"""
        # Create AST block with multiple commands
        commands = [
            Command(name="prepareMagic", params=ParamList(params=[Value("Fire")])),
            Command(name="die", params=None),
            Command(name="bvar", params=ParamList(params=[Value("BattleVar96"), Value("5")]))
        ]
        block = Block(statements=commands)

        # Resolve the block
        resolved = type_resolver.resolve(block)

        # Should still be a Block
        assert isinstance(resolved, Block)
        assert len(resolved.statements) == 3

        # Check each command was resolved
        # First: prepareMagic(Fire) -> prepareMagic(1)
        assert resolved.statements[0].params.params[0].value == "1"

        # Second: attack() -> unchanged
        assert resolved.statements[1].name == "die"
        assert resolved.statements[1].params is None

        # Third: bvar(battle, 5) -> set_status(96, 5)
        assert resolved.statements[2].name == "bvar"
        assert resolved.statements[2].params.params[0].value == "96"
        assert resolved.statements[2].params.params[1].value == "5"

    def test_resolve_value_directly(self, type_resolver):
        """Test direct resolution of a Value node"""
        # Test resolving a known value
        fire_value = Value("Fire")
        resolved = type_resolver._resolve_value(fire_value, "magic")

        assert resolved == 1  # Fire -> 1

        # Test resolving a number
        number_value = Value("20")
        resolved = type_resolver._resolve_value(number_value, "magic")

        assert resolved == "20"  # Should stay as number

        # Test number bigger than all values possible
        number_value = Value("200")
        with pytest.raises(ParamMagicIdError):
            resolved = type_resolver._resolve_value(number_value, "magic")

    # NEW TESTS FOR IF STATEMENTS

    def test_resolve_if_hp_specific_target(self, type_resolver):
        """Test resolution of: if(0, Self, >=, 50%)"""
        # Create AST for: if(0, Self, >=, 50%);
        params = [
            Value("0"),  # subject_id: HP OF SPECIFIC TARGET
            Value("Self"),  # left: target_advanced_specific
            Value(">="),  # comparator
            Value("50")  # right: percent
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Check it's still a Command
        assert isinstance(resolved, Command)
        assert resolved.name == "IF"

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # Check each parameter
        # subject_id should remain 0
        assert resolved.params.params[0].value == "0"

        # Self should be converted to appropriate target_advanced_specific value
        # Assuming "Self" maps to 0
        assert resolved.params.params[1].value.isdigit()
        assert resolved.params.params[1].value == "200"

        # Comparator ">=" should be converted to index (probably 5)
        comparator_index = resolved.params.params[2].value
        assert comparator_index == "5"

        # "50%" should be converted to 50
        assert resolved.params.params[3].value == "5"

    def test_resolve_if_hp_generic_target(self, type_resolver):
        """Test resolution of: if(1, All Enemies, <, 25%)"""
        # Create AST for: if(1, All Enemies, <, 25%);
        params = [
            Value("1"),  # subject_id: HP OF GENERIC TARGET
            Value("ENEMY_TEAM"),  # left: target_advanced_generic
            Value("<"),  # comparator
            Value("25")  # right: percent
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 1
        assert resolved.params.params[0].value == "1"

        # "All Enemies" should be converted to appropriate target_advanced_generic value
        assert resolved.params.params[1].value.isdigit()

        # Comparator "<" should be converted to index (probably 1)
        comparator_index = resolved.params.params[2].value
        assert comparator_index.isdigit()

        # "25" should be converted to 2
        assert resolved.params.params[3].value == "2"

    def test_resolve_if_random_value(self, type_resolver):
        """Test resolution of: if(2, 100, ==, 0) - RANDOM VALUE"""
        # Create AST for: if(2, 100, ==, 0);
        params = [
            Value("2"),  # subject_id: RANDOM VALUE
            Value("100"),  # left: int_shift (100 should become 99)
            Value("=="),  # comparator
            Value("0")  # right: int
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 2
        assert resolved.params.params[0].value == "2"

        # 100 should become 99 (int_shift: value - 1)
        assert resolved.params.params[1].value == "99"

        # Comparator "==" should be index 0
        assert resolved.params.params[2].value == "0"

        # Right should remain 0
        assert resolved.params.params[3].value == "0"

    def test_resolve_if_status_specific_target(self, type_resolver):
        """Test resolution of: if(4, Self, ==, Death)"""
        # Create AST for: if(4, Self, ==, Death);
        params = [
            Value("4"),  # subject_id: STATUS OF SPECIFIC TARGET
            Value("Self"),  # left: target_advanced_specific
            Value("=="),  # comparator
            Value("Death")  # right: status_ai
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 4
        assert resolved.params.params[0].value == "4"

        # Self should be converted
        assert resolved.params.params[1].value.isdigit()

        # Comparator "==" should be index 0
        assert resolved.params.params[2].value == "0"

        # Death should be converted to status_ai value
        assert resolved.params.params[3].value.isdigit()

    def test_resolve_if_dead_check(self, type_resolver):
        """Test resolution of: if(8, 0, ==, Self)"""
        # Create AST for: if(8, 0, ==, Self) - DEAD check
        params = [
            Value("8"),  # subject_id: DEAD
            Value("0"),  # left: empty type (should remain 0)
            Value("=="),  # comparator
            Value("Self")  # right: target_advanced_specific
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 8
        assert resolved.params.params[0].value == "8"

        # Left should remain 0 (empty type)
        assert resolved.params.params[1].value == "0"

        # Comparator "==" should be index 0
        assert resolved.params.params[2].value == "0"

        # Self should be converted to target_advanced_specific value
        assert resolved.params.params[3].value.isdigit()

    def test_resolve_if_global_var(self, type_resolver):
        """Test resolution of: if(80, TonberryCount, >, 5)"""
        # Create AST for: if(80, TonberryCount, >, 5);
        params = [
            Value("80"),  # subject_id: TonberryCount80
            Value("TonberrySrIsDefeated"),  # left: global_var
            Value(">"),  # comparator
            Value("5")  # right: int
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 80
        assert resolved.params.params[0].value == "80"

        # TonberrySrIsDefeated should be converted to global_var value
        assert resolved.params.params[1].value == "82"

        # Comparator ">" should be index 2
        assert resolved.params.params[2].value == "2"

        # Right should remain 5
        assert resolved.params.params[3].value == "5"

    def test_resolve_if_local_var(self, type_resolver):
        """Test resolution of: if(220, varA, !=, 10)"""
        # Create AST for: if(220, varA, !=, 10);
        params = [
            Value("220"),  # subject_id: varA
            Value("varA"),  # left: local_var
            Value("!="),  # comparator
            Value("10")  # right: int
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should have 4 parameters
        assert len(resolved.params.params) == 4

        # subject_id should remain 220
        assert resolved.params.params[0].value == "220"

        # varA should be converted to local_var value
        assert resolved.params.params[1].value.isdigit()

        # Comparator "!=" should be index 3
        assert resolved.params.params[2].value == "3"

        # Right should remain 10
        assert resolved.params.params[3].value == "10"

    def test_resolve_if_complex_structure(self, type_resolver):
        """Test resolution of IF with IfStatement structure"""
        # Create a complete IfStatement AST
        # if(0, Self, >=, 50%) { attack(); }
        condition_params = ParamList(params=[
            Value("0"),  # subject_id
            Value("Self"),  # left
            Value(">="),  # comparator
            Value("50")  # right
        ])
        condition = Condition(params=condition_params)

        # Then block with attack command
        then_block = Block(statements=[
            Command(name="attack", params=None)
        ])

        # Create IfStatement
        if_statement = IfStatement(
            condition=condition,
            then_block=then_block,
            elif_branches=[],
            else_block=None
        )

        # Resolve the IfStatement
        resolved = type_resolver.resolve(if_statement)

        # Should still be an IfStatement
        assert isinstance(resolved, IfStatement)

        # Condition parameters should be resolved
        cond_params = resolved.condition.params.params
        assert len(cond_params) == 4

        # Check subject_id
        assert cond_params[0].value == "0"

        # Self should be converted
        assert cond_params[1].value == "200"

        # Comparator ">=" should be converted
        assert cond_params[2].value == "5"

        # "50%" should be 5
        assert cond_params[3].value == "5"

        # Then block should be resolved
        assert isinstance(resolved.then_block, Block)
        assert len(resolved.then_block.statements) == 1

    def test_resolve_if_with_numeric_subject_id(self, type_resolver):
        """Test that numeric subject_id values work correctly"""
        # Test with numeric subject_id
        params = [
            Value("0"),  # numeric subject_id
            Value("Self"),  # left
            Value("=="),  # comparator
            Value("100%")  # right
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        resolved = type_resolver.resolve(command)

        # subject_id should remain 0
        assert resolved.params.params[0].value == "0"

        assert resolved.params.params[1].value == "200"

        assert resolved.params.params[2].value == "0"

        # "100%" should become 100
        assert resolved.params.params[3].value == "10"

    def test_resolve_if_with_hex_values(self, type_resolver):
        """Test IF resolution with hex values"""
        params = [
            Value("0x0"),  # hex subject_id (should become 0)
            Value("0x1"),  # hex left value
            Value("=="),  # comparator
            Value("0x64")  # hex 100
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        resolved = type_resolver.resolve(command)

        # Hex values should be converted to decimal
        assert resolved.params.params[0].value == "0"  # 0x0 -> 0
        assert resolved.params.params[1].value == "1"  # 0x1 -> 1
        assert resolved.params.params[3].value == "10"  # 0x64 -> 100

    def test_resolve_if_insufficient_params(self, type_resolver):
        """Test IF with insufficient parameters (should handle gracefully)"""
        # Only 2 params instead of 4
        params = [
            Value("0"),
            Value("Self")
        ]
        param_list = ParamList(params=params)
        command = Command(name="IF", params=param_list)

        with pytest.raises(ParamCountError):
            resolved = type_resolver.resolve(command)


if __name__ == "__main__":
    # Run tests and stop at first failure
    pytest.main([__file__, "-v", "-x", "--tb=short"])
