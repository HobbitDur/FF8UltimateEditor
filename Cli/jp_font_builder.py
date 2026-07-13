"""CLI tool: build the Japanese linear font atlas for the ILP-JP mod.

Converts the Japanese ``sysfnt_even.TEX`` / ``sysfnt_odd.TEX`` pair into a
single linear atlas the Western FF8 engine can sample (see
:mod:`FF8GameData.tex.jpfontatlas`). Also exposes a generic ``decode`` command
to render any FF8 PC ``.TEX`` to PNG for inspection.
"""
import argparse
import sys

from .base import BaseCliTool
from FF8GameData.tex.texfile import TexFile
from FF8GameData.tex.jpfontatlas import build_linear_atlas, JP_GLYPH_COUNT


def _cmd_build(args):
    even = TexFile.read(args.even)
    odd = TexFile.read(args.odd)
    print(f"[build] even: {even.width}x{even.height}, {even.num_palettes} palettes")
    print(f"[build] odd : {odd.width}x{odd.height}, {odd.num_palettes} palettes")

    atlas = build_linear_atlas(even, odd, glyph_count=args.glyphs)
    atlas.write(args.output)
    print(f"[build] wrote linear atlas: {atlas.width}x{atlas.height} "
          f"({args.glyphs} glyphs, {atlas.height // 12} rows) -> {args.output}")

    if args.png:
        atlas.to_image(args.palette).save(args.png)
        print(f"[build] wrote preview PNG (palette {args.palette}) -> {args.png}")


def _cmd_decode(args):
    tex = TexFile.read(args.input)
    print(f"[decode] {tex.width}x{tex.height}, {tex.num_palettes} palettes, "
          f"{tex.palette_entries} entries")
    tex.to_image(args.palette).save(args.output)
    print(f"[decode] wrote PNG (palette {args.palette}) -> {args.output}")


class JpFontBuilderCliTool(BaseCliTool):
    """Build / inspect FF8 Japanese font textures."""

    @property
    def name(self) -> str:
        return "jp-font-builder"

    @property
    def description(self) -> str:
        return "JP Font Builder — combine sysfnt_even/odd.TEX into one linear atlas for the ILP-JP mod"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli jp-font-builder",
            description="Build the Japanese linear font atlas for ILP-JP",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ff8-cli jp-font-builder build --even sysfnt_even.TEX --odd sysfnt_odd.TEX \\
                                --output sysfnt_jp_linear.TEX --png preview.png
  ff8-cli jp-font-builder decode --input sysfnt_even.TEX --output even.png
            """,
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_build = sub.add_parser("build", help="Combine even/odd TEX into one linear atlas")
        p_build.add_argument("--even", required=True, help="sysfnt_even.TEX path")
        p_build.add_argument("--odd", required=True, help="sysfnt_odd.TEX path")
        p_build.add_argument("--output", "-o", required=True, help="Output .TEX atlas path")
        p_build.add_argument("--png", help="Also write a preview PNG to this path")
        p_build.add_argument("--palette", type=int, default=0, help="Palette index for the preview (default 0)")
        p_build.add_argument("--glyphs", type=int, default=JP_GLYPH_COUNT,
                             help=f"Number of glyph cells (default {JP_GLYPH_COUNT})")
        p_build.set_defaults(func=_cmd_build)

        p_decode = sub.add_parser("decode", help="Render any FF8 PC .TEX to PNG")
        p_decode.add_argument("--input", "-i", required=True, help="Input .TEX path")
        p_decode.add_argument("--output", "-o", required=True, help="Output PNG path")
        p_decode.add_argument("--palette", type=int, default=0, help="Palette index (default 0)")
        p_decode.set_defaults(func=_cmd_decode)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            if not hasattr(args, "func"):
                print("[error] No command specified", file=sys.stderr)
                return 1
            args.func(args)
            return 0
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
