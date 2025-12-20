import re
from typing import List

from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIDecompilerTypeResolver import AIDecompilerTypeResolver


class AIDecompiler:
    def __init__(self, game_data: GameData, battle_text=(), info_stat={}):
        self.game_data = game_data
        self.battle_text = battle_text
        self.info_stat = info_stat
        self.type_resolver = AIDecompilerTypeResolver(game_data, battle_text, info_stat)

    def decompile(self, bytecode: List[int]):
        print("decompile")
        command_list = self.decompile_bytecode_to_command_list(bytecode)
        print("command_list")
        print(command_list)
        self.type_resolver.resolve(command_list)
        print("command_list_typed")
        print(command_list)
        code = self.decompile_from_command_list(command_list)
        print(code)
        return code

    def decompile_bytecode_to_command_list(self, code: List[int]):
        print("_get_command_list_from_ai_bytes_section")
        current_if_type = CurrentIfType.NONE
        index_read = 0
        list_result = []
        while index_read < len(code):
            all_op_code_info = self.game_data.ai_data_json["op_code_info"]
            op_code_ref = [x for x in all_op_code_info if x["op_code"] == code[index_read]]
            if not op_code_ref and code[index_read] >= 0x40:
                index_read += 1
                continue
            elif op_code_ref:  # >0x40 not used
                op_code_ref = op_code_ref[0]
                start_param = index_read + 1
                end_param = index_read + 1 + op_code_ref['size']
                command = CommandAnalyser(code[index_read], code[start_param:end_param], game_data=self.game_data,
                                          battle_text=self.battle_text,
                                          info_stat_data=self.info_stat, color=self.game_data.AIData.COLOR, current_if_type=current_if_type, line_index=len(list_result))
                current_if_type = command.get_current_if_type()
                list_result.append(command)
                index_read += 1 + op_code_ref['size']
        print(list_result)
        return list_result

    def decompile_from_command_list(self, command_list: List[CommandAnalyser]):
        print("decompile_from_command_list")
        func_list = []
        if_list_count = []
        else_list_count = []
        pending_elseif = False  # Track if we're expecting an elseif

        for command_index, command in enumerate(command_list):
            last_else = False

            # Update block counters
            for i in range(len(if_list_count)):
                if_list_count[i] -= command.get_size()
                if if_list_count[i] == 0:
                    func_list.append('}')

            for i in range(len(else_list_count)):
                else_list_count[i] -= command.get_size()
                if else_list_count[i] == 0:
                    func_list.append('}')
            # Remove completed blocks
            while 0 in else_list_count:
                else_list_count.remove(0)
            while 0 in if_list_count:
                if_list_count.remove(0)

            op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == command.get_id()][0]

            if command.get_id() == 2:  # IF
                op_list = command.get_op_code()
                jump_value = int.from_bytes(bytearray([op_list[5], op_list[6]]), byteorder='little')

                # Check if this is an elseif (IF after a JUMP that created an else)
                if pending_elseif:
                    # This IF is actually an elseif
                    if_list_count.append(jump_value)
                    func_line_text = 'elseif'
                    func_line_text += command.get_param_text()
                    func_list.append(func_line_text)
                    func_list.append('{')
                    pending_elseif = False
                else:
                    # Regular IF
                    if_list_count.append(jump_value)
                    func_line_text = "if"
                    func_line_text += command.get_param_text()
                    func_list.append(func_line_text)
                    func_list.append('{')

            elif command.get_id() == 35:  # JUMP
                op_list = command.get_op_code()
                jump_value = int.from_bytes(bytearray([op_list[0], op_list[1]]), byteorder='little')

                if jump_value & 0x8000 != 0:  # Jump backward (loop)
                    func_line_text = op_info['func_name']
                    func_line_text += command.get_param_text()
                    func_list.append(func_line_text)

                elif jump_value > 0:
                    # Check if next command is an IF (would be elseif)
                    if (command_index + 1 < len(command_list) and
                            command_list[command_index + 1].get_id() == 2):
                        # This JUMP + next IF = elseif
                        # Don't output "else" now, just mark that we expect an elseif
                        pending_elseif = True
                        # Still need to track the else block size for the jump
                        else_list_count.append(jump_value - 3)  # Don't count JUMP itself
                    else:
                        # Regular else
                        last_else = True
                        else_list_count.append(jump_value - 3)  # Don't count JUMP itself
                        func_list.append("else")
                        func_list.append('{')

                else:  # jump_value == 0
                    # Empty jump (no else)
                    pass

            else:
                func_line_text = op_info['func_name']
                func_line_text += command.get_param_text()
                func_list.append(func_line_text)

            # Update else counters (skip the newly added else)
            for i in range(len(else_list_count)):
                if i == len(else_list_count) - 1 and last_else:
                    continue
                else_list_count[i] -= command.get_size()

        # Close any remaining blocks
        for _ in range(len(if_list_count)):
            func_list.append('}')
        for _ in range(len(else_list_count)):
            func_list.append('}')

        func_list = AIDecompiler.compute_indent_bracket(func_list)
        code_text = ""
        for func_name in func_list:
            code_text += func_name
            code_text += '<br/>'
        return code_text

    @staticmethod
    def compute_indent_bracket(func_list: List):
        indent = 0
        new_text = ""
        indent_text = "&nbsp;" * 4
        for i in range(len(func_list)):
            command_without_space = func_list[i].replace(' ', '')
            if command_without_space == '}':
                indent -= 1
            func_list[i] = indent_text * indent + func_list[i]
            if command_without_space == '{':
                indent += 1
            new_text += func_list[i] + "<br/>"
        return func_list

    @staticmethod
    def format_c_style_indentation(html_text):
        """
        Comprehensive C-style formatting that properly handles elseif: statements.
        """
        # Step 1: Completely remove all existing indentation
        cleaned_text = re.sub(r'(&nbsp;)+', '', html_text)  # Remove all &nbsp;
        cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)  # Normalize spaces
        cleaned_text = re.sub(r'\s+<br/>\s+', '<br/>', cleaned_text)  # Clean around <br/>

        lines = cleaned_text.split('<br/>')
        formatted_lines = []
        indent_level = 0

        i = 0
        while i < len(lines):
            original_line = lines[i].strip()

            if not original_line:
                formatted_lines.append('')
                i += 1
                continue

            # Remove any remaining whitespace
            line = original_line.strip()

            # Check line type
            is_elseif = line.startswith('elseif:')
            is_control = line.startswith(('if:', 'elseif:', 'jump:'))

            # Count braces in this exact line
            open_braces = line.count('{')
            close_braces = line.count('}')

            # Calculate current indentation level
            current_indent = max(0, indent_level - close_braces)
            indent = "&nbsp;" * (4 * current_indent)

            # Format the line with proper indentation
            formatted_line = indent + line
            formatted_lines.append(formatted_line)

            # Update indent level for next lines
            indent_level = current_indent + open_braces

            i += 1

        transformed_text = '<br/>'.join(formatted_lines)
        return transformed_text
