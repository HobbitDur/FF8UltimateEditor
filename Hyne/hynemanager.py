"""
Hyne: FF8 Steam .ff8 save-file editor, native to this project's PyQt6 toolset (replaces the
need for the third-party Hyne.exe GUI tool in ExternalTools/Hyne, which shares the name).

File format (verified in IDA against FF8_EN.exe, cross-checked with a real end-to-end
round-trip): a .ff8 file is `[u32 LE compressedSize][LZSS data]`, decompressing to a fixed
8192-byte PSX memcard block:
  [0..383]    header (SJIS title + playtime) — not touched by this tool
  [384..5411] savemap, 5028 bytes (memcpy'd from the runtime global SG_CHECKSUM)
    savemap+0..1    CRC16 (LE u16), copy 1
    savemap+2..3    "magic" field (0x08FF on a committed file) — not touched
    savemap+80..    game-state block, byte-identical layout to init.out (confirmed via
                     IDA: SG_ARRAY_CHARA_DATA - SG_CHECKSUM == 1168 == 80 + 1088, where 1088
                     is Quezacotl/quezacotlmanager.py's independently-documented
                     CHARACTER_DATA_OFFSET). So every entry class Quezacotl already exposes
                     for init.out (GfEntry, CharacterEntry, ConfigEntry, MiscEntry, ItemEntry)
                     applies unchanged here — only the base offset differs (add 80, then 384).
    savemap+5024..5025  CRC16, copy 2 (same value as copy 1)
  CRC is computed over savemap+80..5023 (4944 bytes) via a byte-at-a-time CRC16/CCITT-like
  algorithm whose table-build loop has a real off-by-one bug (table[255] is never written and
  stays 0) — NOT the textbook CRC-16/CCITT-FALSE table. See crc16_ff8() below.

Bytes outside the parsed entries (shops cache, worldmap/chocobo-world/script-variable state
past the item table, the header) are preserved byte-for-byte: the manager keeps the whole
8192-byte image in one buffer and every entry is a thin view over it, so anything never
decoded is simply never touched.

FFNx's AddMoreItems (255 inventory slots instead of 198, FF8GameData/itemids.py) keeps all its
slots in a 522-byte block in the image's unused tail, outside the CRC:
  [0x1600..0x1603] magic 0x4D495846, [0x1604] u16 version 1, [0x1606] u16 slot count 255,
  [0x1608] u32 FNV-1a over the 510 slot bytes, [0x160C..] 255 x (u8 item id, u8 quantity).
FFNx uses the block only when it is valid AND its first 198 slots equal the savemap's own item
table (otherwise the vanilla table was changed after it, by the game or a tool, and FFNx takes
that table and empties slots 199-255). So with a block this tool edits its 255 slots and copies
the first 198 into the savemap's table on save; without one the save is edited as vanilla.

FFNx's AddMoreAbility (up to 255 kernel.bin abilities) keeps learned ability ids 128-254 in a
524-byte block right after it, also outside the CRC; ids 0-127 stay in each GF's 16-byte field:
  [0x1810..0x1813] magic 0x42415846 ("FXAB"), [0x1814] u16 version 1, [0x1816] u16 GF count 16,
  [0x1818] u32 FNV-1a over the 512 bytes that follow,
  [0x181C..] 16 x 16 bytes: each GF's savemap learned field again (ids 0-127),
  [0x191C..] 16 x 16 bytes: each GF's ids 128-255.
FFNx uses the block only when it is valid AND its copy of the 16 learned fields still equals the
savemap's (otherwise something saved over the slot without FFNx) - then ids 128+ start unlearned.
This tool writes the block only once an id past 127 is ticked, or when the save already has one.
"""
import os
import re
import shutil
import struct
import time

from FF8GameData.gamedata import GameData
from Quezacotl.quezacotlmanager import (
    GfEntry, CharacterEntry, ConfigEntry, MiscEntry, ItemEntry,
    NB_GF, GF_ENTRY_SIZE, NB_CHARACTERS, CHARACTER_ENTRY_SIZE,
    CONFIG_ENTRY_SIZE, MISC_ENTRY_SIZE, NB_ITEMS, ITEM_ENTRY_SIZE,
    GF_DATA_OFFSET, CHARACTER_DATA_OFFSET, CONFIG_DATA_OFFSET, MISC_DATA_OFFSET,
    ITEMS_DATA_OFFSET, LEARNED_ABILITY_BITS,
)

