import struct

from FF8GameData.gamedata import GameData

# Character/party ids (IDA: FF8ComId). 0-7 are the playable characters in menu order;
# 8-10 are the Laguna-flashback trio; 0xFF is an empty slot.
CHARACTER_NAMES = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea"]

# Ability id space is the shared FF8Abilities / junctionable_ability enum (kernel_lookups
# json). The game validates the two character ability blocks to these sub-ranges (IDA
# sub_4DA600): "active" (command) abilities 0x14-0x26, "passive" (junction) abilities
# 0x27-0x39. 0 = None/empty in both.
ACTIVE_ABILITY_RANGE = range(0x14, 0x27)   # 20..38 command abilities (Magic, GF, Draw...)
PASSIVE_ABILITY_RANGE = range(0x27, 0x3A)  # 39..57 passive abilities (HP+20%, Str+40%...)
ABILITY_COUNT = 116  # ability ids 0 (none) .. 115 (Card Mod): the 7 kernel.bin ability sections

# GF compatibility per GF (u16). Game clamps to [1000, 6000] (IDA
# itemAction_ModifyGfCompatibility); 1000 = minimum / neutral, 6000 = maximum.
GF_COMPATIBILITY_MIN = 1000
GF_COMPATIBILITY_MAX = 6000

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
# Shops block = 20 shop records x 20 bytes (IDA: SG_SHOP): per record, 16 per-slot availability
# bytes + a 2-byte visited flag + 2 pad. The 16 bytes are a *recomputed cache*: the game
# overwrites them from shop.bin + story flags on every shop entry, so editing them has no
# lasting effect (shop.bin is authoritative). New game zeroes the block. The tool therefore
# preserves it untouched rather than exposing a no-op editor.
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
        """ability_id is the 0-based ability index (== junctionable_ability value).

        The 16-byte block at offset 0x14 is a 128-bit "learned" bitfield; bit i means the
        GF has learned ability id i."""
        byte_index, bit = divmod(ability_id, 8)
        return bool(self._buffer[self._offset + 20 + byte_index] & (1 << bit))

    def set_ability(self, ability_id, learned):
        byte_index, bit = divmod(ability_id, 8)
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

    # Offset 65-67: the "forgotten" bits, one per slot of the GF's kernel.bin ability list (bit k =
    # slot k+1). BuildGFAbilityList reads them as `*(u32 *)&LearningAbility >> 8` and leaves a
    # forgotten slot out of the learnable abilities, so the GF can never learn it again.
    def is_forgotten(self, slot):
        """slot is 1-21."""
        return bool(self._buffer[self._offset + 65 + (slot - 1) // 8] & (1 << ((slot - 1) % 8)))

    def set_forgotten(self, slot, forgotten):
        position = self._offset + 65 + (slot - 1) // 8
        bit = 1 << ((slot - 1) % 8)
        if forgotten:
            self._buffer[position] |= bit
        else:
            self._buffer[position] &= ~bit & 0xFF


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

    # offset 80-83 = activeAbilities[4] (equipped command abilities: Magic/GF/Draw/Item...)
    # offset 84-87 = passifAbilities[4] (equipped passive/junction abilities: HP+20%...)
    # (IDA: CharacterData.activeAbilities / passifAbilities, each an FF8Abilities byte.)
    def get_active_ability(self, slot):
        """slot is 0-3."""
        return self._byte(80 + slot)

    def set_active_ability(self, slot, value):
        self._set_byte(80 + slot, value)

    def get_passive_ability(self, slot):
        """slot is 0-3."""
        return self._byte(84 + slot)

    def set_passive_ability(self, slot, value):
        self._set_byte(84 + slot, value)

    # offset 88-89 = JunctionedGFs: u16 bitmask, bit n = GF n (gforce.json order), so any of the
    # 16 GFs can be junctioned at once (IDA: CharacterData.JunctionedGFs).
    @property
    def junctioned_gfs(self):
        return _u16(self._buffer, self._offset + 88)

    @junctioned_gfs.setter
    def junctioned_gfs(self, value):
        _set_u16(self._buffer, self._offset + 88, value)

    def is_gf_junctioned(self, gf_id):
        """gf_id is 0-15."""
        return bool(self.junctioned_gfs & (1 << gf_id))

    def set_gf_junctioned(self, gf_id, junctioned):
        mask = 1 << gf_id
        self.junctioned_gfs = (self.junctioned_gfs | mask) if junctioned else (self.junctioned_gfs & ~mask)

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

    # Offset 148 (IDA: CharacterData.Exists) is a bitfield, not a boolean:
    #   0x01 in the roster: SCRIPT_ADDMEMBER sets it, SUBMEMBER clears it, ISMEMBER / the party
    #        select / partyRest read it.
    #   0x02 locked in the party (SCRIPT_HOLD sets 0x02|0x04): the party select won't swap it out.
    #   0x04 locked, and keeps its place in the walking field party (the party select keeps it in
    #        SG_PARTY_FIELD1); ADDMEMBER gives Squall 0x0D.
    #   0x08 replaced by Laguna's party in dreams (the dream party setup at 0x4ACF50 swaps the
    #        members having it for Laguna/Kiros/Ward); ADDMEMBER sets it for all but Rinoa,
    #        Seifer and Edea.
    # Bits 4-7 have no reader or writer.
    EXIST_BITS = [
        (0x01, "In the roster"),
        (0x02, "Locked in the party (HOLD)"),
        (0x04, "Locked, keeps its field-party place (HOLD)"),
        (0x08, "Replaced by Laguna's party in dreams"),
    ]

    @property
    def exist(self):
        """In the roster (bit 0x01 of exist_flags)."""
        return bool(self._byte(148) & 0x01)

    @exist.setter
    def exist(self, value):
        self.set_exist_flag(0x01, value)

    @property
    def exist_flags(self):
        return self._byte(148)

    def set_exist_flag(self, mask, value):
        flags = self._byte(148)
        self._set_byte(148, flags | mask if value else flags & ~mask)

    @property
    def unknown4(self):
        return self._byte(149)

    @unknown4.setter
    def unknown4(self, value):
        self._set_byte(149, value)

    # CurrentStatus is a 16-bit bitmask spanning offset 150-151 (IDA: `Status1Flag status_1`),
    # not an 8-bit byte + a separate unknown byte as the original C# tool's struct implied.
    # Only bits 0-6 are real persistent statuses (Death/Poison/Petrify/Darkness/Silence/
    # Berserk/Zombie); bits 8-9 are HP-derived synthetic flags the game recomputes, and 10-15
    # are unused. Bit 7 (IDA STATUS1_UNUSED1) has no known effect, but it is not plain padding:
    # partyRest heals every status except it (status_1 &= 0x80), so the tool keeps it as is.
    def has_status(self, status_index):
        """status_index is a 0-based bit index into the status_1 word."""
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
    """The single 20-byte config record (IDA: SAVEMAP_CONFIG).

    Field names/order follow the EXE struct: offset 7 is the map-seal bitfield, and the last
    12 bytes are the button-remap table (physical slots L2..Start)."""

    _FIELDS = [
        "battle_speed", "battle_message_speed", "field_message_speed", "volume", "flag", "scan", "camera",
        "map_seal", "key_l2", "key_r2", "key_l1", "key_r1", "key_triangle", "key_circle",
        "key_cross", "key_square", "key_select", "key_l3", "key_r3", "key_start",
    ]

    # Offset 3 ("volume", IDA SAVEMAP_CONFIG.analog_volume) is not a sound volume: its only reader
    # is sub_4C3010, which sets the pad's analog dead zone from it (the save code only copies it).
    ANALOG_DEAD_ZONE_HELP = ("Analog stick dead zone (offset 0x03, not a sound volume). The game sets the "
                             "stick threshold to (12 x (value + 5))² / 256, capped at 127: a stick pushed "
                             "less than that counts as centred. Values above 5 all hit the cap.")

    # map_seal (offset 7) bit meanings (IDA: MapSeal enum).
    MAP_SEAL_BITS = [
        (0x01, "Item locked"), (0x02, "Magic locked"), (0x04, "GF locked"), (0x08, "Draw locked"),
        (0x10, "Command ability locked"), (0x20, "Limit break locked"),
        (0x40, "Resurrection locked"), (0x80, "Save locked"),
    ]

    # flag (offset 4) bit meanings (IDA). Some bits are hardware-managed and normally set by
    # the game, not the player (marked "auto").
    #
    # Identified by walking all 26 references to SG_SETTING.flag (0x1CFE73C) and decoding the
    # mask each one tests. The in-game Config menu drives its rows from a 16-byte-stride table
    # at 0xB88978 (mask at +0, optional handler at +4, three text ids at +8/+10/+12); its rows
    # are 0x20 (Controls, handler 0x4EDD20), 0x04 (Cursor), 0x01 (Battle Mode) and 0x100 - the
    # last being bit 0 of the *scan* byte at offset 5, since the code reads flag as a word.
    #
    #   0x01 is Battle Mode: Wait. Battle_ShouldAtbKeepRunning (0x4A9450) freezes the ATB gauges
    #        while a command is pending only when it is set (Active when clear).
    #   0x10 is written by battle_vibrate_init (0x4A93A1 sets it, 0x4A93B6 clears it) and read by
    #        BattleUI_InitForBattle: the pad can vibrate.
    #   0x80 swaps the analog sticks: sub_4C3010 copies it (only when 0x20 custom controls is on)
    #        into the pad's gamepad_options bit 7, which makes sub_49F0A0 read axis ^ 2.
    #   0x04 is the Config menu's "Cursor: Memory". BattleMenu_CommandWindow_Update tests it at
    #        0x4BBBC5 / 0x4BC659, and the stub at 0x4BB9B0 wipes the per-character remembered
    #        cursor slots (BATTLE_CHARA_UI +0x54..+0x68) when it is CLEAR - i.e. Cursor: Initial.
    #   0x02 has exactly one reader, au_re_xorEAX_0_0 (0x4C2FD0), which computes (flag >> 1) & 1
    #        and passes it to return_0 - a do-nothing stub. It is a PSX audio setting whose
    #        consumer the PC port replaced with a stub (FF8's PSX Config menu had a Sound
    #        stereo/mono row); nothing in the PC build reads or writes it.
    #   0x08 has no reader and no writer at all among those 26 references.
    #   0x40 is NOT 'no controller detected'. sub_4C3060 (0x4C3060) reads the pad's
    #        vibrate_option_enabled for port 0 via sub_49F150 and sets the bit when it is 0xFF,
    #        and sub_4C2FF0 (0x4C2FF0) pushes it back the other way through sub_49F170 - a
    #        straight get/set pair, i.e. the persisted pad vibration option. (Distinct from
    #        vibrate_capable, which is a separate field of the same input struct.)
    FLAG_BITS = [
        (0x01, "Battle Mode: Wait (unset = Active)"),
        (0x02, "PSX audio setting (stubbed on PC)"),
        (0x04, "Cursor: Memory"),
        (0x08, "Bit 3 (unused - no reader or writer)"),
        (0x10, "Vibration hardware present (auto)"),
        (0x20, "Use custom button config"),
        (0x40, "Pad vibration option (auto)"),
        (0x80, "Swap analog sticks (with custom controls)"),
    ]
    UNUSED_FLAG_BITS = (0x02, 0x08)  # nothing in the PC build acts on them (see above)

    # The 12 remap bytes are physical button slots, in this order. The order is the PSX
    # DualShock button word (see remap_pad_input @0x4A2D60), so slots 9 and 10 are L3 and R3 -
    # they were previously mislabelled "Unknown 1/2" on the belief that a PSX pad has only ten
    # configurable buttons.
    KEY_FIELDS = [
        ("key_l2", "L2"), ("key_r2", "R2"), ("key_l1", "L1"), ("key_r1", "R1"),
        ("key_triangle", "Triangle"), ("key_circle", "Circle"), ("key_cross", "Cross"),
        ("key_square", "Square"), ("key_select", "Select"), ("key_l3", "L3"),
        ("key_r3", "R3"), ("key_start", "Start"),
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
    """The single 80-byte misc record (IDA: SG_PARTY_BATTLE + the limit-break globals).

    The first 48 bytes (party, unlocked weapons, Griever name, weapon ids, gil, limit-break
    unlocks) are edited here. The 32-byte tail (offset 0x30) is the items-battle-order array
    (index = battle-usable item id - 1, value = its place in the in-battle item menu), edited
    as a reordering only (get/set_battle_order).
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
        """Offset 3 is unused padding — the high byte of the 32-bit party word. FF8's party is
        fixed at 3 members (every party reader/writer bounds at index 3); the game never stores
        a character here. Preserved but never edited."""
        return self._byte(3)

    @party_mem4.setter
    def party_mem4(self, value):
        self._set_byte(3, value)

    # Offset 4-7 is a single u32 bitmask (IDA: SAVEMAP_MISC1.unlocked_weapons): bit i =
    # weapon-upgrade recipe i has been built/owned (read/written by the Junk Shop). The
    # original C# tool exposed it as 4 separate "KnownWeapons" bytes; the u32 view is the
    # real field.
    @property
    def unlocked_weapons(self):
        return _u32(self._buffer, self._offset + 4)

    @unlocked_weapons.setter
    def unlocked_weapons(self, value):
        _set_u32(self._buffer, self._offset + 4, value)

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

    # Offset 0x17 is not padding (the IDB's misleading `align` name): it is a persisted
    # status/limit menu cursor-selection byte, read by the status-menu init code. Kept as a
    # raw byte; the tool preserves it rather than exposing a cursor position.
    @property
    def status_menu_selection(self):
        return self._byte(23)

    @status_menu_selection.setter
    def status_menu_selection(self, value):
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

    # Quistis (0x20) and Zell (0x22) limit-break unlocks are each a 16-bit bitfield spanning
    # two bytes (Blue Magic / Duel moves). Exposed as u16 for the checkbox editors; the
    # per-byte views below remain for completeness.
    @property
    def limit_quistis(self):
        return _u16(self._buffer, self._offset + 32)

    @limit_quistis.setter
    def limit_quistis(self, value):
        _set_u16(self._buffer, self._offset + 32, value)

    @property
    def limit_zell(self):
        return _u16(self._buffer, self._offset + 34)

    @limit_zell.setter
    def limit_zell(self, value):
        _set_u16(self._buffer, self._offset + 34, value)

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

    # Offset 48-79: SG_ITEM_BATTLE_ORDER, battle_order[item id - 1] = the place (0-31) of battle item
    # 1-32 in the in-battle Item list. It must stay a permutation of 0-31: the Item menu's init
    # (sub_4F8180) writes BATTLE_ORDER_EDIT_ID[2 * place] for each item, so a place of 32 or more
    # writes past those 32-entry arrays, and a repeated place leaves another one empty.
    # Inventory_ReserveBattleOrderPosition swaps a newly obtained battle item into the first place
    # no owned item uses.
    BATTLE_ORDER_SIZE = 32

    def get_battle_order(self):
        return list(self._buffer[self._offset + 48:self._offset + 48 + self.BATTLE_ORDER_SIZE])

    def set_battle_order(self, order):
        if sorted(order) != list(range(self.BATTLE_ORDER_SIZE)):
            raise ValueError("The battle item order must hold each place 0-31 exactly once")
        self._buffer[self._offset + 48:self._offset + 48 + self.BATTLE_ORDER_SIZE] = bytes(order)


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
    tool never decoded (Shops) are preserved byte-for-byte on save instead of being reset.
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
