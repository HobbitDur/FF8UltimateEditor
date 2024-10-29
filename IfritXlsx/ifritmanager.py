import argparse
import glob
import os
import re
import shutil
import sys

from PyQt5.QtWidgets import QApplication

import fshandler
import xlsxmanager
from ennemy import Ennemy
from gamedata import GameData
from launchergui import WindowLauncher
from xlsxmanager import XlsxToDat, DatToXlsx


class IfritManager():
    LIST_LANG = ('eng', 'fre', 'ita')
    LIST_OPTION = ('fs_to_xlsx', 'xlsx_to_fs', 'both')
    FOLDER_INPUT = "OriginalFiles"
    FOLDER_OUTPUT = "OutputFiles"
    FILE_INPUT_BATTLE = os.path.join(FOLDER_INPUT, "decompressed_battle")  # Path for battle.fs decompressed
    FILE_OUTPUT_BATTLE = os.path.join(FOLDER_OUTPUT, "battle")
    FILE_XLSX = os.path.join(FOLDER_OUTPUT, "ifrit.xlsx")

    def __init__(self, gui=True):
        self.gui = gui  # True for gui, false for cmd
        if self.gui:
            self.__gui_launch()
        else:
            self.args = self.__cmd_setup()
            self.exec()

    def __cmd_setup(self):
        parser = argparse.ArgumentParser(prog="Ifrit Enhanced Command line",
                                         description="This program allow you to quickly translate your battle.fs in an easy to edit xlsx file, and transform it "
                                                     "back to battle.fs file")
        parser.add_argument("xlsx",
                            help="Define if you want to transform from battle.fs to xlsx or if you want to transform your modified xlsx back to a battle.fs",
                            choices=self.LIST_OPTION, default='fs_to_xlsx', nargs='?')
        parser.add_argument("-d", "--delete",
                            help="Delete temporary file created (.dat extracted for example). Only applied for xlsx_to_fs command, as the temporary files are needed to build back to battle.fs",
                            action='store_true')
        parser.add_argument("-c", "--copy", help="Copy  to FF8 repository into direct folder, expecting path to the FF8 folder", type=str)
        parser.add_argument("-cf", "--copyfile", help="Work only on file given", type=int)
        parser.add_argument("-l", "--limit", help="Limit to one monster.", type=int, default=-1)
        parser.add_argument("-o", "--open", help="Open xlsx file for faster management", action='store_true')
        parser.add_argument("--nopack", help="Doesn't create a pack, only let intermediate file. Only applied to fs_to_xlsx", action='store_true')
        parser.add_argument("--lang", help="Choose the language you use", choices=self.LIST_LANG, default='eng', nargs='?')
        parser.add_argument("--analyse-ia", help="Analyse the IA", action='store_true')
        return parser.parse_args()

    def __gui_launch(self):
        app = QApplication.instance()
        if not app:  # sinon on crée une instance de QApplication
            app = QApplication(sys.argv)

        window_installer = WindowLauncher(self, self.LIST_LANG, self.LIST_OPTION)

        sys.exit(app.exec_())

    def exec(self, lang=LIST_LANG[0], launch_option=LIST_OPTION[0], limit_option=-1, no_pack_option=False, open_xlsx_option=False, delete_option=False,
             ff8_path="", analyse_ia=True):
        if not self.gui:
            args = self.__cmd_setup()
            local_lang = args.lang
            local_launch_option = args.xlsx
            local_limit_option = args.limit
            local_no_pack = args.nopack
            local_copy = args.copy
            local_open = args.open
            local_delete = args.delete
            local_analyse_ia = args.analyse_ia
        else:
            local_lang = lang
            local_launch_option = launch_option
            local_limit_option = limit_option
            local_no_pack = no_pack_option
            local_copy = ff8_path
            local_open = open_xlsx_option
            local_delete = delete_option
            local_analyse_ia = analyse_ia




        FILE_BATTLE_SPECIAL_PATH_FORMAT = os.path.join(local_lang, "battle")
        FILE_MONSTER_INPUT_PATH = os.path.join(self.FILE_INPUT_BATTLE,
                                               FILE_BATTLE_SPECIAL_PATH_FORMAT)  # Final path for .dat file (dependent of deling-CLI.exe)
        FILE_MONSTER_OUTPUT_PATH = os.path.join(self.FILE_OUTPUT_BATTLE, FILE_BATTLE_SPECIAL_PATH_FORMAT)
        FILE_MONSTER_INPUT_REGEX = os.path.join(FILE_MONSTER_INPUT_PATH, "c0m*.dat")
        FILE_MONSTER_OUTPUT_REGEX = os.path.join(FILE_MONSTER_OUTPUT_PATH, "c0m*.dat")

        if local_launch_option == "fs_to_xlsx" or local_launch_option == "both":
            dat_to_xlsx_mananager = DatToXlsx(self.FILE_XLSX)
            if not local_no_pack:
                print("-------Unpacking fs file-------")
                fshandler.unpack(self.FOLDER_INPUT, self.FILE_INPUT_BATTLE)
            # Check if .dat exist
            file_monster = glob.glob(FILE_MONSTER_INPUT_REGEX)

            if not file_monster:
                raise FileNotFoundError("No .dat files found in {}".format(FILE_MONSTER_INPUT_PATH))
            if local_limit_option >= 0:
                file_monster = [file_monster[local_limit_option]]  # Just to not work on all files everytime
            print("-------Transforming dat to XLSX-------")
            os.makedirs(self.FOLDER_OUTPUT, exist_ok=True)
            self.dat_to_xlsx(file_monster, dat_to_xlsx_mananager, local_analyse_ia)

        if local_launch_option == "xlsx_to_fs" or local_launch_option == "both":
            xlsx_to_dat_mananager = XlsxToDat(self.FILE_XLSX)
            print("-------Copying files from input to output-------")
            # Copying files from Input to Output before modifying
            os.makedirs(self.FILE_OUTPUT_BATTLE, exist_ok=True)
            os.makedirs(FILE_MONSTER_OUTPUT_PATH, exist_ok=True)
            if os.path.exists(self.FILE_INPUT_BATTLE): # If input file exist, copy from there. If not, means we use the output files directly.
                shutil.copytree(FILE_MONSTER_INPUT_PATH, FILE_MONSTER_OUTPUT_PATH, dirs_exist_ok=True)

            print("-------Transforming XLSX to dat-------")
            self.xlsx_to_dat(FILE_MONSTER_OUTPUT_PATH, xlsx_to_dat_mananager, local_limit_option, local_analyse_ia)

            if not local_no_pack:
                print("-------Packing to fs file-------")
                fshandler.pack(FILE_MONSTER_INPUT_PATH, self.FILE_OUTPUT_BATTLE, local_lang)
            if local_delete:
                # Delete files
                print("-------Deleting files-------")
                ## Delete opened archive battle.fs (in Original file)
                shutil.rmtree(self.FILE_INPUT_BATTLE)
                ## Delete dat files in OutputFiles (in Output file)
                shutil.rmtree(os.path.join(self.FILE_OUTPUT_BATTLE, local_lang))

        if local_copy and local_copy != "":

            os.makedirs(os.path.join(local_copy, 'direct', 'battle'), exist_ok=True)
            for file in glob.glob(os.path.join(FILE_MONSTER_OUTPUT_PATH, "c0m*.dat")):
                if 0 < local_limit_option != int(re.search(r'\d\d+', file).group()):
                    continue
                shutil.copy(file, os.path.join(local_copy, 'direct', 'battle'))

        if local_open:
            os.startfile(self.FILE_XLSX)

        print("Work over")

    def create_checksum_file_all_monster(self, ennemy_list, file_name):
        with open(os.path.join(self.FOLDER_OUTPUT, file_name), "w") as f:
            for key, ennemy in ennemy_list.items():
                f.write("File name: {} | Checksum: {}\n".format(ennemy.origin_file_name, ennemy.origin_file_checksum))

    # def create_checksum_file(self, ennemy, file_name):
    #    with open(os.path.join(self.FOLDER_OUTPUT, file_name), "w") as f:
    #        f.write("File name: {} | Checksum: {}\n".format(ennemy.origin_file_name, ennemy.origin_file_checksum))

    def dat_to_xlsx(self, file_list, dat_xlsx_manager, analyse_ia):
        monster = {}

        print("Getting game data")
        game_data = GameData()
        game_data.load_all()

        print("Reading ennemy files")
        for monster_file in file_list:
            file_name = os.path.basename(monster_file)
            file_index = int(re.search(r'\d{3}', file_name).group())
            if file_index == 0 or file_index == 127 or file_index > 143:  # Avoid working on garbage file
                continue
            print("Reading file {}".format(file_name))
            monster = Ennemy(game_data)
            monster.load_file_data(monster_file, game_data)
            monster.analyse_loaded_data(game_data, analyse_ia)

            # print("Creating checksum file")
            # self.create_checksum_file(monster, "checksum_origin_file.txt")
            print("Writing to xlsx file")
            dat_xlsx_manager.export_to_xlsx(monster, file_name, game_data, analyse_ia)

        dat_xlsx_manager.create_ref_data(game_data)

    def xlsx_to_dat(self, output_path, xlsx_dat_manager: XlsxToDat, local_limit, analyse_ia=True):
        print("Getting game data")
        game_data = GameData()
        game_data.load_all()
        for sheet in xlsx_dat_manager.workbook:
            if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE:
                monster_index = int(re.search(r'\d+', sheet.title).group())
                if local_limit > 0 and local_limit != monster_index:  # Only doing the monster asked
                    continue
                print("Importing data from xlsx")
                ennemy = xlsx_dat_manager.import_from_xlsx(sheet, game_data, output_path, local_limit, analyse_ia)
                if ennemy:
                    print("Writing data to dat files")
                    ennemy.write_data_to_file(game_data, output_path, analyse_ia)

                # print("Creating checksum file")
                # self.create_checksum_file(ennemy, "checksum_output_file.txt")