IMAGE_SIZE = 8192
HEADER_SIZE = 384
SAVEMAP_SIZE = 5028

# savemap+80 is where the init.out-shaped game state starts; every Quezacotl offset constant
# (GF_DATA_OFFSET, CHARACTER_DATA_OFFSET, ...) is relative to that point, so the absolute
# offset inside the 8192-byte image is HEADER_SIZE + 80 + <quezacotl offset>.
SAVEMAP_GAMESTATE_OFFSET = 80
GAMESTATE_BASE = HEADER_SIZE + SAVEMAP_GAMESTATE_OFFSET  # 464

CRC_OFFSET_1 = HEADER_SIZE + 0        # savemap+0
CRC_OFFSET_2 = HEADER_SIZE + 5024     # savemap+5024
CRC_SPAN_START = GAMESTATE_BASE       # image offset 464 == savemap+80
CRC_SPAN_LEN = 4944                   # covers savemap+80..5023

ITEM_EXT_OFFSET = 0x1600              # FFNx AddMoreItems inventory block (see the docstring)
ITEM_EXT_MAGIC = 0x4D495846
ITEM_EXT_VERSION = 1
ITEM_EXT_SLOTS = 255
ITEM_EXT_HEADER_SIZE = 12
ITEM_EXT_SIZE = ITEM_EXT_HEADER_SIZE + 2 * ITEM_EXT_SLOTS   # 522
ITEM_MAX_QUANTITY = 100

ABILITY_EXT_OFFSET = 0x1810           # FFNx AddMoreAbility learned-ability block (see the docstring)
ABILITY_EXT_MAGIC = 0x42415846
ABILITY_EXT_VERSION = 1
ABILITY_EXT_HEADER_SIZE = 12
ABILITY_EXT_GF_BYTES = LEARNED_ABILITY_BITS // 8                     # 16 per GF, per half
ABILITY_EXT_NATIVE = ABILITY_EXT_OFFSET + ABILITY_EXT_HEADER_SIZE    # the learned fields' copy
ABILITY_EXT_EXTENDED = ABILITY_EXT_NATIVE + NB_GF * ABILITY_EXT_GF_BYTES
ABILITY_EXT_SIZE = ABILITY_EXT_HEADER_SIZE + 2 * NB_GF * ABILITY_EXT_GF_BYTES   # 524
SAVE_ABILITY_IDS = 255                # a save can mark ids 0-254 learned (255 means "no ability")
GF_LEARNED_OFFSET = 20                # a GF record's 16-byte learned field


def item_extension_checksum(slot_bytes) -> int:
    """FNV-1a (32-bit) over the slots' bytes, item id then quantity, as FFNx computes it."""
    value = 2166136261
    for byte in slot_bytes:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def normalize_item_slots(slots):
    """[(id, quantity)] made acceptable to FFNx, as FFNx itself does before saving: an empty
    id or quantity empties the slot, quantities stop at 100, and a second slot of the same item
    adds to the first. Slots keep their places."""
    first = {}
    result = []
    for item_id, quantity in slots:
        if not item_id or not quantity:
            result.append((0, 0))
            continue
        quantity = min(ITEM_MAX_QUANTITY, quantity)
        if item_id in first:
            index = first[item_id]
            result[index] = (item_id, min(ITEM_MAX_QUANTITY, result[index][1] + quantity))
            result.append((0, 0))
        else:
            first[item_id] = len(result)
            result.append((item_id, quantity))
    return result


def lzss_decompress(payload: bytes) -> bytes:
    """Archive_LZSSDecompress@0x40f852: flag byte (LSB-first) gates 8 tokens; bit=1 -> literal
    byte; bit=0 -> 2-byte back-reference (12-bit offset, base 0xFEE, length = 3..18). Ring
    positions before the real output start read as 0x00 (not the 0x20 many other PSX LZSS
    variants use)."""
    out = bytearray()
    i = 0
    n = len(payload)
    flag_bits = 0
    flags = 0
    while True:
        if flag_bits == 0:
            flag_bits = 8
            if i >= n:
                break
            flags = payload[i]
            i += 1
        bit = flags & 1
        flags >>= 1
        flag_bits -= 1
        if bit:
            if i >= n:
                break
            out.append(payload[i])
            i += 1
        else:
            if i + 1 >= n:
                break
            ref_lo = payload[i]
            ref_hi = payload[i + 1]
            i += 2
            raw12 = ((ref_hi & 0xF0) << 4) | ref_lo
            length = (ref_hi & 0xF) + 3
            cur_len = len(out)
            delta = (cur_len - raw12 + 0xFEE) & 0xFFF
            win_pos = cur_len - delta
            copy_end = cur_len + length
            while win_pos < 0 and len(out) < copy_end:
                out.append(0)
                win_pos += 1
            while len(out) < copy_end:
                out.append(out[win_pos])
                win_pos += 1
    return bytes(out)


