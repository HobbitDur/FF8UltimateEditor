"""Monster battle .dat section 6: the camera animation collection.

Unlike the entity animation section (section 5), section 6 of a monster is NOT a byte-code
program. It is a *camera animation collection*: keyframed camera motions the battle engine
plays while filming the monster (a spell/ability effect points the camera at one of these).
The byte-code camera VM the wiki documents (opcodes 00-09 + the shared arithmetic/jumps)
lives in the camera *setting* half of a full camera blob, which monster files do not carry -
they ship only this collection (verified: all 133 non-empty c0m*.dat camera sections read as
a collection, EOF word == section length, every pointer resolves).

Layout (all offsets little-endian; verified against FF8_EN.exe BS_GetCameraAnimationPointer
@0x503520 and BS_Camera_ReadAnimation @0x503C70, and every vanilla monster file):

    collection:
        u16 nbOfSet
        u16 setPointer[nbOfSet]     # relative to collection start, x1
        u16 eof                     # == collection byte length
        ... sets (located by setPointer, not necessarily contiguous) ...

    set (at collection + setPointer[s]):
        s16 animPointer[8]          # x2, relative to the SET start; a slot is empty when
                                    # its target word is 0xFFFF (idle monsters reuse one
                                    # 0xFFFF for several slots, so pointers can overlap)

    animation (at set + 2*animPointer[a]): a chain of blocks, ended by a control word 0xFFFF
        block:
            u16 controlWord         # FOV = (cw>>6)&3, ROLL = (cw>>8)&3, LAYOUT = cw&1
            u16 fov[fov_words]      # 0/1 -> none (keep / default 0x200,0x200);
                                    # 2 -> one word (start==end); 3 -> two words (start,end)
            u16 roll[roll_words]    # 0/1 -> none (copy current / default 0,0);
                                    # 2 -> one word; 3 -> two words
            frame[...]              # until a word with bit15 set (the 0xFFFF terminator,
                                    # consumed); each frame is 18 bytes:
                u16 duration
                u8  posInterpMode ; u8 pad
                s16 posZ ; s16 posX ; s16 posY
                u8  lookInterpMode ; u8 pad
                s16 lookZ ; s16 lookX ; s16 lookY

The model is a *view over the raw section bytes*: every editable field carries its absolute
offset, and setting it patches the raw bytearray in place. Every scalar the editor exposes is
fixed size (durations u16, coordinates s16, modes/FOV/ROLL), so editing a value never changes
the section length - a saved file is byte-for-byte identical except the bytes the user
actually changed. get_bytes() returns that raw bytearray; it is the single source of truth,
exactly like IfritSeq's hex box.
"""
import struct

FRAME_SIZE = 18
_EMPTY_ANIM_POINTER = -1          # 0xFFFF as a signed int16
_END_OF_ANIMATION = 0xFFFF        # a control word that ends the animation
NB_SLOT_PER_SET = 8               # the engine masks the requested anim index with & 7

# How many u16 words the FOV / ROLL field occupies for each 2-bit mode.
_FOV_WORDS = (0, 0, 1, 2)
_ROLL_WORDS = (0, 0, 1, 2)


class CameraParseError(ValueError):
    """The section does not read as a camera animation collection."""


class CameraField:
    """One scalar living at an absolute offset in the shared section buffer.

    Reading and writing go straight to the buffer, so the model never holds a second copy
    that could drift from the bytes, and an edit is a byte patch of known size.
    """
    __slots__ = ("data", "offset", "kind")

    def __init__(self, data: bytearray, offset: int, kind: str):
        self.data = data
        self.offset = offset
        self.kind = kind  # 'u16' | 's16' | 'u8'

    @property
    def bit_size(self) -> int:
        return 8 if self.kind == "u8" else 16

    @property
    def minimum(self) -> int:
        return -32768 if self.kind == "s16" else 0

    @property
    def maximum(self) -> int:
        return {"u8": 0xFF, "u16": 0xFFFF, "s16": 32767}[self.kind]

    def get(self) -> int:
        if self.kind == "u8":
            return self.data[self.offset]
        fmt = "<h" if self.kind == "s16" else "<H"
        return struct.unpack_from(fmt, self.data, self.offset)[0]

    def set(self, value: int):
        if not self.minimum <= value <= self.maximum:
            raise ValueError(f"{value} out of range for {self.kind}")
        if self.kind == "u8":
            self.data[self.offset] = value & 0xFF
        else:
            fmt = "<h" if self.kind == "s16" else "<H"
            struct.pack_into(fmt, self.data, self.offset, value)


