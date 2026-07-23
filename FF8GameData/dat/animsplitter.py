"""Split an animation too long for the file format into several ones played back to back.

An animation stores its frame count on one byte, so it cannot go over 255 frames. Adding
interpolated frames to reach 30 or 60 fps multiplies the count by 2 or 4, and the longest
animations then no longer fit. Splitting one long animation into shorter parts and making
the sequence play them one after the other keeps the same motion under the limit.

The parts share their boundary frame (part 1 ends on the frame part 2 starts with), so the
interpolation of each part covers the whole motion, including across the cut. Playing the
parts back to back therefore shows the original animation plus one repeated frame.

Rewriting the sequence is the delicate half:
- a bare op code < 0x80 pauses the sequence until the animation ends, so "XX" can simply
  become "XX Z1 Z2" and the parts play in a row;
- "A0 XX" does NOT pause the sequence: "A0 XX A0 Z1" would replace part 1 with part 2 on
  the same frame, so an animation played that way cannot be split this way (see
  can_split_animation);
- inserting bytes moves every following op code, so every relative jump of the sequence
  (E6/ED and the conditional ones) has to be recomputed, otherwise the loops of the
  sequence land in the middle of a parameter.

(FF8_EN.exe: AnimSeq_DispatchActionOpcode @0x504BB0, pre_Battle_ReadAnimation @0x509440
reads the frame count as a byte.)
"""
import copy

from . import interpolation
from .sequencecommand import (read_sequence_command_list, get_jump_target, is_jump,
                              is_jump_int16)

MAX_ANIMATION_FRAME = 255       # frame count is one byte
# Under Slow status the engine plays every frame twice and computes the frame count as
# 2 * nb_frame - 1 in an 8 bit register (FF8_EN.exe pre_Battle_ReadAnimation @0x509482:
# "shl cl, 1 / dec cl"). Over 128 frames that count wraps: a 137 frame animation gets
# 2*137-1 = 273 & 0xFF = 17 and stops almost immediately. Slow (and Haste) are only
# applied to the animation of the base sequence, ie. the looping idle stance
# (Battle_QueueAnimation @0x509520), so a loopable animation must stay under this.
MAX_SLOW_SAFE_ANIMATION_FRAME = 128
MAX_ANIMATION_ID = 0x7F         # a bare op code IS the animation id, so it stops at 0x7F
_INT8_RANGE = (-128, 127)
_INT16_RANGE = (-32768, 32767)


def get_max_frame_for_animation(can_be_slowed: bool, max_frame: int = MAX_ANIMATION_FRAME,
                                slow_doubles_frame_count: bool = True) -> int:
    """Longest an animation can be: the format limit, or the lower Slow-safe one.

    can_be_slowed is for the animations Slow status can reach, ie. the ones played by a
    base sequence (see animloopdetector.get_slowable_animation_id_set). A loop inside an
    attack sequence is never slowed and can use the whole format limit.
    slow_doubles_frame_count is the battle engine behaviour described on
    MAX_SLOW_SAFE_ANIMATION_FRAME; a model format without it (a field model) passes False.
    """
    if can_be_slowed and slow_doubles_frame_count:
        return min(max_frame, MAX_SLOW_SAFE_ANIMATION_FRAME)
    return max_frame


def get_converted_frame_count(nb_frame: int, factor: int, smooth_loop: bool) -> int:
    """Frame count once (factor - 1) frames are inserted between each pair of frames."""
    if smooth_loop:
        return nb_frame * factor
    return (nb_frame - 1) * factor + 1


