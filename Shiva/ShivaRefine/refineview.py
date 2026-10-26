"""The refine abilities of mngrp.bin, read from a shared MngrpManager.

No Qt here: the Shiva tab and the CLI both read the refine data this way, so they cannot
disagree on how the entries and their text line up.

A refine table (m000 to m004) is one flat list of entries; kernel.bin's menu abilities each give
the first and last entry of their slice of it (FF8GameData/menu/mngrp/m00x/refineabilities.py).
That is the only place the slices come from: with a kernel.bin, the views are its abilities and
recipes can be added or removed, every range after the change moving with it. Without one, each
table is a single view of all its entries, editable but with a fixed count.
"""
import copy

from FF8GameData.menu.mngrp.m00x.refineabilities import (MAX_ABILITY_ENTRIES, MAX_MSG_SIZE,
                                                         MAX_TABLE_ENTRIES, RefineAbility,
                                                         check_refine_ranges)


class RefineView:
    """A slice of a m00x table - a refine ability, or a whole table - with the text objects of its
    msg section.

    The entries and the texts belong to the shared mngrp and are edited in place: the m00x
    sections keep the text of an entry in another section (the msg one), the two lined up by
    position. The offsets between them are recomputed when the file is written."""

    def __init__(self, bin_section, msg_section, ability, kind, editable_range):
        self.bin_section = bin_section
        self.msg_section = msg_section
        self.ability = ability
        self.kind = kind                      # "ability", "table" (no kernel.bin) or "unused"
        self.editable_range = editable_range  # a kernel.bin ability: recipes can be added or removed
        self.bin_name = bin_section.m00bin.name
        self.input_type = bin_section.m00bin.input_id
        self.output_type = bin_section.m00bin.output_id

    @property
    def key(self):
        """Names the same slice across rebuilds of the layout (the list selection follows it)."""
        if self.kind == "ability":
            return self.table, self.kind, self.ability.index
        return self.table, self.kind, self.first if self.kind == "unused" else 0

    @property
    def name(self):
        return self.ability.name

    @property
    def description(self):
        return self.ability.description

    @property
    def table(self):
        return self.ability.table

    @property
    def first(self):
        return self.ability.first

    @property
    def last(self):
        return self.ability.last

    @property
    def entries(self):
        return self.bin_section.entries[self.ability.first:self.ability.last + 1]

    @property
    def texts(self):  # One FF8Text per entry, same order
        return self.msg_section.get_text_list()[self.ability.first:self.ability.last + 1]

    def duplicate_inputs(self):
        """{row: earlier row} of the entries taking the same input as an earlier one. Only for an
        ability: the refine menu uses the first entry of the slice matching the item, the later
        ones never show."""
        if self.kind != "ability":
            return {}
        first_row = {}
        duplicates = {}
        for row, entry in enumerate(self.entries):
            if entry.element_in_id in first_row:
                duplicates[row] = first_row[entry.element_in_id]
            else:
                first_row[entry.element_in_id] = row
        return duplicates


