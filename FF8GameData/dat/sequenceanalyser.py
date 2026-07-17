from FF8GameData.dat.sequencecommand import read_sequence, SequenceCommand
from FF8GameData.dat.sequencevm import as_sequence_vm


def describe_command(command: SequenceCommand) -> str:
    """What one command does, in plain text (no hex prefix).

    This is THE description of a command: the full-sequence analyser and the per-command
    rows of IfritSeq both call it, so a command cannot read differently in the two views.
    """
    info = command.get_op_code_info()
    if info is None:
        # An op code the json does not describe. The engine ignores it (dispatcher
        # default case) - the walker already gave it zero parameters.
        return "Unknown"
    if command.is_animation():
        return info['text'].format(f"{command.op_code:02X}")
    parameters = bytes(command.parameters or b"")
    if info['complexity'] == "simple":
        return info['text'].format(*_simple_param_list(command.vm, info, parameters))
    # Complex op codes: the parameters do not simply map one to one onto the text
    op_code = command.op_code
    if op_code in (0xB8, 0xB5, 0xB6, 0x97, 0x98):
        return _describe_sound(command.vm, info, parameters)
    if op_code in (0x99, 0xB1):
        return _describe_walk_effect(op_code, parameters)
    if op_code in (0xC3, 0xC7, 0xCB, 0xCF, 0xD3, 0xD7, 0xDB, 0xDF, 0xE3, 0xE5):
        return _describe_special_value(command.vm, info, parameters)
    if op_code in (0xB0, 0xB4):
        return _describe_hit_effect(parameters)
    # Complex op codes with no dedicated description (AB, 9F): parameters shown, no text
    return ""


class SequenceAnalyser:
    """Turn a sequence into the text IfritSeq displays, one line per command.

    Command boundaries come from sequencecommand.read_sequence(), the walk shared with
    the loop detector and the splitter, so a byte string cannot be described one way and
    rewritten another. This fixed two mis-reads the old private walk had (both checked
    against FF8_EN.exe AnimSeq_DispatchActionOpcode @0x504bb0):
    - AB (Renzokuken init) consumed one parameter byte instead of two, so every command
      after it in Squall's weapon sequences was read one byte off;
    - B0/B4 (hit particle effect) had their first byte eaten by the generic parameter
      loop before the dedicated parser ran, so the effect id shown was actually the flag
      byte, and the real following command was swallowed as fake extra parameters.

    The first argument may be a GameData (the entity VM is used, as before) or a SequenceVM
    (e.g. the camera VM). The parameter is still called game_data so the many callers that
    pass game_data=... keep working.
    """

    def __init__(self, game_data, model_anim_data, sequence: bytearray):
        self._sequence = sequence
        self._model_anim_data = model_anim_data
        self.vm = as_sequence_vm(game_data)
        self.__raw_text = ""
        self.__analyse_sequence()

    def get_size(self):
        return len(self._sequence)

    def get_text(self):
        return self.__raw_text

    def __analyse_sequence(self):
        text_analyze = ""
        data = bytes(self._sequence)
        while data:
            for command in read_sequence(self.vm, data):
                if command.is_unknown():
                    # Unknown 0xC0+ op code: its parameter size is unknown, so the reading
                    # of the following bytes is a guess. Say so and try the next byte as
                    # an op code rather than dropping the rest of the sequence.
                    text_analyze += f"{command.op_code:02X}: Unknown\n"
                    data = bytes(command.unknown_tail)
                    break
                text_analyze += self.__line(command) + "\n"
            else:
                data = b""
        self.__raw_text = text_analyze

    @staticmethod
    def __line(command: SequenceCommand) -> str:
        """One line: the command's bytes in hex, then what it does."""
        text = f"{command.op_code:02X}"
        for param in bytes(command.parameters or b""):
            text += f" {param:02X}"
        return text + ": " + describe_command(command)


def _simple_param_list(vm, info, parameters) -> list:
    """The values the json text's placeholders are filled with, in placeholder order."""
    description_param = []
    for index_param_in_str, param_type in enumerate(info['param_type']):
        param_index = info['param_index'][index_param_in_str]
        param_data_int = parameters[param_index]
        if param_type == "anim_id":
            description_param.append(f"{param_data_int}")
        elif param_type in ("effect_id", "fade_effect_id"):
            param_data_info = [x['text'] for x in vm.data_json[param_type]
                               if x['param_id'] == param_data_int]
            if param_data_info:
                description_param.append(param_data_info[0])
            else:
                # Unknown id (vanilla c0m056 has a fade id 5 the json does not list):
                # show the raw value instead of shifting every following placeholder,
                # which used to crash the analyse with an IndexError.
                print(f"Param {param_data_int} for {param_type} unexpected")
                description_param.append(f"{param_data_int}")
        elif param_type == "ubyte":
            description_param.append(f"{param_data_int}")
        elif param_type == "sbyte":
            description_param.append(
                f"{int.from_bytes(parameters[param_index: param_index + 1], byteorder='little', signed=True)}")
        elif param_type == "int16":
            description_param.append(
                f"{int.from_bytes(parameters[param_index: param_index + 2], byteorder='little', signed=True)}")
        else:
            description_param.append("Unknown type parameter")
    return description_param