class CameraFrame:
    """One 18-byte keyframe: a camera position and look-at, held for `duration` ticks."""

    def __init__(self, data: bytearray, offset: int):
        self.offset = offset
        self.duration = CameraField(data, offset + 0, "u16")
        self.pos_interp_mode = CameraField(data, offset + 2, "u8")
        # byte 3: padding (engine skips it)
        self.pos_z = CameraField(data, offset + 4, "s16")
        self.pos_x = CameraField(data, offset + 6, "s16")
        self.pos_y = CameraField(data, offset + 8, "s16")
        self.look_interp_mode = CameraField(data, offset + 10, "u8")
        # byte 11: padding
        self.look_z = CameraField(data, offset + 12, "s16")
        self.look_x = CameraField(data, offset + 14, "s16")
        self.look_y = CameraField(data, offset + 16, "s16")

    def fields(self):
        """(label, CameraField) pairs, in display order."""
        return [
            ("Duration", self.duration),
            ("Pos interp", self.pos_interp_mode),
            ("Pos X", self.pos_x), ("Pos Y", self.pos_y), ("Pos Z", self.pos_z),
            ("Look interp", self.look_interp_mode),
            ("Look X", self.look_x), ("Look Y", self.look_y), ("Look Z", self.look_z),
        ]


class CameraBlock:
    """One control-word block: FOV/ROLL setup + a list of keyframes."""

    def __init__(self, data: bytearray, offset: int):
        self.offset = offset
        self.control_word = struct.unpack_from("<H", data, offset)[0]
        self.fov_mode = (self.control_word >> 6) & 3
        self.roll_mode = (self.control_word >> 8) & 3
        self.layout = self.control_word & 1
        self.fov_start = None
        self.fov_end = None
        self.roll_start = None
        self.roll_end = None
        self.frames = []
        self.end = offset  # set by _parse

    def optional_fields(self):
        """(label, CameraField) pairs for the FOV/ROLL values that are actually stored."""
        result = []
        if self.fov_start is not None:
            result.append(("FOV start", self.fov_start))
        if self.fov_end is not None and self.fov_end is not self.fov_start:
            result.append(("FOV end", self.fov_end))
        if self.roll_start is not None:
            result.append(("Roll start", self.roll_start))
        if self.roll_end is not None and self.roll_end is not self.roll_start:
            result.append(("Roll end", self.roll_end))
        return result


class CameraAnimation:
    """One camera animation: a chain of blocks. Empty when the slot points at a 0xFFFF."""

    def __init__(self, slot: int, offset: int):
        self.slot = slot
        self.offset = offset
        self.empty = False
        self.blocks = []


class CameraSet:
    """One set of 8 animation slots."""

    def __init__(self, index: int, offset: int):
        self.index = index
        self.offset = offset
        self.animations = []  # 8 CameraAnimation


class CameraCollection:
    """The whole section 6, parsed as an editable view over its raw bytes."""

    def __init__(self, data: bytearray):
        self.data = data
        self.nb_set = 0
        self.eof = 0
        self.set_pointers = []
        self.sets = []
        self.empty = len(data) < 6
        if not self.empty:
            self._parse()

    # ------------------------------------------------------------------ parse
    def _u16(self, offset: int) -> int:
        if offset + 2 > len(self.data):
            raise CameraParseError(f"read past end at offset {offset}")
        return struct.unpack_from("<H", self.data, offset)[0]

    def _parse(self):
        self.nb_set = self._u16(0)
        if not 1 <= self.nb_set <= 32:
            raise CameraParseError(f"implausible set count {self.nb_set}")
        self.set_pointers = [self._u16(2 + 2 * index) for index in range(self.nb_set)]
        self.eof = self._u16(2 + 2 * self.nb_set)
        if self.eof != len(self.data):
            raise CameraParseError(f"eof word {self.eof} != section length {len(self.data)}")
        for index, pointer in enumerate(self.set_pointers):
            self.sets.append(self._parse_set(index, pointer))

    def _parse_set(self, index: int, set_offset: int) -> CameraSet:
        if not 0 <= set_offset < len(self.data):
            raise CameraParseError(f"set {index} pointer {set_offset} out of range")
        camera_set = CameraSet(index, set_offset)
        for slot in range(NB_SLOT_PER_SET):
            pointer = struct.unpack_from("<h", self.data, set_offset + 2 * slot)[0]
            camera_set.animations.append(self._parse_animation(slot, set_offset, pointer))
        return camera_set

    def _parse_animation(self, slot: int, set_offset: int, pointer: int) -> CameraAnimation:
        anim_offset = set_offset + 2 * pointer
        animation = CameraAnimation(slot, anim_offset)
        if pointer == _EMPTY_ANIM_POINTER or not 0 <= anim_offset < len(self.data) \
                or self._u16(anim_offset) == _END_OF_ANIMATION:
            animation.empty = True
            return animation
        position = anim_offset
        while True:
            control_word = self._u16(position)
            if control_word & 0x8000:  # 0xFFFF: end of the animation
                break
            block, position = self._parse_block(position)
            animation.blocks.append(block)
        return animation

    def _parse_block(self, offset: int):
        block = CameraBlock(self.data, offset)
        position = offset + 2
        fov_words = _FOV_WORDS[block.fov_mode]
        if fov_words >= 1:
            block.fov_start = CameraField(self.data, position, "u16")
            block.fov_end = (CameraField(self.data, position + 2, "u16") if fov_words == 2
                             else block.fov_start)  # 'same' mode shares the one word
        position += 2 * fov_words
        roll_words = _ROLL_WORDS[block.roll_mode]
        if roll_words >= 1:
            block.roll_start = CameraField(self.data, position, "u16")
            block.roll_end = (CameraField(self.data, position + 2, "u16") if roll_words == 2
                              else block.roll_start)
        position += 2 * roll_words
        while True:
            word = self._u16(position)
            if word & 0x8000:  # frame terminator (0xFFFF), consumed
                position += 2
                break
            if position + FRAME_SIZE > len(self.data):
                raise CameraParseError(f"frame at {position} runs past end of section")
            block.frames.append(CameraFrame(self.data, position))
            position += FRAME_SIZE
        block.end = position
        return block, position

    # ------------------------------------------------------------------- bytes
    def get_bytes(self) -> bytearray:
        """The section bytes, the single source of truth (patched in place on edit)."""
        return self.data

    def is_empty(self) -> bool:
        return self.empty


