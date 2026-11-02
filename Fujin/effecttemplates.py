"""Building an effect part by part (Choreography's + tab): the parts Fujin knows, each a piece of an
effect it describes (Cure's, Hypnotize's, Antidote's, Silence's, Float's, Haste's, Dispel's, Aura's), and the description an effect made
of some of them gets.

A part brings its parameters (at the game's values), its task or what it adds to another part's
task (an action in its phases, a spawn, a draw), the pools and the data it uses. An effect is built
from its source effect's whole description, keeping what its parts bring: all of a family's parts
together are that effect exactly (whatever order they were added in), some of them a smaller effect
of the same kind. Parts of two families never mix: their nodes and directors differ (the heal
ring's effect-library nodes and per-action director, Hypnotize's plain nodes and master, Antidote's
one layout on the target, Silence's, Float's, Haste's, Dispel's and Aura's cycles of one task per action).

No Qt here.
"""
import functools
import json
import re

from Fujin.effectprogram import load_description, new_effect

# key: hint (a few words beside its name in the + menu: its name is its tab's title, title()), group,
# family, source effect, part key (its parameters' "part"), the tasks it owns, the actions it adds to
# its host's phases, the parts it needs, doc
TEMPLATES = {
    # Cure's family (the heal ring: effect-library nodes, one emitter per target in turn)
    "emitter": ("one per target, in turn", "How the effect starts", "heal_ring", 1, "emitter", ("emitter",), (), (),
                "One per target, in turn: it follows its target, plays the sound, gives the result (HP) and ends "
                "the action. The parts it spawns start from it (Cure's way)."),
    "ring": ("a light climbing in a helix", "Moving parts", "heal_ring", 1, "ring", ("ring",), (), ("emitter",),
             "A light climbing around the target in a helix, spawned by the emitter after a delay; the parts "
             "drawn or spawned along it come from it (Cure's ring)."),
    "overlay": ("the target lit by the ring", "Drawn by another part", "heal_ring", 1, "overlay", (),
                ("overlay_start", "hide_target", "show_target", "overlay"), ("ring",),
                "The target hidden and redrawn lit by an image projected from the ring (Cure's overlay)."),
    "glow": ("a flipbook on the ground", "Drawn by another part", "heal_ring", 1, "glow", (), (), ("ring",),
             "A flipbook on the ground under the ring, fading out (Cure's glow)."),
    "sparkles": ("flying off the ring", "Moving parts", "heal_ring", 1, "sparkles", ("sparkle",), (), ("ring",),
                 "One per helix step of the ring, flying off at a random speed (burst, then drift)."),
    "motes": ("rising around the target", "Moving parts", "heal_ring", 1, "motes", ("mote",), (), ("ring",),
              "Spawned on a circle around the target below the ring, rising at a random speed."),
    "glints": ("streaks around the ring", "Moving parts", "heal_ring", 1, "glints", (), (), ("ring",),
               "Streaks of the effect library growing, spinning and shrinking around the ring."),
    "files": ("the texture's file", "Files", "heal_ring", 1, "files", (), (), ("emitter",),
              "The magic-folder file the effect's texture is loaded from (empty: the game's)."),
    # Hypnotize's family (plain nodes, the master starting one task for the whole cast)
    "main": ("one for the whole cast", "How the effect starts", "layouts", 133, "timing", ("main",), (), (),
             "One for the whole cast at once: it plays the sound, gives every target its result, and spawns the "
             "parts below on its own clock (Hypnotize's way)."),
    "main_layout": ("in front of the caster", "Drawn by another part", "layouts", 133, "main", (), (),
                    ("main",), "The main task's prim layout, framed on the caster's screen position."),
    "rings": ("at the caster's bones", "Moving parts", "layouts", 133, "rings", ("ring",), (), ("main",),
              "Eight prim layouts at points of the caster's bones, one every few ticks (Hypnotize's rings)."),
    "targets": ("at the targets' bones", "Moving parts", "layouts", 133, "targets", ("target",), (),
                ("main",), "Prim layouts at random bones of random targets, at random sizes."),
    "sprites": ("around a target", "Moving parts", "layouts", 133, "sprites", ("sprite",), (), ("main",),
                "A flipbook at random points around a target's bone."),
    # Antidote's family (the status-cure items: the master starting one prim layout on the target)
    "anchor_layout": ("played on the target", "How the effect starts", "on_target", 294, "layout", ("play",), (), (),
                      "One prim layout played at an anchor on the target (a share of its height); the target "
                      "takes the result when it ends (Antidote's way)."),
    "anchor_timing": ("the sound on the effect's clock", "Sound", "on_target", 294, "timing", (), (),
                      ("anchor_layout",), "The sound, played on a tick of the effect's own clock."),
    # Silence's family (the status spells: one task per action, every few ticks, on its target)
    "cycle_layout": ("one per action, in turn", "How the effect starts", "per_action_target", 122, "layout",
                     ("target",), (), (), "One task per action, every few ticks: a prim layout at one of its target's "
                     "effect points, followed every tick, its sound, the action's result, its end (Silence's way)."),
    # Float's family (one task per action, its layouts in frames turned with the target, scaled by its size)
    "turned_glyph": ("one per action, turned with its target", "How the effect starts", "per_action_turned", 115, "glyph",
                     ("target",), (), (), "One task per action, every few ticks: a prim layout at the target's feet, "
                     "turned with it and scaled by its size; its sound, the action's result, its end (Float's way)."),
    "turned_upper": ("higher on the target, later", "Moving parts", "per_action_turned", 115, "upper", (), (),
                     ("turned_glyph",), "A second layout at one of the target's effect points, turned with it, from a "
                     "later tick, its depth from a point of it."),
    # Haste's family (Float's way with the clock spells' options: two layouts, the end when both finish)
    "clock": ("one per action, a clock on its target", "How the effect starts", "per_action_clock", 125, "clock",
              ("target",), (), (), "One task per action, every few ticks: a clock at the target's feet, turned with "
              "it and scaled by its size; its sound, a screen fade, the result when its layouts have finished "
              "(Haste's way)."),
    "clock_lower": ("under the target's effect point", "Moving parts", "per_action_clock", 125, "lower", (), (),
                    ("clock",), "A second layout under the target's effect point, lowered by its size, turned with "
                    "it."),
    # Dispel's family (one task per action: a screen flash, a ring layout, particles)
    "flash_ring": ("one per action, a flash and a ring", "How the effect starts", "per_action_ring", 109, "ring",
                   ("target",), (), (), "One task per action, every few ticks (not while a young one runs on that "
                   "target): a screen flash, a ring layout at the target's effect position, its sound, a fade, the "
                   "result (Dispel's way)."),
    "ring_sparkles": ("around the target", "Moving parts", "per_action_ring", 109, "sparkles", ("particle",), (),
                      ("flash_ring",), "A flipbook at random points around the target, every few ticks."),
    "ring_circle": ("on a rising circle", "Moving parts", "per_action_ring", 109, "circle", ("particle",), (),
                    ("flash_ring",), "A flipbook on a rising circle around the target, every few ticks."),
    # Aura's family (one task per action: a layout at the feet with a table of draw modes, flames, a glow)
    "aura": ("one per action, at its target's feet", "How the effect starts", "per_action_aura", 111, "aura",
             ("target",), (), (), "One task per action, every few ticks (not while a young one runs on that target): "
             "a prim layout at the target's feet scaled by the square root of its size, its sound, the result "
             "(Aura's way)."),
    "aura_flames": ("spinning around the target", "Moving parts", "per_action_aura", 111, "flames", ("flame",), (),
                    ("aura",), "Flame models spinning around the target, a few a tick, fading in and out."),
    "aura_glow": ("a flipbook at its feet", "Drawn by another part", "per_action_aura", 111, "glow", (), (), ("aura",),
                  "A flipbook at the target's feet, with a screen fade."),
}
GROUPS = ("How the effect starts", "Moving parts", "Drawn by another part", "Sound", "Files")
STARTS = {"heal_ring": "emitter", "layouts": "main", "on_target": "anchor_layout", "per_action_target": "cycle_layout",
          "per_action_turned": "turned_glyph", "per_action_clock": "clock",
          "per_action_ring": "flash_ring", "per_action_aura": "aura"}