def _describe_sound(vm, info, parameters) -> str:
    sound_id = parameters[0]
    sound_flag = parameters[1] if len(parameters) > 1 else 0
    if sound_flag & 0x04:
        volume_text = [x['text'] for x in vm.data_json["sound_channel_flag"]
                       if x["param_id"] == 0x04][0]
    elif sound_flag & 0x01:
        volume_text = [x['text'] for x in vm.data_json["sound_channel_flag"]
                       if x["param_id"] == 0x01][0]
    else:
        volume_text = [x['text'] for x in vm.data_json["sound_channel_flag"]
                       if x["param_id"] == 0xFFFF][0]
    if sound_flag & 0x02:
        channel_mask = parameters[2]
    else:
        channel_mask = 0

    if info['op_code'] == 0xB8:
        sound_category = sound_id / 10000
        sound_index_reminder = sound_id % 10000
        if sound_category != 0x45:
            sound_shift = [x['value'] for x in vm.data_json["sound_channel_flag"]
                           if x["param_id"] == sound_category]
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
        return info['text'].format(sound_category, final_sound_id, channel_mask, volume_text)
    if info['op_code'] in (0xB5, 0xB6):
        if sound_id >= 7:
            final_sound_id = "sound id >= 7 is unexpected"
        else:
            final_sound_id = sound_id
        return info['text'].format(final_sound_id, channel_mask, volume_text)
    # 0x97 / 0x98
    return info['text'].format(channel_mask, volume_text)


def _describe_walk_effect(op_code, parameters) -> str:
    if op_code == 0x99:
        sound_id_text = "3"
    else:  # 0xB1
        sound_id_text = "2"
    text = f"Queue walk effect and sound (sound walk ID, {sound_id_text})"
    bone_selection = parameters[0]
    text += f" applied on bone {bone_selection} and do:\n"
    for param in parameters[1:]:
        if param == 0xFF:  # End of list
            break
        frame_to_wait = param & 0x3F
        effect_on = not bool(param & 0x40)
        sound_on = not bool(param & 0x80)
        text += f"Wait {frame_to_wait} frames, then apply effect:{effect_on} aand/or play sound: {sound_on}\n"
    return text


def _describe_special_value(vm, info, parameters) -> str:
    if parameters[0] < 0x80:
        if info['op_code'] == 0xE5:
            special_read = [x['text'] for x in vm.data_json["e5_special_params"]
                            if parameters[0] == x['param_id']]
        else:
            special_read = [x['text'] for x in
                            vm.data_json["special_change_current_value_params"]
                            if parameters[0] == x['param_id']]
        if special_read:
            special_read = special_read[0]
        else:
            print(f"No param_id in special_change_current_value_params for {parameters[0]}")
        return info['text'].format(special_read)
    if info['op_code'] == 0xE5:
        special_read = [x['text'] for x in vm.data_json["e5_special_params"]
                        if 0x80 == x['param_id']]
    else:
        special_read = [x['text'] for x in
                        vm.data_json["special_change_current_value_params"]
                        if 0x80 == x['param_id']]
    if special_read:
        special_read = special_read[0]
    else:
        print(f"No param_id in special_change_current_value_params for >=0x80 values")
    return info['text'].format(special_read.format(parameters[0]))


def _describe_hit_effect(parameters) -> str:
    """B0/B4: spawn hit particle effect on attacker (B0) / target (B4).

    Byte layout (from FF8_EN.exe ProcessAttackerPostHitSequence @ 0x505900):
    - byte 0: effect id (stored in the effect workspace)
    - byte 1: flag byte:
        - bit0 (0x01): one extra byte (effect param 1)
        - bit1 (0x02): one extra byte (effect param 2, bit7 forced by camera angle)
        - bit2 (0x04): one extra byte (effect param 3)
        - bit3 (0x08): spawn effect at a specific bone -> one extra byte (bone id).
          WARNING: the game only consumes this byte when the attack HITS (B4 on a
          miss leaves it in the stream) - vanilla data avoids that situation.
        - bit4 (0x10): spawn effect at a random bone (no extra byte)
        - bit5 (0x20): flip effect direction (used with bit3/bit4)
        - bit6 (0x40): custom position vector -> three extra int16 LE (x, y, z)
        - none of bit3/bit4/bit6: spawn default effect at the entity
    """
    effect_id = parameters[0]
    extra_flags = parameters[1] if len(parameters) > 1 else 0
    index = 2
    extra_params = []
    for bit in (0x01, 0x02, 0x04):
        if extra_flags & bit:
            extra_params.append(parameters[index])
            index += 1
    if extra_flags & 0x08:
        bone_id = parameters[index]
        index += 1
        branch_desc = f"spawn at bone {bone_id}"
        if extra_flags & 0x20:
            branch_desc += " (flipped direction)"
    elif extra_flags & 0x10:
        branch_desc = "spawn at a random bone"
        if extra_flags & 0x20:
            branch_desc += " (flipped direction)"
    elif extra_flags & 0x40:
        vec_x = int.from_bytes(parameters[index:index + 2], 'little', signed=True)
        vec_y = int.from_bytes(parameters[index + 2:index + 4], 'little', signed=True)
        vec_z = int.from_bytes(parameters[index + 4:index + 6], 'little', signed=True)
        branch_desc = f"spawn at custom position ({vec_x}, {vec_y}, {vec_z})"
    else:
        branch_desc = "spawn default effect"

    text = f"Spawn hit particle effect - effectId={effect_id}, flags=0x{extra_flags:02X}, {branch_desc}"
    if extra_params:
        text += f", extraParams={extra_params}"
    return text
