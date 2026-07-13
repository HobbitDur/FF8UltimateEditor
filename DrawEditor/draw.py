from FF8GameData.gamedata import GameData


class Draw:

    FIRST_WORLD_ID = 129  # Draw IDs 129..256 are world-map draw points

    def __init__(self, game_data: GameData, id, data_hex: bytearray):

        self.game_data = game_data
        self._id = id
        self.magic_index = 0
        self.high_yield = False
        self.refill = False
        self._location_text = ""
        # World-map position, from wmset Section 34 (only meaningful for world draw points).
        self.x = 0
        self.y = 0
        self.sub_id = 0
        self.pad = 0
        if data_hex:
            self.__analyze_data(data_hex)

    def is_world(self):
        return self._id >= self.FIRST_WORLD_ID

    def set_exe_byte(self, value_int: int):
        self.high_yield = bool(value_int & 0x80)
        self.refill = bool(value_int & 0x40)
        self.magic_index = value_int & 0x3F

    def get_exe_byte(self) -> int:
        value = self.magic_index & 0x3F
        if self.high_yield:
            value |= 0x80
        if self.refill:
            value |= 0x40
        return value

    def get_block_xy(self):
        """World-map block coordinates decoded from the record: (blockX 0..127, blockY 0..95)."""
        return self.x & 0x7F, 2 * self.y + (self.x >> 7)

    def set_block_xy(self, block_x, block_y):
        block_x &= 0x7F
        block_y = max(0, min(95, block_y))
        self.x = block_x | ((block_y & 1) << 7)
        self.y = block_y >> 1

    def __str__(self):
        return f"Draw ID: {self._id} - Magic:{self.get_magic_name()} - HighYield:{self.high_yield} - Refill:{self.refill}"

    def __repr__(self):
        return self.__str__()

    def __analyze_data(self, data_hex: bytearray):
        value_int = data_hex[0]
        self.high_yield = bool(value_int & 0x80)
        self.refill = bool(value_int & 0x40)
        self.magic_index = value_int & 0x3F

    def get_id(self):
        return self._id
    def set_id(self, id):
        self._id = id

    def get_magic_name(self):
        magic_name = [x['name'] for x in self.game_data.magic_data_json["magic"] if x["id"] == self.magic_index]
        if magic_name:
            return magic_name[0]
        else:
            print(f"Magic not found for id: {self.magic_index}")
            return ""

    def get_location(self):
        field_myst_ref = [x['field_myst_ref'] for x in self.game_data.draw_data_json["draw"] if x["id"] == self._id]
        if field_myst_ref:
            field_myst_ref = field_myst_ref[0]
        else:
            print(f"field_myst_ref not found for id: {self._id}")
            return ""
        location = [x['name'] for x in self.game_data.field_data_json["field"] if x["id"] == field_myst_ref]
        if location:
            return location[0]
        else:
            print(f"Location not found for id: {field_myst_ref}")
            return ""