FAMILIES = {"heal_ring": "Around one target at a time (Cure's kind)",
            "layouts": "Over the whole cast at once (Hypnotize's kind)",
            "on_target": "One layout on the target (Antidote's kind)",
            "per_action_target": "One per action, on its target (Silence's kind)",
            "per_action_turned": "One per action, turned with its target (Float's kind)",
            "per_action_clock": "One per action, a clock on its target (Haste's kind)",
            "per_action_ring": "One per action, a flash and a ring (Dispel's kind)",
            "per_action_aura": "One per action, at its target's feet (Aura's kind)"}


@functools.cache
def title(key):
    """A part's name: its tab's title (its part's in its source effect's description)."""
    template = TEMPLATES[key]
    return next(part["title"] for part in load_description(template[3])["parts"] if part["key"] == template[4])


def hint(key):
    return TEMPLATES[key][0]


def with_needs(parts, key):
    """What adding `key` to an effect made of `parts` adds: the parts it needs (directly or not) not
    in it yet and `key`, in TEMPLATES' order; [] when it cannot be (another family, or added)."""
    if key in parts or (parts and TEMPLATES[key][2] != family(parts)):
        return []
    wanted, todo = set(), [key]
    while todo:
        part = todo.pop()
        if part not in wanted and part not in parts:
            wanted.add(part)
            todo.extend(TEMPLATES[part][7])
    if not parts:
        wanted.add(STARTS[TEMPLATES[key][2]])
    return [k for k in TEMPLATES if k in wanted]


