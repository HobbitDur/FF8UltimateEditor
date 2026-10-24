"""Multi-part monsters: other monsters the game draws as part of a monster (Seifer's Gunblade).

Some monsters are drawn as several linked monsters. Seifer (c0m085-c0m087) is one: his file
has his body only, and his gunblade is the "Gunblade" monster (c0m082, or c0m142 with
c0m087) placed in the same encounter slot position, not targetable. The parts are tied by the
AnimSeq link opcode 0x90 (see the wiki's Animation sequences page): XX < 3 unlinks, 3 <= XX < 16
links self to battle slot XX (encounter slot XX - 3), XX >= 16 links self to the loaded
monster with that com_id. A sequence queued on one part starts with the same index on every
part (QueueChainTransformation 0x505C00 -> task 0x505C70 -> someResetBattleStateEntity for each
chain member), and every part copies the chain head's (lowest slot) 0x20-byte transform each
tick (end of 0x502AB0), so they move as one body. Each part still poses its own skeleton with
its own animation, skeleton scale and root track (BattleModel_BuildBoneMatricesFromPose 0x508C90).

MAG_040_SCAN_FindScannedEntities (0x84D320) takes the whole chain of the scanned monster
and MAG_040_SCAN_Viewer_Update copies the main entity's position, rotation and scale to
every part, so the Scan screen shows Seifer with his gunblade.

Which monsters are linked is only known from the encounters (scene.out) and the parts'
sequences, so it is read from those files, never from a fixed list.
"""
import os
import re
import struct

from FF8GameData.dat.sequencecommand import read_sequence

LINK_OPCODE = 0x90
FIRST_ENEMY_SLOT = 3           # battle slots 0-2 = party, 3-10 = encounter slots 0-7
FIRST_MONSTER_COM_ID = 16
SEQUENCE_SECTION = 4           # 0-based: the monster .dat's section 5 (animation sequences)
MONSTER_SECTION_COUNT = 11     # characters (7), weapons (8/5) and Edea (10) keep no sequences there


def read_sequences(dat_bytes) -> list:
    """The animation sequences of a monster .dat, as byte strings (empty ones skipped)."""
    nb_section = struct.unpack_from("<I", dat_bytes, 0)[0]
    if nb_section < MONSTER_SECTION_COUNT:
        return []
    offsets = struct.unpack_from(f"<{nb_section}I", dat_bytes, 4)
    start, end = offsets[SEQUENCE_SECTION], offsets[SEQUENCE_SECTION + 1]
    section = dat_bytes[start:end]
    if len(section) < 2:
        return []
    count = struct.unpack_from("<H", section, 0)[0]
    starts = sorted({offset for offset in struct.unpack_from(f"<{count}H", section, 2) if offset})
    bounds = starts + [len(section)]
    return [section[bounds[i]:bounds[i + 1]] for i in range(len(starts))]


def sequence_by_index(dat_bytes, index) -> bytes:
    """Animation sequence `index` of a monster .dat (b"" when it has none)."""
    nb_section = struct.unpack_from("<I", dat_bytes, 0)[0]
    if nb_section < MONSTER_SECTION_COUNT:
        return b""
    offsets = struct.unpack_from(f"<{nb_section}I", dat_bytes, 4)
    section = dat_bytes[offsets[SEQUENCE_SECTION]:offsets[SEQUENCE_SECTION + 1]]
    count = struct.unpack_from("<H", section, 0)[0] if len(section) >= 2 else 0
    if not 0 <= index < count:
        return b""
    start = struct.unpack_from("<H", section, 2 + 2 * index)[0]
    if not start:
        return b""
    ends = [offset for offset in struct.unpack_from(f"<{count}H", section, 2) if offset > start]
    return section[start:min(ends, default=len(section))]


def played_animations(vm, sequence) -> list:
    """The animations a sequence plays, in order (00-7F play and wait, A0 XX play)."""
    animations = []
    for command in read_sequence(vm, bytes(sequence)):
        if command.is_unknown():
            break
        if command.op_code < 0x80:
            animations.append(command.op_code)
        elif command.op_code == 0xA0 and command.parameters:
            animations.append(command.parameters[0])
    return animations


