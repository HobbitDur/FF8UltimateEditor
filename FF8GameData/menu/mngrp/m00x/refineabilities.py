"""The refine abilities of a kernel.bin: which slice of which m00X table each one offers.

A menu ability (kernel.bin section 18, 8 bytes each) holds, after its two text offsets and its AP:
  byte 5  the refine table it opens (0-4 = m000-m004; 128/129 = shops, 255 = no table)
  byte 6  the first entry of its slice of that table
  byte 7  the last entry of its slice, inclusive
Menu_Prog19_RefineMenu_Init computes `entry_count = last - first + 1` (a u8) and points the list at
`Menu_RefineEntryBuffer + 8 * first`, so the recipes of an ability are wherever those two bytes say,
and adding one means moving them. Menu_RefineEntryBuffer is 0x800 bytes: 256 entries per table.

Saving mngrp.bin never touches kernel.bin: a mngrp editor adding or removing recipes says which
ranges it then needs (RefineLayout.kernel_warnings). write_refine_ranges patches them, only when
asked to (Shiva's "Refine ranges" dialog), and only bytes 6-7: what an ability is (byte 5, its
name, its AP...) stays SolomonRing's business.
"""
from dataclasses import dataclass

MENU_ABILITY_SECTION_ID = 18
MENU_ABILITY_SIZE = 8
OFFSET_TABLE = 5
OFFSET_FIRST = 6
OFFSET_LAST = 7
REFINE_TABLES = range(5)       # m000 to m004
MAX_TABLE_ENTRIES = 256        # Menu_RefineEntryBuffer: 0x800 bytes of 8-byte entries
MAX_ABILITY_ENTRIES = 255      # RefineMenuTask.entry_count is a u8
MAX_MSG_SIZE = 0x5000          # Menu_RefineTextBuffer, up to Menu_RefineEntryBuffer


class RefineKernelError(Exception):
    """kernel.bin's refine ranges cannot be used (abilities offering the same recipes...)."""


@dataclass
class RefineAbility:
    """One menu ability opening a refine table, and the slice of it it offers."""
    index: int          # Its place in kernel.bin section 18 (None: a whole table, or entries no ability offers)
    table: int          # m00X
    first: int
    last: int
    name: str = ""
    description: str = ""

    @property
    def count(self):
        return self.last - self.first + 1


def _menu_ability_section(game_data, kernel_path):
    from FF8GameData.kernel.kernelmanager import KernelManager
    if not getattr(game_data, "kernel_data_json", None):
        game_data.load_kernel_data()
    kernel_manager = KernelManager(game_data)
    kernel_manager.load_file(str(kernel_path))
    for section in kernel_manager.section_list:
        if section is not None and section.id == MENU_ABILITY_SECTION_ID:
            return section
    raise RefineKernelError(f"{kernel_path}: no menu ability section")


def find_overlaps(abilities):
    """[(ability, other)] of the abilities offering some of the same entries of a table."""
    pairs = []
    for position, ability in enumerate(abilities):
        for other in abilities[position + 1:]:
            if other.table == ability.table and other.first <= ability.last and ability.first <= other.last:
                pairs.append((ability, other))
    return pairs


def check_no_overlap(abilities, source="kernel.bin"):
    """Raise RefineKernelError when two abilities offer some of the same entries of a table.

    Each refine ability owns its own block of its table: an overlap is a broken kernel.bin (older
    Shiva versions could make one), and editing a recipe there would edit it in both abilities."""
    overlaps = [f"  m00{ability.table}: {ability.name or 'menu ability'} (menu ability {ability.index}, "
                f"entries {ability.first}-{ability.last}) and {other.name or 'menu ability'} "
                f"(menu ability {other.index}, entries {other.first}-{other.last})"
                for ability, other in find_overlaps(abilities)]
    if overlaps:
        shown = overlaps[:8] + ([f"  ... and {len(overlaps) - 8} more"] if len(overlaps) > 8 else [])
        raise RefineKernelError(f"{source}: refine abilities offering the same recipes:\n" + "\n".join(shown)
                                + "\nEach refine ability needs its own entries: fix their first/last entry "
                                  "(bytes 6-7 of the menu ability) in kernel.bin.")


