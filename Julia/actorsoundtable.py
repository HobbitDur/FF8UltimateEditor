"""FFNx's fixed-size battle_actor_sounds.bin table of world sound IDs."""
import json
import struct
from pathlib import Path


WORLD_SOUND_BASES = {1: 2150, 21: 150, 22: 180, 24: 370, 30: 710, 35: 980,
                     40: 1230, 41: 1510, 42: 1920, 50: 2784}


def world_sound_to_archive_id(world_id):
    """FF8 GetSoundID_ForWorld, including its category-69 exception."""
    if not 0 <= world_id <= 0xFFFFFFFF:
        raise ValueError("A sound ID must be between 0 and 4294967295.")
    category, offset = divmod(world_id, 10000)
    if category == 69:
        return 2060 if world_id == 690000 else world_id - 688040
    return WORLD_SOUND_BASES.get(category, 0) + offset


class ActorSoundTable:
    ROWS = 216
    SLOTS = 7
    FORMAT = struct.Struct("<1512I")

    def __init__(self, resource_folder):
        self.resource_folder = Path(resource_folder)
        with (self.resource_folder / "battle_actor_sound.json").open(encoding="utf-8") as file:
            defaults = json.load(file)["actor_world_sound_slots"]
        self._defaults = [tuple(defaults[str(row)]) if row < 160 else (0,) * self.SLOTS
                          for row in range(self.ROWS)]
        self.reset()

    def reset(self):
        self.rows = [list(row) for row in self._defaults]

    def load(self, path):
        data = Path(path).read_bytes()
        if len(data) != self.FORMAT.size:
            raise ValueError(f"Expected {self.FORMAT.size:,} bytes; found {len(data):,}.")
        values = self.FORMAT.unpack(data)
        self.rows = [list(values[row * self.SLOTS:(row + 1) * self.SLOTS])
                     for row in range(self.ROWS)]

    def save(self, path):
        Path(path).write_bytes(self.FORMAT.pack(*(value for row in self.rows for value in row)))

    def set_slot(self, row, slot, value):
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("A sound ID must be between 0 and 4294967295.")
        self.rows[row][slot] = value

    def copy_actor(self, source, destination):
        self.rows[destination] = self.rows[source].copy()
