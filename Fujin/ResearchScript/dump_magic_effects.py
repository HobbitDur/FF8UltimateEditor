"""============================================================================================
 HOW THE Fujin "spell logic" DATA (FF8GameData/Resources/json/magic_effect.json) IS PRODUCED
============================================================================================

This IDA script is the ONLY way to (re)generate `magic_effect.json`. Keep it: the JSON it
writes is decompiler output (Hex-Rays pseudocode of every FF8 spell animation) that CANNOT be
recovered from the game exe alone, so if the JSON is ever lost or the exe research is updated,
re-run this script to rebuild it.

WHAT IT DOES (one pass, on the open FF8_EN.exe database):

 1. Cleans variable names (persisted in the IDB) on every player-castable spell
    (effect_id 1-223): the init function plus its spell-local sub-functions - director,
    particle ticks - reached two call levels deep, following BOTH direct calls AND the
    function pointers passed to AddTaskToQueue (the ticks are registered by pointer, never
    called directly). Also cleans the shared effect-helper library. Parameters become
    `cast_context` (spell init) / `task_node` (tick), and locals are named after the engine
    call that produces them (AddTaskToQueue -> task_node, Field_Alloc -> render_header, ...).
    The undocumented monster/cinematic slots 226-345 are exported but NOT renamed.

 2. Exports the decompiled pseudocode of every non-free effect to
    FF8GameData/Resources/json/magic_effect.json (path in FF8GAMEDATA_JSON below), which the
    Fujin subtool auto-loads at launch for its read-only "spell logic" tab.

HOW TO RUN:

 1. Open FF8_EN.exe (2013 Steam english build) in IDA, let auto-analysis finish, and make
    sure the Hex-Rays decompiler is available. The magic dispatch tables must already be
    named / analysed (this is the HobbitDur research database, not a fresh exe).
 2. Edit FF8GAMEDATA_JSON below if your FF8UltimateEditor checkout lives elsewhere.
 3. File > Script file... > select this file. It prints progress in the Output window and
    writes the JSON (plus a fallback copy next to the .i64). Takes ~30-60 s.

VERIFY (outside IDA):
    python -c "import json; d=json.load(open('FF8GameData/Resources/json/magic_effect.json'));\
 print([f['name'] for f in d['143']['functions']])"
    -> Firaga (143) lists its init + director + root + particle-tick functions, all named
       MAG_143_* (no anonymous sub_ / engine helpers - those show inline in the pseudocode).

Reference: FF8ModdingWiki "Magic Effect Anatomy & Authoring" and "Magic Spell Effect Runtime".
Dispatch tables: MagicList_Logic @0xC81774, MagicList_TextureLoad @0xC81DB8 (400 slots each,
indexed by effect_id - 1).
"""

import json
import os
import re

import ida_bytes
import ida_funcs
import ida_hexrays
import ida_name
import ida_nalt
import ida_typeinf
import idautils
import idc

MAGIC_LIST_LOGIC = 0xC81774
MAGIC_LIST_TEXTURE_LOAD = 0xC81DB8
SLOT_COUNT = 400
PLAYER_SPELL_MAX = 223  # rename vars only up to this effect_id (skip 226-345 UNKNOWN)

# How deep to follow a spell's own calls when collecting its functions. Firaga is 2 deep
# (init -> director -> particle ticks) but the state-machine spells (Cure, Double, ...) nest
# further (init -> director -> state handler -> emitter -> its own states), so we walk deeper.
# The magic-region bound + the shared-helper name filter keep this from exploding into engine.
MAX_WALK_DEPTH = 5

# Uniform prototype for the per-spell INIT functions. They are all called the same way
# (`C3_28_GF_data_pointer = MAG_xxx(&attacker_context)`) and all return their root task queue,
# but the decompiler guessed different signatures per function (int vs unsigned __int8 *
# parameter; TaskQueueExample * / TaskQueueHeader * / void return). Applying this makes them
# read consistently, and types the parameter as MagicCastContext so accesses like
# `cast_context->action_data` / `cast_context->flags` read as struct members instead of raw
# `*(cast_context + 4)`. Tick/state functions are left alone (their arg counts vary).
INIT_PROTOTYPE = "TaskQueueHeader *__cdecl %s(MagicCastContext *cast_context)"


