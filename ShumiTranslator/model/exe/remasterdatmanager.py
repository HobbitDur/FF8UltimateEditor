import os
import pathlib

from FF8GameData.ExeSection.exefile import SectionExeFile
import csv

from FF8GameData.GenericSection.offsetandtext import SectionOffsetAndText
from FF8GameData.GenericSection.sizeandoffsetandtext import SectionSizeAndOffsetAndText
from FF8GameData.gamedata import GameData, LangType, RemasterCardType



class RemasterDatManager:
    def __init__(self, game_data: GameData):
        self.game_data = game_data

        self._section = None
        self._lang = LangType.ENGLISH

    def __str__(self):
        return str(self._section)

    def __repr__(self):
        return self.__str__()

    def get_section(self) -> SectionSizeAndOffsetAndText:
        return self._section

    def save_file(self, file_dat):
        self._section.update_data_hex()
        with open(file_dat, "wb") as f:
            f.write(self._section.get_data_hex())

    def load_file(self, file_to_load, remaster_type: RemasterCardType):
        file_name = pathlib.Path(file_to_load).name
        file_data = bytearray()
        with open(file_to_load, "rb") as file:
            file_data.extend(file.read())
        if remaster_type == RemasterCardType.CARD_NAME:
            self._section = SectionSizeAndOffsetAndText(self.game_data, file_data, id=0, own_offset=0, name=file_name, ignore_empty_offset=False)
        elif remaster_type == RemasterCardType.CARD_NAME2:
            self._section = SectionOffsetAndText(self.game_data, file_data, id=0, own_offset=0, name=file_name, ignore_empty_offset=False)

        if "en" in file_name:
            self._lang = LangType.ENGLISH
        elif "it" in file_name:
            self._lang = LangType.ITALIAN
        elif "es" in file_name:
            self._lang = LangType.SPANISH
        elif "fr" in file_name:
            self._lang = LangType.FRENCH
        elif "de" in file_name:
            self._lang = LangType.GERMAN
