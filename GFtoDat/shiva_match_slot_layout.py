"""Give the Shiva monster file the same animation/sequence *shape* as the vanilla
slot owner (c0m071, G-Soldier: 20 animations, 13 sequences).

The engine (or the encounter) can request animation ids and sequence slots that
exist in the vanilla file — e.g. G-Soldier's seq 13 `0E E6 FF` is an arrival
sequence looping run-anim 14 until the party finishes loading.  Requests beyond
our data read garbage and crash a fixed number of frames after battle start.

  - Animations 4..19 are added as copies of the 6-frame floating loop, so any
    unexpected animation id still plays something sane.
  - Every sequence slot 1..13 gets valid content referencing only anims 0-2
    (slots 2 and 7 stay empty: they are empty in every vanilla monster).

Run from the repo root:  python shiva_match_slot_layout.py
"""
import copy
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "c0m071.dat"
NB_ANIMATIONS = 20  # same as vanilla G-Soldier

SEQUENCES = {
    1: "a3 00 e6 ff",                            # idle: base seq, loop anim 0
    3: "00 b8 0d 02 08 b8 0e 02 10 a8 06 a9 e6 ff",  # death: anim 0 + generic sounds + fade
    4: "c3 08 d8 00 01 e5 08 00 a2",             # hit reaction
    5: "c3 08 d8 00 01 e5 08 00 a2",             # hit reaction (2nd slot, as G-Soldier)
    6: "00 a2",                                  # misc: play idle once
    8: "a8 01 a0 00 c3 0c e1 23 e5 7f ba c3 7f c5 ff e5 7f e7 f9 c3 08 d9 08 e5 08 a1 a2",
       # escape (verbatim G-Soldier, only references anim 0)
    9: "00 a2",                                  # misc: play idle once
    10: "bb 01 a2",                              # attack: apparition
    11: "bb 01 a2",                              # attack: apparition (abilities use this)
    12: "bb 02 a2",                              # attack: floating loop (abilities use this)
    13: "00 e6 ff",                              # arrival: loop anim 0 (G-Soldier loops run anim 14)
}
NB_SEQ = 13


def main():
    sys.path.insert(0, str(BASE))
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser

    game_data = GameData(str(BASE / "FF8GameData"))
    game_data.load_all()
    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(str(TARGET), game_data)
    enemy.analyse_loaded_data(game_data)

    anims = enemy.animation_data.animations
    if len(anims) != 4 or [a.get_nb_frame() for a in anims] != [6, 86, 6, 1]:
        sys.exit(f"Unexpected animations {[a.get_nb_frame() for a in anims]} "
                 f"(expected [6, 86, 6, 1]) — aborting.")

    float_loop = anims[0]
    while len(anims) < NB_ANIMATIONS:
        anims.append(copy.deepcopy(float_loop))
    enemy.animation_data.nb_animations = len(anims)

    enemy.seq_animation_data['nb_anim_seq'] = NB_SEQ
    enemy.seq_animation_data['seq_animation_data'] = [
        {"id": i, "data": bytearray(bytes.fromhex(SEQUENCES[i].replace(" ", ""))) if i in SEQUENCES else bytearray()}
        for i in range(1, NB_SEQ + 1)]

    backup = TARGET.with_suffix(".dat.before_slotmatch.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)
        print(f"Backup written to {backup.name}")
    enemy.write_data_to_file(game_data, str(TARGET))
    print(f"Animations: {len(anims)} ({[a.get_nb_frame() for a in anims]})")
    print(f"Sequences: {NB_SEQ} slots, filled: {sorted(SEQUENCES)}")
    print(f"{TARGET.name} written ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
