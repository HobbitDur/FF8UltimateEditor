import csv

from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text
from ShumiTranslator.model.kernel.kernelsectiondata import SectionData
from ShumiTranslator.model.kernel.kernelsectionheader import SectionHeader


class KernelManager():
    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.section_list = []

    def save_file(self, file):
        current_offset = 0
        current_file_data = bytearray()

        # Then creating the file
        for index_section, section in enumerate(self.section_list):
            # First updating all offset on section data
            if section.type == SectionType.DATA and section.section_text_linked:
                section_text_linked = section.section_text_linked
                section_text_list = section_text_linked.get_text_list()
                section.set_all_offset(section_text_list)
            # Then updating text
            if section.type == SectionType.FF8_TEXT:
                section.update_data_hex()
                self.section_list[0].set_section_offset_value_from_id(index_section, current_offset)
            if section.type == SectionType.DATA:
                section.update_data_hex()
                self.section_list[0].set_section_offset_value_from_id(index_section, current_offset)
            current_offset += len(section)

        for section in self.section_list:
            current_file_data.extend(section.get_data_hex())
        with open(file, "wb") as in_file:
            in_file.write(current_file_data)

    def load_file(self, file):
        current_file_data = bytearray()
        with open(file, "rb") as in_file:
            while el := in_file.read(1):
                current_file_data.extend(el)
        # First we read all offset section
        self.section_list = []
        # +1 for the number of section
        section_header = SectionHeader(game_data=self.game_data, data_hex=current_file_data[0:(len(
            self.game_data.kernel_data_json["sections"]) + 1) * SectionHeader.OFFSET_SIZE], name="header")
        self.section_list.append(section_header)
        for index, section_info in enumerate(self.game_data.kernel_data_json["sections"]):
            section_id = index + 1
            section_offset_value = self.section_list[0].get_section_offset_value_from_id(section_id)
            next_section_offset_value = self.section_list[0].get_section_offset_value_from_id(section_id + 1)
            own_offset = section_offset_value
            if next_section_offset_value is None:
                next_section_offset_value = len(current_file_data)
            if section_info["type"] == SectionType.DATA:
                data_hex = current_file_data[own_offset:next_section_offset_value]
                # if section_info['id'] == 4:
                #     index_unknown = 0
                #     for i in range(0, 33*12, 12):
                #         print(f"Weapons Data Section: {self.game_data.kernel_data_json['weapon_data'][index_unknown]}")
                #         print(f"Unknown 0x03:  {data_hex[i+0x03]}")
                #         #{" ".join(f"0x{byte:02X}" for byte in data_hex[i + 0x15:i + 0x15 + 7])}
                #         index_unknown+=1
                new_section = SectionData(game_data=self.game_data, id=section_id, own_offset=own_offset,
                                          data_hex=data_hex,
                                          subsection_nb_text_offset=section_info['sub_section_nb_text_offset'],
                                          name=section_info['section_name'])
                new_section.init_subsection(nb_subsection=section_info['number_sub_section'],
                                            subsection_sized=section_info['sub_section_size'])
            elif section_info["type"] == SectionType.FF8_TEXT:
                section_data_linked = [self.section_list[i] for i in range(1, len(self.section_list)) if
                                       section_info['section_id_data_linked'] == self.section_list[i].id][0]
                new_section = ListFF8Text(game_data=self.game_data, id=section_id, own_offset=own_offset,
                                          data_hex=current_file_data[own_offset:next_section_offset_value],
                                          section_data_linked=section_data_linked,
                                          name=section_info['section_name'])
            else:
                new_section = None
            self.section_list.append(new_section)

        for i, section in enumerate(self.section_list):
            if section.type == SectionType.FF8_TEXT:
                # Adding the link from data to text as text were not constructed yet.
                section.section_data_linked.section_text_linked = section
                # Initializing the text now that we can get all the offset
                section.init_text(section.section_data_linked.get_all_offset())