def read_refine_abilities(game_data, kernel_path):
    """[RefineAbility] of every menu ability opening a refine table, in kernel.bin order.

    Raises RefineKernelError when two of them overlap (check_no_overlap)."""
    section = _menu_ability_section(game_data, kernel_path)
    data = section.get_data_hex()
    texts = section.section_text_linked.get_text_list() if section.section_text_linked else []
    abilities = []
    for index in range(len(data) // MENU_ABILITY_SIZE):
        raw = data[index * MENU_ABILITY_SIZE:(index + 1) * MENU_ABILITY_SIZE]
        if raw[OFFSET_TABLE] not in REFINE_TABLES:
            continue
        name = texts[2 * index].get_str() if 2 * index < len(texts) else ""
        description = texts[2 * index + 1].get_str() if 2 * index + 1 < len(texts) else ""
        abilities.append(RefineAbility(index=index, table=raw[OFFSET_TABLE], first=raw[OFFSET_FIRST],
                                       last=raw[OFFSET_LAST], name=name, description=description))
    check_no_overlap(abilities, str(kernel_path))
    return abilities


def check_refine_ranges(abilities):
    """The reasons kernel.bin cannot hold those ranges ([] when it can)."""
    errors = []
    for ability in abilities:
        label = ability.name or f"menu ability {ability.index}"
        if not 0 <= ability.first <= ability.last <= 0xFF:
            errors.append(f"{label}: recipes {ability.first}-{ability.last} do not fit kernel.bin's two bytes")
        elif ability.count > MAX_ABILITY_ENTRIES:
            errors.append(f"{label}: {ability.count} recipes, the game counts at most {MAX_ABILITY_ENTRIES}")
    return errors


def range_problems(abilities, table_counts):
    """[(ability, reason)] of the ranges kernel.bin should not get, for tables holding
    table_counts[table] recipes: a slice with no recipe, past the table's end, too long for the
    game, or offering the same entries as another ability."""
    problems = []
    for ability in abilities:
        count = table_counts[ability.table]
        if ability.first > ability.last:
            problems.append((ability, f"first {ability.first} is after last {ability.last}: no recipe"))
        elif ability.last >= count:
            problems.append((ability, f"last {ability.last} is past the table's end (entries 0-{count - 1})"))
        elif ability.count > MAX_ABILITY_ENTRIES:
            problems.append((ability, f"{ability.count} recipes, the game counts at most {MAX_ABILITY_ENTRIES}"))
    for ability, other in find_overlaps([ability for ability in abilities if ability.first <= ability.last]):
        problems.append((ability, f"offers the same entries as {other.name or f'menu ability {other.index}'}"))
        problems.append((other, f"offers the same entries as {ability.name or f'menu ability {ability.index}'}"))
    return problems


def write_refine_ranges(game_data, kernel_path, abilities, new_ranges):
    """Patch bytes 6-7 (first, last entry) of the menu abilities whose range changes.

    abilities: the RefineAbility list read from kernel_path (read_refine_abilities); new_ranges:
    {menu ability index: (first, last)}. The file must still hold what was read for them (another
    tool may have saved it meanwhile), and nothing else is written. Returns how many changed."""
    by_index = {ability.index: ability for ability in abilities}
    changed = {index: rng for index, rng in new_ranges.items()
               if (by_index[index].first, by_index[index].last) != tuple(rng)}
    if not changed:
        return 0
    for index, (first, last) in changed.items():
        if not 0 <= first <= last <= 0xFF:
            raise RefineKernelError(f"{by_index[index].name}: entries {first}-{last} do not fit kernel.bin's two bytes")
    section = _menu_ability_section(game_data, kernel_path)
    data = section.get_data_hex()
    for index in changed:
        raw = data[index * MENU_ABILITY_SIZE:(index + 1) * MENU_ABILITY_SIZE]
        ability = by_index[index]
        if len(raw) < MENU_ABILITY_SIZE or (raw[OFFSET_TABLE], raw[OFFSET_FIRST], raw[OFFSET_LAST]) != \
                (ability.table, ability.first, ability.last):
            raise RefineKernelError(f"{kernel_path} changed since it was read (menu ability {index}, {ability.name}): "
                                    f"reopen it before writing the refine ranges.")
    with open(kernel_path, "r+b") as kernel_file:
        for index, (first, last) in changed.items():
            kernel_file.seek(section.own_offset + index * MENU_ABILITY_SIZE + OFFSET_FIRST)
            kernel_file.write(bytes((first, last)))
    return len(changed)
