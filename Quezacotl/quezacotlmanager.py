import struct

from FF8GameData.gamedata import GameData

# Universal GF learned-ability list: a single 128-bit (16 byte) bitfield, identical layout
# for every GF. Bit N (1-indexed) lives in byte (N-1)//8 of the LearnedAbility block, at
# bit (N-1)%8. Names ported from the original Quezacotl C# tool (Form1.Designer.cs
# checkBoxGfAb001..120 labels); "???" entries were never identified by the original author.
GF_ABILITY_NAMES = {
    1: "Dummy?", 2: "HP-J", 3: "Str-J", 4: "Vit-J", 5: "Mag-J", 6: "Spr-J", 7: "Spd-J",
    8: "Eva-J", 9: "Hit-J", 10: "Luck-J", 11: "ElemAtk-J", 12: "ST-Atk-J", 13: "Elem-Def-J",
    14: "ST-Def-J", 15: "Elem-Defx2", 16: "Elem-Defx4", 17: "ST-Def-Jx2", 18: "ST-Def-Jx4",
    19: "Ability x3", 20: "Ability x4", 21: "Magic", 22: "GF", 23: "Draw", 24: "Item",
    25: "Empty", 26: "Card", 27: "Doom", 28: "Mad Rush", 29: "Treatment", 30: "Defend",
    31: "DarkSide", 32: "Recover", 33: "Absorb", 34: "Revive", 35: "LV Down", 36: "LV Up",
    37: "Kamikaze", 38: "Devour", 39: "MiniMog", 40: "HP +20%", 41: "HP +40%", 42: "HP +80%",
    43: "Str +20%", 44: "Str +40%", 45: "Str +60%", 46: "Vit +20%", 47: "Vit +40%",
    48: "Vit +60%", 49: "Mag +20%", 50: "Mag +40%", 51: "Mag +60%", 52: "Spr +20%",
    53: "Spr +40%", 54: "Spr +60%", 55: "Spd +20%", 56: "Spd +40%", 57: "Eva +30%",
    58: "Luck +50%", 59: "Mug", 60: "Med Data", 61: "Counter", 62: "Return Damage",
    63: "Cover", 64: "Initiative", 65: "Move HP-Up", 66: "HPBonus", 67: "StrBonus",
    68: "VitBonus", 69: "MagBonus", 70: "SprBonus", 71: "Auto-Protect", 72: "Auto-Shell",
    73: "Auto-Reflect", 74: "Auto-Haste", 75: "Auto-Potion", 76: "Expendx2-1",
    77: "Expendx3-1", 78: "Ribbon", 79: "Alert", 80: "Move-Find", 81: "Enc-Half",
    82: "Enc-None", 83: "RareItem", 84: "SumMag+10%", 85: "SumMag+20%", 86: "SumMag+30%",
    87: "SumMag+40%", 88: "GFHP+10%", 89: "GFHP+20%", 90: "GFHP+30%", 91: "GFHP+40%",
    92: "Boost", 93: "Haggle", 94: "Sell-High", 95: "Familiar", 96: "CallShop",
    97: "JunkShop", 98: "T Mag-RF", 99: "I Mag-RF", 100: "F Mag-RF", 101: "L Mag-RF",
    102: "TimeMag-RF", 103: "STMag-RF", 104: "SuptMag-RF", 105: "ForbidMag-RF",
    106: "RecovMed-RF", 107: "STMed-RF", 108: "Ammo-RF", 109: "Tool-RF", 110: "ForbidMed-RF",
    111: "GFRecovMed-RF", 112: "GFAblMed-RF", 113: "Mid Mag-RF", 114: "HighMag-RF",
    115: "MedLVUp", 116: "Card Mod", 117: "???", 118: "???", 119: "???", 120: "???",
}

CHARACTER_NAMES = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea"]

# CurrentStatus is a 16-bit mask (IDA: Status1Flag); only the low byte's meaning was
# identified by the original tool, the high byte is unnamed but still editable.
CHARACTER_STATUS_NAMES = [
    "KO", "Poison", "Petrify", "Darkness", "Silence", "Berserk", "Zombie", "???",
    "Unknown 9", "Unknown 10", "Unknown 11", "Unknown 12",
    "Unknown 13", "Unknown 14", "Unknown 15", "Unknown 16",
]

