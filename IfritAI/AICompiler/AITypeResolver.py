# AITypeResolver.py - Complete implementation with error handling
from FF8GameData.dat.daterrors import ParamMagicIdError, ParamMagicTypeError, ParamStatusAIError, ParamItemError, ParamGfError, ParamCardError, \
    ParamSpecialActionError, \
    ParamTargetBasicError, ParamTargetGenericError, ParamTargetSpecificError, ParamTargetSlotError, ParamAptitudeError, ParamSceneOutSlotIdError, \
    ParamSlotIdEnableError, \
    ParamAssignSlotIdError, ParamLocalVarParamError, ComparatorError, ParamCountError, AICodeError, SubjectIdError, ParamIntShiftError, ParamBattleTextError, \
    ParamIntError, \
    ParamPercentError, ParamPercentElemError, ParamBoolError, ParamMonsterAbilityError, ParamLocalVarError, ParamBattleVarError, ParamGlobalVarError
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import *


class AITypeResolver:
    def __init__(self, game_data: GameData, battle_text=(), info_stat_data={}):
        self.game_data = game_data
        self._battle_text = battle_text
        self._info_stat_data = info_stat_data

        # Define which types are lookup types vs formula types
        self.lookup_types = self._get_lookup_type_categories()
        self.formula_types = self._get_formula_type_handlers()

        self.type_mappings = self._build_type_mappings()
        print("Type mapping")
        print(self.type_mappings)

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
            "scene_out_slot_id", "slot_id_enable", "assign_slot_id",
            "card", "item", "gender", "special_byte_check", "subject_id", "hp_percent"
        ]

    def _get_formula_type_handlers(self):
        """Define handlers for formula-based type conversions"""
        return {
            'int': lambda x: self._parse_int(x),
            'monster_line_ability': lambda x: self._parse_int(x),
            'percent': lambda x: self._parse_percent(x),
            'percent_elem': lambda x: self._parse_percent_elem(x),
            'int_shift': lambda x, y: self._parse_int_shift(x, y),
            'bool': lambda x: self._parse_bool(x),
            'alive': lambda x: self._parse_int_shift(x, [3]),
            '': lambda x: 0  # Empty type
        }

    def _parse_int(self, value_str):
        """Parse integer value (formula type)"""
        try:
            if '-' in value_str:
                raise ParamIntError(value_str)
            # Handle hex, binary, decimal
            if value_str.startswith('0x'):
                return int(value_str, 16)
            elif value_str.startswith('0b'):
                return int(value_str, 2)
            else:
                return int(value_str)
        except ValueError:
            raise ParamIntError(value_str)

    def _parse_percent(self, value_str):
        print("parse_percent")
        print(value_str)
        """Parse percentage value (formula type)"""
        if '%' in value_str:
            value_str = value_str.replace('%', '')
            value_str = value_str.replace(' ', '')
            try:
                return int(int(value_str) / 10)
            except ValueError:
                raise ParamPercentError(value_str)
        else:
            return int(value_str)

    def _parse_percent_elem(self, value_str):
        """Parse elemental percentage value (formula type)"""
        try:
            return 900 - int(value_str) * 10
        except ValueError:
            raise ParamPercentElemError(value_str)

    def _parse_int_shift(self, value_str, param):
        """Parse int_shift value (formula type) - shift by -1"""
        try:
            value = int(value_str)
            if value - param[0] < 0:
                raise ValueError
            return value + param[0]
        except ValueError:
            raise ParamIntShiftError(value_str, param[0])

    def _parse_subject_id(self, value_str):
        """Parse subject_id value (formula type)"""
        try:
            # First try direct integer conversion
            return int(value_str)
        except ValueError:
            # Check if it's a named subject
            normalized_val = self._normalize_string(value_str)
            for subject in self.game_data.ai_data_json.get('if_subject', []):
                if self._normalize_string(subject['short_text']) == normalized_val:
                    return subject['subject_id']

            # Not found as integer or named subject
            raise SubjectIdError(value_str)

    def _parse_bool(self, value_str):
        """Parse boolean value (formula type)"""
        lower_val = str(value_str).lower()
        if lower_val in ['true', '1', 'yes', 'on']:
            return 1
        elif lower_val in ['false', '0', 'no', 'off']:
            return 0
        try:
            return int(value_str)
        except ValueError:
            raise ParamBoolError(f"Invalid boolean value: '{value_str}'")

    def _build_type_mappings(self):
        """Build lookup dictionaries from the JSON data"""
        mappings = {}

        # Build mappings for each type from the JSON
        if hasattr(self.game_data, 'ai_data_json'):
            ai_data = self.game_data.ai_data_json

            # Map command names to their parameter types
            mappings['command_signatures'] = {}
            for op_info in ai_data.get('op_code_info', []):
                func_name = op_info.get('func_name')
                param_types = op_info.get('param_type', [])
                if func_name:
                    mappings['command_signatures'][func_name.upper()] = param_types

            # Build type value mappings for lookup types
            mappings['type_values'] = {}

            # Initialize all lookup type categories
            for category in self._get_lookup_type_categories():
                mappings['type_values'][category] = {}

            # Populate known mappings

            # battle_text
            for i, battle_text in enumerate(self._battle_text):
                normalized = self._normalize_string(battle_text)
                print("battle_text")
                print(normalized)
                mappings['type_values']['battle_text'][normalized] = i
            print(mappings['type_values']['battle_text'])
            # magic
            for magic in self.game_data.magic_data_json.get('magic', []):
                normalized = self._normalize_string(magic['name'])
                mappings['type_values']['magic'][normalized] = magic['id']
            # target_basic
            for target_dict in self.__get_target_list(advanced=False, specific=False):
                mappings['type_values']['target_basic'][self._normalize_string(target_dict['data'])] = target_dict['id']
            # monster_ability
            for monster_ability in self.game_data.enemy_abilities_data_json.get('abilities', []):
                normalized = self._normalize_string(monster_ability['name'])
                mappings['type_values']['monster_ability'][normalized] = monster_ability['id']
            # local_var
            for local_var in ai_data.get('list_var', []):
                if local_var.get('var_type') == "local":
                    normalized = self._normalize_string(local_var['var_name'])
                    mappings['type_values']['local_var'][normalized] = local_var['op_code']
            # local_var_param
            for local_var_param in self.__get_possible_local_var_param():
                mappings['type_values']['local_var_param'][self._normalize_string(local_var_param['data'])] = local_var_param['id']
            # battle_var
            for battle_var in ai_data.get('list_var', []):
                if battle_var.get('var_type') == "battle":
                    normalized = self._normalize_string(battle_var['var_name'])
                    mappings['type_values']['battle_var'][normalized] = battle_var['op_code']
            # global_var
            for global_var in ai_data.get('list_var', []):
                if global_var.get('var_type') == "global":
                    normalized = self._normalize_string(global_var['var_name'])
                    mappings['type_values']['global_var'][normalized] = global_var['op_code']
            # target_slot
            for target_slot in self.game_data.ai_data_json.get('target_slot', []):
                normalized = self._normalize_string(target_slot['text'])
                mappings['type_values']['target_slot'][normalized] = target_slot['param_id']
            # special_action
            for special_action in self.game_data.special_action_data_json.get('special_action', []):
                normalized = self._normalize_string(special_action['name'])
                mappings['type_values']['special_action'][normalized] = special_action['id']
            # target_advanced_generic
            for target_dict in self.__get_target_list(advanced=True, specific=False):
                mappings['type_values']['target_advanced_generic'][self._normalize_string(target_dict['data'])] = target_dict['id']
            # target_advanced_specific
            for target_dict in self.__get_target_list(advanced=True, specific=True):
                mappings['type_values']['target_advanced_specific'][self._normalize_string(target_dict['data'])] = target_dict['id']
            # comparator
            for i, comp in enumerate(self.game_data.ai_data_json.get('list_comparator_ifritAI', [])):
                mappings['type_values']['comparator'][comp] = i
            # subject_id
            for subject in ai_data.get('if_subject', []):
                normalized = self._normalize_string(subject['short_text'])
                mappings['type_values']['subject_id'][normalized] = subject['subject_id']
            # status_ai
            for status_ai in self.game_data.status_data_json.get('status_ai', []):
                normalized = self._normalize_string(status_ai['name'])
                mappings['type_values']['status_ai'][normalized] = status_ai['id']
            # activate
            for activate in self.game_data.ai_data_json.get('activate_type', []):
                normalized = self._normalize_string(activate['name'])
                mappings['type_values']['activate'][normalized] = activate['name']
            # aptitude
            for aptitude in self.game_data.ai_data_json.get('aptitude_list', []):
                normalized = self._normalize_string(aptitude['text'])
                mappings['type_values']['aptitude'][normalized] = aptitude['aptitude_id']
            # magic_type
            for magic_type in self.game_data.magic_data_json.get('magic_type', []):
                normalized = self._normalize_string(magic_type['name'])
                mappings['type_values']['magic_type'][normalized] = magic_type['id']
            # gforce
            for gforce in self.game_data.gforce_data_json.get('gforce', []):
                normalized = self._normalize_string(gforce['name'])
                mappings['type_values']['gforce'][normalized] = gforce['id']
            # scene_out_slot_id
            for scene_out_slot_id in self.game_data.ai_data_json.get('scene_out_slot_id', []):
                normalized = self._normalize_string(scene_out_slot_id['text'])
                mappings['type_values']['scene_out_slot_id'][normalized] = scene_out_slot_id['param_id']
            # slot_id_enable
            for slot_id_enable in self.game_data.ai_data_json.get('slot_id_enable', []):
                normalized = self._normalize_string(slot_id_enable['text'])
                mappings['type_values']['slot_id_enable'][normalized] = slot_id_enable['param_id']
            # assign_slot_id
            for assign_slot_id in self.game_data.ai_data_json.get('assign_slot_id', []):
                normalized = self._normalize_string(assign_slot_id['text'])
                mappings['type_values']['assign_slot_id'][normalized] = assign_slot_id['param_id']
            # card
            for card in self.game_data.card_data_json.get('card_info', []):
                normalized = self._normalize_string(card['name'])
                mappings['type_values']['card'][normalized] = card['id']
            # item
            for item in self.game_data.card_data_json.get('items', []):
                normalized = self._normalize_string(item['name'])
                mappings['type_values']['item'][normalized] = item['id']
            # gender
            for gender in self.game_data.ai_data_json.get('gender_type', []):
                normalized = self._normalize_string(gender['type'])
                mappings['type_values']['gender'][normalized] = gender['id']
            # special_byte_check
            for special_byte_check in self.game_data.ai_data_json.get('special_byte_check', []):
                normalized = self._normalize_string(special_byte_check['data'])
                mappings['type_values']['special_byte_check'][normalized] = special_byte_check['id']
            # hp_percent
            for hp_percent in self.game_data.ai_data_json.get('hp_percent', []):
                normalized = self._normalize_string(hp_percent['data'])
                mappings['type_values']['hp_percent'][normalized] = hp_percent['id']
        return mappings

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        if text is None:
            return ""
        return str(text).upper().replace(' ', '_').replace('-', '_')

    def resolve(self, ast):
        """Resolve all symbolic names to their numeric values"""
        return self.visit(ast)

    def visit_Command(self, node):
        """Resolve command parameters based on command signature"""
        cmd_name = node.name.upper()

        # Handle IF command specially
        if cmd_name == 'IF':
            return self._resolve_if_command(node)

        # Handle other commands
        if cmd_name in self.type_mappings['command_signatures']:
            expected_types = self.type_mappings['command_signatures'][cmd_name]
            if node.params:
                resolved_params = self._resolve_param_list(node.params.params, expected_types)
                node.params = ParamList(params=resolved_params)
        return node

    def _resolve_if_command(self, node):
        """Special handling for IF command based on if_subject structure"""
        if not node.params or len(node.params.params) < 4:
            raise ParamCountError(f"IF command expects 4 parameters, got {len(node.params.params) if node.params else 0}")

        # Parameters: [subject_id, left_condition, comparator, right_condition]
        params = node.params.params

        # 1. Resolve subject_id (first parameter)
        subject_id = int(self._resolve_value(params[0], "subject_id"))

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

        # Subject ID - always resolved as int
        resolved_params.append(Value(str(subject_id)))

        # Left condition
        if left_type:
            resolved_left = self._resolve_value(params[1], left_type, param_list)
            resolved_params.append(Value(str(resolved_left)))

        # Comparator
        if len(params) > 2:
            resolved_comparator = self._resolve_value(params[2], 'comparator', param_list)
            resolved_params.append(Value(str(resolved_comparator)))

        # Right condition
        if right_type:
            resolved_right = self._resolve_value(params[3], right_type, param_list)
            resolved_params.append(Value(str(resolved_right)))

        # Update node parameters
        node.params = ParamList(params=resolved_params)
        return node

    def _raise_specific_error(self, param_type, value):
        print("_raise_specific_error")
        print(f"param_type: {param_type}")
        print(f"value: {value}")
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
            'local_var': ParamLocalVarError,
            'battle_var': ParamBattleVarError,
            'global_var': ParamGlobalVarError,
            'local_var_param': ParamLocalVarParamError,
            'comparator': ComparatorError,
            'subject_id': SubjectIdError,
            'monster_ability': ParamMonsterAbilityError,
        }

        error_class = error_classes.get(param_type, AICodeError)
        print(f"error_class: {error_class}")
        raise error_class(value)

    def _resolve_param_list(self, params, expected_types):
        """Resolve a list of parameters based on expected types"""
        resolved = []
        for i, (param, expected_type) in enumerate(zip(params, expected_types)):
            resolved_val = self._resolve_value(param, expected_type)
            resolved.append(Value(str(resolved_val)))
        return resolved

    def _resolve_value(self, value_node, expected_type, param=None):

        print("_resolve_value")
        print(f"value_node: {value_node}")
        print(f"expected_type: {expected_type}")
        print(f"param: {param}")

        """Resolve a single value based on type. Returns int if resolved, raises error otherwise."""
        value_str = value_node.value
        # Removing the "" for string
        if value_str[0] == "\"" and value_str[-1] == "\"" :
            print(value_str)
            value_str = value_str[1:-1]
            print(value_str)
        # Managing hex value
        if "0x" in value_str:
            value_str = str(int(value_str, 16))
        # Check if it's a formula type first
        if expected_type in self.formula_types:
            if param and expected_type in ("int_shift",):
                return self.formula_types[expected_type](value_str, param)
            else:
                return self.formula_types[expected_type](value_str)

        # Check if it's a lookup type
        elif expected_type in self.lookup_types and expected_type in self.type_mappings['type_values']:
            print("lookup type")
            # Look up in type mappings
            normalized = self._normalize_string(value_str)
            mapping = self.type_mappings['type_values'][expected_type]
            print(f"Mapping: {mapping}")
            print(f"normalized: {normalized}")
            # If it's already an integer, check that the ID is a possible value
            if value_str.isdigit():
                print("Digit")
                if int(value_str) in mapping.values():
                    return value_str
            if normalized in mapping:
                print("mapping normalized")
                print(normalized)
                return mapping[normalized]  # Returns int
            # NOT FOUND - raise error with valid values
            self._raise_specific_error(expected_type, value_str)
        # Unknown/unexpected type
        else:
            raise AICodeError(f"Cannot resolve value: '{value_str}"
                            f"Unknown type: {expected_type}")

    def visit_IfStatement(self, node):
        # Resolve the main condition
        if node.condition and node.condition.params:
            # The condition in an IfStatement uses the same structure as Command('IF')
            # So we need to handle it similarly
            self._resolve_if_condition(node.condition)

        # Resolve then block
        self.visit(node.then_block)

        # Resolve elseif branches
        for elif_branch in node.elif_branches:
            if elif_branch.condition and elif_branch.condition.params:
                self._resolve_if_condition(elif_branch.condition)
            self.visit(elif_branch.block)

        # Resolve else block
        if node.else_block:
            self.visit(node.else_block)

        return node

    def _resolve_if_condition(self, condition_node):
        """Resolve an IF condition in an IfStatement"""
        # Create a temporary Command node to reuse the IF resolution logic
        temp_cmd = Command(name='IF', params=condition_node.params)
        resolved_cmd = self._resolve_if_command(temp_cmd)
        condition_node.params = resolved_cmd.params
        return condition_node

    def visit_Block(self, node):
        for i, stmt in enumerate(node.statements):
            node.statements[i] = self.visit(stmt)
        return node

    def visit_ParamList(self, node):
        # ParamList itself doesn't need resolution, its params are resolved elsewhere
        return node

    def visit_Value(self, node):
        # Value nodes are terminal, no resolution needed here
        return node

    def visit(self, node):
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        return node

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
