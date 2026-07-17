"""Synthesize a brand-new idle animation (slot 0) for the Shiva monster file.

The motion is generated, not copied: starting from a standing base pose (the
apparition animation frame BASE_POSE_FRAME — the float loop's own pose is bent
over, her summon-finale stance), every bone that Square's own loop animates gets
a new, much subtler sine curve (one breathing cycle per loop plus a faint second
harmonic), phase-staggered by hierarchy depth so the movement ripples through
the torso, arms and hair instead of moving in lock-step.  The root keeps the
float loop's position (her settled battle spot) with a gentle vertical bob so
she keeps floating.  24 frames at 15 fps = a 1.6 s seamless loop.

Tune AMPLITUDE_FACTOR / BOB_RAW below and re-run to taste.

Run from the repo root:  python shiva_new_idle.py
"""
"""
Learned the rig from Square's own float loop (anim 2): measured which bone axes it animates and by how much — 41 bone-axes turned out to be "alive" (torso ~5–10°, arm chains and hair ribbons 20–43°). Animating only those bones guarantees anatomically sensible motion; the trunk stays put.
Generated 24 new frames (1.6 s seamless loop at 15 fps): each live bone-axis gets a sine curve at ~35% of its original amplitude (capped at 12°), plus a faint second harmonic so it doesn't feel metronome-like. The phases are staggered by hierarchy depth (0.45 rad per level), so movement ripples outward through shoulders → arms → hands → ribbon tips like follow-through, instead of everything swinging in lock-step. The root gets a small vertical bob (+ a slight forward/back drift) so she keeps floating.
Wrote it as animation 0 through your existing infrastructure: set_all_bones_matrix per frame, then _recompute_frame_storage_types() (from your 60fps-converter work) to compute the optimal delta bit-widths — so the bit-packed encoding is exactly as compact and well-formed as vanilla. Sequence 1 still loops anim 0, nothing else changed. Backup: c0m071.dat.before_newidle.bak.
Verified by full reload from disk: 24-frame anim 0 parses back, matrices animate, and the four renders above are frames 0/6/12/18 of the saved file.

Tuning to taste
The knobs are at the top of the script — re-run after editing (it regenerates from the base pose each time, but restore c0m071.dat.before_newidle.bak over the file first, or just re-run — it aborts only if the layout is unexpected... actually it will regenerate anim 0 in place safely since it reads the loop from anim 2):

AMPLITUDE_FACTOR = 0.35 — overall energy (0.2 = calmer, 0.5 = livelier)
AMPLITUDE_CAP_RAW = 140 — max per-bone swing (~12°); lower to ~80 if the ribbons feel too active in motion
NB_FRAMES = 24 — loop length (more = slower breathing)
BOB_RAW = 8 — floating bob height
"""
import copy
import math
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "c0m071.dat"

BASE_POSE_ANIM = 1        # apparition
BASE_POSE_FRAME = 35      # standing pose within it
NB_FRAMES = 24            # 1.6 s loop at 15 fps
AMPLITUDE_FACTOR = 0.35   # fraction of the float loop's own amplitude per bone
AMPLITUDE_CAP_RAW = 140   # max swing (raw 4096 = 360 deg) ~ 12 deg
# --- named bone groups (Shiva skeleton, mapped from the standing pose) ---
# Arms: 16-19-26-33 (left) and 18-25-32-39 (right), each ending in a hand with
# five 2-segment fingers.  Back hair: the 3 strands off the head via 21/22/24.
# Mustache: the two long falling ribbons via 20/23 ending at leaves 67/68.
ARM_BONES = {16, 19, 26, 33, 18, 25, 32, 39}
ARM_SEGMENT = {16: 0, 18: 0, 19: 1, 25: 1, 26: 2, 32: 2, 33: 3, 39: 3}
BACK_HAIR_BONES = {21, 28, 35, 46, 22, 29, 36, 47, 24, 31, 38, 49}
MUSTACHE_BONES = {20, 27, 34, 45, 60, 67, 23, 30, 37, 48, 61, 68}
KNEE_BONES = {9, 10}

ARM_SHARE = 0.6             # each arm bone gets >= this share of its twin's amplitude
ARM_FORWARD_RAW = 45        # forward/back pitch swing per real forearm segment (~4 deg)
BACK_HAIR_SHARE = 0.5       # back hair keeps the motion you previously tuned and liked
BACK_HAIR_FORWARD_RAW = 10
MUSTACHE_DAMP = 0.45        # falling ribbons keep only this share of their measured motion
KNEE_BEND_RAW = 50          # one-sided knee flex, deepest when the bob dips;
                            # negative value flips the bend direction
MIN_AMP_RAW = 4             # below this a bone axis stays still (as in the original loop)
BOB_RAW = 30              # vertical bob amplitude (position raw units)
SWAY_RAW = 4              # slight forward/back drift
TWO_PI = 2 * math.pi


def bone_depths(bones):
    depths = []
    for b in bones:
        d, p = 0, b.parent_id
        while p != 0xFFFF:
            d += 1
            p = bones[p].parent_id
        depths.append(d)
    return depths


