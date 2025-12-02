# test_code_generator.py
"""
Tests for AI Code Generator.
Tests that AST nodes are correctly converted to FF8 bytecode.
"""
import pytest
from IfritAI.AICompiler.AIAST import *


class TestAICodeGenerator:
    """Test suite for AI Code Generator"""

    def test_prepare_magic_with_number(self, ai_compiler):
        """Test that prepareMagic(2) generates [3, 2]"""
        code_generator = ai_compiler.generator

        # Create AST for: prepareMagic(2);
        number_value = Value("2")
        param_list = ParamList(params=[number_value])
        command = Command(name="prepareMagic", params=param_list)

        bytecode = code_generator.generate(command)
        expected = [0x03, 0x02]

        assert bytecode == expected, f"Expected {expected}, got {bytecode}"

    def test_if_statement_with_die(self, ai_compiler):
        """Test that if (1,2,3,4) { die(); } generates correct bytecode"""
        code_generator = ai_compiler.generator

        # Create AST for: if (1,2,3,4) { die(); }

        # 1. Create condition: (1,2,3,4)
        condition_params = ParamList(params=[
            Value("1"),
            Value("2"),
            Value("3"),
            Value("4")
        ])
        condition = Condition(params=condition_params)

        # 2. Create then block: die();
        die_command = Command(name="die", params=None)
        then_block = Block(statements=[die_command])

        # 3. Create if statement
        if_stmt = IfStatement(
            condition=condition,
            then_block=then_block,
            elif_branches=[],
            else_block=None
        )

        # Generate bytecode
        bytecode = code_generator.generate(if_stmt)

        # Expected bytecode based on your specification
        expected = [2, 1, 2, 3, 4, 0, 4, 0, 8, 35, 0, 0]

        assert bytecode == expected, f"Expected {expected}, got {bytecode}"

    def test_if_else_statement(self, ai_compiler):
        """Test that if (1,2,3,4) { die(); } else { statChange(5,6); } generates correct bytecode"""
        code_generator = ai_compiler.generator

        # Create AST for: if (1,2,3,4) { die(); } else { stateChange(5,6); }

        # 1. Create condition: (1,2,3,4)
        condition_params = ParamList(params=[
            Value("1"),
            Value("2"),
            Value("3"),
            Value("4")
        ])
        condition = Condition(params=condition_params)

        # 2. Create then block: die();
        die_command = Command(name="die", params=None)
        then_block = Block(statements=[die_command])

        # 3. Create else block: stateChange(5,6);
        state_change_params = ParamList(params=[
            Value("5"),
            Value("6")
        ])
        state_change_command = Command(name="statChange", params=state_change_params)
        else_block = Block(statements=[state_change_command])

        # 4. Create if statement
        if_stmt = IfStatement(
            condition=condition,
            then_block=then_block,
            elif_branches=[],
            else_block=else_block
        )

        # Generate bytecode
        bytecode = code_generator.generate(if_stmt)
        print(if_stmt)

        # Expected bytecode
        expected = [2, 1, 2, 3, 4, 0, 4, 0, 8, 35, 3, 0, 40, 5, 6]

        assert bytecode == expected, f"Expected {expected}, got {bytecode}"

    def test_if_elseif_else_statement(self, ai_compiler):
        """Test if with elseif and else"""
        code_generator = ai_compiler.generator

        # Create AST for:
        # if (100, 200, 3, 99) { prepareMagic(1); }
        # elseif(100, 200, 3, 101) { prepareMagic(2); }
        # else { prepareMagic(3); }

        # Create conditions
        condition1_params = ParamList(params=[
            Value("100"),
            Value("200"),
            Value("3"),
            Value("99")
        ])
        condition1 = Condition(params=condition1_params)

        condition2_params = ParamList(params=[
            Value("100"),
            Value("200"),
            Value("3"),
            Value("101")
        ])
        condition2 = Condition(params=condition2_params)

        # Create commands
        magic1 = Command(name="prepareMagic", params=ParamList(params=[Value("1")]))
        magic2 = Command(name="prepareMagic", params=ParamList(params=[Value("2")]))
        magic3 = Command(name="prepareMagic", params=ParamList(params=[Value("3")]))

        # Create blocks
        then_block = Block(statements=[magic1])
        elseif_block = Block(statements=[magic2])
        else_block = Block(statements=[magic3])

        # Create elseif branch
        elif_branch = ElifBranch(condition=condition2, block=elseif_block)

        # Create if statement
        if_stmt = IfStatement(
            condition=condition1,
            then_block=then_block,
            elif_branches=[elif_branch],
            else_block=else_block
        )

        # Generate bytecode
        bytecode = code_generator.generate(if_stmt)

        # Expected bytecode
        expected = [2, 100, 200, 3, 99, 0, 5, 0, 3, 1, 35, 15, 0, 2, 100, 200, 3, 101, 0, 5, 0, 3, 2, 35, 2, 0, 3, 3]

        assert bytecode == expected, f"Expected {expected}, got {bytecode}"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x", "--tb=short"])