NB_GF = 16
GF_ENTRY_SIZE = 68
NB_CHARACTERS = 8
CHARACTER_ENTRY_SIZE = 152
CONFIG_ENTRY_SIZE = 20
MISC_ENTRY_SIZE = 80
NB_ITEMS = 198
ITEM_ENTRY_SIZE = 2

GF_DATA_OFFSET = 0
CHARACTER_DATA_OFFSET = GF_DATA_OFFSET + NB_GF * GF_ENTRY_SIZE       # 1088
SHOPS_DATA_OFFSET = CHARACTER_DATA_OFFSET + NB_CHARACTERS * CHARACTER_ENTRY_SIZE  # 2304
CONFIG_DATA_OFFSET = 2704
MISC_DATA_OFFSET = CONFIG_DATA_OFFSET + CONFIG_ENTRY_SIZE            # 2724
ITEMS_DATA_OFFSET = MISC_DATA_OFFSET + MISC_ENTRY_SIZE               # 2804

# The vanilla init.out only reserves 4 item slots. The original "enhanced" Quezacotl grows
# the file to fit all 198 slots on open; we do the same instead of asking the user to
# reopen the file.
FULL_FILE_SIZE = ITEMS_DATA_OFFSET + NB_ITEMS * ITEM_ENTRY_SIZE  # 3200


def _u16(buffer, offset):
    return struct.unpack_from('<H', buffer, offset)[0]


def _set_u16(buffer, offset, value):
    struct.pack_into('<H', buffer, offset, value & 0xFFFF)


def _u32(buffer, offset):
    return struct.unpack_from('<I', buffer, offset)[0]


def _set_u32(buffer, offset, value):
    struct.pack_into('<I', buffer, offset, value & 0xFFFFFFFF)


class GfEntry:
    """One 68-byte GF record (InitWorker.cs GfData / ReadGF)."""

    def __init__(self, buffer, offset, gf_id, game_data: GameData):
        self._buffer = buffer
        self._offset = offset
        self.gf_id = gf_id
        self.game_data = game_data

    @property
    def gf_name(self):
        return self.game_data.gforce_data_json["gforce"][self.gf_id]["name"]

    @property
    def name(self):
        return self.game_data.translate_hex_to_str(self._buffer[self._offset:self._offset + 12]).strip('\x00')

    @name.setter
    def name(self, value):
        text = bytearray(self.game_data.translate_str_to_hex(value))
        text = (text + bytearray(12))[:12]
        self._buffer[self._offset:self._offset + 12] = text

    @property
    def exp(self):
        return _u32(self._buffer, self._offset + 12)

    @exp.setter
    def exp(self, value):
        _set_u32(self._buffer, self._offset + 12, value)

    @property
    def unknown1(self):
        return self._buffer[self._offset + 16]

    @unknown1.setter
    def unknown1(self, value):
        self._buffer[self._offset + 16] = value & 0xFF

    @property
    def available(self):
        return self._buffer[self._offset + 17] != 0

    @available.setter
    def available(self, value):
        self._buffer[self._offset + 17] = 1 if value else 0

    @property
    def current_hp(self):
        return _u16(self._buffer, self._offset + 18)

    @current_hp.setter
    def current_hp(self, value):
        _set_u16(self._buffer, self._offset + 18, value)

    def has_ability(self, ability_id):
        """ability_id is 1-120, matching GF_ABILITY_NAMES."""
        byte_index, bit = divmod(ability_id - 1, 8)
        return bool(self._buffer[self._offset + 20 + byte_index] & (1 << bit))

    def set_ability(self, ability_id, learned):
        byte_index, bit = divmod(ability_id - 1, 8)
        pos = self._offset + 20 + byte_index
        if learned:
            self._buffer[pos] |= (1 << bit)
        else:
            self._buffer[pos] &= ~(1 << bit) & 0xFF

    def get_ap_ability(self, slot):
        """slot is 1-22, raw AP invested in that ability slot."""
        return self._buffer[self._offset + 36 + (slot - 1)]

    def set_ap_ability(self, slot, value):
        self._buffer[self._offset + 36 + (slot - 1)] = value & 0xFF

    @property
    def kills(self):
        return _u16(self._buffer, self._offset + 60)

    @kills.setter
    def kills(self, value):
        _set_u16(self._buffer, self._offset + 60, value)

    @property
    def kos(self):
        return _u16(self._buffer, self._offset + 62)

    @kos.setter
    def kos(self, value):
        _set_u16(self._buffer, self._offset + 62, value)

    @property
    def learning_ability(self):
        return self._buffer[self._offset + 64]

    @learning_ability.setter
    def learning_ability(self, value):
        self._buffer[self._offset + 64] = value & 0xFF


