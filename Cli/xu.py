"""
Xu CLI Tool.

Headless battle_scan_cameras.bin editing (same data as the Xu GUI):
  • new         (write a file with the vanilla rows)
  • list        (print every row, or only the changed ones)
  • set         (change fields of one row)
  • copy        (copy one row's framing into another)
  • export-csv / import-csv
"""

import argparse
import sys

from .base import BaseCliTool
from .common import write_csv, read_csv

CSV_HEADER = ["row", "label"]


def _manager(path=None, exe=None):
    """The rows of a .bin (path) and/or the vanilla rows of an FF8 exe (exe)."""
    from Xu.xumanager import XuManager
    manager = XuManager()
    if path:
        manager.load_file(path)
    if exe:
        from .common import load_game_data
        game_data = load_game_data()
        if not game_data.exe_data_json:
            game_data.load_exe_data()
        manager.load_exe(exe, game_data.exe_data_json)
    return manager


def _row_arg(args, prefix=""):
    """--row N or --c0m N (the monster's normal-state row)."""
    from Xu.xumanager import ROW_COUNT, row_for_c0m
    row, c0m = getattr(args, prefix + "row"), getattr(args, prefix + "c0m")
    if (row is None) == (c0m is None):
        raise ValueError(f"give exactly one of --{prefix}row / --{prefix}c0m")
    row = row_for_c0m(c0m) if c0m is not None else row
    if not 0 <= row < ROW_COUNT:
        raise ValueError(f"row must be in 0..{ROW_COUNT - 1}")
    return row


def _format(manager, row):
    values = ", ".join(f"{name}={value}" for name, value in zip(_fields(), manager.rows[row].values()))
    return f"{'*' if not manager.is_reference(row) else ' '} {manager.row_label(row)}: {values}"


def _fields():
    from Xu.xumanager import ROW_FIELDS
    return ROW_FIELDS


def _cmd_new(args) -> int:
    _manager(exe=args.exe).save_file(args.output)
    print(f"[ok] vanilla scan camera table written to {args.output}")
    return 0


def _cmd_list(args) -> int:
    from Xu.xumanager import ROW_COUNT
    manager = _manager(args.input, args.exe)
    if args.changed and manager.vanilla is None:
        raise ValueError("--changed compares with the vanilla rows: give the FF8 exe with --exe")
    for row in range(ROW_COUNT):
        if not args.changed or not manager.is_reference(row):
            print(_format(manager, row))
    return 0


def _cmd_set(args) -> int:
    manager = _manager(args.input)
    row = _row_arg(args)
    changes = [(field, getattr(args, field)) for field in _fields() if getattr(args, field) is not None]
    if not changes:
        raise ValueError("nothing to set (give at least one field option)")
    for field, value in changes:
        manager.set_field(row, field, value)
    manager.save_file(args.output or args.input)
    print("[ok]", _format(manager, row))
    return 0


def _cmd_copy(args) -> int:
    manager = _manager(args.input)
    source, target = _row_arg(args, "from_"), _row_arg(args, "to_")
    manager.copy_row(source, target)
    manager.save_file(args.output or args.input)
    print("[ok]", _format(manager, target))
    return 0


def _cmd_export_csv(args) -> int:
    from Xu.xumanager import ROW_COUNT
    manager = _manager(args.input)
    rows = [[row, manager.row_label(row)[5:], *manager.rows[row].values()] for row in range(ROW_COUNT)]
    write_csv(args.output, CSV_HEADER + list(_fields()), rows)
    print(f"[ok] {ROW_COUNT} rows exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _manager(args.input)
    fields = _fields()
    changed = 0
    for line in read_csv(args.csv):
        if not line:
            continue
        row = int(line[0])
        for field, text in zip(fields, line[2:2 + len(fields)]):
            value = int(text, 0)
            if getattr(manager.rows[row], field) != value:
                manager.set_field(row, field, value)
                changed += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {changed} value(s) changed, saved to {args.output or args.input}")
    return 0


def _add_row_selector(parser, prefix="", what="row"):
    dash = prefix.replace("_", "-")
    parser.add_argument(f"--{dash}row", dest=prefix + "row", type=int, help=f"{what.capitalize()} number (0-261)")
    parser.add_argument(f"--{dash}c0m", dest=prefix + "c0m", type=int,
                        help=f"Monster c0m number: its normal {what} (c0m + 16, or c0m + 22 from c0m144)")


class XuCliTool(BaseCliTool):
    """CLI tool for battle_scan_cameras.bin (FFNx direct/exe) editing."""

    @property
    def name(self) -> str:
        return "xu"

    @property
    def description(self) -> str:
        return "Scan camera editor: battle_scan_cameras.bin rows (how the Scan screen frames each monster)"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="ff8-cli xu",
                                         description="Headless battle_scan_cameras.bin editor (same data as the Xu GUI)")
        sub = parser.add_subparsers(dest="command", required=True)

        p_new = sub.add_parser("new", help="Write a battle_scan_cameras.bin with the vanilla rows of an FF8 exe")
        p_new.add_argument("--exe", "-e", required=True, help="FF8 exe (EN, FR, DE, IT or ES) to read the rows from")
        p_new.add_argument("--output", "-o", required=True, help="Output path")
        p_new.set_defaults(func=_cmd_new)

        p_list = sub.add_parser("list", help="Print the rows")
        p_list.add_argument("--input", "-i", required=True, help="Path to battle_scan_cameras.bin")
        p_list.add_argument("--exe", "-e", help="FF8 exe giving the vanilla rows (marks the changed rows with *)")
        p_list.add_argument("--changed", action="store_true", help="Only rows that differ from vanilla (needs --exe)")
        p_list.set_defaults(func=_cmd_list)

        p_set = sub.add_parser("set", help="Change fields of one row")
        p_set.add_argument("--input", "-i", required=True, help="Path to battle_scan_cameras.bin")
        _add_row_selector(p_set)
        for field in _fields():
            p_set.add_argument(f"--{field.replace('_', '-')}", dest=field, type=lambda text: int(text, 0))
        p_set.add_argument("--output", "-o", help="Output path (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set)

        p_copy = sub.add_parser("copy", help="Copy one row's framing into another")
        p_copy.add_argument("--input", "-i", required=True, help="Path to battle_scan_cameras.bin")
        _add_row_selector(p_copy, "from_", "source row")
        _add_row_selector(p_copy, "to_", "target row")
        p_copy.add_argument("--output", "-o", help="Output path (overwrites input if omitted)")
        p_copy.set_defaults(func=_cmd_copy)

        p_export = sub.add_parser("export-csv", help="Export every row to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to battle_scan_cameras.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV made by export-csv")
        p_import.add_argument("--input", "-i", required=True, help="Path to battle_scan_cameras.bin")
        p_import.add_argument("--csv", "-c", required=True, help="CSV path")
        p_import.add_argument("--output", "-o", help="Output path (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)
        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
