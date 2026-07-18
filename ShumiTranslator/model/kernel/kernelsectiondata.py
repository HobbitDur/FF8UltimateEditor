from typing import List

from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData
from FF8GameData.GenericSection.listff8text import ListFF8Text
from ShumiTranslator.model.kernel.kernelsubsectiondata import SubSectionData


class SectionData(Section):
    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, subsection_nb_text_offset: int, name: str,
                 section_text_linked: ListFF8Text = None):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self._subsection_nb_text_offset = subsection_nb_text_offset
        self.section_text_linked = section_text_linked
        self._subsection_list = []
        self._subsection_size = None

    def init_subsection(self, subsection_sized: int, nb_subsection: int):
        self._subsection_size = subsection_sized
        for i in range(nb_subsection):
            self.add_subsection(self._data_hex[i * subsection_sized: (i + 1) * subsection_sized])
        self.update_data_hex()

    def append_blank_subsection(self):
        """Grow the section by one all-zero subsection (used by a "growable" section's
        Add-entry UI). Returns the new SubSectionData.

        Rebuilds ``_data_hex`` directly rather than via ``update_data_hex()`` - that
        method's rebuild is guarded to skip any length mismatch (so a bad load never
        silently drops trailing bytes), which would also block this deliberate growth."""
        blank = bytearray(self._subsection_size)
        self.add_subsection(blank)
        rebuilt = bytearray()
        for subsection in self._subsection_list:
            subsection.update_data_hex()
            rebuilt.extend(subsection.get_data_hex())
        self._data_hex = rebuilt
        self._size = len(self._data_hex)
        return self._subsection_list[-1]

    def add_subsection(self, data_hex: bytearray):
        if self._subsection_list:
            offset = self._subsection_list[-1].own_offset + self._subsection_list[-1].get_size()
            id = self._subsection_list[-1].id + 1
        else:
            offset = 0
            id = 0
        self._subsection_list.append(
            SubSectionData(game_data=self._game_data, data_hex=data_hex, own_offset=offset, id=id, nb_text_offset=self._subsection_nb_text_offset))



    def update_data_hex(self):
        """Rebuild the section raw bytes from its subsections.

        This flushes in-place edits done on subsection payloads back into the
        section ``_data_hex`` for every data section (``set_all_offset`` only does
        this for sections that own a linked text section). As a safety guard, the
        rebuild is skipped when the subsections do not fully cover the section
        (which would otherwise drop trailing bytes)."""
        rebuilt = bytearray()
        for subsection in self._subsection_list:
            subsection.update_data_hex()
            rebuilt.extend(subsection.get_data_hex())
        if len(rebuilt) == len(self._data_hex):
            self._data_hex = rebuilt
        self._size = len(self._data_hex)
        return self._data_hex

    def get_all_offset(self):
        offset_list = []

        for subsection in self._subsection_list:
            sub_offset_list = subsection.get_all_offset()
            offset_list.extend(sub_offset_list)
        return offset_list

    def set_all_offset(self, text_list):
        text_index = 0
        current_section_offset = 0
        for i in range(len(self._subsection_list)):
            current_section_offset = self._subsection_list[i].set_offset_values(
                text_list[text_index:text_index + self._subsection_list[i].nb_data_with_offset()], current_section_offset)
            text_index += self._subsection_list[i].nb_data_with_offset()
        self._data_hex = bytearray()
        for data in self._subsection_list:
            self._data_hex.extend(data.get_data_hex())
        self._size = len(self._data_hex)

    def get_subsection_list(self) -> List[SubSectionData]:
        return self._subsection_list

    def set_offset_from_id(self, subsection_id:int, data_id:int, value:int):
        self._subsection_list[subsection_id].set_offset_from_id(data_id, value)