class MagicSlot:
    """One (magic id, quantity) pair inside a CharacterEntry."""

    def __init__(self, buffer, offset):
        self._buffer = buffer
        self._offset = offset

    @property
    def magic_id(self):
        return self._buffer[self._offset]

    @magic_id.setter
    def magic_id(self, value):
        self._buffer[self._offset] = value & 0xFF

    @property
    def quantity(self):
        return self._buffer[self._offset + 1]

    @quantity.setter
    def quantity(self, value):
        self._buffer[self._offset + 1] = value & 0xFF


class CharacterEntry:
    """One 152-byte character record (InitWorker.cs CharactersData / ReadCharacters)."""

    def __init__(self, buffer, offset, char_id, game_data: GameData):
        self._buffer = buffer
        self._offset = offset
        self.char_id = char_id
        self.game_data = game_data
        self.magics = [MagicSlot(buffer, offset + 16 + i * 2) for i in range(32)]

    @property
    def name(self):
        return CHARACTER_NAMES[self.char_id] if self.char_id < len(CHARACTER_NAMES) else f"Character {self.char_id}"

    def _byte(self, add):
        return self._buffer[self._offset + add]

    def _set_byte(self, add, value):
        self._buffer[self._offset + add] = value & 0xFF

    @property
    def current_hp(self):
        return _u16(self._buffer, self._offset)

    @current_hp.setter
    def current_hp(self, value):
        _set_u16(self._buffer, self._offset, value)

    @property
    def hp_bonus(self):
        return _u16(self._buffer, self._offset + 2)

    @hp_bonus.setter
    def hp_bonus(self, value):
        _set_u16(self._buffer, self._offset + 2, value)

    @property
    def exp(self):
        return _u32(self._buffer, self._offset + 4)

    @exp.setter
    def exp(self, value):
        _set_u32(self._buffer, self._offset + 4, value)

    @property
    def model_id(self):
        return self._byte(8)

    @model_id.setter
    def model_id(self, value):
        self._set_byte(8, value)

    @property
    def weapon_id(self):
        return self._byte(9)

    @weapon_id.setter
    def weapon_id(self, value):
        self._set_byte(9, value)

    @property
    def str_stat(self):
        return self._byte(10)

    @str_stat.setter
    def str_stat(self, value):
        self._set_byte(10, value)

    @property
    def vit(self):
        return self._byte(11)

    @vit.setter
    def vit(self, value):
        self._set_byte(11, value)

    @property
    def mag(self):
        return self._byte(12)

    @mag.setter
    def mag(self, value):
        self._set_byte(12, value)

    @property
    def spr(self):
        return self._byte(13)

    @spr.setter
    def spr(self, value):
        self._set_byte(13, value)

    @property
    def spd(self):
        return self._byte(14)

    @spd.setter
    def spd(self, value):
        self._set_byte(14, value)

    @property
    def luck(self):
        return self._byte(15)

    @luck.setter
    def luck(self, value):
        self._set_byte(15, value)

    # Magic1..32 / Magic1Quantity..32Quantity occupy offset 16..79, exposed via self.magics

    @property
    def command1(self):
        return self._byte(80)

    @command1.setter
    def command1(self, value):
        self._set_byte(80, value)

    @property
    def command2(self):
        return self._byte(81)

    @command2.setter
    def command2(self, value):
        self._set_byte(81, value)

    @property
    def command3(self):
        return self._byte(82)

    @command3.setter
    def command3(self, value):
        self._set_byte(82, value)

    @property
    def unknown1(self):
        return self._byte(83)

    @unknown1.setter
    def unknown1(self, value):
        self._set_byte(83, value)

    @property
    def ability1(self):
        return self._byte(84)

    @ability1.setter
    def ability1(self, value):
        self._set_byte(84, value)

    @property
    def ability2(self):
        return self._byte(85)

    @ability2.setter
    def ability2(self, value):
        self._set_byte(85, value)

    @property
    def ability3(self):
        return self._byte(86)

    @ability3.setter
    def ability3(self, value):
        self._set_byte(86, value)

    @property
    def ability4(self):
        return self._byte(87)

    @ability4.setter
    def ability4(self, value):
        self._set_byte(87, value)

    @property
    def jun_gf1(self):
        return self._byte(88)

    @jun_gf1.setter
    def jun_gf1(self, value):
        self._set_byte(88, value)

    @property
    def jun_gf2(self):
        return self._byte(89)

    @jun_gf2.setter
    def jun_gf2(self, value):
        self._set_byte(89, value)

    @property
    def unknown2(self):
        return self._byte(90)

    @unknown2.setter
    def unknown2(self, value):
        self._set_byte(90, value)

    @property
    def alt_model(self):
        return self._byte(91) != 0

    @alt_model.setter
    def alt_model(self, value):
        self._set_byte(91, 1 if value else 0)

    # Junction stat bonuses, offset 92..110
    _JUNCTION_FIELDS = [
        ("jun_hp", 92), ("jun_str", 93), ("jun_vit", 94), ("jun_mag", 95), ("jun_spr", 96),
        ("jun_spd", 97), ("jun_eva", 98), ("jun_hit", 99), ("jun_luck", 100),
        ("jun_ele_atk", 101), ("jun_status_atk", 102),
        ("jun_ele_def1", 103), ("jun_ele_def2", 104), ("jun_ele_def3", 105), ("jun_ele_def4", 106),
        ("jun_status_def1", 107), ("jun_status_def2", 108), ("jun_status_def3", 109), ("jun_status_def4", 110),
    ]

    @property
    def unknown3(self):
        return self._byte(111)

    @unknown3.setter
    def unknown3(self, value):
        self._set_byte(111, value)

    def get_gf_compatibility(self, gf_id):
        """gf_id is 0-15, matches gforce.json order. GfComp1..16 at offset 112..143."""
        return _u16(self._buffer, self._offset + 112 + gf_id * 2)

    def set_gf_compatibility(self, gf_id, value):
        _set_u16(self._buffer, self._offset + 112 + gf_id * 2, value)

    @property
    def kills(self):
        return _u16(self._buffer, self._offset + 144)

    @kills.setter
    def kills(self, value):
        _set_u16(self._buffer, self._offset + 144, value)

    @property
    def kos(self):
        return _u16(self._buffer, self._offset + 146)

    @kos.setter
    def kos(self, value):
        _set_u16(self._buffer, self._offset + 146, value)

    @property
    def exist(self):
        return self._byte(148) != 0

    @exist.setter
    def exist(self, value):
        self._set_byte(148, 1 if value else 0)

    @property
    def unknown4(self):
        return self._byte(149)

    @unknown4.setter
    def unknown4(self, value):
        self._set_byte(149, value)

    # CurrentStatus is a 16-bit bitmask spanning offset 150-151 (confirmed against IDA's
    # `Status1Flag status_1` struct field), not an 8-bit byte + a separate unknown byte as
    # the original C# tool's struct declaration implied.
    def has_status(self, status_index):
        """status_index is 0-15, see CHARACTER_STATUS_NAMES."""
        return bool(_u16(self._buffer, self._offset + 150) & (1 << status_index))

    def set_status(self, status_index, active):
        value = _u16(self._buffer, self._offset + 150)
        if active:
            value |= (1 << status_index)
        else:
            value &= ~(1 << status_index) & 0xFFFF
        _set_u16(self._buffer, self._offset + 150, value)


