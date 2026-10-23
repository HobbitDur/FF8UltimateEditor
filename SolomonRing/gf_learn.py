"""GF learn slots: what the two raw unlock bytes of each ability slot mean, in plain terms.

Each of a GF's 21 learn slots stores (BuildGFAbilityList @0x4ACB70):
  * a "Level/prereq" byte: 0-100 = minimum GF level, 101-121 = the ability of slot
    (value - 101) on the same GF must be fully learned first, anything else = never
    offered (neither branch of the engine accepts it);
  * an "Excluded slot" byte, read only for the 101-121 case: once the ability of that
    slot is learned this one stops being offered. 0xFF = none.

Slots are counted from 0 in the file and from 1 in the editor ("Ability 1" = slot 0).
Shared by the SolomonRing G-Forces tab and the solomon-ring CLI, so both read and write
the bytes the same way."""

SLOT_COUNT = 21
MAX_LEVEL = 100
AFTER_BASE = 101
NO_HIDDEN = 0xFF
NEVER_DEFAULT = 0xFF

LEVEL, AFTER, NEVER = "level", "after", "never"


def decode_unlock(raw):
    """Raw Level/prereq byte -> (kind, value). ``value`` is the level, the 0-based slot,
    or the raw byte itself for NEVER."""
    if raw <= MAX_LEVEL:
        return LEVEL, raw
    if raw < AFTER_BASE + SLOT_COUNT:
        return AFTER, raw - AFTER_BASE
    return NEVER, raw


def encode_unlock(kind, value):
    if kind == LEVEL:
        if not 0 <= value <= MAX_LEVEL:
            raise ValueError(f"GF level must be 0-{MAX_LEVEL}, got {value}")
        return value
    if kind == AFTER:
        if not 0 <= value < SLOT_COUNT:
            raise ValueError(f"Slot must be 0-{SLOT_COUNT - 1}, got {value}")
        return AFTER_BASE + value
    if not AFTER_BASE + SLOT_COUNT <= value <= 0xFF:
        raise ValueError(f"A never-learnable value must be {AFTER_BASE + SLOT_COUNT}-255, got {value}")
    return value


def describe_unlock(raw):
    """Short text for a raw Level/prereq byte, with slots counted from 1 like the editor."""
    kind, value = decode_unlock(raw)
    if kind == LEVEL:
        return "no requirement" if value <= 1 else f"GF level {value}"
    if kind == AFTER:
        return f"after Ability {value + 1}"
    return "never learnable"


def describe_hidden(raw):
    if raw == NO_HIDDEN:
        return "never hidden"
    if raw < SLOT_COUNT:
        return f"hidden once Ability {raw + 1} is learned"
    return f"raw 0x{raw:02X} (outside the 21 slots)"


def parse_unlock_text(text):
    """CLI form of a Level/prereq value: ``level:N``, ``after:N`` (N = Ability 1-21),
    ``never``, or a plain raw number (decimal or 0x hex)."""
    text = text.strip().lower()
    if text == NEVER:
        return NEVER_DEFAULT
    kind, sep, number = text.partition(":")
    if sep:
        if kind == LEVEL:
            return encode_unlock(LEVEL, int(number, 0))
        if kind == AFTER:
            return encode_unlock(AFTER, int(number, 0) - 1)
        raise ValueError(f"Unknown unlock kind '{kind}' (use level:N, after:N or never)")
    return int(text, 0)


def parse_hidden_text(text):
    """CLI form of an Excluded slot value: ``none``, ``hidden:N`` / ``N`` with N = Ability
    1-21, or a raw ``0x`` hex byte."""
    text = text.strip().lower()
    if text in ("none", "hidden:none"):
        return NO_HIDDEN
    if text.startswith("0x"):
        return int(text, 16)
    number = int(text.partition(":")[2] if text.startswith("hidden:") else text)
    if not 1 <= number <= SLOT_COUNT:
        raise ValueError(f"Ability slot must be 1-{SLOT_COUNT}, got {number}")
    return number - 1


def learnability(slots):
    """Which slots the game can ever offer, and why the others cannot be learned.

    ``slots`` = list of (ability id, Level/prereq raw, Excluded slot raw), one per slot in
    file order. Returns a list, one entry per slot, of the problems found ([] = fine).
    Mirrors BuildGFAbilityList: a level slot is offered from that level on; a prerequisite
    slot once the ABILITY of its target slot is learned, unless its Excluded slot's ability
    is learned too."""
    problems = [[] for _ in slots]
    reachable = set()
    for index, (_ability, raw, _hidden) in enumerate(slots):
        if decode_unlock(raw)[0] == LEVEL:
            reachable.add(index)
    # Prerequisite chains: keep extending from what is already learnable until nothing moves.
    changed = True
    while changed:
        changed = False
        for index, (_ability, raw, hidden) in enumerate(slots):
            kind, target = decode_unlock(raw)
            if index in reachable or kind != AFTER or target == index:
                continue
            if target in reachable and slots[target][0] != 0 and hidden != target:
                reachable.add(index)
                changed = True

    for index, (ability, raw, hidden) in enumerate(slots):
        kind, target = decode_unlock(raw)
        if kind == NEVER:
            problems[index].append(f"Level/prereq {raw} is neither a level (0-100) nor a slot "
                                   f"(101-121): the game never offers this ability.")
        elif kind == AFTER:
            if target == index:
                problems[index].append("Waits for itself: it can never be learned.")
            elif slots[target][0] == 0:
                problems[index].append(f"Waits for Ability {target + 1}, which is empty: "
                                       f"it can never be learned.")
            elif hidden == target:
                problems[index].append(f"Hidden once Ability {target + 1} is learned, but that is "
                                       f"also what it waits for: it can never be learned.")
            elif index not in reachable:
                problems[index].append(f"Waits for Ability {target + 1}, which can never be learned "
                                       f"itself (a loop or a broken chain).")
            if hidden != NO_HIDDEN and hidden >= len(slots):
                problems[index].append(f"Excluded slot 0x{hidden:02X} is outside the 21 slots.")
        if ability == 0 and kind != NEVER and not problems[index]:
            # An empty slot that the game can offer lands "None" in the junction menu's list.
            problems[index].append("Empty slot the game can still offer: it shows up as an "
                                   "empty ability in the GF's learn list.")
    return problems


def learn_tree(slots):
    """The unlock chains as a forest: list of (slot index, children), roots first being
    the level slots in file order. A prerequisite slot hangs under the slot it waits for;
    slots that wait for themselves or for an invalid slot, and never-learnable ones, are
    returned separately: (roots, orphans)."""
    children = {index: [] for index in range(len(slots))}
    roots, orphans = [], []
    for index, (_ability, raw, _hidden) in enumerate(slots):
        kind, target = decode_unlock(raw)
        if kind == LEVEL:
            roots.append(index)
        elif kind == AFTER and target != index and target < len(slots):
            children[target].append(index)
        else:
            orphans.append(index)

    placed = set()

    def build(index):
        placed.add(index)
        return index, [build(child) for child in children[index] if child not in placed]

    forest = [build(root) for root in roots]
    # What a loop holds never hangs under a level slot: show it with the orphans.
    orphans.extend(index for index in range(len(slots)) if index not in placed and index not in orphans)
    return forest, sorted(orphans)
