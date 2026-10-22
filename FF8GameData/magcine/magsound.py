"""What the sound-related parts of a MAG file hold, and which audio.dat entry each one plays.

Verified in FF8_EN.exe:
 - Sound-effect table (packed header +0x10): u32 offsets relative to the table, the first one
   also gives the table size (count = first / 4). Each entry is a sound block {u32 world sound
   id, "SCOT", PlayStation payload}. Cinematic opcode 0x2B PlaySE (0xB25BB0) passes the block to
   BdPlaySE (0x501330), which only reads the leading id: PlayWorldSound -> GetSoundID_ForWorld
   (0x46B120) -> audio.dat entry. The SCOT payload is PlayStation data the PC build never reads.
 - "Voice bank" (packed header +0x24) is the CONTROLLER VIBRATION bank, not audio: op 0x39
   sub-op 2 claims slot (operand high byte + 1) through BdSound_ClaimVoiceSlot (0x4A29A0), and
   BdVibration_UpdatePerFrame (0x4A2A90) steps two byte envelopes per slot
   (BdVibration_StepEnvelope 0x4A2B80) into Pad_SetVibration (0x49F1A0): left and right motor.
   Pattern = u16 left length, u16 right length, then the two streams of {level, frames} pairs
   ending with frames 0xFF; a level is interpolated over frames + 1 ticks and sent x2 (max 255).
Not verified (shown as such):
 - Music table (packed header +0x18): entries point to the same {u32 id, "SCOT"} block shape,
   but the code that consumes them is not traced.
 - Standalone SCOT files (streamed GF parts): u32 id + "SCOT"; which call plays them on PC is
   not traced either. Both are previewed as "audio.dat entry = id" (category 0 ids map to
   themselves in GetSoundID_ForWorld).
 - AKAO files: PlayStation sample banks; nothing on PC references them.

No Qt here: only "which entry / what envelope", so it is testable without audio.
"""
import struct
from dataclasses import dataclass, field

from Julia.actorsoundtable import WORLD_SOUND_BASES, world_sound_to_archive_id

SCOT = b"SCOT"
SOUND_TABLE, MUSIC_TABLE, STREAM, AKAO = "Sound effect", "Music table", "Streamed sound", "AKAO bank"


@dataclass
class SoundEntry:
    table: str            # SOUND_TABLE / MUSIC_TABLE / STREAM / AKAO
    index: int            # entry number in its table (the PlaySE index for the sound table)
    offset: int           # absolute offset of the block in the file
    sound_id: int = None  # leading u32 (world sound id), None when the block has none
    archive_id: int = None  # audio.dat / audio.fmt entry the PC plays, None = not playable
    verified: bool = False  # the PC call that plays it is traced in the exe
    note: str = ""


@dataclass
class VibrationPattern:
    index: int            # slot index as op 0x39 sub-op 2 claims it (operand high byte + 1)
    offset: int
    left: list = field(default_factory=list)    # per-tick motor level 0-255
    right: list = field(default_factory=list)
    left_points: list = field(default_factory=list)    # [(level, frames)], the last frames = 0xFF
    right_points: list = field(default_factory=list)
    left_size: int = 0    # bytes of each stream (the u16 lengths)
    right_size: int = 0

    @property
    def ticks(self):
        return max(len(self.left), len(self.right))


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _block(data, offset, table, index, verified):
    """A {u32 id, "SCOT"} block, or a not-playable entry explaining what is there."""
    if offset + 8 > len(data):
        return SoundEntry(table, index, offset, note="Block is outside the file")
    sound_id = _u32(data, offset)
    if data[offset + 4:offset + 8] != SCOT:
        return SoundEntry(table, index, offset, sound_id,
                          note="No SCOT signature after the id: not a sound block")
    archive_id = world_sound_to_archive_id(sound_id)
    note = ("PlaySE -> PlayWorldSound reads this id; the SCOT payload is PlayStation data" if verified
            else "Same block shape as the sound table; the PC call that plays it is not traced")
    return SoundEntry(table, index, offset, sound_id, archive_id, verified, note)


def _packed_header(data):
    if len(data) < 0x30:
        return None
    h = struct.unpack_from("<12I", data)
    if h[0] == 0 and h[5] == 0x30 and 0x30 <= h[2] <= h[6] <= h[7] <= len(data):
        return h
    return None


def sound_entries(data):
    """Every sound block of a MAG file, in file order of its tables."""
    data = bytes(data)
    if data[4:8] == SCOT:
        return [_block(data, 0, STREAM, 0, False)]
    if data[:4] == b"AKAO":
        return [SoundEntry(AKAO, 0, 0, note="PlayStation AKAO sample bank: the PC build never "
                                            "plays it (no audio.dat entry)")]
    h = _packed_header(data)
    if h is None:
        return []
    entries = []
    table = h[4]
    if table and table + 4 <= len(data):
        first = _u32(data, table)
        count = first // 4 if first % 4 == 0 and table + first <= len(data) else 0
        for index in range(count):
            relative = _u32(data, table + 4 * index)
            entries.append(_block(data, table + relative, SOUND_TABLE, index, True))
    for index, at in enumerate(range(h[6], h[7] - 3, 4)):
        value = _u32(data, at)
        if value:
            entries.append(_block(data, h[6] + (value & 0xFFFFFF), MUSIC_TABLE, index, False))
    return entries


