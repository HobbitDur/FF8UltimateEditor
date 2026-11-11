"""Frame-by-frame playback of an entity animation sequence: what the sequence will DO.

sequenceanalyser says what each command means; it cannot say what the sequence does over
time - how many frames it takes, which branch a jump takes, when the sound lands, where
the model ends up. That needs the byte-code to be run, not just read. This module runs it,
one battle frame at a time, and returns a timeline a preview can play back. It is the
entity counterpart of camerabake.bake_camera_animation(), and like it, it holds no Qt: the
widget only plays what is baked here, so the playback can be tested without a screen.

The walk is NOT re-implemented here either - sequencecommand.iter_command decodes the
command at the instruction pointer, exactly as everywhere else, so the preview cannot read
a sequence differently from the editor showing it.

The driver (FF8_EN.exe AnimSeq_UpdateEntityPerFrame @0x504290) runs every battle frame:

1. if a background sequence id was set (opcode 9A), that sequence runs first, from its
   start, every frame (no saved position);
2. the main sequence resumes at the byte offset saved from the previous frame;
3. it runs until an opcode PAUSES it - a bare op code < 0x80 (queue animation and wait for
   it to end), A1 (yield), B9 (frame wait), A9 (hard stop), AC. The offset is saved and
   the next frame resumes there;
4. the animation advances by one frame.

An animation of N frames occupies exactly N ticks (frames 0..N-1) and the interpreter
resumes on tick N, the tick whose read reports completion and does not draw (FF8_EN.exe
Battle_ReadAnimation @0x508F90 returns early) - the same timing animsplitter relies on to
chain the parts of a split animation.

What the timeline is EXACT about, from the file alone:
  - control flow: the arithmetic op codes (C0-E5) and every jump (E6-F3);
  - timing: how many frames the sequence takes, and which frame each command runs on;
  - sequence chaining: A7 (goto), A2 (end -> queued/idle), A3 (set base), 9A (background);
  - transforms the sequence writes itself: position (95, E5 0D/0E/0F), Y rotation (E5 17),
    scale (E5 24-27), hidden model parts (E5 20, 81), animation speed factor (E5 2A).

What it CANNOT know from the file, because it lives in the running battle: the C3 reads
of the battle context (who the target is, how far, the random value, whether the attack
hit...). Those are not guessed - they are BattleContext fields with documented defaults,
so a preview can expose them as knobs and show which branch each assumption takes. Every
such read is recorded in BakeResult.assumption_list, so the UI can say "this branch was
taken because target distance was assumed to be X".

What it does not render at all (no assets in the .dat): sounds, particle/fade effects,
battle text, other entities. Those become events on the timeline - which is what matters
for editing anyway, since the frame they land on is the thing that gets mistuned.
"""
import math
import random

from .sequenceanalyser import describe_command
from .sequencecommand import SequenceCommand, iter_command, get_jump_target
from .sequencevm import as_sequence_vm

# Why the bake stopped.
STOP_END = "end"                 # the sequence ended and nothing followed it
STOP_LOOP = "loop"               # the whole state repeated: it runs forever from there
STOP_HANG = "hang"               # E4 or an unknown 0xC0+ op code: the engine hangs here
STOP_ERROR = "error"             # jump/goto that cannot be followed (bad offset, no such sequence)
STOP_MAX_FRAMES = "max_frames"   # the safety cap was reached, the sequence may go on

# Op codes that stop the interpreter for the current frame.
_PAUSE_YIELD = 0xA1        # resume at the next op code next frame
_PAUSE_WAIT = 0xB9         # resume after its parameter says
_PAUSE_HARD_STOP = 0xA9    # end of sequence, resolved by the driver next frame
_PAUSE_RESTORE = 0xAC      # restore base model, queue a sequence, end the sequence

_BUGGED_SET_ZERO = 0xE4    # sets current_value = 0 without advancing the pointer: hangs

# How many op codes one frame may execute before the bake calls it an infinite loop. A
# frame legitimately runs a few dozen (an arithmetic block, a jump, an action); a sequence
# jumping to itself with offset 0, or A2-chaining into a sequence that A2s straight back,
# would otherwise spin forever inside a single frame.
_MAX_OP_CODE_PER_FRAME = 2000

_PSX_ONE = 4096  # 4096 units == 1.0 == a full turn, the engine's fixed-point scale


def _c_div(numerator, denominator):
    """Integer division truncating toward zero, like C - Python's // floors instead."""
    if denominator == 0:
        return numerator  # the engine would fault; keep going rather than crash a preview
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def _c_mod(numerator, denominator):
    if denominator == 0:
        return numerator
    return numerator - denominator * _c_div(numerator, denominator)


def _compute_sin(angle):
    """PSX-style sine: 4096 units is a full turn, the result is scaled to 4096 == 1.0."""
    return round(_PSX_ONE * math.sin(angle * 2 * math.pi / _PSX_ONE))


def _compute_cos(angle):
    return round(_PSX_ONE * math.cos(angle * 2 * math.pi / _PSX_ONE))


class BattleContext:
    """Everything a sequence reads from the running battle that a file cannot contain.

    These are the C3 special reads whose value depends on the fight, not on the data being
    edited (who the target is, how far away, the random draw, whether the blow landed). A
    preview has to assume something; assuming it HERE, explicitly and with one documented
    default per field, is what lets the UI show the assumption next to the branch it
    decided and let the user change it.

    `seed` seeds the random value C3 0x0C returns, so two bakes of the same sequence with
    the same context give the same timeline - a preview that changed shape on every replay
    would be unusable.
    """

    def __init__(self, *, own_slot=4, target_slot=0, target_is_self=False,
                 target_distance=2048, own_speed_factor=0, target_speed_factor=0,
                 angle_to_target=0, target_was_hit=True, back_attack=0, is_monster=True,
                 anim_status=0, battle_state_flags=0, camera_flag=0, gf_loaded=0,
                 nb_target_hit=1, another_entity_free=1, encounter_id=0, invisible=0,
                 target_effect_y_offset_f0=0, target_effect_y_offset_f1=0,
                 weapon_word_28=0, weapon_word_30=0, weapon_word_32=0,
                 original_scene_out_x=0, neutral_scale=_PSX_ONE, idle_sequence_id=1,
                 target_position=None, effect_signal_ready=True, seed=0):
        self.own_slot = own_slot                      # C3 0x1B
        self.target_slot = target_slot                # C3 0x18
        self.target_is_self = target_is_self          # C3 0x10 / 0x11
        self.target_distance = target_distance        # C3 0x10 / 0x11, engine units
        self.own_speed_factor = own_speed_factor      # C3 0x11
        self.target_speed_factor = target_speed_factor
        self.angle_to_target = angle_to_target        # C3 0x1A, 4096 = a full turn
        self.target_was_hit = target_was_hit          # C3 0x19, and whether B4 shows
        self.back_attack = back_attack                # C3 0x22
        self.is_monster = is_monster                  # C3 0x1C
        self.anim_status = anim_status                # C3 0x1F
        self.battle_state_flags = battle_state_flags  # C3 0x08
        self.camera_flag = camera_flag                # C3 0x23
        self.gf_loaded = gf_loaded                    # C3 0x28
        self.nb_target_hit = nb_target_hit            # C3 0x29
        self.another_entity_free = another_entity_free  # C3 0x2E
        self.encounter_id = encounter_id              # C3 0x33
        self.invisible = invisible                    # C3 0x37
        self.target_effect_y_offset_f0 = target_effect_y_offset_f0  # C3 0x36
        self.target_effect_y_offset_f1 = target_effect_y_offset_f1  # C3 0x35
        self.weapon_word_28 = weapon_word_28          # C3 0x14
        self.weapon_word_30 = weapon_word_30          # C3 0x15
        self.weapon_word_32 = weapon_word_32          # C3 0x16
        self.original_scene_out_x = original_scene_out_x  # C3 0x2C
        # What the engine's scale fields hold for "unscaled". The model's own scale in the
        # file is 1024-neutral (monsterdata.ScaleType) but the runtime field E5 0x24-0x27
        # writes has not been pinned down, so it is a knob rather than a hidden constant:
        # the preview shows value / neutral_scale as the factor.
        self.neutral_scale = neutral_scale
        # The idle the entity falls back to when a sequence ends with nothing queued.
        # initAnimationSequenceAtStartBattle @0x5027D0 sets it to 1 for every entity at
        # battle start; A3 and E5 0x0B change it while the fight runs.
        self.idle_sequence_id = idle_sequence_id
        # Where the TARGET stands, in the entity's own raw units, for the 9E move task
        # (a lerp of the entity's world position toward the target's - FF8_EN.exe
        # moveEntityToTargetSmoothly @0x50F750). Straight ahead at target_distance:
        # ahead is local -Z (attack sequences approach with NEGATIVE E5 0F forward
        # offsets - c0m001 seq 14, Squall's run - so the facing points down -Z).
        self.target_position = (target_position if target_position is not None
                                else (0, 0, -target_distance))
        # Attack/spell sequences synchronise with their (separately running) magic-effect
        # code through control-flag bit 0x10: they poll it before each shot (c0m001 seq
        # 11/12: read flags, AND 0x10, loop until set, then XOR it off and raise 0x20 to
        # trigger the effect). No effect code runs in a preview, so with this True the
        # bit reads as set and the choreography plays through instead of polling forever.
        self.effect_signal_ready = effect_signal_ready
        self.seed = seed


