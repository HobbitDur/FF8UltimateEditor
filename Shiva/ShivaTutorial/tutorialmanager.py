"""Tutorial demo editor logic (was the Trepies tool), for the demo data in mngrp.bin.

The tutorial menu demos (Junction/GF/limit break/character switch) are driven by
three kinds of mngrp.bin raw sections (see the wiki page
FF8/TechnicalReference/Menu/Menu_mngrp_demo_script.md and the demo record table
Menu_TutorialDemoRecords @0xB88360 in FF8_EN.exe):

  * demo input scripts (raw 168-175 and 205): a stream of UInt16 LE words,
    high nibble = opcode, low 12 bits = operand, interpreted per frame by
    Menu_ReadPad_OrRunDemoScript (0x4BE100) to fake controller input and show
    caption windows;
  * mock save characters (raw 176/178): 8 records of 152 bytes in the savemap
    character format (current HP forced to 9999 at load);
  * mock save GFs (raw 177/179): 16 records of 68 bytes in the savemap GF
    format (HP forced to 9999, names replaced by the real save's names).

Sections are addressed by RAW mngrphd.bin slot (entry = header + 8 * slot);
bit 0 of the stored seek is the "stored uncompressed" flag, always set on PC.
Unlike the ShumiTranslator save path (which normalises text and padding), this
manager patches only the edited raw slots: an unmodified load/save round-trip
is byte-exact for both mngrp.bin and mngrphd.bin.
"""

import struct

from FF8GameData.gamedata import GameData
from FF8GameData.GenericSection.section import Section

SECTOR_SIZE = 0x800  # mngrp.bin sections are stored 0x800-aligned

# Opcode -> mnemonic (high nibble of each script word, low 12 bits = operand).
DEMO_OPCODE_NAMES = {
    0x1: "HOLD_BUTTON",
    0x2: "WAIT_WINDOW_READY",
    0x3: "SHOW_TEXT",
    0x4: "HIDE_TEXT",
    0x5: "SET_TEXT_INDEX",
    0x6: "SET_TEXT_X",
    0x7: "SET_TEXT_Y",
    0x8: "WAIT_CONFIRM",
    0x9: "WAIT",
    0xA: "WAIT_ANIM",
    0xF: "END",
}
DEMO_OPCODE_IDS = {name: opcode for opcode, name in DEMO_OPCODE_NAMES.items()}

# Opcodes that take a meaningful operand (the others always store 0).
DEMO_OPCODES_WITH_OPERAND = {0x1, 0x5, 0x6, 0x7, 0x9}

# HOLD_BUTTON operand = bit index ORed into the engine pad word
# (PAD_PRESSED/PAD_REPEAT). Bits 0-11 are the physical button slots consumed
# through the button-config remap (sub_4A2D60, identity with default config),
# bits 12-15 the D-pad (passed through unchanged; order confirmed from the
# mouse-to-direction synthesizer sub_49EFE0 angle math).
PAD_BIT_NAMES = {
    0: "L2",
    1: "R2",
    2: "L1 (prev char/page)",
    3: "R1 (next char/page)",
    4: "Triangle (Cancel)",
    5: "Circle (Menu)",
    6: "Cross (Confirm)",
    7: "Square (Examine)",
    8: "Select",
    11: "Start",
    12: "Left",
    13: "Down",
    14: "Right",
    15: "Up",
}

# Demo record table (Menu_TutorialDemoRecords @0xB88360): script slot ->
# (demo name, caption text slot, mock character slot, mock GF slot).
DEMO_INFO = {
    168: ("Junction demo", 160, 176, 177),
    169: ("Magic junction demo", 161, 176, 177),
    170: ("Elemental junction demo", 162, 178, 179),
    171: ("Status junction demo", 163, 178, 179),
    172: ("GF demo", 164, 176, 177),
    173: ("Limit break demo (Squall)", 165, 176, 177),
    174: ("Limit break demo (Zell)", 166, 176, 177),
    175: ("Limit break demo (Rinoa)", 167, 176, 177),
    205: ("Character switch demo", 204, 178, 179),
}
SCRIPT_SLOTS = tuple(DEMO_INFO)
MOCK_CHAR_SLOTS = (176, 178)
MOCK_GF_SLOTS = (177, 179)
CAPTION_SLOTS = tuple(info[1] for info in DEMO_INFO.values())

