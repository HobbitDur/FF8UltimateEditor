"""
Zone CLI Tool.

Named after Zone, the Forest Owls' devoted magazine collector.
Headless mmag.bin editing (same data as the Zone GUI):
  • export-csv  (mmag.bin → CSV: one row per magazine page entry)
  • import-csv  (CSV → new mmag.bin)
  • show        (pretty-print one entry, resolving names and, with --mngrp,
                 the text overlay strings from the book-text sections)
  • export-png  (render a page - or every page - the way the menu draws it)
"""

import argparse
import os
import sys

from Zone.zonerender import BUTTON_STYLES, BUTTON_STYLE_ICONS

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

CSV_HEADER = ["Entry", "Name",
              "Window X", "Window Y", "Window W", "Window H",
              "Pic X", "Pic Y", "Pic W", "Pic H",
              "Pic tint R", "Pic tint G", "Pic tint B",
              "Paper E1", "Paper E2",
              "Text file", "Texture category", "Texture page",
              "Weapon index", "Weapon spacing", "Duel move ID", "Angelo move ID",
              "Weapon list X", "Weapon list Y", "Weapon qty column X",
              "Duel combo X", "Duel combo Y", "Footer"]
for _kind in ("Pic ov", "Text ov"):
    for _slot in range(1, 5):
        CSV_HEADER += [f"{_kind}{_slot} X", f"{_kind}{_slot} Y", f"{_kind}{_slot} ID"]


def _load_manager(mmag_path: str):
    from Zone.zonemanager import ZoneManager
    manager = ZoneManager(load_game_data())
    manager.load_file(mmag_path)
    return manager


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input)
    rows = []
    for index, entry in enumerate(manager.entries):
        row = [index, manager.entry_name(index),
               entry.window_x, entry.window_y, entry.window_width, entry.window_height,
               entry.picture_x, entry.picture_y, entry.picture_width, entry.picture_height,
               entry.picture_tint_r, entry.picture_tint_g, entry.picture_tint_b,
               entry.paper_e1, entry.paper_e2,
               entry.text_file_index, entry.texture_category, entry.texture_page,
               entry.weapon_index, entry.weapon_line_spacing,
               entry.duel_move_id, entry.angelo_move_id,
               entry.weapon_list_x, entry.weapon_list_y, entry.weapon_quantity_column_x,
               entry.duel_combo_x, entry.duel_combo_y, entry.footer_flag]
        for overlay in entry.picture_overlays + entry.text_overlays:
            row += [overlay.x, overlay.y, overlay.id]
        rows.append(row)
    write_csv(args.output, CSV_HEADER, rows)
    print(f"[ok] {len(rows)} magazine page entries exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        entry = manager.entries[int(row[0])]
        # Column 1 is the informational entry name, ignored on import
        (entry.window_x, entry.window_y, entry.window_width, entry.window_height,
         entry.picture_x, entry.picture_y, entry.picture_width, entry.picture_height,
         entry.picture_tint_r, entry.picture_tint_g, entry.picture_tint_b,
         entry.paper_e1, entry.paper_e2,
         entry.text_file_index, entry.texture_category, entry.texture_page,
         entry.weapon_index, entry.weapon_line_spacing,
         entry.duel_move_id, entry.angelo_move_id,
         entry.weapon_list_x, entry.weapon_list_y, entry.weapon_quantity_column_x,
         entry.duel_combo_x, entry.duel_combo_y, entry.footer_flag) = \
            (int(value) for value in row[2:28])
        for slot, overlay in enumerate(entry.picture_overlays + entry.text_overlays):
            overlay.x, overlay.y, overlay.id = (int(value) for value in
                                                row[28 + slot * 3:31 + slot * 3])
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} entries applied, written to {args.output or args.input}")
    return 0