# What kind of thing a command is, for a timeline that groups events instead of listing 60
# indistinguishable rows. Op codes absent from this map are "state" (they change the
# entity's own state without being worth a marker of their own).
EVENT_ANIMATION = "animation"
EVENT_SOUND = "sound"
EVENT_EFFECT = "effect"
EVENT_TEXT = "text"
EVENT_TARGET = "target"
EVENT_MODEL = "model"
EVENT_FLOW = "flow"
EVENT_MOVE = "move"
EVENT_STATE = "state"

# Short, stable names for the C3/E5 special variables, used to build the readable
# formula of current_value (a preview showing "speed_to_target(2500) - 100" explains a
# jump arc; the raw json descriptions are sentences and would drown it).
SPECIAL_VAR_NAME = {
    0x08: "state_flags", 0x09: "anim_frame", 0x0A: "anim_total", 0x0B: "base_seq",
    0x0C: "random", 0x0D: "pos_lateral", 0x0E: "pos_vertical", 0x0F: "pos_forward",
    0x10: "speed_to_target", 0x11: "adj_speed_to_target", 0x12: "sine", 0x13: "cosine",
    0x14: "weapon_w28", 0x15: "weapon_w30", 0x16: "weapon_w32", 0x17: "rotation_y",
    0x18: "target_slot", 0x19: "target_hit", 0x1A: "angle_to_target", 0x1B: "own_slot",
    0x1C: "facing", 0x1F: "anim_status", 0x20: "hide_part", 0x22: "back_attack",
    0x23: "camera_flag", 0x24: "scale_model", 0x25: "scale_z", 0x26: "scale_y",
    0x27: "scale_x", 0x28: "gf_loaded", 0x29: "nb_hit", 0x2A: "anim_speed",
    0x2C: "sceneout_x", 0x2E: "other_entity_free", 0x33: "encounter",
    0x35: "target_fx_y_f1", 0x36: "target_fx_y_f0", 0x37: "invisible",
}


# What each short name MEANS, for the preview's formula tooltips. Keyed by the name as
# it appears in a formula; the bracketed families are covered by their prefix.
SPECIAL_VAR_GLOSSARY = {
    "anim_frame": "current frame of the animation the entity is playing (C3 09)",
    "anim_total": "total frames of that animation (C3 0A)",
    "base_seq": "the idle sequence id the entity falls back to (C3 0B)",
    "random": "random value 0..32767, seeded in the preview (C3 0C)",
    "pos_lateral": "entity-LOCAL offset, sideways (C3/E5 0D - the vector is rotated by "
                   "the entity's facing before being applied)",
    "pos_vertical": "entity-LOCAL offset, vertical - PSX down-positive, negative is up "
                    "(C3/E5 0E)",
    "pos_forward": "entity-LOCAL offset along the FACING - negative values move toward "
                   "the target; this is how attacks leap/run at it (C3/E5 0F)",
    "speed_to_target": "walk speed toward the target, from its distance "
                       "(C3 10; the distance is a preview assumption)",
    "adj_speed_to_target": "walk speed toward the target, from its distance minus both "
                           "combatants' speed stats (C3 11; assumed in the preview)",
    "sine": "sine of the last E5 12 angle, 4096 = 1.0 (C3 12)",
    "cosine": "cosine of the last E5 13 angle, 4096 = 1.0 (C3 13)",
    "rotation_y": "the entity's Y rotation, 4096 = a full turn (C3 17)",
    "state_flags": "animation-state control flags bitmask (C3/E5 08)",
    "angle_to_target": "angle toward the target, 4096 = a full turn (C3 1A)",
    "e5[": "one of the entity's 8 local variables - how the AI and earlier frames pass "
           "values to the sequence (C3/E5 00-07)",
    "save[": "one of the 8 saved slots, kept across sequences (C3/E5 78-7F)",
    "stack[": "a scratch slot of the VM (C3/E5 80+)",
}


# The known bits of the animation-state control flags (BattleStateControlerFlag in
# FF8_EN.exe, plus the effect-sync pair decoded from usage), for a readable rendering.
STATE_FLAG_NAME = {0x01: "stop_base_anim", 0x02: "loop_anim", 0x04: "preparation",
                   0x08: "wait_anim_end", 0x10: "effect_ready", 0x20: "effect_fire",
                   0x40: "continue_fight", 0x80: "unk_80_after_hit",
                   0x100: "take_damage", 0x200: "effect_done"}


def state_flags_text(value) -> str:
    """The flags value with its set bits named: '144 = effect_ready | 0x80'."""
    if not value:
        return "0"
    name_list = [name for bit, name in STATE_FLAG_NAME.items() if value & bit]
    unknown = value & ~sum(STATE_FLAG_NAME)
    if unknown:
        name_list.append(hex(unknown))
    return f"{value} = " + " | ".join(name_list)


def special_var_name(parameter) -> str:
    """The short name of a C3/E5 special variable parameter."""
    if parameter <= 0x07:
        return f"e5[{parameter}]"
    if parameter >= 0x80:
        return f"stack[{parameter:02X}]"
    if parameter >= 0x78:
        return f"save[{0x7F - parameter}]"
    return SPECIAL_VAR_NAME.get(parameter, f"var[{parameter:02X}]")