def lzss_compress_all_literal(data: bytes) -> bytes:
    """Emit every token as a literal (flag byte = 0xFF). Valid input to Archive_LZSSDecompress,
    but DO NOT USE for anything that gets written back to disk: it inflates an 8192-byte image to
    ~9216 bytes, which BREAKS a real save (see lzss_compress below). Kept only because a couple of
    early tests exercise the all-literal token-framing path in isolation."""
    out = bytearray()
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append(0xFF if len(chunk) == 8 else (1 << len(chunk)) - 1)
        out.extend(chunk)
    return bytes(out)


# Max representable back-reference distance: the format's offset field is 12 bits (0..4095) with
# mod-4096 ring-buffer arithmetic, so a distance of exactly 4096 would alias to 0 and corrupt the
# reference - the window must stop at 4095, not 4096.
_LZSS_WINDOW = 4095
_LZSS_MIN_MATCH = 3
_LZSS_MAX_MATCH = 18


def lzss_compress(data: bytes) -> bytes:
    """Real (back-reference-using) LZSS compressor for Archive_LZSSDecompress@0x40f852's format.

    MUST be used for anything written back to a real save file. Save_EmuMC_CreateFile@0x4c4fa0
    enforces a hard per-file block budget: `v6 = ceil(requestedSize / 8192) * 8192`, checked
    against remaining capacity on a 245760-byte (=30*8192) emulated memory card - i.e. ONE save
    file must compress to <= 8192 bytes to fit its single allotted "block". A file that exceeds
    8192 bytes (like the all-literal encoder's ~9216-byte output for a full image) silently
    claims a SECOND block, corrupting the "1 save = 1 block" accounting; the game then flags that
    save slot "unused block" and deletes it (root-caused after breaking a real save file - see
    the [[ff8-save-file-format]] memory entry).

    A greedy longest-match encoder is more than sufficient: real save data is mostly zeroed/
    repeated bytes (unused item slots, unrecruited-character blocks, ...), so even this naive
    matcher lands within a couple bytes of the game's own compressor's output size, comfortably
    under the 8192-byte ceiling.
    """
    n = len(data)
    out = bytearray()
    flag_byte_pos = None
    flag_bits_used = 0
    flag_value = 0

    def start_group():
        nonlocal flag_byte_pos, flag_bits_used, flag_value
        out.append(0)  # placeholder, patched in below
        flag_byte_pos = len(out) - 1
        flag_bits_used = 0
        flag_value = 0

    def push_bit(bit, payload_bytes):
        nonlocal flag_bits_used, flag_value
        if flag_bits_used == 8 or flag_byte_pos is None:
            start_group()
        if bit:
            flag_value |= (1 << flag_bits_used)
        out.extend(payload_bytes)
        flag_bits_used += 1
        out[flag_byte_pos] = flag_value

    i = 0
    while i < n:
        best_len = 0
        best_dist = 0
        window_start = max(0, i - _LZSS_WINDOW)
        max_len = min(_LZSS_MAX_MATCH, n - i)
        if max_len >= _LZSS_MIN_MATCH:
            for j in range(window_start, i):
                length = 0
                while length < max_len and data[j + length] == data[i + length]:
                    length += 1
                if length > best_len:
                    best_len = length
                    best_dist = i - j
                    if best_len == max_len:
                        break
        if best_len >= _LZSS_MIN_MATCH:
            # Inverse of the decompressor's win_pos = cur_len - ((cur_len - raw12 + 0xFEE) &
            # 0xFFF): raw12 = (i - dist + 0xFEE) & 0xFFF.
            raw12 = (i - best_dist + 0xFEE) & 0xFFF
            ref_lo = raw12 & 0xFF
            ref_hi = ((raw12 >> 4) & 0xF0) | ((best_len - 3) & 0xF)
            push_bit(0, bytes([ref_lo, ref_hi]))
            i += best_len
        else:
            push_bit(1, bytes([data[i]]))
            i += 1
    return bytes(out)