def ensure_cast_context_type():
    """Make sure the MagicCastContext struct exists before the init prototypes reference it.
    If a richer definition already exists in the IDB (e.g. with action_data typed as
    BattleTask68Data *), keep it; otherwise declare a minimal fallback."""
    existing = ida_typeinf.tinfo_t()
    if existing.get_named_type(None, "MagicCastContext"):
        return
    decl = ("struct MagicCastContext { unsigned char attacker_slot; unsigned char flags; "
            "unsigned char unknown_2; unsigned char unknown_3; void *action_data; };")
    ida_typeinf.parse_decls(None, decl, False, ida_typeinf.PT_SIL)

# Address range of the magic-effect code. The MAG_* functions and their private
# sub-functions live from ~0x575520 up to the top of the main code (Leviathan's private code
# reaches ~0xB65130); the shared battle engine sits BELOW 0x575000, so the low bound alone
# excludes every widely-shared engine helper. The high bound just keeps the walk out of the
# packed overlay segment above the main image. We only export a spell's OWN functions
# (callees inside this range) - engine helpers then appear inline by name in the pseudocode
# instead of as separate, noisy entries.
MAG_REGION_LO = 0x575000
MAG_REGION_HI = 0xB69000

# Where the pseudocode dump is written so Fujin can auto-load it. Adjust if your checkout
# lives elsewhere; the script also writes a copy next to the .i64 as a fallback.
FF8GAMEDATA_JSON = (r"C:\Users\l.guerra\Desktop\Dev\FF8UltimateEditor"
                    r"\FF8GameData\Resources\json\magic_effect.json")

# Locals that hold the result of one of these engine calls get the mapped name.
CALL_TO_LVAR_NAME = {
    "AddTaskToQueue": "task_node",
    "Effect_AddTaskAndInitFromCtx": "task_node",
    "Field_Alloc": "render_header",
    "Magic_TextureOFF_ToEAX1": "tex_base",
    "GetDefaultEffectPosition": "effect_pos",
    "GetEffectSpawnPosition": "spawn_pos",
    "BuildAxisAngleRotationMatrix": "rot_matrix",
    "Battle_QueueTIMUpload_GetEOF": "tim_eof",
    "rand": "rnd",
}

# Shared engine helpers: their names are already clean and their bodies are NOT exported,
# so we do not descend into them when collecting a spell's functions (but we do clean their
# own locals in a separate pass for IDB quality).
SHARED_HELPERS = re.compile(
    r"^(BdLink_|AddTaskToQueue|ExecuteTaskQueue|BS_|Battle_|Magic_|Effect_|Field_|"
    r"GetEffectSpawnPosition|GetDefaultEffectPosition|GetRotationBetween|"
    r"BuildAxisAngle|NormalizeVector|FixedPoint|compute(Sin|Cosine)|scale3DMatrix|"
    r"ComposeAffine|ComposeZYX|TransformVector|BdPlaySE3D|ApplyActionResult|"
    r"IO_GetFile|xorEAX|nullsub_|_rand|_sprintf|preCam|Call_|memset)"
)

SHARED_HELPER_ADDRS = [
    0x508300, 0x508360, 0x508420, 0x8DC540, 0x5713E0, 0x5714F0, 0x571480,
    0x572200, 0x505E30, 0x571400, 0x502170, 0x5099A0, 0x5013A0, 0x506690,
]


def function_name(addr):
    name = ida_name.get_name(addr)
    return name if name else ""


def decompile_text(addr):
    func = ida_funcs.get_func(addr)
    if func is None:
        return "// no function defined at 0x%X" % addr
    try:
        code = ida_hexrays.decompile(func.start_ea)
        return str(code) if code else "// decompilation failed"
    except ida_hexrays.DecompilationFailure as error:
        return "// decompilation failed: %s" % error


def strings_used_by(addr):
    found = []
    func = ida_funcs.get_func(addr)
    if func is None:
        return found
    for item_ea in idautils.FuncItems(func.start_ea):
        for xref in idautils.DataRefsFrom(item_ea):
            text = ida_bytes.get_strlit_contents(xref, -1, ida_nalt.STRTYPE_C)
            if text:
                found.append(text.decode("ascii", "replace"))
    return found