def main():
    sys.path.insert(0, str(BASE))
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser

    game_data = GameData(str(BASE / "FF8GameData"))
    game_data.load_all()
    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(str(TARGET), game_data)
    enemy.analyse_loaded_data(game_data)

    bones = enemy.bone_data.bones
    loop_anim = enemy.animation_data.animations[2]  # Square's floating loop
    base_frame = enemy.animation_data.animations[BASE_POSE_ANIM].frames[BASE_POSE_FRAME]
    depths = bone_depths(bones)

    # Learn how much the original loop animates each bone/axis
    measured = {}
    for b in range(len(bones)):
        for axis in range(3):
            loop_base = int(loop_anim.frames[0].rotation_vector_data[b][axis].get_rotate_raw())
            deltas = [((int(f.rotation_vector_data[b][axis].get_rotate_raw()) - loop_base + 2048) % 4096) - 2048
                      for f in loop_anim.frames]
            rng = max(deltas) - min(deltas)
            measured[(b, axis)] = min(rng / 2 * AMPLITUDE_FACTOR, AMPLITUDE_CAP_RAW)

    # Twin amplitude per arm segment/axis: the loop favours one arm over the
    # other, so each arm bone borrows from the same segment on the other arm.
    arm_segment_max = {}
    for b in ARM_BONES:
        for axis in range(3):
            key = (ARM_SEGMENT[b], axis)
            arm_segment_max[key] = max(arm_segment_max.get(key, 0), measured[(b, axis)])
    # Same idea for the back-hair strands (grouped by depth as before)
    hair_depth_max = {}
    for b in BACK_HAIR_BONES:
        for axis in range(3):
            key = (depths[b], axis)
            hair_depth_max[key] = max(hair_depth_max.get(key, 0), measured[(b, axis)])

    curves = []  # (bone, axis, center_raw, amplitude_raw, phase, forward, knee)
    for b in range(len(bones)):
        for axis in range(3):
            amp = measured[(b, axis)]
            forward = 0
            if b in MUSTACHE_BONES:
                amp *= MUSTACHE_DAMP
            elif b in ARM_BONES:
                amp = max(amp, ARM_SHARE * arm_segment_max[(ARM_SEGMENT[b], axis)])
                if axis == 0:
                    forward = ARM_FORWARD_RAW
            elif b in BACK_HAIR_BONES:
                amp = max(amp, BACK_HAIR_SHARE * hair_depth_max[(depths[b], axis)])
                if axis == 0:
                    forward = BACK_HAIR_FORWARD_RAW
            knee = KNEE_BEND_RAW if (axis == 0 and b in KNEE_BONES) else 0
            if amp < MIN_AMP_RAW and not forward and not knee:
                continue
            center = int(base_frame.rotation_vector_data[b][axis].get_rotate_raw())
            phase = depths[b] * 0.45 + axis * 0.30 + (b % 7) * 0.25
            curves.append((b, axis, center, amp, phase, forward, knee))

    print(f"Animating {len(curves)} bone axes over {NB_FRAMES} frames")

    # Root position: her settled battle spot (the float loop's), not the
    # apparition frame's mid-flight position.
    base_pos = [loop_anim.frames[0].position[axis].get_pos_raw() for axis in range(3)]
    print("base position (loop):", base_pos,
          "| apparition frame position:", [base_frame.position[a].get_pos_raw() for a in range(3)])
    new_frames = []
    for t in range(NB_FRAMES):
        w = TWO_PI * t / NB_FRAMES
        frame = copy.deepcopy(base_frame)
        frame.position[0].set_pos_raw(base_pos[0])
        frame.position[1].set_pos_raw(base_pos[1] + round(BOB_RAW * math.sin(w)))
        frame.position[2].set_pos_raw(base_pos[2] + round(SWAY_RAW * math.sin(w + 0.8)))
        for b, axis, center, amp, phase, forward, knee in curves:
            value = center + amp * math.sin(w + phase) + 0.25 * amp * math.sin(2 * w + phase * 1.7)
            if forward:
                value += forward * math.sin(w - 0.6)  # trails the bob slightly
            if knee:
                value += knee * (0.5 - 0.5 * math.sin(w))  # one-sided: flexes as the bob dips
            frame.rotation_vector_data[b][axis].rotate_raw(round(value) % 4096)
        frame.set_all_bones_matrix(bones)
        new_frames.append(frame)

    new_idle = copy.deepcopy(enemy.animation_data.animations[0])
    new_idle.frames = new_frames
    new_idle._recompute_frame_storage_types()
    enemy.animation_data.animations[0] = new_idle

    backup = TARGET.with_suffix(".dat.before_newidle.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)
        print(f"Backup written to {backup.name}")
    enemy.write_data_to_file(game_data, str(TARGET))
    print(f"Animations now: {[a.get_nb_frame() for a in enemy.animation_data.animations]}")
    print(f"{TARGET.name} written ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
