"""
Minimog CLI Tool.

Headless icon.sp1 editing (same data as the Minimog GUI):
  • list                   (print icons with their quads and decoded fields)
  • set-quad               (edit one quad's UV/size/offsets/CLUT/flags)
  • add-quad               (append a quad to an icon, the directory is rebuilt)
  • remove-quad            (delete a quad from an icon)
  • export-png             (render one icon or a contact sheet from icon.TEX)
  • export-tex-png         (convert the raw icon.TEX atlas to PNG using one chosen palette)
  • export-tex-true-colors (same atlas layout, but each region uses its own icon's real CLUT)
"""

import argparse
import sys

from .base import BaseCliTool

QUAD_FIELDS = ("u", "v", "width", "height", "dx", "dy", "clut", "abe", "tpage")


def _load_manager(sp1_path: str):
    from Minimog.minimogmanager import MinimogManager
    manager = MinimogManager()
    manager.load_file(sp1_path)
    return manager


def _apply_quad_args(quad, args) -> int:
    applied = 0
    for field, attribute in (("u", "u"), ("v", "v"), ("width", "width"), ("height", "height"),
                             ("dx", "dx"), ("dy", "dy"), ("clut", "clut"),
                             ("tpage", "texture_page")):
        value = getattr(args, field)
        if value is not None:
            setattr(quad, attribute, value)
            applied += 1
    if args.abe is not None:
        quad.semi_transparent = bool(args.abe)
        applied += 1
    return applied


def _add_quad_arguments(parser, for_set: bool):
    help_suffix = "" if for_set else " (default 0)"
    parser.add_argument("--u", type=int, help=f"Texture U 0-255{help_suffix}")
    parser.add_argument("--v", type=int, help=f"Texture V 0-255{help_suffix}")
    parser.add_argument("--width", type=int, help=f"Width 0-255{help_suffix}")
    parser.add_argument("--height", type=int, help=f"Height 0-255{help_suffix}")
    parser.add_argument("--dx", type=int, help=f"Signed X draw offset -128..127{help_suffix}")
    parser.add_argument("--dy", type=int, help=f"Signed Y draw offset -128..127{help_suffix}")
    parser.add_argument("--clut", type=int,
                        help="CLUT selector 0-2047 (primitive CLUT = 0x3810 + value, "
                             "TEX palette = value / 64)")
    parser.add_argument("--abe", type=int, choices=(0, 1), help="Semi-transparency bit")
    parser.add_argument("--tpage", type=int, choices=(0, 1, 2, 3), help="Texture page bits 30-31")


def _cmd_list(args) -> int:
    manager = _load_manager(args.input)
    icons = manager.icons
    if args.icon_id is not None:
        icons = [manager.icons[args.icon_id]]
    for icon in icons:
        note = " (key-config button, quads unused in-game)" if icon.is_button_icon else ""
        print(f"{icon.name}{note}")
        for index, quad in enumerate(icon.quads):
            print(f"    quad {index}: {quad}")
    print(f"[ok] {len(icons)} icon(s), {sum(len(i.quads) for i in icons)} quad(s)")
    return 0


def _cmd_set_quad(args) -> int:
    manager = _load_manager(args.input)
    quad = manager.icons[args.icon_id].quads[args.quad]
    if _apply_quad_args(quad, args) == 0:
        print("[error] Nothing to set: give at least one of "
              + ", ".join(f"--{f}" for f in QUAD_FIELDS), file=sys.stderr)
        return 1
    manager.save_file(args.output or args.input)
    print(f"[ok] icon {args.icon_id} quad {args.quad}: {quad}")
    return 0


def _cmd_add_quad(args) -> int:
    from Minimog.minimogmanager import Sp1Quad
    manager = _load_manager(args.input)
    quad = Sp1Quad()
    _apply_quad_args(quad, args)
    manager.add_quad(args.icon_id, quad)
    manager.save_file(args.output or args.input)
    icon = manager.icons[args.icon_id]
    print(f"[ok] icon {args.icon_id} now has {len(icon.quads)} quads, "
          f"new quad {len(icon.quads) - 1}: {quad}")
    return 0


def _cmd_remove_quad(args) -> int:
    manager = _load_manager(args.input)
    removed = manager.remove_quad(args.icon_id, args.quad)
    manager.save_file(args.output or args.input)
    print(f"[ok] icon {args.icon_id} quad {args.quad} removed ({removed})")
    return 0


def _cmd_export_png(args) -> int:
    from FF8GameData.tex.texfile import TexFile
    manager = _load_manager(args.input)
    tex_file = TexFile.read(args.tex)
    if args.icon_id is not None:
        image = manager.render_icon(args.icon_id, tex_file, scale=args.scale)
        if image is None:
            print(f"[error] icon {args.icon_id} has no visible quad", file=sys.stderr)
            return 1
        image.save(args.output)
        print(f"[ok] icon {args.icon_id} ({image.width}x{image.height}) saved to {args.output}")
        return 0
    # Contact sheet of every icon
    sheet = manager.render_sheet(tex_file, scale=args.scale)
    sheet.save(args.output)
    print(f"[ok] {len(manager.icons)} icons rendered to {args.output}")
    return 0