def direct_callees(addr):
    """Functions referenced by the body of `addr`: both direct calls (code refs) AND
    functions passed by pointer (data refs) - the effect task ticks are registered as
    `AddTaskToQueue(&queue, MAG_..._Tick)`, i.e. the tick is a function-pointer argument,
    never a direct call, so following code refs alone misses the whole animation."""
    callees = []
    func = ida_funcs.get_func(addr)
    if func is None:
        return callees
    for item_ea in idautils.FuncItems(func.start_ea):
        refs = list(idautils.CodeRefsFrom(item_ea, False)) + list(idautils.DataRefsFrom(item_ea))
        for xref in refs:
            callee = ida_funcs.get_func(xref)
            # keep only references to a function START (a real callback/callee, not a
            # jump inside the same function or a pointer into the middle of code) that lives
            # inside the magic-effect code block (a spell-local function, not an engine helper)
            if (callee and callee.start_ea == xref and callee.start_ea != func.start_ea
                    and MAG_REGION_LO <= callee.start_ea < MAG_REGION_HI):
                callees.append(callee.start_ea)
    return sorted(set(callees))


def spell_local_functions(init_addr):
    """Init function + its spell-local callees (skip the shared engine helpers), MAX_WALK_DEPTH deep."""
    collected = []
    to_visit = [init_addr]
    depth = {init_addr: 0}
    while to_visit:
        current = to_visit.pop(0)
        if current in collected:
            continue
        collected.append(current)
        if depth[current] >= MAX_WALK_DEPTH:
            continue
        for callee in direct_callees(current):
            if SHARED_HELPERS.match(function_name(callee)):
                continue
            if callee not in depth:
                depth[callee] = depth[current] + 1
                to_visit.append(callee)
    return collected


def _call_target_name(expr):
    """Name of the function called by a cot_call expression, or ''."""
    target = expr.x
    if target.op == ida_hexrays.cot_obj:
        return ida_funcs.get_func_name(target.obj_ea) or ""
    if target.op == ida_hexrays.cot_helper:
        return target.helper or ""
    return ""


class _AssignCollector(ida_hexrays.ctree_visitor_t):
    """Map lvar index -> name of the engine call whose result it is assigned."""

    def __init__(self):
        ida_hexrays.ctree_visitor_t.__init__(self, ida_hexrays.CV_FAST)
        self.lvar_to_call = {}

    def visit_expr(self, expr):
        if expr.op == ida_hexrays.cot_asg and expr.x.op == ida_hexrays.cot_var:
            rhs = expr.y
            if rhs.op == ida_hexrays.cot_cast:
                rhs = rhs.x
            if rhs.op == ida_hexrays.cot_call:
                name = _call_target_name(rhs)
                if name:
                    self.lvar_to_call.setdefault(expr.x.v.idx, name)
        return 0


def clean_variable_names(func_addr, is_init):
    """Apply the heuristic renames to one function. Returns number of renames applied."""
    try:
        cfunc = ida_hexrays.decompile(func_addr)
    except ida_hexrays.DecompilationFailure:
        return 0
    if not cfunc:
        return 0

    lvars = cfunc.lvars
    existing = {lv.name for lv in lvars}
    desired = {}  # old_name -> preferred new base name

    def is_argument(lvar):
        # is_arg_var is a method in some IDA builds, a property in others
        flag = getattr(lvar, "is_arg_var", False)
        return flag() if callable(flag) else bool(flag)

    # 1. First argument
    for lv in lvars:
        if is_argument(lv):
            desired[lv.name] = "cast_context" if is_init else "task_node"
            break

    # 2. Locals named after their producing call
    collector = _AssignCollector()
    collector.apply_to(cfunc.body, None)
    for idx, call_name in collector.lvar_to_call.items():
        if idx < 0 or idx >= len(lvars):
            continue
        base = CALL_TO_LVAR_NAME.get(call_name)
        if base:
            desired.setdefault(lvars[idx].name, base)

    # 3. Resolve collisions and apply
    used = set(existing) - set(desired.keys())
    applied = 0
    for old_name, base in desired.items():
        new_name = base
        suffix = 2
        while new_name in used:
            new_name = "%s_%d" % (base, suffix)
            suffix += 1
        if new_name == old_name:
            used.add(new_name)
            continue
        if ida_hexrays.rename_lvar(func_addr, old_name, new_name):
            used.add(new_name)
            applied += 1
    return applied


