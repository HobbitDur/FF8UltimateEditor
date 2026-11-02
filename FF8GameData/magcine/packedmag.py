"""One packed MAG file (MAGxxx_B.00 / .01, the streamed battle/magxxx_b.0k): its parts, every
offset that points into it, and resizing a part with all of those offsets kept right.

The parts themselves are read by the specialised readers - MagFile (section map), MagContainer
(objects, meshes, models), magsound (sound blocks, controller vibration), cinescript (the
cinematic script) - and PackedMag gathers them behind one object. What only PackedMag knows is
the pointer map, which lets a part grow or shrink in place.

Every offset the game follows into a packed file, decoded from FF8_EN.exe:
  - header u32 +0x04..+0x24 (script, CLUT table, object table, sound table, texture table, music
    table, end of tables, stage camera, controller vibration bank), file-relative, 0 = absent.
    The effect code reads +0x04, +0x18, +0x20, +0x24 of the .00 and +0x1C of the .01 (all 46 copies
    of the cinematic engine) and never a fixed offset past the header;
  - texture / CLUT / music table entries: low 24 bits relative to their own table, high byte flags;
  - object table: u32 count, then u32 offsets relative to the table (GfCinematic_GetObjectPtr
    0xB657E0), 0 = not in this file;
  - sprite frame lists: s32 frame offsets relative to the object table (classified by shape, so
    PackedMag refuses to rewrite one rather than trust the guess);
  - sound table: u32 offsets relative to the table, count = first offset / 4;
  - vibration bank: u32 offsets relative to the bank, the table ends at the first pattern;
  - the script: every jump/call/spawn/particle reference is a s16 relative to its instruction.
    Two opcodes hold raw file positions instead: 0x29 bit14 (VRAM upload from file slot + 4 KB
    page) and 0x06 (stream a file into slot + 4 KB page, or slot + an exe descriptor offset).
    A position past a resized part, or an exe descriptor offset into this file, cannot be updated:
    PackedMag refuses the resize then. No vanilla camera file has either.
Inside meshes, models, camera tracks and vibration patterns every offset is relative to the part.

The files of an effect are loaded one after the other at the start of the 1 MB magic buffer
(IO_GetFile_MAGIC 0x571B80, cursor reset by Magic_ClearMemoryForTex): a bigger .00 only pushes the
.01 further. Script opcode 0x21 (bit15 clear) puts work buffers at fixed positions of that buffer,
so the loaded files must end before the lowest one (`work_buffer_floor`).
"""
import struct
from dataclasses import dataclass

from FF8GameData.magcine.cinescript import CineOpcodeTable, CineProgram, decode_instruction
from FF8GameData.magcine.magcontainer import MagContainer
from FF8GameData.magcine.magfile import MagFile
from FF8GameData.magcine import magsound

HEADER_SIZE = 0x30
MAGIC_BUFFER_SIZE = 0x100000
# header u32 index -> name, for the file-relative offsets (index 0, 10, 11 are unused)
HEADER_POINTERS = {1: "script", 2: "CLUT table", 3: "object table", 4: "sound table", 5: "texture table",
                   6: "music table", 7: "end of tables", 8: "stage camera", 9: "controller vibration bank"}
UNUSED_HEADER_WORDS = (0, 10, 11)


class MagResizeError(ValueError):
    pass


@dataclass(frozen=True)
class MagPointer:
    location: int          # where the value is stored
    base: int              # the offset it is relative to (0: file-relative)
    target: int            # the absolute offset it points to
    owner: str             # what holds it, for messages
    mask: int = 0xFFFFFFFF  # the bits holding the offset (texture/CLUT/music entries: the low 24)
    signed: bool = False
    certain: bool = True   # False: found by a shape guess, never rewritten

    def encode(self, stored, base, target):
        """The u32 to store when base and target have moved."""
        relative = target - base
        if self.signed:
            if not -0x80000000 <= relative < 0x80000000:
                raise MagResizeError(f"{self.owner}: the offset no longer fits")
            return relative & 0xFFFFFFFF
        if not 0 <= relative <= self.mask:
            raise MagResizeError(f"{self.owner}: the offset no longer fits")
        return (stored & ~self.mask & 0xFFFFFFFF) | relative


@dataclass(frozen=True)
class FixedReference:
    """A script operand holding a raw position in a loaded file (it does not follow a move)."""
    instruction: int       # offset of the instruction
    slot: int              # file slot (0 = the .00, 1 = the .01, 2+ = streamed parts)
    position: int          # position in that file, None: an exe descriptor offset
    text: str


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def is_packed(data):
    if len(data) < HEADER_SIZE:
        return False
    h = struct.unpack_from("<12I", data)
    return h[0] == 0 and h[5] == HEADER_SIZE and HEADER_SIZE <= h[2] <= h[6] <= h[7] <= len(data)


