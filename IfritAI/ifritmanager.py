from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.gamedata import GameData


class IfritManager:
    def __init__(self, game_data_folder="FF8GameData"):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.ennemy = MonsterAnalyser(self.game_data)
        self.ai_data = []

    def init_from_file(self, file_path):
        self.ennemy.load_file_data(file_path, self.game_data)
        self.ennemy.analyse_loaded_data(self.game_data)
        self.ai_data = self.ennemy.battle_script_data['ai_data']

    def save_file(self, file_path):
        self.ennemy.write_data_to_file(self.game_data, file_path)

