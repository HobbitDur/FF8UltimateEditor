"""
Junkshop CLI Tool.

Headless mwepon.bin editing (same data as the Junkshop GUI):
  • export-csv  (mwepon.bin → CSV: one row per weapon upgrade, price + 4 recipe slots)
  • import-csv  (base mwepon.bin + CSV → new mwepon.bin)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Weapon ID", "Weapon name", "Price",
              "Item1 ID", "Item1 name", "Qty1",
              "Item2 ID", "Item2 name", "Qty2",
              "Item3 ID", "Item3 name", "Qty3",
              "Item4 ID", "Item4 name", "Qty4"]


def _load_manager(mwepon_bin_path: str):
    from Junkshop.junkshopmanager import JunkshopManager
    manager = JunkshopManager(load_game_data())
    manager.load_file(mwepon_bin_path)
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input)
    rows = []
    for upgrade in manager.weapon_upgrades:
        row = [upgrade.weapon_id, upgrade.name, upgrade.price]
        for item_id, quantity in upgrade.items:
            row.extend([item_id, manager.get_item_name(item_id), quantity])
        rows.append(row)
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} weapon upgrades exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    from Junkshop.junkshopmanager import WeaponUpgrade
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        upgrade = manager.weapon_upgrades[int(row[0])]
        upgrade.price = int(row[2])
        for i in range(WeaponUpgrade.NB_ITEM):
            upgrade.items[i][0] = int(row[3 + i * 3])
            upgrade.items[i][1] = int(row[5 + i * 3])
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} upgrades applied, written to {args.output or args.input}")
    return 0


class JunkshopCliTool(BaseCliTool):
    """CLI tool for mwepon.bin (weapon upgrade recipes) editing."""

    @property
    def name(self) -> str:
        return "junkshop"

    @property
    def description(self) -> str:
        return "Weapon upgrade editor: export/import mwepon.bin (prices, recipes) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli junkshop",
            description="Headless mwepon.bin editor (same data as the Junkshop GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export mwepon.bin to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to mwepon.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto a mwepon.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base mwepon.bin")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output mwepon.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
