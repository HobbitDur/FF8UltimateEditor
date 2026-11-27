import os

from FF8GameData.gamedata import GameData


class WeaponUpgrade:
    """One 12-byte entry of the mwepon.bin file, indexed by weapon-upgrade ID.

    Layout (little endian), confirmed against the FF8 executable (sub_4EA890,
    reads ``mweaponbinbuffer + 12 * weapon_id``):
        - offset 0 (uint16): offset of the upgrade's shop text inside mwepon.msg (FF8GameData.menu.mweponmsg)
        - offset 2 (byte)  : unused padding (always 0) - with Cronos, the high byte of the price
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
    The text offset belongs to mwepon.msg's editor (ShumiTranslator moves it with the texts), so a
    save keeps the one on disk; the padding is preserved byte-perfect.

    Cronos (``cronos`` True): its JunkShopPrice16.hext makes byte 2 the high byte of the price,
    price = 10 * (byte3 + 256 * byte2), up to 655,350 gil instead of 2,550. A vanilla file has 0
    there, so its prices read the same either way.
    """

    NB_ITEM = 4
    PRICE_STEP = 10  # The game stores price / 10 and multiplies it back by 10
    MAX_PRICE = 255 * PRICE_STEP  # vanilla: byte 3 only
    CRONOS_MAX_PRICE = 0xFFFF * PRICE_STEP  # Cronos JunkShopPrice16.hext: bytes 3 (low) and 2 (high)

    def __init__(self, weapon_id, name, name_offset=0, padding=0, price_div10=0, items=None):
        self.weapon_id = weapon_id
        self.name = name
        self.name_offset = name_offset  # Bytes 0-1, offset into mwepon.msg, preserved as-is
        self.padding = padding  # Byte 2, unused by the game, preserved as-is
        self.price_div10 = price_div10
        # items is a list of NB_ITEM [item_id, quantity] pairs
        self.items = items if items is not None else [[0, 0] for _ in range(self.NB_ITEM)]
        self.cronos = False  # True: the price is read and written on 16 bits (see the class doc)

    @property
    def price(self):
        if self.cronos:
            return ((self.padding << 8) | (self.price_div10 & 0xFF)) * self.PRICE_STEP
        return self.price_div10 * self.PRICE_STEP

    @price.setter
    def price(self, value):
        stored = int(value) // self.PRICE_STEP
        if self.cronos:
            stored = max(0, min(stored, 0xFFFF))
            self.price_div10 = stored & 0xFF
            self.padding = stored >> 8
        else:  # byte 2 is left as it is: the vanilla game does not read it
            self.price_div10 = stored

    @property
    def cronos_price(self):
        """The price Cronos charges for this record (bytes 3 and 2), whatever the mode."""
        return ((self.padding << 8) | (self.price_div10 & 0xFF)) * self.PRICE_STEP

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

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.weapon_upgrades = []
        # The weapon names come only from a kernel.bin (set_weapon_names) - none built in.
        self.weapon_name_list = []
        self.cronos = False  # 16-bit prices (Cronos JunkShopPrice16.hext), see WeaponUpgrade

    @property
    def max_price(self):
        return WeaponUpgrade.CRONOS_MAX_PRICE if self.cronos else WeaponUpgrade.MAX_PRICE

    def set_cronos(self, enabled):
        """Read and write the prices on 16 bits (Cronos) or on byte 3 only (vanilla). The bytes
        of the loaded upgrades are not changed, only how their price reads."""
        self.cronos = bool(enabled)
        for weapon_upgrade in self.weapon_upgrades:
            weapon_upgrade.cronos = self.cronos

    def set_weapon_names(self, names):
        """Name the weapons from a kernel.bin (an empty list: none open) - re-labels the loaded
        upgrades too, without touching their data."""
        self.weapon_name_list = list(names)
        for weapon_upgrade in self.weapon_upgrades:
            weapon_upgrade.name = self.get_weapon_name(weapon_upgrade.weapon_id)

    def get_weapon_name(self, weapon_id):
        if 0 <= weapon_id < len(self.weapon_name_list) and self.weapon_name_list[weapon_id]:
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
        self.set_cronos(self.cronos)

    def save_file(self, file_path=""):
        """Write mwepon.bin. Saving over the loaded file keeps the text offsets it holds on disk now:
        ShumiTranslator may have moved them with mwepon.msg's texts since the load."""
        if not file_path:
            file_path = self.file_path
        self._take_text_offsets_from_disk(file_path)
        file_data = bytearray()
        for weapon_upgrade in self.weapon_upgrades:
            file_data.extend(weapon_upgrade.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)

    def _take_text_offsets_from_disk(self, file_path):
        if os.path.normcase(os.path.abspath(file_path)) != os.path.normcase(os.path.abspath(self.file_path)):
            return
        if not os.path.exists(file_path):
            return
        with open(file_path, "rb") as in_file:
            on_disk = in_file.read()
        if len(on_disk) // self.NB_BYTE_PER_WEAPON != len(self.weapon_upgrades):
            return
        for weapon_upgrade in self.weapon_upgrades:
            offset = weapon_upgrade.weapon_id * self.NB_BYTE_PER_WEAPON
            weapon_upgrade.name_offset = on_disk[offset] | (on_disk[offset + 1] << 8)
