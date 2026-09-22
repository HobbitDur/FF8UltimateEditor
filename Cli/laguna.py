"""Laguna - GF cinematic script (MAGxxx_B.00) CLI tool.

The seven summons sharing Ifrit's engine (Ifrit MAG200, Leviathan MAG005, Bahamut MAG201,
Cerberus MAG202, Alexander MAG203, Brothers MAG204, Eden MAG205) keep their choreography as byte
code in their .00 mag file.

Commands:
    • info      - header, script region, reachable instructions, resources
    • disasm    - disassemble the reachable scripts (or --linear from an offset)
    • timeline  - simulate the scripts tick by tick: bone spawns/deaths and notable events
    • opcodes   - print the decoded instruction set
    • patch     - rewrite one instruction in place (same length): --at 0x1C0 --op 0x0409 --words 1,2
"""
import argparse
import os

from .base import BaseCliTool


def _load(args):
    from Laguna.lagunamanager import LagunaManager
    manager = LagunaManager()
    manager.load_file(args.input)
    return manager


def _int(text):
    return int(text, 0)


def _cmd_info(args) -> int:
    from FF8GameData.magcine.magcontainer import MagContainer, HEADER_FIELDS
    manager = _load(args)
    program = manager.program
    print(f"{os.path.basename(args.input)} - GF {manager.gf or '(unknown: not a vanilla file name)'}")
    container = MagContainer(bytes(manager.data))
    for offset, label in HEADER_FIELDS:
        value = container.header[offset // 4]
        print(f"  header +{offset:02X} {label:28} {f'0x{value:X}' if value else '-'}")
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
    parser.add_argument("--input", "-i", required=True, help="Path to MAGxxx_B.00")


class LagunaCliTool(BaseCliTool):
    """GF cinematic script editor (Ifrit/Leviathan/Bahamut/Cerberus/Alexander/Brothers/Eden)."""

    @property
    def name(self) -> str:
        return "laguna"

    @property
    def description(self) -> str:
        return ("GF cinematic script editor (MAGxxx_B.00 of Ifrit, Leviathan, Bahamut, Cerberus, "
                "Alexander, Brothers, Eden): disassemble, simulate, patch")

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="ff8-cli laguna", description=self.description)
        sub = parser.add_subparsers(dest="command", required=True)

        p_info = sub.add_parser("info", help="Header, script region and resources")
        _add_input(p_info)
        p_info.set_defaults(func=_cmd_info)

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
        except (OSError, ValueError) as error:
            print(f"[error] {error}")
            return 1