# Attach the junction stat properties generically (keeps the list above as the single
# source of truth for their offsets).
def _make_junction_property(add):
    def getter(self):
        return self._byte(add)

    def setter(self, value):
        self._set_byte(add, value)

    return property(getter, setter)


for _name, _add in CharacterEntry._JUNCTION_FIELDS:
    setattr(CharacterEntry, _name, _make_junction_property(_add))


class ConfigEntry:
    """The single 20-byte config record (InitWorker.cs ConfigData)."""

    _FIELDS = [
        "battle_speed", "battle_message", "field_message", "volume", "flag", "scan", "camera",
        "key_unk1", "key_escape", "key_pov", "key_window", "key_trigger", "key_cancel",
        "key_menu", "key_talk", "key_triple_triad", "key_select", "key_unk2", "key_unk3", "key_start",
    ]

    def __init__(self, buffer, offset):
        self._buffer = buffer
        self._offset = offset


def _make_config_property(add):
    def getter(self):
        return self._buffer[self._offset + add]

    def setter(self, value):
        self._buffer[self._offset + add] = value & 0xFF

    return property(getter, setter)


for _add, _name in enumerate(ConfigEntry._FIELDS):
    setattr(ConfigEntry, _name, _make_config_property(_add))


class MiscEntry:
    """The single 80-byte misc record (InitWorker.cs MiscData / ReadMisc).

    Only the first 48 bytes were ever decoded by the original tool; the remaining tail is
    kept untouched (round-tripped as raw bytes) since its meaning is unknown.
    """

    def __init__(self, buffer, offset, game_data: GameData):
        self._buffer = buffer
        self._offset = offset
        self.game_data = game_data

    def _byte(self, add):
        return self._buffer[self._offset + add]

    def _set_byte(self, add, value):
        self._buffer[self._offset + add] = value & 0xFF

    @property
    def party_mem1(self):
        return self._byte(0)

    @party_mem1.setter
    def party_mem1(self, value):
        self._set_byte(0, value)

    @property
    def party_mem2(self):
        return self._byte(1)

    @party_mem2.setter
    def party_mem2(self, value):
        self._set_byte(1, value)

    @property
    def party_mem3(self):
        return self._byte(2)

    @party_mem3.setter
    def party_mem3(self, value):
        self._set_byte(2, value)

    @property
    def party_mem4(self):
        """4th party slot (IDA: `party[4]`); unused by the original C# tool, which treated
        offset 3 as padding, but it is real game data (e.g. 0xFF = empty)."""
        return self._byte(3)

    @party_mem4.setter
    def party_mem4(self, value):
        self._set_byte(3, value)

    # KnownWeapons1..4 live at offset 4..7.
    @property
    def known_weapons1(self):
        return self._byte(4)

    @known_weapons1.setter
    def known_weapons1(self, value):
        self._set_byte(4, value)

    @property
    def known_weapons2(self):
        return self._byte(5)

    @known_weapons2.setter
    def known_weapons2(self, value):
        self._set_byte(5, value)

    @property
    def known_weapons3(self):
        return self._byte(6)

    @known_weapons3.setter
    def known_weapons3(self, value):
        self._set_byte(6, value)

    @property
    def known_weapons4(self):
        return self._byte(7)

    @known_weapons4.setter
    def known_weapons4(self, value):
        self._set_byte(7, value)

    @property
    def griever_name(self):
        start = self._offset + 8
        return self.game_data.translate_hex_to_str(self._buffer[start:start + 12]).strip('\x00')

    @griever_name.setter
    def griever_name(self, value):
        text = bytearray(self.game_data.translate_str_to_hex(value))
        text = (text + bytearray(12))[:12]
        self._buffer[self._offset + 8:self._offset + 20] = text

    # IDA identifies offset 20-23 as 4 individual weapon-id bytes for the Laguna-squad
    # sequence (Laguna/Kiros/Ward), not two unknown u16 fields as the original C# tool's
    # struct implied.
    @property
    def weapon_id_laguna(self):
        return self._byte(20)

    @weapon_id_laguna.setter
    def weapon_id_laguna(self, value):
        self._set_byte(20, value)

    @property
    def weapon_id_kiros(self):
        return self._byte(21)

    @weapon_id_kiros.setter
    def weapon_id_kiros(self, value):
        self._set_byte(21, value)

    @property
    def weapon_id_ward(self):
        return self._byte(22)

    @weapon_id_ward.setter
    def weapon_id_ward(self, value):
        self._set_byte(22, value)

    @property
    def align(self):
        return self._byte(23)

    @align.setter
    def align(self, value):
        self._set_byte(23, value)

    @property
    def gil(self):
        return _u32(self._buffer, self._offset + 24)

    @gil.setter
    def gil(self, value):
        _set_u32(self._buffer, self._offset + 24, value)

    @property
    def gil_laguna(self):
        return _u32(self._buffer, self._offset + 28)

    @gil_laguna.setter
    def gil_laguna(self, value):
        _set_u32(self._buffer, self._offset + 28, value)

    @property
    def limit_quistis1(self):
        return self._byte(32)

    @limit_quistis1.setter
    def limit_quistis1(self, value):
        self._set_byte(32, value)

    @property
    def limit_quistis2(self):
        return self._byte(33)

    @limit_quistis2.setter
    def limit_quistis2(self, value):
        self._set_byte(33, value)

    @property
    def limit_zell1(self):
        return self._byte(34)

    @limit_zell1.setter
    def limit_zell1(self, value):
        self._set_byte(34, value)

    @property
    def limit_zell2(self):
        return self._byte(35)

    @limit_zell2.setter
    def limit_zell2(self, value):
        self._set_byte(35, value)

    @property
    def limit_irvine(self):
        return self._byte(36)

    @limit_irvine.setter
    def limit_irvine(self, value):
        self._set_byte(36, value)

    @property
    def limit_selphie(self):
        return self._byte(37)

    @limit_selphie.setter
    def limit_selphie(self, value):
        self._set_byte(37, value)

    @property
    def limit_angelo_completed(self):
        return self._byte(38)

    @limit_angelo_completed.setter
    def limit_angelo_completed(self, value):
        self._set_byte(38, value)

    @property
    def limit_angelo_known(self):
        return self._byte(39)

    @limit_angelo_known.setter
    def limit_angelo_known(self, value):
        self._set_byte(39, value)

    def get_angelo_point(self, index):
        """index is 0-7."""
        return self._byte(40 + index)

    def set_angelo_point(self, index, value):
        self._set_byte(40 + index, value)