# Savemap record order (fixed by the save format, not by the mock files).
CHARACTER_NAMES = ("Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea")
GF_NAMES = ("Quezacotl", "Shiva", "Ifrit", "Siren", "Brothers", "Diablos", "Carbuncle", "Leviathan",
            "Pandemona", "Cerberus", "Alexander", "Doomtrain", "Bahamut", "Cactuar", "Tonberry", "Eden")

NB_CHARACTER_RECORDS = 8
CHARACTER_RECORD_SIZE = 152
NB_GF_RECORDS = 16
GF_RECORD_SIZE = 68
NB_MAGIC_SLOTS = 32
NB_GF_COMPATIBILITY = 16
NB_GF_AP_SLOTS = 24
GF_NAME_SIZE = 12
GF_COMPLETE_ABILITIES_SIZE = 16


class DemoScriptOp:
    """One UInt16 script word: opcode (high nibble) + operand (low 12 bits)."""

    def __init__(self, opcode: int, operand: int = 0):
        self.opcode = opcode & 0xF
        self.operand = operand & 0xFFF

    @classmethod
    def from_word(cls, word: int):
        return cls(word >> 12, word & 0xFFF)

    @property
    def word(self):
        return (self.opcode << 12) | self.operand

    @property
    def name(self):
        return DEMO_OPCODE_NAMES.get(self.opcode, f"OPCODE_0x{self.opcode:X}")

    def describe(self, captions=None):
        """Human hint for the operand (button name, caption preview...)."""
        if self.opcode == 0x1:
            return PAD_BIT_NAMES.get(self.operand & 0xFF, f"pad bit {self.operand & 0xFF}")
        if self.opcode == 0x9:
            return f"{self.operand} frames"
        if self.opcode == 0x5 and captions is not None and self.operand < len(captions):
            caption = (captions[self.operand] or "").replace("\n", " / ")
            return caption if len(caption) <= 60 else caption[:57] + "..."
        return ""

    def __str__(self):
        if self.opcode in DEMO_OPCODES_WITH_OPERAND or self.opcode not in DEMO_OPCODE_NAMES:
            return f"{self.name} {self.operand}"
        return self.name


class DemoScript:
    """A demo input script section: ops up to and including END + raw tail.

    The tail (zero padding after END in the vanilla files) is preserved so an
    untouched script serialises back byte-exactly.
    """

    def __init__(self, raw_slot: int, data: bytes):
        self.raw_slot = raw_slot
        self.ops = []
        self.tail = b""
        pos = 0
        while pos + 2 <= len(data):
            op = DemoScriptOp.from_word(struct.unpack_from("<H", data, pos)[0])
            self.ops.append(op)
            pos += 2
            if op.opcode == 0xF:
                break
        self.tail = bytes(data[pos:])

    @property
    def name(self):
        return DEMO_INFO[self.raw_slot][0]

    def to_bytes(self):
        data = bytearray()
        for op in self.ops:
            data.extend(struct.pack("<H", op.word))
        data.extend(self.tail)
        return bytes(data)

    def to_text(self, captions=None):
        """Readable, re-importable op list (one op per line, ; = comment)."""
        lines = [f"; Trepies demo script, raw slot {self.raw_slot} ({self.name})"]
        offset = 0
        for op in self.ops:
            line = str(op)
            hint = op.describe(captions)
            if hint:
                line = f"{line:<24}; {hint}"
            lines.append(line)
            offset += 2
        return "\n".join(lines) + "\n"

    def set_ops_from_text(self, text: str):
        """Parse a to_text() style listing back into self.ops."""
        ops = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            mnemonic = parts[0].upper()
            if mnemonic in DEMO_OPCODE_IDS:
                opcode = DEMO_OPCODE_IDS[mnemonic]
            elif mnemonic.startswith("OPCODE_0X"):
                opcode = int(mnemonic[len("OPCODE_0X"):], 16)
            else:
                raise ValueError(f"line {line_number}: unknown opcode '{parts[0]}'")
            operand = 0
            if len(parts) > 1:
                operand = int(parts[1], 0)
                if not 0 <= operand <= 0xFFF:
                    raise ValueError(f"line {line_number}: operand {operand} out of range (0-4095)")
            elif opcode in DEMO_OPCODES_WITH_OPERAND:
                raise ValueError(f"line {line_number}: {mnemonic} needs an operand")
            ops.append(DemoScriptOp(opcode, operand))
        if not ops or ops[-1].opcode != 0xF:
            raise ValueError("script must end with an END op")
        self.ops = ops


