"""
Odine CLI Tool.

Named after Dr. Odine, inventor of para-magic and the junction system.
Headless magsort.bin editing (same data as the Odine GUI):
  • export-csv  (magsort.bin → CSV: one row per spell, category + order)
  • import-csv  (CSV → new magsort.bin)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Category", "Order", "Magic ID", "Magic name"]
CATEGORIES = ["offensive", "supportive", "disruptive"]


def _load_manager(magsort_bin_path: str):
    from Odine.odinemanager import OdineManager
    manager = OdineManager(load_game_data())
    manager.load_file(magsort_bin_path)
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input)
    rows = []
    for category in CATEGORIES:
        for order, magic_id in enumerate(getattr(manager, category)):
            rows.append([category, order, magic_id, manager.get_magic_name(magic_id)])
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} spell assignments exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    from Odine.odinemanager import OdineManager
    manager = OdineManager(load_game_data())
    manager.file_path = args.input

    entries = {category: [] for category in CATEGORIES}
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        category = row[0].strip().lower()
        if category not in entries:
            raise ValueError(f"Unknown category: {category}")
        entries[category].append((int(row[1]), int(row[2])))

    for category in CATEGORIES:
        ordered = [magic_id for _, magic_id in sorted(entries[category])]
        setattr(manager, category, ordered)

    manager.save_file(args.output or args.input)
    print(f"[ok] {sum(len(v) for v in entries.values())} spells applied, written to {args.output or args.input}")
    return 0


class OdineCliTool(BaseCliTool):
    """CLI tool for magsort.bin (Magic menu Offensive/Supportive/Disruptive sort) editing."""

    @property
    def name(self) -> str:
        return "odine"

    @property
    def description(self) -> str:
        return "Magic menu sort editor: export/import magsort.bin (spell categories/order) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli odine",
            description="Headless magsort.bin editor (same data as the Odine GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export magsort.bin to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to magsort.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Build a magsort.bin from a CSV")
        p_import.add_argument("--input", "-i", required=True,
                               help="Path to a magsort.bin (only used as the default output path)")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output magsort.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