def parse_camera_collection(data) -> CameraCollection:
    """Parse section 6 into an editable collection. Raises CameraParseError on anything that
    does not read as a collection (so a caller can fall back to keeping the section raw)."""
    return CameraCollection(bytearray(data))


def _keyframe_bytes(pos, look, duration: int) -> bytes:
    """One 18-byte keyframe from (x, y, z) tuples. Stored order is Z, X, Y (see the layout)."""
    x, y, z = pos
    lx, ly, lz = look
    return (struct.pack("<H", duration) + struct.pack("<BB", 0, 0) + struct.pack("<hhh", z, x, y)
            + struct.pack("<BB", 0, 0) + struct.pack("<hhh", lz, lx, ly))


def build_default_animation() -> bytes:
    """Bytes for a minimal, ready-to-edit new camera animation: one block (default FOV/roll)
    with two keyframes (a start and an end, seeded with sane framing values copied from a
    vanilla shot), then the end-of-animation marker."""
    # control word: FOV mode 1 (default 0x200), ROLL mode 1 (default 0), layout 0 -> 0x0140.
    # Default modes store no FOV/roll words, so the block is just the keyframe list.
    control_word = (1 << 6) | (1 << 8)
    data = bytearray(struct.pack("<H", control_word))
    data += _keyframe_bytes((1739, 2985, -4001), (355, 236, 316), 15)
    data += _keyframe_bytes((1848, 5044, 286), (0, 0, 0), 15)
    data += struct.pack("<H", 0xFFFF)  # frame-list terminator
    data += struct.pack("<H", 0xFFFF)  # end-of-animation control word
    return bytes(data)


def add_animation_to_slot(data, set_index: int, slot: int) -> bytearray:
    """Return new section bytes with a default animation placed in a currently-empty slot.

    The animation is appended at the end of the section and the slot's pointer is repointed at
    it; the collection's EOF word (its byte length) and 4-byte alignment are kept consistent.
    Structural edit - unlike value edits, this changes the section length, which the file
    writer absorbs by recomputing the header offsets from each section's size.
    """
    collection = parse_camera_collection(data)
    if not 0 <= set_index < collection.nb_set:
        raise ValueError(f"set {set_index} does not exist")
    if not 0 <= slot < NB_SLOT_PER_SET:
        raise ValueError(f"slot {slot} is out of range")
    set_start = collection.set_pointers[set_index]
    new_data = bytearray(collection.get_bytes())
    # The anim pointer is (offset from the set start) / 2, so the animation must begin an even
    # number of bytes from the set: pad until it does.
    while (len(new_data) - set_start) % 2 != 0:
        new_data.append(0x00)
    anim_offset = len(new_data)
    pointer = (anim_offset - set_start) // 2
    if not -32768 <= pointer <= 32767:
        raise ValueError("the camera section is too large to add another animation")
    new_data += build_default_animation()
    while len(new_data) % 4 != 0:  # keep the section 4-byte aligned like vanilla
        new_data.append(0x00)
    struct.pack_into("<h", new_data, set_start + 2 * slot, pointer)   # repoint the slot
    struct.pack_into("<H", new_data, 2 + 2 * collection.nb_set, len(new_data))  # EOF == length
    return new_data
