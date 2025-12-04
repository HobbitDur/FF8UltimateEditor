import re
from typing import List

from FF8GameData.dat.commandanalyser import CommandAnalyser
from FF8GameData.gamedata import GameData


class AIDecompiler:
    @staticmethod
    def decompile_from_command_list(game_data: GameData, command_list: List[CommandAnalyser]):
        func_list = []
        if_list_count = []
        else_list_count = []

        for command in command_list:
            last_else = False
            just_finished_if = False
            for i in range(len(if_list_count)):
                if_list_count[i] -= command.get_size()
                if if_list_count[i] == 0:
                    func_list.append('}')
                    just_finished_if = True
            for i in range(len(else_list_count)):
                if else_list_count[i] == 0:
                    func_list.append('}')
            while 0 in else_list_count:
                else_list_count.remove(0)
            while 0 in if_list_count:
                if_list_count.remove(0)
            op_info = [x for x in game_data.ai_data_json['op_code_info'] if x["op_code"] == command.get_id()][0]
            if command.get_id() == 2:  # IF
                op_list = command.get_op_code()
                jump_value = int.from_bytes(bytearray([op_list[5], op_list[6]]), byteorder='little')
                if_list_count.append(jump_value)
                func_line_text = op_info['func_name']
                func_line_text += command.get_text(for_decompiled=True)
                # func_line_text += "//" + command_text
                func_list.append(func_line_text)
                func_list.append('{')
            elif command.get_id() == 35:
                op_list = command.get_op_code()
                jump_value = int.from_bytes(bytearray([op_list[0], op_list[1]]), byteorder='little')
                if jump_value & 0x8000 != 0:  # Jump backward so we don't add anything related to else, just a jump backward for the moment
                    func_line_text = op_info['func_name']
                    func_line_text += command.get_text(for_decompiled=True)
                    func_list.append(func_line_text)
                elif jump_value >= 0 and not just_finished_if:  # It's an independant jump
                    last_else = True
                    else_list_count.append(jump_value)  # Adding the else size himself
                    func_list.append("else")
                    func_list.append('{')
                elif jump_value > 0:  # We don't add the endif
                    last_else = True
                    else_list_count.append(jump_value)  # Adding the else size himself
                    func_list.append("else")
                    func_list.append('{')
            else:
                func_line_text = op_info['func_name']
                func_line_text += command.get_text(for_decompiled=True) + ";"
                func_list.append(func_line_text)
            # The else are closing after the function (you don't count the jump contrary to an if)
            for i in range(len(else_list_count)):
                if i == len(else_list_count) - 1 and last_else:  # Don't update the else we just added with his own size !
                    continue
                else_list_count[i] -= command.get_size()

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
