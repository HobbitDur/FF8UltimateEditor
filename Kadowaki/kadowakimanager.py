import json
import os

from FF8GameData.gamedata import GameData


class MenuItem:
    """One 4-byte entry of the mitem.bin file, indexed by item ID."""

    def __init__(self, item_id, name, type_id=0, flags=0, param1=0, param2=0):
        self.item_id = item_id
        self.name = name
        self.type_id = type_id
        self.flags = flags
        self.param1 = param1
        self.param2 = param2

    def to_bytes(self):
        return bytes([self.type_id, self.flags, self.param1, self.param2])

    def __str__(self):
        return (f"{self.name} (id {self.item_id}): type {self.type_id}, flags 0x{self.flags:02x}, "
                f"param1 {self.param1}, param2 {self.param2}")


class KadowakiManager:
    NB_BYTE_PER_ITEM = 4

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.menu_items = []
        self._lookup_json_cache = {}

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        self.menu_items = []
        nb_items = len(file_data) // self.NB_BYTE_PER_ITEM
        for item_id in range(nb_items):
            offset = item_id * self.NB_BYTE_PER_ITEM
            self.menu_items.append(MenuItem(item_id, self.get_item_name(item_id), file_data[offset],
                                            file_data[offset + 1], file_data[offset + 2], file_data[offset + 3]))

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        file_data = bytearray()
        for menu_item in self.menu_items:
            file_data.extend(menu_item.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)

    def get_item_name(self, item_id):
        for item in self.game_data.item_data_json["items"]:
            if item["id"] == item_id:
                return item["name"]
        return f"Item {item_id}"

    def get_item_type_info(self, type_id):
        """Return the mitem.json definition of an item type, None if the type is unknown."""
        for item_type in self.game_data.mitem_data_json["item_type"]:
            if item_type["id"] == type_id:
                return item_type
        return None

    def get_param_type_info(self, param_type_name):
        """Return the mitem.json definition of a param type (widget, description, values...)."""
        for param_type in self.game_data.mitem_data_json["param_type"]:
            if param_type["name"] == param_type_name:
                return param_type
        return None

    def get_param_list_values(self, param_type_info):
        """Return the [{id, name}] choices of a "list" param type, resolving the optional source json."""
        list_values = []
        source = param_type_info.get("source")
        if source == "gforce":
            list_values.extend(self.game_data.gforce_data_json["gforce"])
        elif source == "junctionable_ability":  # Shared kernel ability enum (kernel_lookups.json)
            for entry in self._load_lookup_json("kernel_lookups.json")["junctionable_ability"]["entries"]:
                list_values.append({"id": entry["value"], "name": entry["name"]})
        elif source == "quistis_blue_magic":  # Blue Magic limits in kernel order (limit_break.json)
            for entry in self._load_lookup_json("limit_break.json")["quistis_blue_magic"]:
                list_values.append({"id": entry["bit"], "name": entry["name"]})
        list_values.extend(param_type_info.get("values", []))
        list_values.extend(param_type_info.get("extra_values", []))
        return list_values

    def _load_lookup_json(self, json_name):
        """Load (once) a json of the shared FF8GameData resources that has no GameData loader."""
        if json_name not in self._lookup_json_cache:
            file_path = os.path.join(self.game_data.resource_folder_json, json_name)
            with open(file_path, encoding="utf8") as json_file:
                self._lookup_json_cache[json_name] = json.load(json_file)
        return self._lookup_json_cache[json_name]
