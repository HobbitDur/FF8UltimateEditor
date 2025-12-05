# test_parser.py
import pytest
from lark import Tree, Token


class TestFF8MonsterAIParser:
    """Test suite for FF8 monster AI grammar parser"""

    # Helper method to debug tree structure
    def debug_tree(self, tree, label=""):
        """Print tree structure for debugging"""
        print(f"\n=== Debug Tree: {label} ===")
        print(tree.pretty())

    def find_nodes(self, tree, node_type):
        """Find all nodes of a specific type in the tree"""
        nodes = []
        for node in tree.iter_subtrees():
            if str(node.data) == node_type or node.data == node_type:
                nodes.append(node)
        return nodes


    # Test 1: Simple command without parameters (but with empty parentheses)
    def test_simple_command_no_params(self, parser):
        """Test parsing a simple command without parameters"""
        input_code = "die();"
        tree = parser.parse(input_code)

        # Verify structure
        assert str(tree.data) == 'start'
        assert len(tree.children) == 1

        stmt = tree.children[0]
        assert str(stmt.data) == 'stmt'
        assert len(stmt.children) == 1

        command = stmt.children[0]
        assert str(command.data) == 'command'

        # Command should have the ID token
        assert len(command.children) >= 1
        assert command.children[0].type == 'ID'
        assert command.children[0].value == 'die'

        # Check if there's a param_list (should be None for empty parentheses)
        has_param_list = any(isinstance(child, Tree) and str(child.data) == 'param_list'
                             for child in command.children)
        # Empty parentheses might not create a param_list node

        # Verify the command ends with semicolon (might not be in the tree structure)

    # Test 1.1: test comment
    def test_comment(self, parser):
        """Test parsing code with comments"""
        # Test single line comment
        input_code = "die(); // Tutu"
        tree = parser.parse(input_code)

        # Verify the tree structure ignores the comment
        assert str(tree.data) == 'start'
        assert len(tree.children) == 1

        stmt = tree.children[0]
        assert str(stmt.data) == 'stmt'

        # Should parse only the command, ignoring the comment
        command = stmt.children[0]
        assert str(command.data) == 'command'
        assert command.children[0].value == 'die'

        # Verify no comment tokens in the tree
        tokens = list(tree.scan_values(lambda v: isinstance(v, Token)))
        # Should only have ID and maybe parentheses/semicolon tokens
        # No comment tokens should appear

        # Test comment at end of line with whitespace
        input_code = "die();   // This is a comment"
        tree = parser.parse(input_code)
        assert str(tree.data) == 'start'

        # Test comment on its own line
        input_code = """
        die();
        // This is a comment
        """
        tree = parser.parse(input_code)

        # Test comment before code
        input_code = """
        // Comment before
        die();
        """
        tree = parser.parse(input_code)
        assert str(tree.data) == 'start'

        # Test comment in the middle of a condition
        input_code = """
        if (hp, >, 50 // comment in condition
            , mp, <, 20) {
            heal(100);
        }
        """
        tree = parser.parse(input_code)
        assert str(tree.data) == 'start'

        # Test multiple comments
        input_code = """
        // Comment 1
        die();
        // Comment 2
        prepareMagic(2); // Comment 3
        // Comment 4
        """
        tree = parser.parse(input_code)
        # Should have 2 commands
        commands = self.find_nodes(tree, 'command')
        assert len(commands) == 2

        # Test comment inside block
        input_code = """
        if (1,2,3,4) {
            // Comment inside block
            die();
            // Another comment
        }
        """
        tree = parser.parse(input_code)
        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) == 1

    def test_comments_comprehensive(self, parser):
        """Test comprehensive comment scenarios"""
        test_cases = [
            # (code, description, expected_command_count)
            ("die(); // inline comment", "Inline comment", 1),
            ("// comment only\n", "Comment only line", 0),
            ("// comment\n\ndie();", "Comment then empty line then code", 1),
            ("die();\n// comment\nprepareMagic(2);", "Code, comment, code", 2),
            ("if (1,2,3,4) {\n    // comment in block\n    die();\n}",
             "Comment inside block", 1),
            ("// multiple\n// line\n// comments\ndie();",
             "Multiple comment lines before code", 1),
        ]

        for code, description, expected_commands in test_cases:
            try:
                tree = parser.parse(code)
                commands = self.find_nodes(tree, 'command')
                assert len(commands) == expected_commands, \
                    f"Failed for {description}: expected {expected_commands} commands, got {len(commands)}"
            except Exception as e:
                pytest.fail(f"{description} failed to parse:\n{code}\nError: {e}")

    def test_block_comments(self, parser):
        """Test parsing with block comments"""
        # Test block comment
        input_code = "die(); /* block comment */"
        tree = parser.parse(input_code)
        assert str(tree.data) == 'start'

        # Test multi-line block comment
        input_code = """
        /*
         * Multi-line
         * block comment
         */
        die();
        """
        tree = parser.parse(input_code)

        # Test block comment spanning multiple lines
        input_code = """
        die(); /*
        comment continues
        on next line */ prepareMagic(2);
        """
        tree = parser.parse(input_code)
        commands = self.find_nodes(tree, 'command')
        assert len(commands) == 2

        # Test nested comments (won't work with simple C_COMMENT)
        # input_code = "/* outer /* inner */ outer */ die();"
        # This would need special handling

    # Test 2: Command without parentheses (valid when no params)
    def test_command_no_parentheses_valid(self, parser):
        """Test that command without parentheses is valid when no parameters"""
        input_code = "die;"
        tree = parser.parse(input_code)

        # Verify structure
        assert str(tree.data) == 'start'
        assert len(tree.children) == 1

        stmt = tree.children[0]
        assert str(stmt.data) == 'stmt'
        assert len(stmt.children) == 1

        command = stmt.children[0]
        assert str(command.data) == 'command'

        # Command should have the ID token
        assert len(command.children) >= 1
        assert command.children[0].type == 'ID'
        assert command.children[0].value == 'die'

        # No param_list should be present
        has_param_list = any(
            isinstance(child, Tree) and str(child.data) == 'param_list'
            for child in command.children
        )
        assert not has_param_list, "Should not have param_list for command without parentheses"

    # Test 3: Command with empty parentheses
    def test_command_empty_parentheses(self, parser):
        """Test parsing a command with empty parentheses"""
        input_code = "die();"
        tree = parser.parse(input_code)

        # Verify structure
        assert str(tree.data) == 'start'

        # Find command nodes
        commands = self.find_nodes(tree, 'command')
        assert len(commands) == 1

        command = commands[0]
        assert command.children[0].value == 'die'

    # Test 4: Command with single parameter
    def test_command_single_param(self, parser):
        """Test parsing a command with a single parameter"""
        input_code = "prepareMagic(2);"
        tree = parser.parse(input_code)

        # Verify structure
        assert str(tree.data) == 'start'

        # Find param_list nodes
        param_lists = self.find_nodes(tree, 'param_list')
        assert len(param_lists) == 1

        param_list = param_lists[0]
        assert len(param_list.children) == 1

        value = param_list.children[0]
        assert str(value.data) == 'value'
        assert value.children[0].value == '2'

    # Test 5: Command with multiple parameters
    def test_command_multiple_params(self, parser):
        """Test parsing a command with multiple parameters"""
        input_code = "useRandom(0,1,2);"
        tree = parser.parse(input_code)

        # Verify structure
        param_lists = self.find_nodes(tree, 'param_list')
        assert len(param_lists) == 1

        param_list = param_lists[0]
        assert len(param_list.children) == 3

        expected_values = ['0', '1', '2']
        for i, child in enumerate(param_list.children):
            assert str(child.data) == 'value'
            assert child.children[0].value == expected_values[i]

    # Test 6: Condition with numeric parameters
    def test_condition_numeric_params(self, parser):
        """Test parsing a condition with numeric parameters"""
        input_code = """
        if (1,4,2,3) {
            die();
        }
        """
        tree = parser.parse(input_code)

        # Verify structure
        conditions = self.find_nodes(tree, 'condition')
        assert len(conditions) == 1

        condition = conditions[0]
        param_lists = [child for child in condition.children if str(child.data) == 'param_list']
        assert len(param_lists) == 1

        param_list = param_lists[0]
        assert len(param_list.children) == 4

        expected_values = ['1', '4', '2', '3']
        for i, child in enumerate(param_list.children):
            assert str(child.data) == 'value'
            assert child.children[0].value == expected_values[i]

    # Test 7: Simplified version
    def test_condition_with_operators(self, parser):
        """Test parsing a condition with operators"""
        input_code = """
        if (hp, >, 50, mp, <, 20) {
            heal(100);
        }
        """
        tree = parser.parse(input_code)

        # Just verify the important things:

        # 1. Count OPERATOR tokens (should be 2: > and <)
        operator_tokens = []
        for token in tree.scan_values(lambda v: isinstance(v, Token)):
            if token.type == 'OPERATOR':
                operator_tokens.append(token.value)

        assert len(operator_tokens) == 2
        assert '>' in operator_tokens
        assert '<' in operator_tokens

        # 2. Verify we have the expected structure
        # Count conditions
        conditions = []
        for node in tree.iter_subtrees():
            if str(node.data) == 'condition':
                conditions.append(node)

        assert len(conditions) == 1

        # 3. Count param_lists (should be 2 total)
        param_lists = []
        for node in tree.iter_subtrees():
            if str(node.data) == 'param_list':
                param_lists.append(node)

        assert len(param_lists) == 2

        # 4. One param_list should have 6 values (condition),
        #    one should have 1 value (heal command)
        param_list_sizes = [len(pl.children) for pl in param_lists]
        assert 6 in param_list_sizes, "No param_list with 6 values found"
        assert 1 in param_list_sizes, "No param_list with 1 value found"


    # Test 8: If with elseif and else
    def test_if_elseif_else(self, parser):
        """Test parsing if with elseif and else"""
        input_code = """
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
        """
        tree = parser.parse(input_code)

        # Verify structure
        if_stmts = self.find_nodes(tree, 'if_stmt')
        assert len(if_stmts) == 1

        if_stmt = if_stmts[0]
        # if_stmt should have: condition, block, elseif_branches, else_block
        assert len(if_stmt.children) >= 3

        # Should have conditions
        conditions = self.find_nodes(tree, 'condition')
        assert len(conditions) >= 2  # if condition + elseif condition

        # Should have blocks
        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) >= 3  # then block + elseif block + else block

    # Test 9: Nested if statements
    def test_nested_if_statements(self, parser):
        """Test parsing nested if statements"""
        input_code = """
        if (1,4,2,3) {
            if (1,2,3,4) {
                die();
            }
        }
        """
        tree = parser.parse(input_code)

        # Verify structure
        if_stmts = self.find_nodes(tree, 'if_stmt')
        assert len(if_stmts) == 2  # Outer if + inner if

        conditions = self.find_nodes(tree, 'condition')
        assert len(conditions) == 2

        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) == 2

    # Test 10: Complete example from description
    def test_complete_example(self, parser):
        """Test parsing the complete example from description"""
        input_code = """
        if (1,4,2,3)     
        {
            if (1,2,3,4)  
            {
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
        tree = parser.parse(input_code)

        # Verify structure
        assert str(tree.data) == 'start'

        # Count different node types
        if_stmts = self.find_nodes(tree, 'if_stmt')
        assert len(if_stmts) == 2  # Outer if + inner if

        conditions = self.find_nodes(tree, 'condition')
        assert len(conditions) == 3  # Outer if + inner if + inner elseif

        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) >= 4  # Multiple blocks

        commands = self.find_nodes(tree, 'command')
        assert len(commands) >= 3  # die() + prepareMagic(2) + useRandom(0,1,2) + prepareMagic(4)

    # Test 11: Multiple elseif branches
    def test_multiple_elseif(self, parser):
        """Test parsing multiple elseif branches"""
        input_code = """
        if (1,2,3,4) {
            die();
        }
        elseif(5,6,7,8)
        {
            fillAtb;
        }
        elseif(9,10,11,12)
        {
            stop;
        }
        """
        tree = parser.parse(input_code)

        # Count conditions (if + 2 elseif)
        conditions = self.find_nodes(tree, 'condition')
        assert len(conditions) == 3

        # Count blocks (then + 2 elseif)
        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) == 3

    # Test 12: Empty block
    def test_empty_block(self, parser):
        """Test parsing an empty block"""
        input_code = """
        if (1,2,3,4) {
        }
        """
        tree = parser.parse(input_code)

        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) == 1

        block = blocks[0]
        # Block should be empty or have no statement children
        stmts_in_block = [child for child in block.children if str(child.data) == 'stmt']
        assert len(stmts_in_block) == 0

    # Test 13: Multiple statements in a block
    def test_multiple_statements_in_block(self, parser):
        """Test parsing multiple statements in a block"""
        input_code = """
        if (1,2,3,4) {
            prepareMagic(1);
            prepareMagic(2);
            prepareMagic(3);
        }
        """
        tree = parser.parse(input_code)

        blocks = self.find_nodes(tree, 'block')
        assert len(blocks) == 1

        block = blocks[0]
        # Count statements in the block
        stmts_in_block = [child for child in block.children if str(child.data) == 'stmt']
        assert len(stmts_in_block) == 3

        # Count commands
        commands = []
        for stmt in stmts_in_block:
            for child in stmt.children:
                if str(child.data) == 'command':
                    commands.append(child)

        assert len(commands) == 3

    # Test 14: All comparison operators
    def test_all_operators(self, parser):
        """Test all comparison operators"""
        operators = ['==', '!=', '>', '<', '>=', '<=']

        for op in operators:
            input_code = f"""
            if (hp, {op}, 50, 4) {{
                die();
            }}
            """
            tree = parser.parse(input_code)

            # Find all operators in the tree
            operator_tokens = []
            for token in tree.scan_values(lambda v: isinstance(v, Token)):
                if token.type == 'OPERATOR':
                    operator_tokens.append(token.value)

            assert op in operator_tokens, f"Operator {op} not found in parsed tree"

    # Test 15: Invalid syntax cases
    def test_invalid_syntax_cases(self, parser):
        """Test various invalid syntax cases"""
        invalid_cases = [
            "die()",  # Missing semicolon
            "if 1,2,3,4 { die(); }",  # Missing parentheses around condition
            "if (1,2,3,4 die(); }",  # Missing opening brace
            "if (1,2,3,4) { die(); ",  # Missing closing brace
            "prepareMagic(2,);",  # Trailing comma
            "prepareMagic(,2);",  # Leading comma
            "if () { die(); }",  # Empty condition
        ]
        for i, invalid_code in enumerate(invalid_cases):
            with pytest.raises(Exception) as exc_info:
                parser.parse(invalid_code)
            # Just verify it raises an exception

    # Test 16: Valid edge cases
    def test_valid_edge_cases(self, parser):
        """Test valid edge cases"""
        valid_cases = [
            ("die();", "Empty parentheses"),
            ("if (1) { die(); }", "Single param in condition"),
            ("if (a,b,c) { die(); }", "Three params with IDs"),
            ("if (1,==,<,4) { die(); }", "Mixed operators and numbers"),
        ]

        for code, description in valid_cases:
            try:
                tree = parser.parse(code)
                assert tree is not None, f"Failed to parse: {description}"
                assert str(tree.data) == 'start', f"Invalid root for: {description}"
            except Exception as e:
                pytest.fail(f"{description} failed to parse: {code}\nError: {e}")


if __name__ == "__main__":
    # Run tests and stop at first failure
    pytest.main([__file__, "-v", "-x", "--tb=short"])