# test_aidecompiler.py
"""
Tests for AI Decompiler static methods.
"""
import pytest
from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from IfritAI.AICompiler.AIDecompiler import AIDecompiler


class TestAIDecompiler:
    """Test suite for AI Decompiler static methods"""

    def normalize_code(self, code):
        """Normalize code for comparison"""
        # Remove HTML tags and normalize whitespace
        import re
        code = re.sub(r'<br/?>', '\n', code)  # Replace <br> tags with newlines
        code = re.sub(r'&nbsp;', ' ', code)  # Replace &nbsp; with spaces
        code = re.sub(r'\s+', ' ', code)  # Normalize whitespace
        code = re.sub(r' ', '', code)  # remove whitespace
        return code.strip()

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

    def test_decompile_simple_command(self, ai_compiler):
        """Test decompiling a simple command"""
        # Create prepareMagic(2) command
        cmd = self.create_test_command(ai_compiler.game_data, 0, 0x03, [2])

        command_list = [cmd]
        print(command_list)
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled simple command ===")
        print(code)
        print("================================")

        # Check if it contains the expected command
        normalized = self.normalize_code(code)
        assert "prepareMagic(Fira);" in normalized

    def test_decompile_multiple_commands(self, ai_compiler):
        """Test decompiling multiple commands"""
        # Create commands: prepareMagic(1); attack(); die();
        cmd1 = self.create_test_command(ai_compiler.game_data, 0, 0x03, [1])  # prepareMagic(1)
        print(cmd1)
        cmd2 = self.create_test_command(ai_compiler.game_data, 1, 0x00, [])  # stop()
        cmd3 = self.create_test_command(ai_compiler.game_data,2,  0x08, [])  # die()

        command_list = [cmd1, cmd2, cmd3]
        print(command_list)
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled multiple commands ===")
        print(code)
        print("=====================================")

        normalized = self.normalize_code(code)
        assert "prepareMagic(Fire);" in normalized
        assert "stop();" in normalized
        assert "die();" in normalized

    def test_decompile_if_statement(self, ai_compiler):
        """Test decompiling if statement"""
        # Create commands for: if (1,2,3,4) { die(); }
        # IF command: [opcode, subject, param_type, comparator, value_low, value_high, jump_low, jump_high]
        if_cmd = self.create_test_command(ai_compiler.game_data, 0, 0x02, [1, 2, 3, 2, 0, 4, 0])
        die_cmd = self.create_test_command(ai_compiler.game_data, 1, 0x08, [])  # die() (assuming opcode 0x02)
        jump_cmd = self.create_test_command(ai_compiler.game_data, 2, 0x23, [0, 0])  # JUMP 0

        command_list = [if_cmd, die_cmd, jump_cmd]
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled if statement ===")
        print(code)
        print("===============================")

        normalized = self.normalize_code(code)
        assert "if(1,Irvine,!=,20)" in normalized
        assert "{" in normalized
        assert "die();" in normalized
        assert "}" in normalized

    def test_decompile_if_else_statement(self, ai_compiler):
        """Test decompiling if-else statement"""
        # Create commands for: if (1,2,3,4) { die(); } else { statChange(5,6); }
        # Note: This test might fail due to CommandAnalyser issues with statChange
        # We'll handle this gracefully


        # IF command
        if_cmd = self.create_test_command(ai_compiler.game_data,0 , 0x02, [1, 2, 3, 2, 0, 4, 0])
        die_cmd = self.create_test_command(ai_compiler.game_data,1,  0x08, [])  # die()
        jump_cmd = self.create_test_command(ai_compiler.game_data,2,  0x23, [3, 0])  # JUMP 3
        stat_change_cmd = self.create_test_command(ai_compiler.game_data, 3, 40, [4, 5])  # statChange(4,5)

        command_list = [if_cmd, die_cmd, jump_cmd, stat_change_cmd]
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled if-else statement ===")
        print(code)
        print("==================================")

        normalized = self.normalize_code(code)
        assert "if(1,Irvine,!=,20)" in normalized
        assert "die();" in normalized
        assert "else" in normalized
        opening_brace_count = normalized.count('{')
        assert opening_brace_count == 2, f"Expected 2 opening braces, found {opening_brace_count}"
        closing_brace_count = normalized.count('}')
        assert closing_brace_count == 2, f"Expected 2 opening braces, found {closing_brace_count}"
        assert "statChange(Speed,50);" in normalized

    def test_decompile_if_else_nested_statement(self, ai_compiler):
        """Test decompiling if-else statement"""

        if_cmd = self.create_test_command(ai_compiler.game_data,0 , 0x02, [1, 2, 3, 2, 0, 4, 0])
        die_cmd = self.create_test_command(ai_compiler.game_data,1,  0x08, [])  # die()
        jump_cmd = self.create_test_command(ai_compiler.game_data,2,  0x23, [12, 0])  # JUMP 3
        stop_cmd = self.create_test_command(ai_compiler.game_data, 3, 0x00, [])  # stop()
        if2_cmd = self.create_test_command(ai_compiler.game_data, 4, 0x02, [1, 2, 3, 2, 0, 4, 0])
        stat_change_cmd = self.create_test_command(ai_compiler.game_data, 5, 40, [4, 5])  # statChange(4,5)

        command_list = [if_cmd, die_cmd, jump_cmd, stop_cmd, if2_cmd, stat_change_cmd]
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled if-else nested statement ===")
        print(code)
        print("==================================")

        normalized = self.normalize_code(code)
        if_count = normalized.count("if(1,Irvine,!=,20)")
        assert if_count == 2, f"Expected 2 if(1,Irvine,!=,20), found {if_count}"
        assert "die();" in normalized
        assert "else" in normalized
        opening_brace_count = normalized.count('{')
        assert opening_brace_count == 3, f"Expected 3 opening braces, found {opening_brace_count}"
        closing_brace_count = normalized.count('}')
        assert closing_brace_count == 3, f"Expected 3 opening braces, found {closing_brace_count}"
        assert "statChange(Speed,50);" in normalized
        assert "stop" in normalized

    def test_decompile_if_elseif_else_statement(self, ai_compiler):
        """Test decompiling if-else statement"""
        # Create commands for: if (1,2,3,4) { die(); } else { statChange(5,6); }
        # Note: This test might fail due to CommandAnalyser issues with statChange
        # We'll handle this gracefully


        # IF command
        if_cmd = self.create_test_command(ai_compiler.game_data,0 , 0x02, [1, 2, 3, 2, 0, 6, 0])
        die_cmd = self.create_test_command(ai_compiler.game_data,1,  0x08, [])  # die()
        jump1_cmd = self.create_test_command(ai_compiler.game_data, 2, 0x23, [17, 0])  # JUMP 3
        if2_cmd = self.create_test_command(ai_compiler.game_data, 0, 0x02, [1, 2, 3, 1, 0, 6, 0])
        stat_change_cmd1 = self.create_test_command(ai_compiler.game_data, 3, 40, [3, 2])  # statChange(3,2)
        jump2_cmd = self.create_test_command(ai_compiler.game_data,2,  0x23, [3, 0])  # JUMP 3
        stat_change_cmd2 = self.create_test_command(ai_compiler.game_data, 3, 40, [4, 5])  # statChange(4,5)

        command_list = [if_cmd, die_cmd, jump1_cmd, if2_cmd, stat_change_cmd1, jump2_cmd, stat_change_cmd2 ]
        code = AIDecompiler.decompile_from_command_list(ai_compiler.game_data, command_list)

        print(f"\n=== Decompiled if-else statement ===")
        print(code)
        print("==================================")

        normalized = self.normalize_code(code)
        assert "if(1,Irvine,!=,20)" in normalized
        assert "die();" in normalized
        assert "elseif(1,Irvine,!=,10)" in normalized
        opening_brace_count = normalized.count('{')
        assert opening_brace_count == 3, f"Expected 3 opening braces, found {opening_brace_count}"
        closing_brace_count = normalized.count('}')
        assert closing_brace_count == 3, f"Expected 3 closing braces, found {closing_brace_count}"
        assert "statChange(Spirit,20);" in normalized
        assert "else" in normalized
        assert "statChange(Speed,50);" in normalized


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
    pytest.main([__file__, "-v", "--tb=short"])