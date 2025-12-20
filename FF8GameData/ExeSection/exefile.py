from FF8GameData.GenericSection.offsetandtext import SectionOffsetAndText
from FF8GameData.GenericSection.section import Section
from FF8GameData.GenericSection.sizeandoffsetandtext import SectionSizeAndOffsetAndText
from FF8GameData.gamedata import GameData, LangType, MsdType, RemasterCardType


class SectionExeFile(Section):
    OFFSET_SIZE = 2
    GENERAL_OFFSET = 0x400000

    def __init__(self, game_data: GameData, data_hex):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=0, own_offset=0, name=".Exe")
        self._section_list = []
        if not self._game_data.exe_data_json:
            self._game_data.load_exe_data()
        self._lang = LangType.ENGLISH
        self.__analyse_data()

    def __str__(self):
        return str("To be define")

    def __repr__(self):
        return self.__str__()

    def produce_msd(self, msd_type: MsdType):
        """/!\\ Draw point and card text seems to have offset as int16 but I didn't manage that"""
        msd_offset_size = 4
        msd_data = bytearray()
        if msd_type == MsdType.CARD_NAME:
            id = 6
        elif msd_type == MsdType.SCAN_TEXT:
            id = 7
        elif msd_type == MsdType.CARD_TEXT:
            id = 4
        elif msd_type == MsdType.DRAW_POINT:
            id = 1
        else:
            print("Unknown msd type")
            id = 6

        index = [i for i in range(len(self._section_list)) if self._section_list[i].id == id][0]
        self._section_list[index].update_data_hex()
        offset_list = self._section_list[index].get_offset_section().get_all_offset()
        text_list = self._section_list[index].get_text_section().get_text_list()
        if len(text_list) != len(offset_list):
            print(f"Unexpected diff size between offset list (size:{len(offset_list)}) and text list (size:{len(text_list)}) for msd type: {msd_type}")
        first_offset = offset_list[0]
        if id != 7:
            # As the offset from .exe vary from the one use in msd, shift them !
            for i in range(len(offset_list)):
                if offset_list[i] == 0:
                    continue
                # First remove the original offset
                offset_list[i] -= first_offset
                # Then add the start of the first one for msd
                offset_list[i] += len(text_list) * msd_offset_size
                msd_data.extend(offset_list[i].to_bytes(length=msd_offset_size, byteorder="little"))
        else:
            # As the offset from .exe vary from the one use in msd, shift them !
            current_text_size = 0
            for i in range(len(text_list)):
                # First remove the original offset
                offset_list = current_text_size
                # Then add the start of the first one for msd
                offset_list += len(text_list) * msd_offset_size
                current_text_size += len(text_list[i])
                msd_data.extend(offset_list.to_bytes(length=msd_offset_size, byteorder="little"))

        msd_data.extend(self._section_list[index].get_text_section().get_data_hex())
        return msd_data

    # TODO Change the index by a value in a json file
    def get_section_draw_text(self) -> SectionOffsetAndText:
        return self._section_list[1]

    # TODO Change the index by a value in a json file
    def get_section_card_name(self) -> SectionSizeAndOffsetAndText:
        return self._section_list[6]

    # TODO Change the index by a value in a json file
    def get_section_scan_text(self) -> SectionOffsetAndText:
        return self._section_list[7]

    # TODO Change the index by a value in a json file
    def get_section_card_misc_text(self) -> SectionSizeAndOffsetAndText:
        return self._section_list[4]

    def produce_remaster_file(self, remaster_type: RemasterCardType):
        if remaster_type == RemasterCardType.CARD_NAME:
            return self._section_list[4].get_data_hex()
        else:
            return self._section_list[4].get_data_hex()

    def produce_misc_card_str_hext(self):
        self._section_list[4].update_data_hex()
        hext_str = "# File produced by ShumiTranslator or CC-Group tool, made by HobbitDur\n"
        hext_str += "# You can support HobbitDur on Patreon: https://www.patreon.com/HobbitMods\n\n"
        # First writing base data (not sure why necessary, but everyone does it)
        hext_str += "#Base writing (not sure why necessary)\n"
        hext_str += "600000:1000\n\n"
        # Then adding the offset of the data
        hext_str += "#Offset to dynamic data\n"
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET)

        card_misc_text_start = self._game_data.exe_data_json["card_data_offset"]["eng_card_misc_text_start"] + 2 + self.__get_lang_misc_text_card_offset()

        hext_str += "#Card misc text start at 0x{:X}, so we just move the pointer of 0x{:X}+0x{:X}=0x{:X}\n".format(card_misc_text_start,
                                                                                                                    self.GENERAL_OFFSET,
                                                                                                                    card_misc_text_start,
                                                                                                                    self.GENERAL_OFFSET + card_misc_text_start)
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET + card_misc_text_start)
        misc_section = self.get_section_card_misc_text()
        text_list = misc_section.get_text_section().get_text_list()

        index_text = 0
        for index_offset, offset in enumerate(misc_section.get_offset_section().get_all_offset()):
            hext_str += "#Offset values:\n"
            hext_str += "{:02X} = {}\n".format(index_offset * self.OFFSET_SIZE, offset.to_bytes(length=2, byteorder="little").hex(sep=" "))
            if offset != 0:
                hext_str += f"#Changing text to \"{text_list[index_text].get_str().replace('\n', '\\n')}\"\n"
                hext_str += "{:03X} = ".format(offset - 2)  # -2 as actually the reference for the offset is from the number of offset
                hext_str += "{}\n".format(text_list[index_text].get_data_hex().hex(sep=" "))
                index_text += 1
        return hext_str

    def produce_draw_str_hext(self):
        self._section_list[1].update_data_hex()
        hext_str = "# File produced by ShumiTranslator or CC-Group tool, made by HobbitDur\n"
        hext_str += "# You can support HobbitDur on Patreon: https://www.patreon.com/HobbitMods\n\n"
        # First writing base data (not sure why necessary, but everyone does it)
        hext_str += "#Base writing (not sure why necessary)\n"
        hext_str += "600000:1000\n\n"
        # Then adding the offset of the data
        hext_str += "#Offset to dynamic data\n"
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET)

        draw_misc_text_start = self._game_data.exe_data_json["draw_text_offset"]["eng_section_start"] + self.__get_lang_draw_text_offset()

        hext_str += "#Draw misc text start at 0x{:X}, so we just move the pointer of 0x{:X}+0x{:X}=0x{:X}\n".format(draw_misc_text_start,
                                                                                                                    self.GENERAL_OFFSET,
                                                                                                                    draw_misc_text_start,
                                                                                                                    self.GENERAL_OFFSET + draw_misc_text_start)
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET + draw_misc_text_start)
        misc_section = self.get_section_draw_text()
        text_list = misc_section.get_text_section().get_text_list()

        index_text = 0
        for index_offset, offset in enumerate(misc_section.get_offset_section().get_all_offset()):
            hext_str += "#Offset values:\n"
            hext_str += "{:02X} = {}\n".format(index_offset * self.OFFSET_SIZE, offset.to_bytes(length=2, byteorder="little").hex(sep=" "))
            if offset != 0:
                hext_str += f"#Changing text to \"{text_list[index_text].get_str().replace('\n', '\\n')}\"\n"
                hext_str += "{:03X} = ".format(offset) # -2 as actually the reference for the offset is from the number of offset
                hext_str += "{}\n".format(text_list[index_text].get_data_hex().hex(sep=" "))
                index_text += 1
        return hext_str

    def get_lang(self):
        return self._lang

    def update_data_hex(self):
        for section in self._section_list:
            section.update_data_hex()

    def __analyse_data(self):
        self.__analyse_lang()

        draw_text_offset_start = self._game_data.exe_data_json["draw_text_offset"]["eng_section_start"] + self.__get_lang_draw_text_offset()
        # 1st section - ignored data: start (0x00) -> start draw text (0x7921E1)
        self._section_list.append(Section(self._game_data, self._data_hex[0:draw_text_offset_start], id=0, own_offset=0, name="Ignored start data"))

        # 2nd section - Start draw text -> End of file
        draw_text_nb_offset = self._game_data.exe_data_json["draw_text_offset"]["nb_offset"]
        draw_text_offset_size = self._game_data.exe_data_json["draw_text_offset"]["offset_size"]
        draw_text_section = SectionOffsetAndText(self._game_data, self._data_hex[draw_text_offset_start:], id=1,
                                                 own_offset=draw_text_offset_start, name="Draw text", offset_size=draw_text_offset_size,
                                                 nb_offset=draw_text_nb_offset,
                                                 ignore_empty_offset=False, nb_byte_shift=0, text_offset_start_0=False)
        draw_text_section.update_data_hex()
        self._section_list.append(draw_text_section)

        # 3rd section - Start card menu (0x796508) -> end of card menu data
        nb_card = len(self._game_data.card_data_json["card_info"])
        card_data_size = self._game_data.exe_data_json["card_data_offset"]["card_data_size"]

        menu_offset = self._game_data.exe_data_json["card_data_offset"]["eng_menu"]
        menu_offset += self.__get_lang_card_offset()
        next_offset = menu_offset + nb_card * card_data_size
        self._section_list.append(Section(self._game_data, self._data_hex[menu_offset:next_offset], id=2, own_offset=0, name="Card menu data"))

        # 4th section - ignored data: end of card menu data -> card_misc_text_start (0x874b5a)
        offset = next_offset
        card_misc_text_offset = self._game_data.exe_data_json["card_data_offset"]["eng_card_misc_text_start"]
        card_misc_text_offset += self.__get_lang_misc_text_card_offset()
        self._section_list.append(Section(self._game_data, self._data_hex[offset:card_misc_text_offset], id=3, own_offset=0, name="Ignored data"))

        # 5th section: card_misc_text_start (0x874b5a) -> end of misc (computed after so taking till eng_game_data, 0x874D00)
        offset = card_misc_text_offset
        eng_game_data_offset = self._game_data.exe_data_json["card_data_offset"]["eng_game_data"]
        eng_game_data_offset += self.__get_lang_card_offset()
        card_misc_text_section = SectionSizeAndOffsetAndText(self._game_data, self._data_hex[offset:eng_game_data_offset], id=4,
                                                             own_offset=offset, name="Card misc text data", offset_size=2,
                                                             ignore_empty_offset=False)
        card_misc_text_section.update_data_hex()
        self._section_list.append(card_misc_text_section)
        # 6th section: eng_game_data (0x874D00) -> end of eng game data (computed after so taking till eng_name_section_start, 0x875074)
        offset = eng_game_data_offset
        eng_name_section_start = self._game_data.exe_data_json["card_data_offset"]["eng_name_section_start"]
        eng_name_section_start += self.__get_lang_card_offset()
        self._section_list.append(Section(self._game_data, self._data_hex[offset:eng_name_section_start], id=5, own_offset=0, name="Card game data"))

        # 7th section:  eng_name_section_start (0x874D00) -> end of name section (taking till the end)
        card_name_section = SectionSizeAndOffsetAndText(self._game_data, self._data_hex[eng_name_section_start:], id=6,
                                                        own_offset=eng_name_section_start, name="Card name", offset_size=2,
                                                        ignore_empty_offset=False)
        card_name_section.update_data_hex()
        self._section_list.append(card_name_section)

        # 8th section: Scan text
        scan_offset_start = self._game_data.exe_data_json["scan_data_offset"]["eng_section_start"] + self.__get_lang_scan_offset()
        scan_nb_offset = self._game_data.exe_data_json["scan_data_offset"]["nb_offset"]
        scan_offset_size = self._game_data.exe_data_json["scan_data_offset"]["offset_size"]
        scan_section = SectionOffsetAndText(self._game_data, self._data_hex[scan_offset_start:], id=7,
                                            own_offset=scan_offset_start, name="Scan text", offset_size=scan_offset_size, nb_offset=scan_nb_offset,
                                            ignore_empty_offset=False, nb_byte_shift=0, text_offset_start_0=True)
        scan_section.update_data_hex()
        self._section_list.append(scan_section)

        # self._section_list.append(Section(self._game_data, self._data_hex[name_offset + len(card_name_section):], id=8,
        #                                  own_offset=name_offset + len(card_name_section), name="Ignored end data"))

    def __analyse_lang(self):
        if self._data_hex[self._game_data.exe_data_json["lang"]["offset"]] == self._game_data.exe_data_json["lang"]["english_value"]:
            self._lang = LangType.ENGLISH
        elif self._data_hex[self._game_data.exe_data_json["lang"]["offset"]] == self._game_data.exe_data_json["lang"]["french_value"]:
            self._lang = LangType.FRENCH
        elif self._data_hex[self._game_data.exe_data_json["lang"]["offset"]] == self._game_data.exe_data_json["lang"]["german_value"]:
            self._lang = LangType.GERMAN
        elif self._data_hex[self._game_data.exe_data_json["lang"]["offset"]] == self._game_data.exe_data_json["lang"]["spanish_value"]:
            self._lang = LangType.SPANISH
        elif self._data_hex[self._game_data.exe_data_json["lang"]["offset"]] == self._game_data.exe_data_json["lang"]["italian_value"]:
            self._lang = LangType.ITALIAN
        else:
            print(f"Unexpected language, value: {self._data_hex[self._game_data.exe_data_json["lang"]["offset"]]}")
            self._lang = LangType.ENGLISH

    def __get_lang_card_offset(self):
        if self._lang == LangType.ENGLISH:
            return 0
        elif self._lang == LangType.FRENCH:
            return self._game_data.exe_data_json["card_data_offset"]["fr_offset"]
        elif self._lang == LangType.ITALIAN:
            return self._game_data.exe_data_json["card_data_offset"]["it_offset"]
        elif self._lang == LangType.GERMAN:
            return self._game_data.exe_data_json["card_data_offset"]["de_offset"]
        elif self._lang == LangType.SPANISH:
            return self._game_data.exe_data_json["card_data_offset"]["es_offset"]
        else:
            print("Unknown Language")
            return 0

    def __get_lang_misc_text_card_offset(self):
        if self._lang == LangType.ENGLISH:
            return 0
        elif self._lang == LangType.FRENCH:
            return self._game_data.exe_data_json["card_data_offset"]["card_misc_text_fr_offset"]
        elif self._lang == LangType.ITALIAN:
            return self._game_data.exe_data_json["card_data_offset"]["card_misc_text_it_offset"]
        elif self._lang == LangType.GERMAN:
            return self._game_data.exe_data_json["card_data_offset"]["card_misc_text_de_offset"]
        elif self._lang == LangType.SPANISH:
            return self._game_data.exe_data_json["card_data_offset"]["card_misc_text_es_offset"]
        else:
            print("Unknown Language")
            return 0

    def __get_lang_scan_offset(self):
        if self._lang == LangType.ENGLISH:
            return 0
        elif self._lang == LangType.FRENCH:
            return self._game_data.exe_data_json["scan_data_offset"]["fr_offset"]
        elif self._lang == LangType.ITALIAN:
            return self._game_data.exe_data_json["scan_data_offset"]["it_offset"]
        elif self._lang == LangType.GERMAN:
            return self._game_data.exe_data_json["scan_data_offset"]["de_offset"]
        elif self._lang == LangType.SPANISH:
            return self._game_data.exe_data_json["scan_data_offset"]["es_offset"]
        else:
            print("Unknown Language")
            return 0

    def __get_lang_draw_text_offset(self):
        if self._lang == LangType.ENGLISH:
            return 0
        elif self._lang == LangType.FRENCH:
            return self._game_data.exe_data_json["draw_text_offset"]["fr_offset"]
        elif self._lang == LangType.ITALIAN:
            return self._game_data.exe_data_json["draw_text_offset"]["it_offset"]
        elif self._lang == LangType.GERMAN:
            return self._game_data.exe_data_json["draw_text_offset"]["de_offset"]
        elif self._lang == LangType.SPANISH:
            return self._game_data.exe_data_json["draw_text_offset"]["es_offset"]
        else:
            print("Unknown Language")
            return 0
