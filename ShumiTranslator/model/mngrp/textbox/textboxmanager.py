from FF8GameData.gamedata import SectionType
from ShumiTranslator.model.mngrp.textbox.textboxentry import TextBoxEntry
from ShumiTranslator.model.mngrp.textbox.sectiontextboxentry import SectionTextBoxEntry
from ShumiTranslator.model.mngrp.textbox.sectionmaptextbox import SectionMapTextBox


class TextBoxManager:
    OFFSET_SIZE = 2
    HEADER_SIZE = 4

    def __init__(self):
        self._nb_offset = 0
        self._map_section = None
        self._complex_string_entry_list = []
        self.type = SectionType.MNGRP_TEXTBOX

    def __str__(self):
        return f"{str(self._map_section)} \n {self._complex_string_entry_list}"

    def add_map_section(self, map_section: SectionMapTextBox):
        self._map_section = map_section

    def add_string_entry(self, string_entry: SectionTextBoxEntry):
        if not self._map_section:
            print("First add a map before adding string entry")
            return
        offset_list = self._map_section.get_offset_list_from_id(len(self._complex_string_entry_list))
        string_entry.init_section(offset_list)
        self._complex_string_entry_list.append(string_entry)

    def get_text_section_by_id(self, section_id):
        return self._complex_string_entry_list[section_id].get_text_section()

    def update_map_offset(self):
        for i in range(len(self._complex_string_entry_list)):
            shift = TextBoxEntry.ENTRY_LENGTH + TextBoxEntry.TEXT_BOX_ID_SIZE * 3
            self._map_section.set_offset_from_text_list(self._complex_string_entry_list[i].get_text_list(), i,
                                                        shift=shift)
