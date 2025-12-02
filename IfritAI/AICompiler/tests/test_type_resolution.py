# test_type_resolution.py
"""
Tests for AST type resolution.
Focuses on verifying the type resolver converts string values to appropriate types.
"""
import pytest
from IfritAI.AICompiler.AIAST import *
from IfritAI.AICompiler.AITypeResolver import AITypeResolver


class TestAITypeResolution:
    """Test suite for AI Type Resolution"""

    @pytest.fixture
    def type_resolver(self, compiler):
        """Get the type resolver from compiler"""
        return compiler.type_resolver

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
        assert resolved_value.value == "1"  # Should be converted to number

    def test_resolve_unknown_value_stays_string(self, type_resolver):
        """Test that unknown values remain as strings"""
        # Create AST for: prepareMagic(UnknownSpell);
        unknown_value = Value("UnknownSpell")
        param_list = ParamList(params=[unknown_value])
        command = Command(name="prepareMagic", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Unknown values should remain as strings
        resolved_value = resolved.params.params[0]
        assert isinstance(resolved_value, Value)
        assert resolved_value.value == "UnknownSpell"  # Should stay as string

    def test_resolve_numeric_literal_stays_number(self, type_resolver):
        """Test that numeric literals remain as numbers"""
        # Create AST for: prepareMagic(100);
        number_value = Value("100")
        param_list = ParamList(params=[number_value])
        command = Command(name="prepareMagic", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Numeric literals should remain unchanged
        resolved_value = resolved.params.params[0]
        assert isinstance(resolved_value, Value)
        assert resolved_value.value == "100"  # Should stay as number

    def test_resolve_hex_number_stays_hex(self, type_resolver):
        """Test that hex numbers remain as hex strings"""
        # Create AST for: prepareMagic(0xFF);
        hex_value = Value("0xFF")
        param_list = ParamList(params=[hex_value])
        command = Command(name="prepareMagic", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Hex numbers should remain unchanged
        resolved_value = resolved.params.params[0]
        assert isinstance(resolved_value, Value)
        assert resolved_value.value == "0xFF"  # Should stay as hex

    def test_resolve_multiple_params_mixed(self, type_resolver):
        """Test resolution of multiple parameters with mixed types"""
        # Create AST for: set_status(poison, 5, 0x10);
        params = [
            Value("poison"),   # Should be resolved to number
            Value("5"),        # Should stay as number
            Value("0x10")      # Should stay as hex
        ]
        param_list = ParamList(params=params)
        command = Command(name="set_status", params=param_list)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Check all params
        resolved_params = resolved.params.params
        assert len(resolved_params) == 3

        # poison -> number
        assert resolved_params[0].value != "poison"
        assert resolved_params[0].value.isdigit()

        # 5 -> stays 5
        assert resolved_params[1].value == "5"

        # 0x10 -> stays 0x10
        assert resolved_params[2].value == "0x10"

    def test_resolve_command_without_params(self, type_resolver):
        """Test resolution of command without parameters"""
        # Create AST for: attack();
        command = Command(name="attack", params=None)

        # Resolve the command
        resolved = type_resolver.resolve(command)

        # Should still be a command without params
        assert isinstance(resolved, Command)
        assert resolved.name == "attack"
        assert resolved.params is None

    def test_resolve_block_of_statements(self, type_resolver):
        """Test resolution of a block containing multiple statements"""
        # Create AST block with multiple commands
        commands = [
            Command(name="prepareMagic", params=ParamList(params=[Value("Fire")])),
            Command(name="attack", params=None),
            Command(name="set_status", params=ParamList(params=[Value("poison"), Value("5")]))
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
        assert resolved.statements[1].name == "attack"
        assert resolved.statements[1].params is None

        # Third: set_status(poison, 5) -> set_status(<number>, 5)
        assert resolved.statements[2].params.params[0].value != "poison"
        assert resolved.statements[2].params.params[0].value.isdigit()
        assert resolved.statements[2].params.params[1].value == "5"

    def test_resolve_value_directly(self, type_resolver):
        """Test direct resolution of a Value node"""
        # Test resolving a known value
        fire_value = Value("Fire")
        resolved = type_resolver.resolve_value(fire_value)

        assert isinstance(resolved, Value)
        assert resolved.value == "1"  # Fire -> 1

        # Test resolving an unknown value
        unknown_value = Value("Unknown")
        resolved = type_resolver.resolve_value(unknown_value)

        assert isinstance(resolved, Value)
        assert resolved.value == "Unknown"  # Should stay as string

        # Test resolving a number
        number_value = Value("123")
        resolved = type_resolver.resolve_value(number_value)

        assert isinstance(resolved, Value)
        assert resolved.value == "123"  # Should stay as number


if __name__ == "__main__":
    # Run tests and stop at first failure
    pytest.main([__file__, "-v", "-x", "--tb=short"])