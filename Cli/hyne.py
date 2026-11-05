"""
Hyne CLI Tool.

Headless .ff8 Steam save-file editing (same data as the Hyne GUI: G-Forces, Characters,
Config, Misc, Items, Triple Triad and the other savemap tabs — the savemap's game-state block is byte-identical in layout to
init.out, so this reuses Quezacotl's JSON shape), via a JSON round-trip:
  • export-json  (.ff8 -> JSON with every editable field)
  • import-json  (base .ff8 + JSON -> new .ff8; only keys present in the JSON are applied,
                  everything else — including the header and unparsed savemap regions — is
                  preserved byte-perfect. A .bak backup of the input is written before save
                  unless --no-backup is passed.)
"""

import argparse
import json
import pathlib
import sys

from CCGroup.cardlocation import NB_CARDS, RARE_CARD_FIRST_ID

from .base import BaseCliTool
from .common import load_game_data
from .quezacotl import (
    _export_properties, _import_properties,
    _gf_to_dict, _gf_from_dict,
    _character_to_dict, _character_from_dict,
    _misc_to_dict, _misc_from_dict,
)


# Rules of the 8 regions, trade rules, last rules and regions, then the Queen and BGU values
TT_EXPORTED_VARS = [*range(272, 292), *range(295, 301), 478]


def _load_manager(ff8_path: str):
    from Hyne.hynemanager import HyneManager
    manager = HyneManager(load_game_data())
    manager.load_file(ff8_path)
    return manager


def _triple_triad_to_dict(tt) -> dict:
    return {
        "common_cards": [[tt.is_obtained(card), tt.copies(card)] for card in range(RARE_CARD_FIRST_ID)],
        "rare_cards": [[tt.is_obtained(card), tt.location(card)] for card in range(RARE_CARD_FIRST_ID, NB_CARDS)],
        "collection_complete": tt.collection_complete,
        "wins": tt.wins,
        "losses": tt.losses,
        "draws": tt.draws,
        "seed": tt.seed,
        "cc_quest": tt.cc_quest,
        "vars": {str(number): tt.var(number) for number in TT_EXPORTED_VARS},
    }


def _triple_triad_from_dict(tt, data: dict) -> None:
    for card, (obtained, copies) in enumerate(data.get("common_cards", [])):
        tt.set_obtained(card, obtained)
        tt.set_copies(card, copies)
    for card, (obtained, location) in enumerate(data.get("rare_cards", []), start=RARE_CARD_FIRST_ID):
        tt.set_obtained(card, obtained)
        tt.set_location(card, location)
    for key in ("collection_complete", "wins", "losses", "draws", "seed", "cc_quest"):
        if key in data:
            setattr(tt, key, data[key])
    for number, value in data.get("vars", {}).items():
        tt.set_var(int(number), value)


def _cmd_export_json(args) -> int:
    manager = _load_manager(args.input)
    data = {
        "gfs": [_gf_to_dict(gf) for gf in manager.gf_entries],
        "characters": [_character_to_dict(c) for c in manager.character_entries],
        "config": _export_properties(manager.config),
        "misc": _misc_to_dict(manager.misc),
        "items": [[item.item_id, item.quantity] for item in manager.item_entries],
        "triple_triad": _triple_triad_to_dict(manager.triple_triad),
        "gf_forgotten": [[slot for slot in range(1, 22) if gf.is_forgotten(slot)] for gf in manager.gf_entries],
        "character_exist_flags": [character.exist_flags for character in manager.character_entries],
        "savemap": {name: getattr(manager, name).to_dict() for name in manager.SAVE_SECTIONS},
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {args.input} exported to {args.output}")
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
    if "triple_triad" in data:
        _triple_triad_from_dict(manager.triple_triad, data["triple_triad"])
    for gf, forgotten in zip(manager.gf_entries, data.get("gf_forgotten", [])):
        for slot in range(1, 22):
            gf.set_forgotten(slot, slot in forgotten)
    for character, flags in zip(manager.character_entries, data.get("character_exist_flags", [])):
        character._set_byte(148, flags)
    for name, values in data.get("savemap", {}).items():
        getattr(manager, name).from_dict(values)
    manager.save_file(args.output or args.input, backup=not args.no_backup)
    print(f"[ok] {args.json} applied, written to {args.output or args.input}")
    return 0


class HyneCliTool(BaseCliTool):
    """CLI tool for .ff8 Steam save-file editing."""

    @property
    def name(self) -> str:
        return "hyne"

    @property
    def description(self) -> str:
        return ".ff8 save-file editor: export/import every tab (GFs, characters, config, misc, items, Triple Triad, savemap) as JSON"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli hyne",
            description="Headless .ff8 save-file editor (same data as the Hyne GUI tabs)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-json", help="Export a .ff8 save to JSON")
        p_export.add_argument("--input", "-i", required=True, help="Path to the .ff8 save file")
        p_export.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_export.set_defaults(func=_cmd_export_json)

        p_import = sub.add_parser("import-json", help="Apply a JSON onto a .ff8 save")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base .ff8 save file")
        p_import.add_argument("--json", "-j", required=True, help="JSON produced by export-json")
        p_import.add_argument("--output", "-o", help="Output .ff8 file (overwrites input if omitted)")
        p_import.add_argument("--no-backup", action="store_true",
                              help="Skip writing a .bak backup of the file being overwritten")
        p_import.set_defaults(func=_cmd_import_json)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
