from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd

import csv

from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.section import Section
from FF8GameData.GenericSection.listff8text import ListFF8Text
from FF8GameData.menu.mngrp.m00x.m00xmanager import m00XManager
from FF8GameData.menu.mngrp.m00x.sectionm00bin import Sectionm00Bin
from FF8GameData.menu.mngrp.seedtest.sectionseedtest import SectionSeedTest
from FF8GameData.menu.mngrp.string.sectionstring import SectionString
from FF8GameData.menu.mngrp.textbox.sectionmaptextbox import SectionMapTextBox
from FF8GameData.menu.mngrp.textbox.sectiontextboxentry import SectionTextBoxEntry
from FF8GameData.menu.mngrp.textbox.textboxmanager import TextBoxManager
from FF8GameData.menu.mngrp.tkmnmes.sectiontkmnmes import SectionTkmnmes


class MngrpManager:
    def __init__(self, game_data: GameData):

        self.mngrphd = None
        self.mngrp = None
        self.game_data = game_data
        self.text_box_manager = TextBoxManager()
        self.m00_manager = m00XManager()
        self.mngrp_path = ""  # The files last loaded, so callers can find sysfnt.tdw next to them
        self.mngrphd_path = ""
        self._as_loaded = ([], [])  # (bytes, encoded bytes) per section at the load or last save

    def __str__(self):
        return str(self.mngrp)

    def __repr__(self):
        return self.__str__()

    def save_file(self, file_mngrp, file_mngrphd):

        encoded = self._encode_sections()
        # A section nobody changed is written as it was loaded: re-encoding it can drop bytes the
        # codec does not keep (padding, alternative encodings), so every save would rewrite
        # sections nobody edited. It stands in as raw bytes for this write only.
        section_list = self.mngrp.get_section_list()
        loaded_bytes = self._as_loaded[0]
        parsed = {}
        for place in self._untouched_sections(encoded):
            parsed[place] = section_list[place]
            section_list[place] = Section(game_data=self.game_data, data_hex=bytearray(loaded_bytes[place]),
                                          id=parsed[place].id, own_offset=parsed[place].own_offset,
                                          name=parsed[place].name)
        try:
            self.mngrp.update_data_hex()
            # Updating mngrphd value from the new mngrp computed
            self.mngrphd.update_from_section_list(section_list)
            self.mngrphd.update_data_hex()
            written = [bytes(section.get_data_hex()) for section in section_list]
        finally:
            for place, section in parsed.items():
                section.own_offset = section_list[place].own_offset
                section_list[place] = section

        with open(file_mngrp, "wb") as in_file:
            in_file.write(self.mngrp.get_data_hex())
        with open(file_mngrphd, "wb") as in_file:
            in_file.write(self.mngrphd.get_data_hex())
        self._as_loaded = (written, encoded)

    def load_file(self, file_mngrphd, file_mngrp):
        self.mngrphd_path = file_mngrphd
        self.mngrp_path = file_mngrp
        mngrphd_data_hex = bytearray()
        mngrp_data_hex = bytearray()
        with open(file_mngrphd, "rb") as file:
            mngrphd_data_hex.extend(file.read())
        with open(file_mngrp, "rb") as file:
            mngrp_data_hex.extend(file.read())

        self.mngrphd = Mngrphd(self.game_data, mngrphd_data_hex)
        self.mngrphd.check_matches(len(mngrp_data_hex), file_mngrp)
        self.mngrp = Mngrp(self.game_data, mngrp_data_hex, self.mngrphd.get_entry_list())
        loaded_bytes = [bytes(section.get_data_hex()) for section in self.mngrp.get_section_list()]
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
                        new_section.section_data_linked = section
                        new_section.section_data_linked.section_text_linked = new_section
                        new_section.init_text(section.get_all_offset())
                        break
                m00msg_counter += 1

            elif section_data_type == SectionType.MNGRP_SEED_TEST:
                new_section = SectionSeedTest(game_data=self.game_data, data_hex=section_data_hex, id=section_id,
                                              own_offset=section_offset_value, name=section_name)
            else:  # Just saving the data, but will not be modified
                new_section = None  # No need to create a new section
            if new_section:
                self.mngrp.set_section_by_id(section_id, new_section)
        self._as_loaded = (loaded_bytes, self._encode_sections())

    def _encode_sections(self):
        """Every section encoded from its current content, as the save would write it.

        Each section keeps its current bytes: Mngrp.update_data_hex shifts the sections after one
        that changed size by comparing the size before and after its own encoding."""
        self.text_box_manager.update_map_offset()
        self.m00_manager.update_offset()
        encoded = []
        for section in self.mngrp.get_section_list():
            current = section.get_data_hex()
            section.update_data_hex()
            encoded.append(bytes(section.get_data_hex()))
            section._set_data_hex(current)
        return encoded

    def _untouched_sections(self, encoded):
        """Places of the sections whose content did not change since the load (or the last save).

        Sections whose offsets depend on each other (the text box map and its entries, a m00X.bin
        and its m00X.msg) only count as untouched together."""
        untouched = {place for place, (now, then) in enumerate(zip(encoded, self._as_loaded[1])) if now == then}
        place_of = {id(section): place for place, section in enumerate(self.mngrp.get_section_list())}
        for group in (self.text_box_manager.get_section_list(),
                      self.m00_manager.get_bin_list() + self.m00_manager.get_msg_list()):
            places = {place_of[id(section)] for section in group if id(section) in place_of}
            if not places <= untouched:
                untouched -= places
        return untouched