def family(parts):
    """The family of an effect made of `parts` (None: no part yet)."""
    return TEMPLATES[parts[0]][2] if parts else None


def addable(parts):
    """The parts that can be added to an effect made of `parts`: a start when it has none, else its
    family's parts not in it yet whose needs it has."""
    if not parts:
        return [key for key in STARTS.values()]
    kind = family(parts)
    return [key for key, t in TEMPLATES.items() if t[2] == kind and key not in parts and set(t[7]) <= set(parts)]


def dependents(parts, key):
    """`key` and the parts of `parts` that need it, directly or not."""
    gone = {key}
    changed = True
    while changed:
        changed = False
        for other in parts:
            if other not in gone and set(TEMPLATES[other][7]) & gone:
                gone.add(other)
                changed = True
    return [part for part in parts if part in gone]


def empty_effect(effect_id, name):
    """A new effect with no part yet: Choreography's + tab adds them."""
    return {"format": 1, "effect": effect_id, "name": name, "template_parts": [], "parts": [], "groups": [],
            "params": [], "pools": [], "tasks": [], "director": {}, "resources": {},
            "doc": "Built part by part in Fujin (Choreography's + tab)."}


def _refs(node):
    """Every "$parameter" and "@data" a piece of a description names."""
    text = json.dumps(node)
    return set(re.findall(r'"\$([^"]+)"', text)), set(re.findall(r'"@([^"]+)"', text))


