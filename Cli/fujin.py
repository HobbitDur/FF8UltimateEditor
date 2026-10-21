"""Fujin CLI: effect sources, native camera constants and MAG section/cinematic tools."""
import argparse
import os
import json
import struct
from pathlib import Path
from dataclasses import asdict

from .base import BaseCliTool


def _load(args):
    from Fujin.magdocument import MagDocument
    manager = MagDocument()
    manager.load_file(args.input)
    return manager


def _int(text):
    return int(text, 0)


def _cmd_info(args) -> int:
    from FF8GameData.magcine.magcontainer import MagContainer, HEADER_FIELDS
    manager = _load(args)
    program = manager.program
    print(f"{os.path.basename(args.input)} - {manager.document.format}, {len(manager.data)} bytes")
    for section in manager.document.sections:
        print(f"  0x{section.start:06X}-0x{section.end:06X} {section.kind:14} {section.name} ({section.size} bytes)")
    for warning in manager.document.warnings:
        print(f"  warning: {warning}")
    if manager.document.format != "Packed MAG":
        return 0
    container = MagContainer(bytes(manager.data))
    for offset, label in HEADER_FIELDS:
        value = container.header[offset // 4]
        print(f"  header +{offset:02X} {label:28} {f'0x{value:X}' if value else '-'}")
    if program is None:
        return 0
    unreached = sum(end - start for start, end in manager.unreached_ranges())
    print(f"  script region 0x{manager.root:X}-0x{manager.script_end:X}: {len(program.instructions)} reachable "
          f"instructions, {len(program.blocks())} blocks, {len(program.particle_scripts)} particle scripts, "
          f"{unreached} bytes not reached, {len(program.errors)} decode errors")
    for offset, message in program.errors[:10]:
        print(f"    error at 0x{offset:X}: {message}")
    for obj in container.objects:
        detail = obj.error or (f"{len(obj.mesh.vertices)} vertices, {len(obj.mesh.faces)} faces" if obj.mesh
                               else ", ".join(f"{k} {v}" for k, v in obj.info.items() if k != "frames" and k != "sections"))
        print(f"  object {obj.index:3} {obj.kind:6} at 0x{obj.offset:05X}: {detail}")
    return 0


def _cmd_disasm(args) -> int:
    manager = _load(args)
    if manager.program is None:
        raise ValueError("This file has no cinematic script; use info or section")
    labels = manager.labels()
    if args.linear is not None:
        start = _int(args.linear)
        instructions, _stop = manager.linear_disassembly(start, min(len(manager.data), start + 2 * args.count))
    else:
        instructions = manager.program.sorted_instructions()
    for instruction in instructions:
        label = labels.get(instruction.offset)
        if label:
            print(f"\n{label}:")
        line = f"  {instruction.offset:05X}  {instruction.raw()[:12].hex(' '):36} {manager.format(instruction, labels)}"
        if args.explain:
            line += f"    ; {manager.describe(instruction)[:110]}"
        print(line)
    return 0


def _cmd_section(args) -> int:
    manager = _load(args)
    start = _int(args.at)
    section = next((s for s in manager.document.sections if s.start == start), None)
    if section is None:
        raise ValueError("No section starts at that offset; use info to list the sections")
    if args.export:
        with open(args.export, "wb") as f:
            f.write(manager.data[section.start:section.end])
        print(f"[ok] exported {section.name}: {section.size} bytes")
    else:
        with open(args.replace, "rb") as f:
            manager.replace_section(start, f.read())
        manager.save_file(args.output or args.input)
        print(f"[ok] replaced {section.name} without moving following offsets")
    return 0


def _cmd_timeline(args) -> int:
    manager = _load(args)
    simulation = manager.simulate(seed=args.seed, target_count=args.targets)
    labels = manager.labels()
    end = simulation.finished_tick if simulation.finished_tick >= 0 else simulation.tick
    print(f"{len(simulation.bones)} bones, sequence end at tick {end} ({end / 15:.1f} s at 15 ticks/s)")
    categories = set(args.categories.split(",")) if args.categories else {"camera", "sound", "draw", "model", "freeze"}
    for bone in simulation.bones:
        death = bone.death_tick if bone.death_tick >= 0 else "end"
        name = labels.get(bone.program, f"{bone.program:05X}")
        print(f"#{bone.index:4} {name:12} ticks {bone.spawn_tick:4}-{death!s:4} parent #{bone.parent}")
        shown = [event for event in bone.events if event.category in categories]
        for event in shown[:args.max_events]:
            print(f"        t{event.tick:4} {event.category:8} {event.offset:05X} {event.text}")
        if len(shown) > args.max_events:
            print(f"        ... {len(shown) - args.max_events} more")
    for tick, offset, message in simulation.warnings[:20]:
        print(f"warning t{tick} at 0x{offset:X}: {message}")
    return 0


def _cmd_opcodes(args) -> int:
    from FF8GameData.magcine.cinescript import CineOpcodeTable
    for code, opcode in sorted(CineOpcodeTable.default().opcodes.items()):
        if not opcode.valid and not args.all:
            continue
        gfs = f" [{', '.join(opcode.gfs)}]" if opcode.gfs else ""
        print(f"0x{code:03X} {opcode.name:32} len {opcode.length_expr:40} {opcode.flow:9}{gfs}")
        if args.verbose:
            print(f"      {opcode.semantics}")
    return 0


def _cmd_patch(args) -> int:
    manager = _load(args)
    offset = _int(args.at)
    old = manager.instruction_at(offset)
    words = [_int(w) for w in args.words.split(",")] if args.words else list(old.words)
    op = _int(args.op) if args.op else old.op
    new = manager.replace_instruction(offset, op, words)
    print(f"0x{offset:X}: {manager.format(old)}  ->  {manager.format(new)}")
    output = args.output or args.input
    manager.save_file(output)
    print(f"[ok] saved {output}")
    return 0


def _add_input(parser):
    parser.add_argument("--input", "-i", required=True, help="Path to any MAG file or streamed part")


def _cmd_effect(args):
    from Fujin.effectcatalog import EffectCatalog
    catalog = EffectCatalog()
    if args.id not in catalog.effect_ids():
        raise ValueError("Effect ID must be between 1 and 400")
    print(json.dumps(dict(effect_id=args.id, name=catalog.name(args.id), runtime=catalog.runtime(args.id),
        note=catalog.notes(args.id), resources=[asdict(r) for r in catalog.resources(args.id)]), indent=2))
    return 0


def _cmd_native(args):
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    from Fujin.effectcatalog import EffectCatalog
    from Fujin.nativeresources import NativeResourceStore
    catalog = EffectCatalog()
    cameras = CameraEffectManager(GameData("FF8GameData"))
    cameras.load_exe(args.input)
    native = NativeResourceStore(catalog.native)
    native.load(Path(args.input).read_bytes(), cameras.language_name)
    if args.parameter:
        entry = native.entries.get(args.parameter)
        if entry is None or entry["kind"] != "camera_parameter":
            raise ValueError("Unknown native camera parameter; use native without --parameter to list them")
        manager = native.managers.get(args.parameter)
        if manager is None:
            raise ValueError(native.unavailable[args.parameter])
        if args.value is None or not args.output:
            raise ValueError("Editing requires --value and --output (Hext destination)")
        field = manager.document.fields_for(manager.document.sections[0])[0]
        manager.set_field(field, args.value)
        text = cameras.hext_text().replace("#Fujin camera effect patch", "#Fujin battle effect patch", 1)
        Path(args.output).write_text(text+"\n"+"\n".join(native.hext_lines()), encoding="utf-8")
        print(f"[ok] {entry['label']} = {args.value}; patch written to {args.output}")
    else:
        for key, entry in native.entries.items():
            if args.effect is not None and args.effect not in entry["effect_ids"]:
                continue
            state = "available" if key in native.managers else native.unavailable[key]
            print(f"{key}: {entry['kind']}, {entry['address']}, {entry['size']} bytes; {state}")
    return 0


class FujinCliTool(BaseCliTool):
    """Effect source catalog, native resources, MAG sections and cinematic scripts."""

    @property
    def name(self) -> str:
        return "fujin"

    @property
    def description(self) -> str:
        return "Battle effects: inspect sources, edit native camera constants, edit MAG sections and cinematic scripts"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="ff8-cli fujin", description=self.description)
        sub = parser.add_subparsers(dest="command", required=True)

        effect = sub.add_parser("effect", help="List sources and provenance for an effect as JSON")
        effect.add_argument("--id", required=True, type=int)
        effect.set_defaults(func=_cmd_effect)
        native = sub.add_parser("native", help="Inspect embedded assets or export a native camera constant edit as Hext")
        native.add_argument("--input", "-i", required=True, help="2013 Steam FF8 executable")
        native.add_argument("--effect", type=int, help="Filter the resource list by effect ID")
        native.add_argument("--parameter", help="Native camera parameter ID from the resource list")
        native.add_argument("--value", type=_int, help="New signed integer value")
        native.add_argument("--output", "-o", help="Hext output path (the executable is never overwritten)")
        native.set_defaults(func=_cmd_native)

        p_info = sub.add_parser("info", help="Header, script region and resources")
        _add_input(p_info)
        p_info.set_defaults(func=_cmd_info)

        p_section = sub.add_parser("section", help="Export or replace one section, preserving byte size")
        _add_input(p_section)
        p_section.add_argument("--at", required=True, help="Section start offset from info (e.g. 0x870)")
        action = p_section.add_mutually_exclusive_group(required=True)
        action.add_argument("--export", help="Destination for the section bytes")
        action.add_argument("--replace", help="File containing the replacement section bytes")
        p_section.add_argument("--output", "-o", help="Destination for the edited MAG file (default: input)")
        p_section.set_defaults(func=_cmd_section)

        p_dis = sub.add_parser("disasm", help="Disassemble the reachable scripts")
        _add_input(p_dis)
        p_dis.add_argument("--linear", help="Disassemble straight from this offset instead (e.g. 0x1CDC)")
        p_dis.add_argument("--count", type=int, default=64, help="Words to cover with --linear")
        p_dis.add_argument("--explain", "-x", action="store_true", help="Append each opcode's meaning")
        p_dis.set_defaults(func=_cmd_disasm)

        p_time = sub.add_parser("timeline", help="Simulate the scripts: bone lifetimes and events")
        _add_input(p_time)
        p_time.add_argument("--seed", type=int, default=0, help="Seed of the random opcodes")
        p_time.add_argument("--targets", type=int, default=1, help="Number of targets")
        p_time.add_argument("--categories", help="Comma list (camera,sound,draw,model,particle,node,file,flag,freeze,light,fog)")
        p_time.add_argument("--max-events", type=int, default=8, help="Events printed per bone")
        p_time.set_defaults(func=_cmd_timeline)

        p_ops = sub.add_parser("opcodes", help="Print the decoded instruction set")
        p_ops.add_argument("--all", action="store_true", help="Include the unimplemented opcodes")
        p_ops.add_argument("--verbose", "-v", action="store_true", help="Print each opcode's meaning")
        p_ops.set_defaults(func=_cmd_opcodes)

        p_patch = sub.add_parser("patch", help="Rewrite one instruction in place (same length)")
        _add_input(p_patch)
        p_patch.add_argument("--at", required=True, help="Offset of the instruction (e.g. 0x1C0)")
        p_patch.add_argument("--op", help="New opcode word (opcode | modifier << 9); default: unchanged")
        p_patch.add_argument("--words", help="Comma list of operand words; default: unchanged")
        p_patch.add_argument("--output", "-o", help="Destination (default: overwrite the input)")
        p_patch.set_defaults(func=_cmd_patch)
        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except (OSError, ValueError, struct.error) as error:
            print(f"[error] {error}")
            return 1
