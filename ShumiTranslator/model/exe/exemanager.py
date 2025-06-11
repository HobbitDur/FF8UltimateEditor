import os

from FF8GameData.ExeSection.exefile import SectionExeFile
import csv

from FF8GameData.gamedata import GameData, MsdType


class ExeManager:
    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.exe_section = None

    def __str__(self):
        return str(self.exe_section)

    def __repr__(self):
        return self.__str__()

    def get_exe_section(self) -> SectionExeFile:
        return self.exe_section

    def save_file(self, folder):
        file_scan = os.path.join(folder, "battle_scans.msd")
        card_name = os.path.join(folder, "card_names.msd")
        card_texts = os.path.join(folder, "card_texts.msd")
        draw_point = os.path.join(folder, "draw_point.msd")
        with open(file_scan, "wb") as f:
            f.write(self.exe_section.produce_msd(MsdType.SCAN_TEXT))
        with open(card_name, "wb") as f:
            f.write(self.exe_section.produce_msd(MsdType.CARD_NAME))
        with open(card_texts, "wb") as f:
            f.write(self.exe_section.produce_msd(MsdType.CARD_TEXT))
        with open(draw_point, "wb") as f:
            f.write(self.exe_section.produce_msd(MsdType.DRAW_POINT))

    def load_file(self, file_exe):
        exe_hex = bytearray()
        with open(file_exe, "rb") as file:
            exe_hex.extend(file.read())

        self.exe_section = SectionExeFile(self.game_data, exe_hex)
