import os
import pathlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from PIL.Image import Palette
from PyQt6.QtWidgets import QWidget

from FF8GameData.gamedata import GameData




class MetaData:
    def __init__(self, meta_file_path: pathlib.Path = None):
        self.meta_file_path = meta_file_path
        self.meta_data_str = ""
        self.depth=8
        self.imageX=0
        self.imageY=0
        self.paletteX=0
        self.paletteY=0
        if meta_file_path:
            self.extract_data_from_str(meta_file_path.read_text(encoding="utf-8"))
        print(f"meta_file_path: {meta_file_path}")


    def __str__(self):
        return f"MetaData(Depth:{self.depth}, imageX:{self.imageX}, imageY:{self.imageY}, paletteX:{self.paletteX}, paletteY:{self.paletteY})"

    def __repr__(self):
        return self.__str__()

    def extract_data_from_str(self, str_data: str):
        self.meta_data_str = str_data
        values = str_data.split("\n")
        self.depth = int(values[0].split("=")[1])
        self.imageX = int(values[1].split("=")[1])
        self.imageY = int(values[2].split("=")[1])
        self.paletteX = int(values[3].split("=")[1])
        self.paletteY = int(values[4].split("=")[1])


class TextureData:
    def __init__(self, meta:MetaData, texture_path: pathlib.Path, palette_path:pathlib.Path):
        self.meta = meta
        self.texture_path = texture_path
        self.palette_path = palette_path




class IfritTextureManager:
    def __init__(self, game_data_folder="FF8GameData", vincent_tim_path=None):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self.texture_data = []

        # --- PATH RESOLUTION LOGIC ---
        # 1. Get the absolute path of the directory where THIS script lives
        current_script_dir = pathlib.Path(__file__).parent.resolve()

        # 2. If no path is provided, assume ExternalsTools is one level up from this script
        # Adjust .parent if your folder structure is different
        if vincent_tim_path is None:
            self.vincent_tim_path = current_script_dir.parent / "ExternalTools" / "VincentTim" / "tim.exe"
        else:
            self.vincent_tim_path = pathlib.Path(vincent_tim_path).resolve()

    def analyze(self, file_path_to_analyze):
        # Ensure the executable actually exists before trying to run it
        if not self.vincent_tim_path.exists():
            raise FileNotFoundError(f"Critical Error: 'tim.exe' not found at {self.vincent_tim_path}")
        temp_path = pathlib.Path(__file__).parent.resolve() / "temp_vincent_tim"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([
                str(self.vincent_tim_path),
                "--export-all",
                "--analysis",
                str(file_path_to_analyze),
                str(temp_path)
            ], check=True)

            # --- COUNTING LOGIC ---
            # 1. Count all .meta files
            meta_files = list(temp_path.glob("*.meta"))
            meta_count = len(meta_files)

            # 2. Count files ending exactly in palette.png
            palette_files = list(temp_path.glob("*palette.png"))
            palette_count = len(palette_files)

            # 3. Count .png files that DO NOT contain "palette" in the name
            # We filter the list of all PNGs manually for precision
            # This creates a list of Path objects that don't have "palette" in the name
            texture_files = [f for f in temp_path.glob("*.png") if "palette" not in f.name.lower()]
            # Now you can get the count easily
            texture_png_count = len(texture_files)

            # 3. Read each file and store in an array (list)
            # This stores the literal text of every .meta file found

            if meta_count == palette_count == texture_png_count:
                for i in range(meta_count):
                    self.texture_data.append(TextureData(meta=MetaData(meta_files[i]), texture_path=texture_files[i], palette_path=palette_files[i]))





        except subprocess.CalledProcessError as e:
            print(f"Error: tim.exe failed with exit code {e.returncode}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