# Symbol per arithmetic family (op_code & 0xFC), for the same formula.
_OPERATION_SYMBOL = {0xC4: "+", 0xC8: "-", 0xCC: "*", 0xD0: "/", 0xD4: "&",
                     0xD8: "|", 0xDC: "^", 0xE0: "%"}

_EVENT_KIND_BY_OP_CODE = {
    0x80: EVENT_MODEL, 0x81: EVENT_MODEL, 0x83: EVENT_MODEL, 0x84: EVENT_EFFECT,
    0x85: EVENT_MODEL, 0x86: EVENT_MODEL, 0x90: EVENT_TARGET, 0x91: EVENT_TEXT,
    0x92: EVENT_TARGET, 0x93: EVENT_TARGET, 0x94: EVENT_MODEL, 0x95: EVENT_MOVE,
    0x96: EVENT_EFFECT, 0x97: EVENT_SOUND, 0x98: EVENT_SOUND, 0x99: EVENT_EFFECT,
    0x9A: EVENT_FLOW, 0x9B: EVENT_MODEL, 0x9C: EVENT_MODEL, 0x9D: EVENT_STATE,
    0x9E: EVENT_MOVE, 0x9F: EVENT_MODEL, 0xA0: EVENT_ANIMATION, 0xA2: EVENT_FLOW,
    0xA3: EVENT_FLOW, 0xA5: EVENT_EFFECT, 0xA6: EVENT_MODEL, 0xA7: EVENT_FLOW,
    0xA8: EVENT_EFFECT, 0xA9: EVENT_FLOW, 0xAA: EVENT_TARGET, 0xAC: EVENT_FLOW,
    0xAD: EVENT_TARGET, 0xAE: EVENT_TARGET, 0xAF: EVENT_TARGET, 0xB0: EVENT_EFFECT,
    0xB1: EVENT_EFFECT, 0xB2: EVENT_TARGET, 0xB4: EVENT_EFFECT, 0xB5: EVENT_SOUND,
    0xB6: EVENT_SOUND, 0xB7: EVENT_TARGET, 0xB8: EVENT_SOUND, 0xBB: EVENT_TEXT,
    0xBD: EVENT_MODEL, 0xBE: EVENT_MODEL, 0xBF: EVENT_TARGET,
}


class ExecutedCommand:
    """One command the interpreter ran, on the frame it ran on."""

    __slots__ = ("seq_id", "address", "op_code", "description", "kind", "is_background",
                 "parameters", "value_note")

    def __init__(self, seq_id, address, op_code, description, kind, is_background=False,
                 parameters=b""):
        self.seq_id = seq_id
        self.address = address
        self.op_code = op_code
        self.description = description
        self.kind = kind
        # Run by the background sequence (9A) rather than by the main one: the editor
        # should not highlight it as the current line of the sequence being previewed.
        self.is_background = is_background
        # The command's raw parameter bytes: what a consumer that REPLAYS the event (the
        # preview playing a B5's sound) needs, and the description alone cannot give back.
        self.parameters = bytes(parameters)
        # For the value-flow commands, what actually happened, with the formula: an E5
        # write reads "pos_y ← speed(2500) - 100 = 2400", a conditional jump
        # "if > 0: anim_total(5) - 1 = 4 → taken". Filled in by the interpreter AFTER
        # the command ran (the outcome is not knowable before).
        self.value_note = ""

    def __repr__(self):
        return (f"ExecutedCommand(seq {self.seq_id} @0x{self.address:X} "
                f"{self.op_code:02X} {self.description!r})")


class SequenceFrame:
    """The entity's state on one battle frame, and what ran to get there."""

    __slots__ = ("index", "seq_id", "address", "anim_id", "anim_frame", "anim_total",
                 "position", "move_position", "rotation_y", "scale", "current_value",
                 "value_expression", "hidden_part_mask", "is_waiting_animation",
                 "command_list", "state_flags", "local_value_list", "saved_value_list")

    def __init__(self, index, seq_id, address, anim_id, anim_frame, anim_total, position,
                 rotation_y, scale, current_value, hidden_part_mask, is_waiting_animation,
                 command_list, move_position=(0, 0, 0), value_expression="",
                 state_flags=0, local_value_list=(0,) * 8, saved_value_list=(0,) * 8):
        self.index = index                  # battle frame number, 0 based
        self.seq_id = seq_id                # sequence the interpreter is in
        self.address = address              # where it resumes/resumed in that sequence
        self.anim_id = anim_id              # animation being played, None before the first
        self.anim_frame = anim_frame        # which frame of it is drawn on this battle frame
        self.anim_total = anim_total
        # ENTITY-LOCAL offset the sequence wrote (E5 0D/0E/0F): (lateral, vertical,
        # forward-along-facing). The engine rotates it by the entity's own rotation
        # before adding it to the world position (pre_pre_linkedToAnimationSequence:
        # someCameraWork loads ComposeZYX(based_rotation) into the GTE, then MVMVA on
        # this vector) - forward is how attacks leap/run toward the target.
        self.position = position
        # (x, y, z) the 9E move task has transported the WHOLE entity by - a separate
        # layer from `position` (the engine keeps them in different fields: based_position
        # vs the VM's own position offsets), so both apply to where the model is drawn.
        self.move_position = move_position
        self.rotation_y = rotation_y
        self.scale = scale                  # (model, x, y, z)
        self.current_value = current_value
        # The formula that built current_value (battle reads as name(value)), for a
        # display that explains the number instead of just stating it.
        self.value_expression = value_expression
        self.hidden_part_mask = hidden_part_mask
        self.is_waiting_animation = is_waiting_animation
        self.command_list = command_list    # [ExecutedCommand] run on this frame
        # The entity's VM-visible variables on this frame, for a watch panel: the
        # control flags and the two 8-slot variable banks (C3/E5 00-07 and 78-7F).
        self.state_flags = state_flags
        self.local_value_list = tuple(local_value_list)
        self.saved_value_list = tuple(saved_value_list)

    def event_list(self):
        """The commands worth a marker on a timeline (everything but plain state work)."""
        return [command for command in self.command_list if command.kind != EVENT_STATE]

    def __repr__(self):
        return (f"SequenceFrame({self.index}: seq {self.seq_id} @0x{self.address:X} "
                f"anim {self.anim_id} frame {self.anim_frame}/{self.anim_total})")


