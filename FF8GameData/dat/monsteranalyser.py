import copy
import io
import math
import os
import re
from math import floor
from typing import List

from IfritAI.AICompiler.AIDecompiler import AIDecompiler
from .sequenceanalyser import SequenceAnalyser
from ..GenericSection.ff8text import FF8Text
from ..gamedata import GameData
from .commandanalyser import CommandAnalyser, CurrentIfType
from ..monsterdata import BoneSection, GeometrySection, AnimationSection, AIData, AnimationFrame, BitReader, BitWriter, Animation

test = []


class GarbageFileError(IndexError):
    pass


class MonsterAnalyser:
    DAT_FILE_SECTION_LIST = ['header', 'skeleton', 'model_geometry', 'model_animation', 'unknown_section4', 'unknown_section5', 'unknown_section6', 'info_stat',
                             'battle_script', 'sound', 'unknown_section10', 'texture']
    MAX_MONSTER_TXT_IN_BATTLE = 10
    MAX_MONSTER_SIZE_TXT_IN_BATTLE = 100
    NUMBER_SECTION = len(DAT_FILE_SECTION_LIST)

    def __init__(self, game_data):
        self.file_raw_data = bytearray()
        self.origin_file_name = ""
        self.origin_path = ""
        self.origin_file_checksum = ""
        self.subsection_ai_offset = {'init_code': 0, 'ennemy_turn': 0, 'counter_attack': 0, 'death': 0, 'unknown': 0}
        self.section_raw_data = [bytearray()] * self.NUMBER_SECTION
        self.header_data = copy.deepcopy(AIData.SECTION_HEADER_DICT)
        self.bone_data = BoneSection()
        self.geometry_data = GeometrySection()
        self.animation_data = AnimationSection()
        self.model_animation_data = copy.deepcopy(AIData.SECTION_MODEL_ANIM_DICT)
        self.seq_animation_data = copy.deepcopy(AIData.SECTION_MODEL_SEQ_ANIM_DICT)
        self.info_stat_data = copy.deepcopy(AIData.SECTION_INFO_STAT_DICT)
        self.battle_script_data = copy.deepcopy(AIData.SECTION_BATTLE_SCRIPT_DICT)
        self.sound_data = bytes()  # Section 9
        self.sound_unknown_data = bytes()  # Section 10
        self.texture_data = copy.deepcopy(AIData.SECTION_TEXTURE_DICT)
        self._ai_command_list = []
        self.id:int = 0

    def __str__(self):
        return "Name: {} \nData:{}".format(self.info_stat_data['monster_name'],
                                           [self.header_data, self.model_animation_data, self.info_stat_data, self.battle_script_data])

    def load_file_data(self, file:str, game_data:GameData):
        self.subsection_ai_offset = {'init_code': 0, 'ennemy_turn': 0, 'counter_attack': 0, 'death': 0, 'unknown': 0}
        self.section_raw_data = [bytearray()] * self.NUMBER_SECTION
        self.bone_data = BoneSection()
        self.geometry_data = GeometrySection()
        self.animation_data = AnimationSection()
        self.header_data = copy.deepcopy(AIData.SECTION_HEADER_DICT)
        self.model_animation_data = copy.deepcopy(AIData.SECTION_MODEL_ANIM_DICT)
        self.info_stat_data = copy.deepcopy(AIData.SECTION_INFO_STAT_DICT)
        self.battle_script_data = copy.deepcopy(AIData.SECTION_BATTLE_SCRIPT_DICT)
        self.texture_data = copy.deepcopy(AIData.SECTION_TEXTURE_DICT)
        self.file_raw_data = bytearray()
        with open(file, "rb") as f:
            while el := f.read(1):
                self.file_raw_data.extend(el)
        self.__analyze_header_section(game_data)
        self.origin_file_name = os.path.basename(file)
        self.origin_path = file
        self.id = int(re.search(r'\d{3}', self.origin_file_name).group())
        # self.origin_file_checksum = get_checksum(file, algorithm='SHA256')



    def analyse_loaded_data(self, game_data: GameData, decompiler: AIDecompiler=None):
        try:
            for i in range(0, self.NUMBER_SECTION - 1):
                self.section_raw_data[i] = self.file_raw_data[self.header_data['section_pos'][i]: self.header_data['section_pos'][i + 1]]

            self.section_raw_data[self.NUMBER_SECTION - 1] = self.file_raw_data[
                                                             self.header_data['section_pos'][self.NUMBER_SECTION - 1]:self.header_data['file_size']]
            # No need to analyze Section 1 : Skeleton
            self.__analyze_bone_section(game_data)
            # No need to analyze Section 2 : Model geometry
            self.__analyze_geometry_section(game_data)
            # No need to analyze Section 3 : Model animation
            self.__analyze_animation_section(game_data)
            #self.__analyze_model_animation(game_data)
            # No need to analyze Section 4 : Unknown
            # self.__analyze_section_4(game_data)
            # No need to analyze Section 5 : Sequence Animation
            self.__analyze_sequence_animation(game_data)
            # No need to analyze Section 6 : Unknown
            # self.__analyze_section_6(game_data)
            # Analyzing Section 7 : Informations & stats
            self.__analyze_info_stat(game_data)
            # Analyzing Section 8 : Battle scripts/AI
            self.analyze_battle_script_section(game_data, decompiler)

            # No need to analyze Section 9 : Sounds
            # No need to analyze Section 10 : Sounds/Unknown
            # Section 11 : Textures
            self._analyze_texture_section(game_data)
        except IndexError as e:
            print(f"Garbage file {self.origin_file_name}")
            raise GarbageFileError

    def write_data_to_file(self, game_data: GameData, dat_path):
        raw_data_to_write = bytearray()

        # First writing header (fix size, will be modified later)
        section_position = 0
        raw_data_to_write.extend(self.section_raw_data[section_position])

        # Writing bone section
        section_position = 1
        bone_data = self.bone_data.to_binary()
        raw_data_to_write.extend(bone_data)

        # Writing geometry (untouched for the moment)
        section_position = 2
        raw_data_to_write.extend(self.section_raw_data[section_position])

        # Writing animation
        section_position = 3
        animation_data = self.animation_data.to_binary()
        raw_data_to_write.extend(animation_data)
        #raw_data_to_write.extend(self.section_raw_data[section_position])

        # Writing Texture animation data (no change atm)
        section_position = 4
        raw_data_to_write.extend(self.section_raw_data[section_position])

        # Monster seq animation
        section_position = 5
        # raw_data_to_write.extend(self.section_raw_data[section_position])
        self.section_raw_data[section_position] = bytearray()
        nb_seq = len(self.seq_animation_data['seq_animation_data'])



        ## Now compute offset
        offset_list = []
        current_offset = AIData.SECTION_MODEL_SEQ_ANIM_NB_SEQ['size'] + nb_seq * AIData.SECTION_MODEL_SEQ_ANIM_OFFSET['size']
        for index, seq in enumerate(self.seq_animation_data['seq_animation_data']):
            if len(seq['data']) == 0:
                self.seq_animation_data['seq_animation_data'][index]['offset'] = 0
            else:
                self.seq_animation_data['seq_animation_data'][index]['offset'] = current_offset
            current_offset+=len(seq['data'])

        current_id = 0
        while current_id < nb_seq:
            for index, seq in enumerate(self.seq_animation_data['seq_animation_data']):
                if seq["id"] != current_id:
                    continue
                offset_list.append(seq['offset'])
                current_id +=1
        ## Now construction the raw data:
        self.section_raw_data[section_position].extend(
            int.to_bytes(nb_seq, byteorder=AIData.SECTION_MODEL_SEQ_ANIM_NB_SEQ['byteorder'], length=AIData.SECTION_MODEL_SEQ_ANIM_NB_SEQ['size']))
        for offset in offset_list:
            self.section_raw_data[section_position].extend(
                int.to_bytes(offset, byteorder=AIData.SECTION_MODEL_SEQ_ANIM_OFFSET['byteorder'], length=AIData.SECTION_MODEL_SEQ_ANIM_OFFSET['size']))
        for seq in self.seq_animation_data['seq_animation_data']:
            self.section_raw_data[section_position].extend(seq['data'])
        raw_data_to_write.extend(self.section_raw_data[section_position])
        # Section 6: no analyze done yet
        section_position = 6
        raw_data_to_write.extend(self.section_raw_data[section_position])

        # Monster stat info
        section_position = 7
        self.section_raw_data[section_position] = bytearray()
        for param_name, value in self.info_stat_data.items():
            property_elem = [x for ind, x in enumerate(AIData.SECTION_INFO_STAT_LIST_DATA) if x['name'] == param_name][0]
            if param_name in ([x['name'] for x in game_data.stat_data_json['stat']] + ['card', 'devour']):  # List of 1 byte value
                value_to_set = bytes(value)
            elif param_name in ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'ap', 'nb_animation', 'padding']:
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
            elif param_name in AIData.ABILITIES_HIGHNESS_ORDER:
                value_to_set = bytearray()
                for el2 in value:
                    value_to_set.extend(el2['type'].to_bytes())
                    value_to_set.extend(el2['animation'].to_bytes())
                    value_to_set.extend(el2['id'].to_bytes(2, property_elem['byteorder']))
                value_to_set = bytes(value_to_set)
            elif param_name in AIData.BYTE_FLAG_LIST:
                byte = 0
                for i, bit in enumerate(value.values()):
                    byte |= (bit << i)
                value_to_set = bytes([byte])
            elif param_name in ['monster_name']:
                value.fill(24)
                value_to_set = value.get_data_hex()
            elif param_name in ['renzokuken']:
                value_to_set = bytearray()
                for i in range(len(value)):
                    value_to_set.extend(value[i].to_bytes(2, AIData.SECTION_INFO_STAT_RENZOKUKEN['byteorder']))
            else:  # Data that we don't modify in the excel
                print("Data not taken into account !")
                continue
            if value_to_set:
                self.section_raw_data[section_position].extend(value_to_set)
                # self.file_raw_data[self.header_data['section_pos'][section_position] + property_elem['offset']:
                #                    self.header_data['section_pos'][section_position] + property_elem['offset'] + property_elem['size']] = value_to_set

        raw_data_to_write.extend(self.section_raw_data[section_position])

        # Now creating the section 8
        # 3 subsection in section 8: The offset subsection (header), the AI and the texts

        self.section_raw_data[8] = bytearray()
        # First computing raw section (offset will be computed after)
        raw_ai_section = bytearray()
        raw_ai_offset = bytearray()
        raw_ai_subsection = []

        # first computing ai subsection
        for index, section in enumerate(self.battle_script_data['ai_data']):
            if section:  # Ignoring the last section that is empty
                raw_ai_subsection.append(bytearray())
                for command in section['command']:
                    raw_ai_subsection[-1].append(command.get_id())
                    raw_ai_subsection[-1].extend(command.get_op_code())

        # The offset need to take into account the different offset themselves !
        offset_value_current_ai_section = 0
        for offset in AIData.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA:
            offset_value_current_ai_section += offset['size']

        # Now computing AI offset and ai section
        for index, subsection in enumerate(raw_ai_subsection):
            raw_ai_offset.extend(
                self.__get_byte_from_int_from_game_data(offset_value_current_ai_section, AIData.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA[index]))
            offset_value_current_ai_section += len(subsection)
            raw_ai_section.extend(subsection)

        # Now analysing the text part. offset_value_current_ai_section point then to the end of AI sub-section, so the start of text offset
        raw_text_section = bytearray()
        raw_text_offset = bytearray()
        current_offset = 0
        for battle_text in self.battle_script_data['battle_text']:
            raw_text_offset.extend(current_offset.to_bytes(length=2, byteorder="little"))
            current_offset += len(battle_text)
        while len(raw_text_offset) % 4 != 0: #For rainbow bug
            raw_text_offset.extend([0x00])
        for battle_text in self.battle_script_data['battle_text']:
            raw_text_section.extend(battle_text.get_data_hex())
        while len(raw_text_section) % 4 != 0:
            raw_text_section.extend([0x00])

        # Now computing offset
        # Number of subsection doesn't change, neither the offset to AI-sub-section
        self.section_raw_data[8].extend(int(3).to_bytes(AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB['size'],AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB['byteorder']))
        self.section_raw_data[8].extend(int(16).to_bytes(AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB['size'],AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB['byteorder']))

        #self.__add_section_raw_data_from_game_data(8, AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB)
        #self.__add_section_raw_data_from_game_data(8, AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB)

        # Now adding others offset
        current_offset_section_compute = 0
        for offset_sect in AIData.SECTION_BATTLE_SCRIPT_BATTLE_SCRIPT_HEADER_LIST_DATA:
            current_offset_section_compute += offset_sect['size']
        current_offset_section_compute += len(raw_ai_offset)
        current_offset_section_compute += len(raw_ai_section)
        self.section_raw_data[8].extend(
            current_offset_section_compute.to_bytes(AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['size'],
                                                    AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['byteorder']))
        current_offset_section_compute += len(raw_text_offset)
        self.section_raw_data[8].extend(
            current_offset_section_compute.to_bytes(AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['size'],
                                                    AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB['byteorder']))

        current_offset_section_compute += len(raw_text_section)
        # Now adding the data
        self.section_raw_data[8].extend(raw_ai_offset)
        self.section_raw_data[8].extend(raw_ai_section)
        self.section_raw_data[8].extend(raw_text_offset)
        self.section_raw_data[8].extend(raw_text_section)

        # And now we can add section 8 !
        raw_data_to_write.extend(self.section_raw_data[8])

        # Now writing others section
        for i in range(9, self.NUMBER_SECTION-1):
            raw_data_to_write.extend(self.section_raw_data[i])

        # Texture
        section_position = 11
        # raw_data_to_write.extend(self.section_raw_data[section_position])
        self.section_raw_data[section_position] = bytearray()
        nb_texture = len(self.texture_data['texture_data'])
        ## Now compute offset
        tim_offset = []
        current_offset = AIData.SECTION_TEXTURE_NB['size'] + nb_texture * AIData.SECTION_TEXTURE_OFFSET['size'] +  AIData.SECTION_TEXTURE_END_OF_FILE['size']
        for index in range(len(self.texture_data['texture_data'])):
            tim_offset.append(current_offset)
            current_offset+=len(self.texture_data['texture_data'][index]['data'])
        eof_texture = current_offset
        ## Now construction the raw data:
        self.section_raw_data[section_position].extend(
            int.to_bytes(nb_texture, byteorder=AIData.SECTION_TEXTURE_NB['byteorder'], length=AIData.SECTION_TEXTURE_NB['size']))
        for offset in tim_offset:
            self.section_raw_data[section_position].extend(
                int.to_bytes(offset, byteorder=AIData.SECTION_TEXTURE_OFFSET['byteorder'], length=AIData.SECTION_TEXTURE_OFFSET['size']))
        self.section_raw_data[section_position].extend(
            int.to_bytes(eof_texture, byteorder=AIData.SECTION_TEXTURE_END_OF_FILE['byteorder'], length=AIData.SECTION_TEXTURE_END_OF_FILE['size']))
        for tex in self.texture_data['texture_data']:
            self.section_raw_data[section_position].extend(tex['data'])

        raw_data_to_write.extend(self.section_raw_data[section_position])


        # Modifying the header section now that all sized are known
        # Modifying the section position
        header_pos_data = AIData.SECTION_HEADER_SECTION_POSITION
        file_size = 0
        for i in range(0, self.NUMBER_SECTION):
            start = header_pos_data['offset'] + i * header_pos_data['size']
            end = start + header_pos_data['size']
            file_size += len(self.section_raw_data[i])
            self.section_raw_data[0][start:end] = self.__get_byte_from_int_from_game_data(file_size, header_pos_data)

        header_file_data = AIData.SECTION_HEADER_FILE_SIZE
        self.section_raw_data[0][header_file_data['offset']:header_file_data['offset'] + header_file_data['size']] = file_size.to_bytes(
            header_pos_data['size'], header_file_data['byteorder'])
        raw_data_to_write[0:len(self.section_raw_data[0])] = self.section_raw_data[0]

        # Write back on file
        with open(dat_path, "wb") as f:
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

    def __get_int_value_from_info(self, data_info, section_number=0, offset=0, signed=False):
        return int.from_bytes(self.__get_raw_value_from_info(data_info, section_number, offset), byteorder=data_info['byteorder'], signed=signed)

    def __get_raw_value_from_info(self, data_info, section_number=0, offset=0):
        if section_number == 0:
            section_offset = 0
        else:
            if section_number >= len(self.header_data['section_pos']):
                return bytearray(b'')
            section_offset = self.header_data['section_pos'][section_number]
        return self.file_raw_data[section_offset + data_info['offset'] + offset:section_offset + data_info['offset'] + data_info['size']+ offset]

    def __analyze_header_section(self, game_data: GameData):
        self.header_data['nb_section'] = self.__get_int_value_from_info(AIData.SECTION_HEADER_NB_SECTION)
        sect_position = [0]  # Adding to the list the header as a section 0
        for i in range(self.header_data['nb_section']):
            sect_position.append(
                int.from_bytes(self.file_raw_data[
                               AIData.SECTION_HEADER_SECTION_POSITION['offset'] + i * AIData.SECTION_HEADER_SECTION_POSITION['size']:
                               AIData.SECTION_HEADER_SECTION_POSITION['offset'] +
                               AIData.SECTION_HEADER_SECTION_POSITION['size'] * (i + 1)],
                               AIData.SECTION_HEADER_SECTION_POSITION['byteorder']))
        self.header_data['section_pos'] = sect_position
        file_size_section_offset = 4 + self.header_data['nb_section'] * 4
        self.header_data['file_size'] = int.from_bytes(
            self.file_raw_data[file_size_section_offset:file_size_section_offset + AIData.SECTION_HEADER_FILE_SIZE['size']],
            AIData.SECTION_HEADER_FILE_SIZE['byteorder'])

    def __analyze_bone_section(self, game_data: GameData):
        SECTION_NUMBER = 1
        if self.section_raw_data[SECTION_NUMBER]:
            self.bone_data.analyze(self.section_raw_data[SECTION_NUMBER])
            #print(self.bone_data)



    def __analyze_geometry_section(self, game_data: GameData):
        #print("__analyze_geometry_section")
        SECTION_NUMBER = 2
        if self.section_raw_data[SECTION_NUMBER]:
            self.geometry_data.analyze(self.section_raw_data[SECTION_NUMBER])

    def __analyze_animation_section(self, game_data: GameData):
        print("__analyze_animation_section")
        SECTION_NUMBER = 3
        if self.section_raw_data[SECTION_NUMBER]:
            self.animation_data.analyze(self.section_raw_data[SECTION_NUMBER], self.bone_data)
            #print(self.animation_data)

        # Run the comprehensive tests
        # self.debug_last_frame_detailed()
        # self.debug_animation_frame_counts()
        # self.test_full_animation_section_roundtrip(game_data)
        # self.test_large_binary_roundtrip()
        # self.debug_animation_binary()
        # self.debug_animation_section_offsets()
        # self.debug_animation_boundary(0)
        # self.debug_animation_1_difference()
        # self.debug_animation_19_end_bytes()
        # self.debug_bit_pattern_at_end()
        self.debug_all_animations_last_bytes()

    def debug_all_animations_last_bytes(self):
        """Compare last 10 bytes of each animation between original and rebuilt"""
        print("\n" + "=" * 80)
        print("COMPARING LAST 10 BYTES OF EACH ANIMATION")
        print("=" * 80)

        original_section = self.section_raw_data[3]

        print(f"\n{'Anim':<6} {'Orig Size':<10} {'Rebuilt Size':<12} {'Match':<8} {'Last 10 bytes (original)':<35} {'Last 10 bytes (rebuilt)'}")
        print("-" * 120)

        for anim_idx in range(len(self.animation_data.animations)):
            # Get original animation data
            anim_start = self.animation_data.offsets[anim_idx]
            if anim_idx + 1 < len(self.animation_data.offsets):
                anim_end = self.animation_data.offsets[anim_idx + 1]
            else:
                anim_end = len(original_section)

            original_data = original_section[anim_start:anim_end]
            original_size = len(original_data)

            # Get rebuilt animation data
            anim = self.animation_data.animations[anim_idx]
            rebuilt_data = anim.to_binary()
            rebuilt_size = len(rebuilt_data)

            # Get last 10 bytes (or fewer if animation is smaller)
            orig_last_10 = original_data[-10:] if original_size >= 10 else original_data
            rebuilt_last_10 = rebuilt_data[-10:] if rebuilt_size >= 10 else rebuilt_data

            # Check if sizes match
            size_match = "✅" if original_size == rebuilt_size else "❌"

            # Check if last 10 bytes match
            bytes_match = "✅" if orig_last_10 == rebuilt_last_10 else "⚠️"

            # Format hex strings
            orig_hex = orig_last_10.hex()
            rebuilt_hex = rebuilt_last_10.hex()

            print(f"{anim_idx:<6} {original_size:<10} {rebuilt_size:<12} {size_match}{bytes_match:<7} {orig_hex:<35} {rebuilt_hex}")

            # If sizes don't match, show the difference
            if original_size != rebuilt_size:
                diff = original_size - rebuilt_size
                print(f"      → Size difference: {diff:+d} bytes ({'missing' if diff > 0 else 'extra'} {abs(diff)} byte{'s' if abs(diff) != 1 else ''})")

            # If last 10 bytes don't match, show where they differ
            if orig_last_10 != rebuilt_last_10:
                # Find first difference from the end
                min_len = min(len(orig_last_10), len(rebuilt_last_10))
                for i in range(min_len):
                    if orig_last_10[i] != rebuilt_last_10[i]:
                        offset_from_end = len(orig_last_10) - i
                        print(f"      → First difference at {offset_from_end} bytes from end: orig=0x{orig_last_10[i]:02x}, rebuilt=0x{rebuilt_last_10[i]:02x}")
                        break

        print("\n" + "=" * 80)

        # Summary
        print("\n📊 SUMMARY:")
        size_matches = 0
        for i in range(len(self.animation_data.animations)):
            anim_start = self.animation_data.offsets[i]
            if i + 1 < len(self.animation_data.offsets):
                anim_end = self.animation_data.offsets[i + 1]
            else:
                anim_end = len(original_section)
            original_size = anim_end - anim_start
            rebuilt_size = len(self.animation_data.animations[i].to_binary())
            if original_size == rebuilt_size:
                size_matches += 1

        total_anims = len(self.animation_data.animations)
        print(f"  Size matches: {size_matches}/{total_anims} animations")

        # Check which animations have perfect last bytes
        perfect_matches = 0
        for anim_idx in range(len(self.animation_data.animations)):
            anim_start = self.animation_data.offsets[anim_idx]
            if anim_idx + 1 < len(self.animation_data.offsets):
                anim_end = self.animation_data.offsets[anim_idx + 1]
            else:
                anim_end = len(original_section)
            original_data = original_section[anim_start:anim_end]
            rebuilt_data = self.animation_data.animations[anim_idx].to_binary()

            if len(original_data) == len(rebuilt_data) and original_data[-10:] == rebuilt_data[-10:]:
                perfect_matches += 1

        print(f"  Perfect last 10 bytes matches: {perfect_matches}/{total_anims} animations")

        # List animations with issues
        print(f"\n⚠️ ANIMATIONS WITH ISSUES:")
        issues_found = False
        for anim_idx in range(len(self.animation_data.animations)):
            anim_start = self.animation_data.offsets[anim_idx]
            if anim_idx + 1 < len(self.animation_data.offsets):
                anim_end = self.animation_data.offsets[anim_idx + 1]
            else:
                anim_end = len(original_section)
            original_data = original_section[anim_start:anim_end]
            rebuilt_data = self.animation_data.animations[anim_idx].to_binary()

            if len(original_data) != len(rebuilt_data) or original_data[-10:] != rebuilt_data[-10:]:
                issues_found = True
                print(f"  Animation {anim_idx}: size={len(original_data)} vs {len(rebuilt_data)}, last_bytes_match={original_data[-10:] == rebuilt_data[-10:]}")

        if not issues_found:
            print("  None! All animations match perfectly!")
    def debug_bit_pattern_at_end(self):
        """Debug the exact bit patterns at the end of animation 19"""
        print("\n" + "=" * 60)
        print("DEBUG BIT PATTERNS AT END OF ANIMATION 19")
        print("=" * 60)

        original_section = self.section_raw_data[3]
        anim_start = self.animation_data.offsets[19]
        anim_end = self.animation_data.offsets[20] if 20 < len(self.animation_data.offsets) else len(original_section)
        original_data = original_section[anim_start:anim_end]

        # Get the last 4 bytes
        print(f"\n--- Last 4 bytes of original animation 19 ---")
        last_4_orig = original_data[-4:]
        print(f"Bytes: {last_4_orig.hex()}")
        print(f"Binary: {' '.join(f'{b:08b}' for b in last_4_orig)}")

        # Get the rebuilt data
        anim = self.animation_data.animations[19]
        rebuilt_data = anim.to_binary()

        print(f"\n--- Last 4 bytes of rebuilt animation 19 ---")
        last_4_rebuilt = rebuilt_data[-4:]
        print(f"Bytes: {last_4_rebuilt.hex()}")
        print(f"Binary: {' '.join(f'{b:08b}' for b in last_4_rebuilt)}")

        # Simulate writing with a BitWriter to see the buffer state
        print(f"\n--- Simulating BitWriter for animation 19 ---")
        writer = BitWriter()

        # Write frame count (8 bits)
        print(f"Before frame count: buffer={writer._buffer:08b} ({writer._bits_in_buffer} bits)")
        writer.write_bits(len(anim.frames), 8)
        print(f"After frame count: buffer={writer._buffer:08b} ({writer._bits_in_buffer} bits)")

        # Write all frames
        prev_frame = None
        for i, frame in enumerate(anim.frames):
            before_bytes = len(writer._data)
            before_bits = writer._bits_in_buffer
            frame.write_to_writer(writer, prev_frame)
            after_bytes = len(writer._data)
            after_bits = writer._bits_in_buffer
            prev_frame = frame
            if i == len(anim.frames) - 1:  # Last frame
                print(f"\nAfter last frame:")
                print(f"  Bytes written: {after_bytes}")
                print(f"  Bits in buffer: {after_bits}")
                print(f"  Buffer value: 0x{writer._buffer:02x} ({writer._buffer:08b})")

                # Show what gets flushed
                if after_bits > 0:
                    flushed_byte = writer._buffer & 0xFF
                    print(f"  Would flush: 0x{flushed_byte:02x} ({flushed_byte:08b})")

        # Now flush and see what we get
        writer.flush()
        print(f"\nAfter flush:")
        print(f"  Total bytes: {len(writer._data)}")
        print(f"  Last byte: 0x{writer._data[-1]:02x} ({writer._data[-1]:08b})")

        # Compare with original's last byte
        print(f"\n--- Comparison ---")
        orig_last_byte = original_data[-1]
        rebuilt_last_byte = writer._data[-1] if writer._data else 0
        print(f"Original last byte: 0x{orig_last_byte:02x} ({orig_last_byte:08b})")
        print(f"Rebuilt last byte:  0x{rebuilt_last_byte:02x} ({rebuilt_last_byte:08b})")

        # Check if the rebuilt's last byte matches the original's second-to-last byte
        if len(original_data) >= 2:
            orig_second_last = original_data[-2]
            print(f"Original second-to-last: 0x{orig_second_last:02x} ({orig_second_last:08b})")

            if rebuilt_last_byte == orig_second_last:
                print("\n✅ Rebuilt's last byte matches original's second-to-last byte!")
                print("   This means the bits are shifted by one byte - we have an extra byte at the end")
            elif rebuilt_last_byte == (orig_last_byte >> 4) or rebuilt_last_byte == (orig_last_byte & 0x0F):
                print("\n⚠️ Rebuilt's last byte matches part of original's last byte - bit shift issue!")

        # Check the actual data difference
        print(f"\n--- The 0x51 vs 0x01 difference ---")
        print(f"Original byte at offset -2: 0x{original_data[-2]:02x} (binary: {original_data[-2]:08b})")
        print(f"Rebuilt byte at offset -1:  0x{rebuilt_data[-1]:02x} (binary: {rebuilt_data[-1]:08b})")

        # Show what the original's last byte contains
        if len(original_data) >= 1:
            last_byte_bits = original_data[-1]
            print(f"\nOriginal's last byte 0x{last_byte_bits:02x} contains {last_byte_bits:08b}")
            print(f"If we shift right by 4 bits: 0x{last_byte_bits >> 4:02x} ({last_byte_bits >> 4:08b})")
            print(f"If we mask lower 4 bits: 0x{last_byte_bits & 0x0F:02x} ({last_byte_bits & 0x0F:08b})")
    def debug_animation_19_end_bytes(self):
        """Debug the last bytes of animation 19 to see exact differences"""
        print("\n" + "=" * 60)
        print("DEBUG ANIMATION 19 - LAST BYTES COMPARISON")
        print("=" * 60)

        original_section = self.section_raw_data[3]
        anim_index = 19

        # Get original animation data
        anim_start = self.animation_data.offsets[anim_index]
        if anim_index + 1 < len(self.animation_data.offsets):
            anim_end = self.animation_data.offsets[anim_index + 1]
        else:
            anim_end = len(original_section)

        original_anim_data = original_section[anim_start:anim_end]

        # Get rebuilt animation data
        anim = self.animation_data.animations[anim_index]
        rebuilt_anim_data = anim.to_binary()

        print(f"\n--- Size Comparison ---")
        print(f"Original animation size: {len(original_anim_data)} bytes")
        print(f"Rebuilt animation size:  {len(rebuilt_anim_data)} bytes")
        print(f"Difference: {len(original_anim_data) - len(rebuilt_anim_data)} bytes")

        # Compare last 20 bytes
        print(f"\n--- Last 20 bytes (hex) ---")
        orig_last_20 = original_anim_data[-20:] if len(original_anim_data) >= 20 else original_anim_data
        rebuilt_last_20 = rebuilt_anim_data[-20:] if len(rebuilt_anim_data) >= 20 else rebuilt_anim_data

        print(f"Original: {orig_last_20.hex()}")
        print(f"Rebuilt:  {rebuilt_last_20.hex()}")

        # Compare byte by byte from the end
        print(f"\n--- Byte-by-byte comparison from the end ---")
        min_len = min(len(original_anim_data), len(rebuilt_anim_data))
        diff_count = 0

        for i in range(1, min_len + 1):
            orig_byte = original_anim_data[-i]
            rebuilt_byte = rebuilt_anim_data[-i]
            if orig_byte != rebuilt_byte:
                diff_count += 1
                if diff_count <= 10:  # Show first 10 differences
                    print(f"  Offset from end -{i:3d} (absolute {len(original_anim_data) - i:4d}): orig=0x{orig_byte:02x}, rebuilt=0x{rebuilt_byte:02x}")

        if diff_count == 0:
            print("  ✅ No differences in overlapping bytes!")

        # Show the extra bytes if one is longer
        if len(original_anim_data) > len(rebuilt_anim_data):
            extra_bytes = original_anim_data[len(rebuilt_anim_data):]
            print(f"\n--- Extra bytes in original (not in rebuilt) ---")
            print(f"  {len(extra_bytes)} extra bytes at the end: {extra_bytes.hex()}")

            # Show the bytes that would be before these extra bytes
            if len(rebuilt_anim_data) >= 10:
                print(f"  Last 10 bytes of rebuilt: {rebuilt_anim_data[-10:].hex()}")
                print(f"  Expected continuation: {original_anim_data[len(rebuilt_anim_data) - 10:len(rebuilt_anim_data) + 10].hex()}")

        elif len(rebuilt_anim_data) > len(original_anim_data):
            extra_bytes = rebuilt_anim_data[len(original_anim_data):]
            print(f"\n--- Extra bytes in rebuilt (not in original) ---")
            print(f"  {len(extra_bytes)} extra bytes at the end: {extra_bytes.hex()}")

        # Check the frame count byte
        print(f"\n--- Frame count byte ---")
        print(f"Original first byte: 0x{original_anim_data[0]:02x} ({original_anim_data[0]})")
        print(f"Rebuilt first byte:  0x{rebuilt_anim_data[0]:02x} ({rebuilt_anim_data[0]})")

        # Check the last few bytes of the previous animation to see if there's overlap
        if anim_index > 0:
            print(f"\n--- Previous animation (18) end ---")
            prev_anim_start = self.animation_data.offsets[anim_index - 1]
            prev_anim_end = anim_start
            prev_anim_data = original_section[prev_anim_start:prev_anim_end]
            print(f"Animation 18 last 16 bytes: {prev_anim_data[-16:].hex()}")

            # Rebuild animation 18 to see its end
            prev_anim = self.animation_data.animations[anim_index - 1]
            prev_rebuilt = prev_anim.to_binary()
            print(f"Rebuilt animation 18 last 16 bytes: {prev_rebuilt[-16:].hex()}")

        # Show the actual bytes around the boundary
        print(f"\n--- Boundary between animations 18 and 19 ---")
        boundary_start = max(0, anim_start - 8)
        boundary_end = min(len(original_section), anim_start + 8)
        print(f"Original bytes around offset 0x{anim_start:04x}:")
        print(f"  {original_section[boundary_start:boundary_end].hex()}")

        # Show what the rebuilt data would be if we wrote sequentially
        print(f"\n--- Sequential write simulation ---")
        test_writer = BitWriter()
        for i in range(anim_index + 1):
            self.animation_data.animations[i].write_to_writer(test_writer)

        all_data = test_writer.get_data(flush=False)
        print(f"Total bytes written for animations 0-{anim_index}: {len(all_data)}")

        # Get just animation 19 from the sequential write
        # First, write animations 0-18 to get their size
        temp_writer = BitWriter()
        for i in range(anim_index):
            self.animation_data.animations[i].write_to_writer(temp_writer)
        anims_0_to_18_size = len(temp_writer.get_data(flush=False))

        # Now get animation 19 data from the sequential write
        anim_19_from_seq = all_data[anims_0_to_18_size:]
        print(f"Animation 19 from sequential write: {len(anim_19_from_seq)} bytes")
        print(f"Last 16 bytes from sequential: {anim_19_from_seq[-16:].hex() if len(anim_19_from_seq) >= 16 else anim_19_from_seq.hex()}")

        # Compare with standalone rebuilt
        if len(anim_19_from_seq) == len(rebuilt_anim_data):
            print("✅ Sequential and standalone match in size")
            if anim_19_from_seq == rebuilt_anim_data:
                print("✅ Sequential and standalone match exactly")
            else:
                print("❌ Sequential and standalone differ")
                # Find first difference
                for i in range(len(anim_19_from_seq)):
                    if anim_19_from_seq[i] != rebuilt_anim_data[i]:
                        print(f"  First difference at byte {i}: seq=0x{anim_19_from_seq[i]:02x}, standalone=0x{rebuilt_anim_data[i]:02x}")
                        break
        else:
            print(f"❌ Size mismatch: sequential={len(anim_19_from_seq)}, standalone={len(rebuilt_anim_data)}")
    def debug_animation_1_difference(self):
        """Debug the specific byte difference in Animation 1"""
        print("\n=== Debug Animation 1 Difference ===")

        original_section = self.section_raw_data[3]
        anim_index = 1

        anim_start = self.animation_data.offsets[anim_index]
        anim_end = self.animation_data.offsets[anim_index + 1]
        original_anim_data = original_section[anim_start:anim_end]

        anim = self.animation_data.animations[anim_index]
        rebuilt_anim_data = anim.to_binary()

        # The difference was at offset 1610 within animation 1
        diff_offset = 1610

        print(f"Animation 1 original size: {len(original_anim_data)}")
        print(f"Animation 1 rebuilt size: {len(rebuilt_anim_data)}")

        if diff_offset < len(original_anim_data) and diff_offset < len(rebuilt_anim_data):
            print(f"\nAt offset {diff_offset}:")
            print(f"  Original: 0x{original_anim_data[diff_offset]:02x}")
            print(f"  Rebuilt:  0x{rebuilt_anim_data[diff_offset]:02x}")

            # Show context around the difference
            start = max(0, diff_offset - 8)
            end = min(len(original_anim_data), diff_offset + 8)
            print(f"\nContext around offset {diff_offset}:")
            print(f"  Original: {original_anim_data[start:end].hex()}")
            print(f"  Rebuilt:  {rebuilt_anim_data[start:end].hex()}")

            # Check if this byte is part of a frame count or frame data
            # Find which frame contains this offset
            br = BitReader(original_anim_data, start_byte=1)
            frame_offsets = []
            for frame_idx in range(original_anim_data[0]):
                start_pos = br._byte_pos
                frame_offsets.append(start_pos)
                # Skip to next frame
                temp_frame = AnimationFrame(len(self.bone_data.bones))
                if frame_idx == 0:
                    temp_frame.move(br, None)
                    temp_frame.rotate_all_bones(br, None, self.bone_data.bones)
                else:
                    # Need prev_frame, but for offset calculation we just need to advance
                    temp_frame.move(br, None)
                    temp_frame.rotate_all_bones(br, None, self.bone_data.bones)

            # Find which frame contains diff_offset
            for i, offset in enumerate(frame_offsets):
                next_offset = frame_offsets[i + 1] if i + 1 < len(frame_offsets) else len(original_anim_data)
                if offset <= diff_offset < next_offset:
                    print(f"\nDifference is inside Frame {i} of Animation 1")
                    print(f"  Frame {i} spans bytes {offset}-{next_offset}")
                    print(f"  Offset within frame: {diff_offset - offset}")
                    break


    def debug_animation_boundary(self, anim_index=0):
        """Debug the boundary between two animations"""
        print(f"\n=== Debug Boundary After Animation {anim_index} ===")

        original_section = self.section_raw_data[3]

        # Get original animation data
        anim_start = self.animation_data.offsets[anim_index]
        anim_end = self.animation_data.offsets[anim_index + 1]
        original_anim_data = original_section[anim_start:anim_end]

        # Get rebuilt animation data
        anim = self.animation_data.animations[anim_index]
        rebuilt_anim_data = anim.to_binary()

        print(f"Animation {anim_index}:")
        print(f"  Original size: {len(original_anim_data)} bytes")
        print(f"  Rebuilt size:  {len(rebuilt_anim_data)} bytes")
        print(f"  Original last 8 bytes: {original_anim_data[-8:].hex()}")
        print(f"  Rebuilt last 8 bytes:  {rebuilt_anim_data[-8:].hex()}")

        # Get the next animation's start in original
        next_anim_start = self.animation_data.offsets[anim_index + 1]
        next_anim_original = original_section[next_anim_start:next_anim_start + 16]

        # Calculate where the next animation would start in rebuilt
        # The next animation's offset is the current offset + size of current animation
        rebuilt_next_start = len(rebuilt_anim_data)

        # Get the actual next animation's data from rebuilt (if we had it)
        next_anim = self.animation_data.animations[anim_index + 1]
        next_anim_rebuilt = next_anim.to_binary()

        print(f"\nNext animation ({anim_index + 1}):")
        print(f"  Original start offset: 0x{next_anim_start:04x}")
        print(f"  Original first 16 bytes: {next_anim_original[:16].hex()}")
        print(f"  Rebuilt first 16 bytes:  {next_anim_rebuilt[:16].hex()}")

        # Check if the rebuilt next animation would align with original if we shift by the bit residue
        print(f"\n--- Bit Residue Analysis ---")

        # Simulate writing animations sequentially to see bit residue
        writer = BitWriter()

        # Write all animations up to and including this one
        for i in range(anim_index + 1):
            self.animation_data.animations[i].write_to_writer(writer)

        # Get the data without final flush
        data_no_flush = writer.get_data(flush=False)
        bits_in_buffer = writer._bits_in_buffer
        buffer_value = writer._buffer

        print(f"After writing animations 0-{anim_index}:")
        print(f"  Total bytes (no flush): {len(data_no_flush)}")
        print(f"  Bits in buffer: {bits_in_buffer}")
        print(f"  Buffer value: 0x{buffer_value:02x}")

        # The next animation's frame count should start at a byte boundary
        # If there are bits in buffer, they belong to the previous animation's last frame

        # Check if the original has the same bit residue pattern
        # We can check by looking at the original data around the boundary

        # Get the last few bytes of original animation and first of next
        boundary_bytes = original_section[anim_end - 4:anim_end + 8]
        print(f"\nOriginal boundary bytes (last 4 of anim {anim_index}, first 8 of anim {anim_index + 1}):")
        print(f"  {boundary_bytes.hex()}")

        # Try to see if the bit residue matches
        if bits_in_buffer > 0:
            # The last byte of data_no_flush contains the bits from the buffer partially
            last_byte = data_no_flush[-1] if data_no_flush else 0
            print(f"\nLast byte of rebuilt data (no flush): 0x{last_byte:02x}")
            print(f"Buffer value: 0x{buffer_value:02x} ({bits_in_buffer} bits)")

            # The original might have these bits distributed differently
            # Let's check if the original's next animation frame count is affected
            original_next_frame_count = next_anim_original[0]
            print(f"Original next animation frame count: {original_next_frame_count}")

            # Simulate what would happen if we wrote the next animation with the current buffer
            test_writer = BitWriter()
            test_writer._data = bytearray(data_no_flush)
            test_writer._buffer = buffer_value
            test_writer._bits_in_buffer = bits_in_buffer

            # Write the next animation's frame count
            test_writer.write_byte(original_next_frame_count)
            print(f"After writing frame count with current buffer:")
            print(f"  Bytes now: {len(test_writer.get_data(flush=False))}")
            print(f"  First byte of frame count in stream: 0x{test_writer._data[-1] if test_writer._data else 0:02x}")
    def debug_animation_section_offsets(self):
        """Debug offset calculations"""
        print("\n=== Animation Section Offset Debug ===")

        data = bytearray()
        data.extend(self.animation_data.nb_animations.to_bytes(4, byteorder='little'))

        animations_data = []
        offsets = []
        current_offset = 4 + self.animation_data.nb_animations * 4

        for i, anim in enumerate(self.animation_data.animations):
            offsets.append(current_offset)
            anim_data = anim.to_binary()
            animations_data.append(anim_data)
            print(f"Animation {i:2d}: offset={current_offset:4d} (0x{current_offset:04x}), size={len(anim_data):4d}")
            current_offset += len(anim_data)

        # Compare with original offsets
        print(f"\nOriginal offsets from file:")
        for i in range(self.animation_data.nb_animations):
            orig_offset = self.animation_data.offsets[i]
            print(f"Animation {i:2d}: orig_offset=0x{orig_offset:04x} ({orig_offset})")
            if i < len(offsets):
                if offsets[i] != orig_offset:
                    diff = offsets[i] - orig_offset
                    print(f"  ❌ MISMATCH! Rebuilt={offsets[i]}, diff={diff:+d}")
    def debug_animation_binary(self):
        """Debug the full animation binary for animation 19"""
        print("\n=== Animation 19 Full Binary Debug ===")

        anim = self.animation_data.animations[19]

        # Get the animation binary
        anim_binary = anim.to_binary()

        print(f"Animation binary size: {len(anim_binary)} bytes")
        print(f"First byte (frame count): 0x{anim_binary[0]:02x} ({anim_binary[0]})")
        print(f"Expected frame count: {len(anim.frames)}")

        # Check if the frame count matches
        if anim_binary[0] != len(anim.frames):
            print(f"❌ MISMATCH! Frame count byte is {anim_binary[0]}, but should be {len(anim.frames)}")

            # Let's see what's happening in to_binary
            print("\n--- Simulating to_binary ---")
            test_data = bytearray()
            test_data.extend(len(anim.frames).to_bytes(1, 'little'))
            print(f"Frame count byte added: 0x{test_data[0]:02x}")

            writer = BitWriter()
            prev_frame = None
            for i, frame in enumerate(anim.frames):
                before = len(writer.get_data(False))
                frame.write_to_writer(writer, prev_frame)
                after = len(writer.get_data(False))
                print(f"Frame {i}: added {after - before} bytes, total bits in buffer: {writer._bits_in_buffer}")
                prev_frame = frame

            frame_data = writer.get_data()
            print(f"Frame data size: {len(frame_data)} bytes")
            print(f"Total size would be: {len(test_data) + len(frame_data)}")

            test_data.extend(frame_data)

            # Compare with anim_binary
            if test_data == anim_binary:
                print("✅ Simulated binary matches anim_binary")
            else:
                print("❌ Simulated binary differs from anim_binary")
                for i in range(min(len(test_data), len(anim_binary))):
                    if test_data[i] != anim_binary[i]:
                        print(f"  First difference at byte {i}: sim=0x{test_data[i]:02x}, actual=0x{anim_binary[i]:02x}")
                        break
        print(f"len(anim.frames) = {len(anim.frames)}")
        print(f"anim.frames[0] type: {type(anim.frames[0])}")
        print(f"Number of frames in list: {len(anim.frames)}")
    def debug_last_frame_detailed(self):
        """Deep debug for the last frame of the last animation"""
        print("\n" + "=" * 60)
        print("DEEP DEBUG FOR LAST FRAME OF ANIMATION 19")
        print("=" * 60)

        original_section = self.section_raw_data[3]
        anim_index = 19

        # Get original animation data
        anim_start = self.animation_data.offsets[anim_index]
        if anim_index + 1 < len(self.animation_data.offsets):
            anim_end = self.animation_data.offsets[anim_index + 1]
        else:
            anim_end = len(original_section)

        original_anim_data = original_section[anim_start:anim_end]
        anim = self.animation_data.animations[anim_index]

        print(f"\n--- Animation Info ---")
        print(f"Original animation size: {len(original_anim_data)} bytes")
        print(f"Number of frames: {len(anim.frames)}")

        # Get the last frame
        last_frame = anim.frames[-1]
        prev_frame = anim.frames[-2] if len(anim.frames) > 1 else None

        print(f"\n--- Last Frame Info ---")
        print(f"Mode bit: {last_frame.mode_bit}")
        print(f"Number of bones: {len(last_frame.rotation_vector_data)}")

        # Check position data
        print(f"\n--- Position Data (last frame) ---")
        for axis, pos in enumerate(last_frame.position):
            print(f"  Axis {axis}: type_bits={pos.position_type_bits}, raw={pos.get_pos_raw()}, world={pos.get_pos_world():.2f}")

        # Check rotation data for first few bones
        print(f"\n--- Rotation Data (last frame, first 5 bones) ---")
        for bone_idx in range(min(5, len(last_frame.rotation_vector_data))):
            print(f"  Bone {bone_idx}:")
            for axis, rot in enumerate(last_frame.rotation_vector_data[bone_idx]):
                print(
                    f"    Axis {axis}: avail={rot.is_rotation_type_available}, type_bits={rot.rotation_type_bits}, raw={rot.get_rotate_raw()}, deg={rot.get_rotate_deg():.2f}")

        # Check supplementary data if mode_bit is 1
        if last_frame.mode_bit == 1:
            print(f"\n--- Supplementary Data (last frame) ---")
            has_supp = False
            for bone_idx, supp in enumerate(last_frame.rotation_vector_data_supp):
                if supp.unk_flag1 or supp.unk_flag2 or supp.unk_flag3:
                    has_supp = True
                    print(f"  Bone {bone_idx}: flags=({supp.unk_flag1},{supp.unk_flag2},{supp.unk_flag3}), values=({supp.unk1},{supp.unk2},{supp.unk3})")
            if not has_supp:
                print("  No supplementary data present")

        # Write just the last frame and compare with original
        print(f"\n--- Last Frame Binary Comparison ---")
        last_frame_binary = last_frame.to_binary(prev_frame)
        print(f"Last frame binary size: {len(last_frame_binary)} bytes")
        print(f"Last frame binary (first 64 bytes): {last_frame_binary[:64].hex()}")

        # Find where the last frame starts in the original animation
        # We need to parse the original animation to find frame boundaries
        print(f"\n--- Finding Last Frame in Original ---")
        br = BitReader(original_anim_data, start_byte=1)  # Skip frame count
        frame_offsets = []
        frame_boundaries = []

        temp_anim = Animation()
        temp_anim.frames = []

        for frame_idx in range(original_anim_data[0]):
            start_pos = br._byte_pos
            start_bit = br._bit_pos
            frame_offsets.append((start_pos, start_bit))

            # Create a temporary frame to advance the reader
            temp_frame = AnimationFrame(len(self.bone_data.bones))
            if frame_idx == 0:
                temp_frame.move(br, None)
                temp_frame.rotate_all_bones(br, None, self.bone_data.bones)
            else:
                temp_frame.move(br, temp_anim.frames[-1])
                temp_frame.rotate_all_bones(br, temp_anim.frames[-1], self.bone_data.bones)

            temp_anim.frames.append(temp_frame)

            # Record where this frame ends
            end_pos = br._byte_pos
            end_bit = br._bit_pos
            frame_boundaries.append((end_pos, end_bit))

            print(f"  Frame {frame_idx:2d}: start=({start_pos}, bit{start_bit}), end=({end_pos}, bit{end_bit})")

        # Get the last frame's original data
        last_frame_start = frame_offsets[-1][0]
        last_frame_end = frame_boundaries[-1][0]
        if frame_boundaries[-1][1] > 0:
            last_frame_end += 1  # Include the partial byte

        original_last_frame_data = original_anim_data[last_frame_start:last_frame_end]
        print(f"\nOriginal last frame data: {len(original_last_frame_data)} bytes")
        print(f"Original last frame (first 64 bytes): {original_last_frame_data[:64].hex()}")

        # Compare original last frame with rebuilt last frame
        print(f"\n--- Comparing Last Frame Data ---")
        min_len = min(len(original_last_frame_data), len(last_frame_binary))
        differences = []

        for i in range(min_len):
            if original_last_frame_data[i] != last_frame_binary[i]:
                differences.append(i)
                if len(differences) <= 10:
                    print(f"Byte {i:3d}: orig=0x{original_last_frame_data[i]:02x}, rebuilt=0x{last_frame_binary[i]:02x}")

        if differences:
            print(f"\nTotal differences in last frame: {len(differences)} bytes")

            # Show context around first difference
            first_diff = differences[0]
            start = max(0, first_diff - 8)
            end = min(len(original_last_frame_data), first_diff + 16)
            print(f"\nContext around first difference (offset {first_diff}):")
            print(f"Original: {original_last_frame_data[start:end].hex()}")
            print(f"Rebuilt:  {last_frame_binary[start:end].hex()}")
        else:
            print("✅ Last frame matches perfectly!")

        # Check BitWriter state when writing the last frame
        print(f"\n--- BitWriter Analysis ---")
        writer = BitWriter()

        # Write all previous frames
        prev = None
        for i in range(len(anim.frames) - 1):
            anim.frames[i].write_to_writer(writer, prev)
            prev = anim.frames[i]

        print(f"Before writing last frame:")
        print(f"  Bytes written: {len(writer.get_data(flush=False))}")
        print(f"  Bits in buffer: {writer._bits_in_buffer}")
        print(f"  Buffer value: 0x{writer._buffer:02x}")

        # Write the last frame
        before_bytes = len(writer.get_data(flush=False))
        before_bits = writer._bits_in_buffer

        last_frame.write_to_writer(writer, prev)

        after_bytes = len(writer.get_data(flush=False))
        after_bits = writer._bits_in_buffer

        print(f"\nAfter writing last frame (before flush):")
        print(f"  Bytes written: {after_bytes}")
        print(f"  Bits in buffer: {after_bits}")
        print(f"  Buffer value: 0x{writer._buffer:02x}")
        print(f"  Bytes added: {after_bytes - before_bytes}")
        print(f"  Bits added: {(after_bytes - before_bytes) * 8 + after_bits - before_bits}")

        # Get data with and without flush
        data_no_flush = writer.get_data(flush=False)
        data_flush = writer.get_data(flush=True)

        print(f"\nFinal data:")
        print(f"  Without flush: {len(data_no_flush)} bytes, last byte: 0x{data_no_flush[-1]:02x}" if data_no_flush else "  No data")
        print(f"  With flush: {len(data_flush)} bytes, last byte: 0x{data_flush[-1]:02x}" if data_flush else "  No data")

        # Compare with original last frame's end
        print(f"\n--- End of Animation Comparison ---")
        print(f"Original animation last 16 bytes: {original_anim_data[-16:].hex()}")

        # Rebuild the entire animation using the shared writer approach and compare
        print(f"\n--- Shared Writer Test ---")
        test_writer = BitWriter()
        for f in anim.frames:
            f.write_to_writer(test_writer, None)  # No prev_frame for this test

        test_data = test_writer.get_data()
        print(f"Shared writer result: {len(test_data)} bytes")
        print(f"Shared writer last 16 bytes: {test_data[-16:].hex() if len(test_data) >= 16 else test_data.hex()}")

        # Check if the issue is with the frame count byte
        print(f"\n--- Frame Count Byte ---")
        print(f"Original frame count byte: 0x{original_anim_data[0]:02x} ({original_anim_data[0]})")
        print(f"Rebuilt frame count byte: 0x{last_frame_binary[0]:02x}" if last_frame_binary else "N/A")

        return differences
    def debug_animation_frame_counts(self):
        """Debug the frame counts for each animation"""
        print("\n=== Animation Frame Count Debug ===")

        original_section = self.section_raw_data[3]

        for anim_idx in range(len(self.animation_data.animations)):
            anim_start = self.animation_data.offsets[anim_idx]

            # Read original frame count
            orig_frame_count = original_section[anim_start] if anim_start < len(original_section) else 0

            # Get rebuilt frame count
            rebuilt_frame_count = len(self.animation_data.animations[anim_idx].frames)

            print(f"Animation {anim_idx:2d}: offset=0x{anim_start:04x}, orig_frames={orig_frame_count:3d}, rebuilt_frames={rebuilt_frame_count:3d}")

            if orig_frame_count != rebuilt_frame_count:
                print(f"  ❌ MISMATCH! Difference of {orig_frame_count - rebuilt_frame_count} frames")

                # Show the raw bytes around this offset
                start = max(0, anim_start - 4)
                end = min(len(original_section), anim_start + 20)
                print(f"  Raw bytes around offset: {original_section[start:end].hex()}")

    def test_full_animation_section_roundtrip(self, game_data: GameData):
        """Test if the entire animation section can be rebuilt identically"""

        print("\n=== Full Animation Section Round-Trip Test ===")

        SECTION_NUMBER = 3
        original_section = self.section_raw_data[SECTION_NUMBER]

        # Rebuild the entire animation section from parsed data
        rebuilt_section = self.animation_data.to_binary()

        print(f"Original section size: {len(original_section)} bytes")
        print(f"Rebuilt section size:  {len(rebuilt_section)} bytes")

        if len(original_section) != len(rebuilt_section):
            print(f"❌ SIZE MISMATCH: {len(original_section)} vs {len(rebuilt_section)}")
            print(f"Difference: {abs(len(original_section) - len(rebuilt_section))} bytes")

        # Compare byte by byte up to the smaller size
        compare_length = min(len(original_section), len(rebuilt_section))

        differences = []
        for i in range(compare_length):
            if original_section[i] != rebuilt_section[i]:
                differences.append(i)
                if len(differences) <= 20:  # Show first 20 differences
                    print(f"Byte {i:4d}: orig=0x{original_section[i]:02x}, rebuilt=0x{rebuilt_section[i]:02x}")

        if differences:
            print(f"\nTotal differences: {len(differences)} bytes")

            # Show context around first difference
            first_diff = differences[0]
            start = max(0, first_diff - 16)
            end = min(compare_length, first_diff + 16)
            print(f"\nContext around first difference (offset {first_diff}):")
            print(f"Original: {original_section[start:end].hex()}")
            print(f"Rebuilt:  {rebuilt_section[start:end].hex()}")

            # Determine if difference is in header or animation data
            nb_animations = int.from_bytes(original_section[0:4], 'little')
            header_size = 4 + nb_animations * 4

            if first_diff < header_size:
                print(f"\n⚠️ Difference is in the ANIMATION SECTION HEADER (offsets or count)")
                # Show header comparison
                print(f"\nHeader comparison:")
                print(f"Original header (first {header_size} bytes): {original_section[:header_size].hex()}")
                print(f"Rebuilt header (first {header_size} bytes):  {rebuilt_section[:header_size].hex()}")
            else:
                print(f"\n⚠️ Difference is inside animation data (after header)")

                # Find which animation contains this difference
                current_offset = header_size
                for anim_idx in range(nb_animations):
                    if anim_idx < len(self.animation_data.animations):
                        anim = self.animation_data.animations[anim_idx]
                        # Get the rebuilt animation data
                        anim_data = anim.to_binary()
                        anim_start = current_offset
                        anim_end = anim_start + len(anim_data)

                        if anim_start <= first_diff < anim_end:
                            offset_in_anim = first_diff - anim_start
                            print(f"  Difference is in Animation {anim_idx} at offset {offset_in_anim} within that animation")

                            # Compare this animation's data specifically
                            orig_anim_data = original_section[anim_start:anim_end]
                            if len(orig_anim_data) == len(anim_data):
                                print(f"  Animation {anim_idx} size matches ({len(anim_data)} bytes)")
                                # Find diff within this animation
                                for j in range(len(anim_data)):
                                    if orig_anim_data[j] != anim_data[j]:
                                        print(f"    Byte {j} in anim: orig=0x{orig_anim_data[j]:02x}, rebuilt=0x{anim_data[j]:02x}")
                                        break
                            else:
                                print(f"  Animation {anim_idx} size mismatch: orig={len(orig_anim_data)}, rebuilt={len(anim_data)}")
                            break

                        current_offset += len(anim_data)
        else:
            print("✅ Animation section matches perfectly!")

        return differences

    def test_large_binary_roundtrip(self, start_offset=0, num_bytes=500):
        """Test a raw binary round-trip on a chunk of the animation section"""

        print(f"\n=== Large Binary Round-Trip Test ({num_bytes} bytes from offset {start_offset}) ===")

        SECTION_NUMBER = 3
        original_section = self.section_raw_data[SECTION_NUMBER]

        # Take a chunk of the original section
        end_offset = min(start_offset + num_bytes, len(original_section))
        original_chunk = original_section[start_offset:end_offset]

        print(f"Original chunk size: {len(original_chunk)} bytes")
        print(f"Original chunk (first 64 bytes): {original_chunk[:64].hex()}")

        # Now we need to extract JUST the animation frames that correspond to this chunk
        # This is more complex - we need to find which frames cover this byte range

        # Alternative: Test round-trip on each animation individually
        print("\n--- Testing each animation individually ---")

        nb_animations = len(self.animation_data.animations)
        print(f"Total animations: {nb_animations}")

        for anim_idx, anim in enumerate(self.animation_data.animations):
            # Get original animation data from the section
            anim_start_offset = self.animation_data.offsets[anim_idx]

            if anim_idx + 1 < nb_animations:
                anim_end_offset = self.animation_data.offsets[anim_idx + 1]
            else:
                anim_end_offset = len(original_section)

            original_anim_data = original_section[anim_start_offset:anim_end_offset]
            rebuilt_anim_data = anim.to_binary()

            print(f"\nAnimation {anim_idx}:")
            print(f"  Original size: {len(original_anim_data)} bytes")
            print(f"  Rebuilt size:  {len(rebuilt_anim_data)} bytes")
            print(f"  Original offset in file: 0x{anim_start_offset:04x}")

            if len(original_anim_data) == len(rebuilt_anim_data):
                # Compare first 100 bytes of this animation
                compare_len = min(100, len(original_anim_data))
                match_count = 0
                first_diff = None

                for i in range(compare_len):
                    if original_anim_data[i] == rebuilt_anim_data[i]:
                        match_count += 1
                    else:
                        if first_diff is None:
                            first_diff = i
                            print(f"  First difference at byte {i} of animation data")
                            print(f"    Original: 0x{original_anim_data[i]:02x}")
                            print(f"    Rebuilt:  0x{rebuilt_anim_data[i]:02x}")
                            # Show surrounding bytes
                            start = max(0, i - 8)
                            end = min(len(original_anim_data), i + 8)
                            print(f"    Context (offset {start}-{end}):")
                            print(f"      Original: {original_anim_data[start:end].hex()}")
                            print(f"      Rebuilt:  {rebuilt_anim_data[start:end].hex()}")
                            break

                if first_diff is None:
                    print(f"  ✅ First {compare_len} bytes match!")
                    # Check if the frame count byte (first byte) matches
                    frame_count_orig = original_anim_data[0] if len(original_anim_data) > 0 else 0
                    frame_count_rebuilt = rebuilt_anim_data[0] if len(rebuilt_anim_data) > 0 else 0
                    print(f"  Frame count: original={frame_count_orig}, rebuilt={frame_count_rebuilt}")

                    # Check a few frame headers if possible
                    if len(original_anim_data) > 1:
                        print(f"  Second byte: orig=0x{original_anim_data[1]:02x}, rebuilt=0x{rebuilt_anim_data[1]:02x}")
            else:
                print(f"  ❌ Size mismatch: {len(original_anim_data)} vs {len(rebuilt_anim_data)}")

                # Show first few bytes of each
                print(f"  Original first 16 bytes: {original_anim_data[:16].hex()}")


    def __analyze_section_4(self, game_data: GameData):
        SECTION_NUMBER = 4
        if self.section_raw_data[SECTION_NUMBER]:
            #print("__analyze_section_4")
            print(self.section_raw_data[SECTION_NUMBER].hex(sep=" "))
            print(game_data.translate_hex_to_str(self.section_raw_data[SECTION_NUMBER]))

    def __analyze_section_6(self, game_data: GameData):
        SECTION_NUMBER = 6
        if self.section_raw_data[SECTION_NUMBER]:
            print("__analyze_section_6")
            print(self.section_raw_data[SECTION_NUMBER].hex(sep=" "))
            print(game_data.translate_hex_to_str(self.section_raw_data[SECTION_NUMBER]))
        test.append(self.section_raw_data[SECTION_NUMBER].hex(sep=" "))

    def __analyze_model_animation(self, game_data: GameData):
        #print("__analyze_model_animation")
        SECTION_NUMBER = 3
        print(self.section_raw_data[SECTION_NUMBER].hex(sep=" "))

        self.model_animation_data['nb_animation'] = self.__get_int_value_from_info(AIData.SECTION_MODEL_ANIM_NB_MODEL, SECTION_NUMBER)
        list_anim_offset = []
        offset_size = AIData.SECTION_MODEL_ANIM_OFFSET['size']
        start_offset = AIData.SECTION_MODEL_ANIM_NB_MODEL['size']
        for index_offset in range(self.model_animation_data['nb_animation']):
            list_anim_offset.append(
                int.from_bytes(self.section_raw_data[SECTION_NUMBER][start_offset + index_offset * offset_size:start_offset + (index_offset + 1) * offset_size],
                               byteorder="little"))
        # print(list_anim_offset)

        animation_list = []
        start_anim = start_offset + len(list_anim_offset) * offset_size

        for index, anim_offset in enumerate(list_anim_offset):
            # print(f"Start anim: {start_anim}")
            # print(f"index: {index}, anim_offset: {anim_offset}")
            if index == len(list_anim_offset) - 1:
                end_anim = len(self.section_raw_data[SECTION_NUMBER])
            else:
                end_anim = list_anim_offset[index + 1]
            # print(f"end_anim: {end_anim}")
            animation_list.append({'nb_frame': int(self.section_raw_data[SECTION_NUMBER][start_anim]),
                                   'unk': self.section_raw_data[SECTION_NUMBER][start_anim + 1: end_anim].hex(sep=" ")})
            start_anim = end_anim
        # print(animation_list)
        # for i, el in enumerate(animation_list):
        #    print(f"Index animation: {i}, Nb frame: {el['nb_frame']}, len_animation: {len(el['unk'])}")

    def __analyze_sequence_animation(self, game_data: GameData):
        SECTION_NUMBER = 5
        self.seq_animation_data['nb_anim_seq'] = self.__get_int_value_from_info(AIData.SECTION_MODEL_SEQ_ANIM_NB_SEQ, SECTION_NUMBER)
        list_seq_anim_offset = []
        offset_size = AIData.SECTION_MODEL_SEQ_ANIM_OFFSET['size']
        start_offset = AIData.SECTION_MODEL_SEQ_ANIM_NB_SEQ['size']
        for index_offset in range(self.seq_animation_data['nb_anim_seq']):
            list_seq_anim_offset.append(
                int.from_bytes(self.section_raw_data[SECTION_NUMBER][start_offset + index_offset * offset_size:start_offset + (index_offset + 1) * offset_size],
                               byteorder="little"))
        self.seq_animation_data['seq_anim_offset'] = list_seq_anim_offset
        animation_seq_list = []
        offset_list_done = []
        for index, anim_offset in enumerate(list_seq_anim_offset):
            start_anim = list_seq_anim_offset[index]
            if anim_offset == 0:
                end_anim = start_anim
            else:
                next_offset = [x for x in list_seq_anim_offset if x > anim_offset]
                if next_offset:
                    end_anim = min(next_offset)
                else:
                    end_anim = len(self.section_raw_data[SECTION_NUMBER])
            # Insert the data to have a continuous byte structure

            self.insert_sorted_with_zeros(offset_list_done, anim_offset)
            if anim_offset == 0:
                animation_seq_list.append({"id": index, "data":self.section_raw_data[SECTION_NUMBER][start_anim: end_anim]})
            else:
                animation_seq_list.insert(offset_list_done.index(anim_offset), {"id": index, "data":self.section_raw_data[SECTION_NUMBER][start_anim: end_anim]})

        self.seq_animation_data['seq_animation_data'] = animation_seq_list


    @staticmethod
    def insert_sorted_with_zeros(lst, value):
        if value == 0:
            lst.append(0)
            return lst

        # Get all non-zero values
        non_zeros = [x for x in lst if x != 0]

        # Find where to insert the value
        insert_pos = 0
        while insert_pos < len(non_zeros) and non_zeros[insert_pos] < value:
            insert_pos += 1

        # Insert in the list, skipping zeros
        count = 0
        for i in range(len(lst)):
            if lst[i] != 0:
                if count == insert_pos:
                    lst.insert(i, value)
                    return lst
                count += 1

        # If we got here, insert at the end before the zeros
        lst.append(value)
        return lst
    def __analyze_info_stat(self, game_data: GameData):
        SECTION_NUMBER = 7
        section_offset = self.header_data['section_pos'][SECTION_NUMBER]
        if section_offset == self.header_data['section_pos'][SECTION_NUMBER + 1]:
            print("Empty info stat, create a default one")
            default_name = FF8Text(game_data, 0, bytearray(), 0)
            default_name.set_str("DefaultMonsterName")
            self.info_stat_data = \
            {'monster_name': default_name, 'hp': [13, 1, 0, 0], 'str': [1, 1, 1, 255], 'vit': [2, 13, 1, 2], 'mag': [1, 5, 1, 250], 'spr': [2, 14, 2, 2],
             'spd': [0, 7, 17, 14], 'eva': [0, 6, 0, 12],
             'abilities_low': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 2, 'animation': 11, 'id': 1}, {'type': 4, 'animation': 11, 'id': 1},
                               {'type': 4, 'animation': 11, 'id': 18}, {'type': 2, 'animation': 11, 'id': 4}, {'type': 2, 'animation': 11, 'id': 7},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}],
             'abilities_med': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 2, 'animation': 11, 'id': 2}, {'type': 4, 'animation': 11, 'id': 2},
                               {'type': 4, 'animation': 11, 'id': 18}, {'type': 2, 'animation': 11, 'id': 5}, {'type': 2, 'animation': 11, 'id': 8},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                               {'type': 0, 'animation': 0, 'id': 0}],
             'abilities_high': [{'type': 8, 'animation': 12, 'id': 2}, {'type': 2, 'animation': 11, 'id': 3}, {'type': 4, 'animation': 11, 'id': 3},
                                {'type': 4, 'animation': 11, 'id': 18}, {'type': 2, 'animation': 11, 'id': 6}, {'type': 2, 'animation': 11, 'id': 9},
                                {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                                {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                                {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0}, {'type': 0, 'animation': 0, 'id': 0},
                                {'type': 0, 'animation': 0, 'id': 0}], 'med_lvl': 25, 'high_lvl': 45,
             'byte_flag_0': {'byte0_zz1': 1, 'byte0_zz2': 1, 'byte0_zz3': 0, 'byte0_unused4': 0, 'byte0_unused5': 0, 'byte0_unused6': 0, 'byte0_unused7': 0, 'byte0_unused8': 0},
             'byte_flag_1': {'Zombie': 0, 'Fly': 0, 'byte1_zz1': 0, 'Immune NVPlus_Moins': 0, 'Hidden HP': 0, 'Auto-Reflect': 0, 'Auto-Shell': 0, 'Auto-Protect': 0},
             'card': [255, 255, 255], 'devour': [255, 255, 255],
             'byte_flag_2': {'IncreaseSurpriseRNG': 0, 'DecreaseSurpriseRNG': 0, 'SurpriseAttackImmunity': 0, 'IncreaseChanceEscape': 1, 'DecreaseChanceEscape': 0,
                             'byte2_unused_6': 0, 'Diablos-missed': 0, 'Always obtains card': 0},
             'byte_flag_3': {'byte3_zz1': 0, 'byte3_zz2': 0, 'byte3_zz3': 0, 'byte3_zz4': 1, 'byte3_unused_5': 0, 'byte3_unused_6': 0, 'byte3_unused_7': 0, 'byte3_unused_8': 0},
             'extra_xp': 3, 'xp': 20, 'low_lvl_mag': [{'ID': 1, 'value': 0}, {'ID': 7, 'value': 0}, {'ID': 4, 'value': 0}, {'ID': 21, 'value': 0}],
             'med_lvl_mag': [{'ID': 2, 'value': 0}, {'ID': 8, 'value': 0}, {'ID': 5, 'value': 0}, {'ID': 22, 'value': 0}],
             'high_lvl_mag': [{'ID': 3, 'value': 0}, {'ID': 9, 'value': 0}, {'ID': 6, 'value': 0}, {'ID': 23, 'value': 0}],
             'low_lvl_mug': [{'ID': 1, 'value': 1}, {'ID': 1, 'value': 1}, {'ID': 7, 'value': 1}, {'ID': 7, 'value': 1}],
             'med_lvl_mug': [{'ID': 1, 'value': 1}, {'ID': 7, 'value': 1}, {'ID': 3, 'value': 1}, {'ID': 3, 'value': 1}],
             'high_lvl_mug': [{'ID': 3, 'value': 1}, {'ID': 7, 'value': 2}, {'ID': 7, 'value': 2}, {'ID': 7, 'value': 2}],
             'low_lvl_drop': [{'ID': 1, 'value': 1}, {'ID': 1, 'value': 1}, {'ID': 101, 'value': 8}, {'ID': 7, 'value': 1}],
             'med_lvl_drop': [{'ID': 1, 'value': 1}, {'ID': 1, 'value': 1}, {'ID': 7, 'value': 1}, {'ID': 7, 'value': 1}],
             'high_lvl_drop': [{'ID': 1, 'value': 2}, {'ID': 1, 'value': 2}, {'ID': 7, 'value': 2}, {'ID': 7, 'value': 2}], 'mug_rate': 50.19607843137255,
             'drop_rate': 50.19607843137255, 'padding': 0, 'ap': 1, 'renzokuken': [160, 160, 160, 141, 259, 332, 333, 259], 'elem_def': [100, 100, 100, 100, 200, 100, 100, 100],
             'status_def': [30, 20, 30, 20, 20, 40, 30, 20, 0, 10, 50, 0, 0, 20, 30, 0, 40, 0, 20, 0]}
            return

        for el in AIData.SECTION_INFO_STAT_LIST_DATA:
            raw_data_selected = self.__get_raw_value_from_info(el, SECTION_NUMBER)
            data_size = len(raw_data_selected)
            if el['name'] in ['monster_name']:
                value = FF8Text(game_data=game_data, own_offset=0, data_hex=raw_data_selected, id=0)
            elif el['name'] in ([x['name'] for x in game_data.stat_data_json['stat']] + ['card', 'devour']):
                value = list(raw_data_selected)
            elif el['name'] in ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'ap', 'padding']:
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
            elif el['name'] in AIData.ABILITIES_HIGHNESS_ORDER:
                list_data = list(raw_data_selected)
                value = []
                for i in range(0, data_size - 1, 4):
                    value.append({'type': list_data[i], 'animation': list_data[i + 1], 'id': int.from_bytes(list_data[i + 2:i + 4], el['byteorder'])})
            elif el['name'] in ['status_def']:  # Case with elem
                value = list(raw_data_selected)
                for i in range(data_size):
                    value[i] = value[i] - 100  # Give percentage, 155 means immune.
            elif el['name'] in AIData.BYTE_FLAG_LIST:  # Flag in byte management
                byte_value = format((int.from_bytes(raw_data_selected)), '08b')[::-1]  # Reversing
                value = {}
                if el['name'] == 'byte_flag_0':
                    byte_list = AIData.SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE
                elif el['name'] == 'byte_flag_1':
                    byte_list = AIData.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE
                elif el['name'] == 'byte_flag_2':
                    byte_list = AIData.SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE
                elif el['name'] == 'byte_flag_3':
                    byte_list = AIData.SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE
                else:
                    print("Unexpected byte flag {}".format(el['name']))
                    byte_list = AIData.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE
                for index, bit_name in enumerate(byte_list):
                    value[bit_name] = +bool(int(byte_value[index]))
            elif el['name'] in 'renzokuken':
                value = []
                for i in range(0, el['size'], 2):  # List of 8 value of 2 bytes
                    value.append(int.from_bytes(raw_data_selected[i:i + 2], el['byteorder']))
            else:
                value = "ERROR UNEXPECTED VALUE"
                print("Unexpected name while analyzing info stat: {}".format(el['name']))

            self.info_stat_data[el['name']] = value

    def analyze_battle_script_section(self, game_data: GameData, decompiler:AIDecompiler=None):
        if not decompiler:
            decompiler = AIDecompiler(game_data)
        SECTION_NUMBER = 8
        if len(self.header_data['section_pos']) <= SECTION_NUMBER:
            return
        section_offset = self.header_data['section_pos'][SECTION_NUMBER]

        # If the size is actually 0, we need to construct manually the minimum data
        if section_offset == self.header_data['section_pos'][SECTION_NUMBER+1]:
            print("Empty AI data, creating a basic one")
            self.battle_script_data = {'battle_nb_sub': 3, 'offset_ai_sub': 16, 'offset_text_offset': 56, 'offset_text_sub': 56, 'text_offset': [], 'battle_text': [], 'ai_data': [{'bytecode': [0, 0, 0, 0], 'code': 'stop();\nstop();\nstop();\nstop();\n', 'command': [CommandAnalyser(0, [], game_data,  line_index= 0), CommandAnalyser(0, [], game_data,  line_index= 1),CommandAnalyser(0, [], game_data,  line_index= 2), CommandAnalyser(0, [], game_data,  line_index= 3)]}, {'bytecode': [0, 0, 0, 0], 'code': 'stop();\nstop();\nstop();\nstop();\n', 'command': [CommandAnalyser(0, [], game_data,  line_index= 0), CommandAnalyser(0, [], game_data,  line_index= 1), CommandAnalyser(0, [], game_data,  line_index= 2), CommandAnalyser(0, [], game_data,  line_index= 3)]}, {'bytecode': [0, 0, 0, 0], 'code': 'stop();\nstop();\nstop();\nstop();\n', 'command': [CommandAnalyser(0, [], game_data,  line_index= 0), CommandAnalyser(0, [], game_data,  line_index= 1), CommandAnalyser(0, [], game_data,  line_index= 2), CommandAnalyser(0, [], game_data,  line_index= 3)]}, {'bytecode': [0, 0, 0, 0], 'code': 'stop();\nstop();\nstop();\nstop();\n', 'command': [CommandAnalyser(0, [], game_data,  line_index= 0), CommandAnalyser(0, [], game_data,  line_index= 1), CommandAnalyser(0, [], game_data,  line_index= 2), CommandAnalyser(0, [], game_data,  line_index= 3)]}, {'bytecode': [0, 0, 0, 0], 'code': 'stop();\nstop();\nstop();\nstop();\n', 'command': [CommandAnalyser(0, [], game_data,  line_index= 0), CommandAnalyser(0, [], game_data,  line_index= 1), CommandAnalyser(0, [], game_data,  line_index= 2), CommandAnalyser(0, [], game_data,  line_index= 3)]}, {}], 'offset_init_code': 20, 'offset_ennemy_turn': 24, 'offset_counterattack': 28, 'offset_death': 32, 'offset_before_dying_or_hit': 36}
            return
        # Reading header
        self.battle_script_data['battle_nb_sub'] = self.__get_int_value_from_info(AIData.SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_NUMBER)
        self.battle_script_data['offset_ai_sub'] = self.__get_int_value_from_info(AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB, SECTION_NUMBER)
        self.battle_script_data['offset_text_offset'] = self.__get_int_value_from_info(AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB,
                                                                                       SECTION_NUMBER)
        self.battle_script_data['offset_text_sub'] = self.__get_int_value_from_info(AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB,
                                                                                    SECTION_NUMBER)

        # Reading text offset subsection
        nb_text = self.battle_script_data['offset_text_sub'] - self.battle_script_data['offset_text_offset']
        for i in range(0, nb_text, AIData.SECTION_BATTLE_SCRIPT_TEXT_OFFSET['size']):
            start_data = section_offset + self.battle_script_data['offset_text_offset'] + i
            end_data = start_data + AIData.SECTION_BATTLE_SCRIPT_TEXT_OFFSET['size']
            text_list_raw_data = self.file_raw_data[start_data:end_data]
            if i > 0 and text_list_raw_data == b'\x00\x00':  # Padding added to have %4 size
                break
            self.battle_script_data['text_offset'].append(
                int.from_bytes(text_list_raw_data, byteorder=AIData.SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB['byteorder']))
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
                self.battle_script_data['battle_text'].append(FF8Text(game_data=game_data, own_offset=0, data_hex=combat_text_raw_data, id=0))
            else:
                self.battle_script_data['battle_text'] = []

        decompiler.set_battle_text_info_stat(self.battle_script_data['battle_text'])

        # Reading AI subsection

        ## Reading offset
        ai_offset = section_offset + self.battle_script_data['offset_ai_sub']
        for offset_param in AIData.SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA:
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
            decompiler.set_battle_text_info_stat(self.battle_script_data['battle_text'], self.info_stat_data)
            command_list_decompiled = decompiler.decompile_bytecode_to_command_list(code)
            code_decompiled = decompiler.decompile(code)
            self.battle_script_data['ai_data'].append({"bytecode": code, "code": code_decompiled, "command": command_list_decompiled})
        self.battle_script_data['ai_data'].append({})  # Adding a end section that is empty to mark the end of the all IA section
    def insert_command(self, code_section_id: int, command: CommandAnalyser, index_insertion: int = 0):
        self.battle_script_data['ai_data'][code_section_id]["command"].insert(index_insertion, command)

    def append_command(self, code_section_id: int, command: CommandAnalyser):
        self.battle_script_data['ai_data'][code_section_id]["command"].append(command)

    def remove_command(self, code_section_id: int, index_removal: int = 0):
        #if self.battle_script_data['ai_data'][code_section_id]["command"]:
        del self.battle_script_data['ai_data'][code_section_id]["command"][index_removal]

    def _analyze_texture_section(self, game_data: GameData):
        SECTION_NUMBER = 11
        self.texture_data['nb_texture'] = self.__get_int_value_from_info(AIData.SECTION_TEXTURE_NB, SECTION_NUMBER)
        list_texture_offset = []
        offset_size = AIData.SECTION_TEXTURE_OFFSET['size']
        start_offset = AIData.SECTION_TEXTURE_NB['size']
        for index_offset in range(self.texture_data['nb_texture']):
            list_texture_offset.append(
                int.from_bytes(self.section_raw_data[SECTION_NUMBER][start_offset + index_offset * offset_size:start_offset + (index_offset + 1) * offset_size],
                               byteorder="little"))
        self.texture_data['tim_offset'] = list_texture_offset


        self.texture_data['eof_texture'] = int.from_bytes(self.section_raw_data[SECTION_NUMBER][start_offset + len(list_texture_offset) * offset_size:start_offset + len(list_texture_offset) * offset_size+AIData.SECTION_TEXTURE_END_OF_FILE['size']], AIData.SECTION_TEXTURE_END_OF_FILE['byteorder'])
        tim_data_list = []
        offset_list_done = []
        for index, texture_offset in enumerate(list_texture_offset):
            start_tim = list_texture_offset[index]
            if texture_offset == 0:
                end_tim = start_tim
            else:
                next_offset = [x for x in list_texture_offset if x > texture_offset]
                if next_offset:
                    end_tim = min(next_offset)
                else:
                    end_tim = len(self.section_raw_data[SECTION_NUMBER])
            # Insert the data to have a continuous byte structure

            self.insert_sorted_with_zeros(offset_list_done, texture_offset)
            if texture_offset == 0:
                tim_data_list.append({"id": index, "data": self.section_raw_data[SECTION_NUMBER][start_tim: end_tim]})
            else:
                tim_data_list.insert(offset_list_done.index(texture_offset),
                                          {"id": index, "data": self.section_raw_data[SECTION_NUMBER][start_tim: end_tim]})

        self.texture_data['texture_data'] = tim_data_list

