"""
TonberryShop CLI Tool.

Headless shop.bin editing (same data as the TonberryShop GUI):
  • export-csv  (shop.bin → CSV: one row per shop slot, item + rare flag)
  • import-csv  (base shop.bin + CSV → new shop.bin)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import PROJECT_ROOT, parse_bool, read_csv, write_csv

CSV_HEADER = ["Shop ID", "Shop name", "Slot", "Item ID", "Item name", "Rare"]


def _load_manager(shop_bin_path: str):
    from TonberryShop.tonberrymanager import TonberryManager
    manager = TonberryManager(resource_folder=str(PROJECT_ROOT / "TonberryShop" / "Resources"))
    manager.read_shop_file(shop_bin_path)
    manager.analyze_shop_file()
    return manager


def _item_id_from_name(manager, name: str) -> int:
    for item_id, item_name in manager.item_values.items():
        if item_name == name:
            return item_id
    raise ValueError(f"Unknown item name '{name}'")


def _cmd_export_csv(args) -> int:
    from TonberryShop.tonberrymanager import Shop, TonberryManager
    manager = _load_manager(args.input)
    rows = []
    for shop_index, shop in enumerate(manager.shop_info):
        for slot in range(Shop.NB_ITEM_PER_SHOP):
            item_name = shop.item[slot]
            item_id = _item_id_from_name(manager, item_name)
            rows.append([shop_index, TonberryManager.SHOP_NAME_LIST[shop_index], slot,
                         item_id, item_name, int(shop.rare[slot])])
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} shop slots exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        shop_index = int(row[0])
        slot = int(row[2])
        item_id = int(row[3]) if str(row[3]).strip() else _item_id_from_name(manager, row[4])
        if item_id not in manager.item_values:
            raise ValueError(f"Unknown item id {item_id} (shop {shop_index}, slot {slot})")
        shop = manager.shop_info[shop_index]
        shop.item[slot] = manager.item_values[item_id]
        shop.rare[slot] = parse_bool(row[5])
        applied += 1
    manager.write_shop_file(args.output or args.input)
    print(f"[ok] {applied} slots applied, written to {args.output or args.input}")
    return 0


class TonberryShopCliTool(BaseCliTool):
    """CLI tool for shop.bin (shop inventories) editing."""

    @property
    def name(self) -> str:
        return "tonberry-shop"

    @property
    def description(self) -> str:
        return "Shop editor: export/import shop.bin inventories (items + rare flags) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli tonberry-shop",
            description="Headless shop.bin editor (same data as the TonberryShop GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export shop.bin inventories to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to shop.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto a shop.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base shop.bin")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output shop.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
