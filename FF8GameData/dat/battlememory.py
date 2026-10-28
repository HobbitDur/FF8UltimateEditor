"""The vanilla battle memory caps a battle file must fit, for the 30 fps conversion warnings.

FF8_EN.exe reads every battle file into fixed PSX-RAM regions whose addresses live only in the
table 0xB6D070-0xB6D0A4, and no loader checks a size: a file over a cap silently overwrites the
next region (study D:/FFNxMenu30fps/gf_study/DAT30FPS_STUDY.md section 6). A converted file
(2n-frame animations) is larger, and the 30 fps FFNx build enlarges these regions; a user without
that build must be told when a converted file no longer fits the vanilla ones. Warnings only:
nothing here refuses a file.

| region | cap | what goes there |
|---|---|---|
| staging buffer 0x199B018 | 294,912 | every battle file, read whole (also r0win.dat) |
| monster arena 0x1939018 | 204,800 per battle | the stage up to its TIM + every distinct monster's [section 1, section 10) |
| party slot 0x196B018 + 64 KB * slot | 65,536 | body [section 1, section 6) (Edea [1, 8)) + weapon [1, 6) (reduced weapon [1, 4)) |
| extra-anim slot 0x19E3018 | 8192 body / 4096 weapon | dXc section 7 (Edea 10) / dXw section 8 |
"""
import struct

STAGING_CAP = 0x48000
MONSTER_ARENA_CAP = 204800
PARTY_SLOT_CAP = 0x10000
EXTRA_BODY_CAP = 8192
EXTRA_WEAPON_CAP = 4096


def section_offsets(data: bytes) -> list:
    """[offset of section 1, ..., offset of section n, file end] of a battle .dat."""
    nb = struct.unpack_from("<I", data, 0)[0]
    if not 1 <= nb <= 16 or 4 + 4 * nb > len(data):
        raise ValueError("not a battle .dat (bad section count)")
    return list(struct.unpack_from(f"<{nb}I", data, 4)) + [len(data)]


def _span(offsets, first, end):
    """Bytes of sections [first, end) (1-based section numbers)."""
    return offsets[end - 1] - offsets[first - 1]


def monster_arena_bytes(data: bytes) -> int:
    """What a monster c0m takes in the monster arena: [section 1, section 10)."""
    offsets = section_offsets(data)
    return _span(offsets, 1, 10) if len(offsets) - 1 >= 10 else 0


def party_bytes(data: bytes) -> int:
    """What a character body or weapon takes in its party slot."""
    offsets = section_offsets(data)
    nb = len(offsets) - 1
    if nb == 10:      # Edea d7c016: [1, 8)
        return _span(offsets, 1, 8)
    if nb in (7, 8):  # body dXc / weapon dXw: [1, 6)
        return _span(offsets, 1, 6)
    if nb == 5:       # reduced weapon d1w/d9w: [1, 4)
        return _span(offsets, 1, 4)
    return 0


def extra_animation_bytes(data: bytes) -> int:
    offsets = section_offsets(data)
    nb = len(offsets) - 1
    if nb in (7, 8, 10):
        return offsets[nb] - offsets[nb - 1]
    return 0


def file_warning_list(name: str, data: bytes) -> list:
    """Caps one file goes over on its own (the staging buffer, a monster alone in the arena, an
    extra-anim slot). A character body + weapon pair is checked by pair_warning_list."""
    warnings = []
    if len(data) > STAGING_CAP:
        warnings.append(f"{name}: {len(data)} bytes, over the {STAGING_CAP}-byte battle file buffer "
                        "(needs the enlarged-memory FFNx build)")
    try:
        offsets = section_offsets(data)
    except (ValueError, struct.error):
        return warnings
    nb = len(offsets) - 1
    lower = name.lower()
    if lower.startswith("c0m") and nb >= 10:
        arena = monster_arena_bytes(data)
        if arena > MONSTER_ARENA_CAP:
            warnings.append(f"{name}: {arena} bytes of model data, over the {MONSTER_ARENA_CAP}-byte monster "
                            "arena on its own (needs the enlarged-memory FFNx build)")
    elif nb in (7, 8, 10):
        cap = EXTRA_WEAPON_CAP if nb == 8 else EXTRA_BODY_CAP
        extra = extra_animation_bytes(data)
        if extra > cap:
            warnings.append(f"{name}: battle-entry animation block {extra} bytes, over its {cap}-byte slot")
    return warnings


def pair_warning_list(body_name: str, body: bytes, weapon_name: str, weapon: bytes) -> list:
    total = party_bytes(body) + (party_bytes(weapon) if weapon else 0)
    if total > PARTY_SLOT_CAP:
        return [f"{body_name} + {weapon_name}: {total} bytes, over the {PARTY_SLOT_CAP}-byte party slot "
                "(needs the enlarged-memory FFNx build)"]
    return []