import hashlib

_SLOT_NUM_RE = re.compile(r"slot(\d)_save(\d{2})\.ff8$", re.IGNORECASE)


def metadata_signature(file_bytes: bytes, user_id: str) -> str:
    """Reproduces Hyne.exe's Metadata::md5sum (src/Metadata.cpp, myst6re/hyne on GitHub):
    MD5(full .ff8 file bytes + userID), lowercase hex. Verified byte-for-byte against a real
    save's metadata.xml entry: md5(open('slot1_save02.ff8','rb').read() + b'18680116') matched
    that file's stored <signature> exactly."""
    return hashlib.md5(file_bytes + user_id.encode("latin1")).hexdigest()


def update_metadata_for_save(save_file_path: str, file_bytes: bytes):
    """Updates metadata.xml's <savefile> entry for this save to match file_bytes, exactly like
    the real Hyne.exe's UserDirectory::updateMetadata() does. This is NOT optional: something
    outside this game's own save code (Steam Cloud sync and/or the DotEmu-era EmuMC layer - both
    outside FF8_EN.exe's own IDA database, confirmed via dotemuCreateFileA/dotemuDeleteFileA
    imports from an external AF3DN module) silently reverts or flags "unused block" a .ff8 file
    whose content no longer matches its metadata.xml-recorded signature, even when the file
    itself is perfectly well-formed (LZSS-valid, CRC-correct, under the 8192-byte block limit).
    Discovered the hard way after two internally-verified saves were silently reverted. See the
    [[ff8-save-file-format]] memory entry for the full story."""
    save_dir = os.path.dirname(os.path.abspath(save_file_path))
    metadata_path = os.path.join(save_dir, "metadata.xml")
    match = _SLOT_NUM_RE.search(os.path.basename(save_file_path))
    if not match or not os.path.exists(metadata_path):
        return  # not a recognized slotN_saveNN.ff8 path, or no metadata.xml alongside it

    slot, num = match.group(1), match.group(2)
    user_dir_name = os.path.basename(save_dir)
    if not user_dir_name.startswith("user_"):
        return
    user_id = user_dir_name[len("user_"):]

    with open(metadata_path, "r", encoding="utf-8") as f:
        xml_text = f.read()

    signature = metadata_signature(file_bytes, user_id)
    timestamp = int(time.time() * 1000)

    block_re = re.compile(
        r'(<savefile\s+num="' + re.escape(str(int(num))) + r'"\s+type="ff8"\s+slot="' +
        re.escape(slot) + r'"\s*>\s*<timestamp>)(.*?)(</timestamp>\s*<signature>)(.*?)(</signature>\s*</savefile>)',
        re.DOTALL,
    )
    new_xml_text, count = block_re.subn(
        lambda m: m.group(1) + str(timestamp) + m.group(3) + signature + m.group(5),
        xml_text,
        count=1,
    )
    if count != 1:
        raise ValueError(
            f"Could not find metadata.xml entry for num={int(num)} slot={slot} to update - "
            "refusing to write a save whose metadata.xml wouldn't be kept in sync (this is what "
            "caused the game to silently revert/flag prior edits as \"unused block\").")

    shutil.copy2(metadata_path, metadata_path + ".bak")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(new_xml_text)


def _build_crc_table():
    """Replicates Save_ComputeChecksumCRC16CCITT@0x500310's table build EXACTLY, including its
    off-by-one bug: the outer loop is `do {...} while (v2 < 0xFF)`, checked AFTER incrementing,
    so it only ever fills indices 0..254 — table[255] is NEVER written and stays 0 (from the
    initial memset). A textbook CRC-16/CCITT-FALSE table does NOT reproduce this."""
    table = [0] * 256
    v2 = 0
    while True:
        v6 = v2 << 8
        for _ in range(8):
            if v6 & 0x8000:
                v6 = ((2 * v6) ^ 0x1021) & 0xFFFF
            else:
                v6 = (2 * v6) & 0xFFFF
        table[v2] = v6
        v2 += 1
        if not (v2 < 0xFF):
            break
    return table


_CRC_TABLE = _build_crc_table()


