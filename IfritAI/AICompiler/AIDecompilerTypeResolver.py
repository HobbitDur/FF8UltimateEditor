# AITypeResolver.py - Complete implementation with error handling
from math import floor

from openpyxl.styles.builtins import normal

from FF8GameData.dat.commandanalyser import CommandAnalyser
from FF8GameData.dat.daterrors import ParamMagicIdError, ParamMagicTypeError, ParamStatusAIError, ParamItemError, ParamGfError, ParamCardError, \
    ParamSpecialActionError, \
    ParamTargetBasicError, ParamTargetGenericError, ParamTargetSpecificError, ParamTargetSlotError, ParamAptitudeError, ParamSceneOutSlotIdError, \
    ParamSlotIdEnableError, \
    ParamAssignSlotIdError, ParamLocalVarParamError, ComparatorError, ParamCountError, AICodeError, SubjectIdError, ParamIntShiftError, ParamBattleTextError, \
    ParamIntError, \
    ParamPercentError, ParamPercentElemError, ParamBoolError, ParamMonsterAbilityError, ParamLocalVarError, ParamBattleVarError, ParamGlobalVarError, \
    ParamInt16Error, ParamActivateError, ParamSlotIdError, ParamHpPercentError
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import *


class AIDecompilerTypeResolver:
    def __init__(self, game_data: GameData, battle_text=(), info_stat_data={}):
        self.game_data = game_data
        self._battle_text = battle_text
        self._info_stat_data = info_stat_data

        # Define which types are lookup types vs formula types
        self.lookup_types = self._get_lookup_type_categories()
        self.formula_types = self._get_formula_type_handlers()

        self.type_mappings = self._build_type_mappings()

        # Build if_subject lookup
        self.if_subject_map = {}
        if hasattr(self.game_data, 'ai_data_json'):
            ai_data = self.game_data.ai_data_json
            for subject in ai_data.get('if_subject', []):
                self.if_subject_map[subject['subject_id']] = subject

    def _get_lookup_type_categories(self):
        """Define which types require dictionary lookup"""
        return [
            "battle_text", "magic", "target_basic",
            "monster_ability", "local_var",
            "local_var_param", "battle_var", "global_var",
            "target_slot", "special_action", "target_advanced_generic",
            "target_advanced_specific", "comparator", "status_ai",
            "activate", "aptitude", "magic_type", "gforce",
            "scene_out_slot_id", "slot_id_enable", "assign_slot_id", "slot_id",
            "card", "item", "gender", "special_byte_check", "subject_id", "hp_percent"
        ]

    def _get_formula_type_handlers(self):
        """Define handlers for formula-based type conversions"""
        return {
            'int': lambda x: self._parse_int(x),
            'int16': lambda x: self._parse_int(x),
            'monster_line_ability': lambda x: self._parse_int(x),
            'percent': lambda x: self._parse_percent(x),
            'percent_elem': lambda x: self._parse_percent_elem(x),
            'int_shift': lambda x, y: self._parse_int_shift(x, y),
            'bool': lambda x: self._parse_bool(x),
            'alive': lambda x: self._parse_int_shift(x, [3]),
            'const': lambda x: None,
            '': lambda x: 0  # Empty type
        }

    def _parse_int(self, value: int):
        """Parse integer value (formula type)"""
        return str(value)

    def _parse_int16(self, value:List[int]):
        """Parse integer value (formula type)"""
        return str(int.from_bytes(bytes(value), byteorder='little', signed=True))

    def _parse_percent(self, value: int):
        """Parse percentage value (formula type)"""
        return str(value*10) + '%'

    def _parse_percent_elem(self, value:int):
        """Parse elemental percentage value (formula type)"""
        return str(floor((900 - value) / 10))

    def _parse_int_shift(self, value: int, param: List):
        """Parse int_shift value (formula type)"""
        return str(value + param[0])

    def _parse_bool(self, value: int):
        """Parse boolean value (formula type)"""
        return str(bool(value))

    def _build_type_mappings(self):
        """Build lookup dictionaries from the JSON data"""
        mappings = {}

        # Build mappings for each type from the JSON
        if hasattr(self.game_data, 'ai_data_json'):
            ai_data = self.game_data.ai_data_json

            # Map command names to their parameter types
            mappings['command_signatures'] = {}
            mappings['command_param_index'] = {}
            for op_info in ai_data.get('op_code_info', []):
                func_id = op_info.get('op_code')
                param_types = op_info.get('param_type', [])
                param_index = op_info.get('param_index', [])
                if func_id:
                    mappings['command_signatures'][func_id] = param_types
                    mappings['command_param_index'][func_id] = param_index


            # Build type value mappings for lookup types
            mappings['type_values'] = {}

            # Initialize all lookup type categories
            for category in self._get_lookup_type_categories():
                mappings['type_values'][category] = {}

            # Populate known mappings

            # battle_text
            for i, battle_text in enumerate(self._battle_text):
                normalized = self._normalize_string(battle_text)
                mappings['type_values']['battle_text'][i] = battle_text
            # magic
            for magic in self.game_data.magic_data_json.get('magic', []):
                normalized = self._normalize_string(magic['name'])
                mappings['type_values']['magic'][magic['id']] = normalized
            # target_basic
            for target_dict in self.__get_target_list(advanced=False, specific=False):
                mappings['type_values']['target_basic'][ target_dict['id']] =self._normalize_string(target_dict['data'])
            # monster_ability
            for monster_ability in self.game_data.enemy_abilities_data_json.get('abilities', []):
                normalized = self._normalize_string(monster_ability['name'])
                mappings['type_values']['monster_ability'][monster_ability['id']] = monster_ability['name']
            # local_var
            for local_var in ai_data.get('list_var', []):
                if local_var.get('var_type') == "local":
                    normalized = self._normalize_string(local_var['var_name'])
                    mappings['type_values']['local_var'][local_var['op_code']] = local_var['var_name']
            # local_var_param
            for local_var_param in self.__get_possible_local_var_param():
                mappings['type_values']['local_var_param'][local_var_param['id']] = self._normalize_string(local_var_param['data'])
            # battle_var
            for battle_var in ai_data.get('list_var', []):
                if battle_var.get('var_type') == "battle":
                    normalized = self._normalize_string(battle_var['var_name'])
                    mappings['type_values']['battle_var'][battle_var['op_code']] = battle_var['var_name']
            # global_var
            for global_var in ai_data.get('list_var', []):
                if global_var.get('var_type') == "global":
                    normalized = self._normalize_string(global_var['var_name'])
                    mappings['type_values']['global_var'][global_var['op_code']] = global_var['var_name']
            # target_slot
            for target_slot in self.game_data.ai_data_json.get('target_slot', []):
                normalized = self._normalize_string(target_slot['text'])
                mappings['type_values']['target_slot'][target_slot['param_id']] = normalized
            # special_action
            for special_action in self.game_data.special_action_data_json.get('special_action', []):
                normalized = self._normalize_string(special_action['name'])
                mappings['type_values']['special_action'][ special_action['id']] =special_action['name']
            # target_advanced_generic
            for target_dict in self.__get_target_list(advanced=True, specific=False):
                mappings['type_values']['target_advanced_generic'][target_dict['id']] = self._normalize_string(target_dict['data'])
            # target_advanced_specific
            for target_dict in self.__get_target_list(advanced=True, specific=True):
                mappings['type_values']['target_advanced_specific'][target_dict['id']] = self._normalize_string(target_dict['data'])
            # comparator
            for i, comp in enumerate(self.game_data.ai_data_json.get('list_comparator_ifritAI', [])):
                mappings['type_values']['comparator'][i] = comp
            # subject_id
            for subject in ai_data.get('if_subject', []):
                normalized = self._normalize_string(subject['short_text'])
                mappings['type_values']['subject_id'][ subject['subject_id']] =normalized
            # status_ai
            for status_ai in self.game_data.status_data_json.get('status_ai', []):
                normalized = self._normalize_string(status_ai['name'])
                mappings['type_values']['status_ai'][status_ai['id']] = normalized
            # activate
            for activate in self.game_data.ai_data_json.get('activate_type', []):
                normalized = self._normalize_string(activate['name'])
                mappings['type_values']['activate'][activate['id']] = normalized
            # aptitude
            for aptitude in self.game_data.ai_data_json.get('aptitude_list', []):
                normalized = self._normalize_string(aptitude['text'])
                mappings['type_values']['aptitude'][aptitude['aptitude_id']] = normalized
            # magic_type
            for magic_type in self.game_data.magic_data_json.get('magic_type', []):
                normalized = self._normalize_string(magic_type['name'])
                mappings['type_values']['magic_type'][magic_type['id']] = normalized
            # gforce
            for gforce in self.game_data.gforce_data_json.get('gforce', []):
                normalized = self._normalize_string(gforce['name'])
                mappings['type_values']['gforce'][gforce['id']] = normalized
            # scene_out_slot_id
            for scene_out_slot_id in self.game_data.ai_data_json.get('scene_out_slot_id', []):
                normalized = self._normalize_string(scene_out_slot_id['text'])
                mappings['type_values']['scene_out_slot_id'][ scene_out_slot_id['param_id']] = normalized
            # slot_id_enable
            for slot_id_enable in self.game_data.ai_data_json.get('slot_id_enable', []):
                normalized = self._normalize_string(slot_id_enable['text'])
                mappings['type_values']['slot_id_enable'][slot_id_enable['param_id']] = normalized
            # assign_slot_id
            for assign_slot_id in self.game_data.ai_data_json.get('assign_slot_id', []):
                normalized = self._normalize_string(assign_slot_id['text'])
                mappings['type_values']['assign_slot_id'][assign_slot_id['param_id']] = normalized
            # slot_id
            for slot_id in self.game_data.ai_data_json.get('slot_id', []):
                normalized = self._normalize_string(slot_id['text'])
                mappings['type_values']['slot_id'][slot_id['param_id']] = normalized
            # card
            for card in self.game_data.card_data_json.get('card_info', []):
                normalized = self._normalize_string(card['name'])
                mappings['type_values']['card'][card['id']] = card['name']
            # item
            for item in self.game_data.item_data_json.get('items', []):
                normalized = self._normalize_string(item['name'])
                mappings['type_values']['item'][item['id']] = item['name']
            # gender
            for gender in self.game_data.ai_data_json.get('gender_type', []):
                normalized = self._normalize_string(gender['type'])
                mappings['type_values']['gender'][gender['id']] = normalized
            # special_byte_check
            for special_byte_check in self.game_data.ai_data_json.get('special_byte_check', []):
                normalized = self._normalize_string(special_byte_check['data'])
                mappings['type_values']['special_byte_check'][special_byte_check['id']] = normalized
            # hp_percent
            for hp_percent in self.game_data.ai_data_json.get('hp_percent', []):
                normalized = self._normalize_string(hp_percent['data'])
                mappings['type_values']['hp_percent'][hp_percent['id']] = normalized
        return mappings

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        if text is None:
            return ""
        return str(text).upper().replace(' ', '_').replace('-', '_')

    def resolve(self, command_list:List[CommandAnalyser]):
        """Resolve command parameters based on command signature"""
        print("resolve_decompiler")
        for command_index, command in enumerate(command_list):
            cmd_id = command.get_id()
            print(f"cmd_id: {cmd_id}")

            # Handle IF command specially
            if cmd_id == 0x02:
                self._resolve_if_command(command)
            else:
                # Handle other commands
                type_param = []
                if cmd_id in self.type_mappings['command_signatures']:
                    expected_types = self.type_mappings['command_signatures'][cmd_id]
                    print(f"expected_types: {expected_types}")
                    ignore_iter = False

                    param_list = command.get_op_code()
                    print(f"param_list: {param_list}")
                    print(f"self.type_mappings['command_param_index']: {self.type_mappings['command_param_index']}")
                    param_index = self.type_mappings['command_param_index'][cmd_id]
                    param_ordered = [param_list[i] for i in param_index]

                    print(f"param_ordered: {param_list}")
                    for i, op_code in enumerate(param_ordered):
                        if ignore_iter:
                            ignore_iter = False
                            continue
                        if expected_types[i] in ("int16", ):# 2 params
                            print("int16 expected type")
                            print(param_list)
                            type_param.append(self._resolve_value(int.from_bytes([op_code,param_list[i+1]], signed=True, byteorder='little') , expected_types[i]))
                            ignore_iter = True
                        else:
                         type_param.append( self._resolve_value(op_code, expected_types[i]))
                if type_param:
                    command_list[command_index].param_typed = type_param


    def _resolve_value(self, value, expected_type, special_param=None):
        print("_resolve_value")
        print(f"expected_type: {expected_type}")
        print(f"value: {value}")

        if expected_type in self.lookup_types:
            print(f"self.type_mappings['type_values'][expected_type]: {self.type_mappings['type_values'][expected_type]}")
            return self.type_mappings['type_values'][expected_type][value]
        elif expected_type in self.formula_types:
            if value and expected_type in ("int_shift",):
                return self.formula_types[expected_type](value, special_param)
            else:
                return self.formula_types[expected_type](value)


    def _resolve_if_command(self, command:CommandAnalyser):
        # Handle other commands
        type_param = []

        if not command.get_op_code() or len(command.get_op_code()) < 7:
            raise ParamCountError(f"IF command expects 7 parameters, got {len(command.get_op_code()) if command.get_op_code() else 0}")

        # Parameters: [subject_id, left_condition, comparator, right_condition]
        params = command.get_op_code()

        # 1. Resolve subject_id (first parameter)
        subject_id = params[0]
        print(f"subject_id: {subject_id}")

        subject_str = self._resolve_value(subject_id, "subject_id")

        # 2. Get subject info
        subject_info = self.if_subject_map.get(subject_id)
        if not subject_info:
            raise AICodeError(f"Unknown subject_id: {subject_id}")

        # 3. Get parameter types for this subject
        left_type = subject_info.get('param_left_type', '')
        right_type = subject_info.get('param_right_type', '')

        # 4. Handle special cases with param_list
        if 'param_list' in subject_info and subject_info['param_list']:
            param_list = subject_info['param_list']
        else:
            param_list = None

        # 5. Resolve each parameter
        resolved_params = []

        # Subject ID
        resolved_params.append(subject_str)

        # Left condition
        if left_type:
            resolved_left = self._resolve_value(params[1], left_type, param_list)
            resolved_params.append(resolved_left)

        # Comparator
        if len(params) > 2:
            resolved_comparator = self._resolve_value(params[2], 'comparator')
            resolved_params.append(resolved_comparator)

        # Right condition
        if right_type:
            resolved_right = self._resolve_value(int.from_bytes(bytes(params[3:5]), byteorder='little', signed=True), right_type, param_list)
            resolved_params.append(resolved_right)

        command.param_typed = resolved_params


    def _raise_specific_error(self, param_type, value):
        """Raise specific error based on parameter type"""
        error_classes = {
            'battle_text': ParamBattleTextError,
            'magic': ParamMagicIdError,
            'magic_type': ParamMagicTypeError,
            'status_ai': ParamStatusAIError,
            'item': ParamItemError,
            'gforce': ParamGfError,
            'card': ParamCardError,
            'special_action': ParamSpecialActionError,
            'target_basic': ParamTargetBasicError,
            'target_advanced_generic': ParamTargetGenericError,
            'target_advanced_specific': ParamTargetSpecificError,
            'target_slot': ParamTargetSlotError,
            'aptitude': ParamAptitudeError,
            'scene_out_slot_id': ParamSceneOutSlotIdError,
            'slot_id_enable': ParamSlotIdEnableError,
            'assign_slot_id': ParamAssignSlotIdError,
            'slot_id': ParamSlotIdError,
            'local_var': ParamLocalVarError,
            'battle_var': ParamBattleVarError,
            'global_var': ParamGlobalVarError,
            'local_var_param': ParamLocalVarParamError,
            'comparator': ComparatorError,
            'subject_id': SubjectIdError,
            'monster_ability': ParamMonsterAbilityError,
            'activate': ParamActivateError,
            'hp_percent': ParamHpPercentError,
        }

        error_class = error_classes.get(param_type, AICodeError)
        raise error_class(value)

    def _resolve_param_list(self, params, expected_types):
        """Resolve a list of parameters based on expected types"""
        print("_resolve_param_list")
        print(params)
        resolved = []
        for i, (param, expected_type) in enumerate(zip(params, expected_types)):
            resolved_val = self._resolve_value(param, expected_type)
            resolved.append(Value(str(resolved_val)))
        return resolved

    def __get_target_list(self, advanced=False, specific=False, slot=False):
        list_target = []
        # The target list has 4 different type of target:
        # 1. The characters
        # 2. All monsters of the game
        # 3. Special target
        # 4. Target stored in variable

        if not slot:
            for i in range(len(self.game_data.ai_data_json['list_target_char'])):
                list_target.append({"id": i, "data": self.game_data.ai_data_json['list_target_char'][i]})
            for i in range(0, len(self.game_data.monster_data_json["monster"])):
                list_target.append({"id": i + 16, "data": self.game_data.monster_data_json["monster"][i]["name"]})
        if slot:
            list_target_data = self.game_data.ai_data_json['target_slot']
        elif advanced:
            if specific:
                list_target_data = self.game_data.ai_data_json['target_advanced_specific']
            else:
                list_target_data = self.game_data.ai_data_json['target_advanced_generic']
        else:
            list_target_data = self.game_data.ai_data_json['target_basic']

        for el in list_target_data:
            if el['param_type'] == "monster_name":
                data = "self"
            elif el['param_type'] == "":
                data = None
            else:
                print("Unexpected param type for target: {}".format(el['param_type']))
                data = None
            if data:
                text = el['text'].format(data)
            else:
                text = el['text']
            list_target.append({"id": el['param_id'], "data": text})
        return list_target

    def __get_target(self, id, advanced=False, specific=False, slot=False):
        target = [x['data'] for x in self.__get_target_list(advanced, specific, slot) if x['id'] == id]
        if target:
            return target[0]
        else:
            print("Unexpected target with id: {}".format(id))
            return "UNKNOWN TARGET"

    def __get_possible_local_var_param(self):
        param_possible = []
        special_param_id = [val_dict["param_id"] for val_dict in self.game_data.ai_data_json["local_var_param"]]
        for i in range(0, 256):
            if i in special_param_id:
                param_possible.append([{'id': val_dict['param_id'], 'data': val_dict['text']}
                                       for val_dict in self.game_data.ai_data_json["local_var_param"] if val_dict['param_id'] == i][0])
            else:
                param_possible.append({'id': i, 'data': str(i)})
        return param_possible
