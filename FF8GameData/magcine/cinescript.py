"""Script byte-code of the GF cinematic engine (Ifrit, Leviathan, Bahamut, Cerberus, Alexander,
Brothers, Eden summons).

A script is a stream of little-endian 16-bit words. The low 9 bits of an instruction's first word
pick the opcode (0x000-0x146); the high 7 bits are per-opcode modifiers (component mask, wait
count, sub-op...). Operands follow as 16-bit words and the instruction length depends on the
opcode and sometimes on those modifier bits or on an operand (inline data blocks). Every jump,
call and "start a script" offset is relative to the instruction's first word.

The opcode table lives in Resources/json/gf_cinematic_opcodes.json (decoded from FF8_EN.exe, all
seven GFs share the numbering; a dozen opcodes only exist in some of them - `gfs`).

Qt-free: used by the Laguna tool and the CLI.
"""
import json
import os
import struct
from dataclasses import dataclass, field

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

_SPEC_PATH = str(RESOURCES_JSON_FOLDER / "gf_cinematic_opcodes.json")


def popcount(value: int) -> int:
    return bin(value & 0xFFFFFFFF).count("1")


class CineOpcode:
    """One opcode of the table, with its length rule and stream references compiled."""

    def __init__(self, code: int, data: dict):
        self.code = code
        self.name = data["name"]
        self.operands = data["operands"]
        self.high_bits = data.get("high_bits", "")
        self.flow = data["flow"]
        self.semantics = data["semantics"]
        self.confidence = data.get("confidence", "")
        self.notes = data.get("notes", "")
        self.gfs = data.get("gfs")  # None = every GF
        self.fallthrough = data.get("fallthrough", True)
        self.length_expr = data["length"]
        self._length = compile(self.length_expr, f"<len 0x{code:X}>", "eval")
        self.refs = []
        for ref in data.get("refs", []):
            cond = ref.get("cond")
            self.refs.append((ref["word"], ref["kind"], ref.get("base", "op"), ref.get("size", 0),
                              compile(cond, "<cond>", "eval") if cond else None))

    @property
    def valid(self) -> bool:
        return self.flow not in ("invalid", "hang")

    def length(self, op: int, words: list) -> int:
        return int(eval(self._length, {"popcount": popcount}, {"op": op, "w": words}))

    def references(self, op: int, offset: int, words: list):
        """Absolute file offsets this instruction points to: [(kind, target, operand word index)]."""
        out = []
        for word, kind, base, _size, cond in self.refs:
            if cond is not None and not eval(cond, {}, {"op": op}):
                continue
            if word >= len(words):
                continue
            origin = offset if base == "op" else offset + 2  # "word0" = the first operand word
            out.append((kind, origin + words[word], word))
        return out


class CineOpcodeTable:
    _cache = None

    def __init__(self, path: str = _SPEC_PATH):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.gf_order = data["gf_order"]
        self.opcodes = {int(k, 16): CineOpcode(int(k, 16), v) for k, v in data["opcodes"].items()}

    @classmethod
    def default(cls) -> "CineOpcodeTable":
        if cls._cache is None:
            cls._cache = CineOpcodeTable()
        return cls._cache

    def get(self, code: int):
        return self.opcodes.get(code)


@dataclass
class CineInstruction:
    offset: int              # absolute offset in the file
    op: int                  # full first word
    words: list              # following words (signed), len = (length-2)/2
    opcode: CineOpcode = None
    refs: list = field(default_factory=list)  # [(kind, target, word index)]
    error: str = ""

    @property
    def code(self) -> int:
        return self.op & 0x1FF

    @property
    def modifier(self) -> int:
        return self.op >> 9

    @property
    def length(self) -> int:
        return 2 + 2 * len(self.words)

    @property
    def name(self) -> str:
        return self.opcode.name if self.opcode else f"Op{self.code:03X}"

    def raw(self) -> bytes:
        return struct.pack("<H", self.op) + b"".join(struct.pack("<h", w) for w in self.words)


