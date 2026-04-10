import json
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Literal, Tuple, Optional
from PIL import Image


class LangType(Enum):
    ENGLISH = 0
    SPANISH = 1
    FRENCH = 2
    ITALIAN = 3
    GERMAN = 4


class MsdType(Enum):
    CARD_NAME = 0
    SCAN_TEXT = 1
    CARD_TEXT = 2
    DRAW_POINT = 3


class RemasterCardType(Enum):
    CARD_NAME = 0
    CARD_NAME2 = 1


class FileType(Enum):
    NONE = 0
    KERNEL = 1
    NAMEDIC = 2
    TKMNMES = 3
    MNGRP = 4
    EXE = 5
    DAT = 6
    REMASTER_DAT = 7
    FIELD_FS = 8
    WORLD_FS = 9


class SectionType(Enum):
    DATA = 1
    FF8_TEXT = 2
    KERNEL_HEADER = 3
    TKMNMES = 4
    MNGRP_STRING = 5
    MNGRP_MAP_COMPLEX_STRING = 6
    MNGRP_TEXTBOX = 7
    MNGRP_M00BIN = 8
    MNGRP_M00MSG = 9
    OFFSET_AND_TEXT = 10
    SIZE_AND_OFFSET_AND_TEXT = 11


class GameData:
    def __init__(self, game_data_submodule_path="FF8GameData", ai_file: str = "ai_vanilla.json"):
        self.resource_folder_json = os.path.join(game_data_submodule_path, "Resources", "json")
        self.resource_folder_image = os.path.join(game_data_submodule_path, "Resources", "image")
        self.resource_folder = os.path.join(game_data_submodule_path, "Resources")
        self.devour_data_json = {}
        self.magic_data_json = {}
        self.enemy_abilities_data_json = {}
        self.gforce_data_json = {}
        self.item_data_json = {}
        self.draw_data_json = {}
        self.special_action_data_json = {}
        self.field_data_json = {}
        self.stat_data_json = {}
        self.monster_data_json = {}
        self.status_data_json = {}
        self.field_data_json = {}
        self.sysfnt_data_json = {}
        self.kernel_data_json = {}
        self.mngrp_data_json = {}
        self.exe_data_json = {}
        self.ai_data_json = {}
        self.anim_sequence_data_json = {}
        self.ai_json_file_name = ai_file
        self.__init_hex_to_str_table()



    def __init_hex_to_str_table(self):
        self.load_sysfnt_data()
        with open(os.path.join(self.resource_folder, "sysfnt.txt"), "r", encoding="utf-8") as localize_file:
            self.translate_hex_to_str_table = localize_file.read()
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.replace(',",",',
                                                                                      ',";;;",')  # Handling the unique case of a "," character (which is also a separator)
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.replace('\n', '')
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.split(',')
            for i in range(len(self.translate_hex_to_str_table)):
                self.translate_hex_to_str_table[i] = self.translate_hex_to_str_table[i].replace(';;;', ',')
                if self.translate_hex_to_str_table[i].count('"') == 2:
                    self.translate_hex_to_str_table[i] = self.translate_hex_to_str_table[i].replace('"', '')

    @staticmethod
    def find_delimiter_from_csv_file(csv_file):
        with open(csv_file, newline='', encoding="utf-8") as text_file:
            csv_text = text_file.read()
        number_comma = csv_text.count(',')
        number_semicolon = csv_text.count(';')
        number_pipe = csv_text.count('|')
        if number_pipe >= number_semicolon and number_pipe >= number_comma:
            delimiter = "|"
        elif number_semicolon >= number_pipe and number_semicolon >= number_comma:
            delimiter = ";"
        else:
            delimiter = ","
        return delimiter

    def load_ai_data(self, ai_json_name=None):
        if ai_json_name:
            self.ai_json_file_name = ai_json_name
        file_path = os.path.join(self.resource_folder_json, self.ai_json_file_name)
        with open(file_path, encoding="utf8") as f:
            self.ai_data_json = json.load(f)

    def load_gforce_data(self):
        file_path = os.path.join(self.resource_folder_json, "gforce.json")
        with open(file_path, encoding="utf8") as f:
            self.gforce_data_json = json.load(f)

    def load_stat_data(self):
        file_path = os.path.join(self.resource_folder_json, "stat.json")
        with open(file_path, encoding="utf8") as f:
            self.stat_data_json = json.load(f)

    def load_status_data(self):
        file_path = os.path.join(self.resource_folder_json, "status.json")
        with open(file_path, encoding="utf8") as f:
            self.status_data_json = json.load(f)

    def load_devour_data(self):
        file_path = os.path.join(self.resource_folder_json, "devour.json")
        with open(file_path, encoding="utf8") as f:
            self.devour_data_json = json.load(f)

    def load_field_data(self):
        file_path = os.path.join(self.resource_folder_json, "field.json")
        with open(file_path, encoding="utf8") as f:
            self.field_data_json = json.load(f)

    def load_enemy_abilities_data(self):
        file_path = os.path.join(self.resource_folder_json, "enemy_abilities.json")
        with open(file_path, encoding="utf8") as f:
            self.enemy_abilities_data_json = json.load(f)

    def load_magic_data(self):
        file_path = os.path.join(self.resource_folder_json, "magic.json")
        with open(file_path, encoding="utf8") as f:
            self.magic_data_json = json.load(f)

    def load_special_action_data(self):
        file_path = os.path.join(self.resource_folder_json, "special_action.json")
        with open(file_path, encoding="utf8") as f:
            self.special_action_data_json = json.load(f)

    def load_monster_data(self):
        file_path = os.path.join(self.resource_folder_json, "monster.json")
        with open(file_path, encoding="utf8") as f:
            self.monster_data_json = json.load(f)

    def load_sysfnt_data(self):
        file_path = os.path.join(self.resource_folder_json, "sysfnt_data.json")
        with open(file_path, encoding="utf8") as f:
            self.sysfnt_data_json = json.load(f)

    def load_item_data(self):
        file_path = os.path.join(self.resource_folder_json, "item.json")
        with open(file_path, encoding="utf8") as f:
            self.item_data_json = json.load(f)

    def load_draw_data(self):
        file_path = os.path.join(self.resource_folder_json, "draw.json")
        with open(file_path, encoding="utf8") as f:
            self.draw_data_json = json.load(f)

    def load_exe_data(self):
        file_path = os.path.join(self.resource_folder_json, "exe.json")
        with open(file_path, encoding="utf8") as f:
            self.exe_data_json = json.load(f)
        for key in self.exe_data_json["lang"]:
            if self.exe_data_json["lang"][key]:
                self.exe_data_json["lang"][key] = int(
                    self.exe_data_json["lang"][key], 16)
        for key in self.exe_data_json["card_data_offset"]:
            self.exe_data_json["card_data_offset"][key] = int(self.exe_data_json["card_data_offset"][key], 16)
        for key in self.exe_data_json["scan_data_offset"]:
            self.exe_data_json["scan_data_offset"][key] = int(self.exe_data_json["scan_data_offset"][key], 16)
        for key in self.exe_data_json["draw_text_offset"]:
            self.exe_data_json["draw_text_offset"][key] = int(self.exe_data_json["draw_text_offset"][key], 16)
        for key in self.exe_data_json["draw_data_offset"]:
            self.exe_data_json["draw_data_offset"][key] = int(self.exe_data_json["draw_data_offset"][key], 16)

    def load_anim_sequence_data(self):
        file_path = os.path.join(self.resource_folder_json, "anim_sequence_info.json")
        with open(file_path, encoding="utf8") as f:
            self.anim_sequence_data_json = json.load(f)
        for i, el in enumerate(self.anim_sequence_data_json["op_code_info"]):
            if el["op_code"]:
                self.anim_sequence_data_json["op_code_info"][i]["op_code"] = int(self.anim_sequence_data_json["op_code_info"][i]["op_code"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["special_change_current_value_params"]):
            if el["param_id"]:
                self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"] = int(
                    self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["e5_special_params"]):
            if el["param_id"]:
                self.anim_sequence_data_json["e5_special_params"][i]["param_id"] = int(self.anim_sequence_data_json["e5_special_params"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["effect_id"]):
            if el["param_id"]:
                self.anim_sequence_data_json["effect_id"][i]["param_id"] = int(self.anim_sequence_data_json["effect_id"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["fade_effect_id"]):
            if el["param_id"]:
                self.anim_sequence_data_json["fade_effect_id"][i]["param_id"] = int(self.anim_sequence_data_json["fade_effect_id"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["sound_channel_flag"]):
            if el["param_id"]:
                self.anim_sequence_data_json["sound_channel_flag"][i]["param_id"] = int(self.anim_sequence_data_json["sound_channel_flag"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["sound_id_from_category"]):
            if el["param_id"]:
                self.anim_sequence_data_json["sound_id_from_category"][i]["param_id"] = int(self.anim_sequence_data_json["sound_id_from_category"][i]["param_id"], 16)

    def load_mngrp_data(self):
        file_path = os.path.join(self.resource_folder_json, "mngrp_bin_data.json")
        with open(file_path, encoding="utf8") as f:
            self.mngrp_data_json = json.load(f)
        for i in range(len(self.mngrp_data_json["sections"])):
            if self.mngrp_data_json["sections"][i]["section_offset"]:
                self.mngrp_data_json["sections"][i]["section_offset"] = int(
                    self.mngrp_data_json["sections"][i]["section_offset"], 16)
            if self.mngrp_data_json["sections"][i]["size"]:
                self.mngrp_data_json["sections"][i]["size"] = int(
                    self.mngrp_data_json["sections"][i]["size"], 16)
            data_type_str = self.mngrp_data_json["sections"][i]["data_type"]
            if data_type_str == "tkmnmes":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.TKMNMES
            elif data_type_str == "mngrp_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_STRING
            elif data_type_str == "data":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.DATA
            elif data_type_str == "text":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.FF8_TEXT
            elif data_type_str == "mngrp_complex_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_TEXTBOX
            elif data_type_str == "mngrp_map_complex_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_MAP_COMPLEX_STRING
            elif data_type_str == "m00bin":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_M00BIN
            elif data_type_str == "m00msg":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_M00MSG

    def load_kernel_data(self):
        file_path = os.path.join(self.resource_folder_json, "kernel_bin_data.json")
        with open(file_path, encoding="utf8") as f:
            self.kernel_data_json = json.load(f)

        for i in range(len(self.kernel_data_json["sections"])):
            if self.kernel_data_json["sections"][i]["section_offset"]:
                self.kernel_data_json["sections"][i]["section_offset"] = int(
                    self.kernel_data_json["sections"][i]["section_offset"], 16)
            if self.kernel_data_json["sections"][i]["section_offset_text_linked"]:
                self.kernel_data_json["sections"][i]["section_offset_text_linked"] = int(
                    self.kernel_data_json["sections"][i]["section_offset_text_linked"], 16)
            if self.kernel_data_json["sections"][i]["section_offset_data_linked"]:
                self.kernel_data_json["sections"][i]["section_offset_data_linked"] = int(
                    self.kernel_data_json["sections"][i]["section_offset_data_linked"], 16)
            data_type_str = self.kernel_data_json["sections"][i]["type"]
            if data_type_str == "data":
                self.kernel_data_json["sections"][i]["type"] = SectionType.DATA
            elif data_type_str == "text":
                self.kernel_data_json["sections"][i]["type"] = SectionType.FF8_TEXT

    def load_card_data(self):
        file_path = os.path.join(self.resource_folder_json, "card.json")
        with open(file_path, encoding="utf8") as f:
            self.card_data_json = json.load(f)
        self.__load_cards()

    def __load_cards(self):
        # Thank you Maki !
        img = Image.open(os.path.join(self.resource_folder_image, "text_0.png"))
        TILES_WIDTH_EL = 128
        TILES_HEIGHT_EL = 128
        for i, list_el in enumerate(self.card_data_json["card_type"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH_EL
            upper = list_el["img_y"] * TILES_HEIGHT_EL
            right = left + TILES_WIDTH_EL
            lower = upper + TILES_HEIGHT_EL
            # Extract the tile using cropping
            tile = img.crop((left, upper, right, lower))
            self.card_data_json["card_type"][i]["img"] = tile

        img = Image.open(os.path.join(self.resource_folder_image, "cards_00.png"))
        img_remaster = Image.open(os.path.join(self.resource_folder_image, "cards_00_remaster.png"))
        img_xylomod = Image.open(os.path.join(self.resource_folder_image, "cards_00_xylomod.png"))

        TILES_WIDTH = 64
        TILES_HEIGHT = 64
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile = img.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img"] = tile

        TILES_WIDTH = 256
        TILES_HEIGHT = 256
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile_remaster = img_remaster.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img_remaster"] = tile_remaster

        TILES_WIDTH = 256
        TILES_HEIGHT = 256
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile_xylomod = img_xylomod.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img_xylomod"] = tile_xylomod

    def translate_str_to_hex(self, string):
        c = 0
        str_size = len(string)
        encode_list = []
        while c < str_size:
            char = string[c]
            if char == '\\':
                encode_list.append(0x02)
                c += 2
                continue
            if char == '\n':  # \n{NewPage}\n,\n
                if '{NewPage}' in string[c + 1:c + 10]:
                    encode_list.append(0x01)
                    c += 10
                else:
                    encode_list.append(0x02)
                    c += 1
                continue
            elif char == '{':
                rest = string[c + 1:]
                index_next_bracket = rest.find('}')
                if index_next_bracket != -1:
                    substring = rest[:index_next_bracket]
                    if substring in self.sysfnt_data_json['Characters']:  # {name}
                        index_list = self.sysfnt_data_json['Characters'].index(substring)
                        if index_list < 11:
                            encode_list.extend([0x03, 0x30 + index_list])
                        elif index_list == 11:
                            encode_list.extend([0x03, 0x40])
                        elif index_list == 12:
                            encode_list.extend([0x03, 0x50])
                        elif index_list == 13:
                            encode_list.extend([0x03, 0x60])
                    elif substring in self.sysfnt_data_json['Icons']:  # {Icons}
                        index_list = self.sysfnt_data_json['Icons'].index(substring)
                        encode_list.extend([0x05, 0x20 + index_list])
                    elif substring in self.sysfnt_data_json['Colors']:  # {Color}
                        index_list = self.sysfnt_data_json['Colors'].index(substring)
                        encode_list.extend([0x06, 0x20 + index_list])
                    elif substring in self.sysfnt_data_json['GuardianForce']:  # {GuardianForce}
                        index_list = self.sysfnt_data_json['GuardianForce'].index(substring)
                        encode_list.extend([0x0c, 0x60 + index_list])
                    elif substring in self.sysfnt_data_json['Locations']:  # {Location}
                        index_list = self.sysfnt_data_json['Locations'].index(substring)
                        encode_list.extend([0x0e, 0x20 + index_list])
                    elif 'Cursor_location_id:0x' in substring:
                        len_curs = len('Cursor_location_id:0x')
                        if len(substring) == len_curs + 4:
                            encode_list.extend([0x0b, int(substring[len_curs:len_curs + 2], 16), int(substring[len_curs + 2:len_curs + 4], 16)])
                        else:
                            encode_list.extend([0x0b, int(substring[len_curs:len_curs + 2], 16)])
                    elif 'Var' in substring:
                        if len(substring) == 5:
                            if 'b' in substring:  # {Varb0}
                                encode_list.extend([0x04, int(substring[-1]) + 0x40])
                            else:  # {Var00}
                                encode_list.extend([0x04, int(substring[-1]) + 0x30])
                        else:  # {Var0}
                            encode_list.extend([0x04, int(substring[-1]) + 0x20])
                    elif 'Wait' in substring:  # {Wait000}
                        encode_list.extend([0x09, int(substring[-1]) + 0x20])
                    elif 'Jp' in substring:  # {Jp000}
                        encode_list.extend([0x1c, int(substring[-1]) + 0x20])
                    elif '{' + substring + '}' in self.translate_hex_to_str_table:  # {} at end of sysfnt
                        encode_list.append(self.translate_hex_to_str_table.index('{' + substring + '}'))
                    elif 'x' in substring and len(substring) == 5:  # {xffff}
                        encode_list.extend([int(substring[1:3], 16), int(substring[3:5], 16)])
                    elif 'x' in substring and len(substring) == 3:  # {xff}
                        encode_list.append(int(substring[1:3], 16))
                    c += len(substring) + 2  # +2 for the {}
                    continue
            encode_list.append(self.translate_hex_to_str_table.index(char))
            c += 1
            # Jp ?
        return encode_list

    def translate_hex_to_str(self, hex_list, zero_as_slash_n=False, first_hex_literal=False, cursor_location_size=2):
        build_str = ""
        i = 0
        hex_size = len(hex_list)
        while i < hex_size:
            hex_val = hex_list[i]
            if i == 0 and first_hex_literal:
                build_str += "{{x{:02x}}}".format(hex_val)
            elif hex_val == 0x00 and zero_as_slash_n:
                build_str += "\n"
            elif hex_val == 0x00:
                pass
            elif hex_val in [0x01, 0x02]:
                build_str += self.translate_hex_to_str_table[hex_val]
            elif hex_val == 0x03:  # {Name}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x30 and hex_val <= 0x3a:
                        build_str += '{' + self.sysfnt_data_json['Characters'][hex_val - 0x30] + '}'
                    elif hex_val == 0x40:
                        build_str += '{' + self.sysfnt_data_json['Characters'][11] + '}'
                    elif hex_val == 0x50:
                        build_str += '{' + self.sysfnt_data_json['Characters'][12] + '}'
                    elif hex_val == 0x60:
                        build_str += '{' + self.sysfnt_data_json['Characters'][13] + '}'
                    else:
                        build_str += "{{x03{:02x}}}".format(hex_val)
                else:
                    build_str += "{x03}"
            elif hex_val == 0x04:  # {Var0}, {Var00} et {Varb0}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and i <= 0x27:
                        build_str += "{{Var{:02x}}}".format(hex_val - 0x20)
                    elif hex_val >= 0x30 and i <= 0x37:
                        build_str += "{{Var0{:02x}}}".format(hex_val - 0x30)
                    elif hex_val >= 0x40 and i <= 0x47:
                        build_str += "{{Varb{:02x}}}".format(hex_val - 0x40)
                    else:
                        build_str += "{{x04{:02x}}}".format(hex_val)

                else:
                    build_str += "{x04}"
            elif hex_val == 0x05:  # {Icons}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x5d:
                        build_str += '{' + self.sysfnt_data_json['Icons'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x05{:02x}}}".format(hex_val)
                else:
                    build_str += "{x05}"
            elif hex_val == 0x06:  # {Color}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x2f:
                        build_str += '{' + self.sysfnt_data_json['Colors'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x06{:02x}}}".format(hex_val)
                else:
                    build_str += "{x06}"
            elif hex_val == 0x09:  # {Wait000}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        build_str += "{{Wait{:03}}}".format(hex_val - 0x20)
                    else:
                        build_str += "{{x09{:02x}}}".format(hex_val)
                else:
                    build_str += "{x06}"
            elif hex_val == 0x0b:  # {cursor_location}
                i += 1
                if i < hex_size:
                    if cursor_location_size == 2:
                        hex_val = hex_list[i]
                        build_str += "{{Cursor_location_id:0x{:02x}}}".format(hex_val)
                    if cursor_location_size == 3:
                        hex_val1 = hex_list[i]
                        i += 1
                        hex_val2 = hex_list[i]
                        build_str += "{{Cursor_location_id:0x{:02x}{:02x}}}".format(hex_val1, hex_val2)
                else:
                    build_str += "{x0b}"
            elif hex_val == 0x0c:  # {GuardianForce}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x60 and hex_val <= 0x6f:
                        build_str += '{' + self.sysfnt_data_json['GuardianForce'][hex_val - 0x60] + '}'
                    else:
                        build_str += "{{x0c{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0c}"
            elif hex_val == 0x0e:  # {Location}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x27:
                        build_str += '{' + self.sysfnt_data_json['Locations'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x0e{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0e}"
            elif hex_val >= 0x19 and hex_val <= 0x1b:  # jp19, jp1a, jp1b
                i += 1
                if i < hex_size:
                    old_hex_val = hex_val
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        character = None  # To be changed, caract(index, oldIndex-0x18);
                    else:
                        character = None
                    if not character:
                        character = "{{x{:02x}{:02x}}}".format(old_hex_val, hex_val)
                    build_str += character
                else:
                    build_str += "{{x{:02x}}}".format(hex_val)
            elif hex_val == 0x1c:  # addJp
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        build_str += "{{Jp{:03}}}".format(hex_val - 0x20)
                    else:
                        build_str += "{{x1c{:02x}}}".format(hex_val)
                else:
                    build_str += "{x1c}"
            elif hex_val >= 0x03 and hex_val <= 0x1f:
                i += 1
                if i < hex_size:
                    build_str += "{{x{:02x}{:02x}}}".format(hex_val, hex_list[i])
                else:
                    build_str += "{{x{:02x}}}".format(hex_val)
            else:
                character = self.translate_hex_to_str_table[hex_val]
                if not character:
                    character = "{{x{:02x}}}".format(hex_val)
                build_str += character
            i += 1

        return build_str

    def load_all(self):
        self.load_monster_data()
        self.load_sysfnt_data()
        self.load_item_data()
        self.load_devour_data()
        self.load_gforce_data()
        self.load_stat_data()
        self.load_status_data()
        self.load_kernel_data()
        self.load_card_data()
        self.load_mngrp_data()
        self.load_exe_data()
        self.load_ai_data()
        self.load_magic_data()
        self.load_enemy_abilities_data()
        self.load_special_action_data()
        self.load_anim_sequence_data()
        self.load_field_data()
        self.load_draw_data()


if __name__ == "__main__":
    # To be able to read a file and write back in a file
    file_to_load = "FF8_EN.exe"  # Fill with the file you want. use os.path.join if it is in folder
    file_export = "export.txt"  # The file to write the final string back
    print("Loading core data engine")
    game_data = GameData(".")
    # game_data.load_all() # This load all data if you want to test further, not just text translation

    print(f"Reading the file: {file_to_load}")
    current_file_data = bytearray()
    with open(file_to_load, "rb") as in_file:
        while el := in_file.read(1):
            current_file_data.extend(el)

    # Ignoring not wanted values (for example only alphabet)
    # EOL => 0x00
    # 0-> 9 => 0x21 -> 0x2a
    # A -> œ => 0x45 -> 0xa7
    # {in} -> {ag} => 0xe8 -> 0xff
    print("Limiting to specific characters")
    transformed_file = bytearray()
    for byte in current_file_data:
        if byte == 0 or 0x21 <= byte <= 0x2a or 0x45 <= byte <= 0xa7 or 0xe8 <= byte <= 0xff:
            transformed_file.append(byte)

    current_file_data = transformed_file
    zero_as_slash_n_param = True
    print(f"Transforming the byte data into ff8 string and considering byte 0 (end of string) as a \\n: {zero_as_slash_n_param}")
    ff8_string = game_data.translate_hex_to_str(current_file_data, zero_as_slash_n_param)
    print("File translated")
    # line_break = 200 # To define how often we return to line (for increase readability)
    # print(f"Now breaking the line every {line_break} characters")
    # ff8_string = '\n'.join(ff8_string[i:i + line_break] for i in range(0, len(ff8_string), line_break))
    # print("Now removing the multiple \\n")
    # Now removing the multiple following \n
    # new_string = ""
    # for index, char in enumerate(ff8_string):
    #     if index % 1000 == 0:
    #         print(index)
    #     if index < len(ff8_string) - 1:
    #         if char == '\n' and ff8_string[index + 1] == '\n':
    #             continue
    #     new_string += char
    # ff8_string = new_string

    print(f"Now writing in export file: {file_export}")
    with open(file_export, "w", encoding="utf-8") as in_file:
        in_file.write(ff8_string)

    print("Enjoy !")