class RecordBytes:
    """Fixed-size record edited in place: field properties read/write the raw
    bytes, so unknown/padding bytes survive byte-exactly."""

    RECORD_SIZE = 0

    def __init__(self, data: bytes):
        if len(data) != self.RECORD_SIZE:
            raise ValueError(f"expected {self.RECORD_SIZE} bytes, got {len(data)}")
        self._data = bytearray(data)

    def to_bytes(self):
        return bytes(self._data)

    def _get_u8(self, offset):
        return self._data[offset]

    def _set_u8(self, offset, value):
        self._data[offset] = int(value) & 0xFF

    def _get_u16(self, offset):
        return struct.unpack_from("<H", self._data, offset)[0]

    def _set_u16(self, offset, value):
        struct.pack_into("<H", self._data, offset, int(value) & 0xFFFF)

    def _get_u32(self, offset):
        return struct.unpack_from("<I", self._data, offset)[0]

    def _set_u32(self, offset, value):
        struct.pack_into("<I", self._data, offset, int(value) & 0xFFFFFFFF)


def _u8_property(offset):
    return property(lambda self: self._get_u8(offset),
                    lambda self, value: self._set_u8(offset, value))


def _u16_property(offset):
    return property(lambda self: self._get_u16(offset),
                    lambda self, value: self._set_u16(offset, value))


def _u32_property(offset):
    return property(lambda self: self._get_u32(offset),
                    lambda self, value: self._set_u32(offset, value))


