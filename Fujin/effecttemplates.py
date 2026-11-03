"""Building an effect part by part (Choreography's + tab): the parts Fujin knows, each a piece of an
effect it describes (Cure's, Hypnotize's, Antidote's, Silence's, Float's, Haste's, Dispel's, Aura's, Aero's, Blind's, Petrify Stare's, Zombie's, Flare's, Reflect's, Berserk's, Fire's, Thunder's), and the description an effect made
of some of them gets.

A part brings its parameters (at the game's values), its task or what it adds to another part's
task (an action in its phases, a spawn, a draw), the pools and the data it uses. An effect is built
from its source effect's whole description, keeping what its parts bring: all of a family's parts
together are that effect exactly (whatever order they were added in), some of them a smaller effect
of the same kind. Parts of two families never mix: their nodes and directors differ (the heal
ring's effect-library nodes and per-action director, Hypnotize's plain nodes and master, Antidote's
one layout on the target, Silence's, Float's, Haste's, Dispel's, Aura's, Aero's, Blind's, Petrify Stare's, Zombie's, Flare's, Reflect's, Berserk's and Thunder's cycles of one task per action,
Fire's chain of one director per action).

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
    # Aero's family (one task per action: two layouts scaled by the target's size, leaves whirling around it)
    "wind": ("one per action, a wind on its target", "How the effect starts", "per_action_wind", 118, "wind",
             ("target",), (), (), "One task per action, every few ticks: two prim layouts on the target scaled by its "
             "size, its sound, the result when both have finished (Aero's way)."),
    "wind_leaves": ("whirling around the target", "Moving parts", "per_action_wind", 118, "leaves", ("leaf",), (),
                    ("wind",), "A leaf a tick circling the target and climbing, then falling and bouncing away."),
    # Blind's family (one task per action: a layout left on the target, some objects additive quads; a screen flash)
    "blind": ("one per action, left on its target", "How the effect starts", "per_action_flash", 121, "layout",
              ("target",), (), (), "One task per action, every few ticks: a prim layout at one of its target's effect "
              "points, followed for a while then left there, some objects drawn as additive quads; its sound, the "
              "result, its end with the layout (Blind's way)."),
    "blind_flash": ("a screen flash and fades", "Drawn by another part", "per_action_flash", 121, "flash", (),
                    ("flash_level_clear", "screen_flash_level"), ("blind",),
                    "A screen flash every target task raises (the highest wins), and screen fades on its ticks."),
    # Petrify Stare's family (one task, the first action's: a layout at the caster, then one on its target)
    "stare": ("from the caster, then on its target", "How the effect starts", "per_action_stare", 120, "stare",
              ("target",), (), (), "The first action's task (its pool holds one): a prim layout at one of the "
              "caster's effect points, ahead of its facing; a screen fade, the sound at the caster, the result, its "
              "end (Petrify Stare's way)."),
    "stare_stone": ("on the target, later", "Drawn by another part", "per_action_stare", 120, "stone", (), (),
                    ("stare",), "A second layout at the target's effect position, from a later tick."),
    # Zombie's family (one task per action: a layout scaled by the target's size, the target swaying)
    "zombie": ("one per action, its target swaying", "How the effect starts", "per_action_sway", 114, "mist",
               ("target",), (), (), "One task per action, every few ticks (not while any young one runs): a prim "
               "layout at the target's effect position scaled by its size, two objects additive quads; the target's "
               "mark, its sound, the result, its end (Zombie's way)."),
    "zombie_overlay": ("the target redrawn swayed", "Drawn by another part", "per_action_sway", 114, "overlay", (), (),
                       ("zombie",), "The target redrawn lifted and swayed by a wave, flat additive from black to its tint."),
    # Flare's family (one task per action: a flash, the target tinted, a burst; a ring, a silhouette, sparks)
    "flare": ("one per action, a burst on its target", "How the effect starts", "per_action_burst", 124, "burst",
              ("target",), (), (), "One task per action, every few ticks (not while a young one runs on that target): a "
              "screen flash and fades, the target turned red and back, a burst layout at its effect position scaled by "
              "its size, its sound, the result (Flare's way)."),
    "flare_ring": ("at the target's feet", "Drawn by another part", "per_action_burst", 124, "ring", (), (), ("flare",),
                   "A second layout at the target's feet, scaled by its size."),
    "flare_silhouette": ("the target redrawn rippled", "Drawn by another part", "per_action_burst", 124, "silhouette", (),
                         (), ("flare",), "The target hidden and redrawn rippled around its effect position."),
    "flare_sparks": ("collapsing into the target", "Moving parts", "per_action_burst", 124, "sparks", ("spark",), (),
                     ("flare",), "Sprites on a sphere around the target that collapse into it, then burst out."),
    # Reflect's family (one barrier per action: a frame on the target, a wall growing through it; hexagons, rings)
    "reflect": ("one per action, a wall around its target", "How the effect starts", "per_action_barrier", 106, "wall",
                ("barrier",), (), (), "One barrier per action, every few ticks (not while a young one runs on that "
                "target): a frame turned with the target, a wall model growing up through it with a scrolling texture, "
                "then fading; its sound, the result (Reflect's way)."),
    "reflect_hexagons": ("orbiting up the wall", "Moving parts", "per_action_barrier", 106, "hexagons", ("hexagon",), (),
                         ("reflect",), "Hexagon models orbiting a point that climbs the wall, tilting, then squashed and faded."),
    "reflect_rings": ("growing above the target", "Moving parts", "per_action_barrier", 106, "rings", ("ring",), (),
                      ("reflect",), "Ring models growing above the target, one every few wall steps."),
    # Berserk's family (one main task per action: light rays; swirls, a flash, a glow, a burst, embers, sparks)
    "berserk": ("one per action, rays around its target", "How the effect starts", "per_action_rays", 108, "rays",
                ("main",), (), (), "One main task per action, every few ticks (not while a young one runs on that "
                "target): light rays turning around the target's effect position, fading; a screen fade, its sound, "
                "the result, its end once the rays are gone (Berserk's way)."),
    "berserk_swirls": ("spiralling in", "Moving parts", "per_action_rays", 108, "swirls", ("swirl",), (), ("berserk",),
                       "Textured ribbons spiralling in towards the target's effect position."),
    "berserk_flash": ("a flash at the target", "Drawn by another part", "per_action_rays", 108, "flash", (), (),
                      ("berserk",), "A sprite sequence at the target's effect position."),
    "berserk_glow": ("a pulsing glow", "Drawn by another part", "per_action_rays", 108, "glow", (), (), ("berserk",),
                     "A model at the target's effect position, pulsing and fading."),
    "berserk_burst": ("at the target's feet", "Drawn by another part", "per_action_rays", 108, "burst", (), (),
                      ("berserk",), "A layout at the target's feet, its objects' draw modes from a table."),
    "berserk_embers": ("rising around the target", "Moving parts", "per_action_rays", 108, "embers", ("ember",), (),
                       ("berserk",), "Sprites rising from a circle around the target's feet."),
    "berserk_sparks": ("around the target", "Moving parts", "per_action_rays", 108, "sparks", ("spark",), (),
                       ("berserk",), "Sprites at random points around the target's effect position."),
    # Fire's family (one director per action, each starting the next one's: flames around the targets, embers, sparks)
    "fire": ("one director per action, flames", "How the effect starts", "per_action_chain", 2, "flames",
             ("director", "director_single", "flame"), (), (), "One director per action, each starting the next "
             "action's a few ticks in: flame flipbooks over a ground glow around the targets (a lone target waits "
             "until no other one burns on it); the sound, the result (Fire's way)."),
    "fire_embers": ("rising from each flame", "Moving parts", "per_action_chain", 2, "embers", ("ember",), (), ("fire",),
                    "Flipbooks rising from each flame, faster and faster, shrinking."),
    "fire_sparks": ("drifting from each flame", "Moving parts", "per_action_chain", 2, "sparks", ("spark",), (), ("fire",),
                    "Shared effect sprites drifting from each flame, slowing, shrinking."),
    # Thunder's family (one bolt per action: sprite layers at its target's point, a screen flash, a ground layer, smoke)
    "thunder": ("one per action, a bolt on its target", "How the effect starts", "per_action_bolt", 3, "strike", ("bolt",), (), (),
                "One bolt per action, every few ticks (not while a young one runs on that target): sprite sequence layers "
                "at one of the target's effect points, each over its own ticks; its sound, the result (Thunder's way)."),
    "thunder_flash": ("over the whole screen", "Drawn by another part", "per_action_bolt", 3, "flash", (), (), ("thunder",),
                      "A flat semi-transparent quad over the whole screen."),
    "thunder_ground": ("at the target's feet", "Drawn by another part", "per_action_bolt", 3, "ground", (), (), ("thunder",),
                       "A sprite sequence on a plane at the target's feet."),
    "thunder_smoke": ("after the strike", "Drawn by another part", "per_action_bolt", 3, "smoke", (), (), ("thunder",),
                      "A sprite sequence at the target's effect point, after the strike."),
}
GROUPS = ("How the effect starts", "Moving parts", "Drawn by another part", "Sound", "Files")
STARTS = {"heal_ring": "emitter", "layouts": "main", "on_target": "anchor_layout", "per_action_target": "cycle_layout",
          "per_action_turned": "turned_glyph", "per_action_clock": "clock",
          "per_action_ring": "flash_ring", "per_action_aura": "aura",
          "per_action_wind": "wind", "per_action_flash": "blind",
          "per_action_stare": "stare", "per_action_sway": "zombie",
          "per_action_burst": "flare", "per_action_barrier": "reflect", "per_action_rays": "berserk",
          "per_action_chain": "fire", "per_action_bolt": "thunder"}
FAMILIES = {"heal_ring": "Around one target at a time (Cure's kind)",
            "layouts": "Over the whole cast at once (Hypnotize's kind)",
            "on_target": "One layout on the target (Antidote's kind)",
            "per_action_target": "One per action, on its target (Silence's kind)",
            "per_action_turned": "One per action, turned with its target (Float's kind)",
            "per_action_clock": "One per action, a clock on its target (Haste's kind)",
            "per_action_ring": "One per action, a flash and a ring (Dispel's kind)",
            "per_action_aura": "One per action, at its target's feet (Aura's kind)",
            "per_action_wind": "One per action, a wind on its target (Aero's kind)",
            "per_action_flash": "One per action, left on its target (Blind's kind)",
            "per_action_stare": "From the caster, then on its target (Petrify Stare's kind)",
            "per_action_sway": "One per action, its target swaying (Zombie's kind)",
            "per_action_burst": "One per action, a burst on its target (Flare's kind)",
            "per_action_barrier": "One per action, a wall around its target (Reflect's kind)",
            "per_action_rays": "One per action, rays around its target (Berserk's kind)",
            "per_action_chain": "One director per action, flames around its targets (Fire's kind)",
            "per_action_bolt": "One per action, a bolt on its target (Thunder's kind)"}


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
        for key in ("draws", "events", "every_tick", "after_draws"):
            if key in task:
                task[key] = [x for x in task[key] if (x.get("part") not in gone_parts if isinstance(x, dict) else True)
                             and not gone(x)]
        tasks.append(task)
    d["tasks"] = tasks
    director = d.get("director") or {}
    for key in ("events", "events_first"):
        if key in director:
            director[key] = [event for event in director[key] if not gone(event) and event[0] not in gone_actions]
            if not director[key]:
                del director[key]
    used_pools = {t["pool"] for t in tasks} | {s["place"][1] for t in tasks for s in t.get("spawns", [])
                                              if s.get("place", [None])[0] == "glint"}         | {a[3] for t in tasks for a in t.get("events", []) if a[0] == "dead_beams"}   # (Reflect's beam pool)
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
