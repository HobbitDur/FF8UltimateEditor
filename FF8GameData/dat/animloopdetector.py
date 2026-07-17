"""Tell whether a model animation loops or is played once, by reading the sequence section.

Nothing in the animation data itself says it: Battle_ReadAnimation (FF8_EN.exe @0x508F90)
stops as soon as current_frame reaches total_frames and never wraps around, and the
animation command struct only carries speed flags. The answer lives in the animation
sequence section (section 5 for a monster), which is the byte-code the battle engine
runs for the entity. Three patterns matter (AnimSeq_DispatchActionOpcode @0x504BB0,
AnimSeq_UpdateEntityPerFrame @0x504290):

- a bare op code < 0x80 queues the animation and pauses the sequence until it ends,
  so the animation is played exactly once;
- A0 XX queues animation XX without pausing the sequence, and the engine re-queues it
  from frame 0 as soon as it ends: it loops;
- a bare op code sitting inside a backward jump is executed again on every iteration,
  so it loops too. This is how idle stances are written, e.g. GIM52A (c0m001) sequence 1
  is A3 / 00 / E6 FF, the E6 FF jumping -1 byte back onto the "play animation 0" op code.

An animation can be both (looped by the idle sequence, played once by another one).

A character body (dXcYYY) has no sequence section of its own: the program driving it is
in its weapon file (dXwYYY), which is why get_animation_kind_dict_from_weapon_file exists.
Every weapon of a character carries a byte-for-byte identical sequence section, so any of
them gives the same answer.
"""
import pathlib

# The byte walk lives in sequencecommand: the ONE way to decode a sequence, shared with
# IfritSeq's analyser and the splitter. Reading a sequence two slightly different ways is
# exactly how a sequence ends up described one way and rewritten another (see that
# module's docstring) - import from sequencecommand, never re-implement the walk.
from .sequencecommand import iter_command as _read_sequence, get_jump_target

ANIM_LOOP = "loop"
ANIM_ONE_SHOT = "one_shot"
ANIM_BOTH = "both"
ANIM_UNUSED = "unused"


def _backward_jump_list(command_list):
    """[(target, jump_address)] of every jump going back, ie. the loop bodies."""
    jump_list = []
    for address, op_code, parameters in command_list:
        target = get_jump_target(address, op_code, parameters)
        if target is not None and target <= address:
            jump_list.append((target, address))
    return jump_list


def get_animation_kind_dict(game_data, seq_animation_data: dict, nb_animation: int) -> dict:
    """{animation id: ANIM_LOOP | ANIM_ONE_SHOT | ANIM_BOTH | ANIM_UNUSED}.

    Returns an empty dict when the answer cannot be trusted, and the caller then has to
    ask the user instead of silently smoothing the wrong animations:
    - the entity has no sequence section (a character body, see the module docstring);
    - the section read as a sequence one plays animations that do not exist, which means
      it is not really a sequence section. It happens on d7c016 (Edea), whose 11-section
      layout is not the monster one the analyser falls back to.
    """
    sequence_list = seq_animation_data.get('seq_animation_data', []) if seq_animation_data else []
    if not sequence_list:
        return {}

    looped = {}    # animation id -> set of sequence ids
    one_shot = {}
    jump_seq = {}  # sequence id -> sequence ids it jumps to (A7)
    anim_in_seq = {}

    for sequence in sequence_list:
        seq_id = sequence['id']
        command_list = list(_read_sequence(game_data, bytes(sequence['data'])))
        backward_jump_list = _backward_jump_list(command_list)
        for address, op_code, parameters in command_list:
            if op_code < 0x80:
                anim_in_seq.setdefault(seq_id, set()).add(op_code)
                in_loop = any(start <= address <= end for start, end in backward_jump_list)
                target_dict = looped if in_loop else one_shot
                target_dict.setdefault(op_code, set()).add(seq_id)
            elif op_code == 0xA0 and parameters:
                looped.setdefault(parameters[0], set()).add(seq_id)
            elif op_code == 0xA7 and parameters:
                jump_seq.setdefault(seq_id, set()).add(parameters[0])

    # A sequence can also loop by jumping to another one that jumps back (A7), everything
    # it plays then repeats forever as well.
    for seq_id in _sequence_on_cycle_list(jump_seq):
        for anim_id in anim_in_seq.get(seq_id, set()):
            looped.setdefault(anim_id, set()).add(seq_id)
            if anim_id in one_shot:
                one_shot[anim_id].discard(seq_id)
                if not one_shot[anim_id]:
                    del one_shot[anim_id]

    if any(anim_id >= nb_animation for anim_id in set(looped) | set(one_shot)):
        return {}

    kind_dict = {}
    for anim_id in range(nb_animation):
        if anim_id in looped and anim_id in one_shot:
            kind_dict[anim_id] = ANIM_BOTH
        elif anim_id in looped:
            kind_dict[anim_id] = ANIM_LOOP
        elif anim_id in one_shot:
            kind_dict[anim_id] = ANIM_ONE_SHOT
        else:
            kind_dict[anim_id] = ANIM_UNUSED
    return kind_dict


