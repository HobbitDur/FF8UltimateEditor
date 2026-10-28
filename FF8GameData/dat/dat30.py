"""Convert a battle model (.dat) to real 30 fps, for FFNx True30FPS.

Under True30FPS with 30 fps on, FFNx runs every battle model's animation reader and sequence
VM on every 30 Hz host frame and expects EVERY battle file to be converted (there is no
marker in the file: an unconverted file plays twice too fast). Study:
D:/FFNxMenu30fps/gf_study/DAT30FPS_STUDY.md.

What a conversion does, for one file (monster c0m, character body dXc, weapon dXw, Edea
d7c016, reduced weapon d1w/d9w):

1. Section 3 (animations): an n-frame animation holds the VM for exactly n ticks, so it gets
   exactly 2n frames (Animation.create_interpolated_frames: in-betweens, then the last pose
   held once more for a one-shot animation, or the in-between back to frame 0 for a loop). A
   single-pose animation gets its pose twice. The frame count is a byte: an animation over
   127 frames is split with the animsplitter (monsters only - a character body and its
   weapons share the animation ids, see IfritManager). The Slow-safe limit of 128 frames no
   longer applies: on a converted model FFNx emulates Slow by holding each frame for two
   host frames instead of letting the engine double the frame count in a byte.
2. The sequences (seqrewrite30): every tick count x2, every per-tick step /2...
3. The extra single-animation block (character body section 7, weapon section 8, Edea
   section 10): the battle-entry animation, swapped in at battle start
   (initAnimationSequenceAtStartBattle 0x5029A8/0x5029C9) and played by sequence 8 - doubled
   like section 3 (one-shot: it ends on AC).
4. The camera (monster section 6, character section 5): every keyframe duration x2
   (FF8GameData.dat.camera30) - FFNx plays every battle camera at 30 Hz too. A block that would
   last over 2047 ticks refuses the whole file.
5. Section 4 (dynamic textures) is left alone: opcode 80 steps it once per call, and the
   sequence rewrite keeps the vanilla call rate everywhere (an 80 in a smoothed tick loop is a
   per-tick event gated on the counter parity, a fallback loop keeps A1 A1, a background
   sequence runs at 15 Hz behind its toggle), so the speed byte keeps its meaning (the study's
   "speed 8 -> 4" only holds for a loop whose 80 would fire on every 30 Hz tick, which the
   rewrite never produces). Stats, AI and sounds are left alone.

ORDER of the section 3 split and the section 5 rewrite: the sequences are rewritten FIRST,
on the vanilla byte-code the rules were made for (and verified against), then a too-long
animation is split and the splitter inserts the part ids after each bare op code playing it.
The insertion is purely structural (a bare op code waits for its animation, the parts play
back to back in the same ticks) and the relinker keeps every jump of the rewrite pointing at
the same command, so the two compose; tests/test_dat30.py checks it by baking the result.

Idempotency: nothing is written into the file to recognise a converted one (offset tables
stay vanilla-shaped). looks_already_converted() is a cheap heuristic for a WARNING only.
"""
import copy

from . import interpolation
from .animloopdetector import is_looping, ANIM_UNUSED
from .animsplitter import (MAX_ANIMATION_FRAME, can_split_animation, get_nb_part_needed,
                           split_and_convert_animation)
from .seqrewrite30 import rewrite_seq_animation_data
from . import camera30

FACTOR = 2

# Section index of the extra single-animation block, by entity type name.
_EXTRA_ANIMATION_SECTION = {"CHARACTER": 7, "WEAPON": 8, "CHARACTER_NO_WEAPON": 10}


def get_camera_section_index(monster):
    """Section index of the per-entity camera collection (monster 6, character 5), or None."""
    from .monsteranalyser import MonsterAnalyser
    layout = MonsterAnalyser.SECTION_INDEX_BY_ENTITY.get(getattr(monster, "entity_type", None), {})
    index = layout.get('camera')
    if index is None or index >= len(monster.section_raw_data):
        return None
    return index


def _camera_collection(monster):
    index = get_camera_section_index(monster)
    if index is None or len(monster.section_raw_data[index]) < 6:
        return index, None
    return index, camera30.parse_camera_collection(bytes(monster.section_raw_data[index]))


