"""One command of a byte-code sequence, as an object instead of a slice of hex.

A sequence (entity animation section, or a camera section) is a flat byte-code program: op
code, then a parameter block whose length depends on the op code and sometimes on the
parameters themselves. Everything that wants to work with a sequence has to walk those
bytes exactly like the engine does, because the parameter length is what tells where the
next op code starts - read one byte too few and the rest of the sequence is garbage.

This module owns that walk, and wraps each command in a SequenceCommand so callers can ask
questions ("which animation does this play?", "where does this jump?") and edit a command
without touching hex. It is the counterpart of CommandAnalyser for the AI script section.

The walk lived in animloopdetector before, alongside a second, subtly different one inside
SequenceAnalyser. They disagreed on AB (see the entity VM's renzokuken_size), so a sequence
containing it was described one way by IfritSeq and read another way by the loop detector
and the splitter. There is now one walk, here, and the two others call it.

What is op-code-family-specific (the animation range, the FF-lists, sound, hit-effect,
Renzokuken, the C3/E5 tables) is NOT hard-coded here any more: it lives in a SequenceVM
(see sequencevm.py). The walk asks the VM. Every function below takes either a SequenceVM
or a GameData - as_sequence_vm() normalises a GameData to its entity VM, so the whole entity
code path (loop detector, splitter, Watts, the tests) keeps passing game_data unchanged; the
camera path passes a camera VM.

read_sequence()/write_sequence() round trip: for every sequence of every vanilla battle
file, write_sequence(read_sequence(data)) is data, byte for byte (see tests/test_seq_command.py).
"""
from .sequencevm import SequenceVM, as_sequence_vm

# The entity animation range, kept as a module constant for the callers that import it. The
# walk itself reads vm.animation_op_code_max so a camera VM (no animation range) is handled.
ANIMATION_OP_CODE_MAX = 0x80

_JUMP_OP_CODE_INT8 = (0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC)
_JUMP_OP_CODE_INT16 = (0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xF2, 0xF3)


def is_jump(op_code: int) -> bool:
    return op_code in _JUMP_OP_CODE_INT8 or op_code in _JUMP_OP_CODE_INT16


def is_jump_int16(op_code: int) -> bool:
    return op_code in _JUMP_OP_CODE_INT16


def get_jump_target(address: int, op_code: int, parameters) -> int:
    """Where a jump goes (op code address + signed offset). None when not a jump."""
    if not parameters:
        return None
    if op_code in _JUMP_OP_CODE_INT8:
        return address + int.from_bytes(parameters[:1], byteorder="little", signed=True)
    if op_code in _JUMP_OP_CODE_INT16:
        return address + int.from_bytes(parameters[:2], byteorder="little", signed=True)
    return None


def get_op_code_info(vm, op_code: int):
    """The json entry describing an op code. Animation op codes all share the 0x00 entry
    (on a VM with an animation range). vm may be a SequenceVM or a GameData."""
    return as_sequence_vm(vm).op_code_info(op_code)


def _op_code_size(vm: SequenceVM, op_code: int):
    return vm.op_code_size(op_code)


def iter_command(vm, sequence: bytes):
    """Yield (address, op_code, parameters) for each command of the sequence.

    The parameter length has to be computed exactly like the engine does, otherwise the
    next op code is read from the middle of a parameter and everything after is garbage.

    parameters is None on an unknown op code: its parameter size is unknown, so where the
    next op code starts is unknowable and the walk stops there.
    """
    vm = as_sequence_vm(vm)
    index = 0
    size_sequence = len(sequence)
    while index < size_sequence:
        address = index
        op_code = sequence[index]
        index += 1
        if op_code < vm.animation_op_code_max:  # Play animation (op code IS the id)
            yield address, op_code, b""
        elif op_code in vm.ff_list_ops:  # Parameter list ended by FF
            start = index
            if op_code in vm.ff_list_with_bone_ops:  # First parameter is the bone id
                index += 1
            while index < size_sequence and sequence[index] != 0xFF:
                index += 1
            index += 1
            yield address, op_code, sequence[start:index]
        elif op_code in vm.sound_ops:  # sound id, flag, and a channel mask if flag & 2
            start = index
            flag = sequence[index + 1] if index + 1 < size_sequence else 0
            index += 2
            if flag & 0x02:
                index += 1
            yield address, op_code, sequence[start:index]
        elif op_code in vm.hit_effect_ops:
            start = index
            flag = sequence[index + 1] if index + 1 < size_sequence else 0
            index += 2
            for bit in (0x01, 0x02, 0x04):
                if flag & bit:
                    index += 1
            if flag & 0x08:
                index += 1
            elif not flag & 0x10 and flag & 0x40:
                index += 6
            yield address, op_code, sequence[start:index]
        elif vm.renzokuken_op is not None and op_code == vm.renzokuken_op:
            # Renzokuken: two parameters, then plain op codes until A1. FF8_EN.exe
            # AnimSeq_DispatchActionOpcode @0x504bb0 case 0xAB reads *ptr, then ptr += 2.
            yield address, op_code, sequence[index:index + vm.renzokuken_size]
            index += vm.renzokuken_size
        else:
            size = _op_code_size(vm, op_code)
            if size is None:
                if op_code < 0xC0:
                    # Op code absent from the json AND from the engine: the dispatcher's
                    # default case (AnimSeq_DispatchActionOpcode @0x504bb0) returns without
                    # moving the pointer, so the engine treats it as a no-op and reads the
                    # next byte as the next op code. Do the same.
                    yield address, op_code, b""
                    continue
                # 0xC0+ op code the VM does not know (F4-FF): computeAnimationSequence
                # @0x50db40 hits 'default: continue' WITHOUT advancing, i.e. the engine
                # hangs on it. There is no defined size, stop rather than guess.
                yield address, op_code, None
                return
            yield address, op_code, sequence[index:index + size]
            index += size