class PackedMag:
    """A packed MAG file: header, parts, pointer map and in-place resizing."""

    def __init__(self, data, name="", table: CineOpcodeTable = None):
        self.data = bytes(data)
        self.name = name
        self.table = table or CineOpcodeTable.default()
        if not is_packed(self.data):
            raise ValueError(f"{name or 'This file'} is not a packed MAG file")
        self.header = struct.unpack_from("<12I", self.data)
        self._sections = self._container = self._program = self._pointers = None

    # ------------------------------------------------------------------ parts
    def offset(self, index):
        """Header offset `index` (see HEADER_POINTERS), 0 when the part is absent."""
        return self.header[index]

    @property
    def sections(self):
        if self._sections is None:
            self._sections = MagFile(self.data, self.name).sections
        return self._sections

    @property
    def container(self):
        if self._container is None:
            self._container = MagContainer(self.data)
        return self._container

    def sound_entries(self):
        return magsound.sound_entries(self.data)

    def vibration_patterns(self):
        return magsound.vibration_patterns(self.data)

    @property
    def program(self):
        """The cinematic script (None in a file without one: the .01 and the streamed parts)."""
        if self._program is None and self.header[1]:
            self._program = CineProgram(self.data, self.header[1], self.table)
        return self._program

    @property
    def camera(self):
        """(offset, track size) of the stage camera track, None without one."""
        at = self.header[8]
        if not at or at + 8 > len(self.data):
            return None
        count, script, keys, size = struct.unpack_from("<4H", self.data, at)
        if count != 2 or script != 8 or not script < keys < size or at + size > len(self.data):
            return None
        return at, size

    # ------------------------------------------------------------------ pointer map
    def pointers(self):
        """Every offset into this file the game follows (MagPointer), in file order."""
        if self._pointers is None:
            self._pointers = sorted(self._find_pointers(), key=lambda p: p.location)
        return self._pointers

    def _find_pointers(self):
        data, h = self.data, self.header
        found = []
        for index, name in HEADER_POINTERS.items():
            if h[index]:
                found.append(MagPointer(4 * index, 0, h[index], f"header +0x{4 * index:02X} ({name})"))
        for start, end, name in ((h[5], h[2], "texture"), (h[2], h[6], "CLUT"), (h[6], h[7], "music")):
            for at in range(start, end - 3, 4):
                if value := _u32(data, at) & 0xFFFFFF:
                    found.append(MagPointer(at, start, start + value, f"{name} table entry {(at - start) // 4}",
                                            mask=0xFFFFFF))
        table = h[3]
        if table and table + 4 <= len(data):
            count = _u32(data, table)
            for index in range(min(count, (len(data) - table - 4) // 4)):
                at = table + 4 + 4 * index
                if value := _u32(data, at):
                    found.append(MagPointer(at, table, table + value, f"object {index}"))
            for obj in self.container.objects:
                if obj.kind != "sprite":
                    continue
                for k, frame in enumerate(obj.info.get("frames", [])):
                    if frame["code"] != 1:
                        found.append(MagPointer(obj.offset + 8 * k, table, table + frame["frame"],
                                                f"object {obj.index} sprite frame {k}", signed=True,
                                                certain=False))
        table = h[4]
        if table and table + 4 <= len(data):
            first = _u32(data, table)
            if first % 4 == 0 and table + first <= len(data):
                for index in range(first // 4):
                    if value := _u32(data, table + 4 * index):
                        found.append(MagPointer(table + 4 * index, table, table + value, f"sound {index}"))
        bank = h[9]
        if bank and bank + 8 <= len(data):
            limit, position, offsets = len(data) - bank, 0, []
            while position + 4 <= limit and (not offsets or position < min(offsets)):
                value = _u32(data, bank + position)
                if value:
                    if value >= limit:
                        break
                    offsets.append(value)
                    found.append(MagPointer(bank + position, bank, bank + value,
                                            f"vibration pattern {position // 4}"))
                position += 4
        return found

    def script_references(self):
        """(instruction offset, target) of every relative script reference."""
        if self.program is None:
            return []
        return [(offset, target) for offset, instruction in self.program.instructions.items()
                for _kind, target, _word in instruction.refs]

    def fixed_references(self):
        """Script operands holding raw positions in the loaded files (FixedReference)."""
        if self.program is None:
            return []
        result = []
        for offset, instruction in sorted(self.program.instructions.items()):
            code, words = instruction.op & 0x1FF, [w & 0xFFFF for w in instruction.words]
            if code == 0x06 and not instruction.op & 0x8000 and words and words[0] & 0xFF != 0xFF:
                lo, hi = words[0] & 0xFF, words[0] >> 8
                if lo & 0x80:
                    result.append(FixedReference(offset, lo & 0x7F, hi << 12,
                                                 f"0x{offset:X} LoadFile into slot {lo & 0x7F} at 0x{hi << 12:X}"))
                else:
                    result.append(FixedReference(offset, lo, None,
                                                 f"0x{offset:X} LoadFile into slot {lo} at an exe descriptor offset"))
            elif code == 0x29 and instruction.op & 0xC000 == 0x4000 and len(words) >= 3:
                result.append(FixedReference(offset, words[1] & 0x7F, words[2] << 12,
                                             f"0x{offset:X} VramUpload from slot {words[1] & 0x7F} at 0x{words[2] << 12:X}"))
        return result

    def work_buffer_floor(self):
        """The lowest fixed work buffer the script puts in the 1 MB magic buffer (op 0x21, bit15
        clear), None when every work buffer follows the .01."""
        if self.program is None:
            return None
        floors = [instruction.words[0] & 0xFFFF | (instruction.words[1] & 0xFFFF) << 16
                  for instruction in self.program.instructions.values()
                  if instruction.op & 0x1FF == 0x21 and not instruction.op & 0x8000 and len(instruction.words) >= 2]
        return min(floors) if floors else None

    # ------------------------------------------------------------------ resizing
    def room_end(self, start):
        """End of the part starting at `start`: the next offset anything points to (or the end)."""
        targets = [p.target for p in self.pointers() if p.target > start]
        return min(targets, default=len(self.data))

    def resize_problem(self, start, end=None, delta=4, loaded_after=0):
        """Why [start, end) cannot change size by `delta` bytes, "" when it can. `loaded_after`:
        bytes of the files loaded after this one into the magic buffer (the .01 for a .00), None
        when unknown."""
        end = self.part_end(start, end)
        if any(self.header[i] for i in UNUSED_HEADER_WORDS):
            return "its header uses words PackedMag does not know"
        if self.program is None:
            return "only a file with the script (the .00) can be resized: the script's raw file positions are needed"
        if self.program.errors:
            return "its script does not decode completely, so some references may be missed"
        for pointer in self.pointers():
            if start < pointer.target < end or start <= pointer.location < end:
                return f"{pointer.owner} points inside the part"
            if not pointer.certain and (pointer.target >= end) != (pointer.base >= end):
                return f"{pointer.owner} would have to change and its format is not certain"
        for offset, target in self.script_references():
            if (offset >= end) != (target >= end) or start < target < end:
                return f"the script reference at 0x{offset:X} crosses the part"
        for ref in self.fixed_references():
            if ref.slot == 0 and (ref.position is None or ref.position >= start):
                return f"the script holds a raw position past it ({ref.text})"
        floor = self.work_buffer_floor()
        if delta and floor is not None:
            if loaded_after is None:
                return (f"the script has a fixed work buffer at 0x{floor:X} and the size of the files loaded "
                        f"after this one is unknown")
            if len(self.data) + loaded_after > floor:
                # vanilla does it with a .01 of textures only, used up once uploaded: moving the
                # .01 would change what the work buffer overwrites
                return (f"the script's work buffer at 0x{floor:X} already reuses the memory of the files "
                        f"loaded after it, which would move")
            if len(self.data) + delta + loaded_after > floor:
                return (f"the effect's files would reach the script's work buffer at 0x{floor:X} "
                        f"(0x{floor - len(self.data) - loaded_after:X} bytes free)")
        if len(self.data) + delta + (loaded_after or 0) > MAGIC_BUFFER_SIZE:
            return "the effect's files would not fit the 1 MB magic buffer"
        return ""

    def part_end(self, start, end=None):
        """Where a replacement of the part [start, end) stops: `end` (default `room_end`) taken
        on to its 4-byte boundary, so earlier zero padding is reused, never past `room_end`."""
        room_end = self.room_end(start)
        end = room_end if end is None else end
        return min(end + (-end % 4), room_end)

    def resized(self, start, raw, end=None, loaded_after=0):
        """The file bytes with the part [start, end) (default: up to `room_end`) replaced by `raw`,
        every offset into the file updated. Zero padding keeps the following parts 4-byte aligned."""
        raw = bytes(raw)
        end = self.part_end(start, end)
        room = raw + bytes((end - start - len(raw)) % 4)
        delta = len(room) - (end - start)
        if problem := self.resize_problem(start, end, delta, loaded_after):
            raise MagResizeError(f"The part at 0x{start:X} cannot change size: {problem}")

        def moved(offset):
            return offset + delta if offset >= end else offset

        result = bytearray(self.data[:start] + room + self.data[end:])
        rewritten = set()
        for pointer in self.pointers():
            if pointer.target - pointer.base == moved(pointer.target) - moved(pointer.base):
                continue
            stored = _u32(self.data, pointer.location)
            struct.pack_into("<I", result, moved(pointer.location),
                             pointer.encode(stored, moved(pointer.base), moved(pointer.target)))
            rewritten.update(range(moved(pointer.location), moved(pointer.location) + 4))
        # every part outside the resized one is where its offsets now say, with the same bytes
        # (apart from the offsets rewritten above)
        for pointer in self.pointers():
            if pointer.target == start:
                continue
            for k, byte in enumerate(self.data[pointer.target:pointer.target + 16]):
                at = moved(pointer.target) + k
                if at not in rewritten and result[at] != byte:
                    raise MagResizeError(f"{pointer.owner} lost its data while resizing")
        return bytes(result)

    def with_camera(self, track, loaded_after=0):
        """The file bytes with the stage camera track replaced by `track` (any size)."""
        if self.camera is None:
            raise MagResizeError("This file has no stage camera track")
        start, size = self.camera
        return self.resized(start, track, start + size, loaded_after)
