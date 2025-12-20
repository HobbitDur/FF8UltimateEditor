from enum import Enum

from .daterrors import ParamSlotIdEnableError, ParamLocalVarParamError, ParamSceneOutSlotIdError, ParamAssignSlotIdError, ParamMagicIdError, \
    ParamMagicTypeError, ParamStatusAIError, ComparatorError, ParamItemError, ParamGfError, ParamCardError, ParamSpecialActionError, ParamTargetBasicError, \
    ParamTargetSpecificError, ParamTargetGenericError, ParamTargetSlotError, ParamAptitudeError
from ..gamedata import GameData


class CurrentIfType(Enum):
    MAGIC = 0
    ITEM = 1
    GFORCE = 2
    SPECIAL_ACTION = 3
    NONE = 4


class CommandAnalyser:
    PARAM_CHAR_LEFT = "["
    PARAM_CHAR_RIGHT = "]"

    def __init__(self, op_id: int, op_code: list, game_data: GameData, battle_text=(), info_stat_data={},
                 line_index=0, color="#0055ff", text_param=False, current_if_type=CurrentIfType.NONE, comment: str = ""):
        self.__op_id = op_id
        self.__op_code = op_code
        self.__battle_text = battle_text
        self.__text_colored = ""
        self.game_data = game_data
        self.info_stat_data = info_stat_data
        self.__color_param = color
        self.line_index = line_index
        self.__if_index = 0
        self.type_data = []
        self.id_possible_list = [{'id': x['op_code'], 'data': x['short_text']} for x in self.game_data.ai_data_json['op_code_info']]
        self.param_possible_list = []
        self.__size = 0
        self.__raw_text = ""
        self.__raw_parameters = []
        self.param_typed = []
        self.__raw_text_added = []
        self.__current_if_type = current_if_type
        self.__jump_value = 0
        self.__comment = comment
        if text_param:
            self.__analyse_op_data_with_text_param()
        else:
            pass
            #self.__analyse_op_data()

    def __str__(self):
        return f"Command(id: {self.__op_id}, param: {self.__op_code}, param_type: {self.param_typed}, text: {self.get_text()}, line_index: {self.line_index})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if self.__op_id == other.__op_id and self.__op_code == other.__op_code:
            return True
        return False


    def reset_data(self):
        self.param_possible_list = []
        self.__if_index = 0
        self.type_data = []
        self.__size = 0
        self.__raw_text = ""
        self.__raw_parameters = []
        self.__raw_text_added = []

    def get_current_if_type(self):
        return self.__current_if_type

    def get_size(self):
        return len(self.__op_code) + 1

    def get_jump_value(self):
        return self.__jump_value

    def set_color(self, color):
        self.__color_param = color
        #self.__analyse_op_data()

    def set_op_id(self, op_id):
        self.reset_data()
        self.__op_id = op_id
        op_info = self.__get_op_code_line_info()
        self.__op_code = [0] * op_info["size"]

        self.id_possible_list = [{'id': x['op_code'], 'data': x['short_text']} for x in self.game_data.ai_data_json['op_code_info']]
        self.__analyse_op_data()

    def set_op_code(self, op_code):
        self.__op_code = op_code
        self.__analyse_op_data()

    def get_id(self):
        return self.__op_id

    def get_op_code(self):
        return self.__op_code

    def get_text_param(self):
        return self.__raw_parameters

    def _normalize_string(self, text):
        """Normalize string for case-insensitive lookup"""
        return text.upper().replace(' ', '_').replace('-', '_')

    def get_param_text(self):
        print("get_param_text")
        text = "("
        for i,param in enumerate(self.param_typed):
            text += self._normalize_string(param)
            if i  < len(self.param_typed) - 1:
                text+=","
        text += ")"
        if self.__op_id != 0x02:
            text += ";"
        print(text)
        return text

    def get_text(self, with_size=True, raw=False, for_code=False, html=False, comment=True, for_decompiled=False):
        text = self.__raw_text
        parameters = self.__raw_parameters.copy()

        if for_decompiled:
            print("for_decompiled")
            if self.__op_id == 2:
                print(parameters)
                del parameters[-1]
            text = "("
            for i, param in enumerate(parameters):
                if i < len(parameters)-1:
                    text += f"{self._normalize_string(param)}, "
                else:
                    text += f"{self._normalize_string(param)}"
            text+=")"
            if self.__op_id != 2:
                text += ";"
            list_comparator_destination = self.game_data.ai_data_json['list_comparator_ifritAI_html']
            for i in range(len(list_comparator_destination)):
                text = text.replace(self.game_data.ai_data_json['list_comparator'][i], list_comparator_destination[i])
            if not self.__comment:
                text += " // " + self.get_text(for_code=True, html=True)
            return text

        if for_code:
            parameters = []
            for parameter in self.__raw_parameters:
                parameters.append(self.PARAM_CHAR_LEFT + str(parameter) + self.PARAM_CHAR_RIGHT)

        if html:
            if for_code:
                list_comparator_destination = self.game_data.ai_data_json['list_comparator_ifritAI_html']
            else:
                list_comparator_destination = self.game_data.ai_data_json['list_comparator_html']
            for i in range(len(list_comparator_destination)):
                text = text.replace(self.game_data.ai_data_json['list_comparator'][i], list_comparator_destination[i])
                for j in range(len(parameters)):
                    parameters[j] = str(parameters[j]).replace(self.game_data.ai_data_json['list_comparator'][i],
                                                               list_comparator_destination[i])
            for i in range(len(parameters)):
                parameters[i] = '<span style="color:' + self.__color_param + ';">' + parameters[i] + '</span>'

        for i in range(len(parameters)):  # Adding special text computation
            for text_added in self.__raw_text_added:
                if text_added['id'] == i:
                    if html:
                        parameters[i] = str(parameters[i]) + text_added['text_html']
                    else:
                        parameters[i] = str(parameters[i]) + text_added['text']
        if not raw:
            text = text.format(*parameters)
        if with_size:
            text += " (size:{}bytes)".format(self.__size)
        if comment and self.__comment:
            text += "//" + self.__comment
        # Removing return line as we compute line by line
        if for_code:
            text = text.replace('<br/>', '')
            text = text.replace('<br>', '')

        return text

    def set_if_index(self, if_index):
        self.__if_index = if_index

    def __get_op_code_line_info(self):
        all_op_code_info = self.game_data.ai_data_json["op_code_info"]
        op_research = [x for x in all_op_code_info if x["op_code"] == self.__op_id]
        if op_research:
            op_research = op_research[0]
        else:
            print("No op_code defined for op_id: {}".format(self.__op_id))
            op_research = [x for x in all_op_code_info if x["op_code"] == 255][0]
        return op_research

    def __analyse_op_data_with_text_param(self):
        op_code_list = self.get_op_code()
        op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x["op_code"] == self.get_id()]
        if op_info:
            op_info = op_info[0]
        else:
            print(f"Didn't find op id: {self.get_id()}, assuming stop")
            op_info = self.game_data.ai_data_json['op_code_info'][0]
        # Analysing simple cases by transforming the text into an integer
        if op_info['complexity'] == "simple":
            # Putting the parameters type in the correct order
            param_type_sorted = op_info['param_type'].copy()
            for i, param_index in enumerate(op_info['param_index']):
                param_type_sorted[param_index] = op_info['param_type'][i]
            for i, param_type in enumerate(param_type_sorted):
                if param_type == "int":
                    op_code_list[i] = int(op_code_list[i])
                elif param_type == "int_shift":
                    shift = op_info['param_list'][0]
                    op_code_list[i] = int(op_code_list[i]) - shift
                elif param_type == "percent":
                    op_code_list[i] = int(int(op_code_list[i]) / 10)
                elif param_type == "bool":
                    bool_text_up = op_code_list[i].upper()
                    if bool_text_up == "TRUE":
                        op_code_list[i] = 1
                    elif bool_text_up == "FALSE":
                        op_code_list[i] = 0
                    else:
                        print(f"Unexpected bool value: {bool_text_up}, should be True or False. Considering True")
                        op_code_list[i] = 1
                elif param_type in ("battle_var", "global_var", "local_var"):
                    op_code_list[i] = [x['op_code'] for x in self.game_data.ai_data_json['list_var'] if x['var_name'] == op_code_list[i]][0]
                elif param_type == "activate":
                    op_code_list[i] = [x['id'] for x in self.game_data.ai_data_json['activate_type'] if x['name'] == op_code_list[i]][0]
                elif param_type == "special_action":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.special_action_data_json['special_action'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.special_action_data_json["special_action"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamSpecialActionError(op_code_list[i])
                elif param_type == "local_var_param":
                    # Managing special case for 203 instead of last attacker
                    try:
                        op_code_list[i] = [x['id'] for x in self.__get_possible_local_var_param() if x['data'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["param_id"] for val_dict in self.game_data.ai_data_json["local_var_param"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamLocalVarParamError(op_code_list[i])
                elif param_type == "monster_line_ability":
                    op_code_list[i] = int(op_code_list[i])
                elif param_type == "card":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.card_data_json['card_info'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.card_data_json["card_info"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamCardError(op_code_list[i])
                elif param_type == "scene_out_slot_id":
                    try:
                        op_code_list[i] = [x['param_id'] for x in self.game_data.ai_data_json['scene_out_slot_id'] if x['text'] == op_code_list[i]][0]
                    except IndexError:
                        raise ParamSceneOutSlotIdError(op_code_list[i])
                elif param_type == "monster":
                    op_code_list[i] = [x['id'] for x in self.game_data.monster_data_json['monster'] if x['name'] == op_code_list[i]][0]
                elif param_type == "slot_id_enable":
                    # Managing special case for 209
                    try:
                        op_code_list[i] = [x['param_id'] for x in self.game_data.ai_data_json['slot_id_enable'] if x['text'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["param_id"] for val_dict in self.game_data.ai_data_json["slot_id_enable"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamSlotIdEnableError(op_code_list[i])
                elif param_type == "assign_slot_id":
                    try:
                        op_code_list[i] = [x['param_id'] for x in self.game_data.ai_data_json['assign_slot_id'] if x['text'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["param_id"] for val_dict in self.game_data.ai_data_json["assign_slot_id"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamAssignSlotIdError(op_code_list[i])
                elif param_type == "item":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.item_data_json['items'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.item_data_json["items"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamItemError(op_code_list[i])
                elif param_type == "gforce":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.gforce_data_json['gforce'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.gforce_data_json["gforce"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamGfError(op_code_list[i])
                elif param_type == "target_slot":
                    try:
                        op_code_list[i] = [x['id'] for x in self.__get_target_list(advanced=True, specific=True, slot=True) if x['data'] == op_code_list[i]][0]
                    except IndexError:
                        target_basic_id = [val_dict["id"] for val_dict in self.__get_target_list(advanced=True, specific=True, slot=True)]
                        if int(op_code_list[i]) in target_basic_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamTargetSlotError(op_code_list[i])
                elif param_type == "target_advanced_specific":
                    try:
                        op_code_list[i] = [x['id'] for x in self.__get_target_list(advanced=True, specific=True) if x['data'] == op_code_list[i]][0]
                    except IndexError:
                        target_basic_id = [val_dict["id"] for val_dict in self.__get_target_list(advanced=True, specific=True)]
                        if int(op_code_list[i]) in target_basic_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamTargetSpecificError(op_code_list[i])
                elif param_type == "target_advanced_generic":
                    try:
                        op_code_list[i] = [x['id'] for x in self.__get_target_list(advanced=True, specific=False) if x['data'] == op_code_list[i]][0]
                    except IndexError:
                        target_basic_id = [val_dict["id"] for val_dict in self.__get_target_list(advanced=True, specific=False)]
                        if int(op_code_list[i]) in target_basic_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamTargetGenericError(op_code_list[i])
                elif param_type == "target_basic":
                    try:
                        op_code_list[i] = [x['id'] for x in self.__get_target_list(advanced=False, specific=False) if x['data'] == op_code_list[i]][0]
                    except IndexError:
                        target_basic_id = [val_dict["id"] for val_dict in self.__get_target_list(advanced=False, specific=False)]
                        if int(op_code_list[i]) in target_basic_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamTargetBasicError(op_code_list[i])

                elif param_type == "comparator":
                    try:
                        op_code_list[i] = self.game_data.ai_data_json['list_comparator_ifritAI'].index(op_code_list[i])
                    except IndexError:
                        raise ComparatorError(op_code_list[i])
                elif param_type == "status_ai":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.status_data_json['status_ai'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.status_data_json["status_ai"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamStatusAIError(op_code_list[i])
                elif param_type == "magic_type":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.magic_data_json['magic_type'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.magic_data_json["magic_type"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamMagicTypeError(op_code_list[i])
                elif param_type == "magic":
                    try:
                        op_code_list[i] = [x['id'] for x in self.game_data.magic_data_json['magic'] if x['name'] == op_code_list[i]][0]
                    except IndexError:
                        special_param_id = [val_dict["id"] for val_dict in self.game_data.magic_data_json["magic"]]
                        if int(op_code_list[i]) in special_param_id:
                            op_code_list[i] = int(op_code_list[i])
                        else:
                            raise ParamMagicIdError(op_code_list[i])
                elif param_type == "monster_ability":
                    op_code_list[i] = [x['id'] for x in self.game_data.enemy_abilities_data_json['abilities'] if x['name'] == op_code_list[i]][0]
                elif param_type == "aptitude":
                    op_code_list[i] = [x['aptitude_id'] for x in self.game_data.ai_data_json['aptitude_list'] if x['text'] == op_code_list[i]][0]
                elif param_type == "battle_text":
                    if int(op_code_list[i]) < len(self.__battle_text):
                        op_code_list[i] = int(op_code_list[i])
                    else:
                        print(f"Battle text index {op_code_list[i]} not found in list : {self.__battle_text}")
                else:
                    print(f"Text data analysis - Unknown type {param_type}, considering a int")
                    op_code_list[i] = int(op_code_list[i])
        elif op_info['op_code'] == 2:  # IF
            # Subject ID (0)
            # Change the subject ID with the name of var
            var_data = [x for x in self.game_data.ai_data_json['list_var'] if x['var_name'] == op_code_list[0]]
            if var_data:  # Local var is str of var name instead of an ID
                subject_id = var_data[0]['op_code']
            else:
                subject_id = int(op_code_list[0])
            # subject_id = int(op_code_list[0])
            op_code_list[0] = int(op_code_list[0])
            # Left condition (1)
            if_subject_dict = [x for x in self.game_data.ai_data_json['if_subject'] if x['subject_id'] == subject_id]
            if if_subject_dict:
                if_subject_dict = if_subject_dict[0]
            else:
                print(f"Unexpected subject ID: {subject_id}")
            ## Now we want to have only the parameter of the subject, for this we remove data around
            split_text = if_subject_dict['left_text'].split('{}')
            if_subject_left_parameter_text = op_code_list[1].replace(split_text[0], '')
            temp_int_right = 0  # To handle special cases of subj ID 15 where text and int are inversed
            if len(split_text) > 1:
                if_subject_left_parameter_text = if_subject_left_parameter_text.replace(split_text[1], '')
            if if_subject_dict['param_left_type'] == "int":
                op_code_list[1] = int(if_subject_left_parameter_text)
            elif if_subject_dict['param_left_type'] == "int_shift":
                shift = if_subject_dict['param_list'][0]
                op_code_list[1] = int(if_subject_left_parameter_text) - shift
            elif if_subject_dict['param_left_type'] == "int_right":
                temp_int_right = if_subject_left_parameter_text
                op_code_list[1] = 200  # Always ALIVE
            elif if_subject_dict['param_left_type'] in ("battle_var", "global_var"):
                op_code_list[1] = 200
            elif if_subject_dict['param_left_type'] == "local_var":
                local_var_found = [x['id'] for x in self.__get_possible_target_advanced_specific() if x['data'] == if_subject_left_parameter_text]
                if local_var_found:
                    op_code_list[1] = local_var_found[0]
                else:
                    print(f"Local var option {if_subject_left_parameter_text} not found in possible value list")
                    op_code_list[1] = 200
            elif if_subject_dict['param_left_type'] == "subject10":  # We don't use if_subject_left_parameter_text
                subject10_list = [x['param_id'] for x in self.game_data.ai_data_json['subject_left_10'] if op_code_list[1] in x['text']]
                if not subject10_list:
                    print(f"Unexpected subject10: {op_code_list[1]}")
                    op_code_list[1] = 0
                else:
                    op_code_list[1] = subject10_list[0]
            elif if_subject_dict['param_left_type'] == "int_shift":
                if if_subject_dict['subject_id'] == 2:
                    shift = 1
                else:
                    print("unexpected int_shift for subject id: {}")
                op_code_list[1] = int(if_subject_left_parameter_text) + shift
            elif if_subject_dict['param_left_type'] in ("target_advanced_specific", "target_advanced_generic"):
                if if_subject_dict['param_left_type'] == "target_advanced_specific":
                    target_list = self.__get_target_list(advanced=True, specific=True)
                if if_subject_dict['param_left_type'] == "target_advanced_generic":
                    target_list = self.__get_target_list(advanced=True, specific=False)
                try:
                    op_code_list[1] = [x['id'] for x in target_list if x['data'] == op_code_list[1]][0]
                except IndexError:
                    target_id = [val_dict["id"] for val_dict in target_list]
                    if int(op_code_list[1]) in target_id:
                        op_code_list[1] = int(op_code_list[1])
                    else:
                        raise ParamTargetSpecificError(op_code_list[1])
            elif if_subject_dict['param_left_type'] == "const":
                op_code_list[1] = if_subject_dict['param_list'][0]  # Unused
            elif if_subject_dict['param_left_type'] == "":
                op_code_list[1] = 0  # Unused
            else:
                print(f"Unexpected if_subject_dict['param_left_type']: {if_subject_dict['param_left_type']}")
                op_code_list[1] = 0
            if op_code_list[1] > 255 or op_code_list[1] < 0:
                print(f"Left param value {op_code_list[1]} is >255 or <0")
            # Comparison (2)
            op_code_list[2] = self.game_data.ai_data_json['list_comparator_ifritAI'].index(op_code_list[2])
            # Right condition (3)
            r_cond = op_code_list[3]
            if if_subject_dict['param_right_type'] == "int":
                r_cond_result = int(r_cond)
            elif if_subject_dict['param_right_type'] == "alive":
                r_cond_result = int(r_cond) + 3
            elif if_subject_dict['param_right_type'] == "gender":
                r_cond_result = [x['id'] for x in self.game_data.ai_data_json['gender_type'] if x['type'] == r_cond][0]
            elif if_subject_dict['param_right_type'] == "percent":
                r_cond_result = int(int(r_cond) / 10)
            elif if_subject_dict['param_right_type'] == "status_ai":
                r_cond_result = [x['id'] for x in self.game_data.status_data_json['status_ai'] if x['name'] == r_cond][0]
            elif if_subject_dict['param_right_type'] == "special_byte_check":
                r_cond_result = [x['id'] for x in self.game_data.ai_data_json['special_byte_check'] if x['data'] == r_cond][0]
            elif if_subject_dict['param_right_type'] == "target_advanced_specific":
                target_list = self.__get_target_list(advanced=True, specific=True)
                r_cond_result = [x['id'] for x in target_list if x['data'] == r_cond][0]
            elif if_subject_dict['param_right_type'] == "target_advanced_generic":
                target_list = self.__get_target_list(advanced=True, specific=False)
                r_cond_result = [x['id'] for x in target_list if x['data'] == r_cond][0]
            elif if_subject_dict['param_right_type'] == "const":
                r_cond_result = if_subject_dict['param_list'][1]  # Unused
            elif if_subject_dict['param_right_type'] == "complex":
                if subject_id == 10:
                    if op_code_list[1] == 0:  # Attack type
                        search_value = [x['id'] for x in self.game_data.ai_data_json['attack_type'] if x['type'] == r_cond]
                        if search_value:
                            r_cond_result = search_value[0]
                        else:
                            print(f"Unexpected attack type: {r_cond}")
                            r_cond_result = 0
                    elif op_code_list[1] == 1:  # Target advanced specific
                        search_value = [x['id'] for x in self.__get_target_list(advanced=True, specific=True) if x['data'] == r_cond]
                        if search_value:
                            r_cond_result = search_value[0]
                        else:
                            print(f"Unexpected target advanced specific: {r_cond}")
                            op_code_list[3] = 0
                    elif op_code_list[1] == 2:  # TURN COUNTER INT
                        r_cond_result = int(r_cond)
                    elif op_code_list[1] == 3:  # Command type
                        search_value = [x['id'] for x in self.game_data.ai_data_json['command_type'] if x['data'] == op_code_list[3]]
                        if search_value:
                            r_cond_result = search_value[0]
                        else:
                            print(f"Unexpected target advanced specific: {r_cond}")
                            r_cond_result = 0
                    elif op_code_list[1] == 4:  # Last Command type or gforce
                        # First Gforce
                        search_gf = [x['id'] for x in self.game_data.gforce_data_json['gforce'] if x['name'] == op_code_list[3]]
                        if search_gf:
                            r_cond_result = search_gf[0] + 64
                        else:
                            search_magic = [x['id'] for x in self.game_data.magic_data_json['magic'] if x['name'] == r_cond]
                            if search_magic:
                                r_cond_result = search_magic[0]
                            else:
                                search_item = [x['id'] for x in self.game_data.item_data_json['items'] if x['name'] == r_cond]
                                if search_item:
                                    r_cond_result = search_item[0]
                                else:
                                    search_special_action = [x['id'] for x in self.game_data.special_action_data_json['special_action'] if
                                                             x['name'] == r_cond]
                                    if search_special_action:
                                        r_cond_result = search_special_action[0]
                                    else:
                                        print(f"Unexpected param {r_cond} when searching for subject 10.4")
                                        r_cond_result = int(r_cond)
                    elif op_code_list[1] == 5:  # Magic type
                        search_value = [x['id'] for x in self.game_data.magic_data_json['magic_type'] if x['name'] == r_cond]
                        if search_value:
                            r_cond_result = search_value[0]
                        else:
                            print(f"Unexpected magic type: {r_cond}")
                            r_cond_result = 0
                    elif op_code_list[1] == 203:  # comID type
                        if r_cond == "SELF":
                            r_cond_result = 200
                        else:
                            r_cond_result = int(r_cond) + 0x10
                    else:
                        print(f"Unexpected param right for subject id 10: {r_cond}")
                        r_cond_result = 0
                else:
                    print(f"Unexpected if subject param right type: {if_subject_dict['param_right_type']}")
            # Unused value (called debug)
            op_code_list[3] = int.to_bytes(r_cond_result, byteorder="little", length=2)[0]
            op_code_list[4] = int.to_bytes(r_cond_result, byteorder="little", length=2)[1]
            # op_code_list[4] = int(op_code_list[4])
            # Expanding jump
            op_code_list[5] = int(op_code_list[5])
            op_code_list[6] = int(op_code_list[6])
        elif op_info['op_code'] == 45:
            op_code_list[0] = [x['id'] for x in self.game_data.magic_data_json['magic_type'] if x['name'] == op_code_list[0]]
            if op_code_list[0]:
                op_code_list[0] = op_code_list[0][0]
            else:
                print("Unexpected magic type for elem id 45")
            op_code_list[1] = int(op_code_list[1])
            op_code_list[2] = int(op_code_list[2])
        elif op_info['op_code'] == 35:
            pass

        self.reset_data()
        self.__op_code = op_code_list
        self.__size = op_info['size'] + 1

    def compute_op_data(self, current_if_type: CurrentIfType):
        self.__current_if_type = current_if_type
        self.set_op_code(self.__op_code)
        return self.__current_if_type

    def __analyse_op_data(self):
        self.reset_data()
        op_info = self.__get_op_code_line_info()
        # Searching for errors in json file
        if len(op_info["param_type"]) != op_info["size"] and op_info['complexity'] == 'simple':
            print(f"Error on JSON for op_code_id: {self.__op_id}")
        if op_info["complexity"] == "simple":
            param_value = []
            for index, type in enumerate(op_info["param_type"]):
                op_index = op_info["param_index"][index]
                self.type_data.append(type)
                if type == "int":
                    param_value.append(str(self.__op_code[op_index]))
                    self.param_possible_list.append([])
                elif type == "int_shift":
                    shift = op_info['param_list'][0]
                    param_value.append(str(self.__op_code[op_index] + shift))
                    self.param_possible_list.append([])
                elif type == "percent":
                    param_value.append(str(self.__op_code[op_index] * 10))
                    self.param_possible_list.append([])
                elif type == "magic_type":
                    try:
                        param_value.append(str([x['name'] for x in self.game_data.magic_data_json['magic_type'] if x['id'] == self.__op_code[op_index]][0]))
                    except IndexError:
                        # param_value.append(self.game_data.magic_data_json['magic_type'][0]['name'])
                        param_value.append("UNKNOWN MAGIC TYPE")
                    self.param_possible_list.append(self.__get_possible_magic_type())
                elif type == "slot_id_enable":
                    self.param_possible_list.append(self.__get_possible_slot_id_enable())
                    try:
                        param_value.append(
                            str([x['text'] for x in self.game_data.ai_data_json['slot_id_enable'] if x['param_id'] == self.__op_code[op_index]][0]))
                    except IndexError:
                        # param_value.append(self.game_data.ai_data_json['slot_id_enable'][0]['text'])
                        param_value.append("UNKNOWN SLOT ID ENABLE")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN SLOT ID ENABLE"})
                elif type == "assign_slot_id":
                    self.param_possible_list.append(self.__get_possible_assign_slot_id())
                    try:
                        param_value.append(
                            str([x['text'] for x in self.game_data.ai_data_json['assign_slot_id'] if x['param_id'] == self.__op_code[op_index]][0]))
                    except IndexError:
                        # param_value.append(self.game_data.ai_data_json['slot_id_enable'][0]['text'])
                        param_value.append("UNKNOWN ASSIGN SLOT ID")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN ASSIGN SLOT ID"})
                elif type == "magic":
                    self.param_possible_list.append(self.__get_possible_magic())
                    try:
                        param_value.append(str([x['name'] for x in self.game_data.magic_data_json['magic'] if x['id'] == self.__op_code[op_index]][0]))
                    except IndexError:
                        # param_value.append(self.game_data.magic_data_json['magic'][0]['name'])
                        param_value.append("UNKNOWN MAGIC")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN MAGIC"})
                elif type == "monster_ability":
                    self.param_possible_list.append(self.__get_possible_monster_abilities())
                    try:
                        param_value.append(
                            str([x['name'] for x in self.game_data.enemy_abilities_data_json['abilities'] if x['id'] == self.__op_code[op_index]][0]))
                    except IndexError:
                        # param_value.append(self.game_data.enemy_abilities_data_json['abilities'][0]['name'])
                        param_value.append("UNKNOWN ABILITIES")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN ABILITIES"})

                elif type == "bool":
                    param_value.append(str(bool(self.__op_code[op_index])))
                    self.param_possible_list.append([{"id": 0, "data": "False"}, {"id": 1, "data": "True"}])
                elif type == "activate":
                    self.param_possible_list.append(self.__get_possible_activate())
                    try:
                        param_value.append([x['name'] for x in self.game_data.ai_data_json['activate_type'] if x['id'] == self.__op_code[op_index]][0])
                    except IndexError:
                        # param_value.append(self.game_data.ai_data_json['activate_type'][0]['name'])
                        param_value.append("UNKNOWN ACTIVATE TYPE")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN ACTIVATE TYPE"})
                elif type == "scene_out_slot_id":
                    self.param_possible_list.append(self.__get_possible_scene_out_slot_id())
                    try:
                        param_value.append(
                            [x['text'] for x in self.game_data.ai_data_json['scene_out_slot_id'] if x['param_id'] == self.__op_code[op_index]][0])
                    except IndexError:
                        # param_value.append(self.game_data.ai_data_json['activate_type'][0]['name'])
                        param_value.append("UNKNOWN SCENE OUT SLOT ID")
                        self.param_possible_list[-1].append({'id': self.__op_code[op_index], 'data': "UNKNOWN SCENE OUT SLOT ID"})
                elif type == "local_var":
                    param_value.append(self.__get_var_name(self.__op_code[op_index]))
                    self.param_possible_list.append(self.__get_possible_local_var())
                elif type == "local_var_param":
                    self.param_possible_list.append(self.__get_possible_local_var_param())
                    param_value.append([x['data'] for x in self.__get_possible_local_var_param() if x['id'] == self.__op_code[op_index]][0])
                elif type == "local_var":
                    param_value.append(self.__get_var_name(self.__op_code[op_index]))
                    self.param_possible_list.append(self.__get_possible_local_var())
                elif type == "battle_var":
                    param_value.append(self.__get_var_name(self.__op_code[op_index]))
                    self.param_possible_list.append(self.__get_possible_battle_var())
                elif type == "global_var":
                    param_value.append(self.__get_var_name(self.__op_code[op_index]))
                    self.param_possible_list.append(self.__get_possible_global_var())
                elif type == "special_action":
                    if self.__op_code[op_index] < len(self.game_data.special_action_data_json["special_action"]):
                        param_value.append(self.game_data.special_action_data_json["special_action"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_special_action())
                    else:
                        param_value.append("UNKNOWN SPECIAL_ACTION")
                elif type == "monster_line_ability":
                    possible_ability_values = []
                    nb_ability_high = len([x for x in self.info_stat_data['abilities_high'] if x['id'] != 0])
                    last_line_ability_high = [i for i, x in enumerate(self.info_stat_data['abilities_high']) if x['id'] != 0]
                    if last_line_ability_high:
                        last_line_ability_high = last_line_ability_high[-1]
                    else:
                        print("No ability high found")
                        last_line_ability_high = 0
                    nb_ability_med = len([x for x in self.info_stat_data['abilities_med'] if x['id'] != 0])
                    last_line_ability_med = [i for i, x in enumerate(self.info_stat_data['abilities_med']) if x['id'] != 0]
                    if last_line_ability_med:
                        last_line_ability_med = last_line_ability_med[-1]
                    else:
                        print("No ability med found")
                        last_line_ability_med = 0
                    nb_ability_low = len([x for x in self.info_stat_data['abilities_low'] if x['id'] != 0])
                    last_line_ability_low = [i for i, x in enumerate(self.info_stat_data['abilities_low']) if x['id'] != 0]
                    if last_line_ability_low:
                        last_line_ability_low = last_line_ability_low[-1]
                    else:
                        print("No ability low found")
                        last_line_ability_low = 0
                    nb_abilities = max(nb_ability_high, nb_ability_med, nb_ability_low)
                    last_line_ability_index = max(last_line_ability_high, last_line_ability_med, last_line_ability_low)
                    for i in range(last_line_ability_index + 1):
                        if self.info_stat_data['abilities_high'][i] != 0:
                            if self.info_stat_data['abilities_high'][i]['type'] == 2:  # Magic
                                high_text = self.game_data.magic_data_json["magic"][self.info_stat_data['abilities_high'][i]['id']]['name']
                            elif self.info_stat_data['abilities_high'][i]['type'] == 4:  # Item
                                high_text = self.game_data.item_data_json["items"][self.info_stat_data['abilities_high'][i]['id']]['name']
                            elif self.info_stat_data['abilities_high'][i]['type'] in (8, 236):  # Ability
                                high_text = self.game_data.enemy_abilities_data_json["abilities"][self.info_stat_data['abilities_high'][i]['id']]['name']
                            elif self.info_stat_data['abilities_high'][i]['type'] == 0:  # Emptyness
                                high_text = "None"
                            else:
                                high_text = "Unexpected type ability"
                        else:
                            high_text = "None"
                        if self.info_stat_data['abilities_med'][i] != 0:
                            if self.info_stat_data['abilities_med'][i]['type'] == 2:  # Magic
                                med_text = self.game_data.magic_data_json["magic"][self.info_stat_data['abilities_med'][i]['id']]['name']
                            elif self.info_stat_data['abilities_med'][i]['type'] == 4:  # Item
                                med_text = self.game_data.item_data_json["items"][self.info_stat_data['abilities_med'][i]['id']]['name']
                            elif self.info_stat_data['abilities_med'][i]['type'] in (8, 236):  # Ability
                                med_text = self.game_data.enemy_abilities_data_json["abilities"][self.info_stat_data['abilities_med'][i]['id']]['name']
                            elif self.info_stat_data['abilities_med'][i]['type'] == 0:  # Emptyness
                                med_text = "None"
                            else:
                                med_text = "Unexpected type ability"
                        else:
                            med_text = "None"
                        if self.info_stat_data['abilities_low'][i] != 0:
                            if self.info_stat_data['abilities_low'][i]['type'] == 2:  # Magic
                                low_text = self.game_data.magic_data_json["magic"][self.info_stat_data['abilities_low'][i]['id']]['name']
                            elif self.info_stat_data['abilities_low'][i]['type'] == 4:  # Item
                                low_text = self.game_data.item_data_json["items"][self.info_stat_data['abilities_low'][i]['id']]['name']
                            elif self.info_stat_data['abilities_low'][i]['type'] in (8, 236):  # Ability
                                low_text = self.game_data.enemy_abilities_data_json["abilities"][self.info_stat_data['abilities_low'][i]['id']]['name']
                            elif self.info_stat_data['abilities_low'][i]['type'] == 0:  # Emptyness
                                low_text = "None"
                            else:
                                low_text = "Unexpected type ability"
                        else:
                            low_text = "None"
                        text = f"Low - {low_text} | Med - {med_text} | High - {high_text}"
                        possible_ability_values.append({'id': i, 'data': text})
                        if self.__op_code[op_index] == i:
                            param_value.append(f"{i}")
                            self.__raw_text_added.append({"id": len(param_value) - 1, "text": " (" + text + " )", "text_html": " (" + text + " )<br/>"})
                    if self.__op_code[op_index] == 253:
                        param_value.append(f"{253}")
                        self.__raw_text_added.append({"id": len(param_value) - 1, "text": " (None) ", "text_html": " (None) "})
                    elif self.__op_code[op_index] > last_line_ability_index:
                        print(f"Unexpected line ability {self.__op_code[op_index]}, last one should be {last_line_ability_index}")
                        param_value.append(f"{self.__op_code[op_index]}")
                        self.__raw_text_added.append({"id": len(param_value) - 1, "text": " (None) ", "text_html": " (None) "})
                    possible_ability_values.append({'id': 253, 'data': "None"})  # 253 is literally the case of None in the code
                    self.param_possible_list.append(possible_ability_values)
                elif type == "battle_text":
                    if self.__op_code[op_index] < len(self.__battle_text):
                        battle_text_str = self.__battle_text[self.__op_code[op_index]].get_str()
                        param_value.append(self.__op_code[op_index])
                        self.param_possible_list.append(self.__get_possible_battle_text())
                        self.__raw_text_added.append(
                            {"id": len(param_value) - 1, "text": " (" + battle_text_str + " )", "text_html": " (" + battle_text_str + " )"})
                    else:
                        param_value.append("UNKNOWN BATTLE TEXT")
                elif type == "ability":
                    if self.__op_code[op_index] < len(self.game_data.enemy_abilities_data_json["abilities"]):
                        param_value.append(self.game_data.enemy_abilities_data_json["abilities"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_ability())
                    else:
                        param_value.append("UNKNOWN CARD")
                elif type == "card":
                    if self.__op_code[op_index] < len(self.game_data.card_data_json["card_info"]):
                        param_value.append(self.game_data.card_data_json["card_info"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_card())
                    else:
                        param_value.append("UNKNOWN CARD")
                elif type == "monster":
                    if self.__op_code[op_index] < len(self.game_data.monster_data_json["monster"]):
                        param_value.append(self.game_data.monster_data_json["monster"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_monster())
                    else:
                        param_value.append("UNKNOWN MONSTER")
                elif type == "item":
                    if self.__op_code[op_index] < len(self.game_data.item_data_json["items"]):
                        param_value.append(self.game_data.item_data_json["items"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_item())
                    else:
                        param_value.append("UNKNOWN ITEM")
                elif type == "status_ai":
                    if self.__op_code[op_index] <= self.game_data.status_data_json["status_ai"][-1]['id']:
                        param_value_temp = [x['name'] for x in self.game_data.status_data_json["status_ai"] if x['id'] == self.__op_code[op_index]]
                        if param_value_temp:
                            param_value.append(param_value_temp[0])
                        else:
                            print(f"Unknown status for id: {self.__op_code[op_index]}")
                            param_value.append(self.__op_code[op_index])
                        self.param_possible_list.append(self.__get_possible_status_ai())
                    else:
                        param_value.append("UNKNOWN STATUS AI")
                elif type == "gforce":
                    if self.__op_code[op_index] < len(self.game_data.gforce_data_json["gforce"]):
                        param_value.append(self.game_data.gforce_data_json["gforce"][self.__op_code[op_index]]['name'])
                        self.param_possible_list.append(self.__get_possible_gforce())
                    else:
                        param_value.append("UNKNOWN GFORCE")
                elif type == "target_advanced_specific":
                    param_value.append(self.__get_target(self.__op_code[op_index], advanced=True, specific=True))
                    self.param_possible_list.append([x for x in self.__get_target_list(advanced=True, specific=True)])
                elif type == "target_advanced_generic":
                    param_value.append(self.__get_target(self.__op_code[op_index], advanced=True, specific=False))
                    self.param_possible_list.append([x for x in self.__get_target_list(advanced=True, specific=False)])
                elif type == "target_basic":
                    param_value.append(self.__get_target(self.__op_code[op_index], advanced=False))
                    self.param_possible_list.append([x for x in self.__get_target_list(advanced=False)])
                elif type == "target_slot":
                    param_value.append(self.__get_target(self.__op_code[op_index], advanced=False, slot=True))
                    self.param_possible_list.append([x for x in self.__get_target_list(advanced=False, slot=True)])
                elif type == "comparator":
                    param_value.append(self.game_data.ai_data_json['list_comparator'][self.__op_code[op_index]])
                    self.param_possible_list.append([{"id": i, "data": x} for i, x in enumerate(self.game_data.ai_data_json['list_comparator'])])
                elif type == "aptitude":
                    try:
                        param_value_append = [x['text'] for x in self.game_data.ai_data_json['aptitude_list'] if x['aptitude_id'] == self.__op_code[op_index]][0]
                    except IndexError:
                        aptitude_id = [val_dict["aptitude_id"] for val_dict in self.game_data.ai_data_json["aptitude_list"]]
                        if int(self.__op_code[op_index]) in aptitude_id:
                            param_value_append = int(self.__op_code[op_index])
                        else:
                            raise ParamAptitudeError(self.__op_code[op_index])

                    param_value.append(param_value_append)
                    self.param_possible_list.append([{"id": x["aptitude_id"], "data": x['text']} for x in self.game_data.ai_data_json['aptitude_list']])
            # Now putting the op_list in the correct order for param value (data analysis already in correct order):
            original_param_possible = self.param_possible_list.copy()
            if len(original_param_possible) != len(op_info['param_index']):
                print(
                    f"Param possible list size: {len(original_param_possible)} different that op_info['param_index']: {len(op_info['param_index'])} for type {op_info["param_type"]}")
                print(f"Param possible list: {original_param_possible} different that op_info['param_index']: {op_info['param_index']}")

            else:
                for i, param_index in enumerate(op_info['param_index']):
                    self.param_possible_list[param_index] = original_param_possible[i]
            self.__raw_text = op_info['text']
            self.__raw_parameters = param_value
        elif op_info["complexity"] == "complex":
            call_function = getattr(self, "_CommandAnalyser__op_" + "{:02}".format(op_info["op_code"]) + "_analysis")
            call_result = call_function(self.__op_code)
            self.__raw_text = call_result[0]
            self.__raw_parameters = [str(x) for x in call_result[1]]
        self.__size = op_info['size'] + 1
        return self.__current_if_type

    def __get_possible_target_advanced_specific(self):
        return [x for x in self.__get_target_list(advanced=True, specific=True)]

    def __get_possible_target_advanced_generic(self):
        return [x for x in self.__get_target_list(advanced=True, specific=False)]

    def __get_possible_var(self):
        return [{"id": x['op_code'], "data": x['var_name']} for x in self.game_data.ai_data_json["list_var"]]

    def __get_possible_slot_id_enable(self):
        return [{"id": x['param_id'], "data": x['text']} for x in self.game_data.ai_data_json["slot_id_enable"]]

    def __get_possible_assign_slot_id(self):
        return [{"id": x['param_id'], "data": x['text']} for x in self.game_data.ai_data_json["assign_slot_id"]]

    def __get_possible_magic(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.magic_data_json["magic"])]

    def __get_possible_magic_type(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.magic_data_json["magic_type"])]

    def __get_possible_item(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.item_data_json["items"])]

    def __get_possible_status_ai(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.status_data_json["status_ai"])]

    def __get_possible_gforce(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.gforce_data_json["gforce"])]

    def __get_possible_gforce_shifted_64(self):
        return [{'id': val_dict['id'] + 64, 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.gforce_data_json["gforce"])]

    def __get_possible_monster(self):
        return [{'id': val_dict['entity_id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.monster_data_json["monster"])]

    def __get_possible_monster_abilities(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.enemy_abilities_data_json["abilities"])]

    def __get_possible_card(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.card_data_json["card_info"])]

    def __get_possible_status_ai(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.status_data_json["status_ai"])]

    def __get_possible_gender(self):
        return [{'id': val_dict['id'], 'data': val_dict['type']} for id, val_dict in enumerate(self.game_data.ai_data_json["gender_type"])]

    def __get_possible_special_action(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.special_action_data_json["special_action"])]

    def __get_possible_ability(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.enemy_abilities_data_json["abilities"])]

    def __get_possible_battle_text(self):
        return [{'id': i, 'data': data.get_str()} for i, data in enumerate(self.__battle_text)]

    def __get_possible_activate(self):
        return [{'id': val_dict['id'], 'data': val_dict['name']} for id, val_dict in enumerate(self.game_data.ai_data_json["activate_type"])]

    def __get_possible_scene_out_slot_id(self):
        return [{'id': val_dict['param_id'], 'data': val_dict['text']} for id, val_dict in enumerate(self.game_data.ai_data_json["scene_out_slot_id"])]

    def __get_possible_special_byte_check(self):
        return [{'id': val_dict['id'], 'data': val_dict['data']} for id, val_dict in enumerate(self.game_data.ai_data_json["special_byte_check"])]

    def __get_possible_battle_var(self):
        return [{'id': val_dict['op_code'], 'data': val_dict['var_name']} for id, val_dict in enumerate(self.game_data.ai_data_json["list_var"]) if
                val_dict['var_type'] == "battle"]

    def __get_possible_local_var(self):
        return [{'id': val_dict['op_code'], 'data': val_dict['var_name']} for id, val_dict in enumerate(self.game_data.ai_data_json["list_var"]) if
                val_dict['var_type'] == "local"]

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

    def __get_possible_global_var(self):
        return [{'id': val_dict['op_code'], 'data': val_dict['var_name']} for id, val_dict in enumerate(self.game_data.ai_data_json["list_var"]) if
                val_dict['var_type'] == "global"]

    def __get_possible_option_battle_var(self):
        return [{'id': val_dict['id'], 'data': val_dict['data']} for id, val_dict in enumerate(self.game_data.ai_data_json["battle_var_option"])]

    def __get_possible_option_global_var(self):
        return [{'id': val_dict['id'], 'data': val_dict['data']} for id, val_dict in enumerate(self.game_data.ai_data_json["global_var_option"])]

    def __get_possible_subject_10_203(self):
        possible_values = [{'id': i + 16, 'data': str(i)} for i in range(0, 143)]
        possible_values.append({'id': 200, 'data': str("SELF")})
        return possible_values

    def __op_35_analysis(self, op_code):
        op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x['op_code'] == 35][0]
        jump = int.from_bytes(bytearray([op_code[0], op_code[1]]), byteorder='little')
        self.param_possible_list.append([])
        self.param_possible_list.append([])

        # Jump backward
        if jump & 0x8000 != 0:
            jump = self.twos_complement(jump, 16)
        self.__jump_value = jump
        if jump == 0:
            return [op_info['text'][0], []]
        else:
            return [op_info['text'][1], [jump]]

    def __op_45_analysis(self, op_code):
        if op_code[0] < len(self.game_data.magic_data_json['magic_type']):
            element = self.game_data.magic_data_json['magic_type'][op_code[0]]['name']
        else:
            element = "UNKNOWN ELEMENT TYPE"
        target = op_code[1] + 256 * op_code[2]
        element_val = 900 - target
        self.param_possible_list.append(self.__get_possible_magic_type())
        self.param_possible_list.append([])
        op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x['op_code'] == 45][0]
        return [op_info['text'], [element, element_val]]

    def __op_02_analysis(self, op_code):
        # op_02 = ['subject_id', 'left condition (target)', 'comparator', 'right condition 1', 'right condition 2', 'jump1', 'jump2']
        op_info = [x for x in self.game_data.ai_data_json['op_code_info'] if x['op_code'] == 2][0]
        subject_id = op_code[0]
        subject_id_param = subject_id
        op_code_left_condition_param = op_code[1]
        op_code_comparator = op_code[2]
        jump_value_op_1 = op_code[5]
        jump_value_op_2 = op_code[6]
        jump_value = int.from_bytes(bytearray([op_code[5], op_code[6]]), byteorder='little')
        op_code_right_condition_param = int.from_bytes(bytearray([op_code[3], op_code[4]]), byteorder='little')
        self.__jump_value = jump_value
        if op_code_comparator < len(self.game_data.ai_data_json['list_comparator']):
            comparator = self.game_data.ai_data_json['list_comparator'][op_code_comparator]
        else:
            comparator = 'UNKNOWN OPERATOR'

        if_text = op_info["text"]
        if_current_subject = [x for x in self.game_data.ai_data_json["if_subject"] if x["subject_id"] == subject_id]
        list_param_possible_left = []
        list_param_possible_right = []

        if if_current_subject:
            if_current_subject = if_current_subject[0]
        else:
            left_subject = {'text': 'UNKNOWN SUBJECT', 'param': None}
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
            print(f"Unexpected subject id: {subject_id}")

        # Analysing left subject
        if if_current_subject:
            specific_left_text = ""
            if if_current_subject["complexity"] == "simple":
                if if_current_subject['param_left_type'] == "target_basic":
                    param_left = self.__get_target(op_code_left_condition_param, advanced=False)
                    list_param_possible_left.extend(self.__get_target_list(advanced=False))
                elif if_current_subject['param_left_type'] == "target_slot":
                    param_left = self.__get_target(op_code_left_condition_param, advanced=False, slot=True)
                    list_param_possible_left.extend(self.__get_target_list(advanced=False, slot=True))
                elif if_current_subject['param_left_type'] == "target_advanced_generic":
                    param_left = self.__get_target(op_code_left_condition_param, advanced=True, specific=False)
                    list_param_possible_left.extend(self.__get_target_list(advanced=True, specific=False))
                elif if_current_subject['param_left_type'] == "target_advanced_specific":
                    param_left = self.__get_target(op_code_left_condition_param, advanced=True, specific=True)
                    list_param_possible_left.extend(self.__get_target_list(advanced=True, specific=True))
                elif if_current_subject['param_left_type'] == "int":
                    param_left = int(op_code_left_condition_param)
                elif if_current_subject['param_left_type'] == "int_shift":
                    shift = if_current_subject['param_list'][0]
                    param_left = int(op_code_left_condition_param) + shift
                elif if_current_subject['param_left_type'] == "int_right":
                    shift = if_current_subject['param_list'][0]
                    param_left = int(op_code_right_condition_param) + shift
                elif if_current_subject['param_left_type'] == "const":
                    param_left = if_current_subject['left_text']
                    list_param_possible_left.extend([{"id": if_current_subject['param_list'][0], "data": if_current_subject['left_text']}])
                elif if_current_subject['param_left_type'] == "local_var":
                    specific_left_text = if_current_subject["left_text"]
                    subject_id_var = [x['var_name'] for x in self.game_data.ai_data_json['list_var'] if x['op_code'] == subject_id]
                    if subject_id_var:
                        subject_id_var = subject_id_var[0]
                        subject_id_param = subject_id_var  # For var, use a specific name
                        specific_left_text = specific_left_text.format(subject_id_var, "{}")
                        local_var_option = [x['text'] for x in self.game_data.ai_data_json['target_advanced_specific'] if
                                            x['param_id'] == op_code_left_condition_param]
                        if local_var_option:  # If it's a defined option
                            param_left = local_var_option[0]
                        else:
                            monster_id_option = [x['name'] for x in self.game_data.monster_data_json['monster'] if
                                                 x['entity_id'] == op_code_left_condition_param]
                            if monster_id_option:
                                param_left = monster_id_option[0]
                            else:
                                chara_id_option = [x for i, x in enumerate(self.game_data.ai_data_json['list_target_char']) if
                                                   i == op_code_left_condition_param]
                                if chara_id_option:
                                    param_left = chara_id_option[0]
                                else:
                                    param_left = "Unknown var"
                                    print(f"Unexpected local var option with code {op_code_left_condition_param}")
                    else:
                        param_left = "Unknown var"
                        print(f"Unexpected var with code {subject_id}")
                    list_param_possible_left.extend(self.__get_possible_target_advanced_specific())
                elif if_current_subject['param_left_type'] == "battle_var":
                    param_left = [x['var_name'] for x in self.game_data.ai_data_json['list_var'] if x['op_code'] == subject_id]
                    if param_left:
                        param_left = param_left[0]
                    else:
                        param_left = "Unknown var"
                        print(f"Unexpected battle var with code {subject_id}")
                    list_param_possible_left.extend(self.__get_possible_option_battle_var())
                elif if_current_subject['param_left_type'] == "global_var":
                    param_left = [x['var_name'] for x in self.game_data.ai_data_json['list_var'] if x['op_code'] == subject_id]
                    if param_left:
                        param_left = param_left[0]
                    else:
                        param_left = "Unknown var"
                        print(f"Unexpected global var with code {subject_id}")
                    list_param_possible_left.extend(self.__get_possible_option_global_var())
                elif if_current_subject['param_left_type'] == "subject10":
                    specific_left_text = "{}"
                    subject_left_data = [x['text'] for x in self.game_data.ai_data_json['subject_left_10'] if x['param_id'] == op_code_left_condition_param]
                    if not subject_left_data:
                        if_current_subject["left_text"] = "Unknown last attack {}".format(op_code_left_condition_param)
                    else:
                        if op_code_left_condition_param == 2:
                            param_left = subject_left_data[0][0]
                        elif op_code_left_condition_param == 4:
                            if op_code_right_condition_param < 64:
                                param_left = subject_left_data[0][1]
                            else:
                                param_left = subject_left_data[0][0]
                        elif op_code_left_condition_param == 203:
                            if op_code_right_condition_param == 200:
                                param_left = subject_left_data[0][1]
                            else:
                                param_left = subject_left_data[0][0]
                        else:
                            param_left = subject_left_data[0][0]
                    sum_text = ""
                    list_param_possible_left.extend(
                        [{'id': x['param_id'], 'data': [sum_text + y for y in x['text']][-1]} for x in self.game_data.ai_data_json['subject_left_10']])
                elif if_current_subject['param_left_type'] == "":
                    param_left = "UNKNOWN {}".format(op_code_left_condition_param)
                else:
                    print("Unexpected param_left_type: {}".format(if_current_subject['param_left_type']))
                    param_left = op_code_left_condition_param
                    list_param_possible_left.append({"id": op_code_left_condition_param, "data": "Unused"})
            elif if_current_subject["complexity"] == "complex":
                if if_current_subject["subject_id"] == 15:  # ALLY SLOT X IS ALIVE
                    param_left = op_code_right_condition_param - 3  # Special case where we take the right condition
                else:
                    print(f"Unexpected subject_id: {if_current_subject["subject_id"]}")
                    param_left = op_code_left_condition_param
            else:
                print(f"Unexpected complexity: {if_current_subject["complexity"]}")
                param_left = op_code_left_condition_param
            if not specific_left_text:
                specific_left_text = if_current_subject["left_text"]
            left_subject = {'text': specific_left_text, 'param': param_left}

        # Analysing right subject
        if if_current_subject:
            right_param_type = if_current_subject['param_right_type']
            if right_param_type:
                if right_param_type == 'hp_percent':
                    right_subject = {'text': '{}%', 'param': op_code_right_condition_param * 10}
                elif right_param_type == 'alive':
                    right_subject = {'text': 'ALIVE', 'param': ''}
                elif right_param_type == "const":
                    right_subject = {'text': if_current_subject['right_text'], 'param': ''}
                    list_param_possible_right = [{"id": if_current_subject['param_list'][1], "data": if_current_subject['right_text']}]
                elif right_param_type == 'gender':
                    param = [x['type'] for x in self.game_data.ai_data_json["gender_type"] if x['id'] == op_code_right_condition_param]
                    if not param:
                        print(f"Gender {op_code_right_condition_param} not found")
                    right_subject = {'text': '{}', 'param': param[0]}
                    list_param_possible_right = self.__get_possible_gender()
                elif right_param_type == 'int':
                    right_subject = {'text': '{}', 'param': op_code_right_condition_param}
                elif right_param_type == "special_byte_check":
                    param = [x['data'] for x in self.game_data.ai_data_json['special_byte_check'] if x['id'] == op_code_right_condition_param]
                    if param:
                        param = param[0]
                    else:
                        param = "Unknown special byte"
                        print(f"Unexpected special byte with value {op_code_right_condition_param}")
                    right_subject = {'text': '{}', 'param': param}
                    list_param_possible_right = self.__get_possible_special_byte_check()
                elif right_param_type == 'status_ai':
                    param = [x['name'] for x in self.game_data.status_data_json["status_ai"] if x['id'] == op_code_right_condition_param]
                    if not param:
                        print(f"status_ai {op_code_right_condition_param} not found")
                    right_subject = {'text': '{}', 'param': param[0]}
                    list_param_possible_right = self.__get_possible_status_ai()
                elif right_param_type == 'target_advanced_specific':
                    right_subject = {'text': '{}', 'param': self.__get_target(op_code[3], advanced=True, specific=True)}
                elif right_param_type == 'text':
                    right_subject = {'text': '{}',
                                     'param': [x['right_text'] for x in self.game_data.ai_data_json['if_subject'] if x['subject_id'] == subject_id][0]}
                elif right_param_type == 'target_advanced_generic':
                    right_subject = {'text': '{}', 'param': self.__get_target(op_code[3], advanced=True, specific=False)}
                    list_param_possible_right = self.__get_possible_target_advanced_specific()
                elif right_param_type == 'complex' and subject_id == 10:
                    attack_right_text = "{}"
                    attack_right_condition_param = str(op_code[3])
                    if op_code[1] == 0:  # LAST ATTACK DAMAGE TYPE IS
                        list_param_possible_right.extend([{"id": x['id'], "data": x['type']} for x in self.game_data.ai_data_json['attack_type']])
                        attack_right_condition_param = self.game_data.ai_data_json['attack_type'][op_code_right_condition_param]['type']
                    elif op_code[1] == 1:  # LAST ATTACKER IS
                        attack_right_condition_param = self.__get_target(op_code_right_condition_param, advanced=True, specific=True)
                        list_param_possible_right.extend(self.__get_possible_target_advanced_specific())
                    elif op_code[1] == 2:  # SELF TURN COUNTER IS
                        attack_right_condition_param = int(op_code_right_condition_param)
                    elif op_code[1] == 3:  # LAST ATTACKER USED COMMAND TYPE
                        list_param_possible_right.extend([{"id": x['id'], "data": x['data']} for x in self.game_data.ai_data_json['command_type']])
                        attack_right_condition_param = [x['data'] for x in self.game_data.ai_data_json['command_type'] if
                                                        x['id'] == op_code_right_condition_param][0]
                        if not attack_right_condition_param:
                            attack_right_condition_param = "Unknown {}".format(op_code_right_condition_param)
                        if op_code_right_condition_param == 1:
                            self.__current_if_type = CurrentIfType.SPECIAL_ACTION
                        elif op_code_right_condition_param == 2 or op_code_right_condition_param == 6:
                            self.__current_if_type = CurrentIfType.MAGIC
                        elif op_code_right_condition_param == 4:
                            self.__current_if_type = CurrentIfType.ITEM
                        elif op_code_right_condition_param == 254:
                            self.__current_if_type = CurrentIfType.GFORCE
                        else:
                            print(f"Unknown condition type for subject 10 op code 3: {op_code_right_condition_param}")
                    elif op_code[1] == 4:  # "LAST GFORCE LAUNCH WAS","LAST ACTION LAUNCH WAS"
                        if op_code_right_condition_param >= 64:
                            attack_right_condition_param = self.game_data.gforce_data_json["gforce"][op_code_right_condition_param - 64]['name']
                            list_param_possible_right.extend(self.__get_possible_gforce_shifted_64())
                        else:
                            if self.__current_if_type == CurrentIfType.GFORCE:
                                attack_right_condition_param = self.game_data.gforce_data_json["gforce"][op_code_right_condition_param]['name']
                                list_param_possible_right.extend(self.__get_possible_gforce())
                            if self.__current_if_type == CurrentIfType.MAGIC:
                                ret = self.game_data.magic_data_json["magic"][op_code_right_condition_param]['name']
                                list_param_possible_right.extend(self.__get_possible_magic())
                            elif self.__current_if_type == CurrentIfType.ITEM:
                                ret = self.game_data.item_data_json["items"][op_code_right_condition_param]['name']
                                list_param_possible_right.extend(self.__get_possible_item())
                            elif self.__current_if_type == CurrentIfType.SPECIAL_ACTION:
                                ret = self.game_data.special_action_data_json["special_action"][op_code_right_condition_param]['name']
                                list_param_possible_right.extend(self.__get_possible_special_action())
                            else:
                                ret = str(op_code_right_condition_param)
                            if ret:
                                attack_right_condition_param = ret
                    elif op_code[1] == 5:
                        attack_right_condition_param = str(self.game_data.magic_data_json['magic_type'][op_code_right_condition_param]['name'])
                        list_param_possible_right.extend(self.__get_possible_magic_type())
                    elif op_code[1] == 203:
                        if op_code_right_condition_param == 200:
                            attack_right_condition_param = "SELF"
                        else:
                            attack_right_condition_param = f"{op_code_right_condition_param - 0x10}"
                        list_param_possible_right.extend(self.__get_possible_subject_10_203())
                    else:
                        attack_right_condition_param = op_code_right_condition_param
                    right_subject = {'text': attack_right_text, 'param': attack_right_condition_param}
            else:
                print(f"Unexpected right_param_type: {right_param_type}")
                right_subject = {'text': '{}', 'param': op_code_right_condition_param}

        if_text = if_text.format('{}', left_subject['text'], '{}', right_subject['text'], '{}')

        # right_subject_text = right_subject['text'].format(*right_subject['param'])

        param_possible_sub_id = []
        param_possible_sub_id.extend(
            [{"id": x['subject_id'], "data": x['short_text']} for x in self.game_data.ai_data_json["if_subject"]])
        # op_02 = ['subject_id', 'left condition (target)', 'comparator', 'right condition (value)', 'jump1', 'jump2', 'debug']
        # List of "Subject id" possible list
        self.param_possible_list.append(param_possible_sub_id)
        # List of "Left subject" possible list
        if if_current_subject:
            self.param_possible_list.append(list_param_possible_left)
        else:
            self.param_possible_list.append([{"id": op_code_left_condition_param, "data": "UNUSED"}])
        # List of "Comparator" possible list
        self.param_possible_list.append([{"id": i, "data": self.game_data.ai_data_json["list_comparator"][i]} for i in
                                         range(len(self.game_data.ai_data_json["list_comparator"]))])
        # List of "Right subject" possible list
        self.param_possible_list.append(list_param_possible_right)
        # List of "Jump1" possible list
        self.param_possible_list.append([])
        # List of "Jump2" possible list
        self.param_possible_list.append([])
        # List of "Debug" possible list
        self.param_possible_list.append([])

        list_param = [subject_id_param, left_subject['param'], comparator, right_subject['param'], jump_value]
        print("if list param")
        print(list_param)
        #if '{}' not in left_subject['text'] and subject_id != 10:
        #    del list_param[1]
        return [if_text, list_param]

    def __get_var_name(self, id):
        # There is specific var known, if not in the list it means it's a generic one
        all_var_info = self.game_data.ai_data_json["list_var"]
        var_info_specific = [x for x in all_var_info if x["op_code"] == id]
        if var_info_specific:
            var_info_specific = var_info_specific[0]['var_name']
        else:
            var_info_specific = "var" + str(id)
        return var_info_specific

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

    @staticmethod
    def twos_complement(value, bit_length):
        """
        Calculate the two's complement of a value with a given bit length.

        :param value: The integer value.
        :param bit_length: The number of bits for the representation.
        :return: The two's complement value.
        """
        # Mask to limit the value to the specified bit length
        mask = (1 << bit_length) - 1
        value = value & mask

        # Check if the sign bit is set (negative number)
        if value >> (bit_length - 1):
            # Calculate two's complement for negative numbers
            value = value - (1 << bit_length)
        return value

    def twos_complement_opposite_16bit(value: int) -> int:
        """
        Convert a signed 16-bit integer (-32768 to 32767) into its unsigned 16-bit representation (0-65535).

        :param value: Signed 16-bit integer (-32768 to 32767)
        :return: Unsigned 16-bit integer (0 to 65535)
        """
        return value & 0xFFFF  # Mask to keep only the lower 16 bits
