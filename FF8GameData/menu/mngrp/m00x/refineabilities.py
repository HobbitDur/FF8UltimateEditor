"""The refine abilities of a kernel.bin: which slice of which m00X table each one offers.

A menu ability (kernel.bin section 18, 8 bytes each) holds, after its two text offsets and its AP:
  byte 5  the refine table it opens (0-4 = m000-m004; 128/129 = shops, 255 = no table)
  byte 6  the first entry of its slice of that table
  byte 7  the last entry of its slice, inclusive
Menu_Prog19_RefineMenu_Init computes `entry_count = last - first + 1` (a u8) and points the list at
`Menu_RefineEntryBuffer + 8 * first`, so the recipes of an ability are wherever those two bytes say,
and adding one means moving them. Menu_RefineEntryBuffer is 0x800 bytes: 256 entries per table.

The writer patches those two bytes in place, nothing else: rebuilding the whole kernel.bin from
its parsed sections is not byte-exact, and the rest of the file is SolomonRing's business.
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
    """kernel.bin cannot take the refine ranges (changed on disk, not the same layout...)."""


@dataclass
class RefineAbility:
    """One menu ability opening a refine table, and the slice of it it offers."""
    index: int          # Its place in kernel.bin section 18 (None: a whole table, or entries no ability offers)
    table: int          # m00X
    first: int
    last: int
    name: str = ""
    description: str = ""
    loaded_first: int = None  # The values read from the file, to patch only what changed
    loaded_last: int = None

    def __post_init__(self):
        if self.loaded_first is None:
            self.loaded_first = self.first
        if self.loaded_last is None:
            self.loaded_last = self.last

    @property
    def count(self):
        return self.last - self.first + 1

    @property
    def changed(self):
        return (self.first, self.last) != (self.loaded_first, self.loaded_last)


def _menu_ability_section(game_data, kernel_path):
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    if not getattr(game_data, "kernel_data_json", None):
        game_data.load_kernel_data()
    kernel_manager = KernelManager(game_data)
    kernel_manager.load_file(str(kernel_path))
    for section in kernel_manager.section_list:
        if section is not None and section.id == MENU_ABILITY_SECTION_ID:
            return section
    raise RefineKernelError(f"{kernel_path}: no menu ability section")


def read_refine_abilities(game_data, kernel_path):
    """[RefineAbility] of every menu ability opening a refine table, in kernel.bin order."""
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


def _changed_abilities(abilities):
    return [ability for ability in abilities if ability.index is not None and ability.changed]


def verify_refine_ranges(game_data, kernel_path, abilities):
    """Raise RefineKernelError unless write_refine_ranges can write those ranges: they fit, and the
    file still holds the values they were read from (another tool may have saved it meanwhile).
    Returns the parsed menu ability section."""
    changed = _changed_abilities(abilities)
    errors = check_refine_ranges(changed)
    if errors:
        raise RefineKernelError("\n".join(errors))
    section = _menu_ability_section(game_data, kernel_path)
    data = section.get_data_hex()
    for ability in changed:
        start = ability.index * MENU_ABILITY_SIZE
        raw = data[start:start + MENU_ABILITY_SIZE]
        if len(raw) < MENU_ABILITY_SIZE or (raw[OFFSET_TABLE], raw[OFFSET_FIRST], raw[OFFSET_LAST]) != \
                (ability.table, ability.loaded_first, ability.loaded_last):
            raise RefineKernelError(
                f"{kernel_path} changed since it was opened (menu ability {ability.index}, "
                f"{ability.name}): reload it before saving the refine recipes.")
    return section


def write_refine_ranges(game_data, kernel_path, abilities):
    """Patch the first/last bytes of the abilities whose range changed. Returns how many were.

    Everything is verified (verify_refine_ranges) before the file is opened for writing."""
    changed = _changed_abilities(abilities)
    if not changed:
        return 0
    section = verify_refine_ranges(game_data, kernel_path, changed)
    with open(kernel_path, "r+b") as kernel_file:
        for ability in changed:
            kernel_file.seek(section.own_offset + ability.index * MENU_ABILITY_SIZE + OFFSET_FIRST)
            kernel_file.write(bytes((ability.first, ability.last)))
    for ability in changed:
        ability.loaded_first, ability.loaded_last = ability.first, ability.last
    return len(changed)
