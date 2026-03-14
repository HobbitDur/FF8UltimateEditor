# test_aidecompiler.py
"""
Tests for AI Decompiler static methods.
"""
import os

import pytest

from FF8GameData.GenericSection.ff8text import FF8Text
from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIDecompiler import AIDecompiler


class TestAIDecompiler:
    """Test suite for AI Decompiler static methods"""

    @pytest.fixture
    def decompiler(self):
        """Create a Lark parser using the grammar from AICompiler"""
        game_data = GameData(os.path.join("..", "..", "..", "FF8GameData"))
        #game_data = GameData(os.path.join("FF8GameData"))
        game_data.load_all()
        # Use the actual grammar from AICompiler
        first_battle_text = FF8Text(game_data, 0, bytearray(), 0)
        first_battle_text.set_str("First battle text")
        second_battle_text = FF8Text(game_data, 0, bytearray(), 1)
        second_battle_text.set_str("Second battle text")
        third_battle_text = FF8Text(game_data, 0, bytearray(), 2)
        third_battle_text.set_str("Third battle text")
        double_space = FF8Text(game_data, 0, bytearray(), 3)
        double_space.set_str("“I'm  done for…”")
        bite_bug_text = FF8Text(game_data, 0, bytearray(), 0)
        bite_bug_text.set_str("Bite Bug")
        battle_text = [first_battle_text, second_battle_text, third_battle_text, double_space]
        info_stat_data = {'monster_name': bite_bug_text, 'hp': [4, 11, 0, 0], 'str': [30, 5, 6, 130], 'vit': [1, 50, 4, 1], 'mag': [24, 5, 2, 100], 'spr': [1, 6, 2, 1], 'spd': [0, 10, 4, 20], 'eva': [0, 10, 2, 30], 'abilities_low': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 8, 'animation': 12, 'id': 2}, {'type': 8, 'animation': 12, 'id': 2}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}], 'abilities_med': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 8, 'animation': 13, 'id': 110}, {'type': 8, 'animation': 14, 'id': 111}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}], 'abilities_high': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 8, 'animation': 13, 'id': 110}, {'type': 8, 'animation': 14, 'id': 111}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}], 'med_lvl': 20, 'high_lvl': 30, 'byte_flag_0': {'byte0_zz1': 1, 'byte0_zz2': 1, 'byte0_zz3': 0, 'byte0_unused4': 0, 'byte0_unused5': 0, 'byte0_unused6': 0, 'byte0_unused7': 0, 'byte0_unused8': 0}, 'byte_flag_1': {'Zombie': 0, 'Fly': 1, 'byte1_zz1': 0, 'Immune NVPlus_Moins': 0, 'Hidden HP': 0, 'Auto-Reflect': 0, 'Auto-Shell': 0, 'Auto-Protect': 0}, 'card': [2, 2, 56], 'devour': [0, 0, 0], 'byte_flag_2': {'IncreaseSurpriseRNG': 0, 'DecreaseSurpriseRNG': 0, 'SurpriseAttackImmunity': 0, 'IncreaseChanceEscape': 1, 'DecreaseChanceEscape': 0, 'byte2_unused_6': 0, 'Diablos-missed': 0, 'Always obtains card': 0}, 'byte_flag_3': {'byte3_zz1': 0, 'byte3_zz2': 1, 'byte3_zz3': 1, 'byte3_zz4': 0, 'byte3_unused_5': 0, 'byte3_unused_6': 0, 'byte3_unused_7': 0, 'byte3_unused_8': 0}, 'extra_xp': 5, 'xp': 15, 'low_lvl_mag': [{'ID': 1, 'value': 0}, {'ID': 50, 'value': 0}, {'ID': 0, 'value': 0}, {'ID': 0, 'value': 0}], 'med_lvl_mag': [{'ID': 2, 'value': 0}, {'ID': 50, 'value': 0}, {'ID': 0, 'value': 0}, {'ID': 0, 'value': 0}], 'high_lvl_mag': [{'ID': 2, 'value': 0}, {'ID': 50, 'value': 0}, {'ID': 0, 'value': 0}, {'ID': 0, 'value': 0}], 'low_lvl_mug': [{'ID': 109, 'value': 2}, {'ID': 109, 'value': 2}, {'ID': 109, 'value': 2}, {'ID': 109, 'value': 2}], 'med_lvl_mug': [{'ID': 110, 'value': 2}, {'ID': 110, 'value': 2}, {'ID': 110, 'value': 2}, {'ID': 110, 'value': 2}], 'high_lvl_mug': [{'ID': 111, 'value': 2}, {'ID': 111, 'value': 2}, {'ID': 111, 'value': 2}, {'ID': 111, 'value': 2}], 'low_lvl_drop': [{'ID': 109, 'value': 1}, {'ID': 109, 'value': 1}, {'ID': 109, 'value': 2}, {'ID': 109, 'value': 2}], 'med_lvl_drop': [{'ID': 109, 'value': 4}, {'ID': 110, 'value': 1}, {'ID': 110, 'value': 2}, {'ID': 110, 'value': 2}], 'high_lvl_drop': [{'ID': 111, 'value': 1}, {'ID': 111, 'value': 1}, {'ID': 111, 'value': 2}, {'ID': 111, 'value': 2}], 'mug_rate': 50.19607843137255, 'drop_rate': 50.19607843137255, 'padding': 0, 'ap': 1, 'renzokuken': [160, 160, 160, 141, 259, 332, 333, 259], 'elem_def': [100, 200, 100, 100, 100, 200, 100, 100], 'status_def': [30, 20, 30, 20, 20, 40, 30, 20, 0, 10, 50, 0, 0, 20, 30, 0, 40, 0, 20, 0]}


        decompiler = AIDecompiler(game_data, battle_text, info_stat_data)
        return decompiler

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        if text is None:
            return ""
        return str(text).upper().replace(' ', '_')

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
                                is_operator = param in ['≠', '==', '≥', '≤', '>', '<', '=', '+', '-', '*', '/', '&&', '||']

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


    def test_stop(self, decompiler):
        bytecode = [0x00]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            stop();
            """
        )
        assert expected == normalized


    def test_print(self, decompiler):
        bytecode = [0x01, 0x01]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            print("Second battle text");
            """
        )
        assert expected == normalized

    def test_print_double_space(self, decompiler):
        bytecode = [0x01, 0x03]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            print("“I'm  done for…”");
            """
        )
        assert expected == normalized


    def test_prepareMagic(self, decompiler):
        """Test decompiling a simple command"""
        # Create prepareMagic(2) command
        bytecode = [3, 2]
        cmd = self.create_test_command(decompiler.game_data, 0, 0x03, [2])

        command_expected = [cmd]
        command_decompiled = decompiler.decompile_bytecode_to_command_list(bytecode)
        assert command_expected == command_decompiled
        code_decompiled = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled simple command ===")
        print(self.pretty_code(code_decompiled))
        print("================================")

        # Check if it contains the expected command
        normalized = self.normalize_code(code_decompiled)
        assert "prepareMagic(FIRA);" in normalized

    def test_target(self, decompiler):
        bytecode = [4, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            target(ZELL);
            """
        )
        assert expected == normalized

    def test_prepareAnim(self, decompiler):
        bytecode = [5, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            prepareAnim(1);
            """
        )
        assert expected == normalized

    def test_usePrepared(self, decompiler):
        bytecode = [6]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            usePrepared();
            """
        )
        assert expected == normalized

    def test_prepareMonsterAbility(self, decompiler):
        bytecode = [7, 3]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            prepareMonsterAbility("Attack (Cronos)");
            """
        )
        assert expected == normalized

    def test_die(self, decompiler):
        bytecode = [8]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            die();
            """
        )
        assert expected == normalized


    def test_anim(self, decompiler):
        bytecode = [9, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            anim(1);
            """
        )
        assert expected == normalized

    def test_useRandom(self, decompiler):
        bytecode = [11, 1, 2, 3]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            useRandom(1,2,3);
            """
        )
        assert expected == normalized

    def test_use(self, decompiler):
        bytecode = [12, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            use(1);
            """
        )
        assert expected == normalized

    def test_unknown13(self, decompiler):
        bytecode = [13, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
             unknown13(1);
            """
        )
        assert expected == normalized


    def test_var(self, decompiler):
        bytecode = [14, 221, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
             var(varB, 10);
            """
        )
        assert expected == normalized


    def test_var_specialCases(self, decompiler):
        bytecode = [14, 221, 203]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
             var(varB, LAST_ATTACKER_SLOT_ID);
            """
        )
        assert expected == normalized

    def test_bvar(self, decompiler):
        bytecode = [15, 96, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            bvar(BattleVar96, 10);
            """
        )
        assert expected == normalized

    def test_gvar(self, decompiler):
        bytecode = [17, 80, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            gvar(GlobalVar80, 10);
            """
        )
        assert expected == normalized


    def test_add(self, decompiler):
        bytecode = [18, 221, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            add(varB, 10);
            """
        )
        assert expected == normalized

    def test_add_specialCases(self, decompiler):
        bytecode = [18, 221, 203]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            add(varB, LAST_ATTACKER_SLOT_ID);
            """
        )
        assert expected == normalized

    def test_badd(self, decompiler):
        bytecode = [19, 96, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            badd(BattleVar96, 10);
            """
        )
        assert expected == normalized

    def test_gadd(self, decompiler):
        bytecode = [21, 80, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            gadd(GlobalVar80, 10);
            """
        )
        assert expected == normalized

    def test_recover(self, decompiler):
        bytecode = [0x16]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            recover();
            """
        )
        assert expected == normalized

    def test_setEscape(self, decompiler):
        # Test both true and false cases
        bytecode_true = [23, 1]
        bytecode_false = [23, 0]

        # Test true case
        code_true = decompiler.decompile(bytecode_true)
        normalized_true = self.normalize_code(code_true)
        expected_true = self.normalize_code(
            """
            setEscape(true);
            """
        )
        assert expected_true in normalized_true

        # Test false case
        code_false = decompiler.decompile(bytecode_false)
        normalized_false = self.normalize_code(code_false)
        expected_false = self.normalize_code(
            """
            setEscape(false);
            """
        )
        assert expected_false in normalized_false

    def test_printSpeed(self, decompiler):
        bytecode = [24, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            printSpeed("Second battle text");
            """
        )
        assert expected == normalized

    def test_doNothing(self, decompiler):
        bytecode = [25, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        # doNothing takes raw int parameters, not symbolic names
        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            doNothing(1);
            """
        )
        assert expected == normalized

    def test_printAndLock(self, decompiler):
        bytecode = [26, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            printAndLock("Second battle text");
            """
        )
        assert expected == normalized

    def test_enterAlt(self, decompiler):
        bytecode = [27, 1, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            enterAlt(1, 0);
            """
        )
        assert expected == normalized

    def test_waitText(self, decompiler):
        bytecode = [28, 2]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            waitText(2);
            """
        )
        assert expected == normalized

    def test_leave(self, decompiler):
        bytecode = [29, 200]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            leave(SELF);
            """
        )
        assert expected == normalized

    def test_specialAction(self, decompiler):
        bytecode = [30, 17]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            specialAction("Elvoret Entrance");
            """
        )
        assert expected == normalized

    def test_enter(self, decompiler):
        bytecode = [31, 3]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            enter(3);
            """
        )
        assert expected == normalized

    def test_waitTextFast(self, decompiler):
        bytecode = [32, 2]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            waitTextFast(2);
            """
        )
        assert expected == normalized

    def test_printAlt(self, decompiler):
        bytecode = [34, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            printAlt("Second battle text");
            """
        )
        assert expected == normalized

    # def test_jump(self, decompiler):
    #     # Test positive jump
    #     bytecode_positive = [35, 10, 0]
    #     code_positive = decompiler.decompile(bytecode_positive)
    #     normalized_positive = self.normalize_code(code_positive)
    #     expected_positive = self.normalize_code(
    #         """
    #         jump(10);
    #         """
    #     )
    #     assert expected_positive in normalized_positive

    def test_jump_negative(self, decompiler):
        # Test negative jump (note: 246, 255 is -10 in signed 16-bit)
        bytecode_negative = [35, 246, 255]
        code_negative = decompiler.decompile(bytecode_negative)
        normalized_negative = self.normalize_code(code_negative)
        expected_negative = self.normalize_code(
            """
            jump(-10);
            """
        )
        assert expected_negative in normalized_negative

    def test_fillAtb(self, decompiler):
        bytecode = [36]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            fillAtb();
            """
        )
        assert expected == normalized

    def test_setScanText(self, decompiler):
        bytecode = [37, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            setScanText("Second battle text");
            """
        )
        assert expected == normalized

    def test_setScanText_255(self, decompiler):
        bytecode = [37, 255]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            setScanText(255);
            """
        )
        assert expected == normalized

    def test_targetStatus(self, decompiler):
        bytecode = [38, 0, 200, 3, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            targetStatus(ENEMY_TEAM, ≠, Poison, False);
            """
        )
        assert expected == normalized

    def test_autoStatus(self, decompiler):
        bytecode = [39, 2, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            autoStatus(ACTIVATE, Petrify);
            """
        )
        assert expected == normalized

    def test_statChange(self, decompiler):
        bytecode = [40, 5, 6]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            statChange(Evade,60%);
            """
        )
        assert expected == normalized

    def test_draw(self, decompiler):
        bytecode = [41]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            draw();
            """
        )
        assert expected == normalized

    def test_cast(self, decompiler):
        bytecode = [42]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            cast();
            """
        )
        assert expected == normalized

    def test_targetAllySlot(self, decompiler):
        bytecode = [43, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            targetAllySlot(1);
            """
        )
        assert expected == normalized

    def test_remain(self, decompiler):
        bytecode = [44]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            remain();
            """
        )
        assert expected == normalized

    def test_elemDmgMod(self, decompiler):
        bytecode = [45, 2, 100, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            elemDmgMod(Thunder, 800%);
            """
        )
        assert expected == normalized

    def test_elemDmgMod2Bytes(self, decompiler):
        bytecode = [45, 3, 132, 3]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            elemDmgMod(EARTH, 0%);
            """
        )
        assert expected == normalized

    def test_blowAway(self, decompiler):
        bytecode = [46]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            blowAway();
            """
        )
        assert expected == normalized

    def test_targetable(self, decompiler):
        bytecode = [47]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            targetable();
            """
        )
        assert expected == normalized

    def test_untargetable(self, decompiler):
        bytecode = [48]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            untargetable();
            """
        )
        assert expected == normalized

    def test_giveGF(self, decompiler):
        bytecode = [49, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            giveGF(Shiva);
            """
        )
        assert expected == normalized

    def test_prepareSummon(self, decompiler):
        bytecode = [50]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            prepareSummon();
            """
        )
        assert expected == normalized

    def test_activate(self, decompiler):
        bytecode = [51]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            activate();
            """
        )
        assert expected == normalized

    def test_enable(self, decompiler):
        bytecode = [52, 1]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            enable(1);
            """
        )
        assert expected == normalized

    def test_loadAndTargetable(self, decompiler):
        bytecode = [53, 209]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            loadAndTargetable(LAST_ENABLED_MONSTER);
            """
        )
        assert expected == normalized

    def test_gilgamesh(self, decompiler):
        bytecode = [54]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            gilgamesh();
            """
        )
        assert expected == normalized

    def test_giveCard(self, decompiler):
        bytecode = [55, 2]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            giveCard("Bite Bug");
            """
        )
        assert expected == normalized

    def test_giveItem(self, decompiler):
        bytecode = [56, 2]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            giveItem("Potion+");
            """
        )
        assert expected == normalized

    def test_gameOver(self, decompiler):
        bytecode = [57]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            gameOver();
            """
        )
        assert expected == normalized

    def test_targetableSlot(self, decompiler):
        bytecode = [58, 2]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            targetableSlot(2);
            """
        )
        assert expected == normalized

    def test_assignSlot(self, decompiler):
        bytecode = [59, 2, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            assignSlot(2, FIRST_SLOT_AVAILABLE);
            """
        )
        assert expected == normalized

    def test_addMaxHP(self, decompiler):
        bytecode = [60, 10]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            addMaxHP(10);
            """
        )
        assert expected == normalized

    def test_proofOfOmega(self, decompiler):
        bytecode = [61]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            proofOfOmega();
            """
        )
        assert expected == normalized

    def test_decompile_multiple_commands(self, decompiler):
        """Test decompiling multiple commands"""
        # Create commands: prepareMagic(1); attack(); die();
        bytecode = [3, 1, 0, 8]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("=====================================")

        normalized = self.normalize_code(code)
        assert "prepareMagic(FIRE);" in normalized
        assert "stop" in normalized
        assert "die" in normalized

    def test_if_hp_specific_target(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 0, 200, 3, 5, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(HP,SELF, ≠, 50%)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_hp_generic_target(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 1, 200, 1, 5, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(HP_IN,enemy_team, <, 50%)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_rand(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 2, 3, 0, 0, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(RANDOM, 3, ⩵, 0)
            {
                stop();
            }
            """
        )
        assert expected == normalized




    def test_if_combat_scene(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 3, 0, 0, 0, 4, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ENCOUNTER_ID, ⩵, 1024)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_status_specific_target(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 4, 203, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(STATUS, LAST_ATTACKER, ⩵, PETRIFY)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_status_generic_target(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 5, 200, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(STATUS_IN, ENEMY_TEAM, ⩵, PETRIFY)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_number_member(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 6, 200, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(NB_ALIVE_IN, ENEMY_TEAM, ⩵, 2)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_level_check(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 7, 220, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(LEVEL, VARA_SLOT_ID, ⩵, 2)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_dead(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 8, 0, 0, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(DEAD, ⩵, ZELL)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_alive(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 9, 0, 0, 0, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ALIVE, ⩵, SQUALL)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_last_attack_damage_type(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 0, 0, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ACTION_DAMAGE_TYPE, ⩵, MAGICAL)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_last_attacker(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 1, 0, 222, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ATTACKER, ⩵, VARC_SLOT_ID)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_turn_counter(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 2, 0, 5, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, SELF_TURN_COUNTER, ⩵, 5)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_last_attacker_command_type(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 3, 0, 17, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ACTION_COMMAND, ⩵, NO_MERCY)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_last_action_launch(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 4, 0, 17, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ACTION_ID, ⩵, 17)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_attacker_last_attack_element(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 5, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ACTION_ELEMENT, ⩵, THUNDER)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_attacker_last_attacker_com_id(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 10, 203, 0, 200, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ATTACKER, LAST_ATTACKER_COM_ID, ⩵, SELF)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_group_level(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 14, 200, 5, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(DIFFICULTY, ≥, 1)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_alive_in_slot(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 15, 200, 0, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(ALIVE_IN_SLOT, ⩵, 1)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_gender_check(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 16, 0, 0, 202, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(GENDER_IN_TEAM, ⩵, MALE)
            {
                stop();
            }
            """
        )
        assert expected == normalized


    def test_if_gforce_obtained(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 17, 200, 0, 204, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(GFORCE_DRAWABLE, ⩵)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_special_byte_check(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 18, 2, 0, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(SPECIAL_BYTE_CHECK, ⩵, ODIN_POSSESS)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_countdown(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 19, 2, 0, 1, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(COUNTDOWN, ⩵)
            {
                stop();
            }
            """
        )
        assert expected == normalized

    def test_if_status_all_in_team(self, decompiler):
        """Test decompiling if statement"""
        bytecode = [2, 20, 200, 0, 2, 0, 4, 0, 0, 35, 0, 0]
        code = decompiler.decompile(bytecode)

        print(f"\n=== Decompiled ===")
        print(self.pretty_code(code))
        print("===============================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(STATUS_OF_ALL_IN, ENEMY_TEAM, ⩵, PETRIFY)
            {
                stop();
            }
            """
        )
        assert expected == normalized


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
        expected = self.normalize_code(
            """
            if(HP_IN, IRVINE, ≠, 20%)
            {
                die();
            }
            else
            {
                statChange(SPEED,50%);
            }
            """
        )
        assert expected == normalized

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
            if(HP_IN,IRVINE,≠,20%)
            {
                die();
            }
            else
            {
                stop();
                if(HP_IN,IRVINE,≠,20%)
                {
                    statChange(SPEED,50%);
                }
            }
            """
        )
        assert expected == normalized

    def test_decompile_if_elseif_else_statement(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = [2, 1, 2, 3, 2, 0, 4, 0, 8, 35, 17, 0, 2, 1, 2, 3, 1, 0, 6, 0, 40, 3, 2, 35, 3, 0, 40, 4, 5]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if-elseif-else statement ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(HP_IN,IRVINE,≠,20%)
            {
                die();
            }
            elseif(HP_IN,IRVINE,≠,10%)
            {
                statChange(SPIRIT,20%);
            }
            else
            {
                statChange(SPEED,50%);
            }
            """
        )
        assert expected == normalized


    def test_if_elseif2_else(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode =  [
            2, 1, 200, 3, 4, 0, 4, 0,
            8,
            35, 27, 0,
            2, 220, 200, 0, 0, 0, 4, 0,
            8,
            35, 15, 0,
            2, 220, 200, 0, 1, 0, 4, 0,
            0,
            35, 3, 0,
            40, 5, 6]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if-elseif-else statement ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(HP_IN,ENEMY_TEAM, ≠, 40%)
            {
                die();
            }
            elseif(VARA,SELF, ⩵, 0)
            {
                die();
            }
            elseif(VARA,SELF, ⩵, 1)
            {
                stop();
            }
            else
            {
               statChange(EVADE,60%); 
            }
            """
        )
        assert expected == normalized

    def test_com1(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode =  [
            2, 4, 200, 0, 24, 0, 9, 0,
            40, 0, 20,
            40, 2, 20,
            35, 6, 0,
            40, 0, 10,
            40, 2, 10,
            0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if com1 ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(STATUS,SELF,⩵,AURA)
            {
                statChange(STRENGTH,200%);
                statChange(MAGIC,200%);
            }
            else
            {
                statChange(STRENGTH,100%);
                statChange(MAGIC,100%); 
            }
            stop();
            """
        )
        assert expected == normalized

    def test_com10_little(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = \
                [2, 2, 2, 0, 0, 0, 36, 0,
                2, 5, 200, 0, 35, 0, 19, 0,
                2, 2, 10, 4, 4, 0, 8, 0,
                38, 0, 200, 0, 35,
                35, 0, 0,
                35, 0, 0,
                14, 220, 1,
                12, 0,
                0,
                35, 0, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if com10 little ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(RANDOM,2,⩵,0)
            {
                if(STATUS_IN,ENEMY_TEAM,⩵,DEFEND)
                {
                    if(RANDOM,10, ≤, 4)
                    {
                        targetStatus(ENEMY_TEAM,⩵,DEFEND,False);
                    }
                }
                var(varA,1);
                use(0);
                stop();
            }
            """
        )
        assert expected == normalized

    def test_com15_init(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = [14, 220, 0, 14, 221, 0, 2, 3, 0, 5, 58, 0, 28, 0, 2, 3, 0, 4, 60, 0, 17, 0, 2, 7, 200, 1, 10, 0, 6, 0, 14, 222, 1, 35, 0, 0, 35, 0, 0, 35, 0, 0, 0, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if com15 init ===")
        print(self.pretty_code(code))
        print("==================================")

        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            var(varA,0);
            var(varB,0);
            if(ENCOUNTER_ID,≥,58)
            {
                if(ENCOUNTER_ID,≤,60)
                {
                    if(LEVEL,SELF, <, 10)
                    {
                        var(varC,1);
                    }
                }
            }
            stop();
            stop();
            """
        )
        assert expected == normalized

    def test_com10_full(self, decompiler):
        """Test decompiling if-else statement"""
        bytecode = [2, 14, 200, 0, 0, 0, 6, 0, 40, 2, 5, 35, 0, 0, 2, 2, 4, 0, 0, 0, 4, 0, 0, 35, 0, 0, 2, 4, 200, 0, 30, 0, 8, 0, 4, 207, 12, 0, 0, 35, 0, 0, 2, 221, 200, 5, 4, 0, 14, 0, 4, 222, 40, 2, 10, 12, 4, 14, 221, 0, 0, 35, 0, 0, 4, 201, 2, 2, 2, 0, 0, 0, 36, 0, 2, 5, 200, 0, 35, 0, 19, 0, 2, 2, 10, 4, 4, 0, 8, 0, 38, 0, 200, 0, 35, 35, 0, 0, 35, 0, 0, 14, 220, 1, 12, 0, 0, 35, 0, 0, 14, 220, 2, 2, 2, 2, 0, 0, 0, 6, 0, 12, 1, 0, 35, 0, 0, 12, 2, 0, 0, 0]
        code = decompiler.decompile(bytecode)
        print(f"\n=== Decompiled if com10 full ===")
        print(self.pretty_code(code))
        print("==================================")
        print(code)
        normalized = self.normalize_code(code)
        expected = self.normalize_code(
            """
            if(DIFFICULTY,⩵,0)
            {
                statChange(MAGIC,50%);
            }
            if(RANDOM,4,⩵,0)
            {
                stop();
            }
            if(STATUS,SELF,⩵,CONFUSE)
            {
                target(RANDOM_NONSELF_ALLY);
                use(0);
                stop();
            }
            if(VARB,SELF,≥,4)
            {
                target(VARC_MASK);
                statChange(MAGIC,100%);
                use(4);
                var(varB,0);
                stop();
            }
            target(RANDOM_ENEMY);
            if(RANDOM,2,⩵,0)
            {
                if(STATUS_IN,ENEMY_TEAM,⩵,DEFEND)
                {
                    if(RANDOM,10, ≤, 4)
                    {
                        targetStatus(ENEMY_TEAM,⩵,DEFEND,False);
                    }
                }
                var(varA,1);
                use(0);
                stop();
            }
            var(varA,2);
            if(RANDOM,2,⩵,0)
            {
                use(1);
                stop();
            }
            use(2);
            stop();
            stop();
            stop();

            """
        )
        assert expected == normalized

    def test_compute_indent_bracket(self, decompiler):
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

        indented = decompiler.compute_indent_bracket(func_list)

        print(f"\n=== Indented list ===")
        for line in indented:
            print(line)
        print("=====================")

        # Check indentation
        assert indented[0] == "if (1,2,3,4)"  # No indent
        assert indented[1] == "{"
        assert indented[2] == "    die();"  # 4 spaces indent
        assert indented[3] == "}"  # Back to no indent
        assert indented[4] == "else"  # No indent
        assert indented[5] == "{"
        assert indented[6] == "    stop();"  # 4 spaces indent
        assert indented[7] == "}"  # Back to no indent

    def test_empty_command_list(self, decompiler):
        """Test decompiling empty command list"""
        command_list = []
        code = decompiler.decompile_from_command_list(command_list)

        assert code == "" or code is None or code == "\n"

    def test_single_command_no_params(self, decompiler):
        """Test decompiling single command without parameters"""
        cmd = self.create_test_command(decompiler.game_data, 0, 0x00, [])  # stop()

        command_list = [cmd]
        code = decompiler.decompile_from_command_list(command_list)

        normalized = self.normalize_code(code)
        assert "stop();" in normalized


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x", "--tb=short"])
    # pytest.main(["-v", "-x", "-s", "--tb=short", __file__]) # Capture all print