def sequence_count(dat_bytes) -> int:
    nb_section = struct.unpack_from("<I", dat_bytes, 0)[0]
    if nb_section < MONSTER_SECTION_COUNT:
        return 0
    start = struct.unpack_from(f"<{nb_section}I", dat_bytes, 4)[SEQUENCE_SECTION]
    return struct.unpack_from("<H", dat_bytes, start)[0]


def idle_animation(vm, dat_bytes) -> int:
    """The animation a monster stands in: the first one its sequence 0 plays (0 by default).
    Linked parts start the same sequence as their chain head, so each part shows the
    animation of ITS sequence 0 (Seifer c0m087: anim 0, its Gunblade c0m142: anim 13)."""
    animations = played_animations(vm, sequence_by_index(dat_bytes, 0))
    return animations[0] if animations else 0


def animation_map(vm, head_bytes, part_bytes) -> dict:
    """{head animation: part animation}: what a linked part plays while its chain head plays
    an animation. Both run the same sequence index, so the head's k-th animation of sequence N
    goes with the part's k-th animation of its sequence N (first sequence that plays it wins)."""
    mapping = {}
    for index in range(min(sequence_count(head_bytes), sequence_count(part_bytes))):
        head = played_animations(vm, sequence_by_index(head_bytes, index))
        part = played_animations(vm, sequence_by_index(part_bytes, index))
        for head_animation, part_animation in zip(head, part):
            mapping.setdefault(head_animation, part_animation)
    return mapping


def link_targets(vm, sequences) -> set:
    """What the link opcode of these sequences links to: {('slot', n)} / {('com_id', n)}."""
    targets = set()
    for data in sequences:
        for command in read_sequence(vm, bytes(data)):
            if command.is_unknown():
                break  # the rest of this sequence cannot be read reliably
            if command.op_code == LINK_OPCODE and command.parameters:
                value = command.parameters[0]
                if FIRST_ENEMY_SLOT <= value < FIRST_MONSTER_COM_ID:
                    targets.add(("slot", value))
                elif value >= FIRST_MONSTER_COM_ID:
                    targets.add(("com_id", value))
    return targets


def _links_to(targets, slot):
    return bool(targets) and (("slot", slot.slot_index + FIRST_ENEMY_SLOT) in targets
                              or ("com_id", slot.enemy_id) in targets)


def linked_parts(encounters, c0m, targets_of) -> list:
    """c0m numbers of the monsters linked with monster `c0m` in at least one encounter.

    targets_of(c0m) gives the link targets of that monster's sequences, or None when its
    file is not open (it then cannot be told apart from an unlinked monster)."""
    parts = []
    for encounter in encounters:
        slots = encounter.enabled_slots()
        for head in (slot for slot in slots if slot.com_file_id == c0m):
            for other in slots:
                if other.com_file_id == c0m or other.com_file_id in parts:
                    continue
                if _links_to(targets_of(other.com_file_id), head) or _links_to(targets_of(c0m), other):
                    parts.append(other.com_file_id)
    return parts


def linked_part_setups(encounters, c0m, targets_of) -> list:
    """[(encounter indices, [part c0m numbers])] for monster `c0m`: one entry per distinct set
    of parts linked to it, in encounter order (Seifer c0m086: [([119], [82])])."""
    setups = {}
    for encounter in encounters:
        parts = linked_parts([encounter], c0m, targets_of)
        if parts:
            setups.setdefault(tuple(parts), []).append(encounter.index)
    return [(indices, list(parts)) for parts, indices in setups.items()]


def c0m_number(path):
    """NNN of a c0mNNN.dat path, or None."""
    match = re.match(r"^c0m(\d{3})\.dat$", os.path.basename(path), re.IGNORECASE)
    return int(match.group(1)) if match else None
