"""Which animations a battle actor plays, read from its dat sequences without running them: its
idle loop, and what its action sequence plays before and while an effect runs (the cast). For
previews that play animations directly (Fujin's effect preview).

The engine drives every actor with its animation sequences (dat section 5, see
FF8GameData.dat.sequencecommand; a character's are in its weapon file), numbered from 1. Its idle
is the loop of sequence 1 ("A3 00 E6 FF": animation 0). (The battle opens on sequence 8, the
entrance: a character's binds its body's section 7 - one entrance animation - and its "AC 00"
restores the normal animations of section 3 afterwards.)

A Magic cast runs sequence 11 for a character (computeCommandAction 0x48D200: byte_B8150C[command],
11 for Magic 2). The sequence and BattleActionSequence_Tick_MagicCast 0x50A9A0 talk through the
actor's state flags (C3 08 / E5 08): 0x10 = the effect's files are loaded, the sequence sets 0x20 to
start the effect, 0x200 = the effect is over. Squall's: animations 18 and 19, 19 looped until
0x10, 20 for 13 frames, sets 0x20 (the effect starts), 20 for 3 more, 21 looped until 0x200, then
22 and 9 back to his stance.

cast_plan interprets that path - animations played once (the sequence waits for them), A0 (loop
one and go on), A1 (one frame), B9 (wait), the value opcodes C0-E3 (set / + / - / * / / / and / or
/ xor of an int16, int8, uint8 or variable), E5 (store), the jumps E6-F3 - with the files loaded at
once, and splits it where the sequence starts the effect. Special reads other than the state
flags read 0 (sequence 1's base sequence check reads 1); anything else is stepped over.
"""
import struct

from FF8GameData.dat.sequencecommand import get_jump_target, iter_command

# dat section holding the animation sequences / the model animations, by section count
SEQUENCE_SECTION = {11: 5, 10: 6, 8: 4, 5: 2}       # monster, Edea, weapon, reduced weapon (Zell, Kiros)
ANIMATION_SECTION = {11: 3, 10: 3, 8: 3, 7: 3}      # monster, Edea, weapon, character body
MAGIC_SEQUENCE, BASE_SEQUENCE = 11, 1
STATE_FLAGS = 0x08                                  # C3 08 / E5 08: the actor's state flags
LOADED, START_EFFECT, EFFECT_OVER = 0x10, 0x20, 0x200
END, TERMINATE = 0xA2, 0xA9
_JUMP_CONDITION = {0xE6: lambda v: True, 0xE7: lambda v: v > 0, 0xE8: lambda v: v >= 0, 0xE9: lambda v: v == 0,
                   0xEA: lambda v: v != 0, 0xEB: lambda v: v <= 0, 0xEC: lambda v: v < 0}
_JUMP_CONDITION.update({op + 7: test for op, test in list(_JUMP_CONDITION.items())})   # ED-F3: int16 offsets


def _section(data, number):
    """The bytes of dat section `number` (1-based), or b"" when the file has none."""
    try:
        count = struct.unpack_from("<I", data, 0)[0]
        if not 1 <= number <= count or count > 64:
            return b""
        start = struct.unpack_from("<I", data, 4 * number)[0]
        end = struct.unpack_from("<I", data, 4 * (number + 1))[0] if number < count else len(data)
        return data[start:max(start, min(end, len(data)))]
    except struct.error:
        return b""


def _section_count(data):
    try:
        return struct.unpack_from("<I", data, 0)[0]
    except struct.error:
        return 0


def read_sequences(path):
    """{sequence id (1-based): bytes} of a dat file (a weapon for a character), {} without any."""
    try:
        with open(path, "rb") as file:
            data = file.read()
    except OSError:
        return {}
    section = _section(data, SEQUENCE_SECTION.get(_section_count(data), 0))
    if len(section) < 2:
        return {}
    count = struct.unpack_from("<H", section, 0)[0]
    offsets = [struct.unpack_from("<H", section, 2 + 2 * index)[0] for index in range(count)
               if 2 + 2 * index + 2 <= len(section)]
    sequences = {}
    for index, offset in enumerate(offsets):
        if not offset:
            continue
        ends = [other for other in offsets if other > offset]
        sequences[index + 1] = bytes(section[offset:min(ends) if ends else len(section)])
    return sequences