def _cmd_show(args) -> int:
    manager = _load_manager(args.input)
    if not 0 <= args.entry < len(manager.entries):
        raise ValueError(f"Entry must be 0-{len(manager.entries) - 1}, got {args.entry}")
    if args.mngrp:
        manager.load_mngrp(args.mngrp)
    entry = manager.entries[args.entry]

    print(f"Entry {args.entry}: {manager.entry_name(args.entry)}")
    print(f"  Window: ({entry.window_x},{entry.window_y}) "
          f"{entry.window_width}x{entry.window_height}")
    if not entry.picture_width or not entry.picture_height:
        print("  Paper mat: none")
    else:
        print(f"  Paper mat: ({entry.picture_x},{entry.picture_y}) "
              f"{entry.picture_width}x{entry.picture_height} "
              f"tint ({entry.picture_tint_r},{entry.picture_tint_g},{entry.picture_tint_b})/128")
    print(f"  Paper background: E1=0x{entry.paper_e1:02X} E2=0x{entry.paper_e2:02X}")
    print(f"  Book text: file {entry.text_file_index} "
          f"(mngrp raw {manager.book_text_raw_file(entry)})")
    print(f"  Page texture: {manager.get_texture_category_name(entry.texture_category)} "
          f"page {entry.texture_page} (mngrp raw {manager.texture_raw_file(entry)})")
    print(f"  Unlocks: weapon={manager.get_weapon_name(entry.weapon_index)}, "
          f"duel={manager.get_duel_move_name(entry.duel_move_id)}, "
          f"angelo={manager.get_angelo_move_name(entry.angelo_move_id)}")
    if entry.weapon_index != 0xFF:
        print(f"    weapon list at ({entry.weapon_list_x},{entry.weapon_list_y}), "
              f"quantity column +{entry.weapon_quantity_column_x}, "
              f"line spacing {entry.weapon_line_spacing}")
    if entry.duel_move_id != 0xFF:
        print(f"    duel combo at ({entry.duel_combo_x},{entry.duel_combo_y})")
    print(f"  Footer: {'yes' if entry.footer_flag else 'no'}")
    for slot, overlay in enumerate(entry.picture_overlays):
        if not overlay.unused:
            print(f"  Picture overlay {slot + 1}: SP2 sprite {overlay.id} "
                  f"at ({overlay.x},{overlay.y})")
    for slot, overlay in enumerate(entry.text_overlays):
        if not overlay.unused:
            line = f"  Text overlay {slot + 1}: string {overlay.id} at ({overlay.x},{overlay.y})"
            if manager.mngrp_loaded:
                text = manager.get_overlay_text(entry, overlay).replace("\n", " / ")
                line += f' = "{text}"'
            print(line)
    return 0


def _cmd_export_png(args) -> int:
    from Zone.zonerender import BUTTON_STYLE_ICONS, PageRenderer
    manager = _load_manager(args.input)
    manager.load_mngrp(args.mngrp)
    if args.kernel:
        manager.load_kernel(args.kernel)
    if args.mwepon:
        manager.load_mwepon(args.mwepon)
    if args.icon_sp1:
        manager.load_icons(args.icon_sp1)
    if args.mitem:
        manager.load_mitem(args.mitem)
    renderer = PageRenderer(manager, menu_folder=args.menu_folder or os.path.dirname(args.mngrp),
                            button_icon_style=args.button_icons)
    if not renderer.has_font:
        print("[warn] sysfnt.TEX not found next to mngrp.bin: text is drawn as boxes")
    if not args.kernel:
        print("[warn] no --kernel: the Combat King pages draw no Duel button combo")
    if not args.mwepon:
        print("[warn] no --mwepon: the Weapons Monthly pages draw no remodel item list")

    if args.entry is None:
        entries = list(range(len(manager.entries)))
        os.makedirs(args.output, exist_ok=True)
    else:
        if not 0 <= args.entry < len(manager.entries):
            raise ValueError(f"Entry must be 0-{len(manager.entries) - 1}, got {args.entry}")
        entries = [args.entry]

    for index in entries:
        image = renderer.render(manager.entries[index],
                                draw_background=not args.no_background)
        if args.scale > 1:
            from PIL import Image
            image = image.resize((image.width * args.scale, image.height * args.scale),
                                 resample=Image.Resampling.NEAREST)  # keep the pixels crisp
        if args.entry is None:
            path = os.path.join(args.output, f"mmag_{index:02d}.png")
        else:
            path = args.output
        image.save(path)
    if args.entry is None:
        print(f"[ok] {len(entries)} pages rendered to {args.output}")
    else:
        print(f"[ok] entry {args.entry} ({manager.entry_name(args.entry)}) rendered to {args.output}")
    return 0


