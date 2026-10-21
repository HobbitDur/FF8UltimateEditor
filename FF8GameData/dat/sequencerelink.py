"""Edit a byte-code sequence structurally: insert, remove or resize commands, then write it
back with every relative jump pointing at the same command as before.

A jump stores an offset relative to its own op code (FF8_EN.exe computeAnimationSequence
@0x50DB40), so inserting one byte anywhere moves every command after it and silently breaks
every jump across the insertion. Every tool that changes the length of a sequence (the
animation splitter, the 30 fps rewriter) has to recompute those offsets; this module is the
one place that does it.

The sequence is read into a list of SequenceNode. A jump node does not keep its offset, it
keeps a REFERENCE to the node it lands on (or to the end sentinel when it jumps exactly past
the last command). The list can then be edited freely; assemble_node_list() lays the nodes
out again and writes each jump's offset from where its target ended up. A one-byte jump
(E6-EC) whose new offset no longer fits a signed byte is promoted to its two-byte form
(ED-F3, op code + 7), which the engine runs identically - or refused when promotion is not
allowed.

Round trip: assemble_node_list(*parse_node_list(vm, data)) == data for every vanilla
sequence (tests/test_seq_rewrite30.py).
"""
from .sequencecommand import iter_command, get_jump_target, is_jump, is_jump_int16

_INT8_RANGE = (-128, 127)
_INT16_RANGE = (-32768, 32767)
JUMP_INT8_TO_INT16 = 7  # E6..EC -> ED..F3


class SequenceNode:
    """One command. `target` is the node a jump lands on (None for a non-jump), `origin` the
    address it was read from (None for a command inserted by an edit)."""
    __slots__ = ("op_code", "parameters", "target", "origin", "address")

    def __init__(self, op_code, parameters=b"", origin=None):
        self.op_code = op_code
        self.parameters = bytearray(parameters or b"")
        self.target = None
        self.origin = origin
        self.address = origin

    def is_jump(self) -> bool:
        return self.op_code is not None and is_jump(self.op_code)

    def copy(self):
        node = SequenceNode(self.op_code, self.parameters, None)
        node.target = self.target
        return node

    def size(self) -> int:
        if self.op_code is None:
            return 0
        if self.is_jump():
            return 1 + (2 if is_jump_int16(self.op_code) else 1)
        return 1 + len(self.parameters)

    def __repr__(self):
        if self.op_code is None:
            return "SequenceNode(END)"
        return f"SequenceNode(0x{self.op_code:02X}, [{self.parameters.hex(' ')}] @{self.address})"


class SequenceRelinkError(ValueError):
    """The sequence cannot be edited safely (unknown op code, jump leaving the sequence,
    jump that cannot be re-encoded)."""


def parse_node_list(vm, data: bytes):
    """(node list, end sentinel) of a sequence. Raises SequenceRelinkError when a jump does
    not land on a command of the sequence (or exactly at its end): editing such a sequence
    could not keep that jump meaningful."""
    data = bytes(data)
    node_list = []
    by_address = {}
    for address, op_code, parameters in iter_command(vm, data):
        if parameters is None:
            raise SequenceRelinkError(f"unknown op code 0x{op_code:02X} at offset {address}: "
                                      f"its size, so the rest of the sequence, is unknown")
        node = SequenceNode(op_code, parameters, address)
        node_list.append(node)
        by_address[address] = node
    end = SequenceNode(None, b"", len(data))
    for node in node_list:
        if not node.is_jump():
            continue
        target = get_jump_target(node.origin, node.op_code, node.parameters)
        if target == len(data):
            node.target = end
        elif target in by_address:
            node.target = by_address[target]
        else:
            raise SequenceRelinkError(f"the jump at offset {node.origin} lands on offset "
                                      f"{target}, which is not a command of this sequence")
    return node_list, end


def assemble_node_list(node_list, end, promote_jump: bool = True) -> bytearray:
    """The bytes of an edited node list, every jump re-pointed at its target node.

    A one-byte jump that no longer reaches is promoted to its two-byte form when
    promote_jump is True (it changes the layout, so the layout is recomputed until stable),
    else SequenceRelinkError is raised.
    """
    for _ in range(64):
        address = 0
        for node in node_list:
            node.address = address
            address += node.size()
        end.address = address
        changed = False
        for node in node_list:
            if node.target is None:
                continue
            offset = node.target.address - node.address
            if not is_jump_int16(node.op_code) and not _INT8_RANGE[0] <= offset <= _INT8_RANGE[1]:
                if not promote_jump:
                    raise SequenceRelinkError(f"jump offset {offset} does not fit in 1 byte(s)")
                node.op_code += JUMP_INT8_TO_INT16
                changed = True
        if not changed:
            break
    data = bytearray()
    for node in node_list:
        data.append(node.op_code)
        if node.is_jump():
            if node.target is None:
                raise SequenceRelinkError(f"jump 0x{node.op_code:02X} without a target")
            offset = node.target.address - node.address
            size = 2 if is_jump_int16(node.op_code) else 1
            low, high = _INT16_RANGE if size == 2 else _INT8_RANGE
            if not low <= offset <= high:
                raise SequenceRelinkError(f"jump offset {offset} does not fit in {size} byte(s)")
            data += offset.to_bytes(size, byteorder="little", signed=True)
        else:
            data += node.parameters
    return data


def insert_and_fix_jump(vm, data: bytes, insertion_dict: dict, promote_jump: bool = False) -> bytearray:
    """Insert raw bytes in a sequence and recompute every relative jump.

    insertion_dict maps an offset of the ORIGINAL data (a command start, or len(data)) to the
    bytes inserted before it. A jump that landed on that command still lands on it, AFTER the
    inserted bytes: the inserted code belongs to the command in front of it (the splitter
    inserts the parts of an animation right after the op code playing it, and a jump to the
    next command must not replay them).
    """
    node_list, end = parse_node_list(vm, data)
    by_origin = {node.origin: node for node in node_list}
    by_origin[len(bytes(data))] = end
    for offset in insertion_dict:
        if offset not in by_origin:
            raise SequenceRelinkError(f"offset {offset} is not the start of a command")
    new_list = []
    for node in node_list + [end]:
        inserted = insertion_dict.get(node.origin)
        if inserted:
            inserted_list, inserted_end = parse_node_list(vm, inserted)
            for inserted_node in inserted_list:
                if inserted_node.target is inserted_end:
                    inserted_node.target = node
            new_list.extend(inserted_list)
        if node is not end:
            new_list.append(node)
    return assemble_node_list(new_list, end, promote_jump)
