"""
JumboCactuar CLI Tool.

Headless scene.out editing (same data as the JumboCactuar GUI):
  • list          (one line per encounter: stage + enabled enemies, filter by monster)
  • show          (every field of one encounter)
  • export-csv    (scene.out → CSV: one row per encounter, every field)
  • import-csv    (base scene.out + CSV → new scene.out)
  • copy          (copy a whole encounter onto another one)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import read_csv, write_csv

SLOT_FLAG_LETTERS = [("enabled", "E"), ("not_targetable", "T"), ("not_visible", "V"), ("not_loaded", "L")]


def _csv_header():
    from FF8GameData.sceneout import NB_SLOT
    header = ["Encounter", "Stage", "Battle flags", "Camera main", "Camera secondary"]
    for slot in range(NB_SLOT):
        header += [f"Slot {slot} enemy (c0m)", f"Slot {slot} level", f"Slot {slot} x", f"Slot {slot} y",
                   f"Slot {slot} z", f"Slot {slot} flags (ETVL)"]
    return header + ["Unknown (hex)"]


def _load_manager(path):
    from JumboCactuar.jumbocactuarmanager import JumboCactuarManager
    manager = JumboCactuarManager()
    manager.load_file(path)
    return manager


def _slot_flags_text(record, slot):
    return "".join(letter if record.slot_flag(name, slot) else "-" for name, letter in SLOT_FLAG_LETTERS)


def _cmd_list(args) -> int:
    from FF8GameData.sceneout import ENEMY_ID_BASE, NB_SLOT
    manager = _load_manager(args.input)
    shown = 0
    for index, record in enumerate(manager.records):
        if args.enemy is not None and not any(
                record.slot_flag("enabled", slot) and record.enemy_byte(slot) == args.enemy + ENEMY_ID_BASE
                for slot in range(NB_SLOT)):
            continue
        print(manager.summary(index))
        shown += 1
    print(f"[ok] {shown} encounter(s)")
    return 0


def _cmd_show(args) -> int:
    from FF8GameData.sceneout import BATTLE_FLAG_NAMES, NB_SLOT
    manager = _load_manager(args.input)
    record = manager.records[args.id]
    print(f"Encounter {args.id}")
    print(f"  Stage: {manager.stage_label(record.stage_id).strip()}")
    flags = [name for bit, name in enumerate(BATTLE_FLAG_NAMES) if record.flag(bit)]
    print(f"  Battle flags: 0x{record.flags:02X} {', '.join(flags) if flags else '(none)'}")
    for index, name in enumerate(("Main", "Secondary")):
        camera_set, camera_anim = record.camera(index)
        print(f"  {name} intro camera: set {camera_set}, animation {camera_anim} (0x{record.camera_byte(index):02X})")
    for slot in range(NB_SLOT):
        print(f"  Slot {slot}: {manager.enemy_label(record.enemy_byte(slot)).strip()}, level {record.level(slot)}, "
              f"position {record.position(slot)}, flags {_slot_flags_text(record, slot)}")
    print(f"  Unknown: {record.unknown.hex(' ').upper()}")
    return 0


def _cmd_export_csv(args) -> int:
    from FF8GameData.sceneout import ENEMY_ID_BASE, NB_SLOT
    manager = _load_manager(args.input)
    rows = []
    for index, record in enumerate(manager.records):
        row = [index, record.stage_id, f"0x{record.flags:02X}", f"0x{record.camera_byte(0):02X}",
               f"0x{record.camera_byte(1):02X}"]
        for slot in range(NB_SLOT):
            row += [record.enemy_byte(slot) - ENEMY_ID_BASE, record.level(slot), *record.position(slot),
                    _slot_flags_text(record, slot)]
        rows.append(row + [record.unknown.hex(" ").upper()])
    write_csv(args.output, _csv_header(), rows)
    print(f"[ok] {len(rows)} encounters exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    from FF8GameData.sceneout import ENEMY_ID_BASE, NB_SLOT
    manager = _load_manager(args.input)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        record = manager.records[int(row[0])]
        record.stage_id = int(row[1], 0)
        record.flags = int(row[2], 0)
        record.set_camera_byte(0, int(row[3], 0))
        record.set_camera_byte(1, int(row[4], 0))
        for slot in range(NB_SLOT):
            enemy, level, x, y, z, flags = row[5 + slot * 6:11 + slot * 6]
            record.set_enemy_byte(slot, int(enemy) + ENEMY_ID_BASE)
            record.set_level(slot, int(level))
            record.set_position(slot, (int(x), int(y), int(z)))
            for name, letter in SLOT_FLAG_LETTERS:
                record.set_slot_flag(name, slot, letter in flags.upper())
        record.unknown = bytes.fromhex(row[5 + NB_SLOT * 6])
        applied += 1
    manager.save_file(args.output or args.input)
    print(f"[ok] {applied} encounters applied, written to {args.output or args.input}")
    return 0


def _cmd_copy(args) -> int:
    manager = _load_manager(args.input)
    manager.records[args.to].data[:] = manager.records[args.source].data
    manager.save_file(args.output or args.input)
    print(f"[ok] encounter {args.source} copied onto {args.to}: {manager.summary(args.to)}")
    return 0


class JumboCactuarCliTool(BaseCliTool):
    """CLI tool for scene.out (the encounter list) editing."""

    @property
    def name(self) -> str:
        return "jumbo-cactuar"

    @property
    def description(self) -> str:
        return "Encounter editor: list/show/copy scene.out encounters, export/import them as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli jumbo-cactuar",
            description="Headless scene.out editor (same data as the JumboCactuar GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_list = sub.add_parser("list", help="One line per encounter: stage and enabled enemies")
        p_list.add_argument("--input", "-i", required=True, help="Path to scene.out")
        p_list.add_argument("--enemy", type=int, help="Only the encounters with this c0m number")
        p_list.set_defaults(func=_cmd_list)

        p_show = sub.add_parser("show", help="Every field of one encounter")
        p_show.add_argument("--input", "-i", required=True, help="Path to scene.out")
        p_show.add_argument("--id", type=int, required=True, help="Encounter id (0-1023)")
        p_show.set_defaults(func=_cmd_show)

        p_export = sub.add_parser("export-csv", help="Export scene.out to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to scene.out")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto a scene.out")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base scene.out")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output scene.out (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        p_copy = sub.add_parser("copy", help="Copy a whole encounter onto another one")
        p_copy.add_argument("--input", "-i", required=True, help="Path to scene.out")
        p_copy.add_argument("--from", dest="source", type=int, required=True, help="Encounter id to copy")
        p_copy.add_argument("--to", type=int, required=True, help="Encounter id to overwrite")
        p_copy.add_argument("--output", "-o", help="Output scene.out (overwrites input if omitted)")
        p_copy.set_defaults(func=_cmd_copy)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
