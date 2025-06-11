from typing import List
import re

from FF8GameData.dat.commandanalyser import CommandAnalyser, CurrentIfType
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData


class CodeAnalyseTool:
    def __init__(self):
        self.counter = 0

    @classmethod
    def searching_if(cls, lines: List[str], if_func_name: str, else_func_name: str):
        # Now searching for IF in the section
        index_start_if = -1
        index_end_if = -1
        func_found = None
        for i in range(len(lines)):
            if if_func_name + ":" in lines[i].replace(' ', '') or (else_func_name + ":" in lines[i].replace(' ', '') and CodeAnalyser.ELSE_TEXT in (lines[i].replace(' ', '')).upper()):  # New if found or else found
                if if_func_name + ":" in lines[i].replace(' ', ''):
                    func_found = if_func_name
                else:
                    func_found = else_func_name
                index_start_if = i
                # Now searching the end
                # Searching the closing bracket of this if. If there is other open bracket, it means we need to search one more close bracket for this if.
                number_close_bracket_to_search = 0
                for j in range(i + 1, len(lines)):
                    if lines[j].replace(' ', '') == '{':
                        number_close_bracket_to_search += 1
                    elif lines[j].replace(' ', '') == '}':
                        number_close_bracket_to_search -= 1
                    if number_close_bracket_to_search == 0:
                        index_end_if = j
                        break
                break

        return index_start_if, index_end_if, func_found

    @classmethod
    def analyse_lines(cls, section_lines: List[str], game_data: GameData, enemy_data: MonsterAnalyser):
        command_list = []
        for i in range(len(section_lines)):
            new_code_line = CodeLine(game_data, enemy_data, section_lines[i], i)
            if new_code_line:
                command_list.append(new_code_line.get_command())
        return command_list

    @classmethod
    def analyse_loop(cls, section_lines: List[str], if_func_name: str, else_func_name: str, game_data: GameData, enemy_data: MonsterAnalyser):
        command_list = []
        last_line = 0
        while True:
            command_list_temp, if_index, round_last_line = CodeAnalyseTool().analyse_one_round(section_lines[last_line:], if_func_name, else_func_name,
                                                                                               game_data, enemy_data)
            last_line += round_last_line
            command_list.extend(command_list_temp)
            last_line += 1  # We analyze the line after the last one analysed, logic no ?
            if if_index < 0 or last_line == len(section_lines):
                break
        return command_list

    @classmethod
    def analyse_one_round(cls, section_lines: List[str], if_func_name: str, else_func_name: str, game_data: GameData, enemy_data: MonsterAnalyser):
        # Searching for IF in the section
        if_start_index, if_end_index, func_found = CodeAnalyseTool.searching_if(section_lines, if_func_name, else_func_name)
        if if_start_index == -1:  # Didn't find any if, we analyse till the end:
            end_analyse_line = len(section_lines) - 1
            last_line = end_analyse_line
        else:
            end_analyse_line = if_start_index - 1
            last_line = end_analyse_line
        # Analysing all normal command before the if (till the end if no one found)
        command_list = []
        if if_start_index != 0:  # If the if is the first of the section, then we don't have to analyse anything
            command_list = CodeAnalyseTool.analyse_lines(section_lines[:end_analyse_line + 1], game_data, enemy_data)
        # Analysing the if section if found one
        if if_start_index != -1:
            if func_found == if_func_name:
                if len(section_lines) > if_end_index + 1:
                    next_line = section_lines[if_end_index + 1]
                else:
                    next_line = ""

                section_command_list = CodeIfSection(game_data, enemy_data, section_lines[if_start_index: if_end_index + 1], if_start_index, next_line)
            elif func_found == else_func_name:
                section_command_list = CodeElseSection(game_data, enemy_data, section_lines[if_start_index: if_end_index + 1], if_start_index)
            else:
                print(f"Unexpected func found: {func_found}")
                section_command_list = None
            command_list.extend(section_command_list.get_command())
            last_line += section_command_list.get_nb_line()
        return command_list, if_start_index, last_line


