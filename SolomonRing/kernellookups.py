import json
import os


class LookupRegistry:
    """Resolves a named option list to a uniform ``{type, entries}`` structure.

    ``type`` is ``"enum"`` (entries have ``value``) or ``"flags"`` (entries have
    ``mask``). Small enums / bitfields live in ``kernel_lookups.json``; large
    reference lists (spells, items, GFs, abilities...) are pulled live from the
    already-loaded ``GameData`` json so they stay in sync with the rest of the app.
    """

    def __init__(self, game_data, game_data_folder="FF8GameData"):
        self.game_data = game_data
        path = os.path.join(game_data_folder, "Resources", "json", "kernel_lookups.json")
        with open(path, encoding="utf-8") as f:
            self._lookups = json.load(f)
        self._cache = {}

    @staticmethod
    def _enum(items, value_key, name_key):
        return {"type": "enum",
                "entries": [{"value": it[value_key], "name": str(it[name_key])} for it in items]}

    def resolve(self, name: str):
        if name in self._lookups:
            return self._lookups[name]
        if name in self._cache:
            return self._cache[name]
        gd = self.game_data
        result = None
        if name == "magic":
            result = self._enum(gd.magic_data_json["magic"], "id", "name")
        elif name == "item":
            result = self._enum(gd.item_data_json["items"], "id", "name")
        elif name == "gforce":
            result = self._enum(gd.gforce_data_json["gforce"], "id", "name")
        elif name == "battle_command":
            result = self._enum(gd.gforce_data_json["battle_command"], "id", "Ability")
        elif name == "command_ability_data":
            result = self._enum(gd.gforce_data_json["command_abilities_data"], "id", "Ability")
        elif name == "special_action":
            result = self._enum(gd.special_action_data_json["special_action"], "id", "name")
        elif name == "stat":
            result = self._enum(gd.stat_data_json["stat"], "id", "name")
        self._cache[name] = result
        return result
