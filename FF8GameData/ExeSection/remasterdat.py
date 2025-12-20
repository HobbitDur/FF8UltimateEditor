from FF8GameData.GenericSection.offsetandtext import SectionOffsetAndText
from FF8GameData.GenericSection.section import Section
from FF8GameData.GenericSection.sizeandoffsetandtext import SectionSizeAndOffsetAndText
from FF8GameData.gamedata import GameData, LangType, MsdType, RemasterCardType


class SectionRemasterDat(Section):
    OFFSET_SIZE = 2

    def __init__(self, game_data: GameData, data_hex, remaster_type:RemasterCardType, file_name):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=0, own_offset=0, name="remaster.dat")

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
        if remaster_type == RemasterCardType.CARD_NAME:
            self._section = SectionSizeAndOffsetAndText(game_data, data_hex, id=0, own_offset=0, name=self.name, ignore_empty_offset=False)

    def __str__(self):
        return str("To be define")

    def __repr__(self):
        return self.__str__()

    def update_data_hex(self):
        self._section.update_data_hex()

    def get_section(self):
        return self._section