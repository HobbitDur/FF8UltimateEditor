"""Lossless MAG document and undo history, with cinematic instruction editing when present.

Content detection maps packed cinematics, TIMs, indexed containers, audio and undecoded parts.
All writes keep the byte size and preserve untouched data. Per-effect profiles describe native
opcode availability; scene simulation is restricted to the seven verified GF summons.
"""
import ntpath
import os
import struct
import re

from FF8GameData.magcine.cinescript import (CineOpcodeTable, CineProgram, decode_instruction,
                                            format_instruction)
from FF8GameData.magcine.cinesim import CineSimulation
from FF8GameData.magcine.magfile import MagFile

# GF name -> (magic effect id, mag file of the script)
CINEMATIC_GFS = {
    "Ifrit": (201, "MAG200_B.00"),
    "Leviathan": (6, "MAG005_B.00"),
    "Bahamut": (202, "MAG201_B.00"),
    "Cerberus": (203, "MAG202_B.00"),
    "Alexander": (204, "MAG203_B.00"),
    "Brothers": (205, "MAG204_B.00"),
    "Eden": (206, "MAG205_B.00"),
}


# Highest streamed part of each GF: battle/magNNN_b.02 .. .NN, loaded during the summon by
# script opcode 0x06 (the .00/.01 are loaded when it starts).
STREAMED_PART_LAST = {"Ifrit": 12, "Leviathan": 17, "Bahamut": 39, "Cerberus": 12, "Alexander": 15,
                      "Brothers": 11, "Eden": 56}


def streamed_part_names(gf):
    """{part number: file name} of the battle/magNNN_b.0k parts of a GF."""
    stem = CINEMATIC_GFS[gf][1][:-3].lower()  # "mag200_b"
    return {k: f"{stem}.{k:02d}" for k in range(2, STREAMED_PART_LAST[gf] + 1)}


def gf_from_file_name(path):
    name = ntpath.basename(path).upper()  # splits on both \ and / on every OS
    for gf, (_effect, file_name) in CINEMATIC_GFS.items():
        if name == file_name:
            return gf
    return ""