def plan_camera(monster, factor: int = FACTOR) -> str:
    """Why the camera section cannot be converted ("" when it can, or when there is none)."""
    try:
        index, collection = _camera_collection(monster)
    except ValueError as error:
        return f"the camera section does not read as a camera collection ({error})"
    if collection is None:
        return ""
    return "; ".join(camera30.collection_problem_list(collection, factor))


def convert_camera_section(monster, factor: int = FACTOR):
    """Multiply every keyframe duration of the model's camera section, in place. Returns the
    CameraConversionReport, or None when the model has no camera."""
    index, collection = _camera_collection(monster)
    if collection is None:
        return None
    report = camera30.CameraConversionReport()
    camera30.convert_collection(collection, factor, report)
    monster.section_raw_data[index] = bytearray(collection.get_bytes())
    return report


def camera_looks_already_converted(monster, factor: int = FACTOR) -> bool:
    try:
        _index, collection = _camera_collection(monster)
    except ValueError:
        return False
    return camera30.collection_looks_converted(collection, factor)


def get_extra_animation_section_index(monster):
    return _EXTRA_ANIMATION_SECTION.get(getattr(monster.entity_type, "name", ""))


def _same_pose(frame_a, frame_b) -> bool:
    for axis in range(3):
        if frame_a.position[axis].get_pos_raw() != frame_b.position[axis].get_pos_raw():
            return False
    for rotation_a, rotation_b in zip(frame_a.rotation_vector_data, frame_b.rotation_vector_data):
        for axis in range(3):
            if int(rotation_a[axis].get_rotate_raw()) != int(rotation_b[axis].get_rotate_raw()):
                return False
    return True


def looks_already_converted(monster, kind_dict=None) -> bool:
    """A guess, for a warning only: does this file look like it was already converted?

    A converted file has an even frame count on every animation, and its one-shot animations
    end on their last pose held twice. Vanilla files almost always have odd counts somewhere,
    and seldom end on a repeated pose. Never use this to refuse a conversion.
    """
    animation_list = [animation for animation in monster.animation_data.animations
                      if len(animation.frames) >= 2]
    if len(animation_list) < 3:
        return False
    if any(len(animation.frames) % 2 for animation in animation_list):
        return False
    one_shot = [animation for anim_id, animation in enumerate(monster.animation_data.animations)
                if len(animation.frames) >= 2
                and not is_looping((kind_dict or {}).get(anim_id, ANIM_UNUSED))]
    if not one_shot:
        return True
    nb_held = sum(1 for animation in one_shot
                  if _same_pose(animation.frames[-1], animation.frames[-2]))
    return nb_held * 2 >= len(one_shot)


def _double_animation(animation, bones, smooth_loop, mode):
    """2n frames for n (n >= 1)."""
    if len(animation.frames) == 1:
        animation.frames.append(copy.deepcopy(animation.frames[0]))
        animation._recompute_frame_storage_types()
        animation.original_tail = b""
        return
    animation.create_interpolated_frames(bones, FACTOR, smooth_loop, mode=mode)


def double_animation(animation, bones, smooth_loop: bool = False, mode=interpolation.LINEAR):
    """2n frames for an n-frame animation (one-shot: the last pose held once more; loop: the
    in-between back to frame 0), for the anim sets outside a model (r0win poses...)."""
    _double_animation(animation, bones, smooth_loop, mode)


def same_pose(frame_a, frame_b) -> bool:
    return _same_pose(frame_a, frame_b)


def plan_animation_list(game_data, monster, kind_dict, allow_split: bool) -> tuple:
    """([(anim id, smooth_loop, needs_split)], [(anim id, reason)]) without touching anything."""
    plan_list, skipped_list = [], []
    for anim_id, animation in enumerate(monster.animation_data.animations):
        nb_frame = len(animation.frames)
        if nb_frame == 0:
            continue
        smooth_loop = is_looping(kind_dict.get(anim_id, ANIM_UNUSED))
        if nb_frame * FACTOR <= MAX_ANIMATION_FRAME:
            plan_list.append((anim_id, smooth_loop, False))
            continue
        if not allow_split:
            skipped_list.append((anim_id, f"{nb_frame} frames: too long once converted (limit "
                                          f"{MAX_ANIMATION_FRAME}), and it cannot be split here"))
            continue
        nb_part = get_nb_part_needed(nb_frame, FACTOR, smooth_loop, MAX_ANIMATION_FRAME)
        if nb_part < 2:
            skipped_list.append((anim_id, f"{nb_frame} frames: cannot be cut in parts small enough"))
            continue
        can_split, reason = can_split_animation(game_data, monster.seq_animation_data,
                                                monster.animation_data, anim_id, nb_part)
        if not can_split:
            skipped_list.append((anim_id, f"{nb_frame} frames, cannot be split: {reason}"))
            continue
        plan_list.append((anim_id, smooth_loop, True))
    return plan_list, skipped_list


