"""Battle camera keyframe coordinate modes: the byte before each keyframe's position and look-at.

It is not an easing mode: it names the reference frame the three coordinates are expressed in.
Verified in FF8_EN.exe: BS_Camera_ResolveCoordinateMode (0x503AE0) -> getCameraScaleMatrix
(0x50D9F0) -> getCameraScalingFactor (0x50D790); the attacker/target frames are built by
AnimSeq92_SetupTargetingContext (0x50D300) and ComputeTransformBetweenPoints (0x50D6B0).

    0xFB         world coordinates, copied as they are
    0xF1         world coordinates (no matrix), mirrored with the battle side
    0xF2         attacker/target midpoint on the ground, axis attacker -> target, not scaled
    0xF3 / 0xF4  offset from the current camera position / look-at (0,0,0 = hold the view)
    0xF5-0xF8    midpoint of an attacker anchor and a target anchor (0xF0/0xF1 bones),
                 scaled by their distance / 5000
    0xF9         a frame the effect code sets itself (Angelo, Death's reaper, Moomba...)
    other >=0xB0 the target's ground position, turned to the target's side, not scaled
    0xHN         entity H (0-6 battle slot, 9 attacker, A target), point N (0-3 skeleton anchor
                 bone, F origin), scaled by the entity's size (2 * model radius * size scale)
"""

NB_BATTLE_SLOTS = 7          # 0-2 party, 3-6 monsters (BattleEntitySlotData[7])
ATTACKER, TARGET = 0x9, 0xA
ORIGIN = 0xF

_ENTITY_NAMES = {ATTACKER: "Attacker", TARGET: "Target"}
_POINT_NAMES = {0: "anchor 0xF0", 1: "model centre", 2: "anchor 0xF2", 3: "anchor 0xF3", ORIGIN: "origin"}
_POINT_HELP = {
    0: "the bone the skeleton names for selector 0xF0 (skeleton header byte 4)",
    1: "the bone the skeleton names for selector 0xF1, the model's centre (header byte 5; Scan aims here)",
    2: "the bone the skeleton names for selector 0xF2 (skeleton header byte 6)",
    3: "the bone the skeleton names for selector 0xF3 (skeleton header byte 7)",
    ORIGIN: "the entity's origin, its position on the ground",
}

_SPECIAL = {
    0xB0: ("Target ground, not scaled",
           "The target's ground position (the centre of the targets when there are several), turned "
           "to face the target's side. Coordinates are world units: the same numbers for a small or "
           "a huge monster. Every value from 0xB0 to 0xFF not listed here does the same."),
    0xF1: ("World, mirrored",
           "World (stage) coordinates without any matrix; one axis is mirrored when the battle is "
           "mirrored."),
    0xF2: ("Attacker-target midpoint, not scaled",
           "Midpoint of the attacker and the target ground positions, X axis from the attacker to "
           "the target. World units, not scaled by size or distance."),
    0xF3: ("Current camera position",
           "An offset from where the camera is now. 0, 0, 0 holds the current position."),
    0xF4: ("Current look-at",
           "An offset from where the camera looks now. 0, 0, 0 holds the current look-at."),
    0xF5: ("Attacker 0xF0 - target 0xF0, by distance",
           "Midpoint of the attacker's 0xF0 anchor and the target's 0xF0 anchor, axis attacker -> "
           "target, scaled by their distance / 5000."),
    0xF6: ("Attacker 0xF0 - target centre, by distance",
           "Midpoint of the attacker's 0xF0 anchor and the target's centre (0xF1), axis attacker -> "
           "target, scaled by their distance / 5000."),
    0xF7: ("Attacker centre - target 0xF0, by distance",
           "Midpoint of the attacker's centre (0xF1) and the target's 0xF0 anchor, axis attacker -> "
           "target, scaled by their distance / 5000."),
    0xF8: ("Attacker centre - target centre, by distance",
           "Midpoint of the attacker's centre (0xF1) and the target's centre (0xF1), axis attacker -> "
           "target, scaled by their distance / 5000."),
    0xF9: ("Effect's own frame",
           "A frame the effect code sets itself (Angelo, Death's reaper, Moomba...). Other effects "
           "leave whatever the last one set."),
    0xFB: ("World",
           "World (stage) coordinates, used as they are."),
}


def _entity_name(entity: int) -> str:
    if entity in _ENTITY_NAMES:
        return _ENTITY_NAMES[entity]
    if entity < 3:
        return f"Party slot {entity}"
    return f"Slot {entity} ({('1st', '2nd', '3rd', '4th')[entity - 3]} monster)"


def mode_name(value: int) -> str:
    """Short label of a coordinate mode, with its hex value."""
    if value in _SPECIAL:
        return f"{value:02X} {_SPECIAL[value][0]}"
    entity, point = value >> 4, value & 0xF
    if value >= 0xB0:
        return f"{value:02X} Target ground, not scaled (= B0)"
    if entity in (7, 8):
        return f"{value:02X} Slot {entity}: no such battle slot"
    if point not in _POINT_NAMES:
        return f"{value:02X} {_entity_name(entity)}, invalid point {point}"
    return f"{value:02X} {_entity_name(entity)}, {_POINT_NAMES[point]} (size-scaled)"


def mode_help(value: int) -> str:
    """What a coordinate mode does, for a tooltip."""
    if value in _SPECIAL:
        return _SPECIAL[value][1]
    entity, point = value >> 4, value & 0xF
    if value >= 0xB0:
        return _SPECIAL[0xB0][1]
    if entity in (7, 8):
        return (f"High digit {entity} names a battle slot past the 7 the game has (0-2 party, 3-6 "
                "monsters): the engine reads unrelated memory. Avoid it.")
    if point not in _POINT_NAMES:
        return (f"Point {point} reads past the skeleton's four anchor bytes (it takes a byte of the "
                "root translation as a bone index). Avoid it; use 0-3 or F.")
    who = {ATTACKER: "the attacker", TARGET: "the target (the last one when there are several)"}.get(
        entity, f"battle slot {entity} ({'party' if entity < 3 else 'monster'})")
    return (f"Relative to {who}, at {_POINT_HELP[point]}. The coordinates are turned with the entity "
            "and multiplied by its size (2 * model radius * size scale / 4096), so the same numbers "
            "frame a small and a huge model alike; an anchor bone follows its animation.")


def mode_choices():
    """(value, label) pairs offered by an editor: the target and attacker points first, then the
    shared frames, then the battle slots. Invalid values are left out (a combo shows one only
    when a file already uses it)."""
    choices = []
    for entity in (TARGET, ATTACKER):
        for point in (1, 0, 2, 3, ORIGIN):
            value = entity << 4 | point
            choices.append((value, mode_name(value)))
    for value in (0xF3, 0xF4, 0xF2, 0xF5, 0xF6, 0xF7, 0xF8, 0xB0, 0xF9, 0xFB, 0xF1):
        choices.append((value, mode_name(value)))
    for entity in range(NB_BATTLE_SLOTS):
        for point in (1, 0, 2, 3, ORIGIN):
            value = entity << 4 | point
            choices.append((value, mode_name(value)))
    return choices