def read_sequence_command_list(vm, sequence: bytes) -> list:
    """[(address, op_code, parameters)] of a sequence, in byte order.

    parameters is None on an unknown op code: the parameter size is what tells where the
    next op code starts, so the rest of the sequence cannot be read.
    """
    return list(iter_command(vm, sequence))


class SequenceCommand:
    """One command: an op code, its parameter bytes, and where it starts in the sequence.

    address is where the command was read from. It is a reading aid, not identity: inserting
    a command moves every following one, and write_sequence() does not use it.
    """

    def __init__(self, vm, op_code: int, parameters=b"", address: int = 0,
                 unknown_tail: bytes = b""):
        # vm may be a SequenceVM or a GameData (normalised to the entity VM). Kept as .vm so
        # the analyser and codec can decode this command with the right op code family.
        self.vm = as_sequence_vm(vm)
        self.op_code = op_code
        # None means "unknown op code, parameters unreadable" and is kept as such: guessing
        # a size here is what silently shifts the rest of the sequence.
        self.parameters = None if parameters is None else bytearray(parameters)
        self.address = address
        # Bytes that could not be read because this command's size is unknown. Only ever set
        # on the last command of a sequence, so a file the tool cannot fully parse still
        # round trips instead of being truncated on save.
        self.unknown_tail = bytearray(unknown_tail)

    def __eq__(self, other):
        if not isinstance(other, SequenceCommand):
            return NotImplemented
        return (self.op_code == other.op_code and self.parameters == other.parameters
                and self.unknown_tail == other.unknown_tail)

    def __repr__(self):
        parameters = "None" if self.parameters is None else self.parameters.hex(" ")
        return f"SequenceCommand(0x{self.op_code:02X}, [{parameters}] @0x{self.address:X})"

    def is_unknown(self) -> bool:
        return self.parameters is None

    def is_animation(self) -> bool:
        """Op codes < the VM's animation range play the animation whose id is the op code
        itself. Always False on the camera VM."""
        return self.vm.is_animation(self.op_code)

    def get_animation_id(self):
        """The animation this command plays, or None when it plays none.

        Both spellings are covered: a bare op code (play once, the sequence waits for it)
        and A0 XX (queue animation XX and keep going, which the engine re-queues on its own
        when it ends - a loop).
        """
        if self.is_animation():
            return self.op_code
        if self.vm.async_anim_op_code is not None \
                and self.op_code == self.vm.async_anim_op_code and self.parameters:
            return self.parameters[0]
        return None

    def get_op_code_info(self):
        return self.vm.op_code_info(self.op_code)

    def get_size(self) -> int:
        """How many bytes this command takes in the sequence, op code included."""
        return 1 + len(self.parameters or b"") + len(self.unknown_tail)

    def to_bytes(self) -> bytearray:
        data = bytearray([self.op_code])
        if self.parameters:
            data += self.parameters
        data += self.unknown_tail
        return data

    def is_jump(self) -> bool:
        return is_jump(self.op_code)

    def get_jump_target(self):
        """The address this command jumps to, or None when it is not a jump."""
        return get_jump_target(self.address, self.op_code, self.parameters)

    def set_jump_target(self, target: int):
        """Point a jump at `target`, an address in the same sequence.

        The offset the engine reads is relative to the op code's own address, so a command
        that has moved must have its address updated first (write_sequence does it).
        """
        if not self.is_jump():
            raise ValueError(f"op code 0x{self.op_code:02X} is not a jump")
        size = 2 if is_jump_int16(self.op_code) else 1
        offset = target - self.address
        self.parameters[:size] = (offset).to_bytes(size, byteorder="little", signed=True)


