"""What changes between two recordings of an effect (FF8GameData.psxgpu.fxdump): per effect part,
the ticks where what it draws differs, the sprite frames it draws only in one of them, and the
length. Fujin's part tabs record the effect with one parameter nudged and show this ("What does
it change?"). No Qt here.
"""
from collections import Counter


def tick_runs(ticks):
    """'3-7, 9' from [3, 4, 5, 6, 7, 9]."""
    ticks = sorted(ticks)
    runs, start = [], None
    for index, tick in enumerate(ticks):
        if start is None:
            start = tick
        if index + 1 == len(ticks) or ticks[index + 1] != tick + 1:
            runs.append(f"{start}" if start == tick else f"{start}-{tick}")
            start = None
    return ", ".join(runs)


def differences(before, after, part_names=None):
    """[{"part": id, "name": text, "ticks": [ticks drawn differently], "gained": {(sequence, frame):
    [ticks]}, "lost": {...}}] for every part whose drawing differs (0: the target / no part), and
    the tick counts (before, after)."""
    names = part_names or {}
    found = {}
    count = max(len(before.ticks), len(after.ticks))
    for index in range(count):
        old = before.ticks[index] if index < len(before.ticks) else None
        new = after.ticks[index] if index < len(after.ticks) else None
        parts = set(old.parts if old else ()) | set(new.parts if new else ())
        for part in parts:
            old_packets = [words for _b, _o, words in old.part_packets({part})] if old else []
            new_packets = [words for _b, _o, words in new.part_packets({part})] if new else []
            old_sprites = Counter((a, f) for p, a, f in (old.sprites if old else ()) if p == part)
            new_sprites = Counter((a, f) for p, a, f in (new.sprites if new else ()) if p == part)
            if old_packets == new_packets and old_sprites == new_sprites:
                continue
            entry = found.setdefault(part, {"part": part, "name": names.get(part, f"part {part}"),
                                            "ticks": [], "gained": {}, "lost": {}})
            entry["ticks"].append(index)
            for sprite in new_sprites - old_sprites:
                entry["gained"].setdefault(sprite, []).append(index)
            for sprite in old_sprites - new_sprites:
                entry["lost"].setdefault(sprite, []).append(index)
    return sorted(found.values(), key=lambda e: (e["ticks"][0], e["part"])), (len(before.ticks), len(after.ticks))


def describe(changes, lengths):
    """Lines of text for differences(): one per part, then its sprite frames gained / lost."""
    lines = []
    if lengths[0] != lengths[1]:
        lines.append(f"The effect lasts {lengths[1]} ticks instead of {lengths[0]}.")
    for entry in changes:
        lines.append(f"{entry['name']}: draws differently at ticks {tick_runs(entry['ticks'])}.")
        for label, sprites in (("now also draws", entry["gained"]), ("no longer draws", entry["lost"])):
            by_sequence = {}
            for (address, frame), ticks in sprites.items():
                by_sequence.setdefault(address, {}).setdefault(frame, []).extend(ticks)
            for address, frames in sorted(by_sequence.items()):
                listed = ", ".join(f"{frame} (tick {tick_runs(ticks)})" for frame, ticks in sorted(frames.items())[:8])
                more = f" and {len(frames) - 8} more" if len(frames) > 8 else ""
                lines.append(f"    {label} sequence 0x{address:X} frames {listed}{more}")
    if len(changes) > 1:
        lines.append("Parts the value does not drive can change too: the game draws its random numbers "
                     "from one stream, so a part drawing more or less shifts the others' rolls.")
    if not lines:
        lines.append("Nothing this effect draws changes (with this cast and these values).")
    return lines
