"""Information & stats section as json.

The values are the ones the Stat tab and the xlsx show (percentages, element names...), and every
id is written next to a "name" so the file reads without a lookup table. The "name" fields are
only a help for the reader: on import only the ids count.

    "low_lvl_mug": [{"id": 1, "value": 1, "name": "Potion"}, ...]
    "elem_def": {"Fire": 100, "Ice": 100, ...}

A key missing from the file keeps the value the .dat already has, so a file can hold only the
values a mod changes. An unknown key is an error (most likely a typo).
"""
import json
import pathlib

from FF8GameData.GenericSection.ff8text import FF8Text
from FF8GameData.monsterdata import AIData
from .common import SectionFileError

ITEM_LIST_KEYS = ['low_lvl_mag', 'med_lvl_mag', 'high_lvl_mag', 'low_lvl_mug', 'med_lvl_mug', 'high_lvl_mug',
                  'low_lvl_drop', 'med_lvl_drop', 'high_lvl_drop']
CARD_KEYS = [name.lower() for name in AIData.CARD_OBTAIN_ORDER]  # drop, mod, rare_mod
MONSTER_NAME_SIZE = 24
# Bit names of each flag byte, bit 0 first. A byte flag dict read from an older xlsx can carry
# older names; only the bit order matters, so the json always uses these names.
BYTE_FLAG_BIT_NAMES = {
    'byte_flag_0': AIData.SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE,
    'byte_flag_1': AIData.SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE,
    'byte_flag_2': AIData.SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE,
    'byte_flag_3': AIData.SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE,
}


def _name_of(table: list, id_value: int) -> str:
    for entry in table:
        if entry['id'] == id_value:
            return entry['name']
    return "Unknown"


def _ability_name(game_data, ability_type: int, ability_id: int) -> str:
    type_name = _name_of(game_data.enemy_abilities_data_json['abilities_type'], ability_type)
    if type_name == "Magic":
        return _name_of(game_data.magic_data_json['magic'], ability_id)
    if type_name == "Item":
        return _name_of(game_data.item_data_json['items'], ability_id)
    return _name_of(game_data.enemy_abilities_data_json['abilities'], ability_id)


# ---------------------------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------------------------

def info_stat_to_json_dict(info_stat_data: dict, game_data) -> dict:
    stat_names = [stat['name'] for stat in game_data.stat_data_json['stat']]
    json_dict = {}
    for key, value in info_stat_data.items():
        if key == 'monster_name':
            json_dict[key] = value.get_str()
        elif key in stat_names:
            json_dict[key] = list(value)
        elif key in AIData.ABILITIES_HIGHNESS_ORDER:
            json_dict[key] = [{'type': ability['type'], 'id': ability['id'], 'animation': ability['animation'],
                               'type_name': _name_of(game_data.enemy_abilities_data_json['abilities_type'], ability['type']),
                               'name': _ability_name(game_data, ability['type'], ability['id'])}
                              for ability in value]
        elif key in ITEM_LIST_KEYS:
            table = game_data.magic_data_json['magic'] if key.endswith('_mag') else game_data.item_data_json['items']
            json_dict[key] = [{'id': item['ID'], 'value': item['value'], 'name': _name_of(table, item['ID'])}
                              for item in value]
        elif key == 'card':
            json_dict[key] = {card_key: {'id': card_id, 'name': _name_of(game_data.card_data_json['card_info'], card_id)}
                              for card_key, card_id in zip(CARD_KEYS, value)}
        elif key == 'devour':
            json_dict[key] = [{'id': devour_id, 'name': _name_of(game_data.devour_data_json['devour'], devour_id)}
                              for devour_id in value]
        elif key == 'renzokuken':
            json_dict[key] = [{'id': anim_id, 'name': _name_of(game_data.attack_animation_data_json['attack_animation'], anim_id)}
                              for anim_id in value]
        elif key == 'elem_def':
            json_dict[key] = {element['name']: percent for element, percent in zip(game_data.magic_data_json['magic_type'], value)}
        elif key == 'status_def':
            json_dict[key] = {status['name']: percent for status, percent in zip(game_data.status_data_json['status'], value)}
        elif key in ['mug_rate', 'drop_rate']:
            # Stored as a byte (0-255) shown as a percentage: 2 decimals are enough to get the
            # exact byte back (one byte step is 0.39%).
            json_dict[key] = float(round(value, 2))
        elif key in AIData.BYTE_FLAG_LIST:
            json_dict[key] = dict(zip(BYTE_FLAG_BIT_NAMES[key], value.values()))
        else:  # Plain values: levels, xp, ap, padding
            json_dict[key] = value
    return json_dict