class BakeResult:
    """The timeline of a sequence: one SequenceFrame per battle frame, and why it stopped."""

    def __init__(self, frame_list, stop_reason, stop_detail="", loop_from=None,
                 assumption_list=None, background_seq_id_list=()):
        self.frame_list = frame_list
        self.stop_reason = stop_reason
        self.stop_detail = stop_detail
        # Sequences that ran underneath this one every frame, set by 9A. Worth naming:
        # their commands are not in the timeline, but they did run.
        self.background_seq_id_list = list(background_seq_id_list)
        # Frame the state first repeated on: the timeline loops from there to the end.
        self.loop_from = loop_from
        # [(frame index, C3 parameter, what was read, value)] - every battle-context read,
        # so the UI can show which assumption decided which branch.
        self.assumption_list = assumption_list or []

    def __len__(self):
        return len(self.frame_list)

    @property
    def nb_frame(self):
        return len(self.frame_list)

    def is_endless(self):
        return self.stop_reason in (STOP_LOOP, STOP_MAX_FRAMES)

    def animation_id_list(self):
        """The animations the sequence plays, in the order they first appear."""
        id_list = []
        for frame in self.frame_list:
            if frame.anim_id is not None and frame.anim_id not in id_list:
                id_list.append(frame.anim_id)
        return id_list

    def iter_event(self):
        """(frame index, ExecutedCommand) of everything worth showing on a timeline."""
        for frame in self.frame_list:
            for command in frame.event_list():
                yield frame.index, command

    def summary(self) -> str:
        """One line for the preview panel's header."""
        if self.stop_reason == STOP_LOOP:
            return f"{self.nb_frame} frames, then loops forever from frame {self.loop_from}"
        if self.stop_reason == STOP_HANG:
            return f"{self.nb_frame} frames, then the engine HANGS ({self.stop_detail})"
        if self.stop_reason == STOP_ERROR:
            return f"{self.nb_frame} frames, then stops: {self.stop_detail}"
        if self.stop_reason == STOP_MAX_FRAMES:
            return f"over {self.nb_frame} frames (still running at the preview limit)"
        return f"{self.nb_frame} frames"


def sequence_dict_from_section(seq_animation_data) -> dict:
    """{id: bytes} from a monster's seq_animation_data, the shape IfritSeq holds."""
    sequence_list = (seq_animation_data or {}).get('seq_animation_data', [])
    return {sequence['id']: bytes(sequence['data']) for sequence in sequence_list}


def background_sequence_id_set(vm, sequence_by_id) -> set:
    """The sequences some 9A names as a background sequence.

    They are a different kind of program and must not be judged like a normal one: the
    driver re-runs a background sequence from its FIRST byte every frame, so it needs no
    terminator and normally ends on a plain A1 (e.g. c0m123 sequence 12, "80 01 A1" -
    step texture animation 1, yield). Run as a main sequence that would fall off its end
    on the second frame, which is why bake_sequence has to be told which kind it is
    (as_background) and why the preview should label them.
    """
    vm = as_sequence_vm(vm)
    id_set = set()
    for data in sequence_by_id.values():
        for _address, op_code, parameters in iter_command(vm, bytes(data or b"")):
            if op_code == 0x9A and parameters and parameters[0]:
                id_set.add(parameters[0])
    return id_set


def _frame_count_function(animation_frame_count):
    """Normalise a list/dict/callable of animation lengths to one callable."""
    if callable(animation_frame_count):
        return animation_frame_count

    def frame_count(anim_id):
        try:
            return int(animation_frame_count[anim_id])
        except (IndexError, KeyError, TypeError, ValueError):
            return 0

    return frame_count


