"""
Piet CLI Tool.

Headless mtmag.bin editing (same data as the Piet GUI):
  • show       (print the mmag.bin entry range of each tutorial-menu book)
  • set-range  (change one book's first/last mmag.bin entry)
"""

import argparse
import sys

from .base import BaseCliTool


def _load_manager(mtmag_bin_path: str):
    from Piet.pietmanager import PietManager
    manager = PietManager()
    manager.load_file(mtmag_bin_path)
    return manager


def _cmd_show(args) -> int:
    manager = _load_manager(args.input)
    for book in manager.books:
        print(book)
    return 0


def _cmd_set_range(args) -> int:
    manager = _load_manager(args.input)
    manager.set_range(args.book, args.first, args.last)
    manager.save_file(args.output or args.input)
    print(f"[ok] {manager.books[args.book]}")
    return 0


class PietCliTool(BaseCliTool):
    """CLI tool for mtmag.bin (tutorial-menu book page ranges) editing."""

    @property
    def name(self) -> str:
        return "piet"

    @property
    def description(self) -> str:
        return "Tutorial book editor: show/set the mmag.bin page ranges of mtmag.bin"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli piet",
            description="Headless mtmag.bin editor (same data as the Piet GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_show = sub.add_parser("show", help="Print the page range of each tutorial book")
        p_show.add_argument("--input", "-i", required=True, help="Path to mtmag.bin")
        p_show.set_defaults(func=_cmd_show)

        p_set = sub.add_parser("set-range", help="Set one book's first/last mmag.bin entry")
        p_set.add_argument("--input", "-i", required=True, help="Path to mtmag.bin")
        p_set.add_argument("--book", type=int, required=True,
                           help="Book id (0=battle tutorial, 1=card rules, 2=card icons)")
        p_set.add_argument("--first", type=int, required=True, help="First mmag.bin entry (0-68)")
        p_set.add_argument("--last", type=int, required=True, help="Last mmag.bin entry (0-68)")
        p_set.add_argument("--output", "-o", help="Output mtmag.bin (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set_range)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
