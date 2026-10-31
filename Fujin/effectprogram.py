"""Effect descriptions compiled into programs (docs/fujin-effect-description.md).

A description (FF8GameData/Resources/json/effects/effect_NNN.json) says an effect as data: its
parameters (with the game's values), its parts, the tasks that run it - each one's phases, motion,
spawns, events and draws, every one a piece of FFNx's parts library - and, for an effect of the
exe, where its copy lives (the functions it stands in for, its memory). compile_program() turns it
into the program the C++ runner reads (Tools/fxhost/fxprogram.h, in the recorder: program=<file>):
one directive per line, names resolved to indices ($n: parameter n), values as numbers.

In a description, a value is a number (or "0x..." text) or "$key", a parameter; a task, a pool or
a part is named by its key; a spawn's or a draw's "if" names a flag of the node ("spawning",
"overlay").

A task's node is the effect library's (the heal ring's: phases, motion, flags) unless the task
lists its "node" fields: a plain node (Hypnotize's), the fields laid out in that order after the
engine's node header, its "end" a condition checked after its counter. Its spawns can come
"every" n ticks of their window, its draws can be prim layouts. The director is "per_action" (the
heal ring's) or "master" (Hypnotize's: it starts one task at its start tick, with the targets of
action 0, and alternates the "magic_buffer" arenas).
"""
import json
from pathlib import Path

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

DESCRIPTIONS = Path(RESOURCES_JSON_FOLDER) / "effects"
FLAGS = {"spawning": 2, "overlay": 8}
# the operations of each kind the runner knows (fxprogram.h OPS) and how many arguments they take
ACTIONS = {"follow_target": 0, "spawn": 1, "heal": 0, "done": 0, "spawning": 1, "overlay": 1, "sequence": 1, "flipbook": 2,
           "helix_start": 7, "overlay_start": 4, "hide_target": 0, "show_target": 0, "unblock_director": 0,
           "velocity_roll": 6, "velocity_rise": 2, "drift": 0, "sound_at": 3, "heal_all_at": 1}
CONDITIONS = {"tick_at_least": 1, "flipbook_end": 0, "layout_end": 0}
MOTIONS = {"helix": 2}
PLACES = {"at_parent": 0, "circle_drop": 8, "glint": 13, "table_point": 3, "random_target_bone": 6,
          "random_target_point": 7, "action_targets": 1}
DRAWS = {"sprite": 4, "ground_flipbook": 6, "projector_overlay": 7, "layout_on_screen": 5, "layout_at_caster_bone": 1,
         "layout_scaled": 1, "sequence_sprite": 3}
# a plain node's fields and their sizes (a layout's is given: ["layout", size])
FIELDS = {"counter": 2, "pos": 6, "scale": 2, "point": 8, "targets": 14}
NODE_HEADER = 0xC


class DescriptionError(ValueError):
    pass


def description_path(effect_id):
    return DESCRIPTIONS / f"effect_{effect_id:03d}.json"


