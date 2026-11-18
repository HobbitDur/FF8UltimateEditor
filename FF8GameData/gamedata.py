import contextlib
import json
import math
import os
import re
import shutil
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
    FONT = 10  # a .tdw font file (ShumiTranslator's font tab)


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
    MNGRP_SEED_TEST = 12


# Card art tiles, shared by every GameData of the process: each tool holds its own GameData, and
# decoding the four card atlases (the remaster ones are large PNGs) cost ~0.4 s per load_card_data,
# five times over at startup. Every user only reads the tiles (resize/convert make copies).
_CARD_ATLASES = {}   # atlas path -> decoded PIL image
_CARD_TILES = {}     # (atlas path, tile size, x, y) -> cropped PIL image


def _card_tile(atlas_path, tile_size, x, y):
    key = (atlas_path, tile_size, x, y)
    tile = _CARD_TILES.get(key)
    if tile is None:
        atlas = _CARD_ATLASES.get(atlas_path)
        if atlas is None:
            atlas = _CARD_ATLASES[atlas_path] = Image.open(atlas_path)
            atlas.load()
        left, upper = x * tile_size, y * tile_size
        tile = _CARD_TILES[key] = atlas.crop((left, upper, left + tile_size, upper + tile_size))
    return tile


class GameData:
    def __init__(self, game_data_submodule_path="FF8GameData", ai_file: str = "ai_vanilla.json"):
        self.resource_folder_json = os.path.join(game_data_submodule_path, "Resources", "json")
        self.resource_folder_image = os.path.join(game_data_submodule_path, "Resources", "image")
        self.resource_folder = os.path.join(game_data_submodule_path, "Resources")
        self.devour_data_json = {}
        # The names of the kernel.bin a tool has open, exactly as that file holds them:
        # {list name: {id: name}} (kernelnames.read_names, "magic" / "item" / "enemy_ability").
        # Empty when none is open - lists that must come from a kernel.bin only (Ifrit's loot)
        # read here rather than the json-backed lists, which always have names.
        self.kernel_names = {}
        self.camera_category_data_json = {}
        self.devour_category_data_json = {}
        self.magic_data_json = {}
        self.enemy_abilities_data_json = {}
        self.gforce_data_json = {}
        self.item_data_json = {}
        self.mitem_data_json = {}
        self.draw_data_json = {}
        self.attack_animation_data_json = {}
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
        self.camera_sequence_data_json = {}
        self.camera_script_data_json = {}
        self.ai_json_file_name = ai_file
        # Character table: which character each byte code is (see CHARACTER_TABLES). Latin by default.
        # Japanese: 4-table font (Deling sysfnt_jp.txt). Table 0 = single-byte glyphs (0x20-0xFF); tables
        # 1/2/3 reached via 2-byte lead bytes 0x19/0x1a/0x1b. jp_encoding says whether that is in use.
        self.jp_encoding = False
        self.jp_tables = []
        self.character_table = "latin"
        self.character_table_modified = False
        self.__init_hex_to_str_table()

    # The character tables ShumiTranslator can read and write texts with: key -> (name, file in
    # Resources, Japanese). A Latin-style file lists the 256 codes from 0x00 (control codes included);
    # the Japanese one lists 4 tables of 224 codes from 0x20. The Vietnamese one is the Latin table with
    # the letters the Vietnamese patch drew over some glyphs (its font, not a new encoding).
    CHARACTER_TABLES = {
        "latin": ("Latin", "sysfnt.txt", False),
        "japanese": ("Japanese", "sysfnt_jp.txt", True),
        "vietnamese": ("Vietnamese", "sysfnt_viet.txt", False),
    }

    def __init_hex_to_str_table(self):
        self.load_sysfnt_data()
        self.latin_table = self.read_character_table_file(os.path.join(self.resource_folder, "sysfnt.txt"))
        self.translate_hex_to_str_table = list(self.latin_table)
        self.character_table_path = os.path.join(self.resource_folder, "sysfnt.txt")
        self.__init_jp_tables()

    @staticmethod
    def _character_table_entries(raw: str):
        """(start, end, comment) of each entry, in file order: start/end of its text inside the quotes,
        and the /*comment*/ that may follow it. Entries are separated by commas; a value may be the
        single character ',' or '"'."""
        spans, i = [], 0
        while True:
            start = raw.find('"', i)
            if start == -1:
                return spans
            end = start + 1
            # the closing quote is the next one followed by a separator, a comment, a line end or the end
            # ('""' is empty, '","' is a comma, '"""' a quote)
            while end < len(raw) and not (raw[end] == '"' and (end + 1 >= len(raw) or raw[end + 1] in ',/\r\n')):
                end += 1
            comment_end = raw.find('*/', end) + 2 if raw.startswith('/*', end + 1) else end + 1
            spans.append((start + 1, end, raw[end + 1:comment_end]))
            i = comment_end

    @classmethod
    def _table_values(cls, raw: str):
        # A commented entry reads as its comment (""/*Names*/ -> "/*Names*/"), as it always has: these
        # are control codes, never printed from the table.
        return [raw[start:end] + comment for start, end, comment in cls._character_table_entries(raw)]

    @classmethod
    def read_character_table_file(cls, path):
        """The entries of a character table file, in order (see CHARACTER_TABLES)."""
        with open(path, "r", encoding="utf-8", newline="") as table_file:
            return cls._table_values(table_file.read())

    @classmethod
    def write_character_table_file(cls, path, values):
        """Write new entries into a character table file, keeping its layout and comments."""
        with open(path, "r", encoding="utf-8", newline="") as table_file:
            raw = table_file.read()
        spans = cls._character_table_entries(raw)
        if len(values) != len(spans):
            raise ValueError(f"{os.path.basename(path)} has {len(spans)} entries, {len(values)} given")
        for (start, end, comment), value in reversed(list(zip(spans, values))):
            if comment and value.endswith(comment):
                value = value[:-len(comment)]
            raw = raw[:start] + value + raw[end:]
        with open(path, "w", encoding="utf-8", newline="") as table_file:
            table_file.write(raw)

    def set_character_table(self, key):
        """Use that character table for every text from now on (see CHARACTER_TABLES)."""
        _name, file_name, _japanese = self.CHARACTER_TABLES[key]
        self.__load_character_table(os.path.join(self.resource_folder, file_name))
        self.character_table = key

    def set_custom_character_table(self, path):
        """Use a character table file of your own (same format as one of CHARACTER_TABLES: 256 codes
        Latin-style, or the 4 Japanese tables)."""
        self.__load_character_table(path)
        self.character_table = "custom"

    def __load_character_table(self, path):
        values = self.read_character_table_file(path)
        if len(values) == 256:          # Latin style: every code from 0x00
            self.__init_jp_tables()
            self.translate_hex_to_str_table = values
            self.jp_encoding = False
        elif 3 * 224 < len(values) <= 4 * 224:  # Japanese: 4 tables of 224 codes from 0x20
            self.__init_jp_tables(path)
            self.translate_hex_to_str_table = list(self.latin_table)  # control codes and {} tags
            self.jp_encoding = True
        else:
            raise ValueError(f"{os.path.basename(path)} has {len(values)} characters: a character table has 256 "
                             "(Latin style, from code 00) or 4 tables of up to 224 (Japanese)")
        self.character_table_path = path
        self.character_table_modified = False

    @property
    def character_table_name(self):
        if self.character_table == "custom":
            return os.path.basename(self.character_table_path)
        return self.CHARACTER_TABLES[self.character_table][0]

    @contextlib.contextmanager
    def using_latin_table(self):
        """Read and write texts with the Latin table for a moment (Deling's own text form)."""
        saved = (self.translate_hex_to_str_table, self.jp_encoding)
        self.translate_hex_to_str_table, self.jp_encoding = self.latin_table, False
        try:
            yield
        finally:
            self.translate_hex_to_str_table, self.jp_encoding = saved

    def table_char(self, table, index):
        """The character of code 0x20 + index of a font table (0 = single byte, 1-3 = Japanese lead
        bytes 0x19-0x1b) in the character table in use."""
        if self.jp_encoding:
            return self.caract_jp(0x20 + index, table) or ""
        values = self.translate_hex_to_str_table
        return values[0x20 + index] if table == 0 and 0x20 + index < len(values) else ""

    def set_table_char(self, table, index, char):
        """Change a character of the table in use, in memory only (its file stays as it was): every text
        is read and written with it from now on. export_character_table keeps it in a file."""
        if self.jp_encoding:
            self.jp_tables[table][index] = char
        elif table == 0:
            self.translate_hex_to_str_table[0x20 + index] = char
        else:
            raise ValueError("the Latin-style character tables have one table only")
        self.character_table_modified = True

    def character_table_values(self):
        """A copy of the characters of the table in use, edits included (to compare or put back)."""
        if self.jp_encoding:
            return tuple(tuple(table) for table in self.jp_tables)
        return tuple(self.translate_hex_to_str_table)

    def set_character_table_values(self, values, modified):
        """Put back characters taken with character_table_values (undo), in place: whatever holds the
        table keeps seeing it."""
        if self.jp_encoding:
            for table, saved in zip(self.jp_tables, values):
                table[:] = saved
        else:
            self.translate_hex_to_str_table[:] = values
        self.character_table_modified = modified

    def export_character_table(self, path):
        """Write the character table in use, edits included, to a new file (the layout of its own file).
        Nothing else changes: the table in use stays the same one, its file untouched."""
        if os.path.abspath(path) != os.path.abspath(self.character_table_path):
            shutil.copyfile(self.character_table_path, path)
        values = ([char for table in self.jp_tables for char in table] if self.jp_encoding
                  else self.translate_hex_to_str_table)
        self.write_character_table_file(path, values)
        return path

    def __init_jp_tables(self, jp_path=None):
        # Loads the Japanese 4-table font map (Resources/sysfnt_jp.txt, or another file in that format).
        # The file holds 4 blocks separated by a blank line; each block is a comma-separated list of
        # quoted glyphs indexed from byte 0x20 (same quoting convention as sysfnt.txt). Missing file =>
        # JP support disabled.
        self.jp_tables = []
        jp_path = jp_path or os.path.join(self.resource_folder, "sysfnt_jp.txt")
        if not os.path.exists(jp_path):
            return
        with open(jp_path, "r", encoding="utf-8") as jp_file:
            raw = jp_file.read()
        for block in re.split(r'\r?\n\s*\r?\n', raw.strip('\r\n')):
            self.jp_tables.append(self._table_values(block))

    def caract_jp(self, ord_val, table=0):
        # Returns the glyph for a byte >= 0x20 in the given JP font table (0..3), or None if out of range.
        if 0 <= table < len(self.jp_tables):
            idx = ord_val - 0x20
            if 0 <= idx < len(self.jp_tables[table]):
                return self.jp_tables[table][idx]
        return None

    def encode_jp_char(self, char, prefer: bytes = None):
        # Reverse of caract_jp: find a character in the JP tables. Table 0 => single byte [0x20+idx];
        # tables 1/2/3 => 2-byte lead sequence [0x18+table, 0x20+idx]. Returns None if not found.
        # A glyph drawn in two tables (記 is 0x1ac8 and 0x1ba1) takes the code found in `prefer` (the bytes the
        # text was loaded from), so an unchanged text saves back identical.
        candidates = []
        for table_idx, table in enumerate(self.jp_tables):
            if char in table:
                idx = table.index(char)
                candidates.append([0x20 + idx] if table_idx == 0 else [0x18 + table_idx, 0x20 + idx])
        if not candidates:
            return None
        if prefer and len(candidates) > 1:
            for candidate in candidates:
                if bytes(candidate) in prefer:
                    return candidate
        return candidates[0]

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
        """The devour effects have NO built-in names: they are the texts of a kernel.bin (section
        29), filled by FF8GameData.kernelnames.read_devour_names when a tool has one open. Until
        then the list is empty, and the tools say to open a kernel.bin."""
        self.devour_data_json = {"devour": []}

    def load_camera_category_data(self):
        file_path = os.path.join(self.resource_folder_json, "camera_category.json")
        with open(file_path, encoding="utf8") as f:
            self.camera_category_data_json = json.load(f)

    def load_devour_category_data(self):
        file_path = os.path.join(self.resource_folder_json, "devour_category.json")
        with open(file_path, encoding="utf8") as f:
            self.devour_category_data_json = json.load(f)

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

    def load_names(self, renames_json_name=None):
        """Reload the vanilla spell, item and enemy attack names, then apply a mod's renames on top
        when one is named (a changes file written by kernelnames.write_changes_file, e.g. by the
        Cronos repository's "names" command): what every tool shows for them - the xlsx columns
        and their drop-downs, the AI parameters, the monster drops and draws.

        The renames file is generated from the mod's kernel.bin, see FF8GameData/kernelnames.py."""
        self.load_magic_data()
        self.load_item_data()
        self.load_enemy_abilities_data()
        self.load_devour_data()  # empty until a kernel.bin names them
        self.kernel_names = {}
        if renames_json_name:
            from FF8GameData.kernelnames import apply_names, read_changes_file
            apply_names(self, read_changes_file(os.path.join(self.resource_folder_json, renames_json_name)))

    def load_attack_animation_data(self):
        file_path = os.path.join(self.resource_folder_json, "attack_animation.json")
        with open(file_path, encoding="utf8") as f:
            self.attack_animation_data_json = json.load(f)

    def load_monster_data(self):
        file_path = os.path.join(self.resource_folder_json, "monster.json")
        with open(file_path, encoding="utf8") as f:
            self.monster_data_json = json.load(f)

    CRONOS_AI_FILE = "ai_cronos.json"

    def get_ai_monster_targets(self, target_list_key: str):
        """The monsters an AI target parameter of this kind (the ai json list: "target_basic",
        "target_advanced_specific", "target_advanced_generic") can name, as {"id", "data"}.

        monster.json flags c0m144-c0m199 "extended_monster_targets": files the vanilla exe
        cannot load, usable with FFNx's AllMonsterFilesUsable patch - so they are in only with
        the Cronos AI tables. The target byte is one value space: the game decodes a special
        target before looking for a monster with that id, so a monster whose id is a special
        target of that same list (200 = self...) can't be named there and is left out. Each
        opcode family reserves its own values, so c0m184-c0m193 (ids 200-209) are in some lists
        and not others."""
        extended = self.ai_json_file_name == self.CRONOS_AI_FILE
        monsters = [{"id": m["entity_id"], "data": m["name"]} for m in self.monster_data_json["monster"]
                    if extended or not m.get("extended_monster_targets", False)]
        reserved = {el["param_id"] for el in self.ai_data_json.get(target_list_key, [])}
        return [m for m in monsters if m["id"] not in reserved]

    def load_sysfnt_data(self):
        file_path = os.path.join(self.resource_folder_json, "sysfnt_data.json")
        with open(file_path, encoding="utf8") as f:
            self.sysfnt_data_json = json.load(f)

    def special_value_context_for_section(self, section_name: str):
        """The 0x0a context of a text section, or None when no name table applies there.

        A 0x0a slot means what the screen drawing the text puts in it (the SeeD test, the
        battle rewards and the item-menu messages each fill their own values), so a slot
        only gets a name inside a section known to be drawn by that screen."""
        for section_prefix, context in self.sysfnt_data_json.get('SpecialValueSections', {}).items():
            if section_name == section_prefix or section_name.startswith(section_prefix + " "):
                return context
        return None

    def _special_value_code_from_name(self, name: str):
        """0x0a code of a special value name, whatever its context (names are unique), or None."""
        for special_values in self.sysfnt_data_json.get('SpecialValues', {}).values():
            for code_str, special_name in special_values.items():
                if special_name == name:
                    return int(code_str[-2:], 16)
        legacy_code = self.sysfnt_data_json.get('SpecialValueLegacyNames', {}).get(name)
        if legacy_code:
            return int(legacy_code[-2:], 16)
        return None

    def load_item_data(self):
        file_path = os.path.join(self.resource_folder_json, "item.json")
        with open(file_path, encoding="utf8") as f:
            self.item_data_json = json.load(f)

    def load_mitem_data(self):
        file_path = os.path.join(self.resource_folder_json, "mitem.json")
        with open(file_path, encoding="utf8") as f:
            self.mitem_data_json = json.load(f)

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
        for key in self.exe_data_json["scan_camera_offset"]:
            self.exe_data_json["scan_camera_offset"][key] = int(self.exe_data_json["scan_camera_offset"][key], 16)
        for section in ("text_icon_sprite_offset", "scan_background_offset"):
            for key, value in self.exe_data_json[section].items():
                if key != "comment":
                    self.exe_data_json[section][key] = int(value, 16)
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

    def load_camera_sequence_data(self):
        """The battle camera script VM op codes (camera_sequence_vm reads this)."""
        file_path = os.path.join(self.resource_folder_json, "camera_sequence_info.json")
        with open(file_path, encoding="utf8") as f:
            self.camera_sequence_data_json = json.load(f)
        for key in ("op_code_info",):
            for el in self.camera_sequence_data_json[key]:
                el["op_code"] = int(el["op_code"], 16)
        for key in ("special_change_current_value_params", "e5_special_params"):
            for el in self.camera_sequence_data_json[key]:
                el["param_id"] = int(el["param_id"], 16)
        # The script editor's lists and help (camera_script.json), read with the VM it describes
        with open(os.path.join(self.resource_folder_json, "camera_script.json"), encoding="utf8") as f:
            self.camera_script_data_json = json.load(f)

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
            elif data_type_str == "mngrp_seed_test":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_SEED_TEST
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
        # The tiles come from a process-wide cache (_card_tile): the JSON is still read fresh for
        # each GameData, only the decoded art is shared.
        def atlas(name):
            return os.path.join(self.resource_folder_image, name)

        for card_type in self.card_data_json["card_type"]:
            card_type["img"] = _card_tile(atlas("text_0.png"), 128, card_type["img_x"], card_type["img_y"])
        for card in self.card_data_json["card_info"]:
            x, y = card["img_x"], card["img_y"]
            card["img"] = _card_tile(atlas("cards_00.png"), 64, x, y)
            card["img_remaster"] = _card_tile(atlas("cards_00_remaster.png"), 256, x, y)
            card["img_xylomod"] = _card_tile(atlas("cards_00_xylomod.png"), 256, x, y)

    def translate_str_to_hex(self, string, jp_prefer: bytes = None):
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
                if string.startswith('{NewPage}', c + 1):
                    # Deling writes a new page as "\n{NewPage}\n": both line breaks belong to the 0x01
                    encode_list.append(0x01)
                    c += 10
                    if c < str_size and string[c] == '\n':
                        c += 1
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
                    elif substring in self.sysfnt_data_json.get('IconLegacyNames', {}):  # old {Icons} names
                        # Encode-only: names from before the list matched the exe's icon table, kept so
                        # old CSVs still give the same bytes. No current icon name reuses one of them.
                        encode_list.extend([0x05, int(self.sysfnt_data_json['IconLegacyNames'][substring][-2:], 16)])
                    elif substring in self.sysfnt_data_json['Colors']:  # {Color}
                        index_list = self.sysfnt_data_json['Colors'].index(substring)
                        encode_list.extend([0x06, 0x20 + index_list])
                    elif substring in self.sysfnt_data_json['GuardianForce']:  # {GuardianForce}
                        index_list = self.sysfnt_data_json['GuardianForce'].index(substring)
                        encode_list.extend([0x0c, 0x60 + index_list])
                    elif substring in self.sysfnt_data_json['Locations']:  # {Location}
                        index_list = self.sysfnt_data_json['Locations'].index(substring)
                        encode_list.extend([0x0e, 0x20 + index_list])
                    elif self._special_value_code_from_name(substring) is not None:  # {SpecialValue} 0x0a
                        # Encoding needs no context: every name is unique, old names included.
                        # The raw form {x0aXX} still encodes via the generic 'x' branch below.
                        encode_list.extend([0x0a, self._special_value_code_from_name(substring)])
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
                    elif re.fullmatch(r'Wait\d{3}', substring):  # {Wait000}: the whole number, as decoded
                        encode_list.extend([0x09, int(substring[4:]) + 0x20])
                    elif re.fullmatch(r'Jp\d{3}', substring):  # {Jp000}: the whole number, as decoded
                        encode_list.extend([0x1c, int(substring[2:]) + 0x20])
                    elif '{' + substring + '}' in self.translate_hex_to_str_table:  # {} at end of sysfnt
                        encode_list.append(self.translate_hex_to_str_table.index('{' + substring + '}'))
                    elif 'x' in substring and len(substring) == 5:  # {xffff}
                        encode_list.extend([int(substring[1:3], 16), int(substring[3:5], 16)])
                    elif 'x' in substring and len(substring) == 3:  # {xff}
                        encode_list.append(int(substring[1:3], 16))
                    c += len(substring) + 2  # +2 for the {}
                    continue
            if self.jp_encoding:
                jp_encoded = self.encode_jp_char(char, jp_prefer)
                if jp_encoded is not None:
                    encode_list.extend(jp_encoded)
                    c += 1
                    continue
            code = self.translate_hex_to_str_table.index(char)
            if jp_prefer and self.translate_hex_to_str_table.count(char) > 1:
                # A character drawn at two codes (the Vietnamese font has two ớ and two ộ) keeps the code
                # the text was loaded with, so an unchanged text saves back identical.
                codes = [i for i, value in enumerate(self.translate_hex_to_str_table) if value == char]
                code = next((i for i in codes if i in jp_prefer), code)
            encode_list.append(code)
            c += 1
        return encode_list

    def translate_hex_to_str(self, hex_list, zero_as_slash_n=False, first_hex_literal=False, cursor_location_size=2,
                             special_value_context=None):
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
                    if 0x20 <= hex_val <= 0x27:
                        build_str += "{{Var{:d}}}".format(hex_val - 0x20)
                    elif 0x30 <= hex_val <= 0x37:
                        build_str += "{{Var0{:d}}}".format(hex_val - 0x30)
                    elif 0x40 <= hex_val <= 0x47:
                        build_str += "{{Varb{:d}}}".format(hex_val - 0x40)
                    else:
                        build_str += "{{x04{:02x}}}".format(hex_val)

                else:
                    build_str += "{x04}"
            elif hex_val == 0x05:  # {Icons}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    # 0x20-0x7E: every code the exe resolves (TEXT_ICON_CODE_TO_SPRITE ends at 0x7E)
                    if 0x20 <= hex_val < 0x20 + len(self.sysfnt_data_json['Icons']):
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
            elif hex_val == 0x0a:  # {SpecialValue} - context-specific value insert (see FF8Char wiki)
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    # Named only in the screen that fills the slot (special_value_context_for_section)
                    special_values = self.sysfnt_data_json.get('SpecialValues', {}).get(special_value_context, {})
                    key = "0x0a{:02x}".format(hex_val)
                    if key in special_values:
                        build_str += '{' + special_values[key] + '}'
                    else:
                        build_str += "{{x0a{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0a}"
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
                    if 0x20 <= hex_val < 0x20 + len(self.sysfnt_data_json['Locations']):
                        build_str += '{' + self.sysfnt_data_json['Locations'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x0e{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0e}"
            elif hex_val >= 0x19 and hex_val <= 0x1b:  # jp19, jp1a, jp1b: 2-byte, lead byte selects JP font table 1/2/3
                i += 1
                if i < hex_size:
                    old_hex_val = hex_val
                    hex_val = hex_list[i]
                    character = None
                    if self.jp_encoding and hex_val >= 0x20:
                        character = self.caract_jp(hex_val, old_hex_val - 0x18)
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
                character = None
                if self.jp_encoding:  # printable byte 0x20-0xFF => JP font table 0
                    character = self.caract_jp(hex_val, 0)
                if character is None:
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
        self.load_mitem_data()
        self.load_devour_data()
        self.load_camera_category_data()
        self.load_devour_category_data()
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
        self.load_attack_animation_data()
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
        current_file_data.extend(in_file.read())  # one read: byte by byte took seconds on the exe

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