def convert_extra_animation_block(monster, mode=interpolation.LINEAR) -> int:
    """Double the extra single-animation block of a character/weapon. Returns how many
    animations it held (0 when the file has none)."""
    from ..monsterdata import AnimationSection
    index = get_extra_animation_section_index(monster)
    if index is None or index >= len(monster.section_raw_data):
        return 0
    # Once parsed (an editor shows it), the file is saved from its entrance_animation_data:
    # convert that very object, or the save would write the unconverted one back.
    section = getattr(monster, 'entrance_animation_data', None)
    if section is None:
        raw = bytes(monster.section_raw_data[index])
        if len(raw) < 8:
            return 0
        section = AnimationSection()
        section.analyze(raw, monster.bone_data)
    if not section.animations:
        return 0
    for animation in section.animations:
        # the battle-entry animation is played once and ends on AC: hold its last pose
        _double_animation(animation, monster.bone_data.bones, False, mode)
    monster.section_raw_data[index] = section.to_binary()
    return len(section.animations)


def convert_monster_to_real30(game_data, monster, kind_dict: dict, allow_split: bool = True,
                              mode=interpolation.LINEAR) -> dict:
    """Convert one loaded MonsterAnalyser in memory. Nothing is touched when an animation
    cannot make it ('skipped_list' not empty).

    kind_dict: {anim id: loop kind} read from the sequences that drive this model (the weapon's
    for a character body), BEFORE anything is rewritten.
    Returns {'nb_converted', 'split_list', 'skipped_list', 'sequence_report', 'nb_extra',
    'camera_report'}. A camera that cannot be converted is listed in 'skipped_list' as
    ('camera', reason), and nothing is touched either.
    """
    report = {'nb_converted': 0, 'split_list': [], 'skipped_list': [], 'sequence_report': None,
              'nb_extra': 0, 'camera_report': None}
    camera_problem = plan_camera(monster)
    if camera_problem:
        report['skipped_list'].append(('camera', camera_problem))
        return report
    has_animation = bool(monster.animation_data.animations) and bool(monster.bone_data.bones)
    plan_list = []
    if has_animation:
        plan_list, report['skipped_list'] = plan_animation_list(game_data, monster, kind_dict,
                                                                allow_split)
        if report['skipped_list']:
            return report

    # 1. the sequences, on the vanilla byte-code
    sequence_list = (monster.seq_animation_data or {}).get('seq_animation_data', [])
    if sequence_list:
        report['sequence_report'] = rewrite_seq_animation_data(game_data, monster.seq_animation_data)

    # 2. the animations (a split inserts the part ids into the rewritten sequences)
    bones = monster.bone_data.bones if has_animation else []
    for anim_id, smooth_loop, needs_split in plan_list:
        animation = monster.animation_data.animations[anim_id]
        if not needs_split:
            _double_animation(animation, bones, smooth_loop, mode)
            report['nb_converted'] += 1
            continue
        nb_frame = len(animation.frames)
        split_report = split_and_convert_animation(game_data, monster.animation_data,
                                                   monster.seq_animation_data, bones, anim_id,
                                                   FACTOR, smooth_loop, MAX_ANIMATION_FRAME, mode)
        report['split_list'].append((anim_id, nb_frame, split_report['nb_part'],
                                     split_report['new_id_list']))
        report['nb_converted'] += split_report['nb_part']

    # 3. the battle-entry block
    if has_animation:
        report['nb_extra'] = convert_extra_animation_block(monster, mode)

    # 4. the camera (checked before anything was touched: plan_camera)
    report['camera_report'] = convert_camera_section(monster)
    return report