class CharacterRecord(RecordBytes):
    """One 152-byte savemap character record (GameSaveFormat.md layout)."""

    RECORD_SIZE = CHARACTER_RECORD_SIZE

    def __init__(self, record_id: int, name: str, data: bytes):
        RecordBytes.__init__(self, data)
        self.record_id = record_id
        self.name = name

    current_hp = _u16_property(0x00)
    max_hp = _u16_property(0x02)
    exp = _u32_property(0x04)
    model_id = _u8_property(0x08)
    weapon_id = _u8_property(0x09)
    stat_str = _u8_property(0x0A)
    stat_vit = _u8_property(0x0B)
    stat_mag = _u8_property(0x0C)
    stat_spr = _u8_property(0x0D)
    stat_spd = _u8_property(0x0E)
    stat_lck = _u8_property(0x0F)
    abilities = _u32_property(0x54)
    junctioned_gfs = _u16_property(0x58)
    unknown_0x5a = _u8_property(0x5A)
    alternative_model = _u8_property(0x5B)
    junction_hp = _u8_property(0x5C)
    junction_str = _u8_property(0x5D)
    junction_vit = _u8_property(0x5E)
    junction_mag = _u8_property(0x5F)
    junction_spr = _u8_property(0x60)
    junction_spd = _u8_property(0x61)
    junction_eva = _u8_property(0x62)
    junction_hit = _u8_property(0x63)
    junction_lck = _u8_property(0x64)
    junction_elem_attack = _u8_property(0x65)
    junction_mental_attack = _u8_property(0x66)
    unknown_0x6f = _u8_property(0x6F)
    kills = _u16_property(0x90)
    kos = _u16_property(0x92)
    exists = _u8_property(0x94)
    unknown_0x95 = _u8_property(0x95)
    mental_status = _u8_property(0x96)
    unknown_0x97 = _u8_property(0x97)

    def get_magic(self, slot):
        return self._data[0x10 + slot * 2], self._data[0x11 + slot * 2]

    def set_magic(self, slot, magic_id, quantity):
        self._data[0x10 + slot * 2] = int(magic_id) & 0xFF
        self._data[0x11 + slot * 2] = int(quantity) & 0xFF

    @property
    def commands(self):
        return list(self._data[0x50:0x53])

    @commands.setter
    def commands(self, values):
        self._data[0x50:0x53] = bytes(int(value) & 0xFF for value in values[:3])

    command_padding = _u8_property(0x53)

    @property
    def junction_elem_defense(self):
        return list(self._data[0x67:0x6B])

    @junction_elem_defense.setter
    def junction_elem_defense(self, values):
        self._data[0x67:0x6B] = bytes(int(value) & 0xFF for value in values[:4])

    @property
    def junction_mental_defense(self):
        return list(self._data[0x6B:0x6F])

    @junction_mental_defense.setter
    def junction_mental_defense(self, values):
        self._data[0x6B:0x6F] = bytes(int(value) & 0xFF for value in values[:4])

    def get_gf_compatibility(self, gf_index):
        return self._get_u16(0x70 + gf_index * 2)

    def set_gf_compatibility(self, gf_index, value):
        self._set_u16(0x70 + gf_index * 2, value)

    def to_dict(self):
        return {
            "name": self.name,
            "current_hp": self.current_hp, "max_hp": self.max_hp, "exp": self.exp,
            "model_id": self.model_id, "weapon_id": self.weapon_id,
            "str": self.stat_str, "vit": self.stat_vit, "mag": self.stat_mag,
            "spr": self.stat_spr, "spd": self.stat_spd, "lck": self.stat_lck,
            "magics": [list(self.get_magic(slot)) for slot in range(NB_MAGIC_SLOTS)],
            "commands": self.commands, "command_padding": self.command_padding,
            "abilities": self.abilities, "junctioned_gfs": self.junctioned_gfs,
            "unknown_0x5a": self.unknown_0x5a, "alternative_model": self.alternative_model,
            "junction_hp": self.junction_hp, "junction_str": self.junction_str,
            "junction_vit": self.junction_vit, "junction_mag": self.junction_mag,
            "junction_spr": self.junction_spr, "junction_spd": self.junction_spd,
            "junction_eva": self.junction_eva, "junction_hit": self.junction_hit,
            "junction_lck": self.junction_lck,
            "junction_elem_attack": self.junction_elem_attack,
            "junction_mental_attack": self.junction_mental_attack,
            "junction_elem_defense": self.junction_elem_defense,
            "junction_mental_defense": self.junction_mental_defense,
            "unknown_0x6f": self.unknown_0x6f,
            "gf_compatibility": [self.get_gf_compatibility(i) for i in range(NB_GF_COMPATIBILITY)],
            "kills": self.kills, "kos": self.kos, "exists": self.exists,
            "unknown_0x95": self.unknown_0x95, "mental_status": self.mental_status,
            "unknown_0x97": self.unknown_0x97,
        }

    def from_dict(self, values: dict):
        for key in ("current_hp", "max_hp", "exp", "model_id", "weapon_id",
                    "abilities", "junctioned_gfs", "unknown_0x5a", "alternative_model",
                    "junction_hp", "junction_str", "junction_vit", "junction_mag",
                    "junction_spr", "junction_spd", "junction_eva", "junction_hit",
                    "junction_lck", "junction_elem_attack", "junction_mental_attack",
                    "unknown_0x6f", "kills", "kos", "exists", "unknown_0x95",
                    "mental_status", "unknown_0x97", "command_padding"):
            if key in values:
                setattr(self, key, values[key])
        for json_key, attr in (("str", "stat_str"), ("vit", "stat_vit"), ("mag", "stat_mag"),
                               ("spr", "stat_spr"), ("spd", "stat_spd"), ("lck", "stat_lck")):
            if json_key in values:
                setattr(self, attr, values[json_key])
        if "magics" in values:
            for slot, (magic_id, quantity) in enumerate(values["magics"][:NB_MAGIC_SLOTS]):
                self.set_magic(slot, magic_id, quantity)
        if "commands" in values:
            self.commands = values["commands"]
        if "junction_elem_defense" in values:
            self.junction_elem_defense = values["junction_elem_defense"]
        if "junction_mental_defense" in values:
            self.junction_mental_defense = values["junction_mental_defense"]
        if "gf_compatibility" in values:
            for gf_index, value in enumerate(values["gf_compatibility"][:NB_GF_COMPATIBILITY]):
                self.set_gf_compatibility(gf_index, value)


