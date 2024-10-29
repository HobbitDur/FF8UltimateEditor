import copy
import glob
import os
import re
import shutil
from math import floor

from simple_file_checksum import get_checksum

from gamedata import GameData


class Ennemy():
    DAT_FILE_SECTION_LIST = ['header', 'skeleton', 'model_geometry', 'model_animation', 'unknown_section4', 'unknown_section5', 'unknown_section6', 'info_stat',
                             'battle_script', 'sound', 'unknown_section10', 'texture']
    MAX_MONSTER_TXT_IN_BATTLE = 10
    MAX_MONSTER_SIZE_TXT_IN_BATTLE = 100

    def __init__(self, game_data):
        self.file_raw_data = bytearray()
        self.origin_file_name = ""
        self.origin_file_checksum = ""
        self.subsection_ai_offset = {'init_code': 0, 'ennemy_turn': 0, 'counter_attack': 0, 'death': 0, 'unknown': 0}
        self.header_data = copy.deepcopy(game_data.SECTION_HEADER_DICT)
        self.model_animation_data = copy.deepcopy(game_data.SECTION_MODEL_ANIM_DICT)
        self.info_stat_data = copy.deepcopy(game_data.SECTION_INFO_STAT_DICT)
        self.battle_script_data = copy.deepcopy(game_data.SECTION_BATTLE_SCRIPT_DICT)
        self.sound_data = bytes()  # Section 9
        self.sound_unknown_data = bytes()  # Section 10
        self.sound_texture_data = bytes()  # Section 11
        self.list_var = [{'op_code': 20, 'var_name': 'Unknown20'},
                         {'op_code': 81, 'var_name': 'TomberryDefeated'},
                         {'op_code': 82, 'var_name': 'TomberrySrIsDefeated'},
                         {'op_code': 83, 'var_name': 'UfoIsDefeated'},
                         {'op_code': 84, 'var_name': 'FirstBugSeen'},
                         {'op_code': 85, 'var_name': 'FirstBombSeen'},
                         {'op_code': 86, 'var_name': 'FirstT-RexaurSeen'},
                         {'op_code': 87, 'var_name': 'LimitBreakIrvine'},
                         {'op_code': 96, 'var_name': 'SetupRandomness96'},
                         {'op_code': 97, 'var_name': 'SetupRandomness97'},
                         {'op_code': 98, 'var_name': 'SetupRandomness98'},
                         {'op_code': 99, 'var_name': 'SetupRandomness99'},
                         ]
        self.was_physical = False
        self.was_magic = False
        self.was_item = False
        self.was_gforce = False
        self.list_op_code = [{'op_code': 0x00, 'size': 0, 'func': self.__op_00_analysis},  # Stop
                             {'op_code': 0x01, 'size': 1, 'func': self.__op_01_analysis},  # Show battle text
                             {'op_code': 0x02, 'size': 7, 'func': self.__op_02_analysis},  # IF condition
                             {'op_code': 0x03, 'size': 0, 'func': self.__op_03_analysis},  # Unknown/unused
                             {'op_code': 0x04, 'size': 1, 'func': self.__op_04_analysis},  # Target
                             {'op_code': 0x05, 'size': 3, 'func': self.__op_05_analysis},  # Unknown
                             {'op_code': 0x06, 'size': 0, 'func': self.__op_06_analysis},  # Unknown ultimecia 126 ? (maybe not if 0x3A size 1)
                             {'op_code': 0x07, 'size': 0, 'func': self.__op_07_analysis},  # Unknown/unused
                             {'op_code': 0x08, 'size': 0, 'func': self.__op_08_analysis},  # End combat
                             {'op_code': 0x09, 'size': 1, 'func': self.__op_09_analysis},  # Change animation
                             {'op_code': 0x0B, 'size': 3, 'func': self.__op_0B_analysis},  # Random attack
                             {'op_code': 0x0C, 'size': 1, 'func': self.__op_0C_analysis},  # Attack/animation
                             {'op_code': 0x0E, 'size': 2, 'func': self.__op_0E_analysis},  # Set var
                             {'op_code': 0x0F, 'size': 2, 'func': self.__op_0F_analysis},  # Set var globally
                             {'op_code': 0x10, 'size': 0, 'func': self.__op_10_analysis},  # Unknown/unused
                             {'op_code': 0x11, 'size': 2, 'func': self.__op_11_analysis},  # Set var map
                             {'op_code': 0x12, 'size': 2, 'func': self.__op_12_analysis},  # Add var
                             {'op_code': 0x13, 'size': 2, 'func': self.__op_13_analysis},  # Add var global
                             {'op_code': 0x14, 'size': 0, 'func': self.__op_14_analysis},  # Unknown/unused
                             {'op_code': 0x15, 'size': 2, 'func': self.__op_15_analysis},  # ADD var savemap
                             {'op_code': 0x16, 'size': 0, 'func': self.__op_16_analysis},  # FUll hp
                             {'op_code': 0x17, 'size': 1, 'func': self.__op_17_analysis},  # Deactivate RUn away
                             {'op_code': 0x18, 'size': 1, 'func': self.__op_18_analysis},  # Show battle text with debug ?
                             {'op_code': 0x19, 'size': 1, 'func': self.__op_19_analysis},  # Unknown
                             {'op_code': 0x1A, 'size': 1, 'func': self.__op_1A_analysis},  # Show battle text + lock
                             {'op_code': 0x1B, 'size': 5, 'func': self.__op_1B_analysis},  # Unknown (biggs 1)
                             {'op_code': 0x1C, 'size': 1, 'func': self.__op_1C_analysis},  # Wait text
                             {'op_code': 0x1D, 'size': 1, 'func': self.__op_1D_analysis},  # Leave ennemy
                             {'op_code': 0x1E, 'size': 1, 'func': self.__op_1E_analysis},  # Launch special action
                             {'op_code': 0x1F, 'size': 1, 'func': self.__op_1F_analysis},  # Enter ennemy
                             {'op_code': 0x20, 'size': 0, 'func': self.__op_20_analysis},  # Unknown Goliath (unused ?)
                             {'op_code': 0x23, 'size': 2, 'func': self.__op_23_analysis},  # Else/Endif
                             {'op_code': 0x24, 'size': 0, 'func': self.__op_24_analysis},  # Fill ATB bar
                             {'op_code': 0x25, 'size': 1, 'func': self.__op_25_analysis},  # Add Scan
                             {'op_code': 0x26, 'size': 4, 'func': self.__op_26_analysis},  # Target with status
                             {'op_code': 0x27, 'size': 2, 'func': self.__op_27_analysis},  # Flag set capacity
                             {'op_code': 0x28, 'size': 2, 'func': self.__op_28_analysis},  # Change stat
                             {'op_code': 0x29, 'size': 0, 'func': self.__op_29_analysis},  # Draw magic
                             {'op_code': 0x2A, 'size': 0, 'func': self.__op_2A_analysis},  # Launch magic draw
                             {'op_code': 0x2B, 'size': 2, 'func': self.__op_2B_analysis},  # Unknown ultimecia 124
                             {'op_code': 0x2C, 'size': 0, 'func': self.__op_2C_analysis},  # Unknown seifer
                             {'op_code': 0x2D, 'size': 3, 'func': self.__op_2D_analysis},  # Change elemental value
                             {'op_code': 0x2E, 'size': 0, 'func': self.__op_2E_analysis},  # Cronos
                             {'op_code': 0x30, 'size': 0, 'func': self.__op_30_analysis},  # DEACTIVATE AS TARGET (gangrene)
                             {'op_code': 0x31, 'size': 1, 'func': self.__op_31_analysis},  # Give gforce (tomberrry)
                             {'op_code': 0x32, 'size': 0, 'func': self.__op_32_analysis},  # Unknown (shiva/brahman)
                             {'op_code': 0x33, 'size': 0, 'func': self.__op_33_analysis},  # Activate target
                             {'op_code': 0x34, 'size': 1, 'func': self.__op_34_analysis},  # Unknown (shiva)
                             {'op_code': 0x35, 'size': 1, 'func': self.__op_35_analysis},  # Activate ennemy as target
                             {'op_code': 0x36, 'size': 0, 'func': self.__op_36_analysis},  # Seifer 4
                             {'op_code': 0x37, 'size': 1, 'func': self.__op_37_analysis},  # Give card
                             {'op_code': 0x38, 'size': 1, 'func': self.__op_38_analysis},  # Give object
                             {'op_code': 0x39, 'size': 0, 'func': self.__op_39_analysis},  # Game over
                             {'op_code': 0x3A, 'size': 1, 'func': self.__op_3A_analysis},  # Unknown seifer and ultimecia 126
                             {'op_code': 0x3B, 'size': 2, 'func': self.__op_3B_analysis},  # Unknown (ultimecia 124)
                             {'op_code': 0x3C, 'size': 1, 'func': self.__op_3C_analysis},  # Increase Max HP
                             {'op_code': 0x3D, 'size': 0, 'func': self.__op_3D_analysis},  # Unknown Minotaure
                             {'op_code': 0x41, 'size': 0, 'func': self.__op_41_analysis},  # Unknown goliath (unused ?)
                             ]
        self.list_comparator = ['⩵', '<', '>', '≠', '≤', '≥']
        self.list_target_char = ['Squall', 'Zell', 'Irvine', 'Quistis', 'Rinoa', 'Selphie', 'Seifer', 'Edea', 'Laguna', 'Kiros', 'Ward']  # Start at 0


    def __str__(self):
        return "Name: {} \nData:{}".format(self.info_stat_data['monster_name'],
                                           [self.header_data, self.model_animation_data, self.info_stat_data, self.battle_script_data])

    def load_file_data(self, file, game_data):
        with open(file, "rb") as f:
            while el := f.read(1):
                self.file_raw_data.extend(el)
        self.__analyze_header_section(game_data)
        self.origin_file_name = os.path.basename(file)
        self.origin_file_checksum = get_checksum(file, algorithm='SHA256')

    def analyse_loaded_data(self, game_data, analyse_ia):
        """This is the main function. Here we have several cases.
        So first the based stat. As there is 4 stats for each in order to compute the final stat, they are stored in a list of size 4.
        For card, this is the ID for the different case: DROP, MOD, RARE_MOD
        There is common value of size 1, just raw value.
        % case with specific compute
        Elem and status have specific computation
        Devour is a set of ID for Low, medium, High
        Abilities
        """

        self.__analyze_animation_section(game_data)
        self.__analyze_info_stat(game_data)
        self.__analyze_battle_script_section(game_data, analyse_ia)
        self.__analyze_sound_section(game_data)
        self.__analyze_sound_unknown_section(game_data)
        self.__analyze_texture_section(game_data)

    def write_data_to_file(self, game_data, path, write_ia=True):
        print("Writing monster {}".format(self.info_stat_data["monster_name"]))
        # First copy original file
        full_dest_path = os.path.join(path, self.origin_file_name)
        # Then load file (python make it difficult to directly modify files)
        # Then modify loaded file
        section_position = 0
        for index_data, data in enumerate([self.model_animation_data, self.info_stat_data, self.battle_script_data]):
            if index_data == 0:
                section_position = 3
            if index_data == 1:
                section_position = 7
            if index_data == 2:
                section_position = 8
            for param_name, value in data.items():
                if param_name != 'battle_text' and 'ia_data' != param_name:  # Combat txt handled differently
                    property_elem = [x for ind, x in enumerate(
                        game_data.SECTION_INFO_STAT_LIST_DATA + game_data.SECTION_BATTLE_SCRIPT_LIST_DATA + game_data.SECTION_MODEL_ANIM_LIST_DATA) if
                                     x['name'] == param_name][0]
                if param_name in (game_data.stat_values + ['card', 'devour']):  # List of 1 byte value
                    value_to_set = bytes(value)
                elif param_name in ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'ap', 'nb_animation'] + game_data.BYTE_FLAG_LIST:
                    value_to_set = value.to_bytes(length=property_elem['size'], byteorder=property_elem['byteorder'])
                elif param_name in ['low_lvl_mag', 'med_lvl_mag', 'high_lvl_mag', 'low_lvl_mug', 'med_lvl_mug', 'high_lvl_mug', 'low_lvl_drop',
                                    'med_lvl_drop',
                                    'high_lvl_drop']:  # Case with 4 values linked to 4 IDs
                    value_to_set = []
                    for el2 in value:
                        value_to_set.append(el2['ID'])
                        value_to_set.append(el2['value'])
                    value_to_set = bytes(value_to_set)
                elif param_name in ['mug_rate', 'drop_rate']:  # Case with %
                    value_to_set = round((value * 255 / 100)).to_bytes()
                elif param_name in ['elem_def']:  # Case with elem
                    value_to_set = []
                    for i in range(len(value)):
                        value_to_set.append(floor((900 - value[i]) / 10))
                    value_to_set = bytes(value_to_set)
                elif param_name in ['status_def']:  # Case with elem
                    value_to_set = []
                    for i in range(len(value)):
                        value_to_set.append(value[i] + 100)
                    value_to_set = bytes(value_to_set)
                elif param_name in game_data.ABILITIES_HIGHNESS_ORDER:
                    value_to_set = bytearray()
                    for el2 in value:
                        value_to_set.extend(el2['type'].to_bytes())
                        value_to_set.extend(el2['animation'].to_bytes())
                        value_to_set.extend(el2['id'].to_bytes(2, property_elem['byteorder']))
                    value_to_set = bytes(value_to_set)
                elif param_name in ['monster_name']:
                    value_to_set = game_data.translate_str_to_hex(value)
                    # Completing the 0 after the name
                    for i in range(len(value_to_set), property_elem['size']):
                        value_to_set.append(0)
                elif param_name in ['renzokuken']:
                    value_to_set = bytearray()
                    for i in range(len(value)):
                        value_to_set.extend(value[i].to_bytes(2, game_data.SECTION_INFO_STAT_RENZOKUKEN['byteorder']))
                elif param_name == 'battle_text':  # Special case for text as the value change for each text
                    if value:
                        value_battle = bytearray()
                        for str_battle in value:
                            value_battle.extend(game_data.translate_str_to_hex(str_battle))
                            value_battle.extend([0])
                        self.file_raw_data[self.header_data['section_pos'][8] + self.battle_script_data['offset_text_sub']:
                                           self.header_data['section_pos'][8] + self.battle_script_data['offset_text_sub'] + len(value_battle)] = value_battle
                    continue  # Not setting the file_raw_data loop
                elif param_name == 'ia_data' and write_ia:
                    # Saving text
                    save_text = self.file_raw_data[self.header_data['section_pos'][8] + self.battle_script_data['offset_text_offset']:
                                                   self.header_data['section_pos'][9]]
                    list_offset = ['offset_init_code', 'offset_ennemy_turn', 'offset_counterattack', 'offset_death', 'offset_before_dying_or_hit']
                    offset_from_ai_subsection = self.battle_script_data['offset_init_code']
                    offset_from_current_section = 0
                    index_list_offset = 0
                    for command in value:
                        if command['id'] == -1:  # Separator
                            index_list_offset += 1
                            offset_from_ai_subsection += offset_from_current_section
                            if command['end']:
                                break
                            self.battle_script_data[list_offset[index_list_offset]] = offset_from_ai_subsection
                            offset_from_current_section = 0
                            continue
                        command_ref = [x for x in self.list_op_code if x['op_code'] == command['id']][0]
                        start_data = self.header_data['section_pos'][section_position] + self.battle_script_data[
                            'offset_ai_sub'] + offset_from_ai_subsection + offset_from_current_section
                        end_data = start_data + command_ref['size'] + 1  # +1 for taking into account the id we are writing
                        if command['id'] == 0x02:  # IF
                            comparator = self.list_comparator.index(command['comparator'])
                            jump = command['jump']
                            value_to_set = [command['id'], command['subject_id'], command['left_param'],
                                            comparator, command['right_param'], command['debug'], *jump]
                        elif command['id'] in [0x0E, 0x0F, 0x11, 0x12, 0x13, 0x15]:  # Modify var
                            if command['param'][-1] == '[global]':
                                if command['id'] in [0x0E, 0x0F, 0x11]:
                                    futur_command_id = 0x0F
                                elif command['id'] in [0x12, 0x13, 0x15]:
                                    futur_command_id = 0x13
                            elif command['param'][-1] == '[savemap]':
                                if command['id'] in [0x0E, 0x0F, 0x11]:
                                    futur_command_id = 0x11
                                elif command['id'] in [0x12, 0x13, 0x15]:
                                    futur_command_id = 0x15
                            else:
                                if command['id'] in [0x0E, 0x0F, 0x11]:
                                    futur_command_id = 0x0E
                                elif command['id'] in [0x12, 0x13, 0x15]:
                                    futur_command_id = 0x12
                            var_ref = [x for x in self.list_var if x['var_name'] == command['param'][0]]
                            if var_ref:
                                var_id = var_ref[0]['op_code']
                            else:
                                var_id = int(command['param'][0])
                            var_set = command['param'][1]
                            value_to_set = [futur_command_id, var_id, var_set]
                        elif command['id'] == 0x1A:  # LOCK PARAM TO REMOVE
                            value_to_set = [command['id'], command['param'][0]]
                        else:
                            value_to_set = [command['id'], *command['param']]
                        offset_from_current_section += command_ref['size'] + 1
                        self.file_raw_data[start_data:end_data] = bytes(value_to_set)

                    # Changing the section 9,10, 11 position and texts offset as we have moved everything a bit
                    # Writing new AI offset
                    for i, header in enumerate(game_data.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA):
                        self.file_raw_data[
                        self.header_data['section_pos'][8] + self.battle_script_data['offset_ai_sub'] + header['offset']:
                        self.header_data['section_pos'][8] + self.battle_script_data['offset_ai_sub'] + header['offset'] + header['size']] = (
                            self.battle_script_data[list_offset[i]]).to_bytes(
                            header['size'], header['byteorder'])

                    # Changing the text offset value and offset text offset value
                    length_offset_text_offset = self.battle_script_data['offset_text_sub'] - self.battle_script_data['offset_text_offset']
                    length_old_ia_section = self.battle_script_data['offset_text_offset'] - self.battle_script_data['offset_ai_sub']
                    self.battle_script_data['offset_text_offset'] = self.battle_script_data['offset_ai_sub'] + offset_from_ai_subsection
                    self.battle_script_data['offset_text_sub'] = self.battle_script_data['offset_text_offset'] + length_offset_text_offset
                    self.file_raw_data[self.header_data['section_pos'][8] + game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['offset']:
                                       self.header_data['section_pos'][8] + game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['offset'] +
                                       game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['size']] = self.battle_script_data[
                        'offset_text_offset'].to_bytes(game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['size'],
                                                       game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['byteorder'])
                    self.file_raw_data[self.header_data['section_pos'][8] + game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['offset']:
                                       self.header_data['section_pos'][8] + game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['offset'] +
                                       game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['size']] = self.battle_script_data['offset_text_sub'].to_bytes(
                        game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['size'], game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['byteorder'])

                    # Changing the file size
                    diff_ia_length = offset_from_ai_subsection - length_old_ia_section
                    futur_file_size = self.header_data['file_size'] + diff_ia_length
                    size_change = offset_from_ai_subsection - length_old_ia_section
                    if futur_file_size > self.header_data['file_size']:
                        self.file_raw_data.extend([0] * (futur_file_size - self.header_data['file_size']))
                    elif futur_file_size < self.header_data['file_size']:  # If the IA have been shorter, fill with 0
                        # Removing the last n byte
                        self.file_raw_data = self.file_raw_data[:-(self.header_data['file_size'] - futur_file_size) or None]
                    # Writing the new file size
                    self.header_data['file_size'] = futur_file_size
                    file_size_section_offset = 4 + self.header_data['nb_section'] * 4
                    self.file_raw_data[file_size_section_offset:file_size_section_offset + game_data.SECTION_HEADER_FILE_SIZE['size']] = (
                        self.header_data['file_size'].to_bytes(game_data.SECTION_HEADER_FILE_SIZE['size'], game_data.SECTION_HEADER_FILE_SIZE['byteorder']))

                    # Writing save text
                    self.file_raw_data[self.header_data['section_pos'][8] + self.battle_script_data['offset_text_offset']:
                                       self.header_data['section_pos'][8] + self.battle_script_data['offset_text_offset'] + len(save_text)] = save_text
                    # Writing section 9 10 11
                    new_section_9_offset = self.header_data['section_pos'][9] + size_change
                    data = self.sound_data + self.sound_unknown_data + self.texture_data
                    self.file_raw_data[new_section_9_offset:
                                       new_section_9_offset + len(self.sound_data) + len(self.sound_unknown_data) + len(self.texture_data)] = data
                    # Changing section 9 10 11 index:
                    for i in range(9, 12):
                        self.header_data['section_pos'][i] = self.header_data['section_pos'][i] + size_change
                        self.file_raw_data[game_data.SECTION_HEADER_SECTION_POSITION['offset'] + (i - 1) * game_data.SECTION_HEADER_SECTION_POSITION['size']:
                                           game_data.SECTION_HEADER_SECTION_POSITION['offset'] + game_data.SECTION_HEADER_SECTION_POSITION['size'] * (
                                               i)] = (self.header_data['section_pos'][i]).to_bytes(game_data.SECTION_HEADER_SECTION_POSITION['size'],
                                                                                                   game_data.SECTION_HEADER_SECTION_POSITION[
                                                                                                       'byteorder'])
                    continue  # Not setting the file_raw_data loop

                else:  # Data that we don't modify in the excel
                    continue
                if value_to_set:
                    self.file_raw_data[self.header_data['section_pos'][section_position] + property_elem['offset']:
                                       self.header_data['section_pos'][section_position] + property_elem['offset'] + property_elem['size']] = value_to_set

        # Write back on file
        with open(full_dest_path, "wb") as f:
            f.write(self.file_raw_data)

    def __get_int_value_from_info(self, data_info, section_number=0):
        return int.from_bytes(self.__get_raw_value_from_info(data_info, section_number), data_info['byteorder'])

    def __get_raw_value_from_info(self, data_info, section_number=0):
        if section_number == 0:
            section_offset = 0
        else:
            if section_number >= len(self.header_data['section_pos']):
                return bytearray(b'')
            section_offset = self.header_data['section_pos'][section_number]
        return self.file_raw_data[section_offset + data_info['offset']:section_offset + data_info['offset'] + data_info['size']]

    def __analyze_header_section(self, game_data):
        self.header_data['nb_section'] = self.__get_int_value_from_info(game_data.SECTION_HEADER_NB_SECTION)
        sect_position = [0]  # Adding to the list the header as a section 0
        for i in range(self.header_data['nb_section']):
            sect_position.append(
                int.from_bytes(self.file_raw_data[game_data.SECTION_HEADER_SECTION_POSITION['offset'] + i * game_data.SECTION_HEADER_SECTION_POSITION['size']:
                                                  game_data.SECTION_HEADER_SECTION_POSITION['offset'] +
                                                  game_data.SECTION_HEADER_SECTION_POSITION['size'] * (i + 1)],
                               game_data.SECTION_HEADER_SECTION_POSITION['byteorder']))
        self.header_data['section_pos'] = sect_position
        file_size_section_offset = 4 + self.header_data['nb_section'] * 4
        self.header_data['file_size'] = int.from_bytes(
            self.file_raw_data[file_size_section_offset:file_size_section_offset + game_data.SECTION_HEADER_FILE_SIZE['size']],
            game_data.SECTION_HEADER_FILE_SIZE['byteorder'])

    def __analyze_animation_section(self, game_data):  # Data loaded but not used or put in the excel for the moment
        self.model_animation_data['nb_animation'] = self.__get_int_value_from_info(game_data.SECTION_MODEL_ANIM_NB_MODEL, 3)

    def __analyze_sound_section(self, game_data):  # Data loaded but not used or put in the excel for the moment
        start_data = self.header_data['section_pos'][9]
        end_data = self.header_data['section_pos'][10]
        self.sound_data = self.file_raw_data[start_data:end_data]

    def __analyze_sound_unknown_section(self, game_data):  # Data loaded but not used or put in the excel for the moment
        start_data = self.header_data['section_pos'][10]
        end_data = self.header_data['section_pos'][11]
        self.sound_unknown_data = self.file_raw_data[start_data:end_data]

    def __analyze_texture_section(self, game_data):  # Data loaded but not used or put in the excel for the moment
        start_data = self.header_data['section_pos'][11]
        end_data = self.header_data['file_size']
        self.texture_data = self.file_raw_data[start_data:end_data]

    def __analyze_info_stat(self, game_data):
        SECTION_NUMBER = 7
        for el in game_data.SECTION_INFO_STAT_LIST_DATA:
            raw_data_selected = self.__get_raw_value_from_info(el, SECTION_NUMBER)
            data_size = len(raw_data_selected)
            if el['name'] in ['monster_name']:
                value = game_data.translate_hex_to_str(raw_data_selected)
            elif el['name'] in (game_data.stat_values + ['card', 'devour']):
                value = list(raw_data_selected)
            elif el['name'] in ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'ap', ]:
                value = int.from_bytes(raw_data_selected, byteorder=el['byteorder'])
            elif el['name'] in ['low_lvl_mag', 'med_lvl_mag', 'high_lvl_mag', 'low_lvl_mug', 'med_lvl_mug', 'high_lvl_mug', 'low_lvl_drop', 'med_lvl_drop',
                                'high_lvl_drop']:  # Case with 4 values linked to 4 IDs
                list_data = list(raw_data_selected)
                value = []
                for i in range(0, data_size - 1, 2):
                    value.append({'ID': list_data[i], 'value': list_data[i + 1]})
            elif el['name'] in ['mug_rate', 'drop_rate']:  # Case with %
                value = int.from_bytes(raw_data_selected) * 100 / 255
            elif el['name'] in ['elem_def']:  # Case with elem
                value = list(raw_data_selected)
                for i in range(data_size):
                    value[i] = 900 - value[i] * 10  # Give percentage
            elif el['name'] in game_data.ABILITIES_HIGHNESS_ORDER:
                list_data = list(raw_data_selected)
                value = []
                for i in range(0, data_size - 1, 4):
                    value.append({'type': list_data[i], 'animation': list_data[i + 1], 'id': int.from_bytes(list_data[i + 2:i + 4], el['byteorder'])})
            elif el['name'] in ['status_def']:  # Case with elem
                value = list(raw_data_selected)
                for i in range(data_size):
                    value[i] = value[i] - 100  # Give percentage, 155 means immune.
                if 'UNKNOWN_STAT' not in game_data.game_info_test.keys():
                    game_data.game_info_test['UNKNOWN_STAT'] = {}
            elif el['name'] in game_data.BYTE_FLAG_LIST:  # Flag in byte management
                byte_value = format((int.from_bytes(raw_data_selected)), '08b')[::-1]  # Reversing
                value = {}
                if el['name'] == 'byte_flag_0':
                    byte_list = game_data.SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE
                elif el['name'] == 'byte_flag_1':
                    byte_list = game_data.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE
                elif el['name'] == 'byte_flag_2':
                    byte_list = game_data.SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE
                elif el['name'] == 'byte_flag_3':
                    byte_list = game_data.SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE
                else:
                    print("Unexpected byte flag {}".format(el['name']))
                    byte_list = game_data.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE
                for index, bit_name in enumerate(byte_list):
                    value[bit_name] = +bool(int(byte_value[index]))
                    # For monster.txt purpose
                    if value[bit_name] == 1 and self.info_stat_data['monster_name'] != '\\n{NewPage}\\n{x0c00}/${x1000}{x0900}{x0c02}':
                        if bit_name not in game_data.game_info_test.keys():
                            game_data.game_info_test[bit_name] = []
                        # if self.info_stat_data['monster_name'] not in game_data.game_info_test.keys():
                        #    game_data.game_info_test[self.info_stat_data['monster_name']] = []
                        game_data.game_info_test[bit_name].append(self.info_stat_data['monster_name'] + " " + self.origin_file_name)
                        # game_data.game_info_test[self.info_stat_data['monster_name']].append({'bit_name':bit_name, 'bit_value':value[bit_name]})

                    # End monster.txt purpose
            elif el['name'] in 'renzokuken':
                value = []
                for i in range(0, el['size'], 2):  # List of 8 value of 2 bytes
                    value.append(int.from_bytes(raw_data_selected[i:i + 2], el['byteorder']))
            else:
                value = "ERROR UNEXPECTED VALUE"
                print("Unexpected name while analyzing info stat: {}".format(el['name']))

            self.info_stat_data[el['name']] = value

            # For monster.txt purpose
            if 'list_monster' not in game_data.game_info_test.keys():
                game_data.game_info_test['list_monster'] = []
            if self.info_stat_data['monster_name'] not in game_data.game_info_test['list_monster']:
                if '\\n{NewPage}\\n{x0c00}/${x1000}{x0900}{x0c02}' not in self.info_stat_data['monster_name']:
                    game_data.game_info_test['list_monster'].append(self.info_stat_data['monster_name'])

    def __analyze_battle_script_section(self, game_data, analyse_ia):
        SECTION_NUMBER = 8
        if len(self.header_data['section_pos']) <= SECTION_NUMBER:
            return
        section_offset = self.header_data['section_pos'][SECTION_NUMBER]

        # Reading header
        self.battle_script_data['battle_nb_sub'] = self.__get_int_value_from_info(game_data.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_NUMBER)
        self.battle_script_data['offset_ai_sub'] = self.__get_int_value_from_info(game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB, SECTION_NUMBER)
        self.battle_script_data['offset_text_offset'] = self.__get_int_value_from_info(game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB,
                                                                                       SECTION_NUMBER)
        self.battle_script_data['offset_text_sub'] = self.__get_int_value_from_info(game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB, SECTION_NUMBER)

        # Reading text offset subsection
        nb_text = self.battle_script_data['offset_text_sub'] - self.battle_script_data['offset_text_offset']
        for i in range(0, nb_text, game_data.SECTION_BATTLE_SCRIPT_TEXT_OFFSET['size']):
            start_data = section_offset + self.battle_script_data['offset_text_offset'] + i
            end_data = start_data + game_data.SECTION_BATTLE_SCRIPT_TEXT_OFFSET['size']
            text_list_raw_data = self.file_raw_data[start_data:end_data]
            if i > 0 and text_list_raw_data == b'\x00\x00':  # Weird case where there is several pointer by the diff but several are 0 (which point to the same value)
                break
            self.battle_script_data['text_offset'].append(
                int.from_bytes(text_list_raw_data, byteorder=game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['byteorder']))
        # Reading text sub-section
        for text_pointer in self.battle_script_data['text_offset']:  # Reading each text from the text offset
            combat_text_raw_data = bytearray()
            for i in range(self.MAX_MONSTER_SIZE_TXT_IN_BATTLE):  # Reading char by char to search for the 0
                char_index = section_offset + self.battle_script_data['offset_text_sub'] + text_pointer + i
                if char_index >= len(self.file_raw_data):  # Shouldn't happen, only on garbage data / self.header_data['file_size'] can be used
                    pass
                else:
                    raw_value = self.file_raw_data[char_index]
                    if raw_value != 0:
                        combat_text_raw_data.extend(int.to_bytes(raw_value))
                    else:
                        break
            if combat_text_raw_data:
                self.battle_script_data['battle_text'].append(game_data.translate_hex_to_str(combat_text_raw_data))
            else:
                self.battle_script_data['battle_text'] = []
        if analyse_ia:
            print("Analysing IA from loaded file")
            # Reading AI subsection

            ## Reading offset
            ai_offset = section_offset + self.battle_script_data['offset_ai_sub']
            for offset_param in game_data.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA:
                start_data = ai_offset + offset_param['offset']
                end_data = ai_offset + offset_param['offset'] + offset_param['size']
                self.battle_script_data[offset_param['name']] = int.from_bytes(self.file_raw_data[start_data:end_data], offset_param['byteorder'])

            start_data = ai_offset + self.battle_script_data['offset_init_code']
            end_data = ai_offset + self.battle_script_data['offset_ennemy_turn']
            init_code = list(self.file_raw_data[start_data:end_data])
            start_data = ai_offset + self.battle_script_data['offset_ennemy_turn']
            end_data = ai_offset + self.battle_script_data['offset_counterattack']
            ennemy_turn_code = list(self.file_raw_data[start_data:end_data])
            start_data = ai_offset + self.battle_script_data['offset_counterattack']
            end_data = ai_offset + self.battle_script_data['offset_death']
            counterattack_code = list(self.file_raw_data[start_data:end_data])
            start_data = ai_offset + self.battle_script_data['offset_death']
            end_data = ai_offset + self.battle_script_data['offset_before_dying_or_hit']
            death_code = list(self.file_raw_data[start_data:end_data])
            start_data = ai_offset + self.battle_script_data['offset_before_dying_or_hit']
            end_data = section_offset + self.battle_script_data['offset_text_offset']
            before_dying_or_hit_code = list(self.file_raw_data[start_data:end_data])
            list_code = [init_code, ennemy_turn_code, counterattack_code, death_code, before_dying_or_hit_code]
            self.battle_script_data['ia_data'] = []
            for index, code in enumerate(list_code):
                first_index_0 = 0
                list_bracket = [0] * 10
                index_read = 0
                list_result = []
                while index_read < len(code):
                    op_code_ref = [x for x in self.list_op_code if x['op_code'] == code[index_read]]

                    if not op_code_ref and code[index_read] >= 0x40:
                        index_read += 1
                        continue
                    elif op_code_ref:  # >0x40 not used
                        op_code_ref = op_code_ref[0]
                        start_param = index_read + 1
                        end_param = index_read + 1 + op_code_ref['size']
                        result = op_code_ref['func'](code[start_param:end_param], game_data)
                        result['id'] = op_code_ref['op_code']
                        list_result.append(result)
                        index_read += 1 + op_code_ref['size']

                        # Managing END
                        ## Getting last_index that is zero
                        for i in range(len(list_bracket)):
                            if list_bracket[i] == 0:
                                first_index_0 = i
                                break
                        ## Decreasing coutdown
                        if first_index_0 > 0:
                            for i in range(first_index_0):
                                list_bracket[i] -= op_code_ref['size'] + 1
                        if result['id'] == 0x02:  # If it's a if, add a bracket
                            list_bracket[first_index_0] = result['jump'][0]
                        elif result['id'] == 0x23:  # IF it's a else, reinit last bracket
                            list_bracket[first_index_0 - 1] = result['param'][0]
                        for i in range(1, first_index_0 + 1):
                            if first_index_0 > 0 and list_bracket[first_index_0 - i] == 0:
                                ret = {'id': 0x23, 'text': 'END', 'param': []}
                                if i == 1 and  result['id'] == 0x23 and result['param'][0] == 0:# if its a else with 0 value, no end needed on the last value
                                    continue
                                elif result['id'] == 0x23:
                                    list_result.insert(len(list_result)-1, ret)
                                else:
                                    list_result.append(ret)
                        # END Managing END
                    else:
                        index_read += 1
                        game_data.unknown_result.append(self.info_stat_data['monster_name'])
                list_result = self.__remove_stop_end(list_result)
                self.battle_script_data['ia_data'].append(list_result)
            self.battle_script_data['ia_data'].append([])  # Adding a end section that is empty to mark the end of the all IA section

    def __remove_stop_end(self, list_result):
        id_remove = 0
        for i in range(len(list_result)):
            if list_result[i]['id'] == 0x00:  # STOP
                if i + 1 < len(list_result):
                    if list_result[i + 1]['id'] == 0x00:
                        id_remove = i + 1
                        break
        return list_result[:id_remove or None]

    def __op_27_analysis(self, op_code, game_data: GameData):
        if op_code[0] == 23:
            ret = 'auto-boomerang'
        else:
            ret = "unknown flag {}".format(op_code[0])
        return {'text': 'MAKE {} of {} to {}'.format(ret, self.info_stat_data['monster_name'], op_code[1]), 'param': [op_code[0], op_code[1]]}

    def __op_1D_analysis(self, op_code, game_data: GameData):
        return {'text': 'MAKE ENNEMY N°{} LEAVE COMBAT'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_09_analysis(self, op_code, game_data: GameData):
        return {'text': 'CHANGE MONSTER ANIMATION TO N°{}'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_1F_analysis(self, op_code, game_data: GameData):
        return {'text': 'MAKE ENNEMY {} ENTER COMBAT'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_35_analysis(self, op_code, game_data: GameData):
        if op_code[0] < len(game_data.monster_values):
            ret = game_data.monster_values[op_code[0]]
        else:
            ret = "unknown monster"
        return {'text': 'ACTIVATE ENNEMY {} AS TARGET'.format(ret), 'param': [op_code[0]]}

    def __op_37_analysis(self, op_code, game_data: GameData):
        if op_code[0] < len(game_data.card_values):
            ret = game_data.card_values[op_code[0]]['name']
        else:
            ret = "unknown card"
        return {'text': 'GIVE CARD {}'.format(ret), 'param': [op_code[0]]}

    def __op_38_analysis(self, op_code, game_data: GameData):
        if op_code[0] < len(game_data.item_values):
            ret = game_data.item_values[op_code[0]]['name']
        else:
            ret = "unknown item"
        return {'text': 'GIVE ITEM {}'.format(ret), 'param': [op_code[0]]}

    def __op_17_analysis(self, op_code, game_data: GameData):
        if op_code[0] > 0:
            ret = "DEACTIVATE RUN"
        else:
            ret = "ACTIVATE RUN"
        return {'text': ret, 'param': [op_code[0]]}

    def __op_1E_analysis(self, op_code, game_data: GameData):
        if op_code[0] < len(game_data.special_action):
            ret = game_data.special_action[op_code[0]]['name']
        else:
            ret = "unknown special action"
        return {'text': 'LAUNCH SPECIAL ACTION {}'.format(ret), 'param': [op_code[0]]}

    def __op_30_analysis(self, op_code, game_data: GameData):
        return {'text': 'DEACTIVATE AS TARGET', 'param': []}

    def __op_39_analysis(self, op_code, game_data: GameData):
        return {'text': 'GAME OVER', 'param': []}

    def __op_24_analysis(self, op_code, game_data: GameData):
        return {'text': 'FILL ATB BAR', 'param': []}

    def __op_08_analysis(self, op_code, game_data: GameData):
        return {'text': 'END COMBAT', 'param': []}

    def __op_34_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0]]}

    def __op_29_analysis(self, op_code, game_data: GameData):
        return {'text': 'DRAW RANDOM MAGIC', 'param': []}

    def __op_2A_analysis(self, op_code, game_data: GameData):
        return {'text': 'LAUNCH MAGIC DRAW', 'param': []}

    def __op_1B_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0], op_code[1], op_code[2], op_code[3], op_code[4]]}

    def __op_10_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN/UNUSED', 'param': []}
    def __op_03_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN/UNUSED', 'param': []}
    def __op_07_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN/UNUSED', 'param': []}
    def __op_14_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN/UNUSED', 'param': []}
    def __op_05_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0], op_code[1], op_code[2]]}

    def __op_06_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_2B_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0], op_code[1]]}

    def __op_2E_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_2C_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_36_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_3A_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0]]}

    def __op_3C_analysis(self, op_code, game_data: GameData):
        return {'text': 'Increase Max HP (but not current) by {}'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_3D_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_3B_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0], op_code[1]]}

    def __op_19_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': [op_code[0]]}

    def __op_32_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_41_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_20_analysis(self, op_code, game_data: GameData):
        return {'text': 'UNKNOWN ACTION', 'param': []}

    def __op_33_analysis(self, op_code, game_data: GameData):
        return {'text': 'ACTIVATE TARGET', 'param': []}

    def __op_16_analysis(self, op_code, game_data: GameData):
        return {'text': 'HEAL ALL HP', 'param': []}

    def __op_25_analysis(self, op_code, game_data: GameData):
        return {'text': 'ADD DESCRIPTION LINE N°{} IN SCAN'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_26_analysis(self, op_code, game_data: GameData):
        if op_code[3] < len(game_data.status_ia_values):
            status = game_data.status_ia_values[op_code[3]]['name']
        else:
            status = "UNKNOWN STATUS"
        if op_code[0] + op_code[2]:
            info = ''
        else:
            info = " unknown {}|{}".format(op_code[0], op_code[2])
        ret = "TARGET {} WITH STATUS {}{}".format(self.__get_target(op_code[1], game_data), status, info)
        return {'text': ret,
                'param': [op_code[0], op_code[1], op_code[2], op_code[3]]}

    def __op_0B_analysis(self, op_code, game_data: GameData):
        return {'text': 'Randomly use ability {} or {} or {}'.format(op_code[0], op_code[1], op_code[2]),
                'param': [op_code[0], op_code[1], op_code[2]]}

    def __op_13_analysis(self, op_code, game_data: GameData):
        ret = self.__op_12_analysis(op_code, game_data)
        ret['param'].append('[global]')
        return ret

    def __op_18_analysis(self, op_code, game_data: GameData):
        ret = self.__op_01_analysis(op_code, game_data)
        if op_code[0] != 0:
            ret['text'] += ' debug: {}'.format(str(op_code[0]))
        return ret

    def __op_31_analysis(self, op_code, game_data: GameData):
        if op_code[0] < len(game_data.gforce_values):
            ret = game_data.gforce_values[op_code[0]]
        else:
            ret = 'Unknown gforce'
        return {'text': 'GIVE G-FORCE {} AT END OF COMBAT'.format(ret),
                'param': [op_code[0]]}

    def __op_12_analysis(self, op_code, game_data):
        return {'text': 'ADD TO {} VALUE {}'.format(self.__get_var_name(op_code[0]), op_code[1]),
                'param': [op_code[0], op_code[1]]}

    def __op_28_analysis(self, op_code, game_data: GameData):
        if op_code[0] == 0:
            aptitude = 'Strength'
        elif op_code[0] == 1:
            aptitude = 'Vitality'
        elif op_code[0] == 2:
            aptitude = 'Magic'
        elif op_code[0] == 3:
            aptitude = 'Spirit'
        elif op_code[0] == 4:
            aptitude = 'Speed'
        elif op_code[0] == 5:
            aptitude = 'Evade'
        else:
            aptitude = "Unknown aptitude"

        if op_code[1] == 10:
            mod_change = "REINIT {} TO BASE VALUE".format(aptitude)
        else:
            mod_change = "MULTIPLY {} BY {}".format(aptitude, op_code[1]/10)
        return {'text': mod_change, 'param': [op_code[0], op_code[1]]}

    def __op_1C_analysis(self, op_code, game_data):
        return {'text': 'Wait {} text'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_23_analysis(self, op_code, game_data):
        jump = int.from_bytes(bytearray([op_code[0], op_code[1]]), byteorder='little')
        if jump == 0:
            text = 'ENDIF'
        else:
            text = 'ELSE'
        return {'text': text, 'param': [jump]}

    def __op_00_analysis(self, op_code, game_data):
        return {'text': 'STOP', 'param': []}

    def __op_2D_analysis(self, op_code, game_data):
        # op_2D = ['element', 'elementval', '?']
        if op_code[0] < len(game_data.magic_type_values):
            element = game_data.magic_type_values[op_code[0]]
        else:
            element = "UNKNOWN ELEMENT TYPE"
        element_val = op_code[1]
        op_code_unknown = op_code[2]
        return {'text': 'Resist element {} at {}'.format(element, element_val), 'param': [op_code[0], element_val, op_code_unknown]}

    def __op_0C_analysis(self, op_code, game_data):
        return {'text': 'Execute ability {}'.format(op_code[0]), 'param': [op_code[0]]}

    def __op_0F_analysis(self, op_code, game_data):
        analysis = self.__op_0E_analysis(op_code, game_data)
        analysis['param'].append('[global]')
        return analysis

    def __op_11_analysis(self, op_code, game_data):
        analysis = self.__op_0E_analysis(op_code, game_data)
        analysis['param'].append('[savemap]')
        return analysis

    def __op_15_analysis(self, op_code, game_data):
        analysis = self.__op_12_analysis(op_code, game_data)
        analysis['param'].append('[savemap]')
        return analysis

    def __op_0E_analysis(self, op_code, game_data):
        return {'text': 'SET {} TO {}'.format(self.__get_var_name(op_code[0]), op_code[1]),
                'param': [op_code[0], op_code[1]]}

    def __op_1A_analysis(self, op_code, game_data):
        analysis = self.__op_01_analysis(op_code, game_data)
        analysis['param'].append('LOCK BATTLE')
        return analysis

    def __op_01_analysis(self, op_code, game_data):
        if op_code[0] < len(self.battle_script_data['battle_text']):
            ret = 'SHOW BATTLE TEXT: {}'.format(self.battle_script_data['battle_text'][op_code[0]])
        else:
            ret = "/!\\SHOW BATTLE BUT NO BATTLE TO SHOW"
        return {'text': ret,
                'param': [op_code[0]]}

    def __op_02_analysis(self, op_code, game_data: GameData):
        # op_02 = ['subject_id', 'target', 'comparator', 'value', 'debug']
        subject_id = op_code[0]
        target = self.__get_target(op_code[1], game_data)
        op_code_comparator = op_code[2]
        op_code_value = op_code[3]
        op_code_jump = int.from_bytes(bytearray([op_code[5], op_code[6]]), byteorder='little')
        if op_code_comparator < len(self.list_comparator):
            comparator = self.list_comparator[op_code_comparator]
        else:
            comparator = 'UNKNOWN OPERATOR'
        if subject_id == 0:
            left_subject = {'text': 'HP of {}'.format(target), 'param': []}
            right_subject = {'text': '{} %'.format(op_code_value * 10), 'param': [op_code_value]}
        elif subject_id == 1:
            left_subject = {'text': 'HP of {}'.format(target), 'param': []}
            right_subject = {'text': '{} %'.format(op_code_value * 10), 'param': [op_code_value]}
        elif subject_id == 2:
            left_subject = {'text': 'RANDOM VALUE BETWEEN 0 AND {}'.format(op_code[1]), 'param': [op_code[1]]}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 3:
            left_subject = {'text': 'Combat scene', 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 4:
            left_subject = {'text': 'STATUS OF {}'.format(target), 'param': []}
            right_subject = {'text': '{}'.format(game_data.status_ia_values[op_code_value]['name']), 'param': [op_code_value]}
        elif subject_id == 5:
            left_subject = {'text': 'STATUS OF {}'.format(target, True), 'param': []}
            right_subject = {'text': '{}'.format(game_data.status_ia_values[op_code_value]['name']), 'param': [op_code_value]}
        elif subject_id == 6:
            left_subject = {'text': 'NUMBER OF MEMBER OF {}'.format(target, True), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 9:
            left_subject = {'text': self.__get_target(op_code[3], game_data), 'param': []}
            right_subject = {'text': 'ALIVE', 'param': []}
        elif subject_id == 10:
            if op_code[1] == 0:
                attack_condition = "ATTACKER WAS TEAM MEMBER N°"
                attack_type = op_code_value
            elif op_code[1] == 1:
                attack_condition = "ATTACKER IS"
                attack_type = target
            elif op_code[1] == 3:
                attack_condition = "Last attack was of type"
                if op_code_value == 1:
                    attack_type = "Physical damage"
                    self.was_physical = True
                elif op_code_value == 2:
                    attack_type = "Magical damage"
                    self.was_magic = True
                elif op_code_value == 4:
                    attack_type = "Item"
                    self.was_object = True
                elif op_code_value == 254:
                    attack_type = "G-Force"
                    self.was_force = True
                else:
                    attack_type = "Unknown {}".format(op_code_value)
            elif op_code[1] == 4:
                if op_code_value >= 64:
                    attack_condition = "LAST GFORCE LAUNCH WAS"
                    attack_type = game_data.gforce_values[op_code_value - 64]
                else:
                    if self.was_magic:
                        ret = game_data.magic_values[op_code_value]['name']
                    elif self.was_item:
                        ret = game_data.item_values[op_code_value]['name']
                    elif self.was_physical:
                        ret = game_data.special_action[op_code_value]['name']
                    else:
                        ret = op_code_value
                    attack_condition = "LAST ACTION LAUNCH WAS"
                    attack_type = ret
                    self.was_magic = False
                    self.was_item = False
                    self.was_physical = False
            elif op_code[1] == 5:
                attack_condition = "Last attack was of element"
                attack_type = game_data.magic_type_values[op_code_value]
            else:
                attack_condition = "Unknown last attack {}".format(op_code[1])
                attack_type = "Unknown attack type {}".format(op_code_value)
            left_subject = {'text': attack_condition, 'param': [op_code[1]]}
            right_subject = {'text': attack_type, 'param': [op_code_value]}
        elif subject_id == 14:
            left_subject = {'text': "Group level {}".format(target), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 15:
            left_subject = {'text': "{} CAN ATTACK WITH HIS ALLY".format(target), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 17:
            left_subject = {'text': "GFORCE STOLEN (TARGET: {})".format(target), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 18:
            left_subject = {'text': "Odin attaque ?".format(target), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id == 19:
            left_subject = {'text': "COUNTDOWN".format(target), 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        elif subject_id <= 19:
            left_subject = {'text': 'UNKNOWN SUBJECT', 'param': []}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        else:
            left_subject = {'text': '{}'.format(self.__get_var_name(subject_id)), 'param': [self.__get_var_name(subject_id)]}
            right_subject = {'text': '{}'.format(op_code_value), 'param': [op_code_value]}
        return {'if_text': 'IF', 'subject_id': subject_id, 'left_subject': left_subject, 'comparator': comparator, 'right_subject': right_subject,
                'then_text': 'THEN', 'left_param': [op_code[1]], 'right_param': [op_code_value], 'jump': [op_code_jump], 'debug': op_code[4]}

    def __op_04_analysis(self, op_code, game_data):
        return {'text': 'TARGET {}'.format(self.__get_target(op_code[0], game_data)), 'param': [op_code[0]]}

    def __get_var_name(self, id):
        var_found = [x['var_name'] for x in self.list_var if x['op_code'] == id]
        if var_found:
            var = var_found[0]
        else:
            var = "var" + str(id)
        return var

    def __get_target(self, id, game_data: GameData, reverse=False):
        if reverse:
            c8_data = "ALL ENNEMY"
        else:
            c8_data = self.info_stat_data['monster_name']
        list_target_other = [c8_data,  # 0xC8
                             'RANDOM ENNEMY',  # 0xC9
                             'RANDOM ALLY',  # 0xCA
                             'LAST ENNEMY TO HAVE ATTACK',  # 0xCB
                             'ALL ENNEMY',  # 0xCC
                             'ALL ALLY',  # 0xCD
                             'UNKNOWN',  # 0xCE
                             'ALLY OR ' + self.info_stat_data['monster_name'] + ' RANDOMLY',  # 0xCF arconada
                             'RANDOM ENNEMY',  # 0xD0 Marsupial with meteor
                             'NEW ALLY']  # 0xD1 shiva

        if id < len(self.list_target_char):
            return self.list_target_char[id]
        elif id >= 0xC8 and id < 0xC8 + len(list_target_other):
            return list_target_other[id - 0xC8]
        elif id >= 16:
            if id - 16 < len(game_data.monster_values):
                ret = game_data.monster_values[id - 16]
            else:
                ret = "UNKNOWN TARGET"
            return ret
