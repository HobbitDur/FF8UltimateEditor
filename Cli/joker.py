"""
Joker CLI Tool.

Headless SP2 sprite-table editing (same data as the Joker GUI). An SP2 table maps
sprite ids to lists of textured quads; it exists as standalone .sp2 files (face.sp2,
cardanm.sp2) and as the Pos 4 section of mngrp.bin (magazine/Chocobo World pictures).

Every command takes the source either as --input file.sp2 or as --mngrp mngrp.bin
(mngrphd.bin searched next to it, or given with --mngrphd):
  • list         (print the sprite directory: quads per id, unused ids flagged)
  • export-json  (SP2 table → JSON, one object per sprite id)
  • import-json  (JSON → .sp2 file, or rewritten in place inside mngrp.bin)
  • set-quad     (set one field of one quad)
"""

import argparse
import json
import sys

from .base import BaseCliTool
from .common import load_game_data

QUAD_FIELDS = ["u", "v", "clut", "width", "height", "dx", "dy", "texpage"]


def _load_manager(args):
    from Joker.jokermanager import JokerManager
    manager = JokerManager(load_game_data())
    if getattr(args, "mngrp", None):
        manager.load_mngrp(args.mngrp, getattr(args, "mngrphd", "") or "")
    else:
        manager.load_file(args.input)
    return manager


def _save_manager(manager, args):
    """Write the table back: to --output (or the source .sp2), or in place inside mngrp.bin."""
    if manager.is_mngrp_mode:
        manager.save_mngrp(getattr(args, "output", "") or "",
                           getattr(args, "output_mngrphd", "") or "")
        print(f"[ok] SP2 table written inside {getattr(args, 'output', '') or manager.mngrp_path} "
              f"(Pos 4, mngrphd updated)")
    else:
        manager.save_file(getattr(args, "output", "") or "")
        print(f"[ok] SP2 table written to {getattr(args, 'output', '') or manager.file_path}")


def _add_source_arguments(parser, writable=False):
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", "-i", help="Path to a .sp2 file (face.sp2, cardanm.sp2)")
    source.add_argument("--mngrp", help="Path to mngrp.bin (edits its Pos 4 picture-sprite section)")
    parser.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
    if writable:
        parser.add_argument("--output", "-o",
                            help="Output file (overwrites the source in place if omitted); "
                                 "with --mngrp this is the output mngrp.bin")
        parser.add_argument("--output-mngrphd",
                            help="Output mngrphd.bin (overwrites the loaded one if omitted)")


def _sprite_to_json(sprite):
    return {
        "id": sprite.sprite_id,
        "used": sprite.used,
        "quads": [{field: getattr(quad, field) for field in QUAD_FIELDS} for quad in sprite.quads],
    }


def _cmd_list(args) -> int:
    manager = _load_manager(args)
    sp2 = manager.sp2
    print(f"{len(sp2.sprites)} sprite ids ({len(sp2.unused_ids())} unused)")
    for sprite in sp2.sprites:
        if not sprite.used:
            print(f"  id {sprite.sprite_id:3}: unused")
            continue
        print(f"  id {sprite.sprite_id:3}: {len(sprite.quads)} quad(s)")
        for quad_index, quad in enumerate(sprite.quads):
            print(f"        quad {quad_index}: uv=({quad.u},{quad.v}) clut=0x{quad.clut:04X} "
                  f"size={quad.width}x{quad.height} offset=({quad.dx},{quad.dy}) "
                  f"texpage=0x{quad.texpage:04X}")
    return 0


def _cmd_export_json(args) -> int:
    manager = _load_manager(args)
    data = {"sprite_count": len(manager.sp2.sprites),
            "sprites": [_sprite_to_json(sprite) for sprite in manager.sp2.sprites]}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[ok] {len(manager.sp2.sprites)} sprites exported to {args.output}")
    return 0


def _cmd_import_json(args) -> int:
    from Joker.jokermanager import Sp2File, Sp2Sprite, Sp2Quad
    manager = _load_manager(args)
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    sprites = []
    for sprite_json in data["sprites"]:
        quads = [Sp2Quad(**{field: quad_json[field] for field in QUAD_FIELDS})
                 for quad_json in sprite_json["quads"]]
        sprites.append(Sp2Sprite(sprite_json["id"], quads=quads, used=sprite_json["used"]))
    manager.sp2 = Sp2File(sprites)
    _save_manager(manager, args)
    return 0


def _cmd_set_quad(args) -> int:
    manager = _load_manager(args)
    sprite = manager.sp2.sprites[args.sprite]
    if not sprite.used:
        print(f"[error] sprite id {args.sprite} is unused", file=sys.stderr)
        return 1
    quad = sprite.quads[args.quad]
    setattr(quad, args.field, int(args.value, 0))
    _save_manager(manager, args)
    return 0


class JokerCliTool(BaseCliTool):
    """CLI tool for SP2 sprite tables (face.sp2, cardanm.sp2, mngrp.bin Pos 4)."""

    @property
    def name(self) -> str:
        return "joker"

    @property
    def description(self) -> str:
        return "SP2 sprite-table editor: face.sp2/cardanm.sp2 files and mngrp.bin Pos 4 pictures"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli joker",
            description="Headless SP2 sprite-table editor (same data as the Joker GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="Print the sprite directory (unused ids flagged)")
        _add_source_arguments(p_list)
        p_list.set_defaults(func=_cmd_list)

        p_export = sub.add_parser("export-json", help="Export the SP2 table to JSON")
        _add_source_arguments(p_export)
        p_export.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_export.set_defaults(func=_cmd_export_json)

        p_import = sub.add_parser("import-json", help="Rebuild the SP2 table from a JSON export")
        _add_source_arguments(p_import, writable=True)
        p_import.add_argument("--json", "-j", required=True, help="JSON produced by export-json")
        p_import.set_defaults(func=_cmd_import_json)

        p_set = sub.add_parser("set-quad", help="Set one field of one quad")
        _add_source_arguments(p_set, writable=True)
        p_set.add_argument("--sprite", type=int, required=True, help="Sprite id")
        p_set.add_argument("--quad", type=int, required=True, help="Quad index inside the sprite")
        p_set.add_argument("--field", choices=QUAD_FIELDS, required=True, help="Quad field to set")
        p_set.add_argument("--value", required=True, help="New value (decimal or 0x hexadecimal)")
        p_set.set_defaults(func=_cmd_set_quad)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