MAX_OPERAND_WORDS = 64  # longest legit instruction is an inline block (0x43/0x44/0x4E, 0x1A)


def decode_instruction(data: bytes, offset: int, table: CineOpcodeTable = None) -> CineInstruction:
    table = table or CineOpcodeTable.default()
    if offset + 2 > len(data):
        return CineInstruction(offset, 0, [], None, error="past end of file")
    op = struct.unpack_from("<H", data, offset)[0]
    opcode = table.get(op & 0x1FF)
    avail = min(MAX_OPERAND_WORDS + 16, (len(data) - offset - 2) // 2)
    lookahead = list(struct.unpack_from(f"<{avail}h", data, offset + 2)) if avail > 0 else []
    if opcode is None:
        return CineInstruction(offset, op, [], None, error=f"unknown opcode 0x{op & 0x1FF:X}")
    try:
        length = opcode.length(op, lookahead)
    except Exception as exc:  # malformed operand for a variable-length rule
        return CineInstruction(offset, op, [], opcode, error=f"length rule failed: {exc}")
    count = (length - 2) // 2
    if length < 2 or length % 2 or count > len(lookahead):
        return CineInstruction(offset, op, [], opcode, error=f"bad length {length}")
    words = lookahead[:count]
    instruction = CineInstruction(offset, op, words, opcode)
    if not opcode.valid:
        instruction.error = f"opcode 0x{instruction.code:X} is not implemented (would hang the VM)"
    instruction.refs = opcode.references(op, offset, words)
    return instruction


@dataclass
class CineBlock:
    """A run of instructions reached from one entry point, in address order."""
    start: int
    kind: str                       # root / code / spawn
    instructions: list = field(default_factory=list)
    entries: set = field(default_factory=set)  # every offset of this block that is jumped to/spawned

    @property
    def end(self) -> int:
        return self.instructions[-1].offset + self.instructions[-1].length if self.instructions else self.start


class CineProgram:
    """Every script reachable from the root program, found by following jumps, calls, spawns
    and fall-through (a recursive-descent disassembly, so inline data is never read as code)."""

    def __init__(self, data: bytes, root: int, table: CineOpcodeTable = None):
        self.data = data
        self.root = root
        self.table = table or CineOpcodeTable.default()
        self.instructions = {}      # offset -> CineInstruction
        self.entry_kinds = {}       # offset -> set of kinds (root/code/spawn)
        self.particle_scripts = set()
        self.data_blocks = {}       # offset -> size
        self.errors = []            # (offset, message)
        self.xrefs = {}             # target -> [(source offset, kind)]
        self._walk()

    def _walk(self):
        todo = [(self.root, "root")]
        while todo:
            offset, kind = todo.pop()
            self.entry_kinds.setdefault(offset, set()).add(kind)
            while offset not in self.instructions:
                if offset < 0 or offset + 2 > len(self.data):
                    self.errors.append((offset, "reference outside the file"))
                    break
                instruction = decode_instruction(self.data, offset, self.table)
                self.instructions[offset] = instruction
                if instruction.error:
                    self.errors.append((offset, instruction.error))
                    break
                for ref_kind, target, _word in instruction.refs:
                    self.xrefs.setdefault(target, []).append((offset, ref_kind))
                    if ref_kind in ("code", "spawn"):
                        todo.append((target, ref_kind))
                    elif ref_kind == "particle":
                        self.particle_scripts.add(target)
                    elif ref_kind == "data":
                        self.data_blocks[target] = 12
                if not instruction.opcode.fallthrough:
                    break
                offset += instruction.length

    def sorted_instructions(self):
        return [self.instructions[o] for o in sorted(self.instructions)]

    def code_span(self):
        offsets = sorted(self.instructions)
        return (offsets[0], self.instructions[offsets[-1]].offset + self.instructions[offsets[-1]].length) \
            if offsets else (self.root, self.root)

    def blocks(self):
        """Contiguous runs of decoded instructions; a new block starts after an instruction without
        fall-through or at a gap."""
        result = []
        current = None
        for instruction in self.sorted_instructions():
            if current is None or instruction.offset != current.end:
                kinds = self.entry_kinds.get(instruction.offset, {"code"})
                current = CineBlock(instruction.offset, _main_kind(kinds))
                result.append(current)
            if instruction.offset in self.entry_kinds:
                current.entries.add(instruction.offset)
            current.instructions.append(instruction)
            if not instruction.opcode or not instruction.opcode.fallthrough:
                current = None
        return result


def _main_kind(kinds):
    for kind in ("root", "spawn", "code"):
        if kind in kinds:
            return kind
    return "code"


COMPONENTS = ["RotX", "RotY", "RotZ", "PosX", "PosY", "PosZ"]
GENERIC_WRITES = set(range(0x0A, 0x18))  # component mask in bits 15..10, one word per component
_ALL_COMPONENT_WRITES = {0x0D, 0x0E, 0x0F, 0x16}   # one value for every masked component
_FLAG_SUBOPS = {0: "Set", 1: "Clear", 2: "JumpIfAny", 3: "JumpIfNone", 4: "WaitWhileAny", 5: "WaitUntilAny"}
_CAMERA_SUBOPS = {0: "Camera", 1: "StageCameraAnim", 2: "ClaimVoice", 3: "StopVoices", 4: "SaveReturnView",
                  5: "Sub504270On", 6: "Sub504270On", 7: "Sub504270Off",
                  8: "ArmCameraReturn"}


def format_instruction(instruction: CineInstruction, labels: dict = None) -> str:
    """One-line text form, e.g. `Wait 16`, `SetVel PosX=-2048`, `FlagOp.Set 0x1000`,
    `SpawnBone @bone_01CA`, or `Name.modifier a, b` for the opcodes without a special form
    (modifier = op >> 9, in hex)."""
    labels = labels or {}
    code, op, words = instruction.code, instruction.op, instruction.words
    ref_words = {word: (kind, target) for kind, target, word in instruction.refs}

    def arg(index):
        if index in ref_words:
            return "@" + labels.get(ref_words[index][1], f"{ref_words[index][1]:05X}")
        return str(words[index])

    name = instruction.name
    if code == 0x09:
        return f"{name} {op >> 9}"
    if code in (0x05, 0x10C):
        sub = (op >> 12) & 0xF
        rest = ", ".join(arg(i) for i in range(1, len(words)))
        return f"{name}.{_FLAG_SUBOPS.get(sub, sub)} 0x{words[0] & 0xFFFF:X}" + (f", {rest}" if rest else "")
    if code == 0x39:
        sub = op >> 12
        return f"{name}.{_CAMERA_SUBOPS.get(sub, sub)} {words[0]}"
    if code in GENERIC_WRITES:
        mask = (op >> 10) & 0x3F
        components = [COMPONENTS[i] for i in range(6) if mask & (0x20 >> i)]
        if code in _ALL_COMPONENT_WRITES:
            return f"{name} {'+'.join(components) or '-'}={words[0] if words else '?'}"
        if code == 0x17:  # base, spread pairs
            pairs = [f"{c}={words[2 * i]}~{words[2 * i + 1]}" for i, c in enumerate(components) if 2 * i + 1 < len(words)]
            return f"{name} " + " ".join(pairs)
        values = [f"{c}={'keep' if (w & 0xFFFF) == 0x7654 else w}" for c, w in zip(components, words)]
        return f"{name} " + " ".join(values)
    args = [arg(i) for i in range(len(words))]
    modifier = f".{instruction.modifier:X}" if instruction.modifier else ""
    return f"{name}{modifier}" + (" " + ", ".join(args) if args else "")
