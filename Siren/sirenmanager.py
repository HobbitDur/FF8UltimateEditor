from FF8GameData.gamedata import GameData


class PriceEntry:
    """One 4-byte entry of the price.bin file, indexed by item ID.

    Layout (little endian):
        - offset 0 (uint16): buy price divided by 10 (the game multiplies it back by 10)
        - offset 2 (byte)  : sell price multiplier
        - offset 3 (byte)  : unused padding (preserved as-is on save)

    The in-game sell price is round((buy_price / 10 / 2) * sell_mult).
    Item id 0 ("Nothing") is a dummy entry with a price of 0.
    """

    PRICE_STEP = 10  # The game stores buy_price / 10 and multiplies it back by 10

    def __init__(self, item_id, name, price_div10=0, sell_mult=0, padding=0):
        self.item_id = item_id
        self.name = name
        self.price_div10 = price_div10
        self.sell_mult = sell_mult
        self.padding = padding  # Byte 3, unused by the game but kept to stay byte-perfect

    @property
    def buy_price(self):
        return self.price_div10 * self.PRICE_STEP

    @buy_price.setter
    def buy_price(self, value):
        self.price_div10 = int(value) // self.PRICE_STEP

    @property
    def sell_price(self):
        """The price the shop pays back when selling the item (display only)."""
        return round((self.buy_price / self.PRICE_STEP / 2) * self.sell_mult)

    def to_bytes(self):
        return bytes([
            self.price_div10 & 0xFF,
            (self.price_div10 >> 8) & 0xFF,
            self.sell_mult & 0xFF,
            self.padding & 0xFF,
        ])

    def __str__(self):
        return (f"{self.name} (id {self.item_id}): buy {self.buy_price} G, "
                f"sell mult {self.sell_mult}, sell {self.sell_price} G")


class SirenManager:
    """price.bin editor logic, ported from the original Siren C# tool (Worker.cs)."""

    NB_BYTE_PER_ITEM = 4

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.price_entries = []

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        self.price_entries = []
        nb_items = len(file_data) // self.NB_BYTE_PER_ITEM
        for item_id in range(nb_items):
            offset = item_id * self.NB_BYTE_PER_ITEM
            price_div10 = file_data[offset] | (file_data[offset + 1] << 8)
            sell_mult = file_data[offset + 2]
            padding = file_data[offset + 3]
            self.price_entries.append(
                PriceEntry(item_id, self.get_item_name(item_id), price_div10, sell_mult, padding))

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        file_data = bytearray()
        for price_entry in self.price_entries:
            file_data.extend(price_entry.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)

    def get_item_name(self, item_id):
        for item in self.game_data.item_data_json["items"]:
            if item["id"] == item_id:
                return item["name"]
        return f"Item {item_id}"
