# test_ast_structure.py
import pytest
from lark import Lark
from IfritAI.AICompiler.AIASTTransformer import AIASTTransformer
from IfritAI.AICompiler.AIAST import *


class TestAIASTTransformer:
    """Test suite for AI AST Transformer"""

    @pytest.fixture
    def parser(self):
        """Create a Lark parser using the grammar from AICompiler"""
        from IfritAI.AICompiler.AICompiler import AICompiler

        # Use the actual grammar from AICompiler
        grammar = AICompiler.grammar
        return Lark(grammar, start='start', parser='lalr')

    @pytest.fixture
    def transformer(self):
        """Create an AIASTTransformer instance"""
        return AIASTTransformer()

    def transform_code(self, parser, transformer, code):
        """Helper to parse and transform code"""
        tree = parser.parse(code)
        return transformer.transform(tree)

    # Test 1: Simple command without parameters
    def test_simple_command_no_params(self, parser, transformer):
        """Test transforming a simple command without parameters"""
        code = "die;"
        ast = self.transform_code(parser, transformer, code)

        # Should be a Command AST node
        assert isinstance(ast, Command)
        assert ast.name == 'die'
        assert ast.params is None

    # Test 2: Command with empty parentheses
    def test_command_empty_parentheses(self, parser, transformer):
        """Test transforming a command with empty parentheses"""
        code = "attack();"
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, Command)
        assert ast.name == 'attack'
        # Empty parentheses should result in None params
        assert ast.params is None

    # Test 3: Command with single parameter
    def test_command_single_param(self, parser, transformer):
        """Test transforming a command with single parameter"""
        code = "prepareMagic(2);"
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, Command)
        assert ast.name == 'prepareMagic'
        assert isinstance(ast.params, ParamList)
        assert len(ast.params.params) == 1

        param = ast.params.params[0]
        assert isinstance(param, Value)
        assert param.value == '2'

    # Test 4: Command with multiple parameters
    def test_command_multiple_params(self, parser, transformer):
        """Test transforming a command with multiple parameters"""
        code = "useRandom(0,1,2);"
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, Command)
        assert ast.name == 'useRandom'
        assert isinstance(ast.params, ParamList)
        assert len(ast.params.params) == 3

        expected_values = ['0', '1', '2']
        for i, param in enumerate(ast.params.params):
            assert isinstance(param, Value)
            assert param.value == expected_values[i]

    # Test 5: Command with mixed parameter types
    def test_command_mixed_params(self, parser, transformer):
        """Test transforming a command with mixed parameter types"""
        code = "set_status(poison, 5);"
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, Command)
        assert ast.name == 'set_status'
        assert isinstance(ast.params, ParamList)
        assert len(ast.params.params) == 2

        # First param should be ID 'poison'
        assert isinstance(ast.params.params[0], Value)
        assert ast.params.params[0].value == 'poison'

        # Second param should be NUMBER '5'
        assert isinstance(ast.params.params[1], Value)
        assert ast.params.params[1].value == '5'

    # Test 6: Simple if statement
    def test_simple_if_statement(self, parser, transformer):
        """Test transforming a simple if statement"""
        code = """
        if (1,2,3,4) {
            die();
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Check condition
        assert isinstance(ast.condition, Condition)
        assert isinstance(ast.condition.params, ParamList)
        assert len(ast.condition.params.params) == 4

        # Check then block
        assert isinstance(ast.then_block, Block)
        assert len(ast.then_block.statements) == 1

        then_stmt = ast.then_block.statements[0]
        assert isinstance(then_stmt, Command)
        assert then_stmt.name == 'die'
        assert then_stmt.params is None

        # Check no elseif branches
        assert len(ast.elif_branches) == 0

        # Check no else block
        assert ast.else_block is None

    # Test 7: If statement with else
    def test_if_else_statement(self, parser, transformer):
        """Test transforming if statement with else"""
        code = """
        if (1,2,3,4) {
            die();
        } else {
            attack();
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Check condition
        assert len(ast.condition.params.params) == 4

        # Check then block
        assert len(ast.then_block.statements) == 1
        then_cmd = ast.then_block.statements[0]
        assert then_cmd.name == 'die'

        # Check no elseif branches
        assert len(ast.elif_branches) == 0

        # Check else block exists
        assert ast.else_block is not None
        assert isinstance(ast.else_block, Block)
        assert len(ast.else_block.statements) == 1

        else_cmd = ast.else_block.statements[0]
        assert else_cmd.name == 'attack'

    # Test 8: If statement with elseif
    def test_if_elseif_statement(self, parser, transformer):
        """Test transforming if statement with elseif"""
        code = """
        if (1,2,3,4) {
            die();
        } elseif (5,6,7,8) {
            prepareMagic(2);
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Check condition
        assert len(ast.condition.params.params) == 4

        # Check then block
        assert len(ast.then_block.statements) == 1
        assert ast.then_block.statements[0].name == 'die'

        # Check elseif branches
        assert len(ast.elif_branches) == 1

        elif_branch = ast.elif_branches[0]
        assert isinstance(elif_branch, ElifBranch)

        # Check elseif condition
        assert isinstance(elif_branch.condition, Condition)
        assert len(elif_branch.condition.params.params) == 4

        # Check elseif block
        assert isinstance(elif_branch.block, Block)
        assert len(elif_branch.block.statements) == 1

        elif_cmd = elif_branch.block.statements[0]
        assert elif_cmd.name == 'prepareMagic'
        assert elif_cmd.params is not None
        assert elif_cmd.params.params[0].value == '2'

        # Check no else block
        assert ast.else_block is None

    # Test 9: If statement with elseif and else
    def test_if_elseif_else_statement(self, parser, transformer):
        """Test transforming if statement with elseif and else"""
        code = """
        if (1,2,3,4) {
            die();
        } elseif (5,6,7,8) {
            prepareMagic(2);
        } else {
            useRandom(0,1,2);
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Check condition
        assert len(ast.condition.params.params) == 4

        # Check then block
        assert len(ast.then_block.statements) == 1
        assert ast.then_block.statements[0].name == 'die'

        # Check elseif branches
        assert len(ast.elif_branches) == 1
        elif_branch = ast.elif_branches[0]
        assert len(elif_branch.condition.params.params) == 4
        assert elif_branch.block.statements[0].name == 'prepareMagic'

        # Check else block
        assert ast.else_block is not None
        assert len(ast.else_block.statements) == 1
        else_cmd = ast.else_block.statements[0]
        assert else_cmd.name == 'useRandom'
        assert len(else_cmd.params.params) == 3

    # Test 10: Multiple elseif branches
    def test_multiple_elseif_branches(self, parser, transformer):
        """Test transforming if statement with multiple elseif branches"""
        code = """
        if (1,2,3,4) {
            attack();
        } elseif (5,6,7,8) {
            defend();
        } elseif (9,10,11,12) {
            escape();
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)
        assert len(ast.elif_branches) == 2

        # Check first elseif
        assert ast.elif_branches[0].block.statements[0].name == 'defend'

        # Check second elseif
        assert ast.elif_branches[1].block.statements[0].name == 'escape'

    # Test 11: Nested if statements
    def test_nested_if_statements(self, parser, transformer):
        """Test transforming nested if statements"""
        code = """
        if (1,4,2,3) {
            if (1,2,3,4) {
                die();
            }
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Outer if condition
        assert len(ast.condition.params.params) == 4

        # Outer if block should have one statement (inner if)
        assert len(ast.then_block.statements) == 1

        inner_stmt = ast.then_block.statements[0]
        assert isinstance(inner_stmt, IfStatement)

        # Inner if condition
        assert len(inner_stmt.condition.params.params) == 4

        # Inner if block
        assert len(inner_stmt.then_block.statements) == 1
        assert inner_stmt.then_block.statements[0].name == 'die'

    # Test 12: Condition with operators
    def test_condition_with_operators(self, parser, transformer):
        """Test transforming condition with operators"""
        code = """
        if (hp, >, 50, mp, <, 20) {
            heal(100);
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)

        # Check condition has 6 params
        assert len(ast.condition.params.params) == 6

        # Check operator values are captured
        param_values = [p.value for p in ast.condition.params.params]
        assert 'hp' in param_values
        assert '>' in param_values
        assert '50' in param_values
        assert 'mp' in param_values
        assert '<' in param_values
        assert '20' in param_values

    # Test 13: Multiple statements at top level
    def test_multiple_statements_top_level(self, parser, transformer):
        """Test transforming multiple statements at top level"""
        code = """
        prepareMagic(1);
        prepareMagic(2);
        prepareMagic(3);
        """
        ast = self.transform_code(parser, transformer, code)

        # Multiple statements should be wrapped in a Block
        assert isinstance(ast, Block)
        assert len(ast.statements) == 3

        for i, stmt in enumerate(ast.statements):
            assert isinstance(stmt, Command)
            assert stmt.name == 'prepareMagic'
            assert stmt.params.params[0].value == str(i + 1)

    # Test 14: Empty block
    def test_empty_block(self, parser, transformer):
        """Test transforming an empty block"""
        code = """
        if (1,2,3,4) {
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)
        assert isinstance(ast.then_block, Block)
        assert len(ast.then_block.statements) == 0

    # Test 15: Multiple statements in block
    def test_multiple_statements_in_block(self, parser, transformer):
        """Test transforming multiple statements in a block"""
        code = """
        if (1,2,3,4) {
            prepareMagic(1);
            prepareMagic(2);
            prepareMagic(3);
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)
        assert len(ast.then_block.statements) == 3

        for i, stmt in enumerate(ast.then_block.statements):
            assert isinstance(stmt, Command)
            assert stmt.name == 'prepareMagic'
            assert stmt.params.params[0].value == str(i + 1)

    # Test 16: Complete complex example
    def test_complete_complex_example(self, parser, transformer):
        """Test transforming a complete complex example"""
        code = """
        if (1,4,2,3) {
            if (1,2,3,4) {
                die();
            }
            elseif(5,6,7,8)
            {
               prepareMagic(2);
            }
            else
            {
            useRandom(0,1,2);
            }
        }
        else
        {
        prepareMagic(4);
        }
        """
        ast = self.transform_code(parser, transformer, code)

        # Verify overall structure
        assert isinstance(ast, IfStatement)

        # Outer if condition
        assert len(ast.condition.params.params) == 4

        # Outer if then block (contains nested if)
        assert len(ast.then_block.statements) == 1
        nested_if = ast.then_block.statements[0]
        assert isinstance(nested_if, IfStatement)

        # Nested if structure
        assert len(nested_if.condition.params.params) == 4
        assert len(nested_if.elif_branches) == 1
        assert nested_if.else_block is not None

        # Outer else block
        assert ast.else_block is not None
        assert len(ast.else_block.statements) == 1
        else_cmd = ast.else_block.statements[0]
        assert else_cmd.name == 'prepareMagic'
        assert else_cmd.params.params[0].value == '4'

    # Test 17: Value types are preserved
    def test_value_types_preserved(self, parser, transformer):
        """Test that Value types are correctly created"""
        code = "test(id, 123, >);"
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, Command)
        assert ast.name == 'test'

        params = ast.params.params
        assert len(params) == 3

        # ID token
        assert isinstance(params[0], Value)
        assert params[0].value == 'id'

        # NUMBER token
        assert isinstance(params[1], Value)
        assert params[1].value == '123'

        # OPERATOR token
        assert isinstance(params[2], Value)
        assert params[2].value == '>'

    # Test 18: ElifBranch structure
    def test_elif_branch_structure(self, parser, transformer):
        """Test that ElifBranch nodes are correctly structured"""
        code = """
        if (1) {
            a();
        } elseif (2) {
            b();
        } elseif (3) {
            c();
        }
        """
        ast = self.transform_code(parser, transformer, code)

        assert isinstance(ast, IfStatement)
        assert len(ast.elif_branches) == 2

        # Check each elif branch
        for i, elif_branch in enumerate(ast.elif_branches):
            assert isinstance(elif_branch, ElifBranch)
            assert isinstance(elif_branch.condition, Condition)
            assert isinstance(elif_branch.block, Block)

            # Condition should have param with value str(i+2)
            assert elif_branch.condition.params.params[0].value == str(i + 2)

            # Block should have command with name chr(ord('a') + i + 1)
            cmd_name = chr(ord('a') + i + 1)
            assert elif_branch.block.statements[0].name == cmd_name


if __name__ == "__main__":
    # Run tests and stop at first failure
    pytest.main([__file__, "-v", "-x", "--tb=short"])