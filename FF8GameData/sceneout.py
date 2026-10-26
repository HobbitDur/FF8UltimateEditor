"""scene.out: the game's encounter list.

The file is a headerless array of 1024 records of 128 bytes (see the wiki's
BattleStructure page): stage id, flags, the two intro-camera bytes, four per-slot flag
bitmasks (MSB = slot 0), 8 slots x 3 int16 coordinates, 8 enemy id bytes (c0m file
number + 0x10), 56 unknown bytes and 8 levels.

Encounter is the read-only view the previews use ("where does THIS monster stand in a
real fight"); EncounterRecord is the editable one (JumboCactuar, the CLI), a 128-byte
buffer with a property per field, so every byte not edited is written back as read.

No Qt: pure parsing, testable headless, usable by the CLI.
"""

ENCOUNTER_SIZE = 128
NB_ENCOUNTER = 1024
NB_SLOT = 8
ENEMY_ID_BASE = 0x10   # enemy id byte = c0m file number + 0x10

OFFSET_STAGE = 0x00
OFFSET_FLAGS = 0x01
OFFSET_CAMERA_MAIN = 0x02
OFFSET_CAMERA_SECONDARY = 0x03
OFFSET_NOT_VISIBLE = 0x04
OFFSET_NOT_LOADED = 0x05
OFFSET_NOT_TARGETABLE = 0x06
OFFSET_ENABLED = 0x07
OFFSET_POSITION = 0x08   # 8 x (x, y, z) int16
OFFSET_ENEMY = 0x38
OFFSET_UNKNOWN = 0x40
UNKNOWN_SIZE = 56        # never read by FF8_EN.exe
OFFSET_LEVEL = 0x78

# Battle flags byte, bit 0 first
BATTLE_FLAG_NAMES = ["Disable Escape", "Disable Victory Fanfare", "Show Timer", "Disable EXP Gain",
                     "Disable Post-Battle Screen", "Surprise Attack", "Back Attack", "Force Normal Battle"]
# The four per-slot bitmasks, by their offset in the record
SLOT_FLAG_OFFSETS = {"enabled": OFFSET_ENABLED, "not_targetable": OFFSET_NOT_TARGETABLE,
                     "not_visible": OFFSET_NOT_VISIBLE, "not_loaded": OFFSET_NOT_LOADED}

CAMERA_SET_MAX = 15   # high nibble: the camera animation set of the stage .x
CAMERA_ANIM_MAX = 7   # bits 0-2: the animation in that set (bit 3 is unused, kept as read)


class EncounterSlot:
    """One of the 8 monster slots of an encounter."""

    __slots__ = ("slot_index", "enemy_id", "position", "level",
                 "enabled", "visible", "loaded", "targetable")

    def __init__(self, slot_index, enemy_id, position, level, enabled, visible,
                 loaded, targetable):
        self.slot_index = slot_index
        self.enemy_id = enemy_id        # raw byte (c0m number + 0x10)
        self.position = position        # (x, y, z) signed, battle world units
        self.level = level
        self.enabled = enabled
        self.visible = visible
        self.loaded = loaded
        self.targetable = targetable

    @property
    def com_file_id(self):
        """The c0mNNN.dat number this slot loads."""
        return self.enemy_id - ENEMY_ID_BASE


class Encounter:
    """One 128-byte scene.out record."""

    __slots__ = ("index", "stage_id", "flags", "camera_main", "camera_secondary",
                 "slots", "raw")

    def __init__(self, index, record):
        self.index = index
        self.raw = bytes(record)
        self.stage_id = record[0x00]
        self.flags = record[0x01]
        self.camera_main = record[0x02]
        self.camera_secondary = record[0x03]
        not_visible, not_loaded, not_targetable, enabled = record[0x04:0x08]
        self.slots = []
        for slot_index in range(NB_SLOT):
            bit = 0x80 >> slot_index   # MSB = slot 0, per the wiki
            base = 0x08 + slot_index * 6
            position = tuple(int.from_bytes(record[base + axis * 2:base + axis * 2 + 2],
                                            "little", signed=True) for axis in range(3))
            self.slots.append(EncounterSlot(
                slot_index, record[0x38 + slot_index], position,
                record[0x78 + slot_index],
                enabled=bool(enabled & bit), visible=not (not_visible & bit),
                loaded=not (not_loaded & bit), targetable=not (not_targetable & bit)))

    def enabled_slots(self):
        return [slot for slot in self.slots if slot.enabled]


class SlotData:
    """Everything one enemy slot holds, spread over the record: what a slot copy carries."""

    __slots__ = ("enemy_byte", "level", "position", "enabled", "not_targetable", "not_visible",
                 "not_loaded")

    def __init__(self, enemy_byte, level, position, enabled, not_targetable, not_visible, not_loaded):
        self.enemy_byte = enemy_byte
        self.level = level
        self.position = tuple(position)
        self.enabled = enabled
        self.not_targetable = not_targetable
        self.not_visible = not_visible
        self.not_loaded = not_loaded

    def __eq__(self, other):
        return isinstance(other, SlotData) and all(
            getattr(self, name) == getattr(other, name) for name in self.__slots__)