class RefineLayout:
    """Every refine ability of a mngrp, sliced as a kernel.bin says (or one view per table)."""

    def __init__(self, manager, abilities=None):
        """abilities: kernel.bin's RefineAbility list (read_refine_abilities), None without one."""
        self.manager = manager
        self.m00_manager = manager.m00_manager
        self.from_kernel = abilities is not None
        self.abilities = list(abilities or [])
        self.views = []
        self.warnings = []
        self._build_views()

    @property
    def ranges_changed(self):
        return any(ability.changed for ability in self.abilities)

    def tables(self):
        """[(bin section, msg section)] of m000 to m004."""
        return list(zip(self.m00_manager.get_bin_list(), self.m00_manager.get_msg_list()))

    def abilities_offering(self, table, index):
        """The kernel.bin abilities whose slice holds entry `index` of `table`."""
        return [ability for ability in self.abilities
                if ability.table == table and ability.first <= index <= ability.last]

    def _build_views(self):
        self.views = []
        self.warnings = []
        for table, (bin_section, msg_section) in enumerate(self.tables()):
            count = len(bin_section.entries)
            if not self.from_kernel:
                whole = RefineAbility(index=None, table=table, first=0, last=count - 1, name="all recipes",
                                      description="The abilities offering them come from kernel.bin")
                self.views.append(RefineView(bin_section, msg_section, whole, "table", False))
                continue
            in_table = sorted((ability for ability in self.abilities if ability.table == table),
                              key=lambda ability: (ability.first, ability.index))
            for ability in in_table:
                self.views.append(RefineView(bin_section, msg_section, ability, "ability", True))
                if ability.last >= count:
                    self.warnings.append(f"{ability.name} offers recipes {ability.first}-{ability.last} "
                                         f"of {bin_section.m00bin.name}, which only has {count}: "
                                         f"the extra ones are empty.")
            # Entries no ability offers stay editable, so nothing in the file is out of sight
            covered = set()
            for ability in in_table:
                covered.update(range(ability.first, ability.last + 1))
            gap_start = None
            for index in range(count + 1):
                if index < count and index not in covered:
                    if gap_start is None:
                        gap_start = index
                elif gap_start is not None:
                    gap = RefineAbility(index=None, table=table, first=gap_start, last=index - 1,
                                        name=f"(no ability) {gap_start}-{index - 1}",
                                        description="Entries of the table no refine ability of kernel.bin offers")
                    self.views.append(RefineView(bin_section, msg_section, gap, "unused", False))
                    gap_start = None

    def insert_entry(self, view, row):
        """Insert a copy of the entry at `row` of view (and of its text) right after it, and move
        every range of that table it pushes. Returns the new entry's row."""
        if not view.editable_range:
            raise ValueError("Recipes can only be added to a refine ability of kernel.bin, which holds their range")
        table = view.table
        if len(view.bin_section.entries) >= MAX_TABLE_ENTRIES:
            raise ValueError(f"{view.bin_name} already holds {MAX_TABLE_ENTRIES} recipes, the game reads no more")
        if view.ability.count >= MAX_ABILITY_ENTRIES:
            raise ValueError(f"{view.name} already has {MAX_ABILITY_ENTRIES} recipes, the game counts no more")
        row = min(max(row, 0), len(view.entries) - 1)
        position = view.first + row + 1
        source_entry = view.bin_section.entries[view.first + row]
        source_text = view.msg_section.get_text_list()[view.first + row]
        self.m00_manager.insert_entry(table, position, copy.copy(source_entry), source_text.get_data_hex())
        for ability in self.abilities:
            if ability is view.ability or ability.table != table:
                continue
            if ability.first >= position:
                ability.first += 1
            if ability.last >= position:
                ability.last += 1
        view.ability.last += 1
        self._build_views()
        return row + 1

    def remove_entry(self, view, row):
        """Remove the entry at `row` of view (and its text), and move every later range back."""
        if not view.editable_range:
            raise ValueError("Recipes can only be removed from a refine ability of kernel.bin, which holds their range")
        if view.ability.count <= 1:
            raise ValueError(f"{view.name} needs at least one recipe")
        table = view.table
        position = view.first + row
        others = [ability for ability in self.abilities if ability is not view.ability and ability.table == table]
        for ability in others:
            if ability.first == ability.last == position:
                raise ValueError(f"{ability.name} also offers that recipe, and only that one")
        self.m00_manager.remove_entry(table, position)
        for ability in others:
            if ability.first > position:
                ability.first -= 1
            if ability.last >= position:
                ability.last -= 1
        view.ability.last -= 1
        self._build_views()

    def check_game_limits(self):
        """The reasons the game could not read this layout ([] when it can)."""
        errors = check_refine_ranges(self.abilities)
        for bin_section, msg_section in self.tables():
            if len(bin_section.entries) > MAX_TABLE_ENTRIES:
                errors.append(f"{bin_section.m00bin.name}: {len(bin_section.entries)} recipes, "
                              f"the game reads {MAX_TABLE_ENTRIES} at most")
            text_size = sum(len(text) for text in msg_section.get_text_list())
            if text_size > MAX_MSG_SIZE:
                errors.append(f"{bin_section.m00bin.name}: {text_size} bytes of recipe text, "
                              f"the game reads {MAX_MSG_SIZE} at most")
        return errors


def build_refine_views(manager, abilities=None):
    """The RefineView of every refine ability (see RefineLayout)."""
    return RefineLayout(manager, abilities).views
