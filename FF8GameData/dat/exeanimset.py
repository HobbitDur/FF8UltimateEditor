"""Battle anim sets stored in the FF8 exe (limit breaks, Blue Magic, Shot, Duel, Angelo...).

Some battle actions do not play the animations of the model files: they bind an "anim set" from
the exe onto the model for the length of the action, with BattleEntity_BindExternalAnimSet
(FF8_EN.exe 0x5022C0). 72 static blocks of the exe's .data are bound that way (73 call sites:
51 push a block address, 22 go through the Renzokuken helpers that bind the caster set and the
boss set(s) of a pack, plus r0win.dat's victory poses, which live in their own file).

A set is::

    +0            u32  section count N (3, or 2 for a model without weapon animations)
    +4            u32  offset of each section, from the start of the set
    +4 + 4N       u32  set size
    section 0     body animations (the .dat section 3 format: u32 count, u32 offsets, animations)
    section 1     AnimSeq sequences (the .dat sequence format: u16 count, u16 offsets, byte code)
    section 2     weapon animations (section 3 format), bound only when the model has a weapon

FFNx (branch BattleAnimSetFiles, docs/ff8/mods/battle_anim_sets.md) loads a set from
<direct_mode_path>/exe/effect_NNN.animset (effect_NNN_K.animset for the K-th set of an effect
that binds several), with no size limit, so a set converted to 30 fps (about 1.7x larger) can be
used although it no longer fits the exe. FFNx recognizes the vanilla set from the effect running
and its contents (size + FNV-1a), which are the same in every release (checked on EN, FR, DE, ES,
IT, JP, JP_NV and the 2000 US exe): `locate_anim_sets` finds them the same way in any exe.

The animations only decode against the bone count of the model they play on, which is not in the
set: `AnimSetInfo.body_bones` / `weapon_bones` (the character's own dXc/dXw models).
"""
import copy
import os
import struct
from dataclasses import dataclass

ANIM_SET_EXTENSION = ".animset"
FFNX_FOLDER = "direct/exe"   # where FFNx reads them, in the game folder
MAX_FILE_SIZE = 0x100000     # FFNx refuses bigger files
BODY_SECTION, SEQUENCE_SECTION, WEAPON_SECTION = 0, 1, 2

# Character -> (battle model prefix, body bone count, weapon bone count or None: no weapon pool).
# Bone counts from the section 1 of each dXc / dXw model (Zell and Kiros carry a reduced weapon
# without animation, Edea none).
CHARACTER_MODELS = {
    "Squall": ("d0c", 23, 2),
    "Zell": ("d1c", 23, None),
    "Irvine": ("d2c", 34, 3),
    "Quistis": ("d3c", 27, 9),
    "Rinoa": ("d4c", 32, 2),
    "Selphie": ("d5c", 25, 7),
    "Seifer": ("d6c", 41, 2),
    "Edea": ("d7c", 35, None),
    "Laguna": ("d8c", 29, 2),
    "Kiros": ("d9c", 35, None),
    "Ward": ("dac", 31, 2),
}
TARGET_MODEL = "Target"   # the boss sets of the Renzokuken packs (no character model)

# effect id -> (character, effect name)
EFFECT_NAMES = {
    71: ("Quistis", "Laser Eye"), 72: ("Quistis", "Aqua Breath"), 73: ("Quistis", "Mighty Guard"),
    74: ("Quistis", "LV? Death"), 184: ("Quistis", "Ultra Waves"), 229: ("Quistis", "Homing Laser"),
    230: ("Quistis", "Fire Breath"), 260: ("Quistis", "Shockwave Pulsar"), 275: ("Quistis", "Electrocute"),
    297: ("Quistis", "White Wind"), 299: ("Quistis", "Micro Missiles"), 300: ("Quistis", "Bad Breath"),
    305: ("Quistis", "Gatling Gun"), 306: ("Quistis", "Degenerator"), 307: ("Quistis", "Ray-Bomb"),
    317: ("Quistis", "Acid"),
    84: ("Rinoa", "Angel Wing"), 86: ("Rinoa", "Angelo Cannon"), 87: ("Rinoa", "Angelo Strike"),
    88: ("Rinoa", "Invincible Moon"), 89: ("Rinoa", "Wishing Star"), 92: ("Rinoa", "Angelo Search"),
    112: ("Zell", "Meteor Barret"), 212: ("Zell", "Burning Rave"), 215: ("Zell", "My Final Heaven"),
    216: ("Zell", "Different Beat"), 274: ("Zell", "Duel"),
    141: ("Squall", "Renzokuken (5 hits)"), 160: ("Squall", "Renzokuken (4 hits)"),
    259: ("Squall", "Renzokuken (6 hits)"), 332: ("Squall", "Renzokuken (7 hits)"),
    333: ("Squall", "Renzokuken (8 hits)"), 159: ("Squall", "Renzokuken vs X-ATM092"),
    161: ("Squall", "Renzokuken vs Elnoyle/Elvoret"), 162: ("Squall", "Fated Circle"),
    163: ("Squall", "Rough Divide"), 164: ("Squall", "Blasting Zone"), 165: ("Squall", "Lion Heart"),
    334: ("Squall", "Renzokuken (boss 334)"), 335: ("Squall", "Renzokuken (boss 335)"),
    336: ("Squall", "Renzokuken (boss 336)"), 337: ("Squall", "Renzokuken (boss 337)"),
    339: ("Squall", "Renzokuken (boss 339)"), 340: ("Squall", "Renzokuken (boss 340)"),
    341: ("Squall", "Renzokuken (boss 341)"), 342: ("Squall", "Renzokuken (boss 342)"),
    343: ("Squall", "Renzokuken (boss 343)"),
    188: ("Irvine", "Normal Shot"), 192: ("Irvine", "Scatter Shot"), 193: ("Irvine", "Dark Shot"),
    194: ("Irvine", "Flame Shot"), 195: ("Irvine", "Canister Shot"), 196: ("Irvine", "Quick Shot"),
    197: ("Irvine", "Armor Shot"), 198: ("Irvine", "Hyper Shot"),
    200: ("Seifer", "No Mercy"), 228: ("Edea", "Ice Strike"), 261: ("Laguna", "Desperado"),
    262: ("Kiros", "Blood Pain"), 263: ("Ward", "Massive Anchor"),
}