def _cmd_export_tex_png(args) -> int:
    """Convert the raw icon.TEX atlas to PNG - no icon.sp1 needed. icon.TEX only
    stores palette indices per pixel, so the same bytes render as completely
    different colors depending which of its palettes is picked here."""
    from FF8GameData.tex.texfile import TexFile
    tex_file = TexFile.read(args.tex)
    if not 0 <= args.palette < tex_file.num_palettes:
        print(f"[error] palette {args.palette} out of range "
              f"(0..{tex_file.num_palettes - 1})", file=sys.stderr)
        return 1
    image = tex_file.to_image(args.palette)
    image.save(args.output)
    print(f"[ok] icon.TEX palette {args.palette} ({image.width}x{image.height}) saved to {args.output}")
    return 0


def _cmd_export_tex_true_colors(args) -> int:
    """Same layout/size as export-tex-png, but each region uses whichever
    icon.sp1 quad actually claims it instead of one picked palette - the
    true in-game coloring, e.g. why 'Target' always comes out red."""
    from FF8GameData.tex.texfile import TexFile
    manager = _load_manager(args.input)
    tex_file = TexFile.read(args.tex)
    image = manager.render_texture_true_colors(tex_file)
    image.save(args.output)
    print(f"[ok] icon.TEX ({image.width}x{image.height}) rendered with each icon's own "
          f"palette, saved to {args.output}")
    return 0


class MinimogCliTool(BaseCliTool):
    """CLI tool for icon.sp1 (menu icon UV table) editing."""

    @property
    def name(self) -> str:
        return "minimog"

    @property
    def description(self) -> str:
        return "Menu icon editor: list/edit icon.sp1 quads (UV, size, offsets, CLUT), render previews"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli minimog",
            description="Headless icon.sp1 editor (same data as the Minimog GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="Print icons with their decoded quads")
        p_list.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_list.add_argument("--icon-id", type=int, help="Only print this icon")
        p_list.set_defaults(func=_cmd_list)

        p_set = sub.add_parser("set-quad", help="Edit one quad of an icon")
        p_set.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_set.add_argument("--icon-id", type=int, required=True, help="Icon id")
        p_set.add_argument("--quad", type=int, required=True, help="Quad index inside the icon")
        _add_quad_arguments(p_set, for_set=True)
        p_set.add_argument("--output", "-o", help="Output icon.sp1 (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set_quad)

        p_add = sub.add_parser("add-quad", help="Append a quad to an icon (rebuilds the directory)")
        p_add.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_add.add_argument("--icon-id", type=int, required=True, help="Icon id")
        _add_quad_arguments(p_add, for_set=False)
        p_add.add_argument("--output", "-o", help="Output icon.sp1 (overwrites input if omitted)")
        p_add.set_defaults(func=_cmd_add_quad)

        p_remove = sub.add_parser("remove-quad", help="Delete a quad from an icon")
        p_remove.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_remove.add_argument("--icon-id", type=int, required=True, help="Icon id")
        p_remove.add_argument("--quad", type=int, required=True, help="Quad index inside the icon")
        p_remove.add_argument("--output", "-o", help="Output icon.sp1 (overwrites input if omitted)")
        p_remove.set_defaults(func=_cmd_remove_quad)

        p_png = sub.add_parser("export-png", help="Render icon(s) to PNG using icon.TEX")
        p_png.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_png.add_argument("--tex", "-t", required=True, help="Path to icon.TEX")
        p_png.add_argument("--icon-id", type=int, help="Icon id (omit for a full contact sheet)")
        p_png.add_argument("--scale", type=int, default=1, help="Integer zoom factor (default 1)")
        p_png.add_argument("--output", "-o", required=True, help="Output PNG path")
        p_png.set_defaults(func=_cmd_export_png)

        p_tex_png = sub.add_parser("export-tex-png",
                                   help="Convert the raw icon.TEX atlas to PNG using one palette")
        p_tex_png.add_argument("--tex", "-t", required=True, help="Path to icon.TEX")
        p_tex_png.add_argument("--palette", type=int, default=0,
                               help="Palette index to render with (0-15 for icon.TEX, default 0)")
        p_tex_png.add_argument("--output", "-o", required=True, help="Output PNG path")
        p_tex_png.set_defaults(func=_cmd_export_tex_png)

        p_tex_true = sub.add_parser("export-tex-true-colors",
                                    help="Convert icon.TEX to PNG, each region using its own icon's real CLUT")
        p_tex_true.add_argument("--input", "-i", required=True, help="Path to icon.sp1")
        p_tex_true.add_argument("--tex", "-t", required=True, help="Path to icon.TEX")
        p_tex_true.add_argument("--output", "-o", required=True, help="Output PNG path")
        p_tex_true.set_defaults(func=_cmd_export_tex_true_colors)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
