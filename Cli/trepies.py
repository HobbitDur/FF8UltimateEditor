"""
Trepies CLI Tool.

Headless editing of the mngrp.bin tutorial demo data (same data as the Trepies GUI):
  • list           (show the 9 demo scripts and mock save sections)
  • export-script  (one demo script → readable/editable op-list text file)
  • import-script  (op-list text file → demo script raw slot)
  • export-json    (scripts + mock characters + mock GFs → JSON)
  • import-json    (apply a JSON produced by export-json)

mngrphd.bin is looked up next to mngrp.bin unless --header is given. Saving
patches only the edited raw slots: everything else stays byte-exact.
"""

import argparse
import json
import os
import sys

from .base import BaseCliTool
from .common import load_game_data


def _header_path(args) -> str:
    header = getattr(args, "header", None)
    if header:
        return header
    header = os.path.join(os.path.dirname(args.input), "mngrphd.bin")
    if not os.path.exists(header):
        raise FileNotFoundError(f"mngrphd.bin not found next to {args.input}, use --header")
    return header


def _load_manager(args):
    from Trepies.trepiesmanager import TrepiesManager
    manager = TrepiesManager(load_game_data())
    manager.load_file(_header_path(args), args.input)
    return manager


def _save_manager(manager, args):
    output = args.output or args.input
    output_header = getattr(args, "output_header", None)
    if not output_header:
        if args.output:
            output_header = os.path.join(os.path.dirname(output), "mngrphd.bin")
        else:
            output_header = manager.file_mngrphd
    manager.save_file(output, output_header)
    return output, output_header


def _cmd_list(args) -> int:
    manager = _load_manager(args)
    print("Demo scripts:")
    for slot, script in manager.scripts.items():
        print(f"  raw {slot}: {script.name} ({len(script.ops)} ops)")
    for slot, mock_file in manager.mock_char_files.items():
        existing = sum(1 for record in mock_file.records if record.exists)
        print(f"Mock characters raw {slot}: {len(mock_file.records)} records ({existing} exist)")
    for slot, mock_file in manager.mock_gf_files.items():
        existing = sum(1 for record in mock_file.records if record.exists)
        print(f"Mock GFs raw {slot}: {len(mock_file.records)} records ({existing} exist)")
    return 0


def _cmd_export_script(args) -> int:
    manager = _load_manager(args)
    if args.slot not in manager.scripts:
        raise ValueError(f"raw slot {args.slot} is not a demo script (valid: {sorted(manager.scripts)})")
    script = manager.scripts[args.slot]
    with open(args.output, "w", encoding="utf8") as out_file:
        out_file.write(script.to_text(manager.get_captions(args.slot)))
    print(f"[ok] {script.name} ({len(script.ops)} ops) exported to {args.output}")
    return 0


def _cmd_import_script(args) -> int:
    manager = _load_manager(args)
    if args.slot not in manager.scripts:
        raise ValueError(f"raw slot {args.slot} is not a demo script (valid: {sorted(manager.scripts)})")
    with open(args.script, encoding="utf8") as in_file:
        manager.scripts[args.slot].set_ops_from_text(in_file.read())
    output, _ = _save_manager(manager, args)
    print(f"[ok] {len(manager.scripts[args.slot].ops)} ops applied to raw {args.slot}, written to {output}")
    return 0


def _cmd_export_json(args) -> int:
    manager = _load_manager(args)
    with open(args.output, "w", encoding="utf8") as out_file:
        json.dump(manager.to_dict(), out_file, indent=1, ensure_ascii=False)
    print(f"[ok] tutorial demo data exported to {args.output}")
    return 0


def _cmd_import_json(args) -> int:
    manager = _load_manager(args)
    with open(args.json, encoding="utf8") as in_file:
        manager.from_dict(json.load(in_file))
    output, _ = _save_manager(manager, args)
    print(f"[ok] tutorial demo data applied, written to {output}")
    return 0


class TrepiesCliTool(BaseCliTool):
    """CLI tool for the mngrp.bin tutorial demo data (scripts + mock saves)."""

    @property
    def name(self) -> str:
        return "trepies"

    @property
    def description(self) -> str:
        return "Tutorial demo editor: mngrp.bin demo input scripts and mock save data"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli trepies",
            description="Headless mngrp.bin tutorial demo editor (same data as the Trepies GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        def add_common(sub_parser, with_output=True):
            sub_parser.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
            sub_parser.add_argument("--header", help="Path to mngrphd.bin (default: next to mngrp.bin)")
            if with_output:
                sub_parser.add_argument("--output", "-o",
                                        help="Output mngrp.bin (overwrites input if omitted)")
                sub_parser.add_argument("--output-header",
                                        help="Output mngrphd.bin (default: next to the output mngrp.bin)")

        p_list = sub.add_parser("list", help="List the demo scripts and mock save sections")
        add_common(p_list, with_output=False)
        p_list.set_defaults(func=_cmd_list)

        p_export_script = sub.add_parser("export-script", help="Export one demo script as an op-list text file")
        add_common(p_export_script, with_output=False)
        p_export_script.add_argument("--slot", "-s", type=int, required=True,
                                     help="Raw mngrphd slot of the script (168-175 or 205)")
        p_export_script.add_argument("--output", "-o", required=True, help="Output text file")
        p_export_script.set_defaults(func=_cmd_export_script)

        p_import_script = sub.add_parser("import-script", help="Apply an op-list text file onto a demo script")
        add_common(p_import_script)
        p_import_script.add_argument("--slot", "-s", type=int, required=True,
                                     help="Raw mngrphd slot of the script (168-175 or 205)")
        p_import_script.add_argument("--script", "-t", required=True, help="Text file produced by export-script")
        p_import_script.set_defaults(func=_cmd_import_script)

        p_export_json = sub.add_parser("export-json", help="Export scripts + mock save data as JSON")
        add_common(p_export_json, with_output=False)
        p_export_json.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_export_json.set_defaults(func=_cmd_export_json)

        p_import_json = sub.add_parser("import-json", help="Apply a JSON produced by export-json")
        add_common(p_import_json)
        p_import_json.add_argument("--json", "-j", required=True, help="JSON produced by export-json")
        p_import_json.set_defaults(func=_cmd_import_json)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