# Bone counts of the boss sets (index >= 1 of a Renzokuken pack): the highest count the set decodes
# against, which is the model's (159 = c0m092 X-ATM092, 55 bones; 161 = c0m091 Elnoyle, 54).
TARGET_BONES = {
    (159, 1): 55, (161, 1): 54, (334, 1): 44, (335, 1): 50, (336, 1): 64, (337, 1): 38, (339, 1): 56,
    (339, 2): 9, (340, 1): 45, (341, 1): 11, (342, 1): 39, (343, 1): 38,
}

# Animations of a set that do not use the model's skeleton: Massive Anchor (263) carries, after
# Ward's 8 body animations (31 bones), 8 more on a 2-bone skeleton that its sequence never plays.
# {(effect id, index): {first animation id: bone count from there}}
BODY_BONE_EXCEPTIONS = {(263, 0): {8: 2}}

# (effect id, index, section count, size, FNV-1a 32 of the set, FF8_EN.exe address, offsets)
_TABLE = (
    (71, 0, 3, 0x1B74, 0xAB77A114, 0x1590024, (20, 5704, 5784, 7028)),
    (72, 0, 3, 0x1B74, 0xAB77A114, 0x158D9AC, (20, 5704, 5784, 7028)),
    (73, 0, 3, 0x1B74, 0xAB77A114, 0x1587F4C, (20, 5704, 5784, 7028)),
    (74, 0, 3, 0x1B74, 0xAB77A114, 0x15863B0, (20, 5704, 5784, 7028)),
    (84, 0, 3, 0x2410, 0x02B88888, 0x1576020, (20, 8252, 8260, 9232)),
    (86, 0, 3, 0x1D60, 0x76BD0DB7, 0x156AA60, (20, 6816, 6836, 7520)),
    (87, 0, 3, 0x11F4, 0x2DD343B1, 0x1560550, (20, 4156, 4172, 4596)),
    (88, 0, 3, 0x1BEC, 0x61268848, 0x15560C0, (20, 6472, 6500, 7148)),
    (89, 0, 3, 0x1020, 0xA7C875DF, 0x1495530, (20, 3692, 3716, 4128)),
    (92, 0, 3, 0x1D0C, 0x21B6F3DB, 0x16C96E8, (20, 6760, 6788, 7436)),
    (112, 0, 2, 0x2038, 0x1FC81F5D, 0x12C3618, (16, 8236, 8248)),
    (141, 0, 3, 0x1D38, 0xA32C1D37, 0xEA8AB4, (20, 6060, 6536, 7480)),
    (159, 0, 3, 0x2334, 0x2E688265, 0xEA3A28, (20, 7436, 7820, 9012)),
    (159, 1, 2, 0x2118, 0xD0B3909C, 0xEA5D5C, (16, 8456, 8472)),
    (160, 0, 3, 0x172C, 0xC56319A6, 0xEA1BA0, (20, 4768, 5164, 5932)),
    (161, 0, 3, 0x2CB4, 0xB6F831A8, 0xE9B324, (20, 9416, 9932, 11444)),
    (161, 1, 2, 0x2FF4, 0x5939BBDF, 0xE9DFD8, (16, 12256, 12276)),
    (162, 0, 3, 0x1688, 0xD2E501C2, 0xDA0100, (20, 4972, 4984, 5768)),
    (163, 0, 3, 0xE3C, 0x12510258, 0xD99DC8, (20, 3108, 3196, 3644)),
    (164, 0, 3, 0x15A8, 0x18775C74, 0xD88AA0, (20, 4800, 4824, 5544)),
    (165, 0, 3, 0x2F18, 0xD9B672F4, 0xD780C8, (20, 10388, 10472, 12056)),
    (184, 0, 3, 0x1B74, 0xAB77A114, 0xD328B4, (20, 5704, 5784, 7028)),
    (188, 0, 3, 0x1570, 0xE7433C69, 0xD1B4B8, (20, 4916, 4952, 5488)),
    (192, 0, 3, 0x1570, 0xE7433C69, 0xD155E8, (20, 4916, 4952, 5488)),
    (193, 0, 3, 0x1570, 0xE7433C69, 0xD12EC0, (20, 4916, 4952, 5488)),
    (194, 0, 3, 0x1BC0, 0xBCEF93E1, 0xD0BD78, (20, 6408, 6444, 7104)),
    (195, 0, 3, 0x23CC, 0x421482F2, 0xD07400, (20, 8232, 8268, 9164)),
    (196, 0, 3, 0xB28, 0x20AE2C87, 0xD05288, (20, 2540, 2580, 2856)),
    (197, 0, 3, 0x23CC, 0x421482F2, 0xCFB348, (20, 8232, 8268, 9164)),
    (198, 0, 3, 0x23CC, 0x421482F2, 0xCF3A78, (20, 8232, 8268, 9164)),
    (200, 0, 3, 0x2628, 0x649E4EE2, 0xE2B518, (20, 8860, 8896, 9768)),
    (212, 0, 2, 0x1350, 0x47DB1C2C, 0x1181078, (16, 4908, 4944)),
    (215, 0, 2, 0x1970, 0xDC33CE93, 0x116D1AC, (16, 6464, 6512)),
    (216, 0, 2, 0x13F8, 0x075DCDD9, 0x1153B30, (16, 5072, 5112)),
    (228, 0, 2, 0x1734, 0x7F4F14F1, 0x18821A0, (16, 5916, 5940)),
    (229, 0, 3, 0x1B74, 0xAB77A114, 0x188062C, (20, 5704, 5784, 7028)),
    (230, 0, 3, 0x1B74, 0xAB77A114, 0x187EAB8, (20, 5704, 5784, 7028)),
    (259, 0, 3, 0x22C4, 0x87E30369, 0xE9264C, (20, 7260, 7800, 8900)),
    (260, 0, 3, 0x1B74, 0xAB77A114, 0x111B3CC, (20, 5704, 5784, 7028)),
    (261, 0, 3, 0x28AC, 0x65452D3C, 0x187C20C, (20, 8940, 8964, 10412)),
    (262, 0, 2, 0x1F68, 0xF82E640D, 0x187A2A4, (16, 7940, 8040)),
    (263, 0, 3, 0x24F8, 0x0ABC31DA, 0x1877DAC, (20, 8704, 8732, 9464)),
    (274, 0, 2, 0x4DF4, 0x8CCF7741, 0x10E2998, (16, 19904, 19956)),
    (275, 0, 3, 0x1B74, 0xAB77A114, 0x10DA574, (20, 5704, 5784, 7028)),
    (297, 0, 3, 0x1B74, 0xAB77A114, 0x1056888, (20, 5704, 5784, 7028)),
    (299, 0, 3, 0x1B74, 0xAB77A114, 0x1047120, (20, 5704, 5784, 7028)),
    (300, 0, 3, 0x1B74, 0xAB77A114, 0x103DCB0, (20, 5704, 5784, 7028)),
    (305, 0, 3, 0x1B74, 0xAB77A114, 0xCEB5E8, (20, 5704, 5784, 7028)),
    (306, 0, 3, 0x1B74, 0xAB77A114, 0xCE454C, (20, 5704, 5784, 7028)),
    (307, 0, 3, 0x1B74, 0xAB77A114, 0xCDF86C, (20, 5704, 5784, 7028)),
    (317, 0, 3, 0x1B74, 0xAB77A114, 0xFFE6B0, (20, 5704, 5784, 7028)),
    (332, 0, 3, 0x2568, 0xA43B207E, 0xE7E368, (20, 7772, 8372, 9576)),
    (333, 0, 3, 0x23E0, 0x15946DE1, 0xE7B0C0, (20, 7340, 8004, 9184)),
    (334, 0, 3, 0x344C, 0xAD73C28E, 0xE71864, (20, 11004, 11576, 13388)),
    (334, 1, 2, 0x56F8, 0x530CD653, 0xE74CB0, (16, 22252, 22264)),
    (335, 0, 3, 0x203C, 0x96051DCC, 0xE6CC48, (20, 6604, 7008, 8252)),
    (335, 1, 2, 0x20D4, 0x89AACE96, 0xE6EC84, (16, 8396, 8404)),
    (336, 0, 3, 0x32E8, 0xEEA0CD91, 0xE640FC, (20, 10824, 11456, 13032)),
    (336, 1, 2, 0x50A8, 0xBBF8EDE0, 0xE673E4, (16, 20636, 20648)),
    (337, 0, 3, 0x29C0, 0x116BAB93, 0xE5DF7C, (20, 8604, 9164, 10688)),
    (337, 1, 2, 0x31FC, 0xC86CAC5E, 0xE6093C, (16, 12784, 12796)),
    (339, 0, 3, 0x2820, 0x25E20240, 0xE567AC, (20, 8488, 8988, 10272)),
    (339, 1, 2, 0x3C84, 0xC97785BB, 0xE58FCC, (16, 15480, 15492)),
    (339, 2, 2, 0xBBC, 0xFF9C1DE1, 0xE5CC50, (16, 2996, 3004)),
    (340, 0, 3, 0x1EF4, 0xAD65B589, 0xE5110C, (20, 6324, 6904, 7924)),
    (340, 1, 2, 0x2D74, 0x6B8D5A8F, 0xE53000, (16, 11624, 11636)),
    (341, 0, 3, 0x15A8, 0xCD9FDBB5, 0xE4F048, (20, 4300, 4736, 5544)),
    (341, 1, 2, 0x588, 0x2AEF3537, 0xE505F0, (16, 1404, 1416)),
    (342, 0, 3, 0x2894, 0xC54D2ACA, 0xE47704, (20, 8540, 9044, 10388)),
    (342, 1, 2, 0x4A80, 0xBE96F73A, 0xE49F98, (16, 19044, 19072)),
    (343, 0, 3, 0x1B4C, 0xDE5C84AD, 0xE426D0, (20, 5700, 6052, 6988)),
    (343, 1, 2, 0x2D8C, 0x55E8CCA3, 0xE4421C, (16, 11648, 11660)),
)