def crc16_ff8(data) -> int:
    crc = 0xFFFF
    for byte in data:
        v9 = (crc & 0xFF) << 8
        index = (byte ^ (crc >> 8)) & 0xFF
        crc = (v9 ^ _CRC_TABLE[index]) & 0xFFFF
    return (~crc) & 0xFFFF


class HyneGfEntry(GfEntry):
    """A save's GF record: learned ids 128+ live in FFNx AddMoreAbility's block."""

    def __init__(self, manager, offset, gf_id):
        super().__init__(manager.buffer, offset, gf_id, manager.game_data)
        self._manager = manager

    def has_ability(self, ability_id):
        if ability_id < LEARNED_ABILITY_BITS:
            return super().has_ability(ability_id)
        if self._manager.ability_extension != "extended":
            return False
        position, bit = self._manager.extended_ability_bit(self.gf_id, ability_id)
        return bool(self._buffer[position] & bit)

    def set_ability(self, ability_id, learned):
        if ability_id < LEARNED_ABILITY_BITS:
            super().set_ability(ability_id, learned)
            return
        if not learned and self._manager.ability_extension != "extended":
            return
        self._manager.enable_ability_extension()
        position, bit = self._manager.extended_ability_bit(self.gf_id, ability_id)
        if learned:
            self._buffer[position] |= bit
        else:
            self._buffer[position] &= ~bit & 0xFF