class _Interpreter:
    """The engine's per-frame driver, running one entity's sequences.

    Private: build a timeline with bake_sequence(). Split out of it only because a frame
    driver plus an op code dispatcher does not read well as one function.
    """

    def __init__(self, vm, sequence_by_id, seq_id, frame_count, context, follow_chain,
                 as_background=False):
        self.vm = as_sequence_vm(vm)
        self.sequence_by_id = sequence_by_id
        self.frame_count = frame_count
        self.context = context
        self.follow_chain = follow_chain
        # Preview the sequence the way 9A runs it: from its first byte every frame, with
        # no position carried over (see background_sequence_id_set).
        self.as_background = as_background
        self.background_id_set = background_sequence_id_set(self.vm, sequence_by_id)
        self.random = random.Random(context.seed)

        # --- interpreter state
        self.seq_id = seq_id
        self.address = 0
        self.background_seq_id = 0
        # NOT the sequence being previewed: the engine gives every entity idle sequence 1
        # at battle start, so a sequence ending with A2 hands over to that one, not to
        # itself (c0m001's entrance, B5.. A8 01 A2, would otherwise chain into itself).
        self.base_seq_id = context.idle_sequence_id
        self.queued_seq_id = None      # set by A7-like chaining, consumed by A2/A3
        self.pending_seq_id = None     # queued by AC: the driver starts it NEXT frame
        self.current_value = 0
        self.local_value = [0] * 8     # e5_data_saved[0..7], C3/E5 0x00-0x07
        self.saved_value = [0] * 8     # E5_7F_save[0..7], C3/E5 0x78-0x7F
        self.stack = {}                # C3/E5 parameter >= 0x80
        self.sine = 0                  # C3 0x12, written by E5 0x12
        self.cosine = 0                # C3 0x13
        self.position = [0, 0, 0]      # x, y, z
        self.rotation_y = 0
        self.scale = [context.neutral_scale] * 4  # model, x, y, z
        # How current_value was built, as a readable formula mirroring the arithmetic
        # exactly (left-to-right like the VM applies it, battle reads shown as
        # name(value)). Not part of the loop-detection state: it mirrors the value.
        self.value_expression = "0"
        # The formula stored into each VM scratch slot (e5 locals, save, stack) by its
        # last E5 write: reading the slot back splices the stored formula in, so
        # "stack[FD]" becomes the "(0 - e5[2]) * anim_frame / anim_total" it stands for.
        self.slot_expression = {}
        self.anim_speed_factor = 0
        self.hidden_part_mask = 0
        # C3/E5 0x08: the entity's animation-state control flags. Seeded from the battle
        # context, then owned by the sequence once it writes them (seq 14 of c0m001 does
        # `C3 08 / DA 80 / E5 08`), so a read-after-write sees the written value.
        self.state_flags = context.battle_state_flags
        self.state_flags_written = False

        # --- 9E transport (moveEntityToTargetSmoothly @0x50F750): a lerp of the WHOLE
        # entity from its resting spot toward the target, run as a parallel task that
        # ticks once per battle frame. move_anchor is original_sceneout_position (where
        # the lerp starts from, updated to the arrival point when it completes) and
        # move_position the current based_position - both (x, z), the engine moves no Y.
        self.move_anchor = [0, 0]
        self.move_position = [0, 0]
        self.move_task = None          # (counter, duration, target_x, target_z) while moving

        # --- animation state
        self.anim_id = None
        self.anim_frame = 0
        self.anim_total = 0
        self.anim_loops = False        # queued by A0: the engine re-queues it when it ends
        self.is_waiting_animation = False
        self.wait_frame = 0            # frames still to skip because of B9

        # --- per-frame collection
        self._value_note = ""          # set by the op that just ran, attached after it
        self.command_list = []
        self.chained_seq_id = set()    # sequences entered through A2 on the current frame
        self.background_used = set()   # background sequences that actually ran
        self.assumption_list = []
        self.frame_index = 0
        self.stop_reason = None
        self.stop_detail = ""

    # ------------------------------------------------------------------ helpers
    def _sequence(self, seq_id):
        return self.sequence_by_id.get(seq_id)

    def _command_at(self, seq_id, address):
        """The command at `address`, decoded the way the engine reads it from there.

        Decoded on the fly rather than looked up in a pre-walked list: a jump sets the
        pointer to any byte, so where a command starts depends on where the last jump
        landed, not on a walk from offset 0.
        """
        data = self._sequence(seq_id)
        if data is None or not 0 <= address < len(data):
            return None
        for _address, op_code, parameters in iter_command(self.vm, data[address:]):
            return SequenceCommand(self.vm, op_code, parameters, address)
        return None

    def _record(self, command, is_background):
        kind = _EVENT_KIND_BY_OP_CODE.get(command.op_code, EVENT_STATE)
        if command.is_animation():
            kind = EVENT_ANIMATION
        try:
            description = describe_command(command)
        except Exception:  # a description is a convenience, never a reason to stop a bake
            description = ""
        self.command_list.append(ExecutedCommand(self.seq_id, command.address,
                                                 command.op_code, description, kind,
                                                 is_background,
                                                 bytes(command.parameters or b"")))

    def _assume(self, parameter, what, value):
        self.assumption_list.append((self.frame_index, parameter, what, value))
        return value

    def _stop(self, reason, detail=""):
        self.stop_reason = reason
        self.stop_detail = detail

    def _state_key(self):
        """Everything that decides the future. Two frames with the same key play the same
        thing forever after, which is exactly what "this sequence loops" means."""
        return (self.seq_id, self.address, self.background_seq_id, self.base_seq_id,
                self.queued_seq_id, self.pending_seq_id, self.current_value,
                tuple(self.local_value), tuple(self.saved_value),
                tuple(sorted(self.stack.items())), self.sine,
                self.cosine, tuple(self.position), self.rotation_y, tuple(self.scale),
                self.anim_speed_factor, self.hidden_part_mask, self.state_flags,
                tuple(self.move_anchor), tuple(self.move_position), self.move_task,
                self.anim_id, self.anim_frame, self.anim_total, self.anim_loops,
                self.is_waiting_animation, self.wait_frame)

    # -------------------------------------------------------------- frame driver
    def run_frame(self):
        """One battle frame, always returning the SequenceFrame it produced.

        A frame is produced even when the frame is the one that hangs or errors: the
        commands that did run before it are exactly what the user needs to see to find
        the problem, so they must not be dropped with the failure.
        """
        self.command_list = []
        self.chained_seq_id = set()

        # 0. A sequence AC queued last frame becomes the current one now, from its start
        # (the driver resolves nextSeqIndex at the top of the frame).
        if self.pending_seq_id is not None:
            self.seq_id = self.pending_seq_id
            self.address = 0
            self.pending_seq_id = None

        # 1. The background sequence (9A) runs first, from its start, every frame.
        if self.background_seq_id and self._sequence(self.background_seq_id) is not None:
            self.background_used.add(self.background_seq_id)
            self._run_program(self.background_seq_id, 0, is_background=True)

        # 2/3. The main sequence, unless it is waiting for something or already stopped.
        if self.is_waiting_animation:
            if self.anim_frame >= self.anim_total:
                self.is_waiting_animation = False
        if self.stop_reason is not None:
            pass  # the background sequence stopped the run; do not start the main one
        elif not self.is_waiting_animation and self.wait_frame > 0:
            self.wait_frame -= 1
        elif not self.is_waiting_animation:
            if self.as_background:
                self.address = 0  # 9A restarts a background sequence every frame
            self.address = self._run_program(self.seq_id, self.address)

        frame = SequenceFrame(self.frame_index, self.seq_id, self.address, self.anim_id,
                              min(self.anim_frame, max(self.anim_total - 1, 0)),
                              self.anim_total, tuple(self.position), self.rotation_y,
                              tuple(self.scale), self.current_value, self.hidden_part_mask,
                              self.is_waiting_animation, self.command_list,
                              (self.move_position[0], 0, self.move_position[1]),
                              self.value_expression, self.state_flags,
                              tuple(self.local_value), tuple(self.saved_value))

        # 4. The animation advances one frame, and the parallel tasks (the 9E transport)
        # tick once, after the frame they drew - like the engine's per-frame task queue.
        self._tick_move_task()
        self._advance_animation()
        self.frame_index += 1
        return frame

    def _tick_move_task(self):
        """One tick of moveEntityToTargetSmoothly @0x50F750: pos = origin +
        (counter<<12)/duration * (target - origin) >> 12, arrival committed into the
        anchor (original_sceneout_position) when counter reaches the duration."""
        if self.move_task is None:
            return
        counter, duration, target_x, target_z = self.move_task
        counter += 1
        ratio = (counter << 12) // duration
        self.move_position[0] = self.move_anchor[0] + (
            (ratio * (target_x - self.move_anchor[0])) >> 12)
        self.move_position[1] = self.move_anchor[1] + (
            (ratio * (target_z - self.move_anchor[1])) >> 12)
        if counter >= duration:
            self.move_anchor = [target_x, target_z]
            self.move_task = None
        else:
            self.move_task = (counter, duration, target_x, target_z)

    def _advance_animation(self):
        if self.anim_id is None or self.anim_total <= 0:
            return
        self.anim_frame += 1
        if self.anim_frame >= self.anim_total and self.anim_loops:
            # A0 does not pause the sequence and the engine re-queues the animation from
            # frame 0 as soon as it ends (see animloopdetector): it plays in a loop.
            self.anim_frame = 0

    def _run_program(self, seq_id, address, is_background=False):
        """Run from `address` until the interpreter pauses. Returns where it resumes."""
        if is_background:
            saved_seq_id, self.seq_id = self.seq_id, seq_id
        for _ in range(_MAX_OP_CODE_PER_FRAME):
            command = self._command_at(self.seq_id, address)
            if command is None:
                # Ran past the end of the sequence: the engine would read whatever follows
                # it in the file. Refuse to guess, and say so - naming the one shape where
                # that is normal rather than broken.
                if self.seq_id in self.background_id_set:
                    self._stop(STOP_ERROR,
                               f"sequence {self.seq_id} runs off its end (offset "
                               f"{address}), but a 9A names it as a background sequence: "
                               f"preview it with as_background, which restarts it every "
                               f"frame as the engine does")
                else:
                    self._stop(STOP_ERROR, f"execution left sequence {self.seq_id} "
                                           f"(offset {address}): it has no terminator "
                                           f"(A2/A9) and no jump back")
                break
            self._record(command, is_background)
            self._value_note = ""
            next_address, pause = self._execute(command, address)
            if self._value_note and self.command_list:
                self.command_list[-1].value_note = self._value_note
            if self.stop_reason is not None:
                break
            address = next_address
            if pause:
                break
        else:
            self._stop(STOP_HANG, f"sequence {self.seq_id} ran {_MAX_OP_CODE_PER_FRAME} "
                                  f"op codes in one frame without pausing")
        if is_background:
            self.seq_id = saved_seq_id
        return address

    # ------------------------------------------------------------ op code dispatch
    def _execute(self, command, address):
        """Run one command. Returns (address of the next one, whether it pauses the frame)."""
        op_code = command.op_code
        parameters = command.parameters
        next_address = address + command.get_size()

        if command.is_unknown():
            self._stop(STOP_HANG, f"op code {op_code:02X} has no known size: the engine's "
                                  f"dispatcher does not advance the pointer on it")
            return next_address, True

        if self.vm.is_animation(op_code):  # a bare op code IS the animation id
            self._queue_animation(op_code, loops=False)
            self.is_waiting_animation = True  # and the sequence waits for it to end
            return next_address, True

        if op_code >= 0xC0:
            return self._execute_vm_op_code(op_code, parameters, address, next_address)
        return self._execute_action_op_code(op_code, parameters, next_address)

    def _queue_animation(self, anim_id, loops):
        total = self.frame_count(anim_id)
        if anim_id == self.anim_id and loops and self.anim_frame < self.anim_total:
            return  # A0 on the animation already running leaves it running, not restarted
        self.anim_id = anim_id
        self.anim_frame = 0
        self.anim_total = max(total, 0)
        self.anim_loops = loops

    def _execute_action_op_code(self, op_code, parameters, next_address):
        """Op codes below 0xC0: the entity actions (FF8_EN.exe
        AnimSeq_DispatchActionOpcode @0x504BB0). Only what changes the timeline or the
        entity's own transform is simulated; the rest is already recorded as an event."""
        if op_code == 0x95:                       # reset position (X and Z)
            self.position[0] = 0
            self.position[2] = 0
        elif op_code == 0x9E and len(parameters) >= 2:  # move to an entity's position
            # AddTaskToQueueAnimSeq_Anim9E @0x50F720: a parallel task lerping the whole
            # entity from its resting spot to entity `parameters[0]`'s position over
            # `parameters[1]` frames. The other entity's position lives in the battle,
            # not in the file: the target's assumed spot is used (own slot = stay put).
            slot = parameters[0]
            duration = max(parameters[1], 1)
            if slot == self.context.own_slot:
                target_x, target_z = self.move_anchor
            else:
                target_x = self.context.target_position[0]
                target_z = self.context.target_position[2]
                self._assume(None, f"position of the slot {slot} entity (9E move)",
                             f"({target_x}, {target_z})")
            self.move_task = (0, duration, target_x, target_z)
        elif op_code == 0x9A and parameters:      # background sequence id (0 clears it)
            self.background_seq_id = parameters[0]
        elif op_code == 0xA0 and parameters:      # play animation without pausing
            self._queue_animation(parameters[0], loops=True)
        elif op_code == 0xA3:                     # this sequence becomes the base one
            self.base_seq_id = self.seq_id
            if self.queued_seq_id is not None:
                return self._goto_sequence(self.queued_seq_id, consume_queue=True)
        elif op_code == 0xA4:                     # force the next A0 to restart
            self.anim_frame = self.anim_total
        elif op_code == 0xA7 and parameters:      # goto sequence
            return self._goto_sequence(parameters[0])
        elif op_code == 0xA2:                     # end: chain into the queued/idle sequence
            self.rotation_y = 0
            return self._end_of_sequence()
        elif op_code == _PAUSE_HARD_STOP:         # A9: stop for this frame
            self._stop(STOP_END, "hard stop (A9)")
            return next_address, True
        elif op_code == _PAUSE_RESTORE and parameters:  # AC: restore model, queue, end
            self.rotation_y = 0
            self.hidden_part_mask = 0   # "restore base model": hidden parts come back
            queued = parameters[0]
            if self.follow_chain and self._sequence(queued) is not None:
                # The queued sequence IS what the entity plays next: continue into it
                # (from its start, next frame) instead of cutting the preview short.
                self.pending_seq_id = queued
                return next_address, True
            self._stop(STOP_END, f"restore base model and queue sequence {queued} (AC)")
            return next_address, True
        elif op_code == _PAUSE_YIELD:             # A1
            return next_address, True
        elif op_code == _PAUSE_WAIT and parameters:  # B9: the sequence goes on XX frames later
            # FF8_EN.exe: the B9 handler (0x504C4B) pauses the frame it runs on and stores XX - 1
            # in delayBeforeNextAnimation; AnimSeq_UpdateEntityPerFrame (0x504290) decrements it
            # on each later frame while it is not 0 and runs the sequence again once it is: the
            # next op code runs XX frames after the B9 (B9 01 on the next frame, B9 00 = 256).
            self.wait_frame = (parameters[0] - 1) & 0xFF
            return next_address, True
        elif op_code == 0xBA:                     # advance the animation one frame
            self._advance_animation()
        return next_address, False

    def _goto_sequence(self, seq_id, consume_queue=False):
        """A7 and friends: the pointer moves to another sequence, on the same frame."""
        if self._sequence(seq_id) is None:
            self._stop(STOP_ERROR, f"jump to sequence {seq_id}, which the file does not have")
            return 0, True
        if consume_queue:
            self.queued_seq_id = None
        self.seq_id = seq_id
        return 0, False

    def _end_of_sequence(self):
        """A2: continue into the queued sequence if there is one, else the idle fallback.

        The new sequence starts on the SAME frame. When nothing follows - or when the
        caller asked not to follow the chain - the timeline ends here instead, which is
        what a preview of one sequence wants.
        """
        if self.queued_seq_id is not None:
            return self._goto_sequence(self.queued_seq_id, consume_queue=True)
        if not self.follow_chain:
            self._stop(STOP_END, "end of sequence (A2)")
            return 0, True
        if self._sequence(self.base_seq_id) is None:
            self._stop(STOP_END, f"end of sequence (A2), idle sequence {self.base_seq_id} "
                                 f"is not in this file")
            return 0, True
        if self.base_seq_id in self.chained_seq_id:
            # A2 does not pause, so a sequence handing over to one that hands straight back
            # never gives the frame up: the engine spins on it. Say so instead of letting
            # the op code budget report a vague hang.
            self._stop(STOP_HANG, f"sequence {self.seq_id} ends with A2 into idle sequence "
                                  f"{self.base_seq_id}, which chains back without ever "
                                  f"pausing")
            return 0, True
        self.chained_seq_id.add(self.base_seq_id)
        return self._goto_sequence(self.base_seq_id)

    # ------------------------------------------------- arithmetic and jumps (C0-F3)
    def _execute_vm_op_code(self, op_code, parameters, address, next_address):
        """C0-E5 (arithmetic on current_value) and E6-F3 (jumps): the VM itself
        (FF8_EN.exe computeAnimationSequence @0x50DB40), identical for every sequence
        flavour. This is the part a preview reproduces exactly."""
        if op_code == _BUGGED_SET_ZERO:
            self._stop(STOP_HANG, "E4 never advances the instruction pointer (use C1 00)")
            return next_address, True

        if op_code == 0xE5:  # write current_value somewhere
            if parameters:
                self._write_special(parameters[0], self.current_value)
                if parameters[0] <= 0x77:
                    # An engine variable (or an e5 local) took the value: THIS is what
                    # the computation was for - scratch slots stay quiet, their formula
                    # resurfaces spliced into the write that finally matters.
                    self._value_note = (f"{special_var_name(parameters[0])} ← "
                                        f"{self._formula_text()}")
            return next_address, False

        if op_code >= 0xE6:  # the jumps
            return self._execute_jump(op_code, parameters, address, next_address)

        value = self._read_operand(op_code, parameters)
        operation = op_code & 0xFC
        # The formula, kept in step with the value: a battle read shows its name AND the
        # value it had, so "speed_to_target(2500) - 100" reads at a glance. The VM
        # applies operators strictly left to right, so the accumulated part is
        # parenthesised before the next operator to keep the formula truthful.
        spliced = None
        if (op_code & 3) == 3 and parameters:
            parameter = parameters[0]
            stored = self.slot_expression.get(parameter)
            # A scratch slot stands for the formula stored into it: splice that in
            # (capped - past that, the name(value) fallback stays readable; a plain
            # stored number adds nothing over the value itself).
            if stored is not None and stored != str(value) and len(stored) <= 90:
                spliced = stored
                operand_expression = stored if " " not in stored else f"({stored})"
            else:
                operand_expression = f"{special_var_name(parameter)}({value})"
        else:
            operand_expression = str(value)
        if operation == 0xC0:
            # An assignment takes the operand as-is - a spliced formula needs no parens
            # of its own at the top level.
            self.value_expression = spliced if spliced is not None else operand_expression
        else:
            symbol = _OPERATION_SYMBOL.get(operation, "?")
            accumulated = self.value_expression
            # No-ops stay out of the formula: "x - 0" or "x * 1" only bury the parts
            # that matter (sequences use them as neutral scaffolding all the time).
            # The arithmetic below still runs them - only the formula skips them.
            if ((operand_expression == "0" and symbol in "+-")
                    or (operand_expression == "1" and symbol in "*/")):
                pass
            elif accumulated == "0" and symbol == "+":
                # "0 + x" is just x (the C1 00 / C7 xx accumulator idiom).
                self.value_expression = (spliced if spliced is not None
                                         else operand_expression)
            else:
                if len(accumulated) > 100:  # an assignment-free loop grows it forever
                    accumulated = "…"
                if " " in accumulated:
                    accumulated = f"({accumulated})"
                # "x + -1" is really "x - 1": fold the sign into the operator when the
                # operand is a plain negative literal.
                if (symbol in "+-" and operand_expression.startswith("-")
                        and operand_expression[1:].isdigit()):
                    symbol = "-" if symbol == "+" else "+"
                    operand_expression = operand_expression[1:]
                self.value_expression = f"{accumulated} {symbol} {operand_expression}"
        if operation == 0xC0:
            self.current_value = value
        elif operation == 0xC4:
            self.current_value += value
        elif operation == 0xC8:
            self.current_value -= value
        elif operation == 0xCC:
            self.current_value *= value
        elif operation == 0xD0:
            self.current_value = _c_div(self.current_value, value)
        elif operation == 0xD4:
            self.current_value &= value
        elif operation == 0xD8:
            self.current_value |= value
        elif operation == 0xDC:
            self.current_value ^= value
        elif operation == 0xE0:
            self.current_value = _c_mod(self.current_value, value)
        return next_address, False

    def _read_operand(self, op_code, parameters):
        """The operand of an arithmetic op code, chosen by its two low bits."""
        parameters = bytes(parameters or b"")
        case = op_code & 3
        if case == 0:  # one int16
            return int.from_bytes(parameters[:2], byteorder="little", signed=True)
        if case == 1:  # one signed byte
            return int.from_bytes(parameters[:1], byteorder="little", signed=True)
        if case == 2:  # one unsigned byte
            return parameters[0] if parameters else 0
        return self._read_special(parameters[0] if parameters else 0)

    _JUMP_CONDITION_TEXT = {1: "> 0", 2: ">= 0", 3: "== 0", 4: "!= 0",
                            5: "<= 0", 6: "< 0"}

    def _formula_text(self) -> str:
        """current_value with the formula that built it ("f = v"), or just the value
        when there is no formula to tell."""
        if self.value_expression and self.value_expression != str(self.current_value):
            return f"{self.value_expression} = {self.current_value}"
        return str(self.current_value)

    def _execute_jump(self, op_code, parameters, address, next_address):
        target = get_jump_target(address, op_code, parameters)
        if target is None:
            return next_address, False
        condition_index = (op_code - 0xE6) % 7
        value = self.current_value
        taken = (condition_index == 0
                 or (condition_index == 1 and value > 0)
                 or (condition_index == 2 and value >= 0)
                 or (condition_index == 3 and value == 0)
                 or (condition_index == 4 and value != 0)
                 or (condition_index == 5 and value <= 0)
                 or (condition_index == 6 and value < 0))
        if condition_index != 0:
            self._value_note = (f"if value {self._JUMP_CONDITION_TEXT[condition_index]}"
                                f": {self._formula_text()} → "
                                f"{'taken' if taken else 'not taken'}")
        if not taken:
            return next_address, False
        data = self._sequence(self.seq_id)
        if data is None or not 0 <= target < len(data):
            self._stop(STOP_ERROR, f"jump to offset {target}, outside sequence {self.seq_id}")
            return next_address, True
        return target, False

    # --------------------------------------------------- C3 reads and E5 writes
    def _read_special(self, parameter):
        """C3-family read (FF8_EN.exe AnimSeq_ReadSpecialVar_C3). Anything the file cannot
        answer goes through _assume() so the UI can show what the branch was decided on."""
        context = self.context
        if parameter >= 0x80:
            return self.stack.get(parameter, 0)
        if parameter <= 0x07:
            return self.local_value[parameter]
        if parameter >= 0x78:  # E5_7F_save, indexed backwards from 0x7F
            return self.saved_value[0x7F - parameter]
        if parameter == 0x08:
            # Animation-state control flags (BattleStateControlerFlag bitmask). Once the
            # sequence writes them (E5 08), it owns the value - only the INITIAL value is
            # a battle assumption. Bit 0x10 is the effect code's "ready" signal: unless
            # the context says otherwise it reads as set (and is said so), or every
            # attack sequence would poll it forever with no effect code running.
            value = self.state_flags
            if context.effect_signal_ready and not value & 0x10:
                value |= 0x10
                self._assume(parameter, "effect-code handshake (flag bit 0x10)",
                             "assumed ready")
            if self.state_flags_written:
                return value
            return self._assume(parameter, "animation-state control flags", value)
        if parameter == 0x09:
            return self.anim_frame
        if parameter == 0x0A:
            return self.anim_total
        if parameter == 0x0B:
            return self.base_seq_id
        if parameter == 0x0C:
            return self._assume(parameter, "random value", self.random.randint(0, 32767))
        if parameter == 0x0D:
            return self.position[0]
        if parameter == 0x0E:
            return self.position[1]
        if parameter == 0x0F:
            return self.position[2]
        if parameter in (0x10, 0x11):
            return self._assume(parameter, "speed factor toward the target",
                                self._speed_factor(parameter))
        if parameter == 0x12:
            return self.sine
        if parameter == 0x13:
            return self.cosine
        if parameter == 0x14:
            return self._assume(parameter, "weapon anim word +28", context.weapon_word_28)
        if parameter == 0x15:
            return self._assume(parameter, "weapon anim word +30", context.weapon_word_30)
        if parameter == 0x16:
            return self._assume(parameter, "weapon anim word +32", context.weapon_word_32)
        if parameter == 0x17:
            return self.rotation_y & 0xFFF
        if parameter == 0x18:
            return self._assume(parameter, "target slot", context.target_slot)
        if parameter == 0x19:
            return self._assume(parameter, "target hit flag", 2 if context.target_was_hit else 0)
        if parameter == 0x1A:
            return self._assume(parameter, "angle to the target",
                                context.angle_to_target & 0xFFF)
        if parameter == 0x1B:
            return self._assume(parameter, "own slot", context.own_slot)
        if parameter == 0x1C:
            if context.is_monster:
                return self._assume(parameter, "entity is a monster", 2048)
            facing = 0 if (self.rotation_y & 0xFFF) <= 2048 else 4096
            return self._assume(parameter, "character facing", facing)
        if parameter == 0x1F:
            return self._assume(parameter, "animation status", context.anim_status)
        if parameter == 0x22:
            return self._assume(parameter, "back attack / preemptive", context.back_attack)
        if parameter == 0x23:
            return self._assume(parameter, "camera flag", context.camera_flag)
        if 0x24 <= parameter <= 0x27:
            return self.scale[parameter - 0x24]
        if parameter == 0x28:
            return self._assume(parameter, "GF summon data loaded", context.gf_loaded)
        if parameter == 0x29:
            return self._assume(parameter, "number of targets hit", context.nb_target_hit)
        if parameter == 0x2A:
            return self.anim_speed_factor
        if parameter == 0x2C:
            return self._assume(parameter, "original sceneout X", context.original_scene_out_x)
        if parameter == 0x2E:
            return self._assume(parameter, "another entity alive and free",
                                context.another_entity_free)
        if parameter == 0x33:
            return self._assume(parameter, "encounter id", context.encounter_id)
        if parameter == 0x35:
            return self._assume(parameter, "target effect point 0xF1 Y offset",
                                context.target_effect_y_offset_f1)
        if parameter == 0x36:
            return self._assume(parameter, "target effect point 0xF0 Y offset",
                                context.target_effect_y_offset_f0)
        if parameter == 0x37:
            return self._assume(parameter, "invisibility", context.invisible)
        return 0  # unlisted parameters read 0, like the engine's default case

    def _speed_factor(self, parameter):
        """C3 0x10/0x11: how fast to walk to the target, from how far it is."""
        if self.context.target_is_self:
            return 1000
        speed = _c_div(5000 * self.context.target_distance, 4096)
        if parameter == 0x11:
            speed -= _c_div(2000 * (self.context.own_speed_factor
                                    + self.context.target_speed_factor), 4096)
        return speed

    def _write_special(self, parameter, value):
        """E5 write (FF8_EN.exe AnimSeq_WriteSpecialVar_E5)."""
        if parameter >= 0x78 or parameter <= 0x07:
            # A pure VM scratch slot: remember the formula it now stands for (engine
            # fields like positions keep their own name instead - clearer than a splice).
            self.slot_expression[parameter] = self.value_expression
        if parameter >= 0x80:
            self.stack[parameter] = value
            return
        if parameter <= 0x07:
            self.local_value[parameter] = value
        elif parameter >= 0x78:
            self.saved_value[0x7F - parameter] = value
        elif parameter == 0x08:
            self.state_flags = value
            self.state_flags_written = True
        elif parameter == 0x0B:
            self.base_seq_id = value
        elif parameter == 0x0D:
            self.position[0] = value
        elif parameter == 0x0E:
            self.position[1] = value
        elif parameter == 0x0F:
            self.position[2] = value
        elif parameter == 0x12:
            self.sine = _compute_sin(value)
        elif parameter == 0x13:
            self.cosine = _compute_cos(value)
        elif parameter == 0x17:
            self.rotation_y = value
        elif parameter == 0x20:
            # value > 0 hides part (value - 1), value < 0 shows part (-1 - value)
            if value > 0:
                self.hidden_part_mask |= 1 << (value - 1)
            elif value < 0:
                self.hidden_part_mask &= ~(1 << (-1 - value))
        elif 0x24 <= parameter <= 0x27:
            self.scale[parameter - 0x24] = value
        elif parameter == 0x2A:
            self.anim_speed_factor = value
        elif parameter == 0x2C:
            self.position[0] = value