class GfRecord(RecordBytes):
    """One 68-byte savemap GF record. The 12-byte name is FF8 text: these are
    the development names ("Quetcoatl"...) that the game overrides with the
    real save's names when the demo loads."""

    RECORD_SIZE = GF_RECORD_SIZE

    def __init__(self, record_id: int, gf_name: str, data: bytes, game_data: GameData):
        RecordBytes.__init__(self, data)
        self.record_id = record_id
        self.gf_name = gf_name  # canonical savemap slot name, not the stored one
        self._game_data = game_data

    exp = _u32_property(0x0C)
    unknown_0x10 = _u8_property(0x10)
    exists = _u8_property(0x11)
    hp = _u16_property(0x12)
    kills = _u16_property(0x3C)
    kos = _u16_property(0x3E)
    unknown_0x40 = _u8_property(0x40)
    learning_ability = _u8_property(0x41)

    @property
    def name(self):
        """Stored (development) name, decoded from FF8 text up to the 0x00."""
        raw = self._data[:GF_NAME_SIZE]
        end = raw.find(0)
        if end == -1:
            end = GF_NAME_SIZE
        return self._game_data.translate_hex_to_str(raw[:end])

    @name.setter
    def name(self, text: str):
        encoded = bytes(self._game_data.translate_str_to_hex(text))
        if len(encoded) >= GF_NAME_SIZE:
            raise ValueError(f"GF name '{text}' too long ({len(encoded)} bytes, max {GF_NAME_SIZE - 1})")
        self._data[:GF_NAME_SIZE] = encoded.ljust(GF_NAME_SIZE, b"\x00")

    @property
    def complete_abilities(self):
        return bytes(self._data[0x14:0x14 + GF_COMPLETE_ABILITIES_SIZE])

    @complete_abilities.setter
    def complete_abilities(self, raw: bytes):
        if len(raw) != GF_COMPLETE_ABILITIES_SIZE:
            raise ValueError(f"complete_abilities must be {GF_COMPLETE_ABILITIES_SIZE} bytes")
        self._data[0x14:0x14 + GF_COMPLETE_ABILITIES_SIZE] = raw

    @property
    def aps(self):
        return list(self._data[0x24:0x24 + NB_GF_AP_SLOTS])

    @aps.setter
    def aps(self, values):
        self._data[0x24:0x24 + NB_GF_AP_SLOTS] = bytes(int(value) & 0xFF for value in values[:NB_GF_AP_SLOTS])

    @property
    def forgotten_abilities(self):
        return bytes(self._data[0x42:0x44])

    @forgotten_abilities.setter
    def forgotten_abilities(self, raw: bytes):
        if len(raw) != 2:
            raise ValueError("forgotten_abilities must be 2 bytes")
        self._data[0x42:0x44] = raw

    def to_dict(self):
        return {
            "gf": self.gf_name,
            "name": self.name,
            "name_raw": self._data[:GF_NAME_SIZE].hex(),
            "exp": self.exp, "unknown_0x10": self.unknown_0x10, "exists": self.exists,
            "hp": self.hp,
            "complete_abilities": self.complete_abilities.hex(),
            "aps": self.aps,
            "kills": self.kills, "kos": self.kos,
            "unknown_0x40": self.unknown_0x40, "learning_ability": self.learning_ability,
            "forgotten_abilities": self.forgotten_abilities.hex(),
        }

    def from_dict(self, values: dict):
        # name_raw keeps a byte-exact round-trip even if the FF8-text codec
        # would normalise the decoded name; an edited "name" wins over it.
        if "name_raw" in values:
            raw = bytes.fromhex(values["name_raw"])
            if len(raw) != GF_NAME_SIZE:
                raise ValueError(f"name_raw must be {GF_NAME_SIZE} bytes")
            self._data[:GF_NAME_SIZE] = raw
        if "name" in values and values["name"] != self.name:
            self.name = values["name"]
        for key in ("exp", "unknown_0x10", "exists", "hp", "kills", "kos",
                    "unknown_0x40", "learning_ability"):
            if key in values:
                setattr(self, key, values[key])
        if "complete_abilities" in values:
            self.complete_abilities = bytes.fromhex(values["complete_abilities"])
        if "aps" in values:
            self.aps = values["aps"]
        if "forgotten_abilities" in values:
            self.forgotten_abilities = bytes.fromhex(values["forgotten_abilities"])


