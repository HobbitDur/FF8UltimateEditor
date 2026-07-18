"""Watts - r0win.dat (battle victory sequence) CLI tool.

Commands:
    • info        - structure of the file: fanfare, camera, and the six win poses
    • show-seq    - disassemble a character's win-pose AnimSeq byte-code
    • camera      - show the Section 2 camera structure (sets/slots/keyframes; -v dumps values)
    • export      - write one part (fanfare-bank, fanfare-seq, camera, <char>-body,
                    <char>-seq, <char>-weapon) to a binary file
    • import      - replace one part from a binary file (validated first)
    • export-all  - write every part to a directory
    • import-anim - replace a body/weapon pose animation with an animation taken from
                    a battle model .dat (the character's own dXc/dXw)
    • set-fanfare-id - change the fanfare AKAO id: on PC this byte is the only part of
                    Section 1 the game reads (it plays song id = AKAO id - 1), so this
                    swaps the victory music
"""
import argparse
import os
import sys

from .base import BaseCliTool
from .common import load_game_data


def _load_manager(args):
    from Watts.wattsmanager import WattsManager
    manager = WattsManager(load_game_data())
    manager.load_file(args.input)
    return manager


def _save_manager(manager, args):
    output = getattr(args, "output", "") or args.input
    manager.save_file(output)
    print(f"[ok] saved {output}")


def _cmd_info(args) -> int:
    manager = _load_manager(args)
    summary = manager.get_summary()
    print(f"r0win.dat - battle victory sequence ({os.path.basename(args.input)})")
    print(f"  fanfare-bank: AKAO sample/instrument bank (PSX-only upload), "
          f"{summary['fanfare_bank_size']} bytes")
    print(f"  fanfare-seq : AKAO music sequence (the fanfare heard in game), "
          f"{summary['fanfare_seq_size']} bytes, AKAO id {summary['fanfare_akao_id']} "
          f"(PC song id {summary['fanfare_akao_id'] - 1})")
    camera = summary["camera"]
    print(f"  camera      : {summary['camera_size']} bytes = sequence byte-code "
          f"{camera['setting_size']} bytes + animation collection "
          f"{camera['collection_size']} bytes ({camera['nb_set']} sets) - see 'camera'")
    for pose in summary["poses"]:
        print(f"  {pose['name']} (com_id {pose['com_id']}, section {pose['section_id']}):")
        print(f"    {pose['name'].lower()}-body  : {pose['body_size']} bytes, "
              f"{pose['body_frames']} frames ({pose['body_bones']} bones)")
        print(f"    {pose['name'].lower()}-seq   : {pose['seq_bytecode'].hex(' ').upper()}")
        if pose["weapon_size"] is not None:
            print(f"    {pose['name'].lower()}-weapon: {pose['weapon_size']} bytes, "
                  f"{pose['weapon_frames']} frames ({pose['weapon_bones']} bones)")
    return 0


def _cmd_show_seq(args) -> int:
    manager = _load_manager(args)
    print(manager.describe_seq(args.char), end="")
    return 0


def _cmd_camera(args) -> int:
    manager = _load_manager(args)
    camera = manager.camera_summary()
    print(f"Section 2 camera ({os.path.basename(args.input)}):")
    print(f"  sequence byte-code (camera VM): {camera['setting_size']} bytes")
    if not camera["collection_parsed"]:
        print("  animation collection: not recognised, kept raw "
              f"({camera['collection_size']} bytes)")
        return 0
    print(f"  animation collection: {camera['collection_size']} bytes, "
          f"{camera['nb_set']} sets of 8 animation slots")
    for cam_set in camera["sets"]:
        print(f"  Set {cam_set['index']}:")
        for slot in cam_set["slots"]:
            if slot["empty"]:
                print(f"    slot {slot['slot']}: empty")
            else:
                print(f"    slot {slot['slot']}: {slot['blocks']} blocks, "
                      f"{slot['frames']} keyframes")
    if args.verbose:
        _dump_camera_keyframes(manager)
    return 0


def _dump_camera_keyframes(manager):
    for cam_set in manager.camera_collection.sets:
        for animation in cam_set.animations:
            if animation.empty or not animation.blocks:
                continue
            print(f"  Set {cam_set.index} slot {animation.slot}:")
            for block_index, block in enumerate(animation.blocks):
                print(f"    block {block_index}: fov_mode {block.fov_mode}, "
                      f"roll_mode {block.roll_mode}, layout {block.layout}")
                for frame_index, frame in enumerate(block.frames):
                    values = {label: field.get() for label, field in frame.fields()}
                    print(f"      #{frame_index}: dur {values['Duration']} "
                          f"pos ({values['Pos X']},{values['Pos Y']},{values['Pos Z']}) "
                          f"look ({values['Look X']},{values['Look Y']},{values['Look Z']})")


def _cmd_export(args) -> int:
    manager = _load_manager(args)
    data = manager.export_part(args.part)
    with open(args.output, "wb") as out_file:
        out_file.write(data)
    print(f"[ok] {args.part} -> {args.output} ({len(data)} bytes)")
    return 0