def read_frame_counts(path):
    """[frame count] of each model animation of a dat file (the animation ids sequences play)."""
    try:
        with open(path, "rb") as file:
            data = file.read()
    except OSError:
        return []
    section = _section(data, ANIMATION_SECTION.get(_section_count(data), 0))
    try:
        count = struct.unpack_from("<I", section, 0)[0]
        return [section[struct.unpack_from("<I", section, 4 + 4 * index)[0]] for index in range(min(count, 255))]
    except (struct.error, IndexError):
        return []


def _loop_animation(vm, sequence):
    """The animation a sequence ends looping on (a backward E6 jump onto an animation), or None."""
    commands = list(iter_command(vm, sequence))
    by_address = {address: op_code for address, op_code, _parameters in commands}
    loop = None
    for address, op_code, parameters in commands:
        if parameters is None:
            break
        if op_code == 0xE6:
            target = get_jump_target(address, op_code, parameters)
            if target is not None and target <= address and by_address.get(target, 0xFF) < vm.animation_op_code_max:
                loop = by_address[target]
    return loop


def idle_animation(vm, sequences):
    """The animation an actor loops when nothing happens: sequence 1's loop, 0 without one."""
    loop = _loop_animation(vm, sequences.get(BASE_SEQUENCE, b""))
    return 0 if loop is None else loop


def cast_plan(vm, sequences, frame_counts, sequence_id=MAGIC_SEQUENCE, max_ticks=150):
    """(before, during): [(animation, ticks)] the actor plays from the start of its action sequence
    to the start of the effect, and from there while the effect runs - its last entry has 0 ticks
    when the sequence loops it until the effect is over. ([], []) when the sequence is missing."""
    sequence = sequences.get(sequence_id, b"")
    commands = list(iter_command(vm, sequence))
    index_of = {address: index for index, (address, _op, _parameters) in enumerate(commands)}
    before, during = [], []
    plan = before
    playing, value, variables = None, 0, {STATE_FLAGS: LOADED, 0x0B: BASE_SEQUENCE}
    started, index, steps, ticks = False, 0, 0, 0

    def spend(animation, count):
        nonlocal ticks
        count = min(count, max_ticks - ticks)
        if animation is None or count <= 0:
            return
        if plan and plan[-1][0] == animation:
            plan[-1] = (animation, plan[-1][1] + count)
        else:
            plan.append((animation, count))
        ticks += count

    while 0 <= index < len(commands) and steps < 5000 and ticks < max_ticks:
        steps += 1
        address, op_code, parameters = commands[index]
        index += 1
        if parameters is None or op_code in (END, TERMINATE):
            break
        if op_code < vm.animation_op_code_max:                  # played once, the sequence waits for it
            playing = op_code
            spend(op_code, max(1, frame_counts[op_code] if op_code < len(frame_counts) else 1))
        elif op_code == 0xA0 and parameters:                    # loop an animation, go on
            playing = parameters[0]
        elif op_code == 0xA1:                                   # one frame
            spend(playing, 1)
        elif op_code == 0xB9 and parameters:                    # wait n - 1 frames
            spend(playing, max(0, parameters[0] - 1))
        elif 0xC0 <= op_code <= 0xDF:                           # the value
            kind, family = op_code & 3, op_code & 0xFC
            if kind == 0:
                operand = int.from_bytes(parameters[:2], "little", signed=True)
            elif kind == 1:
                operand = int.from_bytes(parameters[:1], "little", signed=True)
            elif kind == 2:
                operand = parameters[0] if parameters else 0
            else:
                operand = variables.get(parameters[0], 0) if parameters else 0
            if family == 0xC0:
                value = operand
            elif family == 0xC4:
                value += operand
            elif family == 0xC8:
                value -= operand
            elif family == 0xCC:
                value *= operand
            elif family == 0xD0:
                value = int(value / operand) if operand else value
            elif family == 0xD4:
                value &= operand
            elif family == 0xD8:
                value |= operand
            elif family == 0xDC:
                value ^= operand
        elif op_code == 0xE5 and parameters:                    # store
            variables[parameters[0]] = value
            if parameters[0] == STATE_FLAGS and value & START_EFFECT and not started:
                started, plan = True, during                    # the effect starts here
        elif op_code in _JUMP_CONDITION:
            target = get_jump_target(address, op_code, parameters)
            if target in index_of and _JUMP_CONDITION[op_code](value):
                if started and target < address and during and during[-1][1] >= 30:
                    break                                       # waiting for the effect to end
                index = index_of[target]
    if started and during:
        during[-1] = (during[-1][0], 0) if during[-1][1] >= 30 else during[-1]
    return (before, during) if started else (before, [])
