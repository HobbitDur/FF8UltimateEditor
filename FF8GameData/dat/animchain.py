"""Which animation the sequences play right after an animation's last frame.

A frame-rate conversion adds frames AFTER every original frame, the last one included: the
in-betweens after the last frame cover the tick that frame was shown for. What they should
show depends on what comes next on screen, and nothing in the animation says it:

- the animation loops (the idle): back toward its own first frame;
- the pose stays (a one-shot the sequence waits on, the end of a sequence): the last pose;
- the sequence cuts to another animation (Ward's attack: anim 29 ends, anim 30 starts on the
  next tick): toward THAT animation's first frame. Holding the last pose, or blending back to
  its own start (A0 makes it look like a loop), turns that cut into a pause or a swing back,
  then a jump twice as big as the steps around it.

The sequences are run (sequencebake, the same interpreter as the IfritSeq preview) under a
few battle contexts, and every time an animation's last frame is drawn, what the next frame
draws is recorded. An animation gets a next animation only when every time ends the same way,
on another animation's first frame, or on the first frames of several animations that all start
from the same pose (Selphie's 9, 23 and 29). A sequence ending (A2: the next sequence depends on
the battle, the idle of a weak character is not the normal one), a loop, a held pose, or
followers starting from different poses keep the conversion's own rule.

The root (skeleton position) of an animation is reset at every animation start: it is not
where the model stands, the entity's own position is added to it, and the root counts in the
skeleton's units: the engine draws it at raw * model scale / 256 (header +0x02, 175 for Squall).
When the sequence moves the entity AT the cut (Squall's attack: the run, anim 32, carries him
2078 raw = 1421 forward; anim 34 starts at root -286 = 196 and the sequence puts the entity 1756
forward on the same tick: 1952), the next animation's first root is measured from a new place.
Blending the root toward it draws the model half-way back for one tick (the "teleport" as Squall
reaches the target). Such cuts are listed in `moved_dict` with how far the sequence moved the
entity there (entity-local, E5 0D/0E/0F units): the in-between adds that move, converted to the
skeleton's units, to the next root, so it draws the model half-way through the jump vanilla
makes in one 1/15 s step (531 for Squall) instead of standing still, then jumping it all.
"""
from .sequencebake import (BattleContext, STOP_ERROR, STOP_HANG, background_sequence_id_set,
                           bake_sequence, sequence_dict_from_section)
from .sequencecommand import iter_command

_END = "end"      # something the file cannot tell: a sequence ending, a cut mid-way, a hang
_WRAP = "wrap"    # back to its own first frame: a loop
_HOLD = "hold"    # the same last pose drawn again

# The battle reads that pick branches in attack sequences: the blow landed or not, a monster
# or a character runs it, the random draw.
_CONTEXT_LIST = (
    {},
    {'target_was_hit': False},
    {'is_monster': False},
    {'is_monster': False, 'target_was_hit': False},
    {'seed': 1},
    {'is_monster': False, 'seed': 1},
)
_MAX_FRAME = 600

# The entity moves AT a cut when its position changes there by more than this many units and
# by more than twice its change on the ticks around the cut (a movement loop running through
# the cut is one more step of that movement, not a jump: Squall's slash 36 -> 37).
MOVE_MIN_UNIT = 16
MOVE_AROUND_RATIO = 2


