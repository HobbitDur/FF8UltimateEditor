"""
Seed CLI Tool.

The Seed GUI is a field model viewer (chara.one / .mch); its only file output
is rebuilding a chara.one after bone edits, which only makes sense interactively.
The CLI therefore exposes the inspection side:
  • list-models  (print the entries of a chara.one container)
"""

import argparse
import sys

from .base import BaseCliTool


def _cmd_list_models(args) -> int:
    import pathlib
    from FF8GameData.mch.mchanalyser import CharaOne
    chara_one = CharaOne(pathlib.Path(args.input).read_bytes())
    for entry in chara_one.entries:
        kind = "main character (.mch)" if entry.is_main else "NPC"
        print(f"{entry.index:3d}: {entry.name} ({kind})")
    print(f"\n{len(chara_one.entries)} models in {args.input}")
    return 0


class SeedCliTool(BaseCliTool):
    """CLI tool for field model containers (chara.one)."""

    @property
    def name(self) -> str:
        return "seed"

    @property
    def description(self) -> str:
        return "Field model viewer: list the models inside a chara.one container"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli seed",
            description="Headless chara.one inspection (the Seed GUI is a 3D viewer)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list-models", help="List the models of a chara.one")
        p_list.add_argument("--input", "-i", required=True, help="Path to a chara.one file")
        p_list.set_defaults(func=_cmd_list_models)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
