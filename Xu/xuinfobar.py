"""The Scan screen's one-line info bar (text layer 1), built the way the game builds it.

manageScanText_Dup (0xB68390, FF8_EN.exe) fills the lines the TextPager shows one at a time, from
the kernel's misc texts (getAddressTextMisc) and the target's battle slot:

  1. MISC_LEVEL " " level " " MISC_HP " " current "/" max - both HP "?????" (MISC_5_QUESTION_MARKS)
     when the slot has the HP-hidden flag (0x2000), or each one above 99999;
  2. monsters only: MISC_UNDEAD and/or MISC_FLY, then MISC_MONSTER, when the .dat info flags have
     Zombie / Fly;
  3. without the HP-hidden flag, one line per affinity group that has an element: the group's text
     (MISC_VERY_WEAK_AGAINST + group) then the element names (MISC_ELEM_FIRE + element), the slot's
     elem_def being <= 600 / 601-799 / 801-899 / 900 / > 900 (ScanText_CollectElementsByAffinity);
  4. monsters only: the text the AI set with setScanText (opcode 0x25), when one is set.

The space and the "/" are characters 0 and 18 of MISC_NUMBERS_SYMBOLS, the digits its characters
1-10 (getNumberInTextFromKernel). concatenateTwoStringWithSpaceOrNext puts the separator between
every two parts, empty ones included (a trailing separator, which draws nothing).

A monster's slot gets (setMonsterInfoFromDatInfoSection 0x48BBD0) its level capped at 100, its HP
from the .dat curve (Stat_ComputeMonsterMaxHP) and elem_def = 10 x the .dat byte; Ifrit shows that
byte as the damage % 900 - 10 x byte (and writes floor((900 - value) / 10)).

Nothing here knows a text: they all come from the kernel.bin the user opened.
"""
from dataclasses import dataclass, field

# FF8KernelMiscText indices (the misc text pointer section of kernel.bin)
MISC_NUMBERS_SYMBOLS = 0x0B
MISC_LEVEL = 0x21
MISC_HP = 0x22
MISC_MONSTER = 0x24
MISC_VERY_WEAK_AGAINST = 0x25    # then weak, strong, has no effect, absorbs (0x25-0x29)
MISC_FLY = 0x63
MISC_ELEM_FIRE = 0x65            # the 8 element names (icons) 0x65-0x6C, in elem_def order
MISC_5_QUESTION_MARKS = 0x71
MISC_UNDEAD = 0x72
MISC_TEXT_SECTION_ID = 56        # kernel.bin "Misc text section" (pointers: section 31)

SYMBOL_SPACE, SYMBOL_SLASH = 0, 18   # characters of MISC_NUMBERS_SYMBOLS
SYMBOL_FIRST_DIGIT = 1
NO_SEPARATOR = 0x07                  # concatenateTwoStringWithSpaceOrNext adds no separator for 7
MAX_SHOWN_NUMBER = 99999             # 5 digits; the game shows "?????" above
MAX_LEVEL = 100
BATTLE_FLAG_HP_HIDDEN = 0x2000
SCAN_TEXT_SIZE = 24                  # setScanText copies at most 24 bytes, the end byte included
CLEAR_SCAN_TEXT = 0xFF               # setScanText's text id that clears it
SET_SCAN_TEXT_OPCODE = 0x25
ELEMENT_COUNT = 8
AFFINITY_GROUPS = ("Very weak against", "Weak against", "Strong against", "Has no effect", "Absorbs")
LINE_TICKS = 45                      # TextPager: a line stays 45 ticks (3 s), then the next one

# Text icon codes (0x05 + code): code >= 0x40 is an entry of the exe's TEXT_ICON_CODE_TO_SPRITE
# table, 0x30-0x3F is the icon.sp1 id code + 80 (Text_RenderGlyphs 0x4A1570)
ICON_TABLE_FIRST_CODE = 0x40
DIRECT_ICON_CODES = range(0x30, 0x40)
DIRECT_ICON_SHIFT = 80


