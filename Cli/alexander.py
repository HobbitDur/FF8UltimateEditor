"""
Alexander CLI Tool.

Headless battle stage (a0stgXXX.x) editing, same operations as the Alexander GUI:
  • export-glb  (a0stgXXX.x → .glb with all 4 groups, group-tagged, sky included)
  • import-glb  (edited .glb + base stage → new a0stgXXX.x; the base stage
                 provides the camera / TIM textures / skeleton template)
"""

import argparse
import sys

from .base import BaseCliTool


def _manager():
    from Alexander.alexandermanager import AlexanderManager
    return AlexanderManager()


def _cmd_export_glb(args) -> int:
    manager = _manager()
    manager.load_stage_file(args.input)
    manager.export_glb(args.output)
    print(f"[ok] {args.input} exported to {args.output}")
    return 0


def _cmd_import_glb(args) -> int:
    manager = _manager()
    manager.load_stage_file(args.input)  # snapshots the write-back template
    manager.load_glb(args.glb)
    note = manager.save(args.output)
    print(f"[ok] Stage written to {args.output}" + (f" ({note})" if note else ""))
    return 0


class AlexanderCliTool(BaseCliTool):
    """CLI tool for battle stages (a0stgXXX.x ↔ glb)."""

    @property
    def name(self) -> str:
        return "alexander"

    @property
    def description(self) -> str:
        return "Battle stage editor: export a0stgXXX.x to .glb and rebuild a stage from an edited .glb"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli alexander",
            description="Headless battle stage editor (same operations as the Alexander GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-glb", help="Export a battle stage to .glb")
        p_export.add_argument("--input", "-i", required=True, help="Path to the a0stgXXX.x file")
        p_export.add_argument("--output", "-o", required=True, help="Output .glb path")
        p_export.set_defaults(func=_cmd_export_glb)

        p_import = sub.add_parser("import-glb", help="Rebuild a stage .x from an edited .glb")
        p_import.add_argument("--input", "-i", required=True,
                              help="Base a0stgXXX.x (provides camera/textures/skeleton)")
        p_import.add_argument("--glb", "-g", required=True, help="Edited .glb (from export-glb)")
        p_import.add_argument("--output", "-o", required=True, help="Path of the .x to write")
        p_import.set_defaults(func=_cmd_import_glb)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