def load_description(effect_id):
    """The description of effect `effect_id` shipped with Fujin, or None."""
    path = description_path(effect_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def compile_program(description):
    """The program text of `description` (a dict); DescriptionError says what is wrong."""
    params = {param["key"]: index for index, param in enumerate(description["params"])}
    tasks = {task["key"]: index for index, task in enumerate(description["tasks"])}
    pools = {pool["key"]: index for index, pool in enumerate(description["pools"])}
    parts = {part["key"]: part["id"] for part in description["parts"]}

    def value(item, where):
        if isinstance(item, str) and item.startswith("$"):
            if item[1:] not in params:
                raise DescriptionError(f"{where}: no parameter {item[1:]}")
            return f"${params[item[1:]]}"
        try:
            return str(_number(item))
        except (TypeError, ValueError):
            raise DescriptionError(f"{where}: {item!r} is not a value") from None

    def step(entry, known, where, names=()):
        """An operation and its values; the arguments at `names` positions are a task / pool name."""
        operation, *arguments = entry
        if operation not in known:
            raise DescriptionError(f"{where}: unknown operation {operation}")
        if len(arguments) != known[operation]:
            raise DescriptionError(f"{where}: {operation} takes {known[operation]} values, not {len(arguments)}")
        out = [operation]
        for position, argument in enumerate(arguments):
            table = dict(names).get(position)
            if table is not None:
                if argument not in table:
                    raise DescriptionError(f"{where}: {operation} names no {argument}")
                out.append(str(table[argument]))
            else:
                out.append(value(argument, where))
        return " ".join(out)

    def action(entry, where):
        return step(entry, ACTIONS, where, names={0: tasks} if entry[0] == "spawn" else ())

    def flag(name, where):
        if name is None:
            return 0
        if name not in FLAGS:
            raise DescriptionError(f"{where}: no flag {name}")
        return FLAGS[name]

    def node(task, where):
        """A plain node's fields, laid out in their order after the node header."""
        if task.get("phases") or task.get("every_tick") or task.get("motion") or task.get("step_spawns"):
            raise DescriptionError(f"{where}: a plain node has no phases, every-tick actions or motion")
        out, offset = ["node plain"], NODE_HEADER
        for item in task["node"]:
            name, size = (item[0], _number(item[1])) if isinstance(item, list) else (item, FIELDS.get(item))
            if name not in FIELDS and name != "layout" or size is None:
                raise DescriptionError(f"{where}: no node field {name}")
            out.append(f"field {name} {offset} {size}")
            offset += size
        if offset > task["size"]:
            raise DescriptionError(f"{where}: its fields take {offset:#x} bytes, the node {task['size']:#x}")
        return out

    copy = description.get("copy") or {}
    lines = [f"# effect program, compiled by Fujin/effectprogram.py from effect_{description['effect']:03d}.json",
             f"program {description['effect']} {description['name'].replace(' ', '_')}"]
    for name, address in (copy.get("functions") or {}).items():
        lines.append(f"function {name} 0x{_number(address):X}")
    for name, address in (copy.get("memory") or {}).items():
        lines.append(f"memory {name} 0x{_number(address):X}")
    texture = description["resources"]["texture"]
    lines.append(f"texture 0x{_number(texture['game_name']):X} {params.get(texture.get('param'), -1)}")
    lines.append(f"camera 0x{_number(description['resources']['camera']):X}")
    for pool in description["pools"]:
        lines.append(f"pool 0x{_number(pool['queue']):X} 0x{_number(pool['storage']):X} {pool['size']} {pool['count']} "
                     f"{parts[pool['part']] if pool.get('part') else -1} {1 if pool.get('in_magic_buffer') else 0}")
    if "magic_buffer" in description:
        buffer = description["magic_buffer"]
        arena_a, arena_b = buffer["arenas"]
        lines.append(f"magic_buffer 0x{_number(arena_a):X} 0x{_number(arena_b):X} 0x{_number(buffer['morph']):X}")
    director = description["director"]
    if director.get("kind") not in ("per_action", "master") or director.get("spawns") not in tasks:
        raise DescriptionError("director: a per_action or master director spawning one of the tasks")
    if director["kind"] == "master":
        lines.append(f"director master {tasks[director['spawns']]} {_number(director.get('start_tick', 1))} "
                     f"{step(director['place'], PLACES, 'director')}")
    else:
        lines.append(f"director per_action {tasks[director['spawns']]}")
    for param in description["params"]:
        if param["type"] == "file":
            lines.append(f"param {param['key']} file {param['default'] or '-'} -")
        else:
            lines.append(f"param {param['key']} {param['type']} {_number(param['default'])} {_number(param['default'])}")
    for task in description["tasks"]:
        where = f"task {task['key']}"
        if task["pool"] not in pools:
            raise DescriptionError(f"{where}: no pool {task['pool']}")
        lines.append(f"task {task['key']} {pools[task['pool']]} 0x{_number(task.get('function', 0)):X} {task['size']}")
        if "node" in task:
            lines += node(task, where)
        if task.get("draws_first"):
            lines.append("order draws_first")
        if task.get("end"):
            lines.append(f"end {step(task['end'], CONDITIONS, where)}")
        lines += [f"tick {action(entry, where)}" for entry in task.get("every_tick", [])]
        for number, phase in enumerate(task.get("phases", [])):
            here = f"{where} phase {number}"
            lines.append("phase")
            lines += [f"phase_tick {action(entry, here)}" for entry in phase.get("each_tick", [])]
            if phase.get("wait"):
                lines.append(f"wait {step(phase['wait'], CONDITIONS, here)}")
            lines += [f"do {action(entry, here)}" for entry in phase.get("do", [])]
        if task.get("motion"):
            lines.append(f"motion {step(task['motion'], MOTIONS, where)}")
        for spawn in task.get("step_spawns", []):
            first, last = (value(item, where) for item in spawn["window"])
            lines.append(f"step_spawn {tasks[spawn['task']]} {flag(spawn.get('if'), where)} {first} {last} "
                         f"{step(spawn.get('place', ['at_parent']), PLACES, where)}")
        for spawn in task.get("spawns", []):
            target = tasks.get(spawn.get("task"), -1)
            first, last = (value(item, where) for item in spawn["window"])
            if "every" in spawn:
                if target < 0:
                    raise DescriptionError(f"{where}: a spawn every n ticks of no task")
                lines.append(f"spawn_every {target} {first} {last} {value(spawn['every'], where)} "
                             f"{step(spawn['place'], PLACES, where)}")
                continue
            count = [value(item, where) for item in spawn["count"]]
            if len(count) != 8:
                raise DescriptionError(f"{where}: a spawn count is 4 (from tick, how many) pairs")
            place = step(spawn["place"], PLACES, where, names={0: pools} if spawn["place"][0] == "glint" else ())
            lines.append(f"spawn {target} {flag(spawn.get('if'), where)} {first} {last} {' '.join(count)} {place}")
        lines += [f"event {action(entry, where)}" for entry in task.get("events", [])]
        for draw in task.get("draws", []):
            limit = "-", "-"
            if "while_tick_below" in draw:
                limit = "below", value(draw["while_tick_below"], where)
            elif "while_tick_at_most" in draw:
                limit = "at_most", value(draw["while_tick_at_most"], where)
            lines.append(f"draw {parts.get(draw.get('part'), 0)} {flag(draw.get('if'), where)} {limit[0]} {limit[1]} "
                         f"{step(draw['draw'], DRAWS, where)}")
    return "\n".join(lines) + "\n"


def write_program(description, path):
    Path(path).write_text(compile_program(description), encoding="ascii")
    return path