def world_id_for_archive(archive_id, current_world_id=None):
    """The world sound id that plays audio.dat entry `archive_id`: in the category of
    `current_world_id` when that category reaches it (the file keeps its style), else category 0
    (GetSoundID_ForWorld maps 0-9999 to themselves)."""
    if not 0 <= archive_id < 10000:
        raise ValueError("an audio.dat entry is between 0 and 9999")
    if current_world_id is not None:
        category = current_world_id // 10000
        base = WORLD_SOUND_BASES.get(category)
        if base is not None and 0 <= archive_id - base < 10000:
            return category * 10000 + archive_id - base
    return archive_id


def set_sound(data, entry, archive_id):
    """New bytes of the block of `entry` (a SoundEntry with an id) playing `archive_id`: only its
    leading u32 changes."""
    if entry.sound_id is None or bytes(data[entry.offset + 4:entry.offset + 8]) != SCOT:
        raise ValueError("this entry is not a sound block")
    world = world_id_for_archive(archive_id, entry.sound_id)
    assert world_sound_to_archive_id(world) == archive_id
    return struct.pack("<I", world)


def _points(stream):
    """[(level, frames)] of one envelope stream, up to and with its frames-0xFF end point."""
    points = []
    for position in range(0, len(stream) - 1, 2):
        points.append((stream[position], stream[position + 1]))
        if stream[position + 1] == 0xFF:
            break
    return points


def encode_points(points, size):
    """The `size` bytes of a stream holding `points` (same count as before: the bytes after the
    end point are kept by the caller). Levels 0-255, frames 0-254, the last frames is 0xFF."""
    raw = bytearray()
    for number, (level, frames) in enumerate(points):
        last = number == len(points) - 1
        if not 0 <= level <= 255:
            raise ValueError("a vibration level is between 0 and 255")
        if not last and not 0 <= frames <= 254:
            raise ValueError("a segment lasts 0 to 254 ticks")
        raw += bytes((level, 0xFF if last else frames))
    if len(raw) > size:
        raise ValueError("the pattern would grow")
    return bytes(raw)


def set_vibration(data, pattern, side, points):
    """(offset, new bytes) writing `points` into the left or right stream of `pattern`, keeping
    its size and segment count."""
    old = pattern.left_points if side == "left" else pattern.right_points
    if len(points) != len(old):
        raise ValueError(f"the {side} motor has {len(old)} points; their number cannot change in place")
    start = pattern.offset + 4 + (0 if side == "left" else pattern.left_size)
    raw = encode_points(points, pattern.left_size if side == "left" else pattern.right_size)
    return start, raw


def _envelope(stream):
    """Per-tick motor levels of one byte stream, stepped like BdVibration_StepEnvelope: the
    claim sets the tick counter to -1, each finished segment resets it to 0."""
    levels = []
    position, counter = 0, -1
    while position + 2 < len(stream) and len(levels) < 10000:
        start, frames, target = stream[position], stream[position + 1], stream[position + 2]
        if frames == 0xFF:
            break
        if counter < frames:
            level = ((counter + 1) * target + start * (frames - counter)) // (frames + 1)
            counter += 1
        else:
            level = target
            position += 2
            counter = 0
        levels.append(max(0, min(255, 2 * level)))
    return levels


def vibration_patterns(data):
    """The controller vibration patterns of a packed MAG (header +0x24), [] when absent."""
    data = bytes(data)
    h = _packed_header(data)
    if h is None or not h[9] or h[9] + 8 > len(data):
        return []
    bank = h[9]
    offsets = []
    # u32 offsets relative to the bank; the table ends where the first pattern starts
    limit = len(data) - bank
    position = 0
    while position + 4 <= limit and (not offsets or position < min(offsets)):
        value = _u32(data, bank + position)
        if value:
            if value >= limit:
                break
            offsets.append(value)
        position += 4
    patterns = []
    for index in range(position // 4):
        value = _u32(data, bank + 4 * index)
        if not value or bank + value + 4 > len(data):
            continue
        at = bank + value
        left_size, right_size = struct.unpack_from("<HH", data, at)
        left = data[at + 4:at + 4 + left_size]
        right = data[at + 4 + left_size:at + 4 + left_size + right_size]
        patterns.append(VibrationPattern(index, at, _envelope(left), _envelope(right), _points(left),
                                         _points(right), left_size, right_size))
    return patterns
