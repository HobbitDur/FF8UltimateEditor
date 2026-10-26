from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text
from FF8GameData.m00x.dataclass import Entry, m000bin, m001bin, m002bin, m003bin, m004bin, TypeId


class Sectionm00Bin(Section):
    """One refine table (m000 to m004): a flat list of 8-byte entries.

    Which entries belong to which refine ability is not in the table: kernel.bin's menu abilities
    give each one a first/last entry (refineabilities.py). The section is padded with zeros up to
    2048 bytes in mngrp.bin, so the entries run up to the last one that is not all zeros (an entry
    after the first one always has a text offset, it cannot be all zeros)."""
    OFFSET_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, m00_id: int, name: str,
                 section_text_linked: ListFF8Text = None):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self.m00_id = m00_id
        self.section_text_linked = section_text_linked
        self.type = SectionType.MNGRP_M00BIN
        if m00_id == 0:
            self.m00bin = m000bin()
        elif m00_id == 1:
            self.m00bin = m001bin()
        elif m00_id == 2:
            self.m00bin = m002bin()
        elif m00_id == 3:
            self.m00bin = m003bin()
        elif m00_id == 4:
            self.m00bin = m004bin()
        else:
            print("Wrong m00_id, should be in [0;4]")

        for type_id in (self.m00bin.input_id, self.m00bin.output_id):
            if type_id not in (TypeId.CARD, TypeId.SPELL, TypeId.ITEM):
                raise ValueError(f"m00x section {self.m00bin.name}: unknown input/output type {type_id}")
        nb_entries = len(self._data_hex) // Entry.ENTRY_SIZE
        while nb_entries > 1 and not any(self._data_hex[(nb_entries - 1) * Entry.ENTRY_SIZE:
                                                         nb_entries * Entry.ENTRY_SIZE]):
            nb_entries -= 1
        self.entries = []
        for index in range(0, nb_entries * Entry.ENTRY_SIZE, Entry.ENTRY_SIZE):
            entry = Entry()
            entry.text_offset = int.from_bytes(bytearray(self._data_hex[index:index + 2]), byteorder='little')
            entry.amount_received = int.from_bytes(bytearray(self._data_hex[index + 2:index + 4]), byteorder='little')
            entry.required_gf_level = int(self._data_hex[index + 4])
            entry.element_in_id = int(self._data_hex[index + 5])
            entry.amount_required = int(self._data_hex[index + 6])
            entry.element_out_id = int(self._data_hex[index + 7])
            self.entries.append(entry)

    def get_all_offset(self):
        return [entry.text_offset for entry in self.entries]

    def set_offset_by_text_list(self, text_list):
        text_offset = 0
        for entry, text in zip(self.entries, text_list):
            entry.text_offset = text_offset
            text_offset += len(text)
        if len(self.entries) != len(text_list):
            print(f"Not same number of entry: {len(self.entries)} than the size of text list: {len(text_list)}")

    def update_data_hex(self):
        self._data_hex = bytearray()
        for entry in self.entries:
            self._data_hex.extend(entry.text_offset.to_bytes(length=2, byteorder="little"))
            self._data_hex.extend(entry.amount_received.to_bytes(length=2, byteorder="little"))
            self._data_hex.extend(entry.required_gf_level.to_bytes(length=1, byteorder="little"))
            self._data_hex.extend(entry.element_in_id.to_bytes(length=1, byteorder="little"))
            self._data_hex.extend(entry.amount_required.to_bytes(length=1, byteorder="little"))
            self._data_hex.extend(entry.element_out_id.to_bytes(length=1, byteorder="little"))
        self._size = len(self._data_hex)
