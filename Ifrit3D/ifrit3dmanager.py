import pathlib

from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData


class Ifrit3DManager:
    def __init__(self, monster_file:str, game_data_folder="FF8GameData"):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.monster_data = MonsterAnalyser(self.game_data)
        self.monster_data.load_file_data(monster_file, self.game_data)
        self.monster_data.analyse_loaded_data(self.game_data)