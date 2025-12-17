# test_aidecompiler.py
"""
Tests for AI Decompiler static methods.
"""
import os

import pytest
from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIDecompiler import AIDecompiler


class TestAIDecompiler:
    """Test suite for AI Decompiler static methods"""

    @pytest.fixture
    def decompiler(self):
        """Create a Lark parser using the grammar from AICompiler"""

        # Use the actual grammar from AICompiler
        battle_text = ["First battle text", "Second battle text", "Third battle text"]
        info_stat_data = {}  # TODO
        game_data = GameData(os.path.join("..", "..", "..", "FF8GameData"))
        game_data.load_all()
        decompiler = AIDecompiler(game_data, battle_text, info_stat_data)
        return decompiler

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        if text is None:
            return ""
        return str(text).upper().replace(' ', '_').replace('-', '_')

    def pretty_code(self, code):
        """Normalize code for comparison - keeps basic formatting"""
        import re

        # Replace ALL <br> tags with newlines
        code = re.sub(r'<br\s*/?>', '\n', code)

        # Replace &nbsp; with regular spaces
        code = re.sub(r'&nbsp;', ' ', code)

        # Remove ALL HTML tags
        code = re.sub(r'<[^>]+>', '', code)

        # Remove all comments
        code = re.sub(r'//.*', '', code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove spaces around commas ONLY
        code = re.sub(r'\s*,\s*', ',', code)

        # Clean up each line
        lines = []
        for line in code.split('\n'):
            line = line.strip()
            if not line:
                continue
            lines.append(line)

        return '\n'.join(lines)

    def normalize_code(self, code):
        """Normalize code for comparison - removes HTML, comments, and normalizes parameters"""
        import re

        # Replace ALL <br> tags with newlines
        code = re.sub(r'<br\s*/?>', '\n', code)

        # Replace &nbsp; with regular spaces
        code = re.sub(r'&nbsp;', ' ', code)

        # Remove ALL HTML tags
        code = re.sub(r'<[^>]+>', '', code)

        # Remove all comments
        code = re.sub(r'//.*', '', code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove ALL whitespace around commas, parentheses, braces, etc.
        code = re.sub(r'\s*,\s*', ',', code)  # Remove spaces around commas
        code = re.sub(r'\s*\(\s*', '(', code)  # Remove spaces after '('
        code = re.sub(r'\s*\)\s*', ')', code)  # Remove spaces before ')'
        code = re.sub(r'\s*\{\s*', '{', code)  # Remove spaces after '{'
        code = re.sub(r'\s*\}\s*', '}', code)  # Remove spaces before '}'

        # Normalize remaining whitespace
        lines = []
        for line in code.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Process function parameters if present
            if '(' in line and ')' in line:
                parts = line.split('(', 1)
                if len(parts) == 2:
                    func_name = parts[0].strip()
                    rest = parts[1]

                    # Find the matching closing parenthesis
                    paren_count = 1
                    i = 0
                    while i < len(rest) and paren_count > 0:
                        if rest[i] == '(':
                            paren_count += 1
                        elif rest[i] == ')':
                            paren_count -= 1
                        i += 1

                    if paren_count == 0:
                        params_text = rest[:i - 1]
                        after_text = rest[i:] if i < len(rest) else ""

                        # Process parameters (already comma-separated without spaces)
                        if params_text:
                            params = [p for p in params_text.split(',') if p]
                            normalized_params = []

                            for param in params:
                                is_number = param.isdigit() or param.replace('.', '', 1).isdigit()
                                is_operator = param in ['!=', '==', '>=', '<=', '>', '<', '=', '+', '-', '*', '/', '&&', '||']

                                if not is_number and not is_operator:
                                    normalized_params.append(self._normalize_string(param))
                                else:
                                    normalized_params.append(param)

                            # Reconstruct line
                            line = func_name + '(' + ','.join(normalized_params) + ')' + after_text

            lines.append(line)

        return '\n'.join(lines)

    def create_test_command(self, game_data, index, opcode, params=()):
        """Helper to create a CommandAnalyser for testing"""

        return CommandAnalyser(
            op_id=opcode,
            op_code=params,
            game_data=game_data,
            battle_text=(),
            info_stat_data={},
            line_index=index,
            color="#0055ff",
            text_param=False,
            current_if_type=CurrentIfType.NONE,
            comment=""
        )

    def test_decompile_simple_command(self, decompiler):
        """Test decompiling a simple command"""
        # Create prepareMagic(2) command
        bytecode = [3, 2]
        cmd = self.create_test_command(decompiler.game_data, 0, 0x03, [2])

        command_expected = [cmd]
        command_decompiled = decompiler.decompile_bytecode_to_command_list(bytecode)
        assert command_expected == command_decompiled
        code_decompiled = decompiler.decompile_from_command_list(command_decompiled)
        print(f"\n=== Decompiled simple command ===")
        print(self.pretty_code(code_decompiled))
        print("================================")

        # Check if it contains the expected command
        normalized = self.normalize_code(code_decompiled)
        assert "prepareMagic(FIRA);" in normalized

    def test_decompile_multiple_commands(self, decompiler):
        """Test decompiling multiple commands"""
        # Create commands: prepareMagic(1); attack(); die();
        bytecode = [3, 1, 0, 8]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled multiple commands ===")
        print(self.pretty_code(code))
        print("=====================================")

        normalized = self.normalize_code(code)
        assert "prepareMagic(FIRE);" in normalized
        assert "stop" in normalized
        assert "die" in normalized

    def test_decompile_if_statement(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 1, 2, 3, 2, 0, 4, 0, 8, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled if statement ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        assert "if(1,IRVINE,!=,20%){die();}" in normalized

    def test_decompile_if_else_statement(self, decompiler):
        """Test decompiling if-else statement"""
        # Create commands for: if (1,2,3,4) { die(); } else { statChange(5,6); }
        # Note: This test might fail due to CommandAnalyser issues with statChange
        # We'll handle this gracefully
        bytecode = [2, 1, 2, 3, 2, 0, 4, 0, 8, 35, 3, 0, 40, 4, 5]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled if-else statement ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        assert "if(1,IRVINE,!=,20%){die();}else{statChange(SPEED,50);}" in normalized

    def test_decompile_if_else_nested_statement(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = [2, 1, 2, 3, 2, 0, 4, 0, 8, 35, 12, 0, 0, 2, 1, 2, 3, 2, 0, 4, 0, 40, 4, 5]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if-else nested statement ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(1,IRVINE,!=,20%)
            {
                die();
            }
            else
            {
                stop();
                if(1,IRVINE,!=,20%)
                {
                    statChange(SPEED,50);
                }
            }
            """
        )
        assert expected in normalized

    def test_decompile_if_elseif_else_statement(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = [2, 1, 2, 3, 2, 0, 6, 0, 8, 35, 17, 0, 2, 1, 2, 3, 1, 0, 6, 0, 40, 3, 2, 35, 3, 0, 40, 4, 5]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if-elseif-else statement ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(1,IRVINE,!=,20)
            {
                die();
            }
            elseif(1,IRVINE,!=,10)
            {
                statChange(SPIRIT,20);
            }
            else
            {
                statChange(SPEED,50);
            }
            """
        )
        assert expected in normalized

    def test_compute_indent_bracket(self):
        """Test the compute_indent_bracket static method"""
        func_list = [
            "if (1,2,3,4)",
            "{",
            "die();",
            "}",
            "else",
            "{",
            "stop();",
            "}"
        ]

        indented = AIDecompiler.compute_indent_bracket(func_list)

        print(f"\n=== Indented list ===")
        for line in indented:
            print(line)
        print("=====================")

        # Check indentation
        assert indented[0] == "if (1,2,3,4)"  # No indent
        assert indented[1] == "{"
        assert indented[2] == "&nbsp;&nbsp;&nbsp;&nbsp;die();"  # 4 spaces indent
        assert indented[3] == "}"  # Back to no indent
        assert indented[4] == "else"  # No indent
        assert indented[5] == "{"
        assert indented[6] == "&nbsp;&nbsp;&nbsp;&nbsp;stop();"  # 4 spaces indent
        assert indented[7] == "}"  # Back to no indent

    def test_empty_command_list(self, ai_compiler):
        """Test decompiling empty command list"""
        command_list = []
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        assert code == "" or code is None or code == "\n"

    def test_single_command_no_params(self, ai_compiler):
        """Test decompiling single command without parameters"""
        cmd = self.create_test_command(ai_compiler.game_data, 0, 0x00, [])  # stop()

        command_list = [cmd]
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        normalized = self.normalize_code(code)
        assert "stop();" in normalized


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x", "--tb=short"])  # Capture all print
