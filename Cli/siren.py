"""
Siren CLI Tool.

Headless price.bin editing (same data as the Siren GUI):
  • export-csv  (price.bin → CSV: one row per item, buy price + sell multiplier)
  • import-csv  (base price.bin + CSV → new price.bin)
  • set-price   (edit a single item's buy price / sell multiplier)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Item ID", "Item name", "Buy price", "Sell multiplier", "Sell price (info)"]


def _load_manager(price_bin_path: str):
    from Siren.sirenmanager import SirenManager
    manager = SirenManager(load_game_data())
    manager.load_file(price_bin_path)
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input)
    rows = [[e.item_id, e.name, e.buy_price, e.sell_mult, e.sell_price]
            for e in manager.price_entries]
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} item prices exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        entry = manager.price_entries[int(row[0])]
        entry.buy_price = int(row[2])
        entry.sell_mult = int(row[3])
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} prices applied, written to {args.output or args.input}")
    return 0


def _cmd_set_price(args) -> int:
    if args.buy_price is None and args.sell_mult is None:
        print("[error] Nothing to set: give --buy-price and/or --sell-mult", file=sys.stderr)
        return 1
    manager = _load_manager(args.input)
    entry = manager.price_entries[args.item_id]
    if args.buy_price is not None:
        entry.buy_price = args.buy_price
    if args.sell_mult is not None:
        entry.sell_mult = args.sell_mult
    manager.save_file(args.output or args.input)
    print(f"[ok] {entry}")
    return 0


class SirenCliTool(BaseCliTool):
    """CLI tool for price.bin (item buy/sell prices) editing."""

    @property
    def name(self) -> str:
        return "siren"

    @property
    def description(self) -> str:
        return "Price editor: export/import price.bin (buy prices, sell multipliers) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli siren",
            description="Headless price.bin editor (same data as the Siren GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export price.bin to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to price.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto a price.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base price.bin")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output price.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        p_set = sub.add_parser("set-price", help="Set one item's buy price / sell multiplier")
        p_set.add_argument("--input", "-i", required=True, help="Path to price.bin")
        p_set.add_argument("--item-id", type=int, required=True, help="Item id (row index)")
        p_set.add_argument("--buy-price", type=int, help="New buy price (multiple of 10)")
        p_set.add_argument("--sell-mult", type=int, help="New sell multiplier (0-255)")
        p_set.add_argument("--output", "-o", help="Output price.bin (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set_price)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