class EncounterRecord:
    """One editable 128-byte scene.out record. Each field reads and writes its own bytes only."""

    def __init__(self, record=bytes(ENCOUNTER_SIZE)):
        if len(record) != ENCOUNTER_SIZE:
            raise ValueError(f"An encounter is {ENCOUNTER_SIZE} bytes, not {len(record)}")
        self.data = bytearray(record)

    def to_bytes(self) -> bytes:
        return bytes(self.data)

    @property
    def stage_id(self):
        return self.data[OFFSET_STAGE]

    @stage_id.setter
    def stage_id(self, value):
        self.data[OFFSET_STAGE] = value

    @property
    def flags(self):
        return self.data[OFFSET_FLAGS]

    @flags.setter
    def flags(self, value):
        self.data[OFFSET_FLAGS] = value

    def flag(self, bit):
        return bool(self.data[OFFSET_FLAGS] & (1 << bit))

    def set_flag(self, bit, value):
        self.data[OFFSET_FLAGS] = _with_bit(self.data[OFFSET_FLAGS], 1 << bit, value)

    # Intro cameras: index 0 = main (0x02), 1 = secondary (0x03)
    def camera_byte(self, index):
        return self.data[OFFSET_CAMERA_MAIN + index]

    def set_camera_byte(self, index, value):
        self.data[OFFSET_CAMERA_MAIN + index] = value

    def camera(self, index):
        """(set, animation) of an intro camera."""
        value = self.camera_byte(index)
        return value >> 4, value & CAMERA_ANIM_MAX

    def set_camera(self, index, camera_set, camera_anim):
        unused_bit = self.camera_byte(index) & 0x08
        self.set_camera_byte(index, (camera_set & 0x0F) << 4 | unused_bit | (camera_anim & CAMERA_ANIM_MAX))

    def slot_flag(self, name, slot_index):
        return bool(self.data[SLOT_FLAG_OFFSETS[name]] & (0x80 >> slot_index))

    def set_slot_flag(self, name, slot_index, value):
        offset = SLOT_FLAG_OFFSETS[name]
        self.data[offset] = _with_bit(self.data[offset], 0x80 >> slot_index, value)

    def position(self, slot_index):
        base = OFFSET_POSITION + slot_index * 6
        return tuple(int.from_bytes(self.data[base + axis * 2:base + axis * 2 + 2], "little", signed=True)
                     for axis in range(3))

    def set_position(self, slot_index, position):
        base = OFFSET_POSITION + slot_index * 6
        for axis, value in enumerate(position):
            self.data[base + axis * 2:base + axis * 2 + 2] = int(value).to_bytes(2, "little", signed=True)

    def enemy_byte(self, slot_index):
        """The raw enemy id byte (c0m file number + 0x10)."""
        return self.data[OFFSET_ENEMY + slot_index]

    def set_enemy_byte(self, slot_index, value):
        self.data[OFFSET_ENEMY + slot_index] = value

    def level(self, slot_index):
        return self.data[OFFSET_LEVEL + slot_index]

    def set_level(self, slot_index, value):
        self.data[OFFSET_LEVEL + slot_index] = value

    @property
    def unknown(self) -> bytes:
        return bytes(self.data[OFFSET_UNKNOWN:OFFSET_UNKNOWN + UNKNOWN_SIZE])

    @unknown.setter
    def unknown(self, value):
        if len(value) != UNKNOWN_SIZE:
            raise ValueError(f"The unknown block is {UNKNOWN_SIZE} bytes, not {len(value)}")
        self.data[OFFSET_UNKNOWN:OFFSET_UNKNOWN + UNKNOWN_SIZE] = value

    def slot(self, slot_index) -> SlotData:
        return SlotData(self.enemy_byte(slot_index), self.level(slot_index), self.position(slot_index),
                        *(self.slot_flag(name, slot_index)
                          for name in ("enabled", "not_targetable", "not_visible", "not_loaded")))

    def set_slot(self, slot_index, slot: SlotData):
        self.set_enemy_byte(slot_index, slot.enemy_byte)
        self.set_level(slot_index, slot.level)
        self.set_position(slot_index, slot.position)
        for name in SLOT_FLAG_OFFSETS:
            self.set_slot_flag(name, slot_index, getattr(slot, name))


def _with_bit(byte, mask, value):
    return byte | mask if value else byte & ~mask & 0xFF


def read_encounters(data) -> list:
    """Every encounter of a scene.out byte string, in file order."""
    nb_encounter = len(data) // ENCOUNTER_SIZE
    return [Encounter(index, data[index * ENCOUNTER_SIZE:(index + 1) * ENCOUNTER_SIZE])
            for index in range(nb_encounter)]


def encounters_with_monster(encounter_list, com_file_id) -> list:
    """[(encounter, slot)] for every ENABLED appearance of c0m file `com_file_id`."""
    enemy_id = com_file_id + ENEMY_ID_BASE
    found = []
    for encounter in encounter_list:
        for slot in encounter.slots:
            if slot.enabled and slot.enemy_id == enemy_id:
                found.append((encounter, slot))
    return found