class CodeLine:
    def __init__(self, game_data: GameData, enemy_data: MonsterAnalyser, code_text_line: str, line_index: int):
        self._code_text_line = code_text_line
        self._line_index = line_index
        self.game_data = game_data
        self.enemy_data = enemy_data
        self._command = None
        self._analyse_line()

    def _analyse_line(self):
        replaced_line = self._code_text_line.replace(' ', '')
        replaced_line = replaced_line.replace('\t', '')
        if replaced_line in ('{', '}'):
            print(f"Unexpected {{ or }}: {replaced_line}")
            return
        elif replaced_line == "":
            print(f"Unexpected empty line")
            return
        code_split = self._code_text_line.split(':', 1)
        func_name = code_split[0].replace(' ', '')
        func_name = func_name.replace('\t', '')
        op_code_list = re.findall(rf"{re.escape(CommandAnalyser.PARAM_CHAR_LEFT)}(.*?){re.escape(CommandAnalyser.PARAM_CHAR_RIGHT)}", code_split[1])
        op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["func_name"] == func_name]
        if op_info:
            op_info = op_info[0]
        else:
            print(f"Didn't find func name: {func_name}, assuming stop")
            op_info = self.game_data.ai_data_json['op_code_info'][0]

        # Adding missing param when needed
        if op_info['size'] != len(op_code_list):
            if op_info['op_code'] == 2 and len(op_code_list) != 7:  # IF
                op_code_original_str_list = op_code_list.copy()
                op_code_list = []
                # If it's var subject, we don't need a subject id.
                if len(op_code_original_str_list) == 4:
                    var_found = [x for x in self.game_data.ai_data_json['list_var'] if x['var_name'] == op_code_original_str_list[0]]
                    if var_found:
                        op_code_original_str_list.insert(0, str(var_found[0]['op_code']))

                # Subject ID (0)
                subject_id = int(op_code_original_str_list[0])
                op_code_list.append(subject_id)
                if subject_id <= 20:
                    subject_id_info = [x for x in self.game_data.ai_data_json['if_subject'] if x['subject_id'] == subject_id][0]
                else:
                    subject_id_info = {"subject_id": subject_id, "short_text": "VAR Subject",  # For a var, subject ID need to be 200 for local var
                                       "left_text": '{}', "complexity": "simple", "param_left_type": "const", "right_text": '{}',
                                       "param_right_type": "int", "param_list": [200]}
                # Left condition (1)
                # First add the left param if needed
                if '{}' not in subject_id_info['left_text']:
                    if subject_id_info['param_left_type'] == "const":
                        op_code_original_str_list.insert(1, str(subject_id_info['param_list'][0]))

                        op_code_original_str_list[1] = str( subject_id_info['param_list'][0])
                    elif subject_id_info['param_left_type'] == "":
                        op_code_original_str_list.insert(1, str(0))  # Unused
                    elif subject_id_info['param_left_type'] == "subject10":
                        pass  # It's a param on itself
                    else:
                        print(f"Unexpected param_left_type for analyse line: {subject_id_info['param_left_type']}")
                elif subject_id_info['param_left_type'] == "int_right" and subject_id_info['param_right_type'] == "alive":
                    alive_left_value = str(op_code_original_str_list[1])
                op_code_list.append(op_code_original_str_list[1])
                # Comparison (2)
                op_code_list.append(op_code_original_str_list[2])

                # Right condition (3 and 4)

                if subject_id_info['right_text'] != "{}" and subject_id_info['right_text'] != "":
                    if subject_id_info['param_right_type'] == "const":
                        op_code_original_str_list.insert(3, str(subject_id_info['param_list'][1]))
                    elif subject_id_info['param_left_type'] == "int_right" and subject_id_info['param_right_type'] == "alive":
                        op_code_original_str_list.insert(3, alive_left_value)
                    else:
                        print(f"Unexpected param_right_type for analyse line: {subject_id_info['param_right_type']}")
                # Right param takes 2 bytes, but we gives only one parameters so we add an empty one
                op_code_list.append(op_code_original_str_list[3])
                op_code_list.append(0)

                # Expanding jump (5 and 6)
                jump_2_byte = int(op_code_original_str_list[4]).to_bytes(byteorder="little", length=2)
                op_code_list.append(int.from_bytes([jump_2_byte[0]]))
                op_code_list.append(int.from_bytes([jump_2_byte[1]]))


            elif op_info['op_code'] == 35 and len(op_code_list) in (0, 1):
                if len(op_code_list) == 0:  # ENDIF
                    op_code_list = [0, 0]  # Endif is a jump to 0
                else:  # Expanding jump
                    jump_value = int(op_code_list[0])
                    if jump_value < 0:
                        jump_value = CommandAnalyser.twos_complement_opposite_16bit(jump_value)
                    jump_2_byte = jump_value.to_bytes(byteorder="little", length=2)
                    byte1 = int.from_bytes([jump_2_byte[0]])
                    byte2 = int.from_bytes([jump_2_byte[1]])
                    op_code_list = [byte1, byte2]
            elif op_info['op_code'] == 45 and len(op_code_list) == 2:
                target = 900 - int(op_code_list[1])
                low_byte = target // 256
                high_byte = target - (low_byte * 256)
                op_code_list[1] = high_byte
                op_code_list.append(low_byte)
            else:
                print(
                    f"When analysing command, wrong size of parameter ({len(op_code_list)} instead of {op_info['size']}) with op id unexpected {op_info['op_code']}")
        # Putting the parameters in the correct order (if not done previously)
        else:
            original_op_list = op_code_list.copy()
            for i, param_index in enumerate(op_info['param_index']):
                op_code_list[param_index] = original_op_list[i]

        self._command = CommandAnalyser(op_id=op_info['op_code'], op_code=op_code_list, game_data=self.game_data, battle_text=self.enemy_data.battle_script_data['battle_text'],
                                        info_stat_data=self.enemy_data.info_stat_data,
                                        line_index=self._line_index, text_param=True)

    def get_command(self):
        return self._command