def affinity_group(elem_def: int):
    """The info bar group (0-4) of an elem_def value, None for the normal 800 band."""
    if elem_def <= 600:
        return 0
    if elem_def < 800:
        return 1
    if 800 < elem_def < 900:
        return 2
    if elem_def == 900:
        return 3
    if elem_def > 900:
        return 4
    return None


@dataclass
class InfoBarSubject:
    """What the info bar reads from the battle slot."""
    level: int = 1
    current_hp: int = 0
    max_hp: int = 0
    hp_hidden: bool = False
    monster: bool = True
    zombie: bool = False
    fly: bool = False
    elem_def: list = field(default_factory=lambda: [800] * ELEMENT_COUNT)  # the slot values

    @classmethod
    def from_info_stat(cls, info_stat, level: int):
        """A monster's slot at a level, from its .dat section 7 (Ifrit's info_stat_data)."""
        from FF8GameData.dat.monsterstatcurve import monster_hp
        level = max(0, min(int(level), MAX_LEVEL))
        hp = monster_hp(list(info_stat['hp'][:4]), level) & 0xFFFFFFFF
        flags = info_stat.get('byte_flag_1', {})
        return cls(level=level, current_hp=hp, max_hp=hp, hp_hidden=bool(flags.get('Hidden HP')),
                   monster=True, zombie=bool(flags.get('Zombie')), fly=bool(flags.get('Fly')),
                   elem_def=[10 * ((900 - int(value)) // 10) for value in info_stat['elem_def'][:ELEMENT_COUNT]])


@dataclass
class InfoBarLine:
    label: str      # what the line is, for the selector
    data: bytes     # the FF8-encoded line the game draws


def misc_texts_from_kernel(game_data, kernel_path) -> list:
    """The kernel.bin misc texts (FF8 bytes, no end byte), by FF8KernelMiscText index."""
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    if not getattr(game_data, "kernel_data_json", None):
        game_data.load_kernel_data()
    kernel = KernelManager(game_data)
    kernel.load_file(str(kernel_path))
    for section in kernel.section_list:
        if section.id == MISC_TEXT_SECTION_ID:
            return [bytes(text.get_data_hex()).split(b"\x00")[0] for text in section.get_text_list()]
    raise ValueError("no misc text section in this kernel.bin")


def icon_table_from_exe(exe: bytes, exe_data_json: dict) -> dict:
    """{text icon code: icon.sp1 id} of an FF8 exe (its TEXT_ICON_CODE_TO_SPRITE table)."""
    from Xu.xumanager import exe_language_prefix
    offsets = exe_data_json["text_icon_sprite_offset"]
    prefix = exe_language_prefix(exe, exe_data_json)
    start = offsets["eng_section_start"] + (offsets[f"{prefix}_offset"] if prefix else 0)
    count = offsets["nb_code"]
    table = exe[start:start + 2 * count]
    if len(table) != 2 * count:
        raise ValueError("the exe is too short for the text icon table")
    return {offsets["first_code"] + i: int.from_bytes(table[2 * i:2 * i + 2], "little") for i in range(count)}


def icon_sprite_id(code: int, icon_table: dict):
    """The icon.sp1 id the game draws for a text icon code, None when it cannot be known here
    (no exe table, or a pad button icon, which follows the player's key config)."""
    if code >= ICON_TABLE_FIRST_CODE:
        return icon_table.get(code)
    if code in DIRECT_ICON_CODES:
        return code + DIRECT_ICON_SHIFT
    return None


class InfoBarBuilder:
    """Builds the lines from the kernel misc texts."""

    def __init__(self, misc_texts: list):
        self.misc = misc_texts

    def text(self, index) -> bytes:
        return self.misc[index] if 0 <= index < len(self.misc) else b""

    def symbol(self, index) -> int:
        symbols = self.text(MISC_NUMBERS_SYMBOLS)
        return symbols[index] if index < len(symbols) else 0

    def number(self, value: int) -> bytes:
        """getNumberInTextFromKernel: the decimal digits of value % 100000, no leading zero."""
        digits = str(int(value) % 100000)
        return bytes(self.symbol(SYMBOL_FIRST_DIGIT + int(d)) for d in digits)

    @staticmethod
    def join(parts, separator: int) -> bytes:
        """concatenateTwoStringWithSpaceOrNext over the parts, left to right."""
        result = parts[0]
        for part in parts[1:]:
            result += (bytes((separator,)) if separator != NO_SEPARATOR else b"") + part
        return result

    def lines(self, subject: InfoBarSubject, scan_text: bytes = b"") -> list:
        space, slash = self.symbol(SYMBOL_SPACE), self.symbol(SYMBOL_SLASH)
        hidden = self.text(MISC_5_QUESTION_MARKS)
        current = max_hp = hidden
        if not subject.hp_hidden:
            if subject.current_hp <= MAX_SHOWN_NUMBER:
                current = self.number(subject.current_hp)
            if subject.max_hp <= MAX_SHOWN_NUMBER:
                max_hp = self.number(subject.max_hp)
        level_hp = self.join((self.text(MISC_LEVEL), self.number(subject.level), self.text(MISC_HP), current),
                             space) + self.join((b"", max_hp), slash)
        result = [InfoBarLine("Level and HP", level_hp)]
        if subject.monster:
            kinds = [self.text(MISC_UNDEAD)] if subject.zombie else []
            kinds += [self.text(MISC_FLY)] if subject.fly else []
            if kinds:
                parts = kinds + [self.text(MISC_MONSTER)]
                parts += [b""] * (4 - len(parts))  # the game always joins 4 parts
                label = " ".join(name for name, on in (("Undead", subject.zombie), ("Fly", subject.fly)) if on)
                result.append(InfoBarLine(f"{label} monster", self.join(parts, space)))
        if not subject.hp_hidden:
            for group, group_label in enumerate(AFFINITY_GROUPS):
                elements = [i for i, value in enumerate(subject.elem_def[:ELEMENT_COUNT])
                            if affinity_group(value) == group]
                if elements:
                    parts = [self.text(MISC_VERY_WEAK_AGAINST + group)]
                    parts += [self.text(MISC_ELEM_FIRE + i) for i in elements]
                    parts += [b""] * (9 - len(parts))  # 1 group text + 8 element slots
                    result.append(InfoBarLine(f"{group_label} ({len(elements)})", self.join(parts, space)))
        if subject.monster and scan_text:
            result.append(InfoBarLine("AI scan text (setScanText)", scan_text_bytes(scan_text)))
        return result


def scan_text_bytes(text: bytes) -> bytes:
    """What setScanText keeps of a battle text: 24 bytes, the end byte included."""
    return bytes(text).split(b"\x00")[0][:SCAN_TEXT_SIZE - 1]


def ai_scan_texts(battle_script_data) -> list:
    """[(text id, FF8 bytes, section index)] of every setScanText call of a monster's AI that sets a
    text (id 0xFF clears it), in AI order, each text id once."""
    texts = battle_script_data.get('battle_text', [])
    found, seen = [], set()
    for section_index, section in enumerate(battle_script_data.get('ai_data', [])):
        commands = section.get('command', []) if isinstance(section, dict) else []
        for command in commands:
            if command.get_id() != SET_SCAN_TEXT_OPCODE:
                continue
            params = command.get_op_code()
            text_id = params[0] if params else CLEAR_SCAN_TEXT
            if text_id == CLEAR_SCAN_TEXT or text_id in seen or text_id >= len(texts):
                continue
            seen.add(text_id)
            found.append((text_id, bytes(texts[text_id].get_data_hex()), section_index))
    return found
