"""Which audio-archive entry a sequence sound command actually plays.

The sound op codes (97/98/B5/B6/B8) carry a one-byte sound id whose meaning depends on
the op code - verified in FF8_EN.exe linkedToSoundAnimSeq @0x505AB0 and the flag each
dispatcher case pushes for it (@0x505170-0x5051B9: B5/B6 push 0, B8 pushes 1, 97 pushes
0x80, 98 pushes 0x81; bit 0x80 = check-miss, low bits = global-vs-actor):
  - B5/B6/97 play an ACTOR sound: BdPlayActorSE @0x5015A0 looks the id (0..6) up in
    BattleActorSoundTable.sound[com_id][id] (stru_B8A418 @0xB8A418, int[160][7] of world
    ids), then GetSoundID_ForWorld @0x46B120 turns the world id into an audio.dat index;
  - B8/98 play a GLOBAL sound: BdPlaySy passes the byte to GetSoundID_ForWorld, where a
    value under 10000 is category 0 and maps to itself - the byte IS the audio.dat index;
  - on a MISSED attack, 97/98 substitute the fixed miss sound 0x15|0xA = audio id 31.
    The preview's bake assumes the attack lands (BattleContext.target_was_hit), so they
    resolve through their normal path here.

The actor table lives pre-decoded in battle_actor_sound.json: `actor_sound_slots` holds
the FULL 7 slots per actor (null = empty slot) so a B5 id N indexes slot N directly -
the older `actor_sounds` key (kept for Julia's used-by column) drops empty slots and
would misalign a modded row with a hole in it. Table keys are exe com ids: 0-10 are the
party characters, monsters are 16 + their c0m file number.

No Qt and no audio here: this module only answers "which entry", so it can be tested
headless; JuliaManager owns the archive and the panel owns the playback.
"""
import json
import ntpath
import os
import re

SOUND_OP_CODES = (0x97, 0x98, 0xB5, 0xB6, 0xB8)
_ACTOR_SOUND_OPS = (0xB5, 0xB6, 0x97)
NB_ACTOR_SLOT = 7


def actor_key_for_file(file_name):
    """The BattleActorSoundTable row (exe com id) for a battle file name, or None.

    c0mNNN.dat (monster) -> 16 + NNN; dXc/dXw (character body / weapon, X hex) -> X.
    """
    name = ntpath.basename(file_name or "").lower()  # splits on both \ and / on every OS
    match = re.match(r"c0m(\d{3})", name)
    if match:
        return 16 + int(match.group(1))
    match = re.match(r"d([0-9a-f])[cw]", name)
    if match:
        return int(match.group(1), 16)
    return None


class SequenceSoundResolver:
    """audio.dat indices for the sound commands of ONE entity's sequences."""

    def __init__(self, game_data, file_name):
        self.actor_key = actor_key_for_file(file_name)
        self._slot_list = [None] * NB_ACTOR_SLOT
        try:
            path = os.path.join(game_data.resource_folder_json, "battle_actor_sound.json")
            with open(path, encoding="utf-8") as f:
                slots = json.load(f)["actor_sound_slots"]
            row = slots.get(str(self.actor_key))
            if row:
                self._slot_list = list(row) + [None] * (NB_ACTOR_SLOT - len(row))
        except (OSError, KeyError, ValueError):
            pass  # no table: actor sounds resolve to None, global ones still work

    def resolve(self, op_code, parameters):
        """The audio.dat index this command plays, or None (not a sound / empty slot)."""
        if op_code not in SOUND_OP_CODES or not parameters:
            return None
        sound_id = parameters[0]
        if op_code in _ACTOR_SOUND_OPS:
            if sound_id >= NB_ACTOR_SLOT:
                return None  # the engine ignores ids past the 7 slots (BdPlayActorSE)
            return self._slot_list[sound_id]
        return sound_id  # B8/98: the byte is the global audio id (category 0)
