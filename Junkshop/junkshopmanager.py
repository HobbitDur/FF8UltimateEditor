import json
import os

from FF8GameData.gamedata import GameData


class WeaponUpgrade:
    """One 12-byte entry of the mwepon.bin file, indexed by weapon-upgrade ID.

    Layout (little endian), confirmed against the FF8 executable (sub_4EA890,
    reads ``mweaponbinbuffer + 12 * weapon_id``):
        - offset 0 (uint16): offset of the weapon name inside mwepon.msg
        - offset 2 (byte)  : unused padding (always 0)
        - offset 3 (byte)  : upgrade price divided by 10 (the game multiplies it back by 10)
        - offset 4 (byte)  : item 1 id
        - offset 5 (byte)  : item 1 quantity
        - offset 6 (byte)  : item 2 id
        - offset 7 (byte)  : item 2 quantity
        - offset 8 (byte)  : item 3 id
        - offset 9 (byte)  : item 3 quantity
        - offset 10 (byte) : item 4 id
        - offset 11 (byte) : item 4 quantity

    When the player buys an upgrade the game removes ``quantity`` of each item id
    (ids equal to 0 mean "no item" and are ignored) and charges ``price`` gils.
    The name offset and padding are gameplay-irrelevant for this editor but are
    preserved byte-perfect so the resulting file stays identical everywhere else.
    """

    NB_ITEM = 4
    PRICE_STEP = 10  # The game stores price / 10 and multiplies it back by 10

    def __init__(self, weapon_id, name, name_offset=0, padding=0, price_div10=0, items=None):
        self.weapon_id = weapon_id
        self.name = name
        self.name_offset = name_offset  # Bytes 0-1, offset into mwepon.msg, preserved as-is
        self.padding = padding  # Byte 2, unused by the game, preserved as-is
        self.price_div10 = price_div10
        # items is a list of NB_ITEM [item_id, quantity] pairs
        self.items = items if items is not None else [[0, 0] for _ in range(self.NB_ITEM)]

    @property
    def price(self):
        return self.price_div10 * self.PRICE_STEP

    @price.setter
    def price(self, value):
        self.price_div10 = int(value) // self.PRICE_STEP

    def to_bytes(self):
        data = bytearray(12)
        data[0] = self.name_offset & 0xFF
        data[1] = (self.name_offset >> 8) & 0xFF
        data[2] = self.padding & 0xFF
        data[3] = self.price_div10 & 0xFF
        for i in range(self.NB_ITEM):
            data[4 + i * 2] = self.items[i][0] & 0xFF
            data[5 + i * 2] = self.items[i][1] & 0xFF
        return bytes(data)

    def __str__(self):
        item_str = ", ".join(f"{item_id}x{qty}" for item_id, qty in self.items)
        return f"{self.name} (id {self.weapon_id}): {self.price} G [{item_str}]"


class JunkshopManager:
    """mwepon.bin editor logic, ported from the original JunkShop C# tool (JunkShopWorker.cs)."""

    NB_BYTE_PER_WEAPON = 12

    def __init__(self, game_data: GameData, resource_folder=os.path.join("Junkshop", "Resources")):
        self.game_data = game_data
        self.resource_folder = resource_folder
        self.file_path = ""
        self.weapon_upgrades = []
        self.weapon_name_list = self._load_weapon_names()

    def _load_weapon_names(self):
        file_path = os.path.join(self.resource_folder, "weapon.json")
        with open(file_path, encoding="utf8") as f:
            weapon_data = json.load(f)
        return [weapon["name"] for weapon in weapon_data["weapons"]]

    def get_weapon_name(self, weapon_id):
        if 0 <= weapon_id < len(self.weapon_name_list):
            return self.weapon_name_list[weapon_id]
        return f"Weapon {weapon_id}"

    def get_item_name(self, item_id):
        for item in self.game_data.item_data_json["items"]:
            if item["id"] == item_id:
                return item["name"]
        return f"Item {item_id}"

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        self.weapon_upgrades = []
        nb_weapons = len(file_data) // self.NB_BYTE_PER_WEAPON
        for weapon_id in range(nb_weapons):
            offset = weapon_id * self.NB_BYTE_PER_WEAPON
            name_offset = file_data[offset] | (file_data[offset + 1] << 8)
            padding = file_data[offset + 2]
            price_div10 = file_data[offset + 3]
            items = []
            for i in range(WeaponUpgrade.NB_ITEM):
                item_id = file_data[offset + 4 + i * 2]
                quantity = file_data[offset + 5 + i * 2]
                items.append([item_id, quantity])
            self.weapon_upgrades.append(
                WeaponUpgrade(weapon_id, self.get_weapon_name(weapon_id),
                              name_offset, padding, price_div10, items))

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        file_data = bytearray()
        for weapon_upgrade in self.weapon_upgrades:
            file_data.extend(weapon_upgrade.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)
