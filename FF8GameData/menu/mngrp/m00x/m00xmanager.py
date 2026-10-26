from FF8GameData.gamedata import SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text
from FF8GameData.menu.mngrp.m00x.sectionm00bin import Sectionm00Bin


class m00XManager:

    def __init__(self):
        self._m00bin_list = []
        self._m00msg_list = []
        self.type = SectionType.DATA

    def add_bin(self, bin_section: Sectionm00Bin):
        self._m00bin_list.append(bin_section)

    def add_msg(self, msg_section: ListFF8Text):
        self._m00msg_list.append(msg_section)

    def get_bin_list(self):
        """The m00x bin sections, holding the refine entries (m000 to m004)."""
        return self._m00bin_list

    def get_msg_list(self):
        """The m00x msg sections, holding the text of the entries of the bin section of the same
        place: the text of the nth entry of a bin is the nth text of its msg."""
        return self._m00msg_list

    def insert_entry(self, m00_id, index, entry, text_hex):
        """Insert an entry and its text at the same place of a table, so they stay lined up."""
        self._m00bin_list[m00_id].entries.insert(index, entry)
        self._keeping_file_bytes(self._m00msg_list[m00_id], lambda msg: msg.insert_text(index, bytearray(text_hex)))

    def remove_entry(self, m00_id, index):
        del self._m00bin_list[m00_id].entries[index]
        self._keeping_file_bytes(self._m00msg_list[m00_id], lambda msg: msg.remove_text(index))

    @staticmethod
    def _keeping_file_bytes(msg_section, change):
        """insert_text / remove_text re-encode the section at once, unpadded. Mngrp's save moves the
        sections after one by how much it grew from the bytes it holds until then (padded, as read),
        so those stay until the save re-encodes it."""
        file_bytes = msg_section.get_data_hex()
        change(msg_section)
        msg_section._set_data_hex(file_bytes)

    def update_offset(self):
        for i in range(len(self._m00bin_list)):
            self._m00bin_list[i].set_offset_by_text_list(self._m00msg_list[i].get_text_list())
