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
        # Placeholder for dynamic lookups so any combo built from one (before a kernel.bin
        # is loaded) still renders as a combo, not a plain spinbox; set_dynamic() replaces
        # this with real per-file content once available, and the widget refreshes in place.
        self.set_dynamic("slot_set_summary", [{"value": i, "name": f"Set {i}"} for i in range(16)])

    @staticmethod
    def _enum(items, value_key, name_key):
        return {"type": "enum",
                "entries": [{"value": it[value_key], "name": str(it[name_key])} for it in items]}

    def _extend(self, name: str, lookup: dict):
        """Build a lookup declared as ``extends`` another one plus ``overrides``.

        The same kernel byte is edited on several tabs, and a checkbox for a given bit
        must read identically everywhere so the tabs can be compared at a glance. Where
        one tab genuinely differs - today only attack-flags 0x20, which is read for
        battle items and inert everywhere else - the deriving lookup overrides just that
        entry instead of restating the whole list and letting the shared wording drift.
        An override replaces the base entry outright (so it can also drop ``disabled``);
        it must name a mask the base already defines, since a lookup that adds bits isn't
        the same field any more.
        """
        base = self.resolve(lookup["extends"])
        if not base:
            raise KeyError(f"lookup {name!r} extends unknown lookup {lookup['extends']!r}")
        overrides = {o["mask"]: o for o in lookup.get("overrides", [])}
        unknown = overrides.keys() - {e["mask"] for e in base["entries"]}
        if unknown:
            raise KeyError(f"lookup {name!r} overrides mask(s) "
                           f"{[hex(m) for m in sorted(unknown)]} absent from "
                           f"{lookup['extends']!r}")
        return {"type": base["type"],
                "entries": [overrides.get(e["mask"], e) for e in base["entries"]]}

    def resolve(self, name: str):
        if name in self._cache:
            return self._cache[name]
        if name in self._lookups:
            lookup = self._lookups[name]
            if "extends" not in lookup:
                return lookup
            self._cache[name] = self._extend(name, lookup)
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
        elif name == "command_ability_ref":
            # Section 11 (Command ability data in battle) as a picker, plus the 0xFF
            # sentinel meaning "no fixed effect - action chosen at runtime".
            entries = [{"value": it["id"], "name": str(it["Ability"])}
                       for it in gd.gforce_data_json["command_abilities_data"]]
            entries.append({"value": 255, "name": "None (chosen at runtime)"})
            result = {"type": "enum", "entries": entries}
        elif name == "attack_animation":
            result = self._enum(gd.attack_animation_data_json["attack_animation"], "id", "name")
        elif name == "stat":
            result = self._enum(gd.stat_data_json["stat"], "id", "name")
        elif name == "card":
            result = self._enum(gd.card_data_json["card_info"], "id", "name")
        self._cache[name] = result
        return result

    def set_dynamic(self, name: str, entries: list):
        """Inject/replace a lookup computed from the currently-loaded kernel.bin itself
        (as opposed to static kernel_lookups.json data or the reference GameData jsons) -
        e.g. the Slot array's per-set summaries, built from Slot Sets' own loaded content.
        Callers must also refresh any already-built combo widgets using this name."""
        self._cache[name] = {"type": "enum", "entries": entries}