def main():
    if not ida_hexrays.init_hexrays_plugin():
        print("Hex-Rays decompiler not available")
        return

    logic_addrs = [ida_bytes.get_dword(MAGIC_LIST_LOGIC + 4 * slot) for slot in range(SLOT_COUNT)]
    fl_addrs = [ida_bytes.get_dword(MAGIC_LIST_TEXTURE_LOAD + 4 * slot) for slot in range(SLOT_COUNT)]

    # --- Pass 0: give every spell-private sub_/nullsub_ a MAG_<eid>_sub_<addr> name ------
    # so no anonymous sub_ leaks into the exported pseudocode. Effects are processed in
    # order, so a helper shared by sibling spells is named after the lowest effect_id that
    # reaches it (and later effects then see the clean name).
    sub_renames = 0
    for slot in range(SLOT_COUNT):
        effect_id = slot + 1
        init_addr = logic_addrs[slot]
        if not init_addr:
            continue
        for func_addr in spell_local_functions(init_addr):
            name = function_name(func_addr)
            if name.startswith("sub_") or name.startswith("nullsub_"):
                ida_name.set_name(func_addr, "MAG_%03d_sub_%X" % (effect_id, func_addr),
                                  ida_name.SN_NOCHECK)
                sub_renames += 1
    print("Pass 0: named %d spell-private sub_ functions" % sub_renames)

    # --- Pass 0b: give every init function the same prototype ---------------------------
    ensure_cast_context_type()
    proto_set = 0
    for slot in range(SLOT_COUNT):
        init_addr = logic_addrs[slot]
        if not init_addr or ida_funcs.get_func(init_addr) is None:
            continue
        decl = INIT_PROTOTYPE % function_name(init_addr)
        tif = ida_typeinf.tinfo_t()
        if ida_typeinf.parse_decl(tif, None, decl + ";", ida_typeinf.PT_SIL):
            if ida_typeinf.apply_tinfo(init_addr, tif, ida_typeinf.TINFO_DEFINITE):
                proto_set += 1
    print("Pass 0b: normalized %d init prototypes" % proto_set)

    # --- Pass 1: clean variable names of the player spells + shared helpers -------------
    renamed_functions = 0
    total_renames = 0
    cleaned = set()

    def clean(addr, is_init):
        nonlocal renamed_functions, total_renames
        if addr in cleaned or ida_funcs.get_func(addr) is None:
            return
        cleaned.add(addr)
        count = clean_variable_names(addr, is_init)
        if count:
            renamed_functions += 1
            total_renames += count

    for slot in range(PLAYER_SPELL_MAX):
        init_addr = logic_addrs[slot]
        if not init_addr:
            continue
        functions = spell_local_functions(init_addr)
        for func_addr in functions:
            clean(func_addr, is_init=(func_addr == init_addr))
        print("cleaned effect %3d: %-32s (%d functions)" % (
            slot + 1, function_name(init_addr), len(functions)))
    for helper_addr in SHARED_HELPER_ADDRS:
        clean(helper_addr, is_init=False)
    print("Pass 1: renamed %d variables across %d functions" % (total_renames, renamed_functions))

    # --- Pass 2: export pseudocode of every non-free effect -----------------------------
    effects = {}
    for slot in range(SLOT_COUNT):
        effect_id = slot + 1
        init_addr = logic_addrs[slot]
        fl_addr = fl_addrs[slot]
        if init_addr == 0 and fl_addr == 0:
            effects[effect_id] = {"free": True}
            continue
        entry = {
            "free": False,
            "logic_addr": "0x%X" % init_addr,
            "logic_name": function_name(init_addr),
            "fl_addr": "0x%X" % fl_addr,
            "fl_name": function_name(fl_addr),
            "files_loaded": strings_used_by(fl_addr),
            "functions": [],
        }
        for func_addr in spell_local_functions(init_addr):
            entry["functions"].append({
                "addr": "0x%X" % func_addr,
                "name": function_name(func_addr),
                "pseudocode": decompile_text(func_addr),
            })
        effects[effect_id] = entry

    payload = json.dumps(effects, indent=1)
    targets = [FF8GAMEDATA_JSON, os.path.join(os.path.dirname(idc.get_idb_path()), "magic_effect.json")]
    for path in targets:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
            print("wrote %s" % path)
        except OSError as error:
            print("could not write %s: %s" % (path, error))


main()
