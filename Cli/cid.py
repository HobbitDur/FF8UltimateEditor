"""
Cid CLI Tool.

Headless draw-point editing (same data as the Cid GUI). Draw points
1..256 share one EXE byte each (magic id / refill / high-yield, saved as a
.hext patch); world draw points (129..256) additionally have a world-map
position in wmset Section 34 (X, Y, Sub ID, saved back into wmsetxx.obj):
  • export-csv  (FF8 exe + wmset → CSV, same columns as the GUI CSV)
  • import-csv  (CSV → .hext patch and/or new wmsetxx.obj)

The CSV format is identical to the GUI's, so files can be exchanged freely.
"""

import argparse
import pathlib
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Draw ID", "Magic ID", "High Yield", "Refill", "X", "Y", "Sub ID"]

NB_DRAW = 256
WORLD_EXE_START_INDEX = 128
GENERAL_OFFSET = 0x400000


def _new_draw_list(game_data):
    from Cid.draw import Draw
    return [Draw(game_data, id=i + 1, data_hex=bytearray()) for i in range(NB_DRAW)]


def _load_exe(game_data, draw_list, exe_path: str):
    file_data = pathlib.Path(exe_path).read_bytes()
    draw_offset = game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
    for i in range(NB_DRAW):
        draw_list[i].set_exe_byte(file_data[draw_offset + i])


def _load_wmset(draw_list, wmset_path: str):
    from Cid.worlddrawsection import WorldDrawSection
    section = WorldDrawSection()
    section.load(wmset_path)
    nb = min(section.get_nb_record(), NB_DRAW - WORLD_EXE_START_INDEX)
    for i in range(nb):
        x, y, sub_id, _pad = section.records[i]
        draw = draw_list[WORLD_EXE_START_INDEX + i]
        draw.x, draw.y, draw.sub_id = x, y, sub_id
    return section


def _apply_csv(draw_list, csv_path: str):
    for row_index, row in enumerate(read_csv(csv_path)):
        if row_index >= NB_DRAW or not row or not str(row[0]).strip():
            continue
        draw = draw_list[row_index]
        draw.magic_index = int(row[1])
        draw.high_yield = bool(int(row[2]))
        draw.refill = bool(int(row[3]))
        if len(row) >= 7:  # position columns are optional (backward compatible)
            draw.x, draw.y, draw.sub_id = int(row[4]), int(row[5]), int(row[6])


def _write_hext(game_data, draw_list, hext_path: str):
    """Same output as CidWidget._save_hext."""
    draw_offset = game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
    hext_str = "#Offset to dynamic data\n"
    hext_str += "+{:X}\n\n".format(GENERAL_OFFSET)
    hext_str += "#Draw point data: MagicID (0x3F) | Refill (0x40) | HighYield (0x80), one byte per draw ID\n"
    hext_str += "#Start of draw data is at 0x{:X}\n\n".format(draw_offset)
    for draw_index, draw in enumerate(draw_list):
        address = draw_offset + draw_index
        hext_str += f"#Draw ID {draw.get_id()} ({draw.get_magic_name()})\n"
        hext_str += " {:X} = {:02X}\n\n".format(address, draw.get_exe_byte())
    with open(hext_path, "w") as hext_file:
        hext_file.write(hext_str)


def _cmd_export_csv(args) -> int:
    game_data = load_game_data()
    draw_list = _new_draw_list(game_data)
    _load_exe(game_data, draw_list, args.exe)
    _load_wmset(draw_list, args.wmset)
    rows = [[draw.get_id(), draw.magic_index, int(draw.high_yield), int(draw.refill),
             draw.x, draw.y, draw.sub_id] for draw in draw_list]
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} draw points exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    if not args.output_hext and not args.output_wmset:
        print("[error] Nothing to write: give --output-hext and/or --output-wmset", file=sys.stderr)
        return 1
    if args.output_wmset and not args.wmset:
        print("[error] --output-wmset needs --wmset (the base wmsetxx.obj)", file=sys.stderr)
        return 1

    game_data = load_game_data()
    draw_list = _new_draw_list(game_data)
    if args.exe:
        _load_exe(game_data, draw_list, args.exe)
    section = _load_wmset(draw_list, args.wmset) if args.wmset else None
    _apply_csv(draw_list, args.csv)

    if args.output_hext:
        _write_hext(game_data, draw_list, args.output_hext)
        print(f"[ok] EXE draw data written to {args.output_hext}")
    if args.output_wmset:
        nb = min(section.get_nb_record(), NB_DRAW - WORLD_EXE_START_INDEX)
        for i in range(nb):
            draw = draw_list[WORLD_EXE_START_INDEX + i]
            section.set_position(i, draw.x, draw.y, draw.sub_id)
        section.save(args.output_wmset)
        print(f"[ok] World positions written to {args.output_wmset}")
    return 0


class CidCliTool(BaseCliTool):
    """CLI tool for draw points (EXE hext + wmset world positions)."""

    @property
    def name(self) -> str:
        return "cid"

    @property
    def description(self) -> str:
        return "Draw point editor: export/import draw points as CSV, save .hext + wmsetxx.obj"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli cid",
            description="Headless draw-point editor (same data and CSV format as the Cid GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export the 256 draw points to CSV")
        p_export.add_argument("--exe", required=True, help="Path to FF8_EN.exe (magic/refill/high-yield)")
        p_export.add_argument("--wmset", required=True, help="Path to wmsetxx.obj (world positions)")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV and write .hext / wmsetxx.obj")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv (or the GUI)")
        p_import.add_argument("--exe", help="Base FF8 exe (kept values for rows the CSV omits)")
        p_import.add_argument("--wmset", help="Base wmsetxx.obj (required with --output-wmset)")
        p_import.add_argument("--output-hext", help="Write the EXE draw data as this .hext patch")
        p_import.add_argument("--output-wmset", help="Write the world positions as this wmsetxx.obj")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
