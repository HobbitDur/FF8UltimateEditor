from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.listff8text import ListFF8Text
from FF8GameData.m00x.dataclass import m000bin, m001bin, m002bin, m003bin, m004bin, TypeId


class Sectionm00Bin(Section):
    OFFSET_SIZE = 2

    def __init__(self, game_data: GameData, data_hex: bytearray, id: int, own_offset: int, m00_id: int, name: str,
                 section_text_linked: ListFF8Text = None):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=id, own_offset=own_offset, name=name)
        self.m00_id = m00_id
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

        for data in self.m00bin.list_data:
            if self.m00bin.input_id == TypeId.CARD:
                input_table = self._game_data.card_data_json["card_info"]
            elif self.m00bin.input_id == TypeId.SPELL:
                input_table = self._game_data.magic_data_json["magic"]
            elif self.m00bin.input_id == TypeId.ITEM:
                input_table = self._game_data.item_data_json['items']
            else:
                print("Error reading input table")
                exit(0)
            if self.m00bin.output_id == TypeId.CARD:
                output_table = self._game_data.card_data_json["card_info"]
            elif self.m00bin.output_id == TypeId.SPELL:
                output_table = self._game_data.magic_data_json["magic"]
            elif self.m00bin.output_id == TypeId.ITEM:
                output_table = self._game_data.item_data_json['items']
            else:
                print("Error reading output table")
                exit(0)
            index = data.offset
            for entry in data.entries:
                entry.text_offset = int.from_bytes(bytearray(self._data_hex[index:index + 2]), byteorder='little')
                entry.amount_received = int(self._data_hex[index + 2])
                entry.unk = int.from_bytes(bytearray(self._data_hex[index + 3:index + 5]), byteorder='little')
                entry.element_in_id = int(self._data_hex[index + 5])
                entry.amount_required = int(self._data_hex[index + 6])
                entry.element_out_id = int(self._data_hex[index + 7])
                index += entry.ENTRY_SIZE

    def get_all_offset(self):
        offset_list = []
        for data in self.m00bin.list_data:
            for entry in data.entries:
                offset_list.append(entry.text_offset)
        return offset_list

    def set_offset_by_text_list(self, text_list):
        text_offset = 0
        nb_entry = 0
        for data in self.m00bin.list_data:
            for entry in data.entries:
                entry.text_offset = text_offset
                text_offset += len(text_list[nb_entry])
                nb_entry+=1
        if nb_entry != len(text_list):
            print(f"Not same number of entry: {nb_entry} than the size of text list: {len(text_list)}")


    def update_data_hex(self):
        self._data_hex = bytearray()
        for index_data, data in enumerate(self.m00bin.list_data):
            for nb_entry, entry in enumerate(data.entries):
                self._data_hex.extend(entry.text_offset.to_bytes(length=2, byteorder="little"))
                self._data_hex.extend(entry.amount_received.to_bytes(length=1, byteorder="little"))
                self._data_hex.extend(entry.unk.to_bytes(length=2, byteorder="little"))
                self._data_hex.extend(entry.element_in_id.to_bytes(length=1, byteorder="little"))
                self._data_hex.extend(entry.amount_required.to_bytes(length=1, byteorder="little"))
                self._data_hex.extend(entry.element_out_id.to_bytes(length=1, byteorder="little"))
        self._size = len(self._data_hex)




