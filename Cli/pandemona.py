"""
Pandemona CLI Tool.

Headless refine-formula editing (same data as the Pandemona GUI). The refine
data lives in the m000-m004 sub-files inside mngrp.bin (mngrphd.bin holds the
section table and is rewritten together with it):
  • export-csv  (mngrp.bin → CSV: one row per refine formula entry)
  • import-csv  (base mngrp.bin + CSV → new mngrp.bin + mngrphd.bin)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Bin", "Section", "Entry", "Text",
              "Input ID", "Amount required", "Output ID", "Amount received", "Unknown"]


def _load_manager(mngrp_path: str, mngrphd_path: str = ""):
    from Pandemona.pandemonamanager import PandemonaManager
    manager = PandemonaManager(load_game_data())
    manager.load_file(mngrp_path, mngrphd_path or "")
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    rows = []
    for section in manager.refine_sections:
        for entry_index, entry in enumerate(section.entries):
            rows.append([section.bin_name, section.name, entry_index, entry.text,
                         entry.element_in_id, entry.amount_required,
                         entry.element_out_id, entry.amount_received, entry.unk])
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} refine entries exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    sections = {(s.bin_name, s.name): s for s in manager.refine_sections}
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        key = (row[0], row[1])
        if key not in sections:
            raise ValueError(f"Unknown refine section {key[0]}/{key[1]}")
        entry = sections[key].entries[int(row[2])]
        entry.text = row[3]
        entry.element_in_id = int(row[4])
        entry.amount_required = int(row[5])
        entry.element_out_id = int(row[6])
        entry.amount_received = int(row[7])
        entry.unk = int(row[8])
        applied += 1
    manager.save_file(args.output or "", args.output_mngrphd or "")
    out_name = args.output or args.input
    print(f"[ok] {applied} refine entries applied, written to {out_name} (+ mngrphd)")
    return 0


class PandemonaCliTool(BaseCliTool):
    """CLI tool for refine formulas (m00x inside mngrp.bin) editing."""

    @property
    def name(self) -> str:
        return "pandemona"

    @property
    def description(self) -> str:
        return "Refine editor: export/import refine formulas (mngrp.bin m000-m004) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli pandemona",
            description="Headless refine-formula editor (same data as the Pandemona GUI). "
                        "mngrphd.bin is auto-detected next to mngrp.bin when not given.",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export the refine formulas to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_export.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto mngrp.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_import.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
        p_import.add_argument("--output-mngrphd", help="Output mngrphd.bin (overwrites the loaded one if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
