from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd
from ShumiTranslator.model.mngrp.m00x.m00xmanager import m00XManager
from ShumiTranslator.model.mngrp.textbox.sectiontextboxentry import SectionTextBoxEntry
from ShumiTranslator.model.mngrp.textbox.textboxmanager import TextBoxManager
from ShumiTranslator.model.mngrp.textbox.sectionmaptextbox import SectionMapTextBox
from ShumiTranslator.model.mngrp.m00x.sectionm00bin import Sectionm00Bin
from ShumiTranslator.model.mngrp.string.sectionstring import SectionString

from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text
from ShumiTranslator.model.mngrp.tkmnmes.sectiontkmnmes import SectionTkmnmes


class MngrpManager:
    def __init__(self, game_data: GameData):

        self.mngrphd = None
        self.mngrp = None
        self.game_data = game_data
        self.text_box_manager = TextBoxManager()
        self.m00_manager = m00XManager()

    def __str__(self):
        return str(self.mngrp)

    def __repr__(self):
        return self.__str__()

    def save_file(self, file_mngrp, file_mngrphd):

        # Some sections are interdependent, so we update their value first
        self.text_box_manager.update_map_offset()
        self.m00_manager.update_offset()

        # then we update mngrp hex
        self.mngrp.update_data_hex()

        # Updating mngrphd value from the new mngrp computed
        self.mngrphd.update_from_section_list(self.mngrp.get_section_list())
        self.mngrphd.update_data_hex()

        with open(file_mngrp, "wb") as in_file:
            in_file.write(self.mngrp.get_data_hex())
        with open(file_mngrphd, "wb") as in_file:
            in_file.write(self.mngrphd.get_data_hex())

    def load_file(self, file_mngrphd, file_mngrp):
        mngrphd_data_hex = bytearray()
        mngrp_data_hex = bytearray()
        with open(file_mngrphd, "rb") as file:
            mngrphd_data_hex.extend(file.read())
        with open(file_mngrp, "rb") as file:
            mngrp_data_hex.extend(file.read())

        self.mngrphd = Mngrphd(self.game_data, mngrphd_data_hex)
        self.mngrp = Mngrp(self.game_data, mngrp_data_hex, self.mngrphd.get_entry_list())
        self.text_box_manager = TextBoxManager()
        self.m00_manager = m00XManager()


        # First we read all offset section
        m00bin_counter = 0
        m00msg_counter = 0
        for index, section_mngrp in enumerate(self.mngrp.get_section_list()):
            if self.mngrphd.get_entry_list()[index].invalid_value:  # If it's a non-existent section, ignore it
                continue
            section_id = section_mngrp.id
            section_data_type = self.game_data.mngrp_data_json["sections"][section_id]["data_type"]
            section_name = self.game_data.mngrp_data_json["sections"][section_id]["section_name"]
            section_offset_value = section_mngrp.own_offset
            section_data_hex = section_mngrp.get_data_hex()

            if section_data_type == SectionType.MNGRP_STRING:
                new_section = SectionString(game_data=self.game_data, data_hex=section_data_hex, id=section_id,
                                            own_offset=section_offset_value, name=section_name)
            elif section_data_type == SectionType.FF8_TEXT:
                new_section = ListFF8Text(game_data=self.game_data, id=section_id, own_offset=section_offset_value,
                                          data_hex=section_data_hex,
                                          section_data_linked=None,
                                          name=section_name)
            elif section_data_type == SectionType.TKMNMES:
                new_section = SectionTkmnmes(game_data=self.game_data, id=section_id, own_offset=section_offset_value,
                                             data_hex=section_data_hex,
                                             name=section_name)
            elif section_data_type == SectionType.MNGRP_MAP_COMPLEX_STRING:
                map_complex_string = SectionMapTextBox(game_data=self.game_data, id=section_id,
                                                       own_offset=section_offset_value,
                                                       data_hex=section_data_hex,
                                                       name=section_name)
                self.text_box_manager.add_map_section(map_complex_string)
                new_section = map_complex_string
            elif section_data_type == SectionType.MNGRP_TEXTBOX:
                new_section = SectionTextBoxEntry(game_data=self.game_data, id=section_id,
                                                  own_offset=section_offset_value,
                                                  data_hex=section_data_hex,
                                                  name=section_name)
                self.text_box_manager.add_string_entry(new_section)
            elif section_data_type == SectionType.MNGRP_M00BIN:
                new_section = Sectionm00Bin(game_data=self.game_data, id=section_id, own_offset=section_offset_value,
                                            data_hex=section_data_hex,
                                            name=section_name, m00_id=m00bin_counter)
                self.m00_manager.add_bin(new_section)
                m00bin_counter += 1
            elif section_data_type == SectionType.MNGRP_M00MSG:
                new_section = ListFF8Text(game_data=self.game_data, id=section_id, own_offset=section_offset_value,
                                          data_hex=section_data_hex,
                                          name=section_name)
                new_section.type = SectionType.MNGRP_M00MSG
                self.m00_manager.add_msg(new_section)
                for section in self.mngrp.get_section_list():
                    if section.type == SectionType.MNGRP_M00BIN and section.m00_id == m00msg_counter:
                        section.section_data_linked = section
                        section.section_data_linked.section_text_linked = new_section
                        new_section.init_text(section.get_all_offset())
                        break
                m00msg_counter += 1

            else:  # Just saving the data, but will not be modified
                new_section = None  # No need to create a new section
            if new_section:
                self.mngrp.set_section_by_id(section_id, new_section)