def get_part_frame_count_list(nb_converted_frame: int, max_frame: int = MAX_ANIMATION_FRAME) -> list:
    """How many frames each part gets, cutting the CONVERTED animation in equal chunks.

    The animation is interpolated first and cut afterwards, so the parts are contiguous
    slices of the final frame stream: no frame is repeated and no interpolated frame is
    missing. Chaining the parts then plays exactly the frames of the unsplit animation,
    in the same number of ticks, because an animation of N frames occupies N ticks and
    the next one's frame 0 lands on the tick right after (the completion tick does not
    draw: FF8_EN.exe Battle_ReadAnimation @0x508F90 returns early, and the sequence
    queues the next animation in that same tick).
    """
    if nb_converted_frame <= max_frame:
        return [nb_converted_frame]
    nb_part = -(-nb_converted_frame // max_frame)  # ceil
    base = nb_converted_frame // nb_part
    remainder = nb_converted_frame % nb_part
    return [base + (1 if index < remainder else 0) for index in range(nb_part)]


def get_nb_part_needed(nb_frame: int, factor: int, smooth_loop: bool,
                       max_frame: int = MAX_ANIMATION_FRAME) -> int:
    """How many parts the animation must be cut into so every part fits once converted."""
    nb_converted = get_converted_frame_count(nb_frame, factor, smooth_loop)
    part_list = get_part_frame_count_list(nb_converted, max_frame)
    if any(nb < 2 for nb in part_list):
        return 0  # cannot be split small enough
    return len(part_list)


def can_split_animation(game_data, seq_animation_data: dict, animation_section,
                        anim_id: int, nb_part: int) -> tuple:
    """(True, "") when the animation can be split and the sequences rewritten.

    Returns (False, reason) otherwise: the reason is meant to be shown to the user.
    """
    nb_new_id = nb_part - 1
    if animation_section.nb_animations + nb_new_id - 1 > MAX_ANIMATION_ID:
        return False, (f"the file would need animation ids over {MAX_ANIMATION_ID}, which a "
                       f"sequence cannot play")

    sequence_list = seq_animation_data.get('seq_animation_data', []) if seq_animation_data else []
    if not sequence_list:
        return False, "the file has no animation sequence section to rewrite"

    played_somewhere = False
    for sequence in sequence_list:
        command_list = read_sequence_command_list(game_data, bytes(sequence['data']))
        for address, op_code, parameters in command_list:
            if parameters is None:
                return False, f"sequence {sequence['id']} has an op code that cannot be read"
            if op_code == 0xA0 and parameters and parameters[0] == anim_id:
                return False, (f"sequence {sequence['id']} plays it with A0 (without pausing "
                               f"the sequence), the parts cannot be chained there")
            if op_code == anim_id and op_code < 0x80:
                played_somewhere = True
        # A jump leaving its own sequence would be broken by any size change
        for address, op_code, parameters in command_list:
            target = get_jump_target(address, op_code, parameters)
            if target is not None and not 0 <= target < len(sequence['data']):
                return False, f"sequence {sequence['id']} jumps outside of itself"
    if not played_somewhere:
        return True, ""  # nothing plays it: split it, no sequence to rewrite
    return True, ""


def split_animation(animation_section, anim_id: int, max_frame: int = MAX_ANIMATION_FRAME) -> list:
    """Cut animation anim_id in parts of at most max_frame frames. Returns the new ids.

    The animation is cut as-is: interpolate it BEFORE calling this, so that the parts are
    contiguous slices of the final frame stream (see get_part_frame_count_list).
    The original animation keeps the first part and the other parts are appended at the
    end of the section, so existing animation ids — and every sequence naming them — stay
    valid.
    """
    animation = animation_section.animations[anim_id]
    part_frame_count_list = get_part_frame_count_list(len(animation.frames), max_frame)
    if len(part_frame_count_list) < 2:
        return []

    part_frame_list = []
    first = 0
    for nb_frame in part_frame_count_list:
        part_frame_list.append(animation.frames[first:first + nb_frame])
        first += nb_frame

    new_id_list = []
    for part_frames in part_frame_list[1:]:
        new_animation = type(animation)()
        new_animation.frames = [copy.deepcopy(frame) for frame in part_frames]
        new_animation.original_tail = b""
        new_animation._recompute_frame_storage_types()
        animation_section.animations.append(new_animation)
        new_id_list.append(animation_section.nb_animations)
        animation_section.nb_animations += 1

    animation.frames = part_frame_list[0]
    animation.original_tail = b""
    animation._recompute_frame_storage_types()
    return new_id_list


def rewrite_sequence_list_for_split(game_data, seq_animation_data: dict, anim_id: int,
                                    new_id_list: list) -> int:
    """Make every sequence playing anim_id play the new parts right after it.

    Returns how many places were rewritten. The relative jumps of each rewritten sequence
    are recomputed, since the inserted bytes move every following op code.
    """
    nb_rewritten = 0
    for sequence in seq_animation_data.get('seq_animation_data', []):
        data = bytes(sequence['data'])
        command_list = read_sequence_command_list(game_data, data)
        insertion_dict = {}
        for address, op_code, parameters in command_list:
            if op_code == anim_id and op_code < 0x80:
                # right after the op code playing the animation
                insertion_dict[address + 1] = bytes(new_id_list)
        if not insertion_dict:
            continue
        sequence['data'] = bytearray(_insert_and_fix_jump(data, command_list, insertion_dict))
        nb_rewritten += len(insertion_dict)
    return nb_rewritten


def split_and_convert_animation(game_data, animation_section, seq_animation_data, bones,
                                anim_id: int, factor: int, smooth_loop: bool,
                                max_frame: int = MAX_ANIMATION_FRAME,
                                mode: str = interpolation.LINEAR) -> dict:
    """Split animation anim_id so it fits, convert every part, and rewrite the sequences.

    `mode` is the interpolation curve of the inserted frames (FF8GameData/dat/interpolation.py).
    Returns {'new_id_list', 'nb_part', 'nb_frame_before', 'frame_count_list', 'nb_rewritten'}.
    Raises ValueError when it cannot be done (see can_split_animation).
    """
    animation = animation_section.animations[anim_id]
    nb_frame_before = len(animation.frames)
    nb_part = get_nb_part_needed(nb_frame_before, factor, smooth_loop, max_frame)
    if nb_part == 0:
        raise ValueError("the animation cannot be cut into parts small enough")
    if nb_part == 1:
        raise ValueError("the animation already fits, no need to split it")

    can_split, reason = can_split_animation(game_data, seq_animation_data, animation_section,
                                            anim_id, nb_part)
    if not can_split:
        raise ValueError(reason)

    # Interpolate the WHOLE animation first, then cut the result: the parts are then
    # contiguous slices of the final frame stream, so chaining them plays exactly the
    # frames of the unsplit animation — no frame repeated at the cut, none missing.
    animation.create_interpolated_frames(bones, factor, smooth_loop, mode=mode)
    new_id_list = split_animation(animation_section, anim_id, max_frame)
    part_id_list = [anim_id] + new_id_list

    nb_rewritten = rewrite_sequence_list_for_split(game_data, seq_animation_data, anim_id,
                                                   new_id_list)
    return {'new_id_list': new_id_list,
            'nb_part': nb_part,
            'nb_frame_before': nb_frame_before,
            'frame_count_list': [len(animation_section.animations[part_id].frames)
                                 for part_id in part_id_list],
            'nb_rewritten': nb_rewritten}


def _new_address(old_address: int, insertion_dict: dict) -> int:
    """Address of an op code once the bytes have been inserted."""
    return old_address + sum(len(inserted) for offset, inserted in insertion_dict.items()
                             if offset <= old_address)


def _insert_and_fix_jump(data: bytes, command_list: list, insertion_dict: dict) -> bytearray:
    """Insert bytes in a sequence and recompute every relative jump offset.

    insertion_dict maps an offset in the ORIGINAL data to the bytes to insert before it.
    """
    new_data = bytearray()
    jump_fix_list = []  # (offset of the parameter in new_data, op code, new offset value)

    for address, op_code, parameters in command_list:
        if address in insertion_dict:
            new_data.extend(insertion_dict[address])
        target = get_jump_target(address, op_code, parameters)
        new_data.append(op_code)
        if target is not None:
            new_offset = _new_address(target, insertion_dict) - _new_address(address, insertion_dict)
            jump_fix_list.append((len(new_data), op_code, new_offset))
            size = 2 if is_jump_int16(op_code) else 1
            new_data.extend(bytes(size))  # placeholder, written below
        elif parameters:
            new_data.extend(parameters)
    # bytes inserted at the very end of the sequence
    end_offset = len(data)
    if end_offset in insertion_dict:
        new_data.extend(insertion_dict[end_offset])

    for offset, op_code, new_offset in jump_fix_list:
        if is_jump_int16(op_code):
            low, high = _INT16_RANGE
            size = 2
        else:
            low, high = _INT8_RANGE
            size = 1
        if not low <= new_offset <= high:
            raise ValueError(f"jump offset {new_offset} does not fit in {size} byte(s) after "
                             f"the split")
        new_data[offset:offset + size] = new_offset.to_bytes(size, byteorder="little", signed=True)
    return new_data