class MockRecordFile:
    """A mock save section: fixed-size records + preserved trailing padding."""

    def __init__(self, raw_slot: int, records: list, tail: bytes):
        self.raw_slot = raw_slot
        self.records = records
        self.tail = tail

    def to_bytes(self):
        data = bytearray()
        for record in self.records:
            data.extend(record.to_bytes())
        data.extend(self.tail)
        return bytes(data)


class TutorialManager:
    """Reads and writes the tutorial demo raw slots inside a shared mngrp.

    The tool it came from (Trepies) loaded mngrp.bin + mngrphd.bin itself and patched only its
    slots on save. Here the file is the shared one Shiva holds: this reads its slots and writes
    them back into it, and Shiva writes the whole file once. A raw slot is a mngrphd entry index,
    which is the position of the section in the full section list, so a slot is reached by that
    position (not by section id, which skips the invalid entries)."""

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self._section_list = []  # The shared mngrp section list, indexed by raw slot
        self.scripts = {}  # raw slot -> DemoScript
        self.mock_char_files = {}  # raw slot -> MockRecordFile of CharacterRecord
        self.mock_gf_files = {}  # raw slot -> MockRecordFile of GfRecord
        self._captions = {}  # caption raw slot -> [str]

    @classmethod
    def from_mngrp(cls, game_data: GameData, mngrp):
        self = cls(game_data)
        self._section_list = mngrp.get_section_list()

        needed = set(SCRIPT_SLOTS) | set(MOCK_CHAR_SLOTS) | set(MOCK_GF_SLOTS)
        missing = sorted(slot for slot in needed
                         if slot >= len(self._section_list) or self._section_list[slot].id == -1)
        if missing:
            raise ValueError(f"mngrp misses tutorial demo raw slots {missing} - not a vanilla-layout mngrp?")

        self.scripts = {slot: DemoScript(slot, self._raw_section(slot)) for slot in SCRIPT_SLOTS}
        self.mock_char_files = {slot: self._parse_char_file(slot) for slot in MOCK_CHAR_SLOTS}
        self.mock_gf_files = {slot: self._parse_gf_file(slot) for slot in MOCK_GF_SLOTS}
        self._captions = {}
        for caption_slot in CAPTION_SLOTS:
            if caption_slot < len(self._section_list) and self._section_list[caption_slot].id != -1:
                self._captions[caption_slot] = self._parse_caption_section(caption_slot)
        return self

    def owned_section_ids(self):
        """The section ids of the slots this editor writes, for Shiva's raw-preserve pass.
        The caption slots are read only, so they are not owned (kept raw like any other)."""
        return {self._section_list[slot].id
                for slot in set(SCRIPT_SLOTS) | set(MOCK_CHAR_SLOTS) | set(MOCK_GF_SLOTS)}

    def save_to_mngrp(self, mngrp):
        """Write each edited slot back into the shared mngrp. Shiva writes the file, and its
        update rebuilds the offsets and the header, so a slot may grow past its sector padding
        without this having to re-lay-out anything.

        set_section_by_id_and_bytearray shifts the following sections' offsets by the size
        change, which a plain list replacement would not, so a grown script stays consistent."""
        section_list = mngrp.get_section_list()
        for slot, data in self._new_section_bytes().items():
            mngrp.set_section_by_id_and_bytearray(section_list[slot].id, bytearray(data))

    def _raw_section(self, raw_slot: int) -> bytes:
        return bytes(self._section_list[raw_slot].get_data_hex())

    def _parse_char_file(self, raw_slot: int) -> MockRecordFile:
        data = self._raw_section(raw_slot)
        records = []
        for record_id in range(NB_CHARACTER_RECORDS):
            start = record_id * CHARACTER_RECORD_SIZE
            records.append(CharacterRecord(record_id, CHARACTER_NAMES[record_id],
                                           data[start:start + CHARACTER_RECORD_SIZE]))
        return MockRecordFile(raw_slot, records, bytes(data[NB_CHARACTER_RECORDS * CHARACTER_RECORD_SIZE:]))

    def _parse_gf_file(self, raw_slot: int) -> MockRecordFile:
        data = self._raw_section(raw_slot)
        records = []
        for record_id in range(NB_GF_RECORDS):
            start = record_id * GF_RECORD_SIZE
            records.append(GfRecord(record_id, GF_NAMES[record_id],
                                    data[start:start + GF_RECORD_SIZE], self.game_data))
        return MockRecordFile(raw_slot, records, bytes(data[NB_GF_RECORDS * GF_RECORD_SIZE:]))

    def _parse_caption_section(self, raw_slot: int):
        """Decoded strings of a caption string section (count, u16 offsets,
        FF8 text), matching how SHOW_TEXT resolves text_index in the exe."""
        data = self._raw_section(raw_slot)
        count = struct.unpack_from("<H", data, 0)[0]
        offsets = list(struct.unpack_from(f"<{count}H", data, 2)) if count else []
        captions = []
        for index, offset in enumerate(offsets):
            if offset == 0:
                captions.append(None)
                continue
            end = len(data)
            for later in offsets[index + 1:]:
                if later:
                    end = later
                    break
            text = data[offset:end].split(b"\x00", 1)[0]
            captions.append(self.game_data.translate_hex_to_str(bytearray(text)))
        return captions

    def get_captions(self, script_slot: int):
        """Caption strings of the text section paired with a demo script."""
        return self._captions.get(DEMO_INFO[script_slot][1], [])

    # ------------------------------------------------------------------ save

    def _new_section_bytes(self):
        """raw slot -> serialised bytes, 0x800-padded, for the editable slots."""
        new_sections = {}
        for slot, script in self.scripts.items():
            new_sections[slot] = self._pad_sector(script.to_bytes())
        for slot, mock_file in {**self.mock_char_files, **self.mock_gf_files}.items():
            new_sections[slot] = self._pad_sector(mock_file.to_bytes())
        return new_sections

    @staticmethod
    def _pad_sector(data: bytes) -> bytes:
        remainder = len(data) % SECTOR_SIZE
        if remainder or not data:
            data += b"\x00" * (SECTOR_SIZE - remainder if remainder else SECTOR_SIZE)
        return data


    # ------------------------------------------------------------------ json

    def to_dict(self):
        return {
            "scripts": {str(slot): {"name": script.name,
                                    "ops": [str(op) for op in script.ops]}
                        for slot, script in self.scripts.items()},
            "mock_characters": {str(slot): [record.to_dict() for record in mock_file.records]
                                for slot, mock_file in self.mock_char_files.items()},
            "mock_gfs": {str(slot): [record.to_dict() for record in mock_file.records]
                         for slot, mock_file in self.mock_gf_files.items()},
        }

    def from_dict(self, values: dict):
        for slot_str, script_dict in values.get("scripts", {}).items():
            script = self.scripts[int(slot_str)]
            script.set_ops_from_text("\n".join(script_dict["ops"]))
        for slot_str, record_dicts in values.get("mock_characters", {}).items():
            records = self.mock_char_files[int(slot_str)].records
            for record, record_dict in zip(records, record_dicts):
                record.from_dict(record_dict)
        for slot_str, record_dicts in values.get("mock_gfs", {}).items():
            records = self.mock_gf_files[int(slot_str)].records
            for record, record_dict in zip(records, record_dicts):
                record.from_dict(record_dict)
