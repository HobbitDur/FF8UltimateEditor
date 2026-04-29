import argparse
import glob
import os
import pathlib

import subprocess

from ennemy import Ennemy
from gamedata import GameData
PATH_SEARCHING = os.path.join("OutputFiles", "cherching_scan")
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="Dat to txt",
                                     description="This program allow you to quickly read a dat file searching for text")
    parser.add_argument("path", help="Path to dat file (with name)", type=str)
    args = parser.parse_args()

    os.makedirs(PATH_SEARCHING, exist_ok=True)
    list_file = glob.glob('OriginalFiles\\*.fs')
    print(list_file)
    for file in list_file:
        print(file)
        subprocess.run(["Resources/ArchiveManagementCLI/deling-cli.exe", "export", file, PATH_SEARCHING])

    #list_file = glob.glob('OutputFiles\\cherching_scan\\**\\*.fs', recursive=True)
    #print(list_file)
    #for file in list_file:
    #    print(file)
    #    subprocess.run(["Resources/ArchiveManagementCLI/deling-cli.exe", "export", file, PATH_SEARCHING])

    list_file = glob.glob('OutputFiles/cherching_scan/**/*.lzs', recursive=True)

    for file in list_file:
        parent = str(pathlib.Path(file).parent)
        subprocess.run(["lzs.exe", "-d", file, parent])

    list_file = glob.glob('OutputFiles/cherching_scan/**', recursive=True)
    game_data = GameData()  # For translate table
    for file in list_file:
        original_file_name = pathlib.Path(file).name
        print(file)
        if file.split('.')[-1] in ["lzs", 'fs', 'fl', 'fi']:
            print("File ignored")
            continue

        if os.path.isfile(file):
            hex_index = 0
            file_raw_data = []
            futur_file_name = original_file_name + '.txt'
            index = 0
            with open(file, "rb") as f:
                while el := f.read(1):
                    file_raw_data.append(int.from_bytes(el))

            translated_data = game_data.translate_hex_to_str(file_raw_data)
            os.makedirs('temp', exist_ok=True)
            with open(os.path.join(os.getcwd(), 'temp', futur_file_name), "w", encoding='utf-8') as f:
                for by in translated_data:
                    f.write(by)
