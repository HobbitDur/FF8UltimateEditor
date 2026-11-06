"""Which sequence a battle actor starts to perform an effect, as the game picks it (computeCommandAction 0x48D200), Qt-free.

The action sequence is the actor's: a character's in its weapon file, chosen by the command (byte_B8150C: 11 for Magic, 14 for a GF,
15 for an item); a monster's is named by its ability slot (dat section 7: type, animation, id; type 2 Magic, 4 item, 8 enemy attack).
The effect's users say which command or ability plays it: the imported kernel.bin's (Fujin.effectusers), else the game's
(effect_users.json). The recorder then runs that sequence with the game's code (castseq=): when it asks, the effect starts.

An effect that binds its own animation set plays that set's sequence itself (Fujin.effectprogram.binds_its_animations), and an effect
this actor has no sequence for starts at once.
"""
import functools
import json
import os
import re
import struct
from pathlib import Path

from FF8GameData.dat.actoranimplan import _section, read_sequences
from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

USERS_FILE = Path(RESOURCES_JSON_FOLDER) / "effect_users.json"
CHARACTER_FILE = re.compile(r"^d[0-9a-z]c\d+\.dat$", re.IGNORECASE)
# a character's command (the effect's user), its sequence: byte_B8150C[command]
CHARACTER_SEQUENCES = (("Magic", 11), ("GF", 14), ("GF attack", 14), ("Battle item", 15))
# a monster's ability slot: its type, the effect's user kind
ABILITY_KINDS = {2: "Magic", 4: "Battle item", 8: "Enemy attack"}
INFO_SECTION = 7
ABILITY_LISTS = (0x34, 0x74, 0xB4)                  # low, medium, high level: 16 x (type, animation, id)


@functools.lru_cache(maxsize=1)
def _shipped():
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def shipped_users(effect):
    """[(kind, entry id)] of the game's kernel.bin entries that play `effect`."""
    return [(user["kind"], user["id"]) for user in _shipped().get(str(effect), [])]


def _stamp(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return 0


@functools.lru_cache(maxsize=32)
def _sequence_ids(path, _stamp_value):
    return frozenset(read_sequences(path))


@functools.lru_cache(maxsize=32)
def monster_abilities(path, _stamp_value=None):
    """[(type, animation sequence, id)] of a monster dat's ability slots."""
    try:
        section = _section(Path(path).read_bytes(), INFO_SECTION)
        return tuple(ability for base in ABILITY_LISTS for ability in struct.iter_unpack("<BBH", section[base:base + 64])
                     if ability[0])
    except (OSError, struct.error):
        return ()


def cast_sequence(users, body, weapon=None):
    """The sequence (1-based, as the game's) the actor of these files starts for an effect with these `users` ([(kind, entry id)]),
    or None: it has none for it."""
    if not body:
        return None
    if CHARACTER_FILE.match(os.path.basename(body)):
        if not weapon:
            return None
        kinds = {kind for kind, _entry in users}
        known = _sequence_ids(weapon, _stamp(weapon))
        return next((sequence for kind, sequence in CHARACTER_SEQUENCES if kind in kinds and sequence in known), None)
    plays = set(users)
    known = _sequence_ids(body, _stamp(body))
    return next((animation for kind, animation, entry in monster_abilities(body, _stamp(body))
                 if (ABILITY_KINDS.get(kind), entry) in plays and animation in known), None)
