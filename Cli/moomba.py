"""
Moomba CLI Tool.

Headless mmag2.bin editing (same data as the Moomba GUI): the 12 pages of the
save-point Chocobo World screen (Mog story slides + Solo RPG manual), sharing the
68-byte entry format of mmag.bin (the MagPageEntry classes Zone also uses).
  • list         (print the entries, with the text overlay strings when mngrp.bin is given)
  • export-json  (mmag2.bin → JSON: every field of every entry)
  • import-json  (base mmag2.bin + JSON → new mmag2.bin)
"""

import argparse
import json
import pathlib
import sys

from .base import BaseCliTool
from .common import load_game_data


def _load_manager(mmag2_bin_path: str, mngrp_path: str = ""):
    from Moomba.moombamanager import MoombaManager
    manager = MoombaManager(load_game_data())
    manager.load_file(mmag2_bin_path)
    if mngrp_path:
        manager.load_mngrp(mngrp_path)
    return manager


def _entry_to_dict(index, entry) -> dict:
    return {
        "id": index,
        "window": {"x": entry.window_x, "y": entry.window_y,
                   "width": entry.window_width, "height": entry.window_height},
        "picture": {"x": entry.picture_x, "y": entry.picture_y,
                    "width": entry.picture_width, "height": entry.picture_height,
                    "scale_x": entry.picture_scale_x, "scale_y": entry.picture_scale_y,
                    "scale_z": entry.picture_scale_z},
        "paper_param_a": entry.paper_param_a,
        "paper_param_b": entry.paper_param_b,
        "text_file_index": entry.text_file_index,
        "texture": {"category": entry.texture_category, "page": entry.texture_page},
        "unlock": {"weapon_index": entry.weapon_index,
                   "weapon_line_spacing": entry.weapon_line_spacing,
                   "duel_move_id": entry.duel_move_id,
                   "angelo_move_id": entry.angelo_move_id,
                   "weapon_list_x": entry.weapon_list_x,
                   "weapon_list_y": entry.weapon_list_y,
                   "weapon_quantity_column_x": entry.weapon_quantity_column_x,
                   "duel_combo_x": entry.duel_combo_x,
                   "duel_combo_y": entry.duel_combo_y},
        "footer_flag": entry.footer_flag,
        "picture_overlays": [{"x": slot.x, "y": slot.y, "id": slot.id}
                             for slot in entry.picture_overlays],
        "text_overlays": [{"x": slot.x, "y": slot.y, "id": slot.id}
                          for slot in entry.text_overlays],
    }


def _dict_to_entry(entry, data: dict):
    entry.window_x = data["window"]["x"]
    entry.window_y = data["window"]["y"]
    entry.window_width = data["window"]["width"]
    entry.window_height = data["window"]["height"]
    entry.picture_x = data["picture"]["x"]
    entry.picture_y = data["picture"]["y"]
    entry.picture_width = data["picture"]["width"]
    entry.picture_height = data["picture"]["height"]
    entry.picture_scale_x = data["picture"]["scale_x"]
    entry.picture_scale_y = data["picture"]["scale_y"]
    entry.picture_scale_z = data["picture"]["scale_z"]
    entry.paper_param_a = data["paper_param_a"]
    entry.paper_param_b = data["paper_param_b"]
    entry.text_file_index = data["text_file_index"]
    entry.texture_category = data["texture"]["category"]
    entry.texture_page = data["texture"]["page"]
    entry.weapon_index = data["unlock"]["weapon_index"]
    entry.weapon_line_spacing = data["unlock"]["weapon_line_spacing"]
    entry.duel_move_id = data["unlock"]["duel_move_id"]
    entry.angelo_move_id = data["unlock"]["angelo_move_id"]
    entry.weapon_list_x = data["unlock"]["weapon_list_x"]
    entry.weapon_list_y = data["unlock"]["weapon_list_y"]
    entry.weapon_quantity_column_x = data["unlock"]["weapon_quantity_column_x"]
    entry.duel_combo_x = data["unlock"]["duel_combo_x"]
    entry.duel_combo_y = data["unlock"]["duel_combo_y"]
    entry.footer_flag = data["footer_flag"]
    for i, slot_data in enumerate(data["picture_overlays"]):
        entry.picture_overlays[i].x = slot_data["x"]
        entry.picture_overlays[i].y = slot_data["y"]
        entry.picture_overlays[i].id = slot_data["id"]
    for i, slot_data in enumerate(data["text_overlays"]):
        entry.text_overlays[i].x = slot_data["x"]
        entry.text_overlays[i].y = slot_data["y"]
        entry.text_overlays[i].id = slot_data["id"]


def _cmd_list(args) -> int:
    manager = _load_manager(args.input, args.mngrp or "")
    for index, entry in enumerate(manager.entries):
        print(f"[{index:2}] {manager.get_entry_name(index)}")
        print(f"     texture: category {entry.texture_category} page {entry.texture_page}, "
              f"window {entry.window_width}x{entry.window_height} at ({entry.window_x},{entry.window_y})")
        for slot in entry.picture_overlays:
            if not slot.unused:
                print(f"     picture overlay: sprite {slot.id} at ({slot.x},{slot.y})")
        for slot in entry.text_overlays:
            if not slot.unused:
                preview = manager.get_overlay_text(slot.id)
                preview = " — " + preview.split("\n")[0][:60] if preview else ""
                print(f"     text overlay: string {slot.id} at ({slot.x},{slot.y}){preview}")
    return 0


def _cmd_export_json(args) -> int:
    manager = _load_manager(args.input)
    data = {"entries": [_entry_to_dict(index, entry) for index, entry in enumerate(manager.entries)]}
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[ok] {len(manager.entries)} entries exported to {args.output}")
    return 0


def _cmd_import_json(args) -> int:
    manager = _load_manager(args.input)
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    applied = 0
    for entry_data in data["entries"]:
        _dict_to_entry(manager.entries[int(entry_data["id"])], entry_data)
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} entries applied, written to {args.output or args.input}")
    return 0


class MoombaCliTool(BaseCliTool):
    """CLI tool for mmag2.bin (Chocobo World screen pages) editing."""

    @property
    def name(self) -> str:
        return "moomba"

    @property
    def description(self) -> str:
        return "Chocobo World screen editor: export/import mmag2.bin (story slides, Solo RPG manual) as JSON"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli moomba",
            description="Headless mmag2.bin editor (same data as the Moomba GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="Print the mmag2.bin entries")
        p_list.add_argument("--input", "-i", required=True, help="Path to mmag2.bin")
        p_list.add_argument("--mngrp", "-m", help="Path to mngrp.bin (mngrphd.bin next to it) "
                                                  "to preview the text overlay strings")
        p_list.set_defaults(func=_cmd_list)

        p_export = sub.add_parser("export-json", help="Export mmag2.bin to JSON")
        p_export.add_argument("--input", "-i", required=True, help="Path to mmag2.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_export.set_defaults(func=_cmd_export_json)

        p_import = sub.add_parser("import-json", help="Apply a JSON onto a mmag2.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base mmag2.bin")
        p_import.add_argument("--json", "-j", required=True, help="JSON produced by export-json")
        p_import.add_argument("--output", "-o", help="Output mmag2.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_json)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