def format_json(json_dict: dict) -> str:
    """json.dumps with a layout made for reading: one line per top-level value, and for a list or
    object value one line per entry (one ability, one item, one element...)."""
    def one_line(value):
        return json.dumps(value, ensure_ascii=False)

    top_lines = []
    for key, value in json_dict.items():
        if isinstance(value, list) and any(isinstance(entry, (dict, list)) for entry in value):
            entry_lines = [f"    {one_line(entry)}" for entry in value]
            top_lines.append(f"  {one_line(key)}: [\n" + ",\n".join(entry_lines) + "\n  ]")
        elif isinstance(value, dict):
            entry_lines = [f"    {one_line(sub_key)}: {one_line(sub_value)}" for sub_key, sub_value in value.items()]
            top_lines.append(f"  {one_line(key)}: {{\n" + ",\n".join(entry_lines) + "\n  }")
        else:
            top_lines.append(f"  {one_line(key)}: {one_line(value)}")
    return "{\n" + ",\n".join(top_lines) + "\n}\n"


def export_section(enemy, file_path: pathlib.Path, tools):
    json_dict = info_stat_to_json_dict(enemy.info_stat_data, tools.game_data)
    file_path.write_text(format_json(json_dict), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------------------------

class _Reader:
    """Reads json values back with an error message naming the file and the key on any mistake."""

    def __init__(self, file_path):
        self.file_path = file_path

    def fail(self, where: str, message: str):
        raise SectionFileError(f"{self.file_path}: {where}: {message}")

    def read_int(self, value, where: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(where, f"expected an integer, got {json.dumps(value)}")
        return value

    def read_number(self, value, where: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.fail(where, f"expected a number, got {json.dumps(value)}")
        return value

    def read_list(self, value, size: int, where: str) -> list:
        if not isinstance(value, list) or len(value) != size:
            self.fail(where, f"expected a list of {size} entries")
        return value

    def read_dict(self, value, keys: list, where: str) -> dict:
        if not isinstance(value, dict):
            self.fail(where, "expected an object")
        missing = [key for key in keys if key not in value]
        unknown = [key for key in value if key not in keys]
        if missing or unknown:
            self.fail(where, f"missing keys {missing}, unknown keys {unknown} (expected {keys})")
        return value


def json_dict_to_info_stat(json_dict: dict, info_stat_data: dict, game_data, file_path):
    """Write the values of json_dict into info_stat_data (in place). Keys absent from json_dict
    are left untouched."""
    read = _Reader(file_path)
    stat_names = [stat['name'] for stat in game_data.stat_data_json['stat']]
    unknown_keys = [key for key in json_dict if key not in info_stat_data]
    if unknown_keys:
        read.fail("top level", f"unknown keys {unknown_keys}")

    for key, value in json_dict.items():
        if key == 'monster_name':
            if not isinstance(value, str):
                read.fail(key, "expected a text")
            name = FF8Text(game_data=game_data, own_offset=0, data_hex=bytearray(), id=0)
            try:
                name.set_str(value)
            except ValueError as error:
                read.fail(key, f"has a character FF8 cannot write: {error}")
            if len(name.get_data_hex()) > MONSTER_NAME_SIZE:
                read.fail(key, f"is too long ({len(name.get_data_hex())} bytes, {MONSTER_NAME_SIZE} max)")
            info_stat_data[key] = name
        elif key in stat_names:
            info_stat_data[key] = [read.read_int(stat, f"{key}[{index}]") for index, stat in enumerate(read.read_list(value, 4, key))]
        elif key in AIData.ABILITIES_HIGHNESS_ORDER:
            abilities = []
            for index, ability in enumerate(read.read_list(value, len(info_stat_data[key]), key)):
                where = f"{key}[{index}]"
                if not isinstance(ability, dict):
                    read.fail(where, "expected an object")
                abilities.append({'type': read.read_int(ability.get('type'), where + ".type"),
                                  'animation': read.read_int(ability.get('animation'), where + ".animation"),
                                  'id': read.read_int(ability.get('id'), where + ".id")})
            info_stat_data[key] = abilities
        elif key in ITEM_LIST_KEYS:
            items = []
            for index, item in enumerate(read.read_list(value, 4, key)):
                where = f"{key}[{index}]"
                if not isinstance(item, dict):
                    read.fail(where, "expected an object")
                items.append({'ID': read.read_int(item.get('id'), where + ".id"),
                              'value': read.read_int(item.get('value'), where + ".value")})
            info_stat_data[key] = items
        elif key == 'card':
            cards = read.read_dict(value, CARD_KEYS, key)
            info_stat_data[key] = [read.read_int(_id_of(cards[card_key], read, f"card.{card_key}"), f"card.{card_key}.id")
                                   for card_key in CARD_KEYS]
        elif key in ['devour', 'renzokuken']:
            entries = read.read_list(value, len(info_stat_data[key]), key)
            info_stat_data[key] = [read.read_int(_id_of(entry, read, f"{key}[{index}]"), f"{key}[{index}].id")
                                   for index, entry in enumerate(entries)]
        elif key == 'elem_def':
            names = [element['name'] for element in game_data.magic_data_json['magic_type']]
            percents = read.read_dict(value, names, key)
            info_stat_data[key] = [read.read_int(percents[name], f"elem_def.{name}") for name in names]
        elif key == 'status_def':
            names = [status['name'] for status in game_data.status_data_json['status']]
            percents = read.read_dict(value, names, key)
            info_stat_data[key] = [read.read_int(percents[name], f"status_def.{name}") for name in names]
        elif key in ['mug_rate', 'drop_rate']:
            info_stat_data[key] = read.read_number(value, key)
        elif key in AIData.BYTE_FLAG_LIST:
            flags = read.read_dict(value, BYTE_FLAG_BIT_NAMES[key], key)
            info_stat_data[key] = {flag: read.read_int(flags[flag], f"{key}.{flag}") for flag in BYTE_FLAG_BIT_NAMES[key]}
        else:
            info_stat_data[key] = read.read_int(value, key)


def _id_of(entry, read: _Reader, where: str):
    if not isinstance(entry, dict):
        read.fail(where, "expected an object with an \"id\"")
    return entry.get('id')


def apply_section(enemy, file_path: pathlib.Path, tools):
    try:
        json_dict = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SectionFileError(f"{file_path}: not valid json: {error}")
    if not isinstance(json_dict, dict):
        raise SectionFileError(f"{file_path}: the json must be an object")
    json_dict_to_info_stat(json_dict, enemy.info_stat_data, tools.game_data, file_path)
    # Serialise once now, so a value that does not fit its bytes (a stat above 255...) is reported
    # against this file instead of failing later, when the .dat is written.
    section_index = enemy.SECTION_INDEX_BY_ENTITY[enemy.entity_type]['info_stat']
    try:
        enemy.prepare_info(bytearray(), section_index, tools.game_data)
    except (OverflowError, ValueError) as error:
        raise SectionFileError(f"{file_path}: a value is out of its range: {error}")
