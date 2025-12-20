import json
import os
from enum import Enum

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


class AIData:
    SECTION_HEADER_NB_SECTION = {'offset': 0, 'size': 4, 'byteorder': 'little', 'name': 'nb_section', 'pretty_name': 'Number section'}
    SECTION_HEADER_SECTION_POSITION = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'section_pos',
                                       'pretty_name': 'Section position'}  # size: nbSections * 4 bytes
    SECTION_HEADER_FILE_SIZE = {'offset': 0x30, 'size': 4, 'byteorder': 'little', 'name': 'file_size', 'pretty_name': 'File size'}  # offset: 4 + nbSections * 4
    SECTION_HEADER_DICT = {'nb_section': 0, 'section_pos': [], 'file_size': 0}

    # Section 3: Animation section
    SECTION_MODEL_ANIM_NB_MODEL = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'nb_anim', 'pretty_name': 'Number model animation'}
    SECTION_MODEL_ANIM_OFFSET = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'anim_offset', 'pretty_name': 'Animation offset'}
    SECTION_MODEL_ANIM_DICT = {'nb_animation': 0, 'animation_offset':[]}
    SECTION_MODEL_ANIM_LIST_DATA = [SECTION_MODEL_ANIM_NB_MODEL, SECTION_MODEL_ANIM_OFFSET]
    # Section 5: Sequence Animation section
    SECTION_MODEL_SEQ_ANIM_NB_SEQ = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_anim_seq', 'pretty_name': 'Number model animation'}
    SECTION_MODEL_SEQ_ANIM_OFFSET = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'seq_anim_offset', 'pretty_name': 'Sequence animation offset'}
    SECTION_MODEL_SEQ_ANIM_DICT = {'nb_anim_seq': 0, 'seq_anim_offset':[],  'seq_animation_data': []}
    SECTION_MODEL_SEQ_ANIM_LIST_DATA = [SECTION_MODEL_SEQ_ANIM_NB_SEQ, SECTION_MODEL_SEQ_ANIM_OFFSET]
    # Section 7: Info & stat section
    SECTION_INFO_STAT_NAME_DATA = {'offset': 0x00, 'size': 24, 'byteorder': 'big', 'name': 'monster_name', 'pretty_name': 'Monster name'}
    NAME_DATA = {'offset': 0x00, 'size': 24, 'byteorder': 'big', 'name': 'name', 'pretty_name': 'Name'}
    HP_DATA = {'offset': 0x18, 'size': 4, 'byteorder': 'big', 'name': 'hp', 'pretty_name': 'HP'}
    STR_DATA = {'offset': 0x1C, 'size': 4, 'byteorder': 'big', 'name': 'str', 'pretty_name': 'STR'}
    VIT_DATA = {'offset': 0x20, 'size': 4, 'byteorder': 'big', 'name': 'vit', 'pretty_name': 'VIT'}
    MAG_DATA = {'offset': 0x24, 'size': 4, 'byteorder': 'big', 'name': 'mag', 'pretty_name': 'MAG'}
    SPR_DATA = {'offset': 0x28, 'size': 4, 'byteorder': 'big', 'name': 'spr', 'pretty_name': 'SPR'}
    SPD_DATA = {'offset': 0x2C, 'size': 4, 'byteorder': 'big', 'name': 'spd', 'pretty_name': 'SPD'}
    EVA_DATA = {'offset': 0x30, 'size': 4, 'byteorder': 'big', 'name': 'eva', 'pretty_name': 'EVA'}
    MED_LVL_DATA = {'offset': 0xF4, 'size': 1, 'byteorder': 'big', 'name': 'med_lvl', 'pretty_name': 'Medium level'}
    HIGH_LVL_DATA = {'offset': 0xF5, 'size': 1, 'byteorder': 'big', 'name': 'high_lvl', 'pretty_name': 'High Level'}
    EXTRA_XP_DATA = {'offset': 0x100, 'size': 2, 'byteorder': 'little', 'name': 'extra_xp',
                     'pretty_name': 'Extra XP'}  # Seems the size was intended for 2 bytes, but in practice no monster has a value > 255
    XP_DATA = {'offset': 0x102, 'size': 2, 'byteorder': 'little', 'name': 'xp',
               'pretty_name': 'XP'}  # Seems the size was intended for 2 bytes, but in practice no monster has a value > 255
    LOW_LVL_MAG_DATA = {'offset': 0x104, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_mag', 'pretty_name': 'Low level Mag draw'}
    MED_LVL_MAG_DATA = {'offset': 0x10C, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_mag', 'pretty_name': 'Medium level Mag draw'}
    HIGH_LVL_MAG_DATA = {'offset': 0x114, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_mag', 'pretty_name': 'High level Mag draw'}
    LOW_LVL_MUG_DATA = {'offset': 0x11C, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_mug', 'pretty_name': 'Low level Mug draw'}
    MED_LVL_MUG_DATA = {'offset': 0x124, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_mug', 'pretty_name': 'Medium level Mug draw'}
    HIGH_LVL_MUG_DATA = {'offset': 0x12C, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_mug', 'pretty_name': 'High level Mug draw'}
    LOW_LVL_DROP_DATA = {'offset': 0x134, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_drop', 'pretty_name': 'Low level drop draw'}
    MED_LVL_DROP_DATA = {'offset': 0x13C, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_drop', 'pretty_name': 'Medium level drop draw'}
    HIGH_LVL_DROP_DATA = {'offset': 0x144, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_drop', 'pretty_name': 'High level drop draw'}
    MUG_RATE_DATA = {'offset': 0x14C, 'size': 1, 'byteorder': 'big', 'name': 'mug_rate', 'pretty_name': 'Mug rate %'}
    DROP_RATE_DATA = {'offset': 0x14D, 'size': 1, 'byteorder': 'big', 'name': 'drop_rate', 'pretty_name': 'Drop rate %'}
    PADDING_DATA = {'offset': 0x14E, 'size': 1, 'byteorder': 'big', 'name': 'padding', 'pretty_name': 'Empty padding'}
    AP_DATA = {'offset': 0x14F, 'size': 1, 'byteorder': 'big', 'name': 'ap', 'pretty_name': 'AP'}
    SECTION_INFO_STAT_RENZOKUKEN = {'offset': 0x150, 'size': 16, 'byteorder': 'little', 'name': 'renzokuken', 'pretty_name': 'Renzokuken'}
    ELEM_DEF_DATA = {'offset': 0x160, 'size': 8, 'byteorder': 'big', 'name': 'elem_def', 'pretty_name': 'Elemental def'}
    STATUS_DEF_DATA = {'offset': 0x168, 'size': 20, 'byteorder': 'big', 'name': 'status_def', 'pretty_name': 'Status def'}
    SECTION_INFO_STAT_BYTE_FLAG_0 = {'offset': 0xF6, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_0', 'pretty_name': 'Byte Flag 0'}
    SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE = ['byte0_zz1', 'byte0_zz2', 'byte0_zz3', 'byte0_unused4', 'byte0_unused5', 'byte0_unused6', 'byte0_unused7',
                                                'byte0_unused8']
    SECTION_INFO_STAT_BYTE_FLAG_1 = {'offset': 0xF7, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_1', 'pretty_name': 'Byte Flag 1'}
    SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE = ['Zombie', 'Fly', 'byte1_zz1', 'Immune NVPlus_Moins', 'Hidden HP', 'Auto-Reflect', 'Auto-Shell', 'Auto-Protect']
    CARD_DATA = {'offset': 0xF8, 'size': 3, 'byteorder': 'big', 'name': 'card', 'pretty_name': 'Card data'}
    DEVOUR_DATA = {'offset': 0xFB, 'size': 3, 'byteorder': 'big', 'name': 'devour', 'pretty_name': 'Devour'}
    SECTION_INFO_STAT_BYTE_FLAG_2 = {'offset': 0xFE, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_2', 'pretty_name': 'Byte Flag 2'}
    SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE = ['IncreaseSurpriseRNG', 'DecreaseSurpriseRNG', 'SurpriseAttackImmunity', 'IncreaseChanceEscape', 'DecreaseChanceEscape', 'byte2_unused_6',
                                                'Diablos-missed', 'Always obtains card']
    SECTION_INFO_STAT_BYTE_FLAG_3 = {'offset': 0xFF, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_3', 'pretty_name': 'Byte Flag 3'}
    SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE = ['byte3_zz1', 'byte3_zz2', 'byte3_zz3', 'byte3_zz4', 'byte3_unused_5', 'byte3_unused_6', 'byte3_unused_7',
                                                'byte3_unused_8']
    ABILITIES_LOW_DATA = {'offset': 0x34, 'size': 64, 'byteorder': 'little', 'name': 'abilities_low', 'pretty_name': 'Abilities Low Level'}
    ABILITIES_MED_DATA = {'offset': 0x74, 'size': 64, 'byteorder': 'little', 'name': 'abilities_med', 'pretty_name': 'Abilities Medium Level'}
    ABILITIES_HIGH_DATA = {'offset': 0xB4, 'size': 64, 'byteorder': 'little', 'name': 'abilities_high', 'pretty_name': 'Abilities High Level'}
    SECTION_INFO_STAT_DICT = {'monster_name': "", 'hp': [], 'str': [], 'vit': [], 'mag': [], 'spr': [], 'spd': [], 'eva': [],
                              'abilities_low': [], 'abilities_med': [], 'abilities_high': [], 'med_lvl': 0, 'high_lvl': 0,
                              'byte_flag_0': {}, 'byte_flag_1': {}, 'card': [], 'devour': [], 'byte_flag_2': {}, 'byte_flag_3': {},
                              'extra_xp': 0, 'xp': 0, 'low_lvl_mag': [], 'med_lvl_mag': [], 'high_lvl_mag': [],
                              'low_lvl_mug': [], 'med_lvl_mug': [], 'high_lvl_mug': [],
                              'low_lvl_drop': [], 'med_lvl_drop': [], 'high_lvl_drop': [], 'mug_rate': 0, 'drop_rate': 0,
                              'padding': 0, 'ap': 0, 'renzokuken': [], 'elem_def': [], 'status_def': []}
    SECTION_INFO_STAT_LIST_DATA = [SECTION_INFO_STAT_NAME_DATA, HP_DATA, STR_DATA, VIT_DATA, MAG_DATA, SPR_DATA, SPD_DATA, EVA_DATA,
                                   ABILITIES_LOW_DATA, ABILITIES_MED_DATA, ABILITIES_HIGH_DATA, MED_LVL_DATA, HIGH_LVL_DATA,
                                   SECTION_INFO_STAT_BYTE_FLAG_0, SECTION_INFO_STAT_BYTE_FLAG_1, CARD_DATA, DEVOUR_DATA,
                                   SECTION_INFO_STAT_BYTE_FLAG_2, SECTION_INFO_STAT_BYTE_FLAG_3,
                                   EXTRA_XP_DATA, XP_DATA, LOW_LVL_MAG_DATA, MED_LVL_MAG_DATA, HIGH_LVL_MAG_DATA,
                                   LOW_LVL_MUG_DATA, MED_LVL_MUG_DATA, HIGH_LVL_MUG_DATA, LOW_LVL_DROP_DATA, MED_LVL_DROP_DATA, HIGH_LVL_DROP_DATA,
                                   MUG_RATE_DATA, DROP_RATE_DATA, PADDING_DATA, AP_DATA, SECTION_INFO_STAT_RENZOKUKEN, ELEM_DEF_DATA, STATUS_DEF_DATA]
    # Battle script section
    # Subsection header
    SECTION_BATTLE_SCRIPT_HEADER_NB_SUB = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'battle_nb_sub', 'pretty_name': 'Number sub-section'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'offset_ai_sub',
                                                  'pretty_name': 'Offset AI sub-section'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB = {'offset': 0x08, 'size': 4, 'byteorder': 'little', 'name': 'offset_text_offset',
                                                           'pretty_name': 'Offset to text offset'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB = {'offset': 0x0C, 'size': 4, 'byteorder': 'little', 'name': 'offset_text_sub',
                                                    'pretty_name': 'Offset to text sub-section'}

    SECTION_BATTLE_SCRIPT_BATTLE_SCRIPT_HEADER_LIST_DATA = [SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB,
                                                            SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB]
    # Subsection AI
    SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'offset_init_code',
                                                 'pretty_name': 'Offset init code'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'offset_ennemy_turn',
                                                   'pretty_name': 'Offset ennemy turn'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK = {'offset': 0x08, 'size': 4, 'byteorder': 'little', 'name': 'offset_counterattack',
                                                     'pretty_name': 'Offset counterattack'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH = {'offset': 0x0C, 'size': 4, 'byteorder': 'little', 'name': 'offset_death', 'pretty_name': 'Offset death'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT = {'offset': 0x10, 'size': 4, 'byteorder': 'little', 'name': 'offset_before_dying_or_hit',
                                                           'pretty_name': 'Offset before dying or getting hit'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA = [SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE, SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN,
                                                 SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK, SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH,
                                                 SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT]
    # Subsection Offset to text offset
    SECTION_BATTLE_SCRIPT_TEXT_OFFSET = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'text_offset', 'pretty_name': 'List of text offset'}
    # Subsection battle text
    SECTION_BATTLE_SCRIPT_BATTLE_TEXT = {'offset': 0x00, 'size': 0, 'byteorder': 'little', 'name': 'battle_text', 'pretty_name': 'Battle text'}
    SECTION_BATTLE_SCRIPT_DICT = {'battle_nb_sub': 0, 'offset_ai_sub': 0, 'offset_text_offset': 0, 'offset_text_sub': 0, 'text_offset': [], 'battle_text': [],
                                  'ai_data': []}
    SECTION_BATTLE_SCRIPT_LIST_DATA = [SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB,
                                       SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB,
                                       SECTION_BATTLE_SCRIPT_TEXT_OFFSET, SECTION_BATTLE_SCRIPT_BATTLE_TEXT, SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE,
                                       SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN, SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK,
                                       SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH, SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT]

    BYTE_FLAG_LIST = ['byte_flag_0', 'byte_flag_1', 'byte_flag_2', 'byte_flag_3']
    CARD_OBTAIN_ORDER = ['DROP', 'MOD', 'RARE_MOD']
    MISC_ORDER = ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'mug_rate', 'drop_rate', 'ap']
    ABILITIES_HIGHNESS_ORDER = ['abilities_low', 'abilities_med', 'abilities_high']
    RESOURCE_FOLDER = "Resources"
    CHARACTER_LIST = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea", "Laguna", "Kiros", "Ward", "Angelo",
                      "Griever", "Boko"]
    COLOR_LIST = ["Darkgrey", "Grey", "Yellow", "Red", "Green", "Blue", "Purple", "White",
                  "DarkgreyBlink", "GreyBlink", "YellowBlink", "RedBlink", "GreenBlink", "BlueBlink", "PurpleBlink", "WhiteBlink"]
    LOCATION_LIST = ["Galbadia", "Esthar", "Balamb", "Dollet", "Timber", "Trabia", "Centra", "Horizon"]
    AI_CODE_NAME_LIST = ["Initialization fight", "Enemy turn", "Counter-Attack", "Death", "Before dying or taking a hit", "End"]
    ELEM_DEF_MIN_VAL = -100
    ELEM_DEF_MAX_VAL = 400
    STATUS_DEF_MIN_VAL = 0
    STATUS_DEF_MAX_VAL = 155
    STAT_MIN_VAL = 0
    STAT_MAX_VAL = 255
    AI_DATA_PATH = os.path.join("Resources", "ai_info.json")
    AI_SECTION_LIST = ['Init code', 'Enemy turn', 'Counter-attack', 'Death', 'Before dying or taking a hit']
    COLOR = "#0055ff"


class GameData:
    AIData = AIData()

    def __init__(self, game_data_submodule_path="FF8GameData"):
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

    def load_ai_data(self):
        file_path = os.path.join(self.resource_folder_json, "ai_info.json")
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
                self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"] = int(self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"], 16)
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
