"""The refine abilities of mngrp.bin, read from a shared MngrpManager.

No Qt here: the Shiva tab and the CLI both read the refine data this way, so they cannot
disagree on how the entries and their text line up.

A refine table (m000 to m004) is one flat list of entries; kernel.bin's menu abilities each give
the first and last entry of their slice of it (FF8GameData/menu/mngrp/m00x/refineabilities.py).
That is the only place the slices come from: with a kernel.bin, the views are its abilities and
recipes can be added or removed, every range after the change moving with it. Without one, each
table is a single view of all its entries.
"""
import copy

from FF8GameData.menu.mngrp.m00x.refineabilities import (MAX_MSG_SIZE,
                                                         MAX_TABLE_ENTRIES, RefineAbility,
                                                         check_no_overlap, check_refine_ranges)


class RefineView:
    """A slice of a m00x table - a refine ability, or a whole table - with the text objects of its
    msg section.

    The entries and the texts belong to the shared mngrp and are edited in place: the m00x
    sections keep the text of an entry in another section (the msg one), the two lined up by
    position. The offsets between them are recomputed when the file is written."""

    def __init__(self, bin_section, msg_section, ability, kind):
        self.bin_section = bin_section
        self.msg_section = msg_section
        self.ability = ability
        self.kind = kind                      # "ability", "table" (no kernel.bin) or "unused"
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
    """Every refine ability of a mngrp, sliced as a kernel.bin says (or one view per table).

    The abilities always keep the range kernel.bin gives them, so each view shows what the game
    shows. Adding or removing a recipe shifts every later entry of its table: the layout lists which
    abilities then need a new first/last entry in kernel.bin (kernel_warnings) and suggests them
    (suggested_ranges), for the Refine ranges dialog to write when asked."""

    def __init__(self, manager, abilities=None):
        """abilities: kernel.bin's RefineAbility list (read_refine_abilities), None without one.

        Each ability owns its own block of its table: abilities that overlap are refused
        (RefineKernelError)."""
        self.manager = manager
        self.m00_manager = manager.m00_manager
        self.from_kernel = abilities is not None
        self.abilities = list(abilities or [])
        self.views = []
        self.warnings = []
        self.shifts = {}         # table: [lowest entry index whose recipe moved, recipes added, removed]
        self.edits = []          # (table, entry index, +1 added / -1 removed, appended at the table's end), in order: suggested_ranges
        check_no_overlap(self.abilities)
        self._build_views()

    @property
    def kernel_update_needed(self):
        """True when the recipes moved since kernel.bin was read: its ranges need editing."""
        return bool(self.shifts)

    def tables(self):
        """[(bin section, msg section)] of m000 to m004."""
        return list(zip(self.m00_manager.get_bin_list(), self.m00_manager.get_msg_list()))

    def abilities_offering(self, table, index):
        """The kernel.bin abilities whose slice holds entry `index` of `table`."""
        return [ability for ability in self.abilities
                if ability.table == table and ability.first <= index <= ability.last]

    def kernel_warnings(self):
        """One line per table whose recipes moved: the abilities whose range in kernel.bin must change."""
        lines = []
        for table, (lowest, added, removed) in sorted(self.shifts.items()):
            name = self.tables()[table][0].m00bin.name
            stale = [ability for ability in sorted(self.abilities, key=lambda ability: ability.first)
                     if ability.table == table and ability.last >= lowest]
            changes = " and ".join(text for text in (f"{added} recipe(s) added" if added else "",
                                                     f"{removed} removed" if removed else "") if text)
            if stale:
                to_do = ("kernel.bin must be modified (\"Refine ranges...\" button) for these to offer "
                         "the right recipes again: "
                         + ", ".join(f"{ability.name} ({ability.first}-{ability.last})" for ability in stale))
            elif self.from_kernel:
                to_do = ("no refine ability's range moved: a recipe past them is offered by none until an "
                         "ability points at it in kernel.bin (\"Refine ranges...\" button)")
            else:
                to_do = ("kernel.bin must be modified (first/last entry of the refine abilities) for them "
                         "to offer the right recipes again: open it to see which")
            lines.append(f"{name}: {changes}, the recipes from entry {lowest} on moved. {to_do}")
        return lines

    def carry_edits(self, previous):
        """Take over the recipes added and removed in a previous layout of the same kernel.bin
        ranges (its warnings and suggested ranges still hold)."""
        self.shifts = previous.shifts
        self.edits = previous.edits
        self._build_views()

    def suggested_ranges(self):
        """{menu ability index: [first, last]}: kernel.bin's ranges moved along with the recipes
        added and removed since. A recipe added at entry p goes to the ability ending at p - 1 (or
        holding it); one removed shrinks the ability holding it; the later ranges move. A recipe
        appended after the table's last one moves none: only the ability ending at p - 1 grows
        (an append into a range that already covers p is not even recorded, see insert_at)."""
        ranges = {ability.index: [ability.first, ability.last] for ability in self.abilities}
        tables = {ability.index: ability.table for ability in self.abilities}
        for table, position, delta, appended in self.edits:
            in_table = [index for index in ranges if tables[index] == table]
            if appended:
                owner = next((index for index in in_table if ranges[index][1] == position - 1), None)
                if owner is not None:
                    ranges[owner][1] += 1
                continue
            if delta > 0:
                owner = next((index for index in in_table if ranges[index][0] <= position - 1 <= ranges[index][1]), None)
            else:
                owner = next((index for index in in_table if ranges[index][0] <= position <= ranges[index][1]), None)
            for index in in_table:
                first, last = ranges[index]
                if index == owner:
                    ranges[index] = [first, last + delta]
                elif delta > 0:
                    ranges[index] = [first + (first >= position), last + (last >= position)]
                else:
                    ranges[index] = [first - (first > position), last - (last >= position)]
        return ranges

    def _build_views(self):
        self.views = []
        self.warnings = []
        for table, (bin_section, msg_section) in enumerate(self.tables()):
            count = len(bin_section.entries)
            if not self.from_kernel:
                whole = RefineAbility(index=None, table=table, first=0, last=count - 1, name="all recipes",
                                      description="The abilities offering them come from kernel.bin")
                self.views.append(RefineView(bin_section, msg_section, whole, "table"))
                continue
            in_table = sorted((ability for ability in self.abilities if ability.table == table),
                              key=lambda ability: (ability.first, ability.index))
            for ability in in_table:
                self.views.append(RefineView(bin_section, msg_section, ability, "ability"))
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
                    self.views.append(RefineView(bin_section, msg_section, gap, "unused"))
                    gap_start = None
        self.warnings += self.kernel_warnings()

    def _record_shift(self, table, lowest, added=0, removed=0, appended=False):
        self.edits.append((table, lowest, added - removed, appended))
        shift = self.shifts.setdefault(table, [lowest, 0, 0])
        shift[0] = min(shift[0], lowest)
        shift[1] += added
        shift[2] += removed

    def insert_entry(self, view, row):
        """Insert a copy of the entry at `row` of view (and of its text) right after it (insert_at).
        Returns the new row (past the view's last one when inserted after it: the recipe then shows
        in the next ability, until kernel.bin is edited)."""
        if not view.entries:
            raise ValueError(f"{view.name} offers recipes {view.first}-{view.last} of {view.bin_name}, which has "
                             f"none there yet: add them after the table's last recipe first")
        row = min(max(row, 0), len(view.entries) - 1)
        self.insert_at(view.table, view.first + row + 1, view.first + row)
        return row + 1

    def insert_at(self, table, position, source_index):
        """Insert a copy of entry source_index of table (and of its text) at position, 0 to the
        table's count (after its last entry): every later recipe of the table moves down one, the
        ranges staying kernel.bin's.

        Appended after the last recipe, it moves none: when a range (as suggested) already covers
        that entry, the recipe fills it and nothing needs kernel.bin; otherwise only the ability
        ending right before it is suggested one longer."""
        bin_section, msg_section = self.tables()[table]
        count = len(bin_section.entries)
        if count >= MAX_TABLE_ENTRIES:
            raise ValueError(f"{bin_section.m00bin.name} already holds {MAX_TABLE_ENTRIES} recipes, the game reads no more")
        if not 0 <= position <= count:
            raise ValueError(f"{bin_section.m00bin.name}: a recipe goes at entry 0 to {count}, not {position}")
        appended = position == count
        fills = appended and any(first <= position <= last for index, (first, last) in self.suggested_ranges().items()
                                 if self._ability_table(index) == table)
        source_entry = bin_section.entries[source_index]
        source_text = msg_section.get_text_list()[source_index]
        self.m00_manager.insert_entry(table, position, copy.copy(source_entry), source_text.get_data_hex())
        if not fills:
            self._record_shift(table, position, added=1, appended=appended)
        self._build_views()

    def _ability_table(self, index):
        return next(ability.table for ability in self.abilities if ability.index == index)

    def remove_entry(self, view, row):
        """Remove the entry at `row` of view (and its text): see remove_at."""
        self.remove_at(view.table, view.first + row)

    def remove_at(self, table, position):
        """Remove entry `position` of table (and its text): every later recipe of the table moves up
        one, the ranges staying kernel.bin's."""
        bin_section = self.tables()[table][0]
        count = len(bin_section.entries)
        if count <= 1:
            raise ValueError(f"{bin_section.m00bin.name} needs at least one recipe")
        if not 0 <= position < count:
            raise ValueError(f"{bin_section.m00bin.name}: its recipes are entries 0 to {count - 1}, not {position}")
        self.m00_manager.remove_entry(table, position)
        self._record_shift(table, position, removed=1)
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
