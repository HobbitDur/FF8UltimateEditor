"""Movements driven by `current_frame / total_frames` end where they are meant to.

Many attack sequences move the model along with an animation they start with A0, one step per
tick for as many ticks as the animation has frames (a `C3 0A` counter), each step written as a
ratio of the frame being played (Ward's attack, the way back after the blow, weapon daw039
sequence 13):

    A0 1D                      play anim 29, keep going
    C3 0A  E5 7F               counter = its frame count
    ...  CF 09  ...  D3 0A     offset = start * current_frame / total_frames ...
    E5 0F  A1  ...  E7 ..      write the forward offset, next tick, loop on the counter

current_frame only goes from 0 to total_frames - 1 on those ticks, so the movement stops one
step short of its end (1/4 of Ward's way back in vanilla, 1/8 once converted). The end of the
sequence then puts the model back on its spot in a single frame. At 15 fps that is one more
big step among others; at 30 fps, where every other step is half as big, it shows as a jump.

A 30 fps conversion knows the frame count of the animation each of those loops runs on, so it
divides by total_frames - 1 instead (D3 0A -> D2 n-1, same size: no jump moves): the last tick
reaches the end. The model then also stands where the end of the sequence puts it, and what is
spawned at its feet meanwhile (99/B1 footstep dust) stays under them.

Only a movement nothing moves again before the sequence ends (A2/AC put the model back), or
before the sequence puts it back itself by writing 0 (Squall: C1 00 E5 0F right after his way
back): that is the one that leaves a jump. A movement the sequence goes on from (Zell's punches, each from
where the last one stopped) has no jump to remove and keeps its vanilla path.
"""
from .sequencecommand import get_jump_target, iter_command

_TOTAL_FRAMES = 0x0A      # C3/CF/D3 special read: ACTIVE_ANIM_CMD->total_frames
_CURRENT_FRAME = 0x09     # ACTIVE_ANIM_CMD->current_frame
_STACK_FIRST = 0xF8       # E5/C3 F8-FF: the sequence's scratch stack, free to sit in between
_OFFSET_VAR = (0x0D, 0x0E, 0x0F)  # E5 0D/0E/0F: the entity-local offset (side, up, forward)
_END_OP = (0xA2, 0xAC)    # end of the sequence: the engine puts the model back


def _is_last_movement(command_list, index, written) -> bool:
    """Whether nothing writes the offset component `written` again, in byte order after the loop
    the command at `index` sits in, before the sequence ends."""
    loop_end = None
    for later, (address, op_code, parameters) in enumerate(command_list[index:], index):
        target = get_jump_target(address, op_code, parameters or b"")
        if target is not None and target <= command_list[index][0]:
            loop_end = later
            break
    if loop_end is None:
        return False
    previous = None
    for address, op_code, parameters in command_list[loop_end + 1:]:
        if parameters is None:
            return False
        if op_code in _END_OP:
            return True
        if op_code == 0xE5 and parameters[:1] == bytes([written]):
            # back to 0 (C1 00 / C0 00 00 just before): the same jump, written by hand
            return previous is not None and previous[0] in (0xC1, 0xC0) and not any(previous[1])
        previous = (op_code, parameters)
        if get_jump_target(address, op_code, parameters) is not None or op_code == 0xA7:
            return False  # another path: not followed here
    return False


def _find_site_list(vm, data: bytes, frame_count):
    """[(address of the D3, anim id, frame count)] in one sequence."""
    command_list = [command for command in iter_command(vm, data)]
    site_list = []
    anim_id = None            # what A0 started, while nothing else was played since
    counted = False           # a C3 0A (the animation's frame count) was read since that A0
    for index, (address, op_code, parameters) in enumerate(command_list):
        if parameters is None:
            break
        if op_code == 0xA0 and parameters:
            anim_id, counted = parameters[0], False
            continue
        if op_code < 0x80 or op_code in (0xA2, 0xA3, 0xA7):
            anim_id, counted = None, False
            continue
        if op_code == 0xC3 and parameters[:1] == bytes([_TOTAL_FRAMES]):
            counted = anim_id is not None
            continue
        if not counted or op_code != 0xCF or parameters[:1] != bytes([_CURRENT_FRAME]):
            continue
        for offset, (next_address, next_op, next_parameters) in enumerate(command_list[index + 1:index + 5], 1):
            if next_parameters is None:
                break
            if next_op == 0xD3 and next_parameters[:1] == bytes([_TOTAL_FRAMES]):
                written = next((parameters[0] for _a, op, parameters in command_list[index + offset + 1:index + offset + 6]
                                if op == 0xE5 and parameters and parameters[0] in _OFFSET_VAR), None)
                count = frame_count(anim_id)
                if written is not None and 2 <= count <= 256 and _is_last_movement(command_list, index, written):
                    site_list.append((next_address, anim_id, count))
                break
            if next_op not in (0xC3, 0xE5) or not next_parameters or next_parameters[0] < _STACK_FIRST:
                break
    return site_list


def end_frame_ratio_movements(vm, seq_animation_data, frame_count) -> list:
    """Make every `current_frame / total_frames` movement of an A0-driven loop reach its end, in
    place. frame_count(anim id) is the frame count of that animation in the converted file (the
    body's for a character). Returns [(seq id, address, anim id, divisor)]."""
    changed = []
    for sequence in (seq_animation_data or {}).get('seq_animation_data', []):
        data = bytearray(sequence['data'])
        site_list = _find_site_list(vm, bytes(data), frame_count)
        for address, anim_id, count in site_list:
            data[address] = 0xD2
            data[address + 1] = count - 1
            changed.append((sequence['id'], address, anim_id, count - 1))
        if site_list:
            sequence['data'] = data
    return changed
