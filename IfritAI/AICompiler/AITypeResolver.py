# AITypeResolver.py
from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import *


class AITypeResolver:
    def __init__(self, game_data:GameData):
        self.game_data = game_data
        self.type_mappings = self._build_type_mappings()

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
                    mappings['command_signatures'][func_name] = param_types

            # Build type value mappings (like gforce, target_basic, etc.)
            mappings['type_values'] = {}

            # Map all the types from your JSON structure
            type_categories = [
                "battle_text",  # Used by: print, printSpeed, printAndLock, printAlt
                "magic",  # Used by: prepareMagic
                "target_basic",  # Used by: target
                "int",
                # Used by: prepareAnim, anim, unknown13, bvar, gvar, badd, gadd, doNothing, enterAlt, waitText, enter, waitTextFast, setScanText, jump, targetAllySlot, addMaxHP
                "monster_ability",  # Used by: prepareMonsterAbility
                "monster_line_ability",  # Used by: useRandom, use
                "local_var",  # Used by: var, add
                "local_var_param",  # Used by: var, add
                "battle_var",  # Used by: bvar, badd
                "global_var",  # Used by: gvar, gadd
                "bool",  # Used by: setEscape
                "target_slot",  # Used by: leave
                "special_action",  # Used by: specialAction
                "target_advanced_generic",  # Used by: targetStatus
                "comparator",  # Used by: targetStatus
                "status_ai",  # Used by: targetStatus, autoStatus
                "activate",  # Used by: autoStatus
                "aptitude",  # Used by: statChange
                "percent",  # Used by: statChange
                "magic_type",  # Used by: elemDmgMod
                "percent_elem",  # Used by: elemDmgMod
                "gforce",  # Used by: giveGF
                "scene_out_slot_id",  # Used by: enable, assignSlot
                "slot_id_enable",  # Used by: loadAndTargetable
                "int_shift",  # Used by: targetableSlot
                "assign_slot_id",  # Used by: assignSlot
                "card",  # Used by: giveCard
                "item"  # Used by: giveItem
            ]

            for category in type_categories:
                mappings['type_values'][category] = {}
                if category == "magic":
                    for magic in self.game_data.magic_data_json['magic']:
                        normalized = self._normalize_string(magic['name'])
                        mappings['type_values']['magic'][normalized] = magic['id']
        return mappings

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        return text.upper().replace(' ', '_').replace('-', '_')

    def resolve(self, ast):
        """Resolve all symbolic names to their numeric values"""
        return self.visit(ast)

    def visit_Command(self, node):
        if node.params and node.name in self.type_mappings['command_signatures']:
            expected_types = self.type_mappings['command_signatures'][node.name]
            resolved_params = []

            for i, (param, expected_type) in enumerate(zip(node.params.params, expected_types)):
                if expected_type in self.type_mappings['type_values']:
                    # This parameter should be resolved using the type mapping
                    resolved_value = self._resolve_typed_value(param.value, expected_type)
                    resolved_params.append(Value(str(resolved_value)))
                else:
                    # Keep as is (for int, string literals, etc.)
                    resolved_params.append(param)

            node.params = ParamList(params=resolved_params)

        return node

    def _resolve_typed_value(self, string_value, expected_type):
        """Resolve a string value to its numeric equivalent based on type"""
        if expected_type not in self.type_mappings['type_values']:
            return string_value  # No mapping for this type

        normalized_input = self._normalize_string(string_value)
        type_mapping = self.type_mappings['type_values'][expected_type]

        if normalized_input in type_mapping:
            return type_mapping[normalized_input]
        else:
            # Check if it's already a numeric value
            if string_value.isdigit():
                return string_value
            else:
                raise ValueError(f"Invalid {expected_type} value: '{string_value}'. "
                                 f"Valid values: {list(type_mapping.keys())}")

    def visit_IfStatement(self, node):
        # If conditions also need type resolution
        # The condition parameters follow the if_subject structure
        if hasattr(self.game_data, 'ai_data_json'):
            if_subjects = self.game_data.ai_data_json.get('if_subject', [])
            # You'll need to determine which subject_id is being used
            # and resolve parameters accordingly
            pass

        # Visit all blocks
        self.visit(node.then_block)
        for elif_branch in node.elif_branches:
            self.visit(elif_branch.block)
        if node.else_block:
            self.visit(node.else_block)
        return node

    def visit_Block(self, node):
        for stmt in node.statements:
            self.visit(stmt)
        return node

    def visit(self, node):
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        return node