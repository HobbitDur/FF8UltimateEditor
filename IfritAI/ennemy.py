import copy
import os

from command import Command
from gamedata import GameData


class Ennemy():
    DAT_FILE_SECTION_LIST = ['header', 'skeleton', 'model_geometry', 'model_animation', 'unknown_section4', 'unknown_section5', 'unknown_section6', 'info_stat',
                             'battle_script', 'sound', 'unknown_section10', 'texture']
    MAX_MONSTER_TXT_IN_BATTLE = 10
    MAX_MONSTER_SIZE_TXT_IN_BATTLE = 100
    NUMBER_SECTION = len(DAT_FILE_SECTION_LIST)

    def __init__(self, game_data):
        self.file_raw_data = bytearray()
        self.origin_file_name = ""
        self.origin_file_checksum = ""
        self.subsection_ai_offset = {'init_code': 0, 'ennemy_turn': 0, 'counter_attack': 0, 'death': 0, 'unknown': 0}
        self.section_raw_data = [bytearray()] * self.NUMBER_SECTION
        self.header_data = copy.deepcopy(game_data.SECTION_HEADER_DICT)
        self.model_animation_data = copy.deepcopy(game_data.SECTION_MODEL_ANIM_DICT)
        self.info_stat_data = copy.deepcopy(game_data.SECTION_INFO_STAT_DICT)
        self.battle_script_data = copy.deepcopy(game_data.SECTION_BATTLE_SCRIPT_DICT)
        self.sound_data = bytes()  # Section 9
        self.sound_unknown_data = bytes()  # Section 10
        self.sound_texture_data = bytes()  # Section 11
        self.was_physical = False
        self.was_magic = False
        self.was_item = False
        self.was_gforce = False

    def __str__(self):
        return "Name: {} \nData:{}".format(self.info_stat_data['monster_name'],
                                           [self.header_data, self.model_animation_data, self.info_stat_data, self.battle_script_data])

    def load_file_data(self, file, game_data):
        self.file_raw_data = bytearray()
        with open(file, "rb") as f:
            while el := f.read(1):
                self.file_raw_data.extend(el)
        self.__analyze_header_section(game_data)
        self.origin_file_name = os.path.basename(file)
        # self.origin_file_checksum = get_checksum(file, algorithm='SHA256')

    def analyse_loaded_data(self, game_data):
        for i in range(0, self.NUMBER_SECTION - 1):
            self.section_raw_data[i] = self.file_raw_data[self.header_data['section_pos'][i]: self.header_data['section_pos'][i + 1]]
        self.section_raw_data[self.NUMBER_SECTION - 1] = self.file_raw_data[
                                                         self.header_data['section_pos'][self.NUMBER_SECTION - 1]:self.header_data['file_size']]

        # No need to analyze Section 1 : Skeleton
        # No need to analyze Section 2 : Model geometry
        # No need to analyze Section 3 : Model animation
        # No need to analyze Section 4 : Unknown
        # No need to analyze Section 5 : Unknown
        # No need to analyze Section 6 : Unknown
        # Analyzing Section 7 : Informations & stats
        self.__analyze_info_stat(game_data)
        # Analyzing Section 8 : Battle scripts/AI
        self.__analyze_battle_script_section(game_data)
        # No need to analyze Section 9 : Sounds
        # No need to analyze Section 10 : Sounds/Unknown
        # No need to analyze Section 11 : Textures

    def write_data_to_file(self, game_data, path):
        print("Writing monster {}".format(self.info_stat_data["monster_name"]))
        raw_data_to_write = bytearray()

        # Write the 8 (0 to 7) first section as raw data
        for i, section_data in enumerate(self.section_raw_data):
            if i < 8:
                raw_data_to_write.extend(section_data)
            else:
                break

        # Then modify the battle section (text + AI)
        # Saving text
        raw_data_save_text = self.file_raw_data[self.header_data['section_pos'][8] + self.battle_script_data['offset_text_sub']:
                                                self.header_data['section_pos'][9]]

        # Now creating the section 8
        # 3 subsection in section 8: The offset subsection (header), the AI and the texts

        # Number of subsection doesn't change, neither the offset to AI-sub-section
        self.section_raw_data[8] = bytearray()
        self.__add_section_raw_data_from_game_data(8, game_data.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB)
        self.__add_section_raw_data_from_game_data(8, game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB)

        # The AI section will change in change so we come back to the sub-section later
        # The offset need to take into account the different offset themself !
        offset_value_current_section = 0
        for offset in game_data.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA:
            offset_value_current_section += offset['size']
        raw_ai_section = bytearray()
        raw_ai_offset = bytearray()
        for index, section in enumerate(self.battle_script_data['ai_data']):
            if section:  # Ignoring the last section that is empty
                raw_ai_offset.extend(
                    self.__get_byte_from_int_from_game_data(offset_value_current_section, game_data.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA[index]))
                for command in section:
                    raw_ai_section.append(command.get_id())
                    raw_ai_section.extend(command.get_op_code())
                    offset_value_current_section += 1 + len(command.get_op_code())

        # Now changing text offset
        sect_data = game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB
        # offset_value_current_section contains the offset from AI code. Need to add the header list + the offset list of AI
        offset_text_offset = offset_value_current_section
        for offset in game_data.SECTION_BATTLE_SCRIPT_BATTLE_SCRIPT_HEADER_LIST_DATA:
            offset_text_offset += offset['size']
        self.__add_section_raw_data_from_game_data(8, sect_data, self.__get_byte_from_int_from_game_data(offset_text_offset, sect_data))
        sect_data = game_data.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB
        self.__add_section_raw_data_from_game_data(8, sect_data, self.__get_byte_from_int_from_game_data(
            offset_text_offset + len(self.battle_script_data['text_offset']) * game_data.SECTION_BATTLE_SCRIPT_TEXT_OFFSET['size'], sect_data))

        # Changing offset code
        self.section_raw_data[8].extend(raw_ai_offset)
        self.section_raw_data[8].extend(raw_ai_section)
        txt_offset_data = game_data.SECTION_BATTLE_SCRIPT_TEXT_OFFSET
        for x in self.battle_script_data['text_offset']:
            self.section_raw_data[8].extend(x.to_bytes(txt_offset_data['size'], txt_offset_data['byteorder']))
        self.section_raw_data[8].extend(raw_data_save_text)

        # And now we can add section 8 !
        raw_data_to_write.extend(self.section_raw_data[8])

        # Now writing others section
        for i in range(9, self.NUMBER_SECTION):
            raw_data_to_write.extend(self.section_raw_data[i])

        # Modifying the header section now that all sized are known
        # Modifying the section position
        header_pos_data = game_data.SECTION_HEADER_SECTION_POSITION
        file_size = 0
        for i in range(0, self.NUMBER_SECTION):
            start = header_pos_data['offset'] + i * header_pos_data['size']
            end = start + header_pos_data['size']
            file_size += len(self.section_raw_data[i])
            self.section_raw_data[0][start:end] = self.__get_byte_from_int_from_game_data(file_size, header_pos_data)

        header_file_data = game_data.SECTION_HEADER_FILE_SIZE
        self.section_raw_data[0][header_file_data['offset']:header_file_data['offset'] + header_file_data['size']] = file_size.to_bytes(
            header_pos_data['size'], header_file_data['byteorder'])
        raw_data_to_write[0:len(self.section_raw_data[0])] = self.section_raw_data[0]

        # Write back on file
        with open(path, "wb") as f:
            f.write(raw_data_to_write)

    def __get_raw_data_from_game_data(self, sect_nb: int, sect_data: dict):
        sect_offset = self.header_data['section_pos'][sect_nb]
        sub_start = sect_offset + sect_data['offset']
        sub_end = sub_start + sect_data['size']
        return self.file_raw_data[sub_start:sub_end]

    def __get_byte_from_int_from_game_data(self, int_value, sect_data):
        return int_value.to_bytes(sect_data['size'], sect_data['byteorder'])

    def __add_section_raw_data_from_game_data(self, sect_nb: int, sect_data: dict, data=bytearray()):
        """If no data given, it uses the file_raw_data"""
        if len(data) == 0:
            data = self.__get_raw_data_from_game_data(sect_nb, sect_data)
        self.section_raw_data[sect_nb].extend(data)

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

    def __analyze_battle_script_section(self, game_data:GameData):
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
            #if i > 0 and text_list_raw_data == b'\x00\x00':  # Weird case where there is several pointer by the diff but several are 0 (which point to the same value)
            #    break
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
        self.battle_script_data['ai_data'] = []
        for index, code in enumerate(list_code):
            index_read = 0
            list_result = []
            while index_read < len(code):
                all_op_code_info = game_data.ai_data_json["op_code_info"]
                op_code_ref = [x for x in all_op_code_info if x["op_code"] == code[index_read]]
                if not op_code_ref and code[index_read] >= 0x40:
                    index_read += 1
                    continue
                elif op_code_ref:  # >0x40 not used
                    op_code_ref = op_code_ref[0]
                    start_param = index_read + 1
                    end_param = index_read + 1 + op_code_ref['size']
                    command = Command(code[index_read], code[start_param:end_param], game_data=game_data, battle_text=self.battle_script_data['battle_text'],
                                      info_stat_data_monster_name=self.info_stat_data['monster_name'], color=game_data.color)
                    list_result.append(command)
                    index_read += 1 + op_code_ref['size']
            self.battle_script_data['ai_data'].append(list_result)
        self.battle_script_data['ai_data'].append([])  # Adding a end section that is empty to mark the end of the all IA section

    def __remove_stop_end(self, list_result):
        id_remove = 0
        for i in range(len(list_result)):
            if list_result[i]['id'] == 0x00:  # STOP
                if i + 1 < len(list_result):
                    if list_result[i + 1]['id'] == 0x00:
                        id_remove = i + 1
                        break
        return list_result[:id_remove or None]