def build_effect(effect_id, name, parts, exe=None, keep=None):
    """The description of effect `effect_id` made of `parts` (template keys, one family): its
    source effect's description keeping what those parts bring. `exe` (FF8_EN.exe's bytes): its
    data copied into it, as new_effect does; `keep`: an earlier build of it whose own data (as
    edited in the Data tab) is kept."""
    if not parts:
        return empty_effect(effect_id, name)
    kinds = {TEMPLATES[part][2] for part in parts}
    if len(kinds) != 1 or STARTS[kinds.pop()] not in parts:
        raise ValueError("an effect's parts are of one family and have its start")
    source = TEMPLATES[parts[0]][3]
    d = new_effect(load_description(source), effect_id, name, exe)
    removed = [key for key, t in TEMPLATES.items() if t[3] == source and key not in parts]
    gone_parts = {TEMPLATES[key][4] for key in removed}
    kept_tasks = {task for key in parts for task in TEMPLATES[key][5]}
    gone_tasks = {task for key in removed for task in TEMPLATES[key][5]} - kept_tasks
    gone_actions = {action for key in removed for action in TEMPLATES[key][6]}
    gone_params = {p["key"] for p in d["params"] if p["part"] in gone_parts}
    d["params"] = [p for p in d["params"] if p["part"] not in gone_parts]
    d["parts"] = [p for p in d["parts"] if p["key"] not in gone_parts]
    kept_params = {p["key"] for p in d["params"]}
    d["groups"] = [g for g in d["groups"] if any(k == g["key"] or k.startswith(g["key"] + ".") for k in kept_params)]

    def gone(entry):
        params, _data = _refs(entry)
        return bool(params & gone_params)

    tasks = []
    for task in d["tasks"]:
        if task["key"] in gone_tasks:
            continue
        for phase in task.get("phases", []):
            phase["do"] = [a for a in phase.get("do", []) if a[0] not in gone_actions and not gone(a)
                           and not (a[0] == "spawn" and a[1] in gone_tasks)]
            phase["each_tick"] = [a for a in phase.get("each_tick", []) if not gone(a)]
            if "wait" in phase and gone(phase["wait"]):
                del phase["wait"]
            for key in ("do", "each_tick"):
                if not phase[key]:
                    del phase[key]
        for key in ("spawns", "step_spawns"):
            if key in task:
                task[key] = [s for s in task[key] if s.get("task") not in gone_tasks and not gone(s)
                             and s.get("pool") not in {p["key"] for p in d["pools"] if p.get("part") in gone_parts}]
        for key in ("draws", "events", "every_tick"):
            if key in task:
                task[key] = [x for x in task[key] if (x.get("part") not in gone_parts if isinstance(x, dict) else True)
                             and not gone(x)]
        tasks.append(task)
    d["tasks"] = tasks
    director = d.get("director") or {}
    for key in ("events", "events_first"):
        if key in director:
            director[key] = [event for event in director[key] if not gone(event)]
            if not director[key]:
                del director[key]
    used_pools = {t["pool"] for t in tasks} | {s["place"][1] for t in tasks for s in t.get("spawns", [])
                                              if s.get("place", [None])[0] == "glint"}
    d["pools"] = [p for p in d["pools"] if p["key"] in used_pools]
    if "param" in d["resources"].get("texture", {}) and d["resources"]["texture"]["param"] not in kept_params:
        del d["resources"]["texture"]["param"]
    # the data still named somewhere (a pointer table keeps what it points at)
    _params, named = _refs({k: v for k, v in d.items() if k not in ("data", "exe_data")})
    table = "data" if "data" in d else "exe_data"
    entries = {k: v for k, v in d[table].items() if isinstance(v, dict)}
    for key in list(named):
        named |= set(entries.get(key, {}).get("pointers", entries.get(key, {}).get("items", [])))
    d[table] = {k: v for k, v in d[table].items() if not isinstance(v, dict) or k in named}
    if keep is not None and table == "data":
        for key, entry in (keep.get("data") or {}).items():
            if isinstance(entry, dict) and key in d["data"]:
                d["data"][key] = entry
    d["template_parts"] = [key for key in TEMPLATES if key in parts]
    d["doc"] = "Built part by part in Fujin (Choreography's + tab): " + ", ".join(title(k) for k in d["template_parts"]) + "."
    return d
