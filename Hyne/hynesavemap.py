"""
The rest of a save's game state, as views over the 8192-byte image buffer of HyneManager: what the
GF / character / config / misc / item entries shared with Quezacotl don't cover (init.out ends
before it). Offsets are image-absolute.

Layout, from myst6re/hyne's SaveData.h, cross-checked against FF8_EN.exe (Save_BuildSaveFileImage
@0x4E2EF0, the SavemapVariables struct) and real saves:
  [388..463]    load-screen header (SaveHeader)            outside the CRC span
  [2768..3167]  20 shops of 20 bytes (ShopEntry)
  [3664..3807]  battle counters and flags, tutorials, field party, position
  [3808..]      field variables: variable N = byte at 3808 + N (also the second copies of gil,
                battle counts, kills and deaths, and the draw points)
  [5088..5215]  world map state (WorldMapState)
  [5344..5407]  Chocobo World (ChocoboWorld)

The game reads some values from a second place. HyneManager keeps those together on save, see
HyneManager._sync_copies.
"""
import struct

SAVE_HEADER_OFFSET = 388
SHOPS_OFFSET = 2768
BATTLE_BLOCK_OFFSET = 3664
FIELD_VARS_OFFSET = 3808
WORLD_MAP_OFFSET = 5088
CHOCOBO_OFFSET = 5344

NB_SHOPS = 20
SHOP_SIZE = 20
SHOP_NB_ITEMS = 16
NB_DRAW_POINTS = 256
DRAW_POINT_STATES = ["Filled", "Half-filled", "Empty", "Completely empty"]
NB_WORLD_POSITIONS = 8
WORLD_POSITION_VALUES = 6
WORLD_PLACE_FORMAT = "<iihH"
NAME_SIZE = 12
MAX_LEVEL = 100
# FFNx moves the enemies scanned once here when scene.out uses a monster of its extra ones (com id
# 160 and up, src/ff8/battle/monsters.cpp): field variables 785-816, one bit per com id.
# FFNx AddMoreMagic keeps the magic drawn once here, all 256 ids, when kernel.bin holds a magic id of 96 or more
MAGIC_MOVED_VAR = 753
MAGIC_MOVED_BITS = 256
EXTENDED_MAGIC_FIRST = 96
SCANNED_MOVED_VAR = 785
SCANNED_MOVED_BITS = 256
SCANNED_VANILLA_BITS = 160
SCENE_RECORD_SIZE = 128
SCENE_ENEMY_IDS_OFFSET = 56
SCENE_ENEMY_SLOTS = 8
FIRST_EXTRA_MONSTER_COM_ID = 160
SHOP_FILE_SIZE = NB_SHOPS * SHOP_NB_ITEMS * 2
SHOP_FILE_RARE_MAX = 128  # (item id, flag) per slot: up to this flag sold only with Familiar (vanilla: 0 or 255)


def scene_uses_extra_monsters(scene_data):
    """FFNx's own test for moving the enemies scanned once: does an encounter use a com id of 160 or up?"""
    return any(scene_data[record + SCENE_ENEMY_IDS_OFFSET + slot] >= FIRST_EXTRA_MONSTER_COM_ID
               for record in range(0, len(scene_data) - SCENE_RECORD_SIZE + 1, SCENE_RECORD_SIZE)
               for slot in range(SCENE_ENEMY_SLOTS))


def read_shop_file(data):
    """shop.bin's [(item ids, rare slots)] by shop. Only its first 20 x 32 bytes count: the game reads
    no further (Cronos's file is twice that, the vanilla list repeated after its own)."""
    if len(data) < SHOP_FILE_SIZE:
        raise ValueError(f"shop.bin too small: {len(data)} bytes, expected {SHOP_FILE_SIZE}")
    shops = []
    for shop in range(NB_SHOPS):
        start = shop * SHOP_NB_ITEMS * 2
        pairs = [(data[start + 2 * slot], data[start + 2 * slot + 1]) for slot in range(SHOP_NB_ITEMS)]
        shops.append(([item for item, _flag in pairs],
                      [slot for slot, (_item, flag) in enumerate(pairs) if flag <= SHOP_FILE_RARE_MAX]))
    return shops


