"""
CCGroup CLI Tool (NPC card players).

Headless Triple Triad card-player editing in field .jsm scripts (same data as
the CCGroup GUI "NPC card players" tab):
  • list        (print every card player and its 7 params, decoded)
  • export-csv  (folder scan → CSV: one row per card player)
  • import-csv  (apply a CSV back onto the .jsm files, in place)
  • set-param   (edit one param of one player in one .jsm)

Param values are written as a plain integer for a literal push, or "var:N" for
a savemap-variable push (e.g. "var:292" = current region game rules).
"""

import argparse
import pathlib
import sys

from .base import BaseCliTool
from .common import read_csv, write_csv

PARAM_KEYS = ["deck", "game-rules", "trade-rules", "rare-chance", "ai-search", "ai-strategy", "level-mask"]
CSV_HEADER = ["Jsm file", "Map", "Player", "Entity", "Script",
              "Deck ID", "Game rules", "Trade rules", "Rare chance", "AI search", "AI strategy", "Level mask"]


def _format_param(param) -> str:
    return f"var:{param.value}" if param.is_variable() else str(param.value)


def _apply_param(param, text: str):
    text = str(text).strip()
    if text.lower().startswith("var:"):
        param.set_variable(int(text[4:]))
    else:
        param.set_literal(int(text))


def _load_folder(folder: str):
    from CCGroup.jsmcardgame import CardGameFolderManager
    manager = CardGameFolderManager()
    manager.load_folder(folder)
    return manager


def _player_rows(manager, folder: str) -> list:
    rows = []
    for jsm_file in manager.jsm_files:
        rel_path = pathlib.Path(jsm_file.jsm_path).relative_to(folder).as_posix()
        for player_index, player in enumerate(jsm_file.players):
            rows.append([rel_path, jsm_file.map_name, player_index,
                         player.entity_name, player.script_name]
                        + [_format_param(p) for p in player.params])
    return rows


def _cmd_list(args) -> int:
    manager = _load_folder(args.folder)
    rows = _player_rows(manager, args.folder)
    print(f"{len(manager.jsm_files)} .jsm files with card players, {manager.nb_players()} players:")
    for row in rows:
        params = ", ".join(f"{name}={value}" for name, value in zip(PARAM_KEYS, row[5:]))
        print(f"  {row[0]} [{row[2]}] {row[3]}.{row[4]}: {params}")
    return 0


def _cmd_export_csv(args) -> int:
    manager = _load_folder(args.folder)
    rows = _player_rows(manager, args.folder)
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} card players exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_folder(args.folder)
    files_by_rel = {pathlib.Path(f.jsm_path).relative_to(args.folder).as_posix(): f
                    for f in manager.jsm_files}
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        jsm_file = files_by_rel.get(str(row[0]).replace("\\", "/"))
        if jsm_file is None:
            raise ValueError(f"Jsm file '{row[0]}' not found under {args.folder}")
        player = jsm_file.players[int(row[2])]
        for param_index, cell in enumerate(row[5:12]):
            if str(cell).strip():
                _apply_param(player.params[param_index], cell)
        applied += 1
    nb_written = manager.save_all()
    print(f"[ok] {applied} players applied, {nb_written} .jsm file(s) written in place")
    return 0


def _cmd_set_param(args) -> int:
    from CCGroup.jsmcardgame import JsmCardGameFile
    sym_path = args.sym or str(pathlib.Path(args.jsm).with_suffix(".sym"))
    jsm_file = JsmCardGameFile(args.jsm, sym_path)
    if not jsm_file.players:
        print(f"[error] No card players found in {args.jsm}", file=sys.stderr)
        return 1
    player = jsm_file.players[args.player]
    param = player.params[PARAM_KEYS.index(args.param)]
    if args.variable is not None:
        param.set_variable(args.variable)
    else:
        param.set_literal(args.value)
    jsm_file.save(args.output or "")
    print(f"[ok] {player.entity_name}.{player.script_name} {args.param} = {_format_param(param)}, "
          f"written to {args.output or args.jsm}")
    return 0


class CCGroupCliTool(BaseCliTool):
    """CLI tool for NPC card players (CARDGAME calls in field .jsm scripts)."""

    @property
    def name(self) -> str:
        return "ccgroup"

    @property
    def description(self) -> str:
        return "NPC card players: list/export/import the 7 CARDGAME params in field .jsm scripts"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli ccgroup",
            description="Headless NPC card-player editor (same data as the CCGroup GUI). "
                        "Param cells hold an integer (literal) or 'var:N' (savemap variable).",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="List every card player found under a field folder")
        p_list.add_argument("--folder", "-f", required=True, help="Folder scanned recursively for .jsm/.sym")
        p_list.set_defaults(func=_cmd_list)

        p_export = sub.add_parser("export-csv", help="Export every card player to CSV")
        p_export.add_argument("--folder", "-f", required=True, help="Folder scanned recursively for .jsm/.sym")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV back onto the .jsm files (in place)")
        p_import.add_argument("--folder", "-f", required=True, help="Folder scanned recursively for .jsm/.sym")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.set_defaults(func=_cmd_import_csv)

        p_set = sub.add_parser("set-param", help="Set one param of one card player in one .jsm")
        p_set.add_argument("--jsm", required=True, help="Path to the .jsm file")
        p_set.add_argument("--sym", help=".sym path (default: next to the .jsm)")
        p_set.add_argument("--player", type=int, required=True, help="Player index (see 'list')")
        p_set.add_argument("--param", required=True, choices=PARAM_KEYS, help="Which param to set")
        group = p_set.add_mutually_exclusive_group(required=True)
        group.add_argument("--value", type=int, help="Literal value")
        group.add_argument("--variable", type=int, help="Savemap variable number (e.g. 292)")
        p_set.add_argument("--output", "-o", help="Output .jsm (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set_param)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
