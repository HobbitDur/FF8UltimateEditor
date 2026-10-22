"""Stable item IDs for FFNx AddMoreItems (kernel section numbers are one-based)."""

BATTLE_SECTION = 8
NAME_SECTION = 9
ORIGINAL_BATTLE_COUNT = 33
ORIGINAL_NAME_COUNT = 166
FIRST_ADDED_ID = 199
MAX_ITEM_ID = 255
MAX_BATTLE_ID = 254


def battle_item_id(row):
    return row if row < ORIGINAL_BATTLE_COUNT else FIRST_ADDED_ID + row - ORIGINAL_BATTLE_COUNT


def battle_item_row(item_id):
    if 0 <= item_id < ORIGINAL_BATTLE_COUNT:
        return item_id
    if FIRST_ADDED_ID <= item_id <= MAX_BATTLE_ID:
        return ORIGINAL_BATTLE_COUNT + item_id - FIRST_ADDED_ID
    return None


class ItemDefinitions:
    def __init__(self, kernel_manager):
        self.manager = kernel_manager

    def section(self, section_id):
        return next(s for s in self.manager.section_list if s is not None and s.id == section_id)

    @property
    def count(self):
        return ORIGINAL_BATTLE_COUNT + len(self.section(NAME_SECTION).get_subsection_list())

    def validate(self):
        battle = self.section(BATTLE_SECTION)
        names = self.section(NAME_SECTION)
        nb = len(battle.get_subsection_list())
        nn = len(names.get_subsection_list())
        if not ORIGINAL_BATTLE_COUNT <= nb <= 89 or not ORIGINAL_NAME_COUNT <= nn <= 223:
            raise ValueError("FFNx items require 33-89 battle records and 166-223 item-name records.")
        if FIRST_ADDED_ID + nb - ORIGINAL_BATTLE_COUNT > ORIGINAL_BATTLE_COUNT + nn:
            raise ValueError("An added battle item has no matching item-name record.")
        for section in (battle, names):
            if section.section_text_linked is None or len(section.section_text_linked.get_text_list()) < 2 * len(section.get_subsection_list()):
                raise ValueError("Item names/descriptions are missing from the linked text section.")

    def text_source(self, item_id):
        if not 0 <= item_id < self.count:
            raise ValueError("Unknown item ID.")
        section = self.section(BATTLE_SECTION if item_id < ORIGINAL_BATTLE_COUNT else NAME_SECTION)
        index = item_id if item_id < ORIGINAL_BATTLE_COUNT else item_id - ORIGINAL_BATTLE_COUNT
        return section.section_text_linked, index

    def text(self, item_id, text_index=0):
        section, index = self.text_source(item_id)
        return section.get_text_list()[2 * index + text_index].get_str()

    def names(self):
        return {item_id: self.text(item_id) for item_id in range(self.count)}

    def existing_battle_row(self, item_id):
        row = battle_item_row(item_id)
        return row if row is not None and row < len(self.section(BATTLE_SECTION).get_subsection_list()) else None

    def _append(self, section_id, name, description, payload=None):
        section = self.section(section_id)
        subsection = section.append_blank_subsection()
        texts = section.section_text_linked
        for value in (name, description):
            texts.add_text(bytearray([0]))
            texts.get_text_list()[-1].set_str(value)
        if payload is not None:
            subsection.get_data_list()[-1].get_data_hex()[:] = payload
        return subsection

    def ensure_battle(self, item_id, template_id=1):
        self.validate()
        row = battle_item_row(item_id)
        if row is None or item_id >= self.count:
            raise ValueError("Added battle settings are available only for item IDs 199-254.")
        section = self.section(BATTLE_SECTION)
        if row < len(section.get_subsection_list()):
            return row
        template = self.existing_battle_row(template_id)
        if template is None:
            template = 1  # Potion is a safe, editable starting point.
        payload = bytes(section.get_subsection_list()[template].get_data_list()[-1].get_data_hex())
        while len(section.get_subsection_list()) <= row:
            index = len(section.get_subsection_list())
            current_id = battle_item_id(index)
            # Backfill field-only IDs with disabled records; the append format is dense.
            inactive = bytearray(20)
            inactive[10 - 4] = 0x20  # native selectability is off; random-select remains zero
            self._append(BATTLE_SECTION, self.text(current_id), self.text(current_id, 1),
                         payload if index == row else inactive)
        return row

    def add(self, name, description="", template_id=1, battle=True):
        self.validate()
        item_id = self.count
        if item_id > MAX_ITEM_ID:
            raise ValueError("All 255 usable item IDs are already defined.")
        if not name.strip():
            raise ValueError("Enter a name for the new item.")
        if not 1 <= template_id < item_id:
            raise ValueError("Choose an existing nonempty item as the template.")
        if battle and item_id > MAX_BATTLE_ID:
            raise ValueError("Item ID 255 is field-only.")
        self._append(NAME_SECTION, name, description)
        if battle:
            self.ensure_battle(item_id, template_id)
        return item_id

    def sync_battle_text(self):
        """Appended battle text is redundant; the canonical names remain in section9."""
        section = self.section(BATTLE_SECTION)
        texts = section.section_text_linked.get_text_list()
        for row in range(ORIGINAL_BATTLE_COUNT, len(section.get_subsection_list())):
            item_id = battle_item_id(row)
            for index in range(2):
                texts[row * 2 + index].set_str(self.text(item_id, index))
