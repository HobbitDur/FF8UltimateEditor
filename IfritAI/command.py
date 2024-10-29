from gamedata import GameData


class Command():

    def __init__(self, op_id: int, op_code: list, game_data: GameData, battle_text=(), info_stat_data_monster_name="",
                 line_index=0, color="#0055ff"):
        self.__op_id = op_id
        self.__op_code = op_code
        self.__battle_text = battle_text
        self.__text = ""
        self.__text_colored = ""
        self.game_data = game_data
        self.info_stat_data_monster_name = info_stat_data_monster_name
        self.__color_param = color
        self.line_index = line_index
        self.__if_index = 0
        self.was_physical = False
        self.was_magic = False
        self.was_item = False
        self.was_gforce = False
        self.type_data = []
        self.id_possible_list = [{'id': x['op_code'], 'data': x['short_text']} for x in self.game_data.ai_data_json['op_code_info']]
        self.param_possible_list = []
        self.__analyse_op_data()

    def __str__(self):
        return f"ID: {self.__op_id}, op_code: {self.__op_code}, text: {self.__text}"

    def __repr__(self):
        return self.__str__()

    def set_color(self, color):
        self.__color_param = color
        self.__analyse_op_data()

    def set_op_id(self, op_id):
        self.__op_id = op_id
        op_info = self.__get_op_code_line_info()
        self.__op_code = [0] * op_info["size"]

        self.id_possible_list=[{'id': x['op_code'], 'data': x['short_text']} for x in self.game_data.ai_data_json['op_code_info']]
        self.__analyse_op_data()

    def set_op_code(self, op_code):
        self.__op_code = op_code
        self.__analyse_op_data()

    def get_id(self):
        return self.__op_id

    def get_op_code(self):
        return self.__op_code

    def get_text(self):
        return self.__text

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

    def __analyse_op_data(self):
        self.param_possible_list = []
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
                elif type == "var":
                    # There is specific var known, if not in the list it means it's a generic one
                    param_value.append(self.__get_var_name(self.__op_code[op_index]))
                    param_list = [{"id": x['op_code'], "data": x['var_name']} for x in
                                  self.game_data.ai_data_json["list_var"]]
                    self.param_possible_list.append(param_list)
                elif type == "special_action":
                    if self.__op_code[op_index] < len(self.game_data.special_action):
                        param_value.append(self.game_data.special_action[self.__op_code[op_index]]['name'])
                        self.param_possible_list.append([{'id': id, 'data': val_dict['name']} for id, val_dict in
                                                         self.game_data.special_action.items()])
                    else:
                        param_value.append("UNKNOWN SPECIAL_ACTION")
                elif type == "card":
                    if self.__op_code[op_index] < len(self.game_data.card_values):
                        param_value.append(self.game_data.card_values[self.__op_code[op_index]]['name'])
                        self.param_possible_list.append([{'id': id, 'data': val_dict['name']} for id, val_dict in
                                                         self.game_data.card_values.items()])
                    else:
                        param_value.append("UNKNOWN CARD")
                elif type == "monster":
                    if self.__op_code[op_index] < len(self.game_data.monster_values):
                        param_value.append(self.game_data.monster_values[self.__op_code[op_index]])
                        self.param_possible_list.append([{'id': i, 'data': self.game_data.monster_values[i]} for i in
                                                         range(len(self.game_data.monster_values))])
                    else:
                        param_value.append("UNKNOWN MONSTER")
                elif type == "item":
                    if self.__op_code[op_index] < len(self.game_data.item_values):
                        param_value.append(self.game_data.item_values[self.__op_code[op_index]]['name'])
                        self.param_possible_list.append([{'id': id, 'data': val_dict['name']} for id, val_dict in
                                                         self.game_data.item_values.items()])
                    else:
                        param_value.append("UNKNOWN ITEM")
                elif type == "gforce":
                    if self.__op_code[op_index] < len(self.game_data.gforce_values):
                        param_value.append(self.game_data.gforce_values[self.__op_code[op_index]])
                        self.param_possible_list.append([{'id': i, 'data': self.game_data.gforce_values[i]} for i in
                                                         range(len(self.game_data.gforce_values))])
                    else:
                        param_value.append("UNKNOWN GFORCE")
                elif type == "target":
                    param_value.append(self.__get_target(self.__op_code[op_index]))
                    self.param_possible_list.append([x for x in self.__get_target_list()])
                else:
                    print("Unknown type, considering a int")
                    param_value.append(self.__op_code[op_index])
            for i in range(len(param_value)):
                param_value[i] = '<span style="color:' + self.__color_param + ';">' + param_value[i] + '</span>'
            self.__text = (op_info['text'] + " (size:{}bytes)").format(*param_value, op_info['size'] + 1)
        elif op_info["complexity"] == "complex":
            call_function = getattr(self, "_Command__op_" + "{:02}".format(op_info["op_code"]) + "_analysis")
            call_result = call_function(self.__op_code)
            self.__text = call_result[0].format(
                *['<span style="color:' + self.__color_param + ';">' + str(x) + '</span>' for x in call_result[1]])
            self.__text += " (size:{}bytes)".format(op_info['size'] + 1)

    def __op_23_analysis(self, op_code):
        if op_code[0] > 0:
            ret = "DEACTIVATE RUN"
        else:
            ret = "ACTIVATE RUN"
        self.param_possible_list.append([{'id': 1, 'data': "DEACTIVATE RUN"}, {'id': 0, 'data': "ACTIVATE RUN"}])
        return [ret, []]

    def __op_38_analysis(self, op_code):
        if op_code[3] < len(self.game_data.status_ia_values):
            status = self.game_data.status_ia_values[op_code[3]]['name']
        else:
            status = "UNKNOWN STATUS"

        info = ", unknown {}|{}".format(op_code[0], op_code[2])
        self.param_possible_list.append([])
        self.param_possible_list.append(self.__get_target_list())
        self.param_possible_list.append([])
        param_possible = []
        for index, el in self.game_data.status_ia_values.items():
            param_possible.append({'id': index, 'data': el['name']})
        self.param_possible_list.append(param_possible)
        ret = "TARGET {} WITH STATUS {}{}"
        return [ret, [self.__get_target(op_code[1]), status, info]]

    def __op_24_analysis(self, op_code):
        ret = self.__op_01_analysis(op_code)
        ret[0] += ' + unknown action'
        return [ret[0], ret[1]]

    def __op_40_analysis(self, op_code):
        aptitude_info = [x for x in self.game_data.ai_data_json['aptitude_list'] if x['aptitude_id'] == op_code[0]]
        if aptitude_info:
            aptitude_text = aptitude_info[0]['text']
        else:
            aptitude_text = "Unknown aptitude"
        self.param_possible_list.append([{"id": x["aptitude_id"], "data" :x['text']} for x in self.game_data.ai_data_json['aptitude_list']])
        self.param_possible_list.append([])
        if op_code[1] == 10:
            return ["REINIT {} TO BASE VALUE", [aptitude_text, op_code[1] / 10]]
        else:

            return ["MULTIPLY {} BY {}", [aptitude_text, op_code[1] / 10]]

    def __op_35_analysis(self, op_code):
        jump = int.from_bytes(bytearray([op_code[0], op_code[1]]), byteorder='little')
        self.param_possible_list.append([])
        self.param_possible_list.append([])
        if jump == 0:
            return ['ENDIF', []]
        elif jump == 3:
            return ['ELSE go next line', []]
        else:
            return ['ELSE jump {} bytes forward', [jump]]

    def __op_45_analysis(self, op_code):
        # op_2D = ['element', 'elementval', '?']
        if op_code[0] < len(self.game_data.magic_type_values):
            element = self.game_data.magic_type_values[op_code[0]]
        else:
            element = "UNKNOWN ELEMENT TYPE"
        element_val = op_code[1]
        op_code_unknown = op_code[2]
        param_possible = []
        for i in range(len(self.game_data.magic_type_values)):
            param_possible.append({'id':i, 'data': self.game_data.magic_type_values[i]})
        self.param_possible_list.append(param_possible)
        self.param_possible_list.append([])
        self.param_possible_list.append([])
        return ['Resist element {} at {}, unknown value (impact on resist element): {}', [element, element_val, op_code_unknown]]

    def __op_26_analysis(self, op_code):
        analysis = self.__op_01_analysis(op_code)
        analysis[0] += ' AND LOCK BATTLE'
        return analysis

    def __op_01_analysis(self, op_code):
        if op_code[0] < len(self.__battle_text):
            ret = 'SHOW BATTLE TEXT: {}'
            param_return = [self.__battle_text[op_code[0]]]
        else:
            ret = "/!\\SHOW BATTLE BUT NO BATTLE TO SHOW"
            param_return = []
        possible_param = []
        for i in range (len(self.__battle_text)):
            possible_param.append({'id': i, 'data': self.__battle_text[i]})
        self.param_possible_list.append(possible_param)
        return [ret, param_return]

    def __op_02_analysis(self, op_code):
        # op_02 = ['subject_id', 'left condition (target)', 'comparator', 'right condition (value)', 'jump1', 'jump2', 'debug']
        subject_id = op_code[0]
        op_code_left_condition_param = op_code[1]
        op_code_comparator = op_code[2]
        op_code_right_condition_param = op_code[3]
        debug_unknown = op_code[4]
        jump_value_op_1 = op_code[5]
        jump_value_op_2 = op_code[6]
        jump_value = int.from_bytes(bytearray([op_code[5], op_code[6]]), byteorder='little')
        target = self.__get_target(op_code_left_condition_param)
        target_reverse = self.__get_target(op_code_left_condition_param, reverse=True)
        if op_code_comparator < len(self.game_data.ai_data_json['list_comparator_html']):
            comparator = self.game_data.ai_data_json['list_comparator_html'][op_code_comparator]
        else:
            comparator = 'UNKNOWN OPERATOR'

        left_subject = {'text': "", 'param': None}
        right_subject = {'text': "", 'param': []}

        if_subject_left_data = [x for x in self.game_data.ai_data_json["if_subject"] if x["subject_id"] == subject_id]
        list_param_possible_left = []
        if if_subject_left_data:
            if_subject_left_data = if_subject_left_data[0]
            if if_subject_left_data["complexity"] == "simple":
                if if_subject_left_data['param_left_type'] == "target":
                    param_left = target
                    list_param_possible_left.extend(self.__get_target_list())
                elif if_subject_left_data['param_left_type'] == "target_reverse":
                    param_left = target_reverse
                    list_param_possible_left.extend(self.__get_target_list(True))
                elif if_subject_left_data['param_left_type'] == "int":
                    param_left = op_code_left_condition_param
                elif if_subject_left_data['param_left_type'] == "":
                    param_left = "UNKNOWN {}".format(op_code_left_condition_param)
                else:
                    print("Unexpected param_left_type: {}".format(if_subject_left_data['param_left_type']))
                    param_left = op_code_left_condition_param
                    list_param_possible_left.append({"id:": op_code_left_condition_param, "data": "Unused"})

                left_subject = {'text': if_subject_left_data["left_text"], 'param': param_left}
        elif subject_id > 19:
            left_subject = {'text': '{}', 'param': self.__get_var_name(subject_id)}
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        else:
            left_subject = {'text': 'UNKNOWN SUBJECT', 'param': None}
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}

        if subject_id == 0:
            right_subject = {'text': '{} %', 'param': [op_code_right_condition_param * 10]}
        elif subject_id == 1:
            right_subject = {'text': '{} %', 'param': [op_code_right_condition_param * 10]}
        elif subject_id == 2:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 3:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 4:
            right_subject = {'text': '{}', 'param': [self.game_data.status_ia_values[op_code_right_condition_param]['name']]}
        elif subject_id == 5:
            right_subject = {'text': '{}', 'param': [self.game_data.status_ia_values[op_code_right_condition_param]['name']]}
        elif subject_id == 6:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 9:
            right_subject = {'text': '{}', 'param': [self.__get_target(op_code[3])]}
        elif subject_id == 10:
            attack_left_text = "{}"
            attack_left_condition_param = [str(op_code[1])]
            attack_right_text = "{}"
            attack_right_condition_param = [str(op_code[3])]
            subject_left_data = [x['text'] for x in self.game_data.ai_data_json['subject_left_10'] if x['param_id'] == op_code[1]]
            if not subject_left_data:
                attack_left_text = "Unknown last attack {}"
            else:
                attack_left_condition_param = subject_left_data
            if op_code[1] == 0:
                attack_right_condition_param = [str(op_code[3])]
            elif op_code[1] == 1:
                attack_right_condition_param = [target]
            elif op_code[1] == 3:
                if op_code_right_condition_param == 1:
                    attack_right_condition_param = ["Physical damage"]
                    self.was_physical = True
                elif op_code_right_condition_param == 2:
                    attack_right_condition_param = ["Magical damage"]
                    self.was_magic = True
                elif op_code_right_condition_param == 4:
                    attack_right_condition_param = ["Item"]
                    self.was_item = True
                elif op_code_right_condition_param == 254:
                    attack_right_condition_param = ["G-Force"]
                    self.was_force = True
                else:
                    attack_right_condition_param = ["Unknown {}".format(op_code_right_condition_param)]
            elif op_code[1] == 4:
                if op_code_right_condition_param >= 64:
                    attack_left_condition_param = [attack_left_condition_param[0][0]]
                    attack_right_condition_param = [self.game_data.gforce_values[op_code_right_condition_param - 64]]
                else:
                    if self.was_magic:
                        ret = self.game_data.magic_values[op_code_right_condition_param]['name']
                    elif self.was_item:
                        ret = self.game_data.item_values[op_code_right_condition_param]['name']
                    elif self.was_physical:
                        ret = self.game_data.special_action[op_code_right_condition_param]['name']
                    else:
                        ret = str(op_code_right_condition_param)
                    attack_left_condition_param = [attack_left_condition_param[0][1]]
                    attack_right_condition_param = [ret]
                    self.was_magic = False
                    self.was_item = False
                    self.was_physical = False
            elif op_code[1] == 5:
                attack_right_condition_param = [str(self.game_data.magic_type_values[op_code_right_condition_param])]
            else:
                attack_left_text = "Unknown attack type {}"
                attack_right_condition_param = [op_code_right_condition_param]

            left_subject = {'text': attack_left_text, 'param': attack_left_condition_param}
            right_subject = {'text': attack_right_text, 'param': attack_right_condition_param}
        elif subject_id == 14:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 15:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 17:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 18:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        elif subject_id == 19:
            right_subject = {'text': '{}', 'param': [op_code_right_condition_param]}
        left_subject_text = left_subject['text'].format(left_subject['param'])
        right_subject_text = right_subject['text'].format(*right_subject['param'])

        param_possible_sub_id = []
        param_possible_sub_id.extend(
            [{"id": x['subject_id'], "data": x['short_text']} for x in self.game_data.ai_data_json["if_subject"]])
        param_possible_sub_id.extend(
            [{"id": x['op_code'], "data": x['var_name']} for x in self.game_data.ai_data_json["list_var"]])
        # op_02 = ['subject_id', 'left condition (target)', 'comparator', 'right condition (value)', 'jump1', 'jump2', 'debug']
        # List of "Subject id" possible list
        self.param_possible_list.append(param_possible_sub_id)
        # List of "Left subject" possible list
        if if_subject_left_data:
            self.param_possible_list.append(list_param_possible_left)
        else:
            self.param_possible_list.append([{"id": op_code_left_condition_param, "data":"UNUSED"}])
        # List of "Comparator" possible list
        self.param_possible_list.append([{"id": i, "data": self.game_data.ai_data_json["list_comparator"][i]} for i in
                                         range(len(self.game_data.ai_data_json["list_comparator"]))])
        # List of "Right subject" possible list
        self.param_possible_list.append([])
        # List of "Jump1" possible list
        self.param_possible_list.append([])
        # List of "Jump2" possible list
        self.param_possible_list.append([])
        # List of "Debug" possible list
        self.param_possible_list.append([])

        if op_code[4] != 0:
            return ["IF {} {} {} (Subject ID:{}) | ELSE jump {} bytes forward | Debug: {}",
                    [left_subject_text, comparator, right_subject_text, subject_id, jump_value, op_code[4]]]
        else:
            return ["IF {} {} {} (Subject ID:{}) | ELSE jump {} bytes forward",
                    [left_subject_text, comparator, right_subject_text, subject_id, jump_value]]

    def __op_39_analysis(self, op_code):
        if op_code[0] == 23:
            ret = 'auto-boomerang'
        else:
            ret = "unknown flag {}".format(op_code[0])
        return ['MAKE {} of {} to {}', [ret, self.info_stat_data_monster_name, op_code[1]]]

    def __get_var_name(self, id):
        # There is specific var known, if not in the list it means it's a generic one
        all_var_info = self.game_data.ai_data_json["list_var"]
        var_info_specific = [x for x in all_var_info if x["op_code"] == id]
        if var_info_specific:
            var_info_specific = var_info_specific[0]['var_name']
        else:
            var_info_specific = "var" + str(id)
        return var_info_specific

    def __get_target_list(self, reverse=False):
        list_target = []
        for i in range(len(self.game_data.ai_data_json['list_target_char'])):
            list_target.append({"id": i, "data": self.game_data.ai_data_json['list_target_char'][i]})
        for i in range(0, len(self.game_data.monster_values)):
            list_target.append({"id": i + 16, "data": self.game_data.monster_values[i]})
        for el in self.game_data.ai_data_json['target_special']:
            if el['param_type'] == "reverse":  # C8 data
                if reverse:
                    data = [x['text'] for x in self.game_data.ai_data_json['target_special'] if x['param_id'] == 204][
                        0] + "(by reverse)" # Same than param id 204. No check as we are sure 204 is there
                else:
                    data = self.info_stat_data_monster_name
            elif el['param_type'] == "monster_name":  # Same than param id 204
                data = self.info_stat_data_monster_name
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

    def __get_target(self, id, reverse=False):
        target = [x['data'] for x in self.__get_target_list(reverse) if x['id'] == id]
        if target:
            return target[0]
        else:
            print("Unexpected target with id: {}".format(id))
            return "UNKNOWN TARGET"
