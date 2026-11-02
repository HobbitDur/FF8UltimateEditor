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
lists its "node" fields: a plain node (Hypnotize's, Antidote's), the fields laid out in that order
after the engine's node header, its "end" a condition checked after its counter, then its "at_end"
actions. Its spawns can come "every" n ticks of their window, its draws can be prim layouts. The
director is "per_action" (the heal ring's) or "master" (Hypnotize's, Antidote's: it starts one task
at its start tick - with the targets of action 0, or at an anchor on target 0 - alternates the
"magic_buffer" arenas, runs its own "events" on its counter after its queues ("events_first":
before) and, with "camera_matrix", keeps a camera matrix of its own (memory camera_matrix, every
tick: Echo Screen's)). An effect with no "camera" resource starts no camera track.

The memory an effect works in is its exe copy's ("copy": "memory", addresses) or its own
("own_memory": name: size in bytes, allocated by the runtime), its pools' queues and storage then
allocated too ("own": true). A new effect has its own.

The data an effect reads (sprite sequences, sound blocks, prim layouts and their tables, its
texture file name, its camera track) is named by "@key": in the exe ("exe_data": key: address,
size, kind) or in the program itself ("data": key: its bytes as "hex", or "pointers": a table of
other keys' addresses). A new effect made with the exe at hand copies its exe data into "data":
its program no longer reads the exe's.
"""
import json
from pathlib import Path

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

DESCRIPTIONS = Path(RESOURCES_JSON_FOLDER) / "effects"
FLAGS = {"spawning": 2, "overlay": 8}
# the operations of each kind the runner knows (fxprogram.h OPS) and how many arguments they take
ACTIONS = {"follow_target": 0, "spawn": 1, "heal": 0, "done": 0, "spawning": 1, "overlay": 1, "sequence": 1, "flipbook": 2,
           "helix_start": 7, "overlay_start": 4, "hide_target": 0, "show_target": 0, "unblock_director": 0,
           "velocity_roll": 6, "velocity_rise": 2, "drift": 0, "sound_at": 3, "heal_all_at": 1, "heal_first_target": 0}
CONDITIONS = {"tick_at_least": 1, "flipbook_end": 0, "layout_end": 0}
# the master director's own events (on its counter, after its queues: "events"; before: "events_first")
DIRECTOR_EVENTS = {"sound_at": 3}
MOTIONS = {"helix": 2}
PLACES = {"at_parent": 0, "circle_drop": 8, "glint": 13, "table_point": 3, "random_target_bone": 6,
          "random_target_point": 7, "action_targets": 1, "target_anchor": 7}
DRAWS = {"sprite": 4, "ground_flipbook": 6, "projector_overlay": 7, "layout_on_screen": 5, "layout_at_caster_bone": 1,
         "layout_scaled": 1, "sequence_sprite": 3, "layout_at_anchor": 2}
# a plain node's fields and their sizes (a layout's is given: ["layout", size])
FIELDS = {"counter": 2, "pos": 6, "scale": 2, "point": 8, "targets": 14, "anchor": 8}
NODE_HEADER = 0xC
TASK_QUEUE = 0x10
# what each named memory holds (fxprogram.h), in bytes: a word, an engine task queue, the root pool
# (the director's kind), the projector overlay's context (fx_overlay.h OverlayCtx), its model draw
# descriptor and its vertex buffer (Cure's room for them)
MEMORY_SIZES = {"root_queue": TASK_QUEUE, "overlay_ctx": 0xF8, "overlay_sprite": 0x40, "overlay_verts": 0x6400,
                "camera_matrix": 0x20}
ROOT_POOL = {"per_action": 2 * 0x64, "master": 0x14}


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


IMAGE_BASE = 0x400000


def _entries(table):
    """The entries of an exe_data / data table (its "doc" left out)."""
    return {key: entry for key, entry in (table or {}).items() if isinstance(entry, dict)}


def data_origin(description, key):
    """The exe address `@key` stands for (its exe data, or where its own data was copied from), or None."""
    entry = _entries(description.get("exe_data")).get(key) or _entries(description.get("data")).get(key) or {}
    address = entry.get("address", entry.get("from"))
    return _number(address) if address is not None else None


def compile_program(description, values=None):
    """The program text of `description` (a dict), its parameters at `values` (key: value, the
    others at the game's); DescriptionError says what is wrong."""
    values = values or {}
    params = {param["key"]: index for index, param in enumerate(description["params"])}
    tasks = {task["key"]: index for index, task in enumerate(description["tasks"])}
    pools = {pool["key"]: index for index, pool in enumerate(description["pools"])}
    parts = {part["key"]: part["id"] for part in description["parts"]}

    exe_data, own_data = _entries(description.get("exe_data")), _entries(description.get("data"))

    def value(item, where):
        if isinstance(item, str) and item.startswith("$"):
            if item[1:] not in params:
                raise DescriptionError(f"{where}: no parameter {item[1:]}")
            return f"${params[item[1:]]}"
        if isinstance(item, str) and item.startswith("@"):
            key = item[1:]
            if key in own_data:
                return f"@{key}"
            if key in exe_data:
                return str(_number(exe_data[key]["address"]))
            raise DescriptionError(f"{where}: no data {key}")
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
    # its own data first: the lines below name it (@key); tables of pointers after what they point at
    for key, entry in own_data.items():
        if " " in key:
            raise DescriptionError(f"data {key}: a key without spaces")
        if "pointers" not in entry:
            try:
                data = bytes.fromhex(entry["hex"])
            except (KeyError, ValueError):
                raise DescriptionError(f"data {key}: its bytes as \"hex\"") from None
            lines.append(f"data {key} {data.hex()}")
    for key, entry in own_data.items():
        if "pointers" in entry:
            missing = [item for item in entry["pointers"] if item not in own_data or "pointers" in own_data[item]]
            if missing:
                raise DescriptionError(f"data {key}: points at no data {', '.join(missing)}")
            lines.append(f"data_pointers {key} {' '.join(entry['pointers'])}")
    for name, address in (copy.get("functions") or {}).items():
        lines.append(f"function {name} 0x{_number(address):X}")
    for name, address in (copy.get("memory") or {}).items():
        lines.append(f"memory {name} 0x{_number(address):X}")
    for name, size in (description.get("own_memory") or {}).items():
        if _number(size) <= 0:
            raise DescriptionError(f"own memory {name}: a size in bytes")
        lines.append(f"own {name} {_number(size)}")
    texture = description["resources"]["texture"]
    lines.append(f"texture {value(texture['game_name'], 'texture')} {params.get(texture.get('param'), -1)}")
    camera = description["resources"].get("camera")         # none: the effect starts no camera track
    lines.append(f"camera {value(camera, 'camera') if camera is not None else 0}")
    for pool in description["pools"]:
        own, in_buffer = pool.get("own"), pool.get("in_magic_buffer")
        queue = "own" if own else f"0x{_number(pool['queue']):X}"
        storage = "own" if own and not in_buffer else f"0x{_number(pool['storage']):X}"
        lines.append(f"pool {queue} {storage} {pool['size']} {pool['count']} "
                     f"{parts[pool['part']] if pool.get('part') else -1} {1 if in_buffer else 0}")
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
        lines += [f"director_event_first {step(entry, DIRECTOR_EVENTS, 'director')}"
                  for entry in director.get("events_first", [])]
        lines += [f"director_event {step(entry, DIRECTOR_EVENTS, 'director')}" for entry in director.get("events", [])]
        if director.get("camera_matrix"):
            lines.append("camera_matrix")
    else:
        lines.append(f"director per_action {tasks[director['spawns']]}")
    for param in description["params"]:
        current = values.get(param["key"], param["default"])
        where = f"parameter {param['key']}"
        if param["type"] == "file":
            if " " in str(current or ""):
                raise DescriptionError(f"{where}: a file name without spaces")
            lines.append(f"param {param['key']} file {current or '-'} -")
        else:
            lines.append(f"param {param['key']} {param['type']} {value(current, where)} {value(param['default'], where)}")
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
        lines += [f"at_end {action(entry, where)}" for entry in task.get("at_end", [])]
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


def write_program(description, path, values=None):
    Path(path).write_text(compile_program(description, values), encoding="ascii")
    return path


# the game folder's folder FujinEffects.dll reads the programs from (its own: FFNx reads none of it)
PROGRAM_FOLDER = "FujinEffects"


def program_file_name(effect_id):
    """The file name FujinEffects.dll reads an effect's program from (in PROGRAM_FOLDER)."""
    return f"effect_{effect_id:03d}.fxprog"


# the dispatch slots the game leaves empty (Magic_GetIDLoad 0x50AF20 falls back to effect 0 there):
# effect ids a new effect can take
FREE_EFFECTS = (224, 225) + tuple(range(346, 401))


def described_effects():
    """The effect ids Fujin ships a description of."""
    return sorted(int(path.stem.split("_")[1]) for path in DESCRIPTIONS.glob("effect_*.json"))


def own_memory(description):
    """{name: size} of memory of its own for each memory `description` names in its exe copy."""
    kind = description["director"].get("kind", "per_action")
    names = (description.get("copy") or {}).get("memory") or description.get("own_memory") or {}
    return {name: ROOT_POOL[kind] if name == "root_pool" else MEMORY_SIZES.get(name, 4) for name in names}


def own_data(description, exe):
    """{key: entry} of `description`'s exe data copied out of `exe` (FF8_EN.exe's bytes)."""
    data = {}
    for key, entry in _entries(description.get("exe_data")).items():
        address = _number(entry["address"])
        if entry.get("kind") == "pointers":
            data[key] = {"kind": "pointers", "from": entry["address"], "pointers": list(entry["items"])}
            continue
        start = address - IMAGE_BASE
        if not 0 <= start <= len(exe) - entry["size"]:
            raise DescriptionError(f"exe data {key}: 0x{address:X} is not in this exe")
        data[key] = {"kind": entry["kind"], "from": entry["address"], "hex": exe[start:start + entry["size"]].hex()}
    return data


def new_effect(description, effect_id, name, exe=None):
    """A new effect (a copy of `description` as effect `effect_id`): it runs by itself, standing in
    for no exe function, in memory of its own (its pools too). With `exe` (FF8_EN.exe's bytes) its
    exe data (flipbooks, sounds, layouts, camera...) is copied into its program; without, it reads
    the exe's. It keeps the files of the effect it is made from ("base")."""
    new = json.loads(json.dumps(description))
    if exe is not None and "exe_data" in new:
        new["data"] = {"doc": "The effect's own data (@key in its values), copied from the exe's (\"from\").",
                       **own_data(description, exe)}
        del new["exe_data"]
    new["base"] = description.get("base", description["effect"])
    new["effect"], new["name"] = effect_id, name
    new["own_memory"] = own_memory(description)
    new.pop("copy", None)
    for pool in new["pools"]:
        pool["own"] = True
        pool.pop("queue", None)
        if not pool.get("in_magic_buffer"):
            pool.pop("storage", None)
    for task in new["tasks"]:
        task.pop("function", None)
    return new


def description_schema(description):
    """A description's parameter table in the shape of the recorder's schema (Choreography's part
    tabs): its parts, fields (numbers as numbers: a description keeps sequences and sounds as "0x..."
    text) and groups."""
    def default(param):
        if isinstance(param["default"], str) and param["default"].startswith("@"):
            return data_origin(description, param["default"][1:]) or 0       # the exe's copy of its data
        return _number(param["default"])
    fields = [param if param["type"] == "file" else dict(param, default=default(param))
              for param in description["params"]]
    return {"effect": description["effect"], "name": description["name"], "parts": description["parts"],
            "fields": fields, "groups": description.get("groups", [])}


# ---- the effect file: one per effect (PROGRAM_FOLDER/effect_NNN.fxprog), the game's and Fujin's
SOURCE = "#source "


def effect_file_text(description, values=None, edited=False):
    """The text of an effect's file: its program (what FujinEffects.dll runs, the parameters at
    `values`), then one comment line the DLL skips, SOURCE + JSON, what Fujin reopens it from: the
    edited values and, when `edited` (an edited description or a new effect), the description -
    its own data's bytes left out (they are the program's data lines)."""
    values = dict(sorted((values or {}).items()))
    source = {"format": 1, "effect": description["effect"], "values": values}
    if edited:
        kept = json.loads(json.dumps(description))
        for entry in _entries(kept.get("data")).values():
            entry.pop("hex", None)
        source["description"] = kept
    try:
        program = compile_program(description, values)
    except (DescriptionError, KeyError, TypeError, ValueError) as error:
        # not complete yet (an effect built part by part with no start): kept for Fujin, the DLL
        # finds no program in it and leaves the slot alone
        program = f"# incomplete: {str(error).splitlines()[0] if str(error) else type(error).__name__}\n"
    return program + SOURCE + json.dumps(source, separators=(",", ":")) + "\n"


def read_effect_file(text):
    """(effect id, its description when the file holds one else None, its values) of an effect
    file's text; ValueError when it is not one."""
    line = next((line for line in text.splitlines() if line.startswith(SOURCE)), None)
    if line is None:
        raise ValueError("not an effect file of Fujin's (no #source line)")
    source = json.loads(line[len(SOURCE):])
    description = source.get("description")
    if description is not None:
        data = {}
        for program_line in text.splitlines():
            if program_line.startswith("data "):
                _directive, key, hex_text = program_line.split(" ", 2)
                data[key] = hex_text.strip()
        for key, entry in _entries(description.get("data")).items():
            if "pointers" not in entry:
                if key not in data:
                    raise ValueError(f"its data {key} is missing")
                entry["hex"] = data[key]
    values = {str(key): value if isinstance(value, str) else int(value) for key, value in source.get("values", {}).items()}
    return int(source["effect"]), description, values
