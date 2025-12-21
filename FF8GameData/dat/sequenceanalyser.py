from ..gamedata import GameData


class SequenceAnalyser:

    def __init__(self, game_data: GameData, model_anim_data, sequence: bytearray):
        self._sequence = sequence
        self._model_anim_data = model_anim_data
        self.game_data = game_data
        self.__op_id = 0
        self.__op_code = []
        self.__raw_parameters = []
        self.__raw_text = ""
        self.__analyse_sequence()

    def __str__(self):
        return f"ID: {self.__op_id}, op_code: {self.__op_code}"

    def __repr__(self):
        return self.__str__()

    def __analyse_sequence(self):
        index_data = 0
        text_analyze = ""
        current_value = 0
        while index_data < len(self._sequence):
            current_opcode_int = self._sequence[index_data]
            hex_data = bytes([self._sequence[index_data]])
            index_data += 1
            current_opcode_hex_str = (hex_data.hex()).upper()
            text_analyze += current_opcode_hex_str
            if current_opcode_int < 0x80:
                current_op_code_data = [x for x in self.game_data.anim_sequence_data_json["op_code_info"] if x['op_code'] == 0x00]
            else:
                current_op_code_data = [x for x in self.game_data.anim_sequence_data_json["op_code_info"] if x['op_code'] == current_opcode_int]
            if current_op_code_data:
                current_op_code_data = current_op_code_data[0]
            else:
                text_analyze += ": Unknown\n"
                continue
            if current_opcode_int < 0x80:
                text_analyze += ": " + current_op_code_data['text'].format(current_opcode_hex_str) + "\n"
                continue
            # Reading param
            if current_op_code_data["size"] == -1:
                current_op_code_size = 1
            else:
                current_op_code_size = current_op_code_data["size"]
            nb_param_analyzed = 0
            param_list = []
            while True:
                if nb_param_analyzed == current_op_code_size:  # If we analyzed all param
                    break
                current_param = self._sequence[index_data]
                index_data += 1
                param_list.append(current_param)
                text_analyze += f" {current_param:02X}"
                nb_param_analyzed += 1

                if current_opcode_int in (0x99, 0xB1, 0x9F):  # Last one is FF
                    if current_param != 0xFF:
                        current_op_code_size += 1
                    else:
                        break
                if current_opcode_int in (0xB8, 0xB5, 0xB6, 0x98, 0x97):
                    if nb_param_analyzed == 2:
                        if current_param & 0x02:
                            current_op_code_size += 1
                    elif current_op_code_size == 1:
                        current_op_code_size = 2
            text_analyze += ": "

            # Now analyzing the opcode
            # Searching the data in op code list
            description_param = []
            if current_op_code_data['complexity'] == "simple":
                for index_param_in_str, param_type in enumerate(current_op_code_data['param_type']):
                    param_index = current_op_code_data['param_index'][index_param_in_str]
                    param_data_int = param_list[param_index]
                    param_data_hex = param_list[param_index: param_index + 1]
                    # For the moment we mainly show int, but in the futur we will show text linked to this ID
                    if param_type == "anim_id":
                        description_param.append(f"{int.from_bytes(param_data_hex, byteorder="little", signed=False)}")
                    elif param_type == "effect_id":
                        param_data_info = [x['text'] for x in self.game_data.anim_sequence_data_json["effect_id"] if x['param_id'] == param_data_int]
                        if param_data_info:
                            param_data_info = param_data_info[0]
                            description_param.append(param_data_info)
                        else:
                            print(f"Param {param_data_int} for {param_type} unexpected")
                            description_param.append(f"{int.from_bytes(param_data_hex, byteorder="little", signed=False)}")
                    elif param_type == "fade_effect_id":
                        param_data_info = [x['text'] for x in self.game_data.anim_sequence_data_json["fade_effect_id"] if x['param_id'] == param_data_int]
                        if param_data_info:
                            param_data_info = param_data_info[0]
                            description_param.append(param_data_info)
                        else:
                            print(f"Param {param_data_int} for {param_type} unexpected")
                    elif param_type == "ubyte":
                        description_param.append(f"{int.from_bytes(param_data_hex, byteorder="little", signed=False)}")
                    elif param_type == "sbyte":
                        description_param.append(f"{int.from_bytes(param_data_hex, byteorder="little", signed=True)}")
                    elif param_type == "int16":
                        description_param.append(f"{int.from_bytes(param_list[param_index: param_index + 2], byteorder="little", signed=True)}")
                    else:
                        description_param.append("Unknown type parameter")
                text_analyze += current_op_code_data['text'].format(*description_param)
            elif current_op_code_data['complexity'] == "complex":
                if current_op_code_data['op_code'] in (0xB8, 0xB5, 0xB6, 0x97, 0x98): # Sound
                    sound_id = param_list[0]
                    sound_flag = param_list[1]
                    if sound_flag & 0x04:
                        volume_text = [x['text'] for x in self.game_data.anim_sequence_data_json["sound_channel_flag"] if x["param_id"] == 0x04][0]
                    elif sound_flag & 0x01:
                        volume_text = [x['text'] for x in self.game_data.anim_sequence_data_json["sound_channel_flag"] if x["param_id"] == 0x01][0]
                    else:
                        volume_text = [x['text'] for x in self.game_data.anim_sequence_data_json["sound_channel_flag"] if x["param_id"] == 0xFFFF][0]
                    if sound_flag & 0x02:
                        channel_mask = param_list[2]
                    else:
                        channel_mask = 0

                    if current_op_code_data['op_code'] == 0xB8:
                        sound_category = sound_id / 10000
                        sound_index_reminder = sound_id % 10000
                        if sound_category != 0x45:
                            sound_shift = [x['value'] for x in self.game_data.anim_sequence_data_json["sound_channel_flag"] if x["param_id"] == sound_category]
                            if sound_shift:
                                sound_shift = sound_shift[0]
                            else:  # default value, expected
                                sound_shift = 0
                            final_sound_id = sound_index_reminder + sound_shift
                        else:
                            if sound_id == 690000:
                                final_sound_id = 2060
                            else:
                                final_sound_id = sound_id - 688040
                        text_analyze += current_op_code_data['text'].format(sound_category, final_sound_id, channel_mask, volume_text)
                    elif current_op_code_data['op_code'] in (0xB5, 0xB6):
                        if sound_id >= 7:
                            final_sound_id = "sound id >= 7 is unexpected"
                        else:
                            final_sound_id = sound_id
                        text_analyze += current_op_code_data['text'].format(final_sound_id, channel_mask, volume_text)
                    elif current_op_code_data['op_code'] in (0x97, 0x98):
                        text_analyze += current_op_code_data['text'].format(channel_mask, volume_text)

                if current_op_code_data['op_code'] in (0x99, 0xb1):
                    pass
                if current_op_code_data['op_code'] in (0xC3, 0xC7, 0xCB, 0xCF, 0xD3, 0xD7, 0xDB, 0xDF, 0xE3, 0xE5):
                    if param_list[0] < 0x80:
                        if current_op_code_data['op_code'] == 0xE5:
                            special_read = [x['text'] for x in self.game_data.anim_sequence_data_json["e5_special_params"] if
                                            param_list[0] == x['param_id']]
                        else:
                            special_read = [x['text'] for x in self.game_data.anim_sequence_data_json["special_change_current_value_params"] if
                                            param_list[0] == x['param_id']]
                        if special_read:
                            special_read = special_read[0]
                        else:
                            print(f"No param_id in special_change_current_value_params for {param_list[0]}")
                        text_analyze += current_op_code_data['text'].format(special_read)
                    else:
                        if current_op_code_data['op_code'] == 0xE5:
                            special_read = [x['text'] for x in self.game_data.anim_sequence_data_json["e5_special_params"] if 0x80 == x['param_id']]
                        else:
                            special_read = [x['text'] for x in self.game_data.anim_sequence_data_json["special_change_current_value_params"] if
                                            0x80 == x['param_id']]
                        if special_read:
                            special_read = special_read[0]
                        else:
                            print(f"No param_id in special_change_current_value_params for >=0x80 values")
                        text_analyze += current_op_code_data['text'].format(special_read.format(param_list[0]))

            text_analyze += "\n"
        self.__raw_text = text_analyze

    def get_size(self):
        return len(self._sequence)

    def get_id(self):
        return self.__op_id

    def get_op_code(self):
        return self.__op_code

    def get_text_param(self):
        return self.__raw_parameters

    def get_text(self):
        return self.__raw_text
