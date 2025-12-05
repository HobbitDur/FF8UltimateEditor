# AITypeResolver.py - Complete implementation with error handling
from FF8GameData.dat.daterrors import LineError, ParamMagicIdError, ParamMagicTypeError, ParamStatusAIError, ParamItemError, ParamGfError, ParamCardError, ParamSpecialActionError, \
    ParamTargetBasicError, ParamTargetGenericError, ParamTargetSpecificError, ParamTargetSlotError, ParamAptitudeError, ParamSceneOutSlotIdError, ParamSlotIdEnableError, \
    ParamAssignSlotIdError, ParamLocalVarParamError, ComparatorError, ParamCountError
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import *


class AITypeResolver:
    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.type_mappings = self._build_type_mappings()

        # Define which types are lookup types vs formula types
        self.lookup_types = self._get_lookup_type_categories()
        self.formula_types = self._get_formula_type_handlers()

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
            "monster_ability", "monster_line_ability", "local_var",
            "local_var_param", "battle_var", "global_var",
            "target_slot", "special_action", "target_advanced_generic",
            "target_advanced_specific", "comparator", "status_ai",
            "activate", "aptitude", "magic_type", "gforce",
            "scene_out_slot_id", "slot_id_enable", "assign_slot_id",
            "card", "item", "gender", "special_byte_check", "alive"
        ]

    def _get_formula_type_handlers(self):
        """Define handlers for formula-based type conversions"""
        return {
            'int': lambda x: self._parse_int(x),
            'percent': lambda x: self._parse_percent(x),
            'percent_elem': lambda x: self._parse_percent_elem(x),
            'int_shift': lambda x: self._parse_int_shift(x),
            'subject_id': lambda x: self._parse_subject_id(x),
            'bool': lambda x: self._parse_bool(x),
            '': lambda x: 0  # Empty type
        }

    def _parse_int(self, value_str):
        """Parse integer value (formula type)"""
        try:
            # Handle hex, binary, decimal
            if value_str.startswith('0x'):
                return int(value_str, 16)
            elif value_str.startswith('0b'):
                return int(value_str, 2)
            else:
                return int(value_str)
        except ValueError:
            raise LineError(f"Invalid integer value: '{value_str}'")

    def _parse_percent(self, value_str):
        """Parse percentage value (formula type)"""
        try:
            return int(value_str)/10
        except ValueError:
            raise LineError(f"Invalid percentage value: '{value_str}'")

    def _parse_percent_elem(self, value_str):
        """Parse elemental percentage value (formula type)"""
        try:
            return 900 - int(value_str)*10
        except ValueError:
            raise LineError(f"Invalid percentage elem value: '{value_str}'")

    def _parse_int_shift(self, value_str):
        """Parse int_shift value (formula type) - shift by -1"""
        try:
            value = int(value_str)
            return value - 1
        except ValueError:
            raise LineError(f"Invalid int_shift value: '{value_str}'")

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
            raise LineError(f"Invalid subject_id: '{value_str}'. "
                            f"Must be a number or a valid subject name.")

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
            raise LineError(f"Invalid boolean value: '{value_str}'")

    def _build_type_mappings(self):
        """Build lookup dictionaries from the JSON data"""
        mappings = {}

        # Build mappings for each type from the JSON
        if hasattr(self.game_data, 'ai_data_json'):
            data = self.game_data.ai_data_json

            # Map command names to their parameter types
            mappings['command_signatures'] = {}
            for op_info in data.get('op_code_info', []):
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
            if 'magic' in mappings['type_values']:
                for magic in self.game_data.magic_data_json.get('magic', []):
                    normalized = self._normalize_string(magic['name'])
                    mappings['type_values']['magic'][normalized] = magic['id']

            if 'comparator' in mappings['type_values']:
                for i, comp in enumerate(self.game_data.ai_data_json.get('list_comparator_ifritAI', [])):
                    mappings['type_values']['comparator'][comp] = i

            if 'local_var' in mappings['type_values']:
                for var in data.get('list_var', []):
                    if var.get('var_type') == "local":
                        normalized = self._normalize_string(var['var_name'])
                        mappings['type_values']['local_var'][normalized] = var['op_code']

            if 'battle_var' in mappings['type_values']:
                for var in data.get('list_var', []):
                    if var.get('var_type') == "battle":
                        normalized = self._normalize_string(var['var_name'])
                        mappings['type_values']['battle_var'][normalized] = var['op_code']

            if 'global_var' in mappings['type_values']:
                for var in data.get('list_var', []):
                    if var.get('var_type') == "global":
                        normalized = self._normalize_string(var['var_name'])
                        mappings['type_values']['global_var'][normalized] = var['op_code']

            if "target_advanced_specific" in mappings['type_values']:
                for target_dict in self.__get_target_list(advanced=True, specific=True):
                    mappings['type_values']['target_advanced_specific'][target_dict['data']] = target_dict['id']

            if "target_advanced_generic" in mappings['type_values']:
                for target_dict in self.__get_target_list(advanced=True, specific=False):
                    mappings['type_values']['target_advanced_generic'][target_dict['data']] = target_dict['id']

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
                resolved_params = self._resolve_param_list(node.params.params, expected_types, cmd_name)
                node.params = ParamList(params=resolved_params)
        return node

    def _resolve_if_command(self, node):
        """Special handling for IF command based on if_subject structure"""
        if not node.params or len(node.params.params) < 4:
            raise ParamCountError(f"IF command expects 4 parameters, got {len(node.params.params) if node.params else 0}")

        # Parameters: [subject_id, left_condition, comparator, right_condition]
        params = node.params.params

        # Create context for error messages
        context = f"IF command parameter"

        # 1. Resolve subject_id (first parameter)
        try:
            subject_id_val = self._resolve_value(params[0], 'subject_id' + " 0 (subject_id)")
            subject_id = int(subject_id_val) if isinstance(subject_id_val, (int, float)) else 0
        except (ValueError, LineError):
            subject_id = 0

        # 2. Get subject info
        subject_info = self.if_subject_map.get(subject_id)
        if not subject_info:
            raise LineError(f"Unknown subject_id: {subject_id}")

        # 3. Get parameter types for this subject
        left_type = subject_info.get('param_left_type', '')
        right_type = subject_info.get('param_right_type', '')

        # 4. Handle special cases with param_list
        if 'param_list' in subject_info and subject_info['param_list']:
            return self._resolve_if_with_constants(node, subject_info)

        # 5. Resolve each parameter
        resolved_params = []

        # Subject ID - always resolved as int
        resolved_params.append(Value(str(subject_id)))

        # Left condition
        if left_type:
            try:
                resolved_left = self._resolve_value(params[1], left_type + " 1 (left condition)")
                resolved_params.append(Value(str(resolved_left)))
            except LineError as e:
                # Raise specific error based on type
                self._raise_specific_error(left_type, params[1].value, e.message)
        else:
            # No type specified, keep original
            resolved_params.append(params[1])

        # Comparator
        if len(params) > 2:
            try:
                resolved_comparator = self._resolve_value(params[2], 'comparator' + " 2 (comparator)")
                resolved_params.append(Value(str(resolved_comparator)))
            except LineError:
                raise ComparatorError(params[2].value)
        else:
            resolved_params.append(Value("0"))  # Default comparator "=="

        # Right condition
        if right_type:
            try:
                resolved_right = self._resolve_value(params[3], right_type + " 3 (right condition)")
                resolved_params.append(Value(str(resolved_right)))
            except LineError as e:
                # Raise specific error based on type
                self._raise_specific_error(right_type, params[3].value, e.message)
        else:
            resolved_params.append(params[3] if len(params) > 3 else Value("0"))

        # Update node parameters
        node.params = ParamList(params=resolved_params)
        return node

    def _raise_specific_error(self, param_type, value):
        """Raise specific error based on parameter type"""
        error_classes = {
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
            'local_var_param': ParamLocalVarParamError,
            'comparator': ComparatorError,
        }

        error_class = error_classes.get(param_type, LineError)
        raise error_class(value)

    def _resolve_if_with_constants(self, node, subject_info):
        """Handle IF subjects that have constant parameters in param_list"""
        subject_id = subject_info['subject_id']
        param_list = subject_info.get('param_list', [])
        params = node.params.params

        resolved_params = []

        # Add subject_id
        resolved_params.append(Value(str(subject_id)))

        # Add constant parameters from param_list
        for const_val in param_list:
            resolved_params.append(Value(str(const_val)))

        # Fill remaining slots with resolved parameters
        left_type = subject_info.get('param_left_type', '')
        right_type = subject_info.get('param_right_type', '')

        context = f"IF command (subject {subject_id})"

        # We need to handle up to 4 parameters total
        for i in range(1, 4):  # Skip subject_id at index 0
            if i < len(resolved_params):
                # This slot is already filled by a constant
                continue

            if i < len(params):
                param = params[i]
                if i == 1 and left_type:  # Left condition
                    try:
                        resolved = self._resolve_value(param, left_type + f" parameter {i}")
                        resolved_params.append(Value(str(resolved)))
                    except LineError as e:
                        self._raise_specific_error(left_type, param.value, e.message)
                elif i == 2:  # Comparator
                    try:
                        resolved = self._resolve_value(param, 'comparator' + f" parameter {i}")
                        resolved_params.append(Value(str(resolved)))
                    except LineError:
                        raise ComparatorError(param.value)
                elif i == 3 and right_type:  # Right condition
                    try:
                        resolved = self._resolve_value(param, right_type + f" parameter {i}")
                        resolved_params.append(Value(str(resolved)))
                    except LineError as e:
                        self._raise_specific_error(right_type, param.value, e.message)
                else:
                    resolved_params.append(param)
            else:
                # No parameter provided, use default
                resolved_params.append(Value("0"))

        # Ensure we have exactly 4 parameters
        while len(resolved_params) < 4:
            resolved_params.append(Value("0"))
        resolved_params = resolved_params[:4]

        node.params = ParamList(params=resolved_params)
        return node

    def _resolve_param_list(self, params, expected_types, command_name=""):
        """Resolve a list of parameters based on expected types"""
        resolved = []
        for i, (param, expected_type) in enumerate(zip(params, expected_types)):
            context = f"{command_name} parameter {i}"
            try:
                resolved_val = self._resolve_value(param, expected_type)
                resolved.append(Value(str(resolved_val)))
            except LineError as e:
                # Raise specific error based on type
                self._raise_specific_error(expected_type, param.value, e.message)
        return resolved

    def _resolve_value(self, value_node, expected_type):
        """Resolve a single value based on type. Returns int if resolved, raises error otherwise."""
        value_str = value_node.value

        # Check if it's a formula type first
        if expected_type in self.formula_types:
            return self.formula_types[expected_type](value_str)

        # Check if it's a lookup type
        elif expected_type in self.lookup_types and expected_type in self.type_mappings['type_values']:
            # Look up in type mappings
            normalized = self._normalize_string(value_str)
            mapping = self.type_mappings['type_values'][expected_type]

            if normalized in mapping:
                return mapping[normalized]  # Returns int

            # NOT FOUND - raise error with valid values
            self._raise_specific_error(expected_type, value_str)
        # Unknown/unexpected type
        else:
            raise LineError(f"Cannot resolve value: '{value_str}"
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