class CodeIfSection:
    def __init__(self, game_data: GameData, enemy_data, section_lines, line_index, next_line: str):
        self._section_lines = section_lines
        self._line_index = line_index
        self.game_data = game_data
        self.enemy_data = enemy_data
        self._command_list = []
        self._section_size = 0
        self._next_line = next_line
        self._connected_else = False
        self.analyse_section()

    def analyse_section(self):
        # First remove first bracket and last bracket
        next_line_to_start = 1  # Starting after the IF
        end_line = len(self._section_lines)
        if self._section_lines[1].replace(' ', '') == '{':
            next_line_to_start += 1
        else:
            print(f"Not a bracket following if: {self._section_lines[1]}")
        if self._section_lines[-1].replace(' ', '') == '}':
            end_line -= 1
        else:
            print(f"Not a bracket ending if: {self._section_lines[-1]}")
        # Checking the section is correct
        ## Size should be at least 2
        if len(self._section_lines) < 2:
            print(f"Section too short, should be at least 2, but it's {len(self._section_lines)} lines")
        ## IF first line is an IF
        op_if_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 2][0]
        op_else_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 35][0]
        if op_if_info['func_name'] not in self._section_lines[0]:
            print(f"Unexpected first line of if section: {self._section_lines[0]}")
        # Analysing the content of the IF
        self._command_list = CodeAnalyseTool.analyse_loop(self._section_lines[next_line_to_start:end_line], op_if_info['func_name'], op_else_info['func_name'],
                                                          self.game_data, self.enemy_data)
        # Adding an endif to the if only if next is not an else
        else_name = op_else_info['func_name'] + ":"

        if not else_name in self._next_line: # Endif
            end_command = CommandAnalyser(op_id=35, op_code=[0, 0], game_data=self.game_data, battle_text=self.enemy_data.battle_script_data['battle_text'],
                                          info_stat_data=self.enemy_data.info_stat_data,
                                          line_index=self._line_index + len(self._section_lines) - 1)
            self._command_list.append(end_command)
        else:
            # As we don't add the ENDIF here, but still need to jump over the jump func, we add the 3 size
            self._connected_else = True
        # Now we can insert on first line the complete if
        if_command = CodeLine(game_data=self.game_data, enemy_data=self.enemy_data,
                              code_text_line=self._section_lines[0] + f"{CommandAnalyser.PARAM_CHAR_LEFT}{self.get_size()}{CommandAnalyser.PARAM_CHAR_RIGHT}",
                              line_index=self._line_index)
        self._command_list.insert(0, if_command.get_command())

    def get_command(self):
        return self._command_list

    def get_nb_line(self):
        return len(self._section_lines)

    def get_size(self):
        size = 0
        for command in self._command_list:
            if command:
                size += command.get_size()
        if self._connected_else:
            size += 3
        return size


class CodeElseSection:
    def __init__(self, game_data: GameData, enemy_data, section_lines, line_index):
        self._section_lines = section_lines
        self._line_index = line_index
        self.game_data = game_data
        self.enemy_data = enemy_data
        self._command_list = []
        self._section_size = 0
        self.analyse_section()

    def analyse_section(self):
        if len(self._section_lines) <= 1:
            return
        # First remove first bracket and last bracket
        next_line_to_start = 1  # Starting after the IF
        end_line = len(self._section_lines)
        if self._section_lines[1].replace(' ', '') == '{':
            next_line_to_start += 1
        else:
            print(f"Not a bracket following if: {self._section_lines[1]}")
        if self._section_lines[-1].replace(' ', '') == '}':
            end_line -= 1
        else:
            print(f"Not a bracket ending if: {self._section_lines[-1]}")
        # Checking the section is correct
        ## If first line is an else
        op_if_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 2][0]
        op_else_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 35][0]
        if op_else_info['func_name'] not in self._section_lines[0]:
            print(f"Unexpected first line of else section: {self._section_lines[0]}")

        # Analysing the content of the IF
        self._command_list = CodeAnalyseTool.analyse_loop(self._section_lines[next_line_to_start:end_line], op_if_info['func_name'], op_else_info['func_name'],
                                                          self.game_data, self.enemy_data)
        # Compute size of else
        else_command = CodeLine(game_data=self.game_data, enemy_data=self.enemy_data,
                                code_text_line=self._section_lines[0] + f"{CommandAnalyser.PARAM_CHAR_LEFT}{self.get_size()}{CommandAnalyser.PARAM_CHAR_RIGHT}",
                                line_index=self._line_index)
        self._command_list.insert(0, else_command.get_command())

    def get_command(self):
        return self._command_list

    def get_nb_line(self):
        return len(self._section_lines)

    def get_size(self):
        size = 0
        for command in self._command_list:
            size += command.get_size()
        return size


