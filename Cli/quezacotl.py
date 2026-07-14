"""
Quezacotl CLI Tool.

Headless init.out editing (same data as the Quezacotl GUI: G-Forces, Characters,
Config, Misc, Items tabs), via a JSON round-trip:
  • export-json  (init.out → JSON with every editable field)
  • import-json  (base init.out + JSON → new init.out; only keys present in the
                  JSON are applied, everything else is preserved byte-perfect)
"""

import argparse
import json
import pathlib
import sys

from .base import BaseCliTool
from .common import load_game_data

NB_GF_ABILITY_BITS = 128
NB_AP_SLOTS = 22
NB_ABILITY_SLOTS = 4
NB_GF_COMPAT = 16
NB_STATUS_BITS = 16
NB_ANGELO_POINTS = 8


def _properties(obj) -> dict:
    """Map property name -> property descriptor for every public property of obj."""
    props = {}
    for klass in reversed(type(obj).__mro__):
        for name, attr in vars(klass).items():
            if isinstance(attr, property) and not name.startswith("_"):
                props[name] = attr
    return props


def _export_properties(obj) -> dict:
    return {name: prop.fget(obj) for name, prop in _properties(obj).items()}


def _import_properties(obj, data: dict):
    props = _properties(obj)
    for name, value in data.items():
        prop = props.get(name)
        if prop is not None and prop.fset is not None:
            prop.fset(obj, value)


def _load_manager(init_out_path: str):
    from Quezacotl.quezacotlmanager import QuezacotlManager
    manager = QuezacotlManager(load_game_data())
    manager.load_file(init_out_path)
    return manager


def _gf_to_dict(gf) -> dict:
    data = _export_properties(gf)
    data["gf_id"] = gf.gf_id
    data["abilities_learned"] = [ability_id for ability_id in range(NB_GF_ABILITY_BITS)
                                 if gf.has_ability(ability_id)]
    data["ap_abilities"] = [gf.get_ap_ability(slot) for slot in range(1, NB_AP_SLOTS + 1)]
    return data


def _gf_from_dict(gf, data: dict):
    _import_properties(gf, data)
    if "abilities_learned" in data:
        learned = set(data["abilities_learned"])
        for ability_id in range(NB_GF_ABILITY_BITS):
            gf.set_ability(ability_id, ability_id in learned)
    for slot_index, ap in enumerate(data.get("ap_abilities", [])):
        gf.set_ap_ability(slot_index + 1, ap)


def _character_to_dict(character) -> dict:
    data = _export_properties(character)
    data["char_id"] = character.char_id
    data["magics"] = [[slot.magic_id, slot.quantity] for slot in character.magics]
    data["active_abilities"] = [character.get_active_ability(s) for s in range(NB_ABILITY_SLOTS)]
    data["passive_abilities"] = [character.get_passive_ability(s) for s in range(NB_ABILITY_SLOTS)]
    data["gf_compatibility"] = [character.get_gf_compatibility(g) for g in range(NB_GF_COMPAT)]
    data["status_bits"] = sum(1 << bit for bit in range(NB_STATUS_BITS) if character.has_status(bit))
    return data


def _character_from_dict(character, data: dict):
    _import_properties(character, data)
    for slot_index, (magic_id, quantity) in enumerate(data.get("magics", [])):
        character.magics[slot_index].magic_id = magic_id
        character.magics[slot_index].quantity = quantity
    for slot_index, value in enumerate(data.get("active_abilities", [])):
        character.set_active_ability(slot_index, value)
    for slot_index, value in enumerate(data.get("passive_abilities", [])):
        character.set_passive_ability(slot_index, value)
    for gf_id, value in enumerate(data.get("gf_compatibility", [])):
        character.set_gf_compatibility(gf_id, value)
    if "status_bits" in data:
        for bit in range(NB_STATUS_BITS):
            character.set_status(bit, bool(data["status_bits"] >> bit & 1))


def _misc_to_dict(misc) -> dict:
    data = _export_properties(misc)
    data["angelo_points"] = [misc.get_angelo_point(i) for i in range(NB_ANGELO_POINTS)]
    return data


def _misc_from_dict(misc, data: dict):
    _import_properties(misc, data)
    for index, value in enumerate(data.get("angelo_points", [])):
        misc.set_angelo_point(index, value)


def _cmd_export_json(args) -> int:
    manager = _load_manager(args.input)
    data = {
        "gfs": [_gf_to_dict(gf) for gf in manager.gf_entries],
        "characters": [_character_to_dict(c) for c in manager.character_entries],
        "config": _export_properties(manager.config),
        "misc": _misc_to_dict(manager.misc),
        "items": [[item.item_id, item.quantity] for item in manager.item_entries],
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] init.out exported to {args.output}")
    return 0


def _cmd_import_json(args) -> int:
    manager = _load_manager(args.input)
    data = json.loads(pathlib.Path(args.json).read_text(encoding="utf-8"))
    for gf, gf_data in zip(manager.gf_entries, data.get("gfs", [])):
        _gf_from_dict(gf, gf_data)
    for character, char_data in zip(manager.character_entries, data.get("characters", [])):
        _character_from_dict(character, char_data)
    if "config" in data:
        _import_properties(manager.config, data["config"])
    if "misc" in data:
        _misc_from_dict(manager.misc, data["misc"])
    for item, (item_id, quantity) in zip(manager.item_entries, data.get("items", [])):
        item.item_id = item_id
        item.quantity = quantity
    manager.save_file(args.output or args.input)
    print(f"[ok] {args.json} applied, written to {args.output or args.input}")
    return 0


class QuezacotlCliTool(BaseCliTool):
    """CLI tool for init.out (new-game initial data) editing."""

    @property
    def name(self) -> str:
        return "quezacotl"

    @property
    def description(self) -> str:
        return "init.out editor: export/import GFs, characters, config, misc and items as JSON"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli quezacotl",
            description="Headless init.out editor (same data as the Quezacotl GUI tabs)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-json", help="Export init.out to JSON")
        p_export.add_argument("--input", "-i", required=True, help="Path to init.out")
        p_export.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_export.set_defaults(func=_cmd_export_json)

        p_import = sub.add_parser("import-json", help="Apply a JSON onto an init.out")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base init.out")
        p_import.add_argument("--json", "-j", required=True, help="JSON produced by export-json")
        p_import.add_argument("--output", "-o", help="Output init.out (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_json)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