def default_parameters(vm, op_code: int) -> bytearray:
    """The smallest valid parameter block for an op code (what a freshly inserted or
    just-switched command starts with). Variable-size op codes get their minimal form:
    an empty FF-terminated list, a sound with no channel mask, a hit effect with no
    optional byte."""
    vm = as_sequence_vm(vm)
    if vm.is_animation(op_code):
        return bytearray()
    if op_code in vm.ff_list_with_bone_ops:
        return bytearray([0x00, 0xFF])  # bone 0, empty list
    if op_code in vm.ff_list_ops:
        return bytearray([0xFF])  # empty list
    if op_code in vm.sound_ops or op_code in vm.hit_effect_ops:
        return bytearray([0x00, 0x00])  # id, flags without any optional byte
    if vm.renzokuken_op is not None and op_code == vm.renzokuken_op:
        return bytearray(vm.renzokuken_size)
    size = vm.op_code_size(op_code)
    if size is None or size < 0:
        return bytearray()
    return bytearray(size)


def normalize_parameters(vm, op_code: int, parameters) -> bytearray:
    """Make a parameter block self-consistent with its op code.

    The size of some op codes depends on their own parameters (a sound's flag bit 1 adds
    a channel-mask byte, a hit effect's flag bits add up to 6 bytes, an FF list runs to
    its terminator). After an edit the block must be padded/truncated to what the engine
    will actually consume, otherwise the next command starts inside or after leftover
    parameter bytes. This is the ONLY place that arithmetic lives outside iter_command -
    the two are kept consistent by tests/test_seq_command.py.
    """
    vm = as_sequence_vm(vm)
    block = bytearray(parameters or b"")
    if vm.is_animation(op_code):
        return bytearray()
    if op_code in vm.ff_list_with_bone_ops:
        if not block:
            block.append(0x00)  # bone id
        body = block[1:]
        if 0xFF in body:
            body = body[:body.index(0xFF) + 1]
        else:
            body.append(0xFF)
        return bytearray([block[0]]) + body
    if op_code in vm.ff_list_ops:
        if 0xFF in block:
            return block[:block.index(0xFF) + 1]
        block.append(0xFF)
        return block
    if op_code in vm.sound_ops:
        while len(block) < 2:
            block.append(0x00)
        needed = 3 if block[1] & 0x02 else 2
        while len(block) < needed:
            block.append(0x00)
        return block[:needed]
    if op_code in vm.hit_effect_ops:
        while len(block) < 2:
            block.append(0x00)
        flags = block[1]
        needed = 2 + bin(flags & 0x07).count("1")
        if flags & 0x08:
            needed += 1
        elif not flags & 0x10 and flags & 0x40:
            needed += 6
        while len(block) < needed:
            block.append(0x00)
        return block[:needed]
    if vm.renzokuken_op is not None and op_code == vm.renzokuken_op:
        while len(block) < vm.renzokuken_size:
            block.append(0x00)
        return block[:vm.renzokuken_size]
    size = vm.op_code_size(op_code)
    if size is None:
        return bytearray() if op_code < 0xC0 else block  # engine no-op / undecodable
    if size < 0:  # a variable-size op code not special-cased above should not exist
        return block
    while len(block) < size:
        block.append(0x00)
    return block[:size]


def read_sequence(vm, sequence: bytes) -> list:
    """[SequenceCommand] of a sequence, in byte order.

    An unknown op code ends the walk (its size, so where the next command starts, is
    unknown). Whatever follows is kept on that last command as unknown_tail, so the
    sequence still round trips through write_sequence().
    """
    vm = as_sequence_vm(vm)
    command_list = []
    for address, op_code, parameters in iter_command(vm, sequence):
        command = SequenceCommand(vm, op_code, parameters, address)
        if parameters is None:  # Walk stopped here: keep the rest verbatim
            command.unknown_tail = bytearray(sequence[address + 1:])
            command_list.append(command)
            return command_list
        command_list.append(command)
    return command_list


def write_sequence(command_list) -> bytearray:
    """The bytes of a list of commands, refreshing each command's address as it goes.

    Addresses are recomputed rather than trusted so that a command list that was edited
    (inserted, removed, reordered) writes out coherently. Jump offsets are NOT recomputed
    here: inserting a command shifts every following op code, so the jumps of an edited
    sequence have to be retargeted by whoever made the edit and knows what each jump
    meant - see animsplitter, which already does exactly that when it cuts an animation.
    """
    data = bytearray()
    for command in command_list:
        command.address = len(data)
        data += command.to_bytes()
    return data