def _cmd_import(args) -> int:
    manager = _load_manager(args)
    with open(args.file, "rb") as in_file:
        data = in_file.read()
    try:
        manager.import_part(args.part, data)
    except ValueError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    _save_manager(manager, args)
    return 0


def _cmd_export_all(args) -> int:
    manager = _load_manager(args)
    os.makedirs(args.output_dir, exist_ok=True)
    for part_key in manager.part_keys():
        data = manager.export_part(part_key)
        path = os.path.join(args.output_dir, f"r0win_{part_key}.bin")
        with open(path, "wb") as out_file:
            out_file.write(data)
        print(f"[ok] {part_key} -> {path} ({len(data)} bytes)")
    return 0


def _cmd_import_anim(args) -> int:
    manager = _load_manager(args)
    try:
        manager.import_animation_from_dat(args.char, args.part, args.source, args.anim_id)
    except ValueError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    _save_manager(manager, args)
    return 0


def _cmd_set_fanfare_id(args) -> int:
    manager = _load_manager(args)
    try:
        manager.set_fanfare_akao_id(args.id)
    except ValueError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"[ok] fanfare AKAO id = {args.id} (PC song id {args.id - 1})")
    _save_manager(manager, args)
    return 0


def _add_input_argument(parser):
    parser.add_argument("--input", "-i", required=True, help="Path to r0win.dat")


class WattsCliTool(BaseCliTool):
    """r0win.dat victory-sequence editor."""

    @property
    def name(self) -> str:
        return "watts"

    @property
    def description(self) -> str:
        return ("r0win.dat editor: battle victory fanfare (AKAO), camera and the six "
                "dedicated character win poses")

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli watts",
            description="Edit r0win.dat, the battle victory sequence file")
        sub = parser.add_subparsers(dest="command", required=True)

        p_info = sub.add_parser("info", help="Print the file structure")
        _add_input_argument(p_info)
        p_info.set_defaults(func=_cmd_info)

        p_seq = sub.add_parser("show-seq", help="Disassemble a character's win-pose AnimSeq")
        _add_input_argument(p_seq)
        p_seq.add_argument("--char", "-c", required=True,
                           help="Rinoa, Quistis, Irvine, Edea, Selphie or Kiros")
        p_seq.set_defaults(func=_cmd_show_seq)

        p_camera = sub.add_parser("camera", help="Show the Section 2 camera structure")
        _add_input_argument(p_camera)
        p_camera.add_argument("--verbose", "-v", action="store_true",
                              help="Also dump every keyframe (duration, position, look-at)")
        p_camera.set_defaults(func=_cmd_camera)

        p_export = sub.add_parser("export", help="Export one part to a binary file")
        _add_input_argument(p_export)
        p_export.add_argument("--part", "-p", required=True,
                              help="fanfare-bank, fanfare-seq, camera, or <char>-body/"
                                   "<char>-seq/<char>-weapon (e.g. rinoa-body)")
        p_export.add_argument("--output", "-o", required=True, help="Destination file")
        p_export.set_defaults(func=_cmd_export)

        p_import = sub.add_parser("import", help="Replace one part from a binary file")
        _add_input_argument(p_import)
        p_import.add_argument("--part", "-p", required=True, help="Same keys as export")
        p_import.add_argument("--file", "-f", required=True, help="Binary file to import")
        p_import.add_argument("--output", "-o",
                              help="Output r0win.dat (omitted: overwrite --input)")
        p_import.set_defaults(func=_cmd_import)

        p_all = sub.add_parser("export-all", help="Export every part to a directory")
        _add_input_argument(p_all)
        p_all.add_argument("--output-dir", "-o", required=True, help="Destination directory")
        p_all.set_defaults(func=_cmd_export_all)

        p_anim = sub.add_parser(
            "import-anim",
            help="Replace a pose animation with animation N of a battle model .dat")
        _add_input_argument(p_anim)
        p_anim.add_argument("--char", "-c", required=True,
                            help="Rinoa, Quistis, Irvine, Edea, Selphie or Kiros")
        p_anim.add_argument("--part", "-p", default="body", choices=("body", "weapon"),
                            help="Which pose animation to replace (default body)")
        p_anim.add_argument("--source", "-s", required=True,
                            help="Battle model .dat holding the animation - must share "
                                 "the character's skeleton (their own dXc/dXw)")
        p_anim.add_argument("--anim-id", "-a", type=int, required=True,
                            help="Animation index inside the source .dat")
        p_anim.add_argument("--output", "-o",
                            help="Output r0win.dat (omitted: overwrite --input)")
        p_anim.set_defaults(func=_cmd_import_anim)

        p_fanfare = sub.add_parser(
            "set-fanfare-id",
            help="Change the fanfare AKAO id (PC plays song id = AKAO id - 1: "
                 "swaps the victory music)")
        _add_input_argument(p_fanfare)
        p_fanfare.add_argument("--id", type=int, required=True,
                               help="New AKAO id (1-255); vanilla is 2 -> song 1, "
                                    "the victory fanfare")
        p_fanfare.add_argument("--output", "-o",
                               help="Output r0win.dat (omitted: overwrite --input)")
        p_fanfare.set_defaults(func=_cmd_set_fanfare_id)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as error:
            print(f"[error] {error}", file=sys.stderr)
            return 1