def _annotate_local_writes(frame_list):
    """Append to each e5[0..7] write note where the slot is next read and what that
    computation feeds - the "what is it FOR" of a stored value (seq 14 of c0m001 parks
    the jump height in e5[2] on frame 0 and only turns it into pos_y from frame 27).

    Only the e5 locals: they are the VM's cross-frame variables. Engine vars (pos_y,
    state_flags...) are consumed by the engine itself, so "never read" would be wrong.
    """
    flat = [(frame.index, command) for frame in frame_list
            for command in frame.command_list if not command.is_background]
    for position, (_frame_index, command) in enumerate(flat):
        if (command.op_code != 0xE5 or not command.value_note
                or not command.parameters or command.parameters[0] > 0x07):
            continue
        slot = command.parameters[0:1]
        suffix = " — never read afterwards"
        for later_position in range(position + 1, len(flat)):
            later_index, later = flat[later_position]
            op_code = later.op_code
            if op_code == 0xE5 and later.parameters[:1] == slot:
                suffix = f" — overwritten on frame {later_index}, unread"
                break
            if (0xC0 <= op_code <= 0xE3 and (op_code & 3) == 3
                    and later.parameters[:1] == slot):
                # Found the read: what does that computation end up feeding? The first
                # noted command after it - an engine write or a branch - names it
                # (scratch hops carry no note and are skipped by construction).
                purpose = ""
                for _frame, feed in flat[later_position + 1:]:
                    if feed.value_note:
                        purpose = (f" ({feed.value_note.split(' ←')[0]})"
                                   if feed.op_code == 0xE5 else " (a branch decision)")
                        break
                suffix = f" — used from frame {later_index}{purpose}"
                break
        command.value_note += suffix


