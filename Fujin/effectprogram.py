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
tick: Echo Screen's)) or "cycle" (Silence's: every "every" ticks it starts one task for the next
action, on its target; its "events" too, every tick: Blind's screen flash; "setup": "master", set
up as the master is: Petrify Stare's) or "chain" (Fire's: one director task per action, each
starting the next one's - "spawns" when the action has several targets, "single" when one - the
root alternating "packet_arena_a" / "packet_arena_b" by its counter). An effect with no "camera"
resource starts no camera track; a texture "tim" (data) is uploaded as it is, no file loaded
(Thunder's). A task's "draw_only" says what it does while the battle only draws
("skip": nothing, "after_draws": its first draws only), its "hold" stops its tick early (Fire's
lone target's director waits until its target is free). The heal ring's director can be "root":
"short" (Double's: four phases, its packet arenas memory words set in the magic buffer; "upload":
"always", Phoenix Down's: its texture uploaded even when the cast repeats, no camera).

A task can name node variables (Double's): an effect node's header fields (pos, counter, flags,
phase) and its "body" ([name, type, count] laid out from 0x30: i16, i32, u8, grey - three colour
bytes as one -, u16, i8), "emitter.name" (its emitter's), "child.name" (the node the last spawning
action, or the spawn whose "init" this is, made), "name.k" (element k); "-$key" is a parameter
negated. Its "after_phase" actions run after its phase, before its draws and spawns; a draw's
"when" is a condition on the node.

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
           "velocity_roll": 6, "velocity_rise": 2, "drift": 0, "sound_at": 3, "heal_all_at": 1, "heal_first_target": 0,
           "anchor_at_bone": 1, "sound_3d_at": 3, "heal_action_at": 1, "unmark_target": 1, "anchor_at_position": 0,
           "heal_action": 0, "screen_fade_at": 5, "blink_target": 2, "screen_flash_curve": 4, "screen_flash_off": 0,
           "spin": 0, "whirl_leaf_move": 2, "flash_level_raise": 5, "follow_bone": 3, "sound_3d_at_position": 4,
           "point_at_position": 1, "mark_ring_from": 2, "unmark_ring": 1, "flash_level_hold": 6,
           "flash_level_set": 2, "mark_target": 1, "tint_target": 7, "spark_step": 2, "spark_move": 0,
           "barrier_frame": 1, "barrier_center": 3, "dead_beams": 3, "orbit_move": 0, "growth_step": 1,
           "spawn_to_feet": 1, "ray_spawn": 11, "mote_step": 2, "chain_next": 1, "release_target": 0,
           "heal_action_all_at": 1, "sound_pan_at": 4, "ember_rise": 2, "fire_spark_move": 2,
           "spawn_size_word": 3, "sound_3d_at_spawn": 3,
           "add": 2, "set": 2, "copy": 3, "flags": 2, "set_when": 4, "add_when": 4, "add_below": 3, "add_var": 2,
           "spin_var": 3, "circle_place": 4, "circle_place_var": 4, "anchor_xz": 2, "anchor_top": 1, "rand_mask": 3,
           "rand_hop": 3, "index_times": 2, "tick_times": 3, "turned_offset": 5, "fade_pulse": 9, "grey_pulse": 5,
           "morph": 4, "spawn_when": 3, "spawn_unless_target_bits": 2, "screen_fade_when": 6, "wrap": 2,
           "revive_ring_step": 2, "actor_setup": 0, "actor_step": 0, "stage_clear": 0, "stage_fade": 3, "call": 1}
CONDITIONS = {"tick_at_least": 1, "flipbook_end": 0, "layout_end": 0, "tick_above": 1, "tick_at_node_end": 0, "leaf_gone": 0, "spark_gone": 0, "rays_done": 1, "ribbon_done": 1,
              "mote_done": 1, "life_out": 0, "at_most": 2, "at_least": 2, "equals": 2, "never": 0, "at_least_var": 2,
              "at_least_when": 4, "equals_when": 4, "above": 2, "actor_done": 0}
# a task's hold (after its every-tick actions: when it holds, its tick stops there)
HOLDS = {"claim_target": 0}
DRAW_ONLY = ("skip", "after_draws")
# the master director's own events (on its counter, after its queues: "events"; before: "events_first")
DIRECTOR_EVENTS = {"sound_at": 3, "flash_level_clear": 0, "screen_flash_level": 0}
MOTIONS = {"helix": 2}
PLACES = {"at_parent": 0, "circle_drop": 8, "glint": 13, "table_point": 3, "random_target_bone": 6,
          "random_target_point": 7, "action_targets": 1, "target_anchor": 7, "action_target": 8, "random_around": 4,
          "rising_circle": 5, "spinning_ring": 10, "whirl_leaf": 5, "collapse_sparks": 6, "orbit_spawn": 6,
          "growth_spawn": 7, "ribbon_start": 3, "ember_ring": 9, "spark_near": 4,
          "flames_on_targets": 11, "flame_embers": 9, "flame_sparks": 12,
          "revive_rising": 6, "revive_at": 3, "revive_scatter": 3, "revive_ring": 5, "revive_fall": 7}
DRAWS = {"sprite": 4, "ground_flipbook": 6, "projector_overlay": 7, "layout_on_screen": 5, "layout_at_caster_bone": 1,
         "layout_scaled": 1, "sequence_sprite": 3, "layout_at_anchor": 2, "layout_on_target": 5,
         "layout_turned": 10, "node_sequence_sprite": 1,
         "layout_table": 3, "spinning_model": 6, "sequence_at_feet": 7,
         "layout_scaled_on_target": 12, "tumbling_model": 2, "layout_engine_at_anchor": 4,
         "layout_on_point": 7, "sway_overlay": 10, "ripple_silhouette": 3,
         "spark_sprite": 1, "barrier_wall": 5, "orbit_model": 5, "growth_model": 3,
         "sequence_at_anchor": 4, "pulse_model": 6, "layout_table_at_spawn": 1, "light_rays": 0, "ribbon": 6,
         "mote_sprite": 0, "flame": 8, "ember": 2, "fire_spark": 5,
         "screen_quad": 2, "point_layer": 4, "ground_layer": 4,
         "prim_model": 5, "prim_model_as": 5, "sprite_turned": 6, "ground_flipbook_colour": 5, "screen_tex_quad": 8,
         "revive_sparkle": 1, "revive_sparkle_sized": 1}
# the arguments of an operation that name a node variable (Double's): "name" (the node's own),
# "emitter.name", "child.name" (the node an action or a spawn just made), an element "name.k"
VAR_ARGS = {"add": (0,), "set": (0,), "copy": (0, 1), "set_when": (0, 2), "add_when": (0, 2), "add_below": (0,),
            "add_var": (0, 1), "spin_var": (0,), "circle_place": (0, 1), "circle_place_var": (0, 1, 2), "anchor_xz": (0,),
            "anchor_top": (0,), "rand_mask": (0,), "rand_hop": (0,), "index_times": (0,), "tick_times": (0,),
            "turned_offset": (0,), "fade_pulse": (0, 1, 2, 3), "grey_pulse": (0, 1), "morph": (3,), "spawn_when": (1,),
            "screen_fade_when": (0,), "wrap": (0, 1), "at_most": (0,), "at_least": (0,), "equals": (0,),
            "at_least_var": (0, 1), "at_least_when": (0, 2), "equals_when": (0, 2), "prim_model": (0, 1, 2, 3, 4),
            "prim_model_as": (1, 2, 3, 4), "sprite_turned": (0, 1, 2, 3, 4, 5), "ground_flipbook_colour": (4,),
            "above": (0,), "revive_sparkle": (0,), "stage_fade": (0,)}
# a node variable's type: its code (fxprogram.h VarType) and size; an effect node's header fields
VAR_TYPES = {"i16": (1, 2), "i32": (2, 4), "u8": (3, 1), "grey": (4, 4), "u16": (5, 2), "i8": (6, 1)}
HEADER_VARS = {"pos": (0x1C, "i16", 4), "counter": (0x24, "i16", 1), "flags": (0x26, "u16", 1), "phase": (0x29, "i8", 1)}
VAR_BASES = {"emitter": 1, "child": 2, "root": 3}
EFFECT_NODE_HEADER = 0x30
# a plain node's fields and their sizes (a layout's is given: ["layout", size])
FIELDS = {"counter": 2, "pos": 6, "scale": 2, "point": 8, "targets": 14, "anchor": 8, "action": 2, "entity": 4, "spawn": 8, "end": 2, "seq": 4, "radius": 2, "angle": 2, "speed": 2, "fade": 2, "leaf": 0x30, "colour": 4, "ripple": 4, "spark": 0x20, "barrier": 0x48,
          "orbit": 0x0E, "growth": 0x0E, "rays": 0x600, "ribbon": 0x412, "mote": 0x10, "drawn": 4,
          "slot": 2, "chain": 2, "delay": 2, "life": 2, "flame": 0x14, "ember": 0x14, "fire_spark": 0x14}
NODE_HEADER = 0xC
TASK_QUEUE = 0x10
# what each named memory holds (fxprogram.h), in bytes: a word, an engine task queue, the root pool
# (the director's kind), the projector overlay's context (fx_overlay.h OverlayCtx), its model draw
# descriptor and its vertex buffer (Cure's room for them)
MEMORY_SIZES = {"root_queue": TASK_QUEUE, "overlay_ctx": 0xF8, "overlay_sprite": 0x40, "overlay_verts": 0x6400,
                "camera_matrix": 0x20, "packet_arena_a": 0x10000, "packet_arena_b": 0x10000, "target_free": 7 * 4}
ROOT_POOL = {"per_action": 2 * 0x64, "master": 0x14, "cycle": 0x14, "chain": 0x10}


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
        if isinstance(item, str) and item.startswith("-$"):   # a parameter negated
            return "-" + value(item[1:], where)
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

    by_key = {task["key"]: task for task in description["tasks"]}
    body = {}

    def body_vars(key):
        """name: (offset, type, count) of task `key`'s node variables: an effect node's header
        fields, then its "body" laid out from 0x30 ([name, type, count], ["pad", n])."""
        if key not in body:
            task, out, offset = by_key[key], dict(HEADER_VARS), EFFECT_NODE_HEADER
            for item in task.get("body", []):
                if item[0] == "pad":
                    offset += _number(item[1])
                    continue
                if item[1] not in VAR_TYPES:
                    raise DescriptionError(f"task {key}: body {item[0]} is of no type {item[1]}")
                count = _number(item[2]) if len(item) > 2 else 1
                out[item[0]] = (offset, item[1], count)
                offset += VAR_TYPES[item[1]][1] * count
            if offset > task["size"]:
                raise DescriptionError(f"task {key}: its body takes {offset:#x} bytes, the node {task['size']:#x}")
            body[key] = out
        return body[key]

    class Vars:
        """The node variables an operation can name from task `own` (child: the task just spawned)."""
        def __init__(self, own, child):
            self.own, self.child = own, child

        def token(self, name):
            words = str(name).split(".")
            base, owner = 0, self.own
            if words[0] in VAR_BASES:
                base = VAR_BASES[words[0]]
                owner = {1: description["director"].get("spawns"), 2: self.child, 3: None}[base]
                words = words[1:]
            if not words or (owner is not None and owner not in by_key):
                raise KeyError(name)
            table = body_vars(owner) if owner else HEADER_VARS
            if words[0] not in table or len(words) > 2:
                raise KeyError(name)
            offset, kind, count = table[words[0]]
            index = int(words[1]) if len(words) > 1 else 0
            if not 0 <= index < count:
                raise KeyError(name)
            code, size = VAR_TYPES[kind]
            return (base << 20) | (code << 16) | (offset + index * size)

        def __contains__(self, name):
            try:
                self.token(name)
                return True
            except (KeyError, ValueError):
                return False

        def __getitem__(self, name):
            return self.token(name)

    def op(entry, known, where, own=None, child=None):
        """An operation naming tasks, pools or node variables."""
        names = {}
        if entry[0] in ("spawn", "spawn_when", "spawn_unless_target_bits"):
            names[0] = tasks
        if entry[0] == "dead_beams":
            names[2] = pools
        if own is not None:
            for position in VAR_ARGS.get(entry[0], ()):
                names[position] = Vars(own, child)
        return step(entry, known, where, names=names)

    def action(entry, where, own=None, child=None):
        return op(entry, ACTIONS, where, own, child)

    def actions(entries, prefix, where, own, child=None):
        """The lines of a list of actions; a spawning action makes its task the child of the next ones."""
        out = []
        for entry in entries:
            out.append(f"{prefix} {action(entry, where, own, child)}")
            if entry[0] in ("spawn", "spawn_when", "spawn_unless_target_bits"):
                child = entry[1]
        return out

    def flag(name, where):
        if name is None:
            return 0
        if name not in FLAGS:
            raise DescriptionError(f"{where}: no flag {name}")
        return FLAGS[name]

    def node(task, where):
        """A plain node's fields, laid out in their order after the node header."""
        if task.get("phases") or task.get("motion") or task.get("step_spawns"):
            raise DescriptionError(f"{where}: a plain node has no phases or motion")
        out, offset = ["node plain"], NODE_HEADER
        for item in task["node"]:
            name, size = (item[0], _number(item[1])) if isinstance(item, list) else (item, FIELDS.get(item))
            if name not in FIELDS and name not in ("layout", "layout_b", "pad") or size is None:
                raise DescriptionError(f"{where}: no node field {name}")
            if name != "pad":                    # ["pad", n]: n bytes the effect does not use
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
            if entry.get("kind") == "actors":   # the program moves its pointers to the copy
                lines.append(f"data_actors {key} {_number(entry['header'])} {_number(entry['body'])} {data.hex()}")
                continue
            lines.append(f"data {key} {data.hex()}")
    for key, entry in own_data.items():
        if "pointers" in entry:
            missing = [item for item in entry["pointers"] if item not in own_data or "pointers" in own_data[item]]
            if missing:
                raise DescriptionError(f"data {key}: points at no data {', '.join(missing)}")
            lines.append(f"data_pointers {key} {' '.join(entry['pointers'])}")
    module = description.get("module")
    if module:   # a port module whose code runs on the program's memory (Doom's kind)
        lines.append(f"module {_number(module['effect'])} 0x{_number(module['from']):X} 0x{_number(module['size']):X}"
                     + (" own" if module.get("own") else ""))
        lines += [f"module_pointer {_number(index)} 0x{_number(word):X}" for index, word in module.get("pointers", [])]
        for name, address in (module.get("memory") or {}).items():   # (a copy's: moved into its block)
            lines.append(f"memory {name} 0x{_number(address):X}")
    for name, address in (copy.get("functions") or {}).items():
        lines.append(f"function {name} 0x{_number(address):X}")
    if not module:
        for name, address in (copy.get("memory") or {}).items():
            lines.append(f"memory {name} 0x{_number(address):X}")
    elif copy.get("memory") and not module.get("memory"):
        for name, address in copy["memory"].items():
            lines.append(f"memory {name} 0x{_number(address):X}")
    for name, size in (description.get("own_memory") or {}).items():
        if _number(size) <= 0:
            raise DescriptionError(f"own memory {name}: a size in bytes")
        lines.append(f"own {name} {_number(size)}")
    texture = description["resources"].get("texture")
    if texture is None:   # (a port's own: its setup uploads it, Elvoret's entrance's exe TIM)
        lines.append("texture 0 -1")
    elif "tim" in texture:   # a TIM of its data the setup uploads as it is (Thunder's): no file
        lines.append(f"texture 0 -1\ntexture_data {value(texture['tim'], 'texture')}")
    else:
        lines.append(f"texture {value(texture['game_name'], 'texture')} {params.get(texture.get('param'), -1)}")
    for extra in description["resources"].get("files", []):   # more files its loader loads into memory words (Devour's pictures)
        if extra["memory"] not in {**(copy.get("memory") or {}), **((module or {}).get("memory") or {})}:
            raise DescriptionError(f"resources: the file word {extra['memory']} is not in the copy's memory")
        lines.append(f"load_file {extra['memory']} {value(extra['game_name'], 'files')}" + (" first" if extra.get("first") else ""))
    camera = description["resources"].get("camera")         # none: the effect starts no camera track
    lines.append(f"camera {value(camera, 'camera') if camera is not None else 0}")
    for pool in description["pools"]:
        own, in_buffer = pool.get("own"), pool.get("in_magic_buffer")
        queue = "own" if own else f"0x{_number(pool['queue']):X}"
        storage = "own" if own and not in_buffer else f"0x{_number(pool['storage']):X}"
        lines.append(f"pool {queue} {storage} {pool['size']} {pool['count']} "
                     f"{parts[pool['part']] if pool.get('part') else -1} {1 if in_buffer else 0}")
        if pool.get("before"):   # a module function the master calls before this queue (Stare's view axes)
            before = pool["before"]
            args = [a if isinstance(a, str) and a.startswith("@") else f"0x{_number(a):X}" for a in before.get("args", [])]
            if len(args) > 3:
                raise DescriptionError(f"pool {pool.get('key')}: a before call takes at most 3 arguments")
            lines.append(" ".join([f"pool_before 0x{_number(before['call']):X}"] + args))
    if "magic_buffer" in description:
        buffer = description["magic_buffer"]
        arena_a, arena_b = buffer["arenas"]
        lines.append(f"magic_buffer 0x{_number(arena_a):X} 0x{_number(arena_b):X} 0x{_number(buffer['morph']):X}")
    director = description["director"]
    if director.get("kind") == "port":   # the port's file loader, setup and root (Ray Bomb's kind: a port module's)
        if not module:
            raise DescriptionError("director: a port director runs a port module's code (\"module\")")
        lines.append("director port -1")
        lines.append(f"port 0x{_number(director['setup']):X} 0x{_number(director['file_loader']):X} 0x{_number(director['root']):X}"
                     + (" exe" if director.get("setup_exe") else ""))   # (the module's own setup: shared memory)
    elif director.get("kind") not in ("per_action", "master", "cycle", "chain") or director.get("spawns") not in tasks:
        raise DescriptionError("director: a per_action, master, cycle or chain director spawning one of the tasks")
    if director["kind"] == "chain":
        if director.get("single") not in tasks:
            raise DescriptionError("director: a chain names its lone target's director (\"single\")")
        lines.append(f"director chain {tasks[director['spawns']]} {tasks[director['single']]}")
    if director["kind"] == "cycle":
        lines.append(f"director cycle {tasks[director['spawns']]} {value(director['every'], 'director')} "
                     f"{step(director['place'], PLACES, 'director')}")
    if director["kind"] == "master":
        lines.append(f"director master {tasks[director['spawns']]} {_number(director.get('start_tick', 1))} "
                     f"{step(director['place'], PLACES, 'director')}")
    if director["kind"] in ("master", "cycle"):
        lines += [f"director_event_first {step(entry, DIRECTOR_EVENTS, 'director')}"
                  for entry in director.get("events_first", [])]
        lines += [f"director_event {step(entry, DIRECTOR_EVENTS, 'director')}" for entry in director.get("events", [])]
    if director["kind"] == "per_action":
        short = " short" if director.get("root") == "short" else ""   # Double's root and setup
        if short and director.get("upload") == "always":   # Phoenix Down's: the texture even when the cast repeats
            short += " upload_always"
        lines.append(f"director per_action {tasks[director['spawns']]}{short}")
        if "arena_size" in director:
            lines.append(f"arena_size {_number(director['arena_size'])}")
        if director.get("each") == "target":   # its task for each target of the action, in turn (Mega Phoenix's)
            lines.append("per_target")
        if director.get("release_file"):   # at its end its file's release asked and waited for (Doom's)
            lines.append("release_file")
        act = director.get("act")
        if act:   # the act family's master (Mega Phoenix's): its actor pools, the stage fades, its wait
            for name in ("stage_in", "stage_out"):   # (either may be left out: no fade)
                if name in act and act[name] not in tasks:
                    raise DescriptionError(f"director: act {name} names no task")
            lines.append(f"act_stage {tasks.get(act.get('stage_in'), -1)} {tasks.get(act.get('stage_out'), -1)} "
                         f"{value(act.get('wait', 0), 'director')}")
            lines += [f"act_pool {name} {_number(size)}" for name, size in act.get("pools", {}).items()]
            for call in act.get("calls", []):   # once, after the stage in task: functions the master calls (Quistis' cast animation)
                args = [a if isinstance(a, str) and a.startswith("@") else f"0x{_number(a):X}" for a in call.get("args", [])]
                if len(args) > 3:
                    raise DescriptionError("director: an act call takes at most 3 arguments")
                for a in args:
                    if a.startswith("@") and a != "@caster" and \
                            a[1:] not in {**(copy.get("memory") or {}), **((module or {}).get("memory") or {})}:
                        raise DescriptionError(f"director: act call argument {a} names no memory word")
                lines.append(" ".join([f"act_call 0x{_number(call['call']):X}"] + args))
            lines += [f"act_zero {name}" for name in act.get("zero", [])]
            lines += [f"act_clear {name}" for name in act.get("clear", [])]
            if act.get("part"):   # the parts of its draws: the system's, each definition's from first_part
                if act["part"] not in parts:
                    raise DescriptionError(f"director: act part names no part {act['part']}")
                lines.append(f"act_parts {parts[act['part']]} {_number(act['first_part'])}")
    if director.get("camera_matrix"):
        lines.append("camera_matrix")
    if director.get("setup") == "master":
        lines.append("master_setup")
    if director.get("seed_shared_rand"):
        lines.append("seed_shared_rand")
    if director["kind"] == "cycle" and "spawn_tick" in director:
        lines.append(f"cycle_spawn_tick {_number(director['spawn_tick'])}")
    for patch in description.get("patches", []):   # values written into data before every cast
        if patch.get("type") not in VAR_TYPES or patch["type"] == "grey":
            raise DescriptionError(f"patch {patch.get('offset')}: of a type i16, u16, i32, u8 or i8")
        lines.append(f"patch {value(patch['data'], 'patch')} {_number(patch['offset'])} {patch['type']} "
                     f"{value(patch['value'], 'patch')}")
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
        if task.get("code"):   # the original it mirrors (a port module's code spawning it finds it)
            lines.append(f"code 0x{_number(task['code']):X}")
        if task.get("native"):   # its body the port of that original (a port module's task)
            lines.append(f"native 0x{_number(task['native']):X}")
        if "node" in task:
            lines += node(task, where)
        if task.get("draws_first"):
            lines.append("order draws_first")
        if task.get("draw_only"):
            if task["draw_only"] not in DRAW_ONLY:
                raise DescriptionError(f"{where}: draw_only is one of {', '.join(DRAW_ONLY)}")
            lines.append(f"draw_only {task['draw_only']}")
        if task.get("hold"):
            lines.append(f"hold {step(task['hold'], HOLDS, where)}")
        own = task["key"]
        if task.get("end"):
            lines.append(f"end {op(task['end'], CONDITIONS, where, own)}")
        lines += actions(task.get("at_end", []), "at_end", where, own)
        lines += actions(task.get("every_tick", []), "tick", where, own)
        for number, phase in enumerate(task.get("phases", [])):
            here = f"{where} phase {number}"
            lines.append("phase")
            lines += actions(phase.get("each_tick", []), "phase_tick", here, own)
            if phase.get("wait"):
                lines.append(f"wait {op(phase['wait'], CONDITIONS, here, own)}")
            lines += actions(phase.get("do", []), "do", here, own)
        lines += actions(task.get("after_phase", []), "move", where, own)
        if task.get("motion"):
            lines.append(f"motion {step(task['motion'], MOTIONS, where)}")
        for spawn in task.get("step_spawns", []):
            first, last = (value(item, where) for item in spawn["window"])
            lines.append(f"step_spawn {tasks[spawn['task']]} {flag(spawn.get('if'), where)} {first} {last} "
                         f"{step(spawn.get('place', ['at_parent']), PLACES, where)}")
            lines += actions(spawn.get("init", []), "spawn_init", where, own, spawn["task"])
        for spawn in task.get("spawns", []):
            target = tasks.get(spawn.get("task"), -1)
            first, last = (value(item, where) for item in spawn["window"])
            if "every" in spawn:
                if target < 0:
                    raise DescriptionError(f"{where}: a spawn every n ticks of no task")
                lines.append(f"spawn_every {target} {first} {last} {value(spawn['every'], where)} "
                             f"{step(spawn['place'], PLACES, where)}")
                if spawn.get("if"):   # (its own line: an every-n-ticks spawn of an effect node gated by a flag)
                    lines.append(f"spawn_gate {flag(spawn['if'], where)}")
                lines += actions(spawn.get("init", []), "spawn_init", where, own, spawn["task"])
                continue
            count = [value(item, where) for item in spawn["count"]]
            if len(count) != 8:
                raise DescriptionError(f"{where}: a spawn count is 4 (from tick, how many) pairs")
            place = step(spawn["place"], PLACES, where, names={0: pools} if spawn["place"][0] == "glint" else ())
            lines.append(f"spawn {target} {flag(spawn.get('if'), where)} {first} {last} {' '.join(count)} {place}")
            lines += actions(spawn.get("init", []), "spawn_init", where, own, spawn.get("task"))
        lines += actions(task.get("events", []), "event", where, own)
        lines += actions(task.get("after_draws", []), "after", where, own)
        for draw in task.get("draws", []):
            limit = "-", "-"
            if "while_tick_below" in draw:
                limit = "below", value(draw["while_tick_below"], where)
            elif "while_tick_at_most" in draw:
                limit = "at_most", value(draw["while_tick_at_most"], where)
            elif "from_tick" in draw:
                limit = "at_least", value(draw["from_tick"], where)
            elif "within" in draw:   # [from, count]: from .. from + count - 1
                limit = "within", " ".join(value(item, where) for item in draw["within"])
            lines.append(f"draw {parts.get(draw.get('part'), 0)} {flag(draw.get('if'), where)} {limit[0]} {limit[1]} "
                         f"{op(draw['draw'], DRAWS, where, own)}")
            if draw.get("when"):   # a condition on the node (Double's column flash)
                lines.append(f"draw_when {op(draw['when'], CONDITIONS, where, own)}")
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
        if entry.get("kind") == "actors":   # its header and what its tables point at, below it
            body = _number(entry["body"])
            start, end = body - IMAGE_BASE, address + entry["size"] - IMAGE_BASE
            if not 0 <= start < end <= len(exe):
                raise DescriptionError(f"exe data {key}: 0x{body:X} is not in this exe")
            data[key] = {"kind": "actors", "from": entry["address"], "body": entry["body"], "header": address - body,
                         "hex": exe[start:end].hex()}
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
    if "module" in new:   # a port module's memory: one block of its own, the addresses moved into it (unless shared)
        new["module"]["own"] = not new["module"].get("shared")
        new["module"]["memory"] = dict((description.get("copy") or {}).get("memory") or {})
        new.pop("copy", None)
        for task in new["tasks"]:
            task.pop("function", None)
        return new
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