class CodeAnalyser:
    ELSE_TEXT = 'ELSE'
    def __init__(self, game_data: GameData, enemy_data: MonsterAnalyser, code_text_split):
        self.game_data = game_data
        self.enemy_data = enemy_data
        self._original_code_text = code_text_split
        self._section_lines = code_text_split
        self._command_list = []
        self.analyse_code()

    def analyse_code(self):
        """The idea is to go through each line, analyse it and remove the text line while adding the command in the list
        First, we search for an if. Having the line index of this if, we know each previous lines are normal command"""
        op_if_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 2][0]
        op_else_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == 35][0]
        temp_command_list = CodeAnalyseTool.analyse_loop(self._section_lines, op_if_info['func_name'], op_else_info['func_name'], self.game_data,
                                                         self.enemy_data)

        # Changing line index of each command as they should be in the correct order
        # Also remove empty lines
        index = 0
        for i in range(len(temp_command_list)):
            if temp_command_list[i]:
                self._command_list.append(temp_command_list[i])
                self._command_list[-1].line_index = index
                index += 1
            else:
                continue
        current_if_type = CurrentIfType.NONE
        for i in range(len(self._command_list)):
            current_if_type = self._command_list[i].compute_op_data(current_if_type)

    def get_command(self):
        return self._command_list

    @staticmethod
    def compute_ifrit_ai_code_to_command(game_data:GameData, enemy_data, ifrit_ai_code: str):
        command_text_list = ifrit_ai_code.splitlines()
        code_analyser = CodeAnalyser(game_data, enemy_data, command_text_list)
        return code_analyser.get_command()

    @staticmethod
    def set_ifrit_ai_code_from_command(game_data:GameData, command_list: List[CommandAnalyser]):
        func_list = []
        if_list_count = []
        else_list_count = []

        for command in command_list:
            last_else = False
            for i in range(len(if_list_count)):
                if_list_count[i] -= command.get_size()
                if if_list_count[i] == 0:
                    func_list.append('}')
            for i in range(len(else_list_count)):
                if else_list_count[i] == 0:
                    # if command.get_id() == 2:
                    #     op_list = command.get_op_code()
                    #     jump_value = int.from_bytes(bytearray([op_list[5], op_list[6]]), byteorder='little')
                    #     else_list_count[i]+=jump_value + command.get_size() # Adding size of if as we compute it in the same turn
                    # elif command.get_id() != 2:  # If we jump to a if, means we are still in the else, just forward jumping
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
                command_text = command.get_text(with_size=False, for_code=True, html=True)
                command_text = command_text.split('|')[0]
                func_line_text = op_info['func_name'] + ": "
                func_line_text += command_text
                func_list.append(func_line_text)
                func_list.append('{')
            elif command.get_id() == 35:
                op_list = command.get_op_code()
                jump_value = int.from_bytes(bytearray([op_list[0], op_list[1]]), byteorder='little')
                if jump_value & 0x8000 != 0: #Jump backward so we don't add anything related to else, just a jump backward for the moment
                    func_line_text = op_info['func_name'] + ": "
                    func_line_text += command.get_text(with_size=False, for_code=True, html=True)
                    func_list.append(func_line_text)
                elif jump_value > 0:  # We don't add the endif
                    last_else = True
                    else_list_count.append(jump_value)  # Adding the else size himself
                    command_text = CodeAnalyser.ELSE_TEXT
                    func_line_text = op_info['func_name'] + ": "
                    func_line_text += command_text
                    func_list.append(func_line_text)
                    func_list.append('{')
            else:
                func_line_text = op_info['func_name'] + ": "
                func_line_text += command.get_text(with_size=False, for_code=True, html=True)
                func_list.append(func_line_text)
            # The else are closing after the function (you don't count the jump contrary to an if
            for i in range(len(else_list_count)):
                if i == len(else_list_count) - 1 and last_else:  # Don't update the else we just added with his own size !
                    continue
                else_list_count[i] -= command.get_size()

        func_list = CodeAnalyser.compute_indent_bracket(func_list)
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