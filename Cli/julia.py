"""
Julia CLI Tool.

Headless battle sound editing (same operations as the Julia GUI, minus playback):
  • list        (print every sound entry: format, channels, rate, length, users)
  • export-wav  (one sound → standalone .wav)
  • export-all  (every sound → sound_NNNN.wav files in a folder)
  • replace     (swap one sound with a .wav, rebuild audio.fmt + audio.dat)

audio.dat is auto-detected next to audio.fmt when not given.
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data


def _load_manager(fmt_path: str, dat_path: str = "", with_names: bool = False):
    from Julia.juliamanager import JuliaManager
    manager = JuliaManager(load_game_data() if with_names else None)
    manager.load(fmt_path, dat_path or None)
    return manager


def _cmd_list(args) -> int:
    manager = _load_manager(args.fmt, args.dat, with_names=True)
    for index, sound in enumerate(manager.sounds):
        if not sound.is_valid:
            print(f"{index:4d}: (empty)")
            continue
        users = ", ".join(manager.actor_names_for(index))
        loop = " loop" if sound.is_looping else ""
        print(f"{index:4d}: {sound.format_label()} {sound.channels}ch {sound.sample_rate}Hz "
              f"{sound.data_length}B{loop}" + (f"  [{users}]" if users else ""))
    print(f"\n{len(manager.sounds)} sound entries")
    return 0


def _cmd_export_wav(args) -> int:
    manager = _load_manager(args.fmt, args.dat)
    manager.export_wav(args.index, args.output)
    print(f"[ok] Sound {args.index} exported to {args.output}")
    return 0


def _cmd_export_all(args) -> int:
    import pathlib
    pathlib.Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    manager = _load_manager(args.fmt, args.dat)
    count = manager.export_all(args.output_dir)
    print(f"[ok] {count} sounds exported to {args.output_dir}")
    return 0


def _cmd_replace(args) -> int:
    manager = _load_manager(args.fmt, args.dat)
    manager.replace_from_wav(args.index, args.wav)
    manager.save(args.output_fmt or None, args.output_dat or None)
    out_fmt = args.output_fmt or args.fmt
    print(f"[ok] Sound {args.index} replaced with {args.wav}, archives written ({out_fmt} + dat)")
    return 0


class JuliaCliTool(BaseCliTool):
    """CLI tool for the battle sound archive (audio.fmt / audio.dat)."""

    @property
    def name(self) -> str:
        return "julia"

    @property
    def description(self) -> str:
        return "Sound editor: list/export/replace battle sounds (audio.fmt + audio.dat) as WAV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli julia",
            description="Headless battle sound editor (same operations as the Julia GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="List every sound entry")
        p_list.add_argument("--fmt", required=True, help="Path to audio.fmt")
        p_list.add_argument("--dat", help="Path to audio.dat (default: next to audio.fmt)")
        p_list.set_defaults(func=_cmd_list)

        p_export = sub.add_parser("export-wav", help="Export one sound to a .wav")
        p_export.add_argument("--fmt", required=True, help="Path to audio.fmt")
        p_export.add_argument("--dat", help="Path to audio.dat (default: next to audio.fmt)")
        p_export.add_argument("--index", type=int, required=True, help="Sound index (see 'list')")
        p_export.add_argument("--output", "-o", required=True, help="Output .wav path")
        p_export.set_defaults(func=_cmd_export_wav)

        p_export_all = sub.add_parser("export-all", help="Export every sound as sound_NNNN.wav")
        p_export_all.add_argument("--fmt", required=True, help="Path to audio.fmt")
        p_export_all.add_argument("--dat", help="Path to audio.dat (default: next to audio.fmt)")
        p_export_all.add_argument("--output-dir", "-o", required=True, help="Output folder")
        p_export_all.set_defaults(func=_cmd_export_all)

        p_replace = sub.add_parser("replace", help="Replace one sound with a .wav and rebuild the archives")
        p_replace.add_argument("--fmt", required=True, help="Path to audio.fmt")
        p_replace.add_argument("--dat", help="Path to audio.dat (default: next to audio.fmt)")
        p_replace.add_argument("--index", type=int, required=True, help="Sound index to replace")
        p_replace.add_argument("--wav", required=True, help="Replacement .wav (PCM or MS-ADPCM)")
        p_replace.add_argument("--output-fmt", help="Output audio.fmt (overwrites input if omitted)")
        p_replace.add_argument("--output-dat", help="Output audio.dat (overwrites input if omitted)")
        p_replace.set_defaults(func=_cmd_replace)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
