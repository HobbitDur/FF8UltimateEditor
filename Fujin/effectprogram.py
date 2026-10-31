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
"""
import json
from pathlib import Path

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

DESCRIPTIONS = Path(RESOURCES_JSON_FOLDER) / "effects"
FLAGS = {"spawning": 2, "overlay": 8}
# the operations of each kind the runner knows (fxprogram.h OPS) and how many arguments they take
ACTIONS = {"follow_target": 0, "spawn": 1, "heal": 0, "done": 0, "spawning": 1, "overlay": 1, "sequence": 1, "flipbook": 2,
           "helix_start": 7, "overlay_start": 4, "hide_target": 0, "show_target": 0, "unblock_director": 0,
           "velocity_roll": 6, "velocity_rise": 2, "drift": 0, "sound_at": 3}
CONDITIONS = {"tick_at_least": 1, "flipbook_end": 0}
MOTIONS = {"helix": 2}
PLACES = {"at_parent": 0, "circle_drop": 8, "glint": 13}
DRAWS = {"sprite": 4, "ground_flipbook": 6, "projector_overlay": 7}


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
                     f"{parts[pool['part']] if pool.get('part') else -1}")
    director = description["director"]
    if director.get("kind") != "per_action" or director.get("spawns") not in tasks:
        raise DescriptionError("director: a per_action director spawning one of the tasks")
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
            count = [value(item, where) for item in spawn["count"]]
            if len(count) != 8:
                raise DescriptionError(f"{where}: a spawn count is 4 (from tick, how many) pairs")
            place = step(spawn["place"], PLACES, where, names={0: pools} if spawn["place"][0] == "glint" else ())
            lines.append(f"spawn {target} {flag(spawn.get('if'), where)} {first} {last} {' '.join(count)} {place}")
        lines += [f"event {action(entry, where)}" for entry in task.get("events", [])]
        for draw in task.get("draws", []):
            below = value(draw["while_tick_below"], where) if "while_tick_below" in draw else "-"
            lines.append(f"draw {parts.get(draw.get('part'), 0)} {flag(draw.get('if'), where)} {below} "
                         f"{step(draw['draw'], DRAWS, where)}")
    return "\n".join(lines) + "\n"


def write_program(description, path):
    Path(path).write_text(compile_program(description), encoding="ascii")
    return path
