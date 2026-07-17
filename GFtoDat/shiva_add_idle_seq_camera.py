"""Make Shiva.dat battle-ready: idle animation, animation sequences and camera data.

The model converted from mag184_e.dat has 3 animations: a 1-frame bind pose, the
86-frame summon apparition and a 6-frame floating loop.  The battle engine loops
animation 0 as idle and drives everything else through section-5 sequences, so:

  1. Animations are reordered to [idle (copy of the floating loop), apparition,
     floating loop, bind pose] — a dedicated idle now sits at index 0.
  2. Section 5 gets the standard vanilla sequence layout (same slots as c0m001,
     Blobra, Bite Bug, ...):
        seq 1  = idle       : A3 00 E6 FF        (base seq, loop anim 0)
        seq 3  = death      : anim 0 + generic death sounds + fade out
        seq 4  = hit        : flag + anim 0 + end
        seq 11 = attack     : BB 01 A2           (the summon apparition!)
        seq 12 = attack     : BB 02 A2           (floating loop)
     The default abilities already reference sequences 11/12.
     (The B5 opcode used by vanilla death seqs is skipped: it plays from the
     monster's own AKAO section 9, which is empty in this file.)
  3. Section 6 (camera data) is copied verbatim from c0m001.dat.

Run from the repo root:  python shiva_add_idle_seq_camera.py
"""
import copy
import shutil
import struct
import sys
from pathlib import Path

BASE = Path(__file__).parent
SHIVA_DAT = BASE / "Shiva.dat"
CAMERA_DONOR = BASE / "extracted_files" / "battle" / "c0m001.dat"

IDLE_SEQ = bytes.fromhex("a3 00 e6 ff".replace(" ", ""))
DEATH_SEQ = bytes.fromhex("00 b8 0d 02 08 b8 0e 02 10 a8 06 a9 e6 ff".replace(" ", ""))
HIT_SEQ = bytes.fromhex("c3 08 d8 00 01 e5 08 00 a2".replace(" ", ""))
ATTACK_APPARITION_SEQ = bytes.fromhex("bb 01 a2".replace(" ", ""))
ATTACK_LOOP_SEQ = bytes.fromhex("bb 02 a2".replace(" ", ""))

SEQUENCES = {  # 1-based sequence id -> data (missing ids up to 12 stay empty)
    1: IDLE_SEQ,
    3: DEATH_SEQ,
    4: HIT_SEQ,
    11: ATTACK_APPARITION_SEQ,
    12: ATTACK_LOOP_SEQ,
}
NB_SEQ = 12


def donor_camera_section(path: Path) -> bytearray:
    data = path.read_bytes()
    nb = struct.unpack_from("<I", data, 0)[0]
    pos = [struct.unpack_from("<I", data, 4 + i * 4)[0] for i in range(nb)]
    return bytearray(data[pos[5]:pos[6]])  # section 6 (index 5 in the position table)


def main():
    sys.path.insert(0, str(BASE))
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser

    game_data = GameData(str(BASE / "FF8GameData"))
    game_data.load_all()
    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(str(SHIVA_DAT), game_data)
    enemy.analyse_loaded_data(game_data)

    anims = enemy.animation_data.animations
    frame_counts = [a.get_nb_frame() for a in anims]
    if frame_counts != [1, 86, 6]:
        sys.exit(f"Unexpected animation layout {frame_counts} (expected [1, 86, 6]) — "
                 f"already converted? Aborting, nothing written.")

    # 1. New idle at index 0 (copy of the 6-frame floating loop)
    bind_pose, apparition, float_loop = anims
    enemy.animation_data.animations = [copy.deepcopy(float_loop), apparition, float_loop, bind_pose]
    enemy.animation_data.nb_animations = 4

    # 2. Standard sequence layout
    enemy.seq_animation_data['nb_anim_seq'] = NB_SEQ
    enemy.seq_animation_data['seq_animation_data'] = [
        {"id": seq_id, "data": bytearray(SEQUENCES.get(seq_id, b""))}
        for seq_id in range(1, NB_SEQ + 1)]

    # 3. Camera data from the donor monster
    camera = donor_camera_section(CAMERA_DONOR)
    enemy.section_raw_data[6] = camera

    backup = SHIVA_DAT.with_suffix(".dat.before_idle.bak")
    if not backup.exists():
        shutil.copy2(SHIVA_DAT, backup)
        print(f"Backup written to {backup.name}")

    enemy.write_data_to_file(game_data, str(SHIVA_DAT))
    print(f"Animations: {[a.get_nb_frame() for a in enemy.animation_data.animations]} "
          f"(idle, apparition, loop, bind pose)")
    print(f"Sequences: {NB_SEQ} slots, filled: {sorted(SEQUENCES)}")
    print(f"Camera: {len(camera)} bytes copied from {CAMERA_DONOR.name}")
    print(f"{SHIVA_DAT.name} written ({SHIVA_DAT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
