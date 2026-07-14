"""
Kadowaki CLI Tool.

Headless mitem.bin editing (same data as the Kadowaki GUI):
  • export-csv  (mitem.bin → CSV: one row per item, menu type/flags/params)
  • import-csv  (base mitem.bin + CSV → new mitem.bin)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Item ID", "Item name", "Type ID", "Flags", "Param1", "Param2"]


def _load_manager(mitem_bin_path: str):
    from Kadowaki.kadowakimanager import KadowakiManager
    manager = KadowakiManager(load_game_data())
    manager.load_file(mitem_bin_path)
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input)
    rows = [[m.item_id, m.name, m.type_id, m.flags, m.param1, m.param2]
            for m in manager.menu_items]
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} menu items exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        menu_item = manager.menu_items[int(row[0])]
        menu_item.type_id = int(row[2])
        menu_item.flags = int(row[3])
        menu_item.param1 = int(row[4])
        menu_item.param2 = int(row[5])
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} items applied, written to {args.output or args.input}")
    return 0


class KadowakiCliTool(BaseCliTool):
    """CLI tool for mitem.bin (item menu behaviour) editing."""

    @property
    def name(self) -> str:
        return "kadowaki"

    @property
    def description(self) -> str:
        return "Item menu editor: export/import mitem.bin (type, flags, params) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli kadowaki",
            description="Headless mitem.bin editor (same data as the Kadowaki GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export mitem.bin to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to mitem.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto a mitem.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base mitem.bin")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output mitem.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