class AnimSetError(ValueError):
    """The bytes are not an anim set FFNx would load."""


@dataclass(frozen=True)
class AnimSetInfo:
    """One vanilla anim set of the exe."""
    effect_id: int
    index: int            # order in the exe when the effect binds several sets (0 = the caster)
    section_count: int
    size: int
    fnv1a: int
    en_address: int       # in the 2013 Steam FF8_EN.exe
    offsets: tuple        # vanilla section offsets, then the size

    @property
    def file_name(self) -> str:
        return anim_set_file_name(self.effect_id, self.index)

    @property
    def character(self) -> str:
        """The model it plays on: a character name (CHARACTER_MODELS), or TARGET_MODEL for a boss set."""
        return EFFECT_NAMES[self.effect_id][0] if self.index == 0 else TARGET_MODEL

    @property
    def effect_name(self) -> str:
        return EFFECT_NAMES[self.effect_id][1]

    @property
    def label(self) -> str:
        role = "" if self.index == 0 else f", target set {self.index}"
        return f"{self.effect_id:03d} {self.effect_name}{role}"

    @property
    def body_bones(self) -> int:
        if self.index:
            return TARGET_BONES[(self.effect_id, self.index)]
        return CHARACTER_MODELS[self.character][1]

    @property
    def weapon_bones(self):
        """Bone count of the weapon animations, None when the set has none."""
        if self.section_count < 3:
            return None
        return CHARACTER_MODELS[self.character][2]

    def body_bones_of(self, anim_id: int) -> int:
        """Bone count of one body animation (BODY_BONE_EXCEPTIONS aside, the model's)."""
        result = self.body_bones
        for first, nb_bone in sorted(BODY_BONE_EXCEPTIONS.get((self.effect_id, self.index), {}).items()):
            if anim_id >= first:
                result = nb_bone
        return result

    @property
    def header(self) -> bytes:
        return struct.pack(f"<{self.section_count + 2}I", self.section_count, *self.offsets)


