"""
Alexander CLI Tool.

Headless battle stage (a0stgXXX.x) editing, same operations as the Alexander GUI:
  • export-glb  (a0stgXXX.x → .glb with all 4 groups, group-tagged, sky included)
  • import-glb  (edited .glb + base stage → new a0stgXXX.x; the base stage
                 provides the camera / TIM textures / skeleton template)
  • convert-30fps (the camera of each stage for FFNx True30FPS: keyframe durations
                 x2 (x4 with --fps 60), script waits; FF8GameData/dat/camera30.py)
"""
import os

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


def _cmd_convert_30fps(args) -> int:
    manager = _manager()
    factor = args.fps // 15
    paths = [os.path.abspath(path) for path in args.input]
    manager.open_files(paths)
    failed = 0
    for path, report, message in manager.convert_cameras_to_real30(paths, factor):
        name = os.path.basename(path)
        if report is None:
            print(f"[error] {name}: {message}", file=sys.stderr)
            failed += 1
            continue
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            output = os.path.join(args.output_dir, name)
            note = manager.write_stage_copy(path, output)
        else:
            output = path
            note = manager.save_camera(path)
        print(f"[ok] {name}: {report.summary()} -> {output}" + (f" ({message})" if message else "")
              + note.replace(chr(10), " "))
    return 1 if failed else 0


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

        p_30 = sub.add_parser("convert-30fps",
                              help="Convert the camera of battle stages for FFNx True30FPS (once per stage)")
        p_30.add_argument("--input", "-i", required=True, nargs="+", help="a0stgXXX.x file(s)")
        p_30.add_argument("--output-dir", "-o", help="Write the converted stages there (omitted: in place)")
        p_30.add_argument("--fps", type=int, choices=(30, 60), default=30,
                          help="Target camera rate: 30 (durations x2, default) or 60 (x4)")
        p_30.set_defaults(func=_cmd_convert_30fps)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