class Int:
    """A little-endian integer field of a view, its offset relative to the view's base."""

    def __init__(self, fmt, offset):
        self.fmt = "<" + fmt
        self.offset = offset

    def __get__(self, view, owner=None):
        return struct.unpack_from(self.fmt, view.buffer, view.base + self.offset)[0]

    def __set__(self, view, value):
        struct.pack_into(self.fmt, view.buffer, view.base + self.offset, value)


class Bits:
    """A run of flag bits (LSB first) of the image, read and set by index."""

    def __init__(self, buffer, offset, count):
        self.buffer = buffer
        self.offset = offset
        self.count = count

    def __len__(self):
        return self.count

    def __iter__(self):
        return (self[index] for index in range(self.count))

    def __getitem__(self, index):
        return bool(self.buffer[self.offset + index // 8] & (1 << (index % 8)))

    def __setitem__(self, index, value):
        if value:
            self.buffer[self.offset + index // 8] |= 1 << (index % 8)
        else:
            self.buffer[self.offset + index // 8] &= ~(1 << (index % 8)) & 0xFF

    def set_indexes(self):
        return [index for index in range(self.count) if self[index]]

    def set_from_indexes(self, indexes):
        chosen = set(indexes)
        for index in range(self.count):
            self[index] = index in chosen


class SaveView:
    """Base of the views: `FIELDS` are the attributes the CLI's JSON carries, a Bits one as the list
    of its set indexes."""
    FIELDS = ()

    def __init__(self, buffer, base=0):
        self.buffer = buffer
        self.base = base

    def bits(self, offset, count):
        return Bits(self.buffer, self.base + offset, count)

    def to_dict(self):
        data = {}
        for field in self.FIELDS:
            value = getattr(self, field)
            data[field] = value.set_indexes() if isinstance(value, Bits) else value
        return data

    def from_dict(self, data):
        for field in self.FIELDS:
            if field in data:
                value = getattr(self, field)
                if isinstance(value, Bits):
                    value.set_from_indexes(data[field])
                elif value != data[field]:   # a value held twice keeps its copies unless it changed
                    setattr(self, field, data[field])


# The field variables another tab holds, (first, last, tab): that tab keeps their copies in step
FIELD_VARS_ELSEWHERE = (
    (4, 11, "Progress"), (16, 17, "Progress"), (20, 23, "Battle"), (26, 27, "Battle"), (28, 59, "Characters"),
    (68, 71, "Battle"), (72, 79, "Misc"), (80, 85, "Progress"), (116, 179, "Draw points"), (204, 204, "Progress"),
    (256, 257, "Progress"), (272, 291, "Triple Triad"), (295, 300, "Triple Triad"), (304, 305, "Items"),
    (475, 475, "Triple Triad"), (477, 478, "Triple Triad"),
    (MAGIC_MOVED_VAR, MAGIC_MOVED_VAR + MAGIC_MOVED_BITS // 8 - 1, "Battle"), (SCANNED_MOVED_VAR, SCANNED_MOVED_VAR + SCANNED_MOVED_BITS // 8 - 1, "Battle"),
)
NB_FIELD_VARS = 1024


def field_var_tab(var):
    """The tab holding this field variable, None if only the Variables tab does."""
    for first, last, tab in FIELD_VARS_ELSEWHERE:
        if first <= var <= last:
            return tab
    return None


class FieldVariables(SaveView):
    """The field variables by number. The CLI's JSON carries the bytes no other section holds, those not zero."""

    def __init__(self, buffer):
        super().__init__(buffer, FIELD_VARS_OFFSET)

    def value(self, var, size=1, signed=False):
        start = self.base + var
        return int.from_bytes(self.buffer[start:start + size], "little", signed=signed)

    def set_value(self, var, value, size=1, signed=False):
        start = self.base + var
        self.buffer[start:start + size] = value.to_bytes(size, "little", signed=signed)

    def to_dict(self):
        return {str(var): self.value(var) for var in range(NB_FIELD_VARS) if self.value(var) and field_var_tab(var) is None}

    def from_dict(self, data):
        for var, value in data.items():
            if field_var_tab(int(var)) is None:
                self.set_value(int(var), value)


class SaveHeader(SaveView):
    """The load screen's copy of the save (savemap +4), plus the names only kept here."""
    FIELDS = ("location", "leader_hp", "leader_max_hp", "save_count", "gil", "time", "level",
              "party_1", "party_2", "party_3", "squall_name", "rinoa_name", "angelo_name", "boko_name",
              "disc", "current_save")

    location = Int("H", 0)
    leader_hp = Int("H", 2)
    leader_max_hp = Int("H", 4)
    save_count = Int("H", 6)
    gil = Int("I", 8)
    time = Int("I", 12)
    level = Int("B", 16)
    party_1 = Int("B", 17)
    party_2 = Int("B", 18)
    party_3 = Int("B", 19)
    disc = Int("I", 68)      # 0-based
    current_save = Int("I", 72)

    def __init__(self, buffer, game_data):
        super().__init__(buffer, SAVE_HEADER_OFFSET)
        self.game_data = game_data

    def _name(self, offset):
        start = self.base + offset
        return self.game_data.translate_hex_to_str(self.buffer[start:start + NAME_SIZE]).strip('\x00')

    def _set_name(self, offset, value):
        text = bytearray(self.game_data.translate_str_to_hex(value))
        start = self.base + offset
        self.buffer[start:start + NAME_SIZE] = (text + bytearray(NAME_SIZE))[:NAME_SIZE]

    @property
    def squall_name(self):
        return self._name(20)

    @squall_name.setter
    def squall_name(self, value):
        self._set_name(20, value)

    @property
    def rinoa_name(self):
        return self._name(32)

    @rinoa_name.setter
    def rinoa_name(self, value):
        self._set_name(32, value)

    @property
    def angelo_name(self):
        return self._name(44)

    @angelo_name.setter
    def angelo_name(self, value):
        self._set_name(44, value)

    @property
    def boko_name(self):
        return self._name(56)

    @boko_name.setter
    def boko_name(self, value):
        self._set_name(56, value)


class ProgressState(SaveView):
    """Play time, steps, SeeD, story progress and the tutorial entries read."""
    FIELDS = ("game_time", "countdown", "steps", "seed_pay", "seed_points", "seed_test_level", "last_field",
              "movie_frame", "story_moment", "disc", "timber_maniacs_bits", "tutorials")

    game_time = Int("I", 0)        # seconds (the header copies it)
    countdown = Int("I", 4)
    seed_test_level = Int("B", 99)
    steps = Int("I", 144 + 4)
    seed_pay = Int("I", 144 + 8)
    seed_points = Int("H", 144 + 16)   # the rank shown is points / 100 (GetSeeDRankFromPoints@0x4C3090)
    movie_frame = Int("I", 144 + 80)
    last_field = Int("H", 144 + 84)
    disc = Int("B", 144 + 204)     # 1-based
    story_moment = Int("H", 144 + 256)

    def __init__(self, buffer):
        super().__init__(buffer, BATTLE_BLOCK_OFFSET)

    @property
    def tutorials(self):
        return self.bits(83, 128)

    @property
    def timber_maniacs_bits(self):
        """The issues read (field variable 304)."""
        return self.bits(144 + 304, 16)


class PartyState(SaveView):
    """The party walking on the field (Laguna's squad included) and where it is."""
    FIELDS = ("party_1", "party_2", "party_3", "module", "location", "last_location", "positions")

    party_1 = Int("B", 104)
    party_2 = Int("B", 105)
    party_3 = Int("B", 106)
    module = Int("H", 112)         # 1 field, 2 world map, 3 battle
    location = Int("H", 114)
    last_location = Int("H", 116)

    def __init__(self, buffer):
        super().__init__(buffer, BATTLE_BLOCK_OFFSET)

    def position(self, member):
        """(x, y, triangle id, direction) of a party member."""
        x = struct.unpack_from("<h", self.buffer, self.base + 118 + 2 * member)[0]
        y = struct.unpack_from("<h", self.buffer, self.base + 124 + 2 * member)[0]
        triangle = struct.unpack_from("<H", self.buffer, self.base + 130 + 2 * member)[0]
        return x, y, triangle, self.buffer[self.base + 136 + member]

    def set_position(self, member, x, y, triangle, direction):
        struct.pack_into("<h", self.buffer, self.base + 118 + 2 * member, x)
        struct.pack_into("<h", self.buffer, self.base + 124 + 2 * member, y)
        struct.pack_into("<H", self.buffer, self.base + 130 + 2 * member, triangle)
        self.buffer[self.base + 136 + member] = direction

    @property
    def positions(self):
        return [list(self.position(member)) for member in range(3)]

    @positions.setter
    def positions(self, values):
        for member, value in enumerate(values):
            self.set_position(member, *value)


class BattleState(SaveView):
    """Battle counts, first-time flags, Renzokuken and special-flag bytes, magic drawn and enemies
    scanned once. Wins and escapes have a second copy in the field variables, written together."""
    FIELDS = ("wins", "escapes", "total_kills", "tonberries", "tonberry_king", "ufo", "first_bite_bug", "first_bomb",
              "first_t_rexaur", "first_irvine", "renzokuken_flags", "renzokuken_indicator", "special_flags",
              "magic_moved", "magic_drawn", "scan_moved", "enemies_scanned")

    _copy1_wins = Int("I", 12)
    _copy2_wins = Int("I", 144 + 20)
    _copy1_escapes = Int("H", 18)
    _copy2_escapes = Int("H", 144 + 26)
    total_kills = Int("I", 144 + 68)
    tonberries = Int("I", 24)
    _tonberry_king = Int("I", 28)
    _ufo = Int("I", 32)
    _first_bite_bug = Int("I", 36)
    _first_bomb = Int("I", 40)
    _first_t_rexaur = Int("I", 44)
    _first_irvine = Int("I", 48)
    renzokuken_flags = Int("B", 80)        # bit 0 Renzokuken auto, bit 1 Ring Master auto
    renzokuken_indicator = Int("B", 81)    # 128 or more: no indicator
    special_flags = Int("B", 82)           # bit 0 dream world, then SPECIAL_FLAGS_NAMES

    SPECIAL_FLAG_NAMES = ["Dream world (Laguna's squad)", "Odin", "Phoenix", "Gilgamesh", "Angelo disabled", "Angel Wing enabled"]

    def __init__(self, buffer):
        super().__init__(buffer, BATTLE_BLOCK_OFFSET)
        self.magic_moved = False  # the magic drawn once are where FFNx moves them, not read from the save
        self.scan_moved = False  # the enemies scanned once are where FFNx moves them, not read from the save

    def moved_scan_block_used(self):
        start = FIELD_VARS_OFFSET + SCANNED_MOVED_VAR
        return any(self.buffer[start:start + SCANNED_MOVED_BITS // 8])

    @property
    def wins(self):
        return self._copy1_wins

    @wins.setter
    def wins(self, value):
        self._copy1_wins = value
        self._copy2_wins = value

    @property
    def escapes(self):
        return self._copy1_escapes

    @escapes.setter
    def escapes(self, value):
        self._copy1_escapes = value
        self._copy2_escapes = value

    # The first-time flags are 32-bit battle-script variables, only bit 0 means something
    @property
    def tonberry_king(self):
        return bool(self._tonberry_king & 1)

    @tonberry_king.setter
    def tonberry_king(self, value):
        self._tonberry_king = (self._tonberry_king & ~1) | int(value)

    @property
    def ufo(self):
        return bool(self._ufo & 1)

    @ufo.setter
    def ufo(self, value):
        self._ufo = (self._ufo & ~1) | int(value)

    @property
    def first_bite_bug(self):
        return bool(self._first_bite_bug & 1)

    @first_bite_bug.setter
    def first_bite_bug(self, value):
        self._first_bite_bug = (self._first_bite_bug & ~1) | int(value)

    @property
    def first_bomb(self):
        return bool(self._first_bomb & 1)

    @first_bomb.setter
    def first_bomb(self, value):
        self._first_bomb = (self._first_bomb & ~1) | int(value)

    @property
    def first_t_rexaur(self):
        return bool(self._first_t_rexaur & 1)

    @first_t_rexaur.setter
    def first_t_rexaur(self, value):
        self._first_t_rexaur = (self._first_t_rexaur & ~1) | int(value)

    @property
    def first_irvine(self):
        return bool(self._first_irvine & 1)

    @first_irvine.setter
    def first_irvine(self, value):
        self._first_irvine = (self._first_irvine & ~1) | int(value)

    @property
    def magic_drawn(self):
        """Bit N = magic id N + 1 drawn once. See magic_moved for where they are."""
        if self.magic_moved:
            return Bits(self.buffer, FIELD_VARS_OFFSET + MAGIC_MOVED_VAR, MAGIC_MOVED_BITS)
        return self.bits(52, 64)

    @property
    def enemies_scanned(self):
        """Save_MarkEnemySpeciesScanned@0x493810, bit = the battle slot's com_file_id: 0-15 party
        members, 16 and up monster c0m(N - 16). See scan_moved for where they are."""
        if self.scan_moved:
            return Bits(self.buffer, FIELD_VARS_OFFSET + SCANNED_MOVED_VAR, SCANNED_MOVED_BITS)
        return self.bits(60, SCANNED_VANILLA_BITS)


class ShopsState(SaveView):
    """The 20 shops. Each time one opens (ShopMenu_Enter@0x4EBBA0) the game sets its visited word, which is
    all the Call Shop list reads, and rewrites the item bytes from shop.bin and Familiar: they only record
    what was on sale last."""
    FIELDS = ("visited", "items")

    def __init__(self, buffer):
        super().__init__(buffer, SHOPS_OFFSET)

    def _shop(self, shop):
        return self.base + shop * SHOP_SIZE

    def is_visited(self, shop):
        return struct.unpack_from("<H", self.buffer, self._shop(shop) + SHOP_NB_ITEMS)[0] != 0

    def set_visited(self, shop, visited):
        struct.pack_into("<H", self.buffer, self._shop(shop) + SHOP_NB_ITEMS, int(visited))

    def has_item(self, shop, slot):
        return bool(self.buffer[self._shop(shop) + slot] & 1)

    @property
    def visited(self):
        return [self.buffer[self._shop(shop) + SHOP_NB_ITEMS] for shop in range(NB_SHOPS)]

    @visited.setter
    def visited(self, values):
        for shop, value in enumerate(values):
            self.buffer[self._shop(shop) + SHOP_NB_ITEMS] = value

    @property
    def items(self):
        return [list(self.buffer[self._shop(shop):self._shop(shop) + SHOP_NB_ITEMS]) for shop in range(NB_SHOPS)]

    @items.setter
    def items(self, values):
        for shop, value in enumerate(values):
            self.buffer[self._shop(shop):self._shop(shop) + SHOP_NB_ITEMS] = bytes(value)


class DrawPointsState(SaveView):
    """Each of the 256 draw points' state, 2 bits (field variables 116-179): 0-127 in fields, 128-255
    on the world map, indexes as in FF8_EN.exe's DrawPointData."""
    FIELDS = ("states",)

    def __init__(self, buffer):
        super().__init__(buffer, FIELD_VARS_OFFSET + 116)

    def state(self, point):
        return (self.buffer[self.base + point // 4] >> (2 * (point % 4))) & 3

    def set_state(self, point, state):
        position = self.base + point // 4
        shift = 2 * (point % 4)
        self.buffer[position] = (self.buffer[position] & ~(3 << shift) & 0xFF) | (state << shift)

    @property
    def states(self):
        return [self.state(point) for point in range(NB_DRAW_POINTS)]

    @states.setter
    def states(self, values):
        for point, state in enumerate(values):
            self.set_state(point, state)


class WorldMapState(SaveView):
    """World map steps, rental car, displayed map, vehicles driven and the PuPu and Obel Lake quests."""
    FIELDS = ("steps", "car_steps", "rental_car", "displayed_map", "vehicles", "pupu_quest", "obel_quest", "positions")

    steps = Int("H", 96)
    rental_car = Int("B", 98)      # 0 forbidden, 255 none
    displayed_map = Int("B", 110)  # 0 none, 1 globe, 2 map
    car_steps = Int("H", 112)
    obel_state = Int("B", 124)     # the scripts' variable 0, also inside obel_quest for the JSON

    def __init__(self, buffer):
        super().__init__(buffer, WORLD_MAP_OFFSET)

    @property
    def vehicles(self):
        return self.bits(116, 8)

    @property
    def pupu_quest(self):
        return self.bits(117, 8)

    @property
    def obel_quest(self):
        return self.bits(118, 64)

    def place(self, row):
        """(x, y, height, angle) of a position row, what World_SaveWorldmapStateToSavemap@0x549E80 stores."""
        return struct.unpack_from(WORLD_PLACE_FORMAT, self.buffer, self.base + 2 * row * WORLD_POSITION_VALUES)

    def set_place(self, row, x, y, height, angle):
        struct.pack_into(WORLD_PLACE_FORMAT, self.buffer, self.base + 2 * row * WORLD_POSITION_VALUES, x, y, height, angle)

    def position(self, row, column):
        return struct.unpack_from("<h", self.buffer, self.base + 2 * (row * WORLD_POSITION_VALUES + column))[0]

    def set_position(self, row, column, value):
        struct.pack_into("<h", self.buffer, self.base + 2 * (row * WORLD_POSITION_VALUES + column), value)

    @property
    def positions(self):
        return [[self.position(row, column) for column in range(WORLD_POSITION_VALUES)]
                for row in range(NB_WORLD_POSITIONS)]

    @positions.setter
    def positions(self, values):
        for row, row_values in enumerate(values):
            for column, value in enumerate(row_values):
                self.set_position(row, column, value)


def _from_decimal_nibbles(value, digits):
    """A number stored one decimal digit per 4 bits, as the game shows it."""
    result = 0
    for digit in range(digits):
        result += min(9, (value >> (4 * digit)) & 0xF) * 10 ** digit
    return result


def _to_decimal_nibbles(value, digits):
    result = 0
    for digit in range(digits):
        result |= ((value // 10 ** digit) % 10) << (4 * digit)
    return result


class ChocoboWorld(SaveView):
    """Boko's Chocobo World state."""
    FIELDS = ("flags", "level", "current_hp", "max_hp", "weapon", "rank", "move", "save_count", "boko_id",
              "class_a_items", "class_b_items", "class_c_items", "class_d_items", "summon_level")

    level = Int("B", 1)
    current_hp = Int("B", 2)
    max_hp = Int("B", 3)
    _weapon = Int("H", 4)
    _rank = Int("B", 6)
    move = Int("B", 7)
    save_count = Int("I", 8)
    _boko_id = Int("H", 12)
    class_a_items = Int("B", 20)
    class_b_items = Int("B", 21)
    class_c_items = Int("B", 22)
    class_d_items = Int("B", 23)
    summon_level = Int("B", 45)    # 0 ChocoFire, 1 ChocoFlare, 2 ChocoMeteor, 3 ChocoBocle

    def __init__(self, buffer):
        super().__init__(buffer, CHOCOBO_OFFSET)

    @property
    def flags(self):
        """Bit 0 enabled, then FLAG_NAMES."""
        return self.bits(0, 8)

    FLAG_NAMES = ["Enabled", "Inside Chocobo World", "MiniMog found", "MiniMog obtained", "MiniMog waiting",
                  "Demon King defeated", "Current event seen", "Event wait OFF"]

    @property
    def weapon(self):
        return _from_decimal_nibbles(self._weapon, 4)

    @weapon.setter
    def weapon(self, value):
        self._weapon = _to_decimal_nibbles(value, 4)

    @property
    def rank(self):
        """1 is the best."""
        return self._rank + 1

    @rank.setter
    def rank(self, value):
        self._rank = value - 1

    @property
    def boko_id(self):
        return _from_decimal_nibbles(self._boko_id, 3)

    @boko_id.setter
    def boko_id(self, value):
        self._boko_id = (self._boko_id & 0xF000) | _to_decimal_nibbles(value, 3)