ANIM_SETS = tuple(AnimSetInfo(*row) for row in _TABLE)


def anim_set_file_name(effect_id: int, index: int = 0) -> str:
    """The name FFNx looks for: effect_NNN.animset, effect_NNN_K.animset for the K-th set."""
    suffix = f"_{index}" if index else ""
    return f"effect_{effect_id:03d}{suffix}{ANIM_SET_EXTENSION}"


def anim_set_info(effect_id: int, index: int = 0):
    for info in ANIM_SETS:
        if info.effect_id == effect_id and info.index == index:
            return info
    return None


def info_from_file_name(file_name: str):
    """The vanilla set an effect_NNN[_K].animset file replaces, or None."""
    base = os.path.basename(file_name)
    for info in ANIM_SETS:
        if info.file_name.lower() == base.lower():
            return info
    return None


def sets_of_character(character: str) -> list:
    """The sets that play on this character's model (index 0 of its effects)."""
    return [info for info in ANIM_SETS if info.index == 0 and info.character == character]


def character_of_model_file(file_name: str):
    """'Squall'... for a character body or weapon model file (d0c000.dat, d0w003.dat), else None."""
    base = os.path.basename(file_name).lower()
    if len(base) < 3 or base[0] != 'd' or base[2] not in 'cw':
        return None
    prefix = base[:2]
    for name, (model_prefix, _body, _weapon) in CHARACTER_MODELS.items():
        if model_prefix[:2] == prefix:
            return name
    return None


