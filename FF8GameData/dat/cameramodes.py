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


# ------------------------------------------------------------------ block control word
# BS_Camera_ReadAnimation (0x503C70) and BS_Camera_EaseTime (0x503FE0); bit 0 layout, bits 1-5
# easing, 6-7 FOV mode, 8-9 roll mode. FOV = projection distance (bigger = zoomed in), roll in
# 4096ths of a turn; both glide from start to end over the block.
FOV_MODES = (
    ("Keep", "Keeps the FOV start/end the camera had (previous block or previous camera)."),
    ("Default 512", "FOV 512 for the whole block (no value stored)."),
    ("Fixed", "One FOV value for the whole block."),
    ("Start → end", "The FOV glides from a start value to an end value across the block."),
)
ROLL_MODES = (
    ("Keep", "Keeps the camera's current roll (tilt) for the whole block."),
    ("None (0)", "No roll for the whole block (no value stored)."),
    ("Fixed", "One roll value for the whole block (4096 = a full turn)."),
    ("Start → end", "The roll glides from a start value to an end value across the block "
                    "(4096 = a full turn)."),
)
LAYOUTS = (
    ("Follow", "Keyframes are placed every frame: a camera tied to an entity follows it as it moves."),
    ("Place once", "Every keyframe is placed once, when the block starts: the camera path does not "
                   "follow entities that move afterwards."),
)
CAPTURE_RETURN_VIEW_EASING = 15     # (control word & 0x3E) == 0x1E also calls BS_Camera_CaptureReturnView


def easing_name(easing: int) -> str:
    if easing == 0:
        return "Linear"
    name = f"Ease out x{easing}" if easing > 0 else f"Ease in x{-easing}"
    return name + " + save return view" if easing == CAPTURE_RETURN_VIEW_EASING else name


def easing_help(easing: int) -> str:
    if easing == 0:
        return "Constant speed from one keyframe to the next."
    if easing > 0:
        text = (f"Starts fast and slows down at the end: a sine applied {easing} time(s) to the block's "
                "time, so a higher number brakes harder.")
    else:
        text = (f"Starts slowly and speeds up at the end: 1 - cosine applied {-easing} time(s) to the "
                "block's time, so a higher number accelerates harder.")
    if easing == CAPTURE_RETURN_VIEW_EASING:
        text += (" Value 15 also saves the view the camera goes back to when the effect ends "
                 "(BS_Camera_CaptureReturnView).")
    return text


def easing_choices():
    """(value, label) from the strongest ease in to the strongest ease out."""
    return [(value, easing_name(value)) for value in range(-16, 16)]