def bake_sequence(vm, sequence_by_id, seq_id, animation_frame_count, context=None,
                  max_frame=600, follow_chain=True, as_background=False) -> BakeResult:
    """Run sequence `seq_id` and return its timeline, one SequenceFrame per battle frame.

    - `vm` is a SequenceVM or a GameData (normalised to the entity VM), as everywhere else.
    - `sequence_by_id` is {id: bytes}; sequence_dict_from_section() builds it from a
      monster's seq_animation_data. Every sequence of the file is needed, not just the one
      previewed: A7 and A2 chain into the others.
    - `animation_frame_count` gives an animation's length in frames - a list, a dict, or a
      callable. That length is what makes the timing real, so pass the model's actual
      animation section.
    - `context` is what the battle would provide (BattleContext); its defaults are used
      when omitted.
    - `max_frame` caps a sequence that never ends. An idle stance is meant to run forever,
      so this is a normal outcome, not an error: the result says STOP_MAX_FRAMES, or
      STOP_LOOP with loop_from set when the whole state repeated (which proves it loops
      rather than merely suggesting it).
    - `follow_chain` False stops at the end of THIS sequence instead of continuing into the
      idle one, for previewing a single sequence in isolation.
    - `as_background` True previews a sequence the way 9A runs it - restarted from its
      first byte every frame. Pass it for the sequences background_sequence_id_set()
      reports, which are written for that and have no terminator.
    """
    context = context or BattleContext()
    if sequence_by_id.get(seq_id) is None:
        return BakeResult([], STOP_ERROR, f"the file has no sequence {seq_id}")

    interpreter = _Interpreter(vm, sequence_by_id, seq_id,
                               _frame_count_function(animation_frame_count), context,
                               follow_chain, as_background)
    frame_list = []
    state_seen = {}
    loop_from = None
    while len(frame_list) < max_frame:
        key = interpreter._state_key()
        if key in state_seen:
            loop_from = state_seen[key]
            interpreter._stop(STOP_LOOP)
            break
        state_seen[key] = len(frame_list)
        frame_list.append(interpreter.run_frame())
        if interpreter.stop_reason is not None:
            break
    else:
        interpreter._stop(STOP_MAX_FRAMES)

    _annotate_local_writes(frame_list)
    return BakeResult(frame_list, interpreter.stop_reason or STOP_MAX_FRAMES,
                      interpreter.stop_detail, loop_from, interpreter.assumption_list,
                      sorted(interpreter.background_used))