def fnv1a32(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


# ----------------------------------------------------------------------------- format
def _animation_section_error(section: bytes):
    if len(section) < 8:
        return "too small"
    count = struct.unpack_from("<I", section, 0)[0]
    if count == 0 or count > (len(section) - 4) // 4:
        return "bad animation count"
    for offset in struct.unpack_from(f"<{count}I", section, 4):
        if offset < 4 + 4 * count or offset >= len(section):
            return "animation offset out of range"
        if section[offset] == 0:
            return "an animation has 0 frames"
    return None


def _sequence_section_error(section: bytes):
    if len(section) < 4:
        return "too small"
    count = struct.unpack_from("<H", section, 0)[0]
    if count == 0 or count > (len(section) - 2) // 2:
        return "bad sequence count"
    for offset in struct.unpack_from(f"<{count}H", section, 2):
        if offset and (offset < 2 + 2 * count or offset >= len(section)):
            return "sequence offset out of range"
    return None


def anim_set_error(data: bytes, section_count: int = None):
    """Why FFNx would ignore these bytes as a set file (the same checks), or None.
    section_count: the vanilla set's count, which the file must keep."""
    if len(data) < 8:
        return "file too small"
    count = struct.unpack_from("<I", data, 0)[0]
    if section_count is not None and count != section_count:
        return f"{count} sections, the vanilla set has {section_count}"
    if count not in (2, 3):
        return f"{count} sections (2 or 3 expected)"
    header_size = 4 * (count + 2)
    if len(data) < header_size:
        return "file too small"
    offsets = struct.unpack_from(f"<{count + 1}I", data, 4)
    if offsets[0] != header_size:
        return "bad first section offset"
    if offsets[-1] != len(data):
        return "the size in the header does not match the file size"
    if len(data) > MAX_FILE_SIZE:
        return f"over {MAX_FILE_SIZE} bytes"
    for index in range(count):
        start, end = offsets[index], offsets[index + 1]
        if end < start or end > len(data):
            return "section offset out of range"
        section = data[start:end]
        problem = (_sequence_section_error(section) if index == SEQUENCE_SECTION
                   else _animation_section_error(section))
        if problem:
            name = ("sequence", "body animation", "weapon animation")[
                0 if index == SEQUENCE_SECTION else 1 if index == BODY_SECTION else 2]
            return f"{name} section: {problem}"
    return None


def split_sequence_section(section: bytes) -> list:
    """[bytes of sequence 0, 1...]: each runs to the next higher offset (the last one keeps the
    section's padding), an offset 0 is an empty sequence."""
    count = struct.unpack_from("<H", section, 0)[0]
    offsets = struct.unpack_from(f"<{count}H", section, 2)
    result = []
    for offset in offsets:
        if offset == 0:
            result.append(b"")
            continue
        higher = [other for other in offsets if other > offset]
        result.append(bytes(section[offset:min(higher) if higher else len(section)]))
    return result


def build_sequence_section(sequence_list: list) -> bytes:
    """The sequence section of these sequences, stored in id order (an empty one gets offset 0),
    padded to 4 bytes."""
    offset = 2 + 2 * len(sequence_list)
    offsets, body = [], bytearray()
    for data in sequence_list:
        offsets.append(offset + len(body) if data else 0)
        body.extend(data)
    if offset + len(body) > 0xFFFF:
        raise AnimSetError("the sequences are over 64 KB (u16 offsets)")
    section = struct.pack(f"<H{len(offsets)}H", len(offsets), *offsets) + bytes(body)
    return _pad4(section)


def _pad4(data: bytes) -> bytes:
    return bytes(data) + b"\x00" * (-len(data) % 4)


class AnimSet:
    """One set: its raw sections (body animations, sequences, weapon animations or None)."""

    def __init__(self, body: bytes, sequences: bytes, weapon: bytes = None, info: AnimSetInfo = None):
        self.body = bytes(body)
        self.sequences = bytes(sequences)
        self.weapon = None if weapon is None else bytes(weapon)
        self.info = info

    @classmethod
    def parse(cls, data: bytes, info: AnimSetInfo = None) -> "AnimSet":
        problem = anim_set_error(bytes(data), info.section_count if info else None)
        if problem:
            raise AnimSetError(problem)
        count = struct.unpack_from("<I", data, 0)[0]
        offsets = struct.unpack_from(f"<{count + 1}I", data, 4)
        sections = [bytes(data[offsets[i]:offsets[i + 1]]) for i in range(count)]
        return cls(sections[0], sections[1], sections[2] if count > 2 else None, info)

    @property
    def section_count(self) -> int:
        return 2 if self.weapon is None else 3

    def to_bytes(self) -> bytes:
        sections = [self.body, self.sequences] + ([self.weapon] if self.weapon is not None else [])
        header_size = 4 * (len(sections) + 2)
        offsets, offset = [], header_size
        for section in sections:
            offsets.append(offset)
            offset += len(section)
        data = struct.pack(f"<{len(sections) + 2}I", len(sections), *offsets, offset) + b"".join(sections)
        problem = anim_set_error(data, self.info.section_count if self.info else None)
        if problem:
            raise AnimSetError(problem)
        return data

    def sequence_list(self) -> list:
        return split_sequence_section(self.sequences)

    def set_sequence_list(self, sequence_list: list):
        self.sequences = build_sequence_section(sequence_list)

    def copy(self) -> "AnimSet":
        return copy.copy(self)


# ----------------------------------------------------------------------------- editing
def split_animation_section(section: bytes) -> list:
    """[bytes of animation 0, 1...] of an animation section (each runs to the next higher offset)."""
    count = struct.unpack_from("<I", section, 0)[0]
    offsets = struct.unpack_from(f"<{count}I", section, 4)
    return [bytes(section[offset:min([other for other in offsets if other > offset] or [len(section)])])
            for offset in offsets]


def join_animation_section(animation_list: list) -> bytes:
    """An animation section holding these animations (bytes each), padded to 4 bytes."""
    offset = 4 + 4 * len(animation_list)
    offsets = []
    for data in animation_list:
        offsets.append(offset)
        offset += len(data)
    return _pad4(struct.pack(f"<{len(animation_list) + 1}I", len(animation_list), *offsets)
                 + b"".join(bytes(data) for data in animation_list))


class AnimSetDocument:
    """A set opened for editing (an editor's 3D view and sequence list): `body` / `weapon` are
    AnimationSections and `seq_animation_data` the sequences in the MonsterAnalyser shape
    ({'seq_animation_data': [{'id', 'data'}]}, ids from 1). Animations that do not use the model's
    skeleton (BODY_BONE_EXCEPTIONS), and a weapon section whose bone count is not known, are kept
    as they are. to_anim_set() builds the set back (validated).

    Both pools are always decoded, on the skeleton given or else on a neutral one of the set's
    bone count (decoding only needs the count): one document serves the character body file and
    its weapon file alike. bind_skeleton() puts a model's REAL bones under a pool for its 3D view."""

    def __init__(self, anim_set: AnimSet, body_bone_section=None, weapon_bone_section=None):
        from ..monsterdata import AnimationSection
        info = anim_set.info
        self.info = info
        self.original = anim_set
        animation_list = split_animation_section(anim_set.body)
        exceptions = BODY_BONE_EXCEPTIONS.get((info.effect_id, info.index), {}) if info else {}
        nb_own = min([first for first in exceptions] + [len(animation_list)])
        if body_bone_section is None:
            if info is None:
                raise AnimSetError("unknown set: its bone counts are not known")
            body_bone_section = synthetic_bone_section(info.body_bones)
        self._bones = {'body': body_bone_section.bones, 'weapon': None}
        self.body = AnimationSection()
        self.body.analyze(join_animation_section(animation_list[:nb_own]), body_bone_section)
        self.foreign_body_animations = animation_list[nb_own:]
        self.weapon = None
        self.raw_weapon = anim_set.weapon
        if anim_set.weapon is not None and weapon_bone_section is None and info is not None and info.weapon_bones:
            weapon_bone_section = synthetic_bone_section(info.weapon_bones)
        if anim_set.weapon is not None and weapon_bone_section is not None:
            self.weapon = AnimationSection()
            self.weapon.analyze(bytes(anim_set.weapon), weapon_bone_section)
            self.raw_weapon = None
            self._bones['weapon'] = weapon_bone_section.bones
        self.seq_animation_data = {'seq_animation_data': [
            {'id': index + 1, 'data': bytearray(data)} for index, data in enumerate(anim_set.sequence_list())]}

    def pool(self, name: str):
        """The 'body' or 'weapon' AnimationSection (None: the set has no weapon animations)."""
        return self.body if name == 'body' else self.weapon

    def bones_of(self, name: str):
        """The bones pool `name` is currently shown on (its matrices are built on them)."""
        return self._bones.get(name)

    def bind_skeleton(self, name: str, bone_section) -> bool:
        """Show pool `name` on `bone_section` (a model of the same bone count): its frames' render
        matrices are rebuilt on those bones when they were built on others. False when the pool is
        missing or the bone count differs (nothing changed)."""
        section = self.pool(name)
        if section is None or bone_section is None:
            return False
        bones = bone_section.bones
        if self._bones.get(name) is bones:
            return True
        if len(bones) != len(self._bones[name] or ()):
            return False
        section.build_bone_matrices(bones)
        self._bones[name] = bones
        return True

    def to_anim_set(self) -> AnimSet:
        body = join_animation_section([bytes(animation.to_binary()) for animation in self.body.animations]
                                      + self.foreign_body_animations)
        weapon = _pad4(self.weapon.to_binary()) if self.weapon is not None else self.raw_weapon
        sequences = sorted(self.seq_animation_data['seq_animation_data'], key=lambda item: item['id'])
        if [item['id'] for item in sequences] != list(range(1, len(sequences) + 1)):
            raise AnimSetError("the sequence ids must run from 1 with no gap")
        anim_set = AnimSet(body, build_sequence_section([bytes(item['data']) for item in sequences]), weapon, self.info)
        anim_set.to_bytes()   # validated
        return anim_set


# ----------------------------------------------------------------------------- exe
def locate_anim_sets(exe: bytes) -> dict:
    """{AnimSetInfo: file offset in `exe`} for every vanilla set found in this exe (any release:
    the sets are byte-identical everywhere). Copies with the same contents (the Blue Magic cast
    set is stored 16 times) are told apart by their order, which every release keeps."""
    found = {}
    groups = {}
    for info in ANIM_SETS:
        groups.setdefault((info.fnv1a, info.size), []).append(info)
    for (fnv, size), info_list in groups.items():
        header = info_list[0].header
        positions = []
        start = exe.find(header)
        while start >= 0:
            if fnv1a32(exe[start:start + size]) == fnv:
                positions.append(start)
            start = exe.find(header, start + 1)
        if len(positions) != len(info_list):
            continue
        for info, position in zip(sorted(info_list, key=lambda i: i.en_address), sorted(positions)):
            found[info] = position
    return found


def read_exe_anim_sets(exe: bytes) -> dict:
    """{AnimSetInfo: AnimSet} of every vanilla set found in the exe."""
    return {info: AnimSet.parse(exe[offset:offset + info.size], info)
            for info, offset in locate_anim_sets(exe).items()}


def build_export_files(anim_sets: dict, convert=False, game_data=None) -> tuple:
    """Every set of `anim_sets` ({AnimSetInfo: AnimSet}) as the FFNx file it is saved as, as is or
    converted to 30 fps (convert_to_real30, which needs `game_data`), every file built and checked
    before the caller writes any. Returns (files [(file name, bytes)], reports [(info, report)] of
    the converted sets, errors [(info, message)] of the sets left out), sorted by effect."""
    files, reports, errors = [], [], []
    for info, anim_set in sorted(anim_sets.items(), key=lambda item: (item[0].effect_id, item[0].index)):
        try:
            if convert:
                anim_set, report = convert_to_real30(game_data, anim_set)
                reports.append((info, report))
            files.append((info.file_name, anim_set.to_bytes()))
        except AnimSetError as error:
            errors.append((info, str(error)))
    return files, reports, errors


def export_files(exe: bytes) -> list:
    """[(file name, bytes)] of every set of the exe, as FFNx reads them (the exe bytes as is)."""
    located = locate_anim_sets(exe)
    return [(info.file_name, bytes(exe[offset:offset + info.size]))
            for info, offset in sorted(located.items(), key=lambda item: (item[0].effect_id, item[0].index))]


def patch_exe(exe: bytearray, info: AnimSetInfo, data: bytes, offset: int = None) -> int:
    """Write a set back into its block of the exe (in memory). Only a set no bigger than the
    vanilla block fits (the rest of the block is zero-filled): a bigger one is refused, it can
    only be used as an effect_NNN.animset file. Returns the file offset written."""
    problem = anim_set_error(bytes(data), info.section_count)
    if problem:
        raise AnimSetError(f"{info.file_name}: {problem}")
    if len(data) > info.size:
        raise AnimSetError(f"{info.file_name}: {len(data)} bytes, its exe block holds only {info.size}: "
                           f"save it as {FFNX_FOLDER}/{info.file_name} for FFNx instead")
    if offset is None:
        offset = locate_anim_sets(bytes(exe)).get(info)
        if offset is None:
            raise AnimSetError(f"{info.file_name}: the vanilla set is not in this exe (already changed?)")
    exe[offset:offset + info.size] = bytes(data) + b"\x00" * (info.size - len(data))
    return offset


# ----------------------------------------------------------------------------- 30 fps
def synthetic_bone_section(nb_bone: int):
    """A BoneSection with the right bone count and neutral bones: a set has no skeleton of its
    own, decoding (and interpolating) the animations only needs the count."""
    from ..monsterdata import BoneSection
    bone_section = BoneSection()
    bone_section.analyze(bytes([nb_bone]) + b"\x00" * 15 + b"\x00" * 48 * nb_bone)
    return bone_section


def parse_animation_section(section: bytes, nb_bone, bone_section=None):
    """The AnimationSection of a set section. nb_bone: one count for every animation, or a callable
    anim id -> count (a section may mix skeletons, BODY_BONE_EXCEPTIONS): each animation is then
    decoded on its own. bone_section: the real skeleton, for a single count."""
    from ..monsterdata import AnimationSection
    if not callable(nb_bone):
        animation_section = AnimationSection()
        animation_section.analyze(bytes(section), bone_section or synthetic_bone_section(nb_bone))
        return animation_section
    count = struct.unpack_from("<I", section, 0)[0]
    offsets = list(struct.unpack_from(f"<{count}I", section, 4))
    ends = [min([other for other in offsets if other > offset] or [len(section)]) for offset in offsets]
    container = AnimationSection()
    container.animations = []
    for anim_id, (start, end) in enumerate(zip(offsets, ends)):
        single = AnimationSection()
        single.analyze(struct.pack("<2I", 1, 8) + bytes(section[start:end]),
                       synthetic_bone_section(nb_bone(anim_id)))
        container.animations.append(single.animations[0])
    container.nb_animations = len(container.animations)
    return container


def convert_to_real30(game_data, anim_set: AnimSet, mode=None) -> tuple:
    """(converted AnimSet, report) for FFNx True30FPS, like a battle model (FF8GameData/dat/dat30):
    every animation gets exactly 2n frames (body and weapon animation of the same id together),
    the sequences are rewritten for a VM ticking at 30 Hz (seqrewrite30), and an animation over
    255 frames once converted is split, the sequences then play its parts back to back (the
    weapon animation of that id is split the same way). All or nothing: AnimSetError, and
    `anim_set` is left untouched. report = {'nb_converted', 'split_list', 'sequence_report'}."""
    from . import interpolation
    from .animloopdetector import ANIM_UNUSED, get_animation_kind_dict, is_looping
    from .animsplitter import (MAX_ANIMATION_FRAME, can_split_animation, get_nb_part_needed,
                               rewrite_sequence_list_for_split, split_animation)
    from .dat30 import FACTOR, double_animation
    from .seqrewrite30 import rewrite_seq_animation_data
    info = anim_set.info
    if info is None:
        raise AnimSetError("unknown set: its bone counts are not known")
    mode = mode or interpolation.LINEAR
    if not getattr(game_data, 'anim_sequence_data_json', None):
        game_data.load_anim_sequence_data()
    body = parse_animation_section(anim_set.body, info.body_bones_of)
    pools = [(body, info.body_bones_of)]
    weapon = None
    if anim_set.weapon is not None:
        weapon = parse_animation_section(anim_set.weapon, lambda _anim_id: info.weapon_bones)
        pools.append((weapon, lambda _anim_id: info.weapon_bones))
    sequence_list = anim_set.sequence_list()
    seq_animation_data = {'seq_animation_data': [{'id': index + 1, 'data': bytearray(data)}
                                                 for index, data in enumerate(sequence_list)]}
    kind_dict = get_animation_kind_dict(game_data, seq_animation_data, body.nb_animations)
    report = {'nb_converted': 0, 'split_list': [], 'sequence_report': None}

    plan = []
    for anim_id, animation in enumerate(body.animations):
        smooth_loop = is_looping(kind_dict.get(anim_id, ANIM_UNUSED))
        nb_frame = len(animation.frames)
        if nb_frame * FACTOR <= MAX_ANIMATION_FRAME:
            plan.append((anim_id, smooth_loop, 0))
            continue
        nb_part = get_nb_part_needed(nb_frame, FACTOR, smooth_loop, MAX_ANIMATION_FRAME)
        if nb_part < 2:
            raise AnimSetError(f"animation {anim_id}: {nb_frame} frames cannot be cut in parts small enough")
        if weapon is not None and weapon.nb_animations != body.nb_animations:
            raise AnimSetError(f"animation {anim_id}: {nb_frame} frames needs a split, which needs as many "
                               "weapon animations as body animations")
        can_split, reason = can_split_animation(game_data, seq_animation_data, body, anim_id, nb_part)
        if not can_split:
            raise AnimSetError(f"animation {anim_id}: {nb_frame} frames, cannot be split: {reason}")
        plan.append((anim_id, smooth_loop, nb_part))

    # 1. the sequences, on the vanilla byte-code
    section_report = rewrite_seq_animation_data(game_data, seq_animation_data)
    manual = section_report.manual_report_list()
    if manual:
        raise AnimSetError("sequence(s) " + ", ".join(str(item.seq_id) for item in manual)
                           + " cannot be rewritten automatically")
    report['sequence_report'] = section_report

    # 2. the animations (a split inserts the part ids into the rewritten sequences)
    for anim_id, smooth_loop, nb_part in plan:
        used = [(pool, bones_of) for pool, bones_of in pools if anim_id < pool.nb_animations]
        if not nb_part:
            for pool, bones_of in used:
                double_animation(pool.animations[anim_id], synthetic_bone_section(bones_of(anim_id)).bones,
                                 smooth_loop, mode)
            report['nb_converted'] += 1
            continue
        nb_frame = len(body.animations[anim_id].frames)
        new_id_list = None
        for pool, bones_of in used:
            pool.animations[anim_id].create_interpolated_frames(synthetic_bone_section(bones_of(anim_id)).bones,
                                                                FACTOR, smooth_loop, mode=mode)
            ids = split_animation(pool, anim_id, MAX_ANIMATION_FRAME)
            if new_id_list is not None and ids != new_id_list:
                raise AnimSetError(f"animation {anim_id}: the body and weapon parts do not line up")
            new_id_list = ids
        rewrite_sequence_list_for_split(game_data, seq_animation_data, anim_id, new_id_list)
        report['split_list'].append((anim_id, nb_frame, nb_part, new_id_list))
        report['nb_converted'] += nb_part

    converted = AnimSet(_pad4(body.to_binary()),
                        build_sequence_section([bytes(item['data']) for item in
                                                seq_animation_data['seq_animation_data']]),
                        _pad4(weapon.to_binary()) if weapon is not None else None, info)
    converted.to_bytes()   # validated before it is handed back
    return converted, report
