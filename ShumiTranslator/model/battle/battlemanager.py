import pathlib
import csv

from FF8GameData.dat.monsteranalyser import GarbageFileError, MonsterAnalyser
from FF8GameData.gamedata import GameData
from FF8GameData.GenericSection.listff8text import ListFF8Text


class BattleManager:
    def __init__(self, game_data: GameData):

        self.ennemy_list = []
        self.section_text_list = []
        self.file_list = []
        self.game_data = game_data

    def __str__(self):
        return str(self.ennemy_list)

    def __repr__(self):
        return self.__str__()

    def reset(self):
        self.ennemy_list = []
        self.section_text_list = []
        self.file_list = []

    def add_file(self, com_file):
        self.file_list.append(com_file)
        ennemy = MonsterAnalyser(self.game_data)
        ennemy.load_file_data(com_file, self.game_data)

        try:
            ennemy.analyse_loaded_data(self.game_data)
            name = ennemy.info_stat_data['monster_name'].get_str()
            self.ennemy_list.append(ennemy)
            self.section_text_list.append(
                ListFF8Text(game_data=self.game_data, data_hex=bytearray(), id=len(self.section_text_list), own_offset=0, name=name))
            self.section_text_list[-1].add_text(self.game_data.translate_str_to_hex(ennemy.info_stat_data['monster_name'].get_str()))
            for text in ennemy.battle_script_data['battle_text']:
                self.section_text_list[-1].add_text(self.game_data.translate_str_to_hex(text.get_str()))
        except GarbageFileError as e:
            pass
            #print(f"GarbageFileError: {e}")



    def get_section_list(self):
        return self.section_text_list

    def save_all_file(self):
        for i in range(len(self.section_text_list)):
            if self.section_text_list[i]:
                self.section_text_list[i].update_data_hex()
                self.ennemy_list[i].info_stat_data['monster_name'] = self.section_text_list[i].get_text_list()[0]
                for j, text in enumerate(self.section_text_list[i].get_text_list()[1:]):
                    self.ennemy_list[i].battle_script_data['battle_text'][j] = text
            self.ennemy_list[i].write_data_to_file(self.game_data, self.file_list[i])