class ZoneCliTool(BaseCliTool):
    """CLI tool for mmag.bin (in-menu magazine page definitions) editing."""

    @property
    def name(self) -> str:
        return "zone"

    @property
    def description(self) -> str:
        return "Magazine page editor: export/import mmag.bin (magazine page views) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli zone",
            description="Headless mmag.bin editor (same data as the Zone GUI). "
                        "mmag2.bin uses the same format and loads too.",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-csv", help="Export mmag.bin to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to mmag.bin")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Build a mmag.bin from a CSV")
        p_import.add_argument("--input", "-i", required=True,
                              help="Path to the base mmag.bin (entries not in the CSV are kept)")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o",
                              help="Output mmag.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        p_show = sub.add_parser("show", help="Pretty-print one magazine page entry")
        p_show.add_argument("--input", "-i", required=True, help="Path to mmag.bin")
        p_show.add_argument("--entry", "-e", required=True, type=int, help="Entry index (0-68)")
        p_show.add_argument("--mngrp", help="Path to mngrp.bin (mngrphd.bin auto-detected "
                                            "next to it) to resolve the text overlay strings")
        p_show.set_defaults(func=_cmd_show)

        p_png = sub.add_parser("export-png", help="Render a page the way the menu draws it")
        p_png.add_argument("--input", "-i", required=True, help="Path to mmag.bin")
        p_png.add_argument("--mngrp", "-m", required=True,
                           help="Path to mngrp.bin (mngrphd.bin auto-detected next to it): "
                                "carries the page textures, the sprites and the book text")
        p_png.add_argument("--entry", "-e", type=int,
                           help="Entry index to render (omit to render every page)")
        p_png.add_argument("--output", "-o", required=True,
                           help="Output PNG, or the output folder when --entry is omitted")
        p_png.add_argument("--kernel", "-k",
                           help="Path to kernel.bin: Zell's Duel button combos, drawn on the "
                                "Combat King pages")
        p_png.add_argument("--mwepon", "-w",
                           help="Path to mwepon.bin: the weapon remodel item lists, drawn on "
                                "the Weapons Monthly pages")
        p_png.add_argument("--icon-sp1", help="Path to icon.sp1 (icon.TEX read beside it): the "
                                              "button and item icons of the unlock block")
        p_png.add_argument("--mitem", help="Path to mitem.bin: which type icon a remodel item uses")
        p_png.add_argument("--button-icons", choices=BUTTON_STYLES, default=BUTTON_STYLE_ICONS,
                           help="Which glyph to draw for a Duel button. In game the engine picks "
                                "it through the player's key config, so 'icons' shows icon.sp1's "
                                "PlayStation pad default and 'boxes' claims nothing")
        p_png.add_argument("--menu-folder", help="Folder holding sysfnt.TEX/sysfnt.tdw for the "
                                                 "text (defaults to the mngrp.bin folder)")
        p_png.add_argument("--scale", type=int, default=1, help="Integer upscale factor")
        p_png.add_argument("--no-background", action="store_true",
                           help="Skip the window/paper background (it is only a flat stand-in)")
        p_png.set_defaults(func=_cmd_export_png)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