def _sequence_on_cycle_list(jump_seq: dict) -> set:
    on_cycle = set()
    for start in jump_seq:
        seen = set()
        to_visit = [start]
        while to_visit:
            current = to_visit.pop()
            for next_seq in jump_seq.get(current, ()):
                if next_seq == start:
                    on_cycle.add(start)
                elif next_seq not in seen:
                    seen.add(next_seq)
                    to_visit.append(next_seq)
    return on_cycle


def get_slowable_animation_id_set(game_data, seq_animation_data: dict) -> set:
    """Animations the engine can play in slow motion (Slow status).

    It matters because Slow makes the engine compute the frame count as 2 * nb_frame - 1
    in a byte, so a slowable animation cannot go over 128 frames (see
    FF8GameData/dat/animsplitter.py). Slow and Haste are only applied while the entity
    runs its BASE sequence (FF8_EN.exe Battle_QueueAnimation @0x509520 checks
    currentAnimSeqId == basedAnimSeq), and the A3 op code is what marks the sequence
    currently running as the base one. So only what an A3 sequence plays can be slowed:
    an idle stance normally, not a loop inside an attack sequence.
    """
    slowable = set()
    for sequence in (seq_animation_data or {}).get('seq_animation_data', []):
        command_list = _read_sequence(game_data, bytes(sequence['data']))
        command_list = list(command_list)
        if not any(op_code == 0xA3 for _, op_code, _ in command_list):
            continue
        for _, op_code, parameters in command_list:
            if op_code < 0x80:
                slowable.add(op_code)
            elif op_code == 0xA0 and parameters:
                slowable.add(parameters[0])
    return slowable


def find_character_weapon_file_list(character_file_path) -> list:
    """The weapon files sitting next to a character body file (d0c000.dat -> d0w*.dat).

    The first character of the name is 'd' and the second one is the character id, so
    Squall's body d0c000.dat is driven by any of d0w000.dat ... d0w007.dat.
    """
    path = pathlib.Path(character_file_path)
    name = path.name.lower()
    if len(name) < 4 or not name.startswith('d') or name[2] != 'c':
        return []
    weapon_prefix = name[:2] + 'w'
    if not path.parent.is_dir():
        return []
    return sorted(file for file in path.parent.iterdir()
                  if file.is_file() and file.name.lower().startswith(weapon_prefix)
                  and file.name.lower().endswith('.dat'))


def get_animation_kind_dict_from_weapon_file(game_data, weapon_file_path, nb_animation: int) -> dict:
    """Classify a character's animations by reading the sequences of one of its weapons.

    nb_animation is the animation count of the BODY: the animation ids the weapon plays
    index the body animations (and the weapon's own ones, the engine reads the same id in
    both, see Battle_QueueAnimation @0x509520). Returns {} if the file cannot be used.
    """
    return get_animation_usage_from_weapon_file(game_data, weapon_file_path, nb_animation)[0]


def get_animation_usage_from_weapon_file(game_data, weapon_file_path, nb_animation: int) -> tuple:
    """(kind dict, slowable id set) of a character, read from one of its weapon files."""
    from .monsteranalyser import MonsterAnalyser  # imported late: heavy and only needed here
    weapon = MonsterAnalyser(game_data)
    weapon.load_file_data(str(weapon_file_path), game_data)
    weapon.analyse_loaded_data(game_data)
    return (get_animation_kind_dict(game_data, weapon.seq_animation_data, nb_animation),
            get_slowable_animation_id_set(game_data, weapon.seq_animation_data))


def analyse_animation_usage(game_data, monster) -> dict:
    """How the sequences use the animations of a loaded entity.

    {'kind_dict': {anim id: kind}, 'slowable_set': {anim id}, 'source': file read}

    A character body has no sequence section: the program driving it — and telling which
    of its animations the idle plays, hence which ones Slow can reach — is in its weapon
    file, so the weapon sitting next to it is read instead. 'source' is empty when the
    entity carries its own sequences, and 'kind_dict' is empty when nothing could be read.
    """
    nb_animation = monster.animation_data.nb_animations
    seq_animation_data = getattr(monster, 'seq_animation_data', None)
    kind_dict = get_animation_kind_dict(game_data, seq_animation_data, nb_animation)
    if kind_dict:
        return {'kind_dict': kind_dict,
                'slowable_set': get_slowable_animation_id_set(game_data, seq_animation_data),
                'source': ""}

    for weapon_file in find_character_weapon_file_list(getattr(monster, 'origin_path', "")):
        try:
            kind_dict, slowable_set = get_animation_usage_from_weapon_file(
                game_data, weapon_file, nb_animation)
        except Exception:  # garbage weapon file (d0w007): try the next one
            continue
        if kind_dict:
            return {'kind_dict': kind_dict, 'slowable_set': slowable_set,
                    'source': weapon_file.name}
    return {'kind_dict': {}, 'slowable_set': set(), 'source': ""}


def is_looping(kind) -> bool:
    """Should the last frame be interpolated back to the first one?

    True for a looping animation, and for an animation that is both looped and played
    once: those are idle stances, nearly cyclic already, so smoothing the wrap costs a
    1 to 3 frame tail on the one-shot use but keeps the loop itself smooth.
    """
    return kind in (ANIM_LOOP, ANIM_BOTH)