class HyneManager:
    """.ff8 save-file editor logic.

    The decompressed 8192-byte image is kept as a single in-memory buffer; GF, character,
    config, misc and item entries are the exact same Quezacotl view classes used by the
    init.out editor, just re-based onto the savemap's game-state offset (GAMESTATE_BASE).
    Anything outside those entries (header, shops cache, worldmap/chocobo/script-variable
    state past the item table) is preserved byte-for-byte because it is never written.
    """

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.game_data.load_gforce_data()
        self.game_data.load_item_data()
        self.game_data.load_magic_data()
        self.file_path = ""
        self.buffer = bytearray()
        self.gf_entries = []
        self.character_entries = []
        self.config = None
        self.misc = None
        self.item_entries = []
        # "extended": the FFNx AddMoreItems block is in use (255 slots); "stale": a block is
        # there but FFNx would ignore it (damaged, or the item table changed since); "none".
        self.item_extension = "none"
        # The same states for FFNx AddMoreAbility's learned-ability block.
        self.ability_extension = "none"

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            raw = in_file.read()
        if len(raw) < 4:
            raise ValueError(f"{file_path} is too small to be a .ff8 save file")
        compressed_size = struct.unpack_from("<I", raw, 0)[0]
        payload = raw[4:4 + compressed_size]
        image = lzss_decompress(payload)
        if len(image) != IMAGE_SIZE:
            raise ValueError(
                f"{file_path}: decompressed to {len(image)} bytes, expected {IMAGE_SIZE} — "
                "not a valid FF8 Steam .ff8 save file")
        self.buffer = bytearray(image)
        self._verify_crc(f"{file_path}: stored checksum does not match the computed one — "
                          "refusing to load a file this tool cannot verify it understands "
                          "correctly (no changes made).")
        self._parse()

    def _verify_crc(self, error_message):
        stored1 = struct.unpack_from("<H", self.buffer, CRC_OFFSET_1)[0]
        stored2 = struct.unpack_from("<H", self.buffer, CRC_OFFSET_2)[0]
        computed = crc16_ff8(self.buffer[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN])
        if not (stored1 == stored2 == computed):
            raise ValueError(
                f"{error_message} (stored 0x{stored1:04X}/0x{stored2:04X}, computed 0x{computed:04X})")

    def _parse(self):
        self.ability_extension = self._ability_extension_state()
        self.gf_entries = [
            HyneGfEntry(self, GAMESTATE_BASE + GF_DATA_OFFSET + i * GF_ENTRY_SIZE, i)
            for i in range(NB_GF)
        ]
        self.character_entries = [
            CharacterEntry(self.buffer, GAMESTATE_BASE + CHARACTER_DATA_OFFSET + i * CHARACTER_ENTRY_SIZE,
                          i, self.game_data)
            for i in range(NB_CHARACTERS)
        ]
        self.config = ConfigEntry(self.buffer, GAMESTATE_BASE + CONFIG_DATA_OFFSET)
        self.misc = MiscEntry(self.buffer, GAMESTATE_BASE + MISC_DATA_OFFSET, self.game_data)
        self.item_extension = self._item_extension_state()
        if self.item_extension == "extended":
            self.item_entries = [
                ItemEntry(self.buffer, ITEM_EXT_OFFSET + ITEM_EXT_HEADER_SIZE + i * ITEM_ENTRY_SIZE, i,
                          self.game_data)
                for i in range(ITEM_EXT_SLOTS)
            ]
        else:
            self.item_entries = [
                ItemEntry(self.buffer, GAMESTATE_BASE + ITEMS_DATA_OFFSET + i * ITEM_ENTRY_SIZE, i,
                          self.game_data)
                for i in range(NB_ITEMS)
            ]

    # ── FFNx AddMoreItems inventory block ────────────────────────────────

    def _native_item_bytes(self):
        start = GAMESTATE_BASE + ITEMS_DATA_OFFSET
        return bytes(self.buffer[start:start + NB_ITEMS * ITEM_ENTRY_SIZE])

    def _item_extension_state(self):
        """What FFNx would make of the block (see the module docstring)."""
        magic, version, slots, checksum = struct.unpack_from("<IHHI", self.buffer, ITEM_EXT_OFFSET)
        if magic != ITEM_EXT_MAGIC:
            return "none"
        slot_bytes = bytes(self.buffer[ITEM_EXT_OFFSET + ITEM_EXT_HEADER_SIZE:ITEM_EXT_OFFSET + ITEM_EXT_SIZE])
        if version != ITEM_EXT_VERSION or slots != ITEM_EXT_SLOTS or checksum != item_extension_checksum(slot_bytes):
            return "stale"
        pairs = list(zip(slot_bytes[0::2], slot_bytes[1::2]))
        ids = [item_id for item_id, _ in pairs if item_id]
        if (any(q > ITEM_MAX_QUANTITY or (not i and q) or (i and not q) for i, q in pairs)
                or len(ids) != len(set(ids))):
            return "stale"
        if slot_bytes[:NB_ITEMS * ITEM_ENTRY_SIZE] != self._native_item_bytes():
            return "stale"
        return "extended"

    def enable_item_extension(self):
        """Give the save FFNx AddMoreItems' 255 slots: a new block holding the item table's 198
        slots, then 57 empty ones. A stale block is replaced the same way FFNx would."""
        if self.item_extension == "extended":
            return
        slot_bytes = self._native_item_bytes() + bytes(2 * (ITEM_EXT_SLOTS - NB_ITEMS))
        self._write_item_extension(slot_bytes)
        self._parse()

    def _write_item_extension(self, slot_bytes):
        struct.pack_into("<IHHI", self.buffer, ITEM_EXT_OFFSET, ITEM_EXT_MAGIC, ITEM_EXT_VERSION,
                         ITEM_EXT_SLOTS, item_extension_checksum(slot_bytes))
        self.buffer[ITEM_EXT_OFFSET + ITEM_EXT_HEADER_SIZE:ITEM_EXT_OFFSET + ITEM_EXT_SIZE] = slot_bytes

    def _sync_item_extension(self):
        """Before a save with the block: make its slots valid for FFNx, copy the first 198 into the
        savemap's item table (which FFNx compares them with, and the vanilla game reads), and
        recompute its checksum."""
        start = ITEM_EXT_OFFSET + ITEM_EXT_HEADER_SIZE
        slot_bytes = bytes(self.buffer[start:start + 2 * ITEM_EXT_SLOTS])
        pairs = normalize_item_slots(list(zip(slot_bytes[0::2], slot_bytes[1::2])))
        slot_bytes = bytes(byte for pair in pairs for byte in pair)
        native = GAMESTATE_BASE + ITEMS_DATA_OFFSET
        self.buffer[native:native + NB_ITEMS * ITEM_ENTRY_SIZE] = slot_bytes[:NB_ITEMS * ITEM_ENTRY_SIZE]
        self._write_item_extension(slot_bytes)

    # ── FFNx AddMoreAbility learned-ability block ────────────────────────

    def _native_learned_bytes(self):
        """The 16 GFs' savemap learned fields (ids 0-127), one after the other."""
        fields = bytearray()
        for gf in range(NB_GF):
            start = GAMESTATE_BASE + GF_DATA_OFFSET + gf * GF_ENTRY_SIZE + GF_LEARNED_OFFSET
            fields += self.buffer[start:start + ABILITY_EXT_GF_BYTES]
        return bytes(fields)

    def _ability_extension_state(self):
        """What FFNx would make of the block (see the module docstring)."""
        magic, version, gf_count, checksum = struct.unpack_from("<IHHI", self.buffer, ABILITY_EXT_OFFSET)
        if magic != ABILITY_EXT_MAGIC:
            return "none"
        data = bytes(self.buffer[ABILITY_EXT_NATIVE:ABILITY_EXT_OFFSET + ABILITY_EXT_SIZE])
        if version != ABILITY_EXT_VERSION or gf_count != NB_GF or checksum != item_extension_checksum(data):
            return "stale"
        if data[:NB_GF * ABILITY_EXT_GF_BYTES] != self._native_learned_bytes():
            return "stale"
        return "extended"

    def extended_ability_bit(self, gf_id, ability_id):
        """(buffer position, bit mask) of a learned id 128+ in the block."""
        byte_index, bit = divmod(ability_id - LEARNED_ABILITY_BITS, 8)
        return ABILITY_EXT_EXTENDED + gf_id * ABILITY_EXT_GF_BYTES + byte_index, 1 << bit

    def enable_ability_extension(self):
        """Give the save FFNx AddMoreAbility's block, with no id past 127 learned yet. A stale
        block is replaced the same way FFNx would."""
        if self.ability_extension == "extended":
            return
        self.buffer[ABILITY_EXT_EXTENDED:ABILITY_EXT_OFFSET + ABILITY_EXT_SIZE] = bytes(NB_GF * ABILITY_EXT_GF_BYTES)
        self.ability_extension = "extended"
        self._sync_ability_extension()

    def _sync_ability_extension(self):
        """Before a save with the block: copy the savemap's learned fields into it (FFNx compares
        them) and recompute its checksum."""
        self.buffer[ABILITY_EXT_NATIVE:ABILITY_EXT_EXTENDED] = self._native_learned_bytes()
        data = bytes(self.buffer[ABILITY_EXT_NATIVE:ABILITY_EXT_OFFSET + ABILITY_EXT_SIZE])
        struct.pack_into("<IHHI", self.buffer, ABILITY_EXT_OFFSET, ABILITY_EXT_MAGIC, ABILITY_EXT_VERSION,
                         NB_GF, item_extension_checksum(data))

    def save_file(self, file_path="", backup=True):
        if not file_path:
            file_path = self.file_path
        if backup and os.path.exists(file_path):
            shutil.copy2(file_path, file_path + ".bak")

        if self.item_extension == "extended":
            self._sync_item_extension()   # before the CRC: it covers the item table
        if self.ability_extension == "extended":
            self._sync_ability_extension()
        crc = crc16_ff8(bytes(self.buffer[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
        struct.pack_into("<H", self.buffer, CRC_OFFSET_1, crc)
        struct.pack_into("<H", self.buffer, CRC_OFFSET_2, crc)

        compressed = lzss_compress(bytes(self.buffer))
        # Hard safety gate: Save_EmuMC_CreateFile@0x4c4fa0 allots exactly one 8192-byte memory-
        # card "block" per save file. Anything at or above that silently claims a second block,
        # corrupting the emulator's block accounting - the game then flags the slot "unused
        # block" and deletes the file (this broke a real save before this check existed). Fail
        # loudly instead of writing a file the game will reject.
        if len(compressed) + 4 >= IMAGE_SIZE:
            raise ValueError(
                f"Compressed save would be {len(compressed) + 4} bytes, at/over the "
                f"{IMAGE_SIZE}-byte single-block limit the game's memory-card emulation enforces "
                "per save file - refusing to write a file it would reject as \"unused block\".")
        # Round-trip the exact bytes we're about to write before committing to disk - this is
        # the one guard that would have caught the original all-literal bug (whose output DID
        # decompress back correctly; it was the emulator's block accounting, not the LZSS
        # stream, that broke) as well as any future encoder regression.
        if lzss_decompress(compressed) != bytes(self.buffer):
            raise ValueError("Internal error: recompressed data does not decompress back to the "
                             "buffer being saved - refusing to write a corrupt file.")

        file_bytes = struct.pack("<I", len(compressed)) + compressed
        with open(file_path, "wb") as out_file:
            out_file.write(file_bytes)

        update_metadata_for_save(file_path, file_bytes)