class MagDocument:
    HEADER_FIELDS = 12  # u32 pointer header

    def __init__(self):
        self.table = CineOpcodeTable.default()
        self.gf = ""
        self.file_path = ""
        self.data = bytearray()
        self.original = b""
        self.program = None
        self.document = MagFile(b"")
        self._undo = []  # data snapshots before each edit
        self._redo = []

    # ------------------------------------------------------------------ file
    def load_file(self, path, gf=""):
        with open(path, "rb") as f:
            raw = f.read()
        self.load_bytes(raw, gf or gf_from_file_name(path), name=ntpath.basename(path))
        self.file_path = path

    def load_bytes(self, raw, gf="", name=""):
        self.data = bytearray(raw)
        self.original = bytes(raw)
        self._undo.clear()
        self._redo.clear()
        self.gf = gf
        self.name = name
        match = re.match(r"mag(\d{3})(?:_|[.-])", name, re.IGNORECASE)
        self.effect_id = int(match[1])+1 if match else None
        self.table = CineOpcodeTable.for_effect(self.effect_id)
        self.file_path = ""
        self.analyse()

    def save_file(self, path=""):
        path = path or self.file_path
        if not path:
            raise ValueError("no file path")
        with open(path, "wb") as f:
            f.write(self.data)
        self.original = bytes(self.data)
        self.file_path = path

    @property
    def modified(self):
        return bytes(self.data) != self.original

    # ------------------------------------------------------------------ analysis
    @property
    def header(self):
        return self.document.header

    @property
    def root(self):
        return self.document.root

    @property
    def script_end(self):
        """The next mapped section boundary, which may be a camera before the sound table."""
        return self.document.script.end if self.document.script else 0

    def analyse(self):
        self.document = MagFile(self.data, getattr(self, "name", ""))
        self.program = (CineProgram(bytes(self.data[:self.script_end]), self.root, self.table)
                        if self.document.script else None)
        if self.program is not None and self.gf not in CINEMATIC_GFS:
            # A stub in the Ifrit-family table can be a real handler in another effect.
            # Stop at it rather than guessing a length or claiming the game would hang.
            for instruction in self.program.instructions.values():
                if instruction.error and instruction.opcode and not instruction.opcode.valid:
                    instruction.error = f"Opcode 0x{instruction.code:X}: this effect's variant is not decoded"
            self.program.errors = [(offset, self.program.instructions[offset].error
                                    if offset in self.program.instructions else message)
                                   for offset, message in self.program.errors]

    def simulate(self, seed=0, target_count=1, max_ticks=3000):
        if self.program is None:
            raise ValueError("This file has no validated cinematic script")
        if self.effect_id is not None and self.effect_id not in {effect for effect, _file in CINEMATIC_GFS.values()}:
            raise ValueError("Playback is verified only for the seven supported GF summons; this effect remains editable")
        return CineSimulation(bytes(self.data[:self.script_end]), self.root, max_ticks=max_ticks,
                              target_count=target_count, table=self.table, seed=seed)

    def unreached_ranges(self):
        """Byte ranges of the script region no reachable instruction covers: particle scripts,
        inline data and dead code (routines nothing references)."""
        covered = bytearray(len(self.data))
        if self.program is None:
            return []
        for instruction in self.program.instructions.values():
            covered[instruction.offset:instruction.offset + instruction.length] = b"\1" * instruction.length
        ranges = []
        offset, end = self.root, self.script_end
        while offset < end:
            if covered[offset]:
                offset += 1
                continue
            start = offset
            while offset < end and not covered[offset]:
                offset += 1
            ranges.append((start, offset))
        return ranges

    def linear_disassembly(self, start, end):
        """Disassemble [start, end) straight through (for unreached ranges): may be data."""
        result = []
        offset = start
        data = bytes(self.data)
        while offset < end:
            instruction = decode_instruction(data, offset, self.table)
            if instruction.error or instruction.length <= 0 or offset + instruction.length > end:
                break
            result.append(instruction)
            offset += instruction.length
        return result, offset

    def labels(self):
        """Readable names for every referenced offset: sub_/bone_/loc_/pfx_ + offset."""
        prefix = {"spawn": "bone", "code": "loc", "root": "root"}
        labels = {}
        if self.program is None:
            return labels
        for offset, kinds in self.program.entry_kinds.items():
            for kind in ("root", "spawn", "code"):
                if kind in kinds:
                    labels[offset] = f"{prefix[kind]}_{offset:04X}"
                    break
        for target, sources in self.program.xrefs.items():
            if target in labels:
                continue
            kinds = {kind for _source, kind in sources}
            if "particle" in kinds:
                labels[target] = f"pfx_{target:04X}"
            elif "data" in kinds:
                labels[target] = f"data_{target:04X}"
        for target, sources in self.program.xrefs.items():  # Call (0x03) targets are subroutines
            if any(self.program.instructions[source].code == 0x03 for source, kind in sources if kind == "code"):
                labels[target] = f"sub_{target:04X}"
        return labels

    def describe(self, instruction):
        opcode = instruction.opcode
        if opcode is None:
            return ""
        if not opcode.valid and self.gf not in CINEMATIC_GFS:
            return "Effect-specific variant not decoded. Inspect/edit the original bytes in Sections."
        text = opcode.semantics
        if opcode.gfs and self.gf in CINEMATIC_GFS and self.gf not in opcode.gfs:
            text = f"[NOT IMPLEMENTED IN {self.gf.upper()} - hangs the VM] " + text
        return text

    def format(self, instruction, labels=None):
        return format_instruction(instruction, labels if labels is not None else self.labels())

    # ------------------------------------------------------------------ editing
    def instruction_at(self, offset):
        return decode_instruction(bytes(self.data), offset, self.table)

    def replace_instruction(self, offset, op, words):
        """Overwrite the instruction at offset with (op, words). It must keep the same length -
        the new encoding's own length rule is checked too, so the stream stays decodable."""
        if self.program is None or not self.root <= offset < self.script_end:
            raise ValueError("The offset is outside the cinematic script")
        old = self.instruction_at(offset)
        if old.error and old.opcode is None:
            raise ValueError(f"no instruction at 0x{offset:X}")
        raw = struct.pack("<H", op & 0xFFFF) + b"".join(struct.pack("<H", w & 0xFFFF) for w in words)
        if len(raw) != old.length:
            raise ValueError(f"the instruction is {old.length} bytes, the new one {len(raw)}: "
                             "edits must keep the length (every jump is relative)")
        if offset+len(raw) > self.script_end:
            raise ValueError("The instruction crosses the script boundary")
        probe = bytearray(self.data)
        probe[offset:offset + len(raw)] = raw
        new = decode_instruction(bytes(probe), offset, self.table)
        if new.error:
            raise ValueError(new.error)
        if new.length != old.length:
            raise ValueError(f"with these modifier bits/operands opcode {new.name} is {new.length} bytes, "
                             f"not {old.length}: the edit would shift the following code")
        self._push_undo()
        self.data[offset:offset + len(raw)] = raw
        self.analyse()
        return new

    def patch_word(self, offset, value):
        """Raw 16-bit write (inline data, particle scripts...)."""
        self.patch_bytes(offset, struct.pack("<H", value & 0xFFFF))

    def patch_bytes(self, offset, raw):
        """Fixed-size write; refuses out-of-file writes and records one atomic undo step."""
        raw = bytes(raw)
        if offset < 0 or offset+len(raw) > len(self.data):
            raise ValueError("The edit is outside the file")
        if self.data[offset:offset+len(raw)] == raw:
            return False
        self._push_undo()
        self.data[offset:offset+len(raw)] = raw
        self.analyse()
        return True

    def replace_section(self, start, raw):
        section = next((s for s in self.document.sections if s.start == start), None)
        if section is None or len(raw) != section.size:
            raise ValueError("A section replacement must keep its exact byte size; offsets are not relocated")
        return self.patch_bytes(start, raw)

    def set_field(self, field, value):
        try:
            raw = struct.pack("<" + field.fmt, value)
        except struct.error as error:
            raise ValueError(f"Value does not fit {field.fmt}: {error}") from error
        return self.patch_bytes(field.offset, raw)

    def _push_undo(self):
        self._undo.append(bytes(self.data))
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(bytes(self.data))
        self.data = bytearray(self._undo.pop())
        self.analyse()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(bytes(self.data))
        self.data = bytearray(self._redo.pop())
        self.analyse()
        return True