class AnimationChain(dict):
    """{animation id: id of the animation the sequences cut to}, plus `moved_dict`: {id: how far
    the sequence moves the entity at that cut, (lateral, vertical, forward) in E5 0D/0E/0F units,
    or None when the runs disagree or a world-frame 9E move is part of it} for the cuts that also
    move the entity (see the module docstring). A plain dict, for every caller that only needs
    the followers."""

    def __init__(self, *args, moved_dict=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.moved_dict = dict(moved_dict or {})

    @property
    def moved_set(self) -> set:
        return set(self.moved_dict)


def _entity_position(frame):
    """Where the sequence put the entity on that tick: its local offset (E5 0D/0E/0F) and what
    the 9E move task carried it by."""
    return tuple(frame.position) + tuple(frame.move_position)


def _position_change(frame_list, index):
    """How far the entity moved from tick index - 1 to tick index (0 outside the run)."""
    if index < 1 or index >= len(frame_list):
        return 0
    before, after = _entity_position(frame_list[index - 1]), _entity_position(frame_list[index])
    return max(abs(a - b) for a, b in zip(before, after))


def _cut_move(frame_list, index):
    """(lateral, vertical, forward) the sequence moved the entity by from tick `index` to the
    next one, in its local E5 0D/0E/0F units; None when a world-frame 9E move is part of it
    (its direction depends on the battle, not on the entity's facing)."""
    before, after = frame_list[index], frame_list[index + 1]
    if tuple(before.move_position) != tuple(after.move_position):
        return None
    return tuple(b - a for a, b in zip(before.position, after.position))


def entity_moves_at_cut(frame_list, index) -> bool:
    """Whether the sequence moves the entity between tick `index` (an animation's last frame)
    and the next one (the next animation's first frame) by a jump, not by a running movement."""
    cut = _position_change(frame_list, index + 1)
    around = max(_position_change(frame_list, index), _position_change(frame_list, index + 2))
    return cut > max(MOVE_MIN_UNIT, MOVE_AROUND_RATIO * around)


def _played_animation_set(vm, data: bytes) -> set:
    played = set()
    for _address, op_code, parameters in iter_command(vm, data):
        if parameters is None:
            break
        if op_code < 0x80:
            played.add(op_code)
        elif op_code == 0xA0 and parameters:
            played.add(parameters[0])
    return played


def _record(frame_list, outcome_dict, moved_dict=None):
    for index, frame in enumerate(frame_list):
        anim_id = frame.anim_id
        if anim_id is None or frame.anim_total < 1 or frame.anim_frame != frame.anim_total - 1:
            continue
        if index + 1 >= len(frame_list):
            outcome = _END
        else:
            following = frame_list[index + 1]
            if following.anim_id == anim_id and following.anim_frame == frame.anim_frame:
                outcome = _HOLD
            elif following.anim_id == anim_id and following.anim_frame == 0:
                outcome = _WRAP
            elif following.anim_id is None or following.anim_frame != 0:
                outcome = _END
            elif following.seq_id != frame.seq_id and any(
                    command.op_code == 0xA2 for command in following.command_list + frame.command_list):
                outcome = _END  # the sequence ended: the next one is the battle's choice
            else:
                outcome = following.anim_id
                if moved_dict is not None and entity_moves_at_cut(frame_list, index):
                    move = _cut_move(frame_list, index)
                    if anim_id in moved_dict and moved_dict[anim_id] != move:
                        move = None  # the contexts move it differently: no single in-between fits
                    moved_dict[anim_id] = move
        outcome_dict.setdefault(anim_id, set()).add(outcome)


def _pose_key(frame):
    """The pose a frame draws, angles folded onto one turn (4096 raw units)."""
    return (tuple(int(position.get_pos_raw()) for position in frame.position),
            tuple(int(rotation.get_rotate_raw()) % 4096
                  for bone in frame.rotation_vector_data for rotation in bone))


def get_animation_chain_dict(vm, seq_animation_data, animation_list, group_by_pose: bool = True) -> dict:
    """{animation id: id of the animation drawn on the tick after its last frame}, for the
    animations that are always followed by the same pose: one other animation, or several that
    start from the same pose (the lowest id stands for them).

    animation_list: the animations of the model converted: their lengths time the run, their
    first frames tell followers apart. group_by_pose False keeps only a single follower: a
    character's body and weapon are converted one at a time and must take the same decision,
    and two animations starting alike in one of them may not in the other (Ward's 10).
    Returns an AnimationChain: its `moved_dict` lists the cuts where the sequence also moves the
    entity under any of the battle contexts, with the move. It is decided on the sequences only, so a
    character's body and weapon take the same decision there too."""
    animation_frame_count = [len(animation.frames) for animation in animation_list]

    def first_pose(anim_id):
        if 0 <= anim_id < len(animation_list) and animation_list[anim_id].frames:
            return _pose_key(animation_list[anim_id].frames[0])
        return ('no frame', anim_id)

    sequence_by_id = sequence_dict_from_section(seq_animation_data)
    if not sequence_by_id:
        return {}
    background = background_sequence_id_set(vm, sequence_by_id)
    outcome_dict = {}
    moved_dict = {}
    for seq_id, data in sequence_by_id.items():
        if not data or seq_id in background:
            continue
        for options in _CONTEXT_LIST:
            try:
                result = bake_sequence(vm, sequence_by_id, seq_id, animation_frame_count,
                                       BattleContext(**options), max_frame=_MAX_FRAME, follow_chain=True)
            except Exception:
                result = None
            if result is None or result.stop_reason in (STOP_ERROR, STOP_HANG):
                # What this sequence does is unknown: none of its animations gets a follower
                for anim_id in _played_animation_set(vm, data):
                    outcome_dict.setdefault(anim_id, set()).add(_END)
                break
            _record(result.frame_list, outcome_dict, moved_dict)
    chain_dict = AnimationChain()
    for anim_id, outcome_set in outcome_dict.items():
        if not all(isinstance(outcome, int) and outcome != anim_id for outcome in outcome_set):
            continue
        if len(outcome_set) == 1 or (group_by_pose and len({first_pose(outcome) for outcome in outcome_set}) == 1):
            chain_dict[anim_id] = min(outcome_set)
    chain_dict.moved_dict = {anim_id: move for anim_id, move in moved_dict.items() if anim_id in chain_dict}
    return chain_dict


def analyse_animation_chain(game_data, monster) -> dict:
    """get_animation_chain_dict for a loaded entity: its own sequences, or for a character body
    those of the weapon next to it (animloopdetector.analyse_animation_usage reads the same
    one), timed with the entity's own animation lengths. {} when nothing could be read.
    A character file (body dXc, weapon dXw) keeps single followers only (get_animation_chain_dict)."""
    import pathlib
    from .animloopdetector import find_character_weapon_file_list
    animation_list = monster.animation_data.animations
    name = pathlib.Path(getattr(monster, 'origin_path', "") or "").name.lower()
    group_by_pose = not (len(name) > 2 and name[0] == 'd' and name[2] in 'cw')
    seq_animation_data = getattr(monster, 'seq_animation_data', None)
    if (seq_animation_data or {}).get('seq_animation_data'):
        return get_animation_chain_dict(game_data, seq_animation_data, animation_list, group_by_pose)
    from .monsteranalyser import MonsterAnalyser  # imported late: heavy and only needed here
    for weapon_file in find_character_weapon_file_list(getattr(monster, 'origin_path', "")):
        try:
            weapon = MonsterAnalyser(game_data)
            weapon.load_file_data(str(weapon_file), game_data)
            weapon.analyse_loaded_data(game_data)
        except Exception:  # garbage weapon file (d0w007): try the next one
            continue
        if (weapon.seq_animation_data or {}).get('seq_animation_data'):
            return get_animation_chain_dict(game_data, weapon.seq_animation_data, animation_list, group_by_pose)
    return {}