class ItemEntry:
    """One (item id, quantity) pair inside the item table."""

    def __init__(self, buffer, offset, slot_index, game_data: GameData):
        self._buffer = buffer
        self._offset = offset
        self.slot_index = slot_index
        self.game_data = game_data

    @property
    def item_id(self):
        return self._buffer[self._offset]

    @item_id.setter
    def item_id(self, value):
        self._buffer[self._offset] = value & 0xFF

    @property
    def quantity(self):
        return self._buffer[self._offset + 1]

    @quantity.setter
    def quantity(self, value):
        self._buffer[self._offset + 1] = value & 0xFF

    @property
    def name(self):
        for item in self.game_data.item_data_json["items"]:
            if item["id"] == self.item_id:
                return item["name"]
        return f"Item {self.item_id}"


class QuezacotlManager:
    """init.out editor logic, ported from the original Quezacotl C# tool (InitWorker.cs).

    The file is kept as a single in-memory buffer and every entry is a thin view over it
    (mirroring the original tool's direct byte-array mutation), so regions the original
    tool never decoded (Shops, GF.ForgottenAbilities, the Misc raw tail) are preserved
    byte-for-byte on save instead of being reset.
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

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            data = bytearray(in_file.read())
        if len(data) <= FULL_FILE_SIZE - 388:
            # Vanilla init.out only reserves 4 item slots; grow it so every item slot is editable.
            data.extend(bytearray(FULL_FILE_SIZE - len(data)))
        self.buffer = data
        self._parse()

    def _parse(self):
        self.gf_entries = [
            GfEntry(self.buffer, GF_DATA_OFFSET + i * GF_ENTRY_SIZE, i, self.game_data)
            for i in range(NB_GF)
        ]
        self.character_entries = [
            CharacterEntry(self.buffer, CHARACTER_DATA_OFFSET + i * CHARACTER_ENTRY_SIZE, i, self.game_data)
            for i in range(NB_CHARACTERS)
        ]
        self.config = ConfigEntry(self.buffer, CONFIG_DATA_OFFSET)
        self.misc = MiscEntry(self.buffer, MISC_DATA_OFFSET, self.game_data)
        self.item_entries = [
            ItemEntry(self.buffer, ITEMS_DATA_OFFSET + i * ITEM_ENTRY_SIZE, i, self.game_data)
            for i in range(NB_ITEMS)
        ]

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            out_file.write(self.buffer)
