import os
import pathlib
import re
import subprocess
from dataclasses import dataclass
from typing import TypedDict

from FF8GameData.gamedata import GameData


@dataclass
class TextureType:
    palette_id: int = 0
    texture: str = ""

@dataclass
class MetaData:
    depth: int
    imageX: int
    imageY: int
    paletteX: int
    paletteY: int

class IfritTextureManager:
    def __init__(self, game_data_folder="FF8GameData", vincent_tim_path=None):
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self._meta = ""
        self._palette = []
        self._texture = TextureType()

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
            all_pngs = temp_path.glob("*.png")
            texture_png_count = len([f for f in all_pngs if "palette" not in f.name.lower()])

            # 3. Read each file and store in an array (list)
            # This stores the literal text of every .meta file found
            meta_contents = []
            for meta_file in meta_files:
                content = meta_file.read_text(encoding="utf-8")
                meta_contents.append(content)

            # Debug: Print how many files were read
            print(f"Stored {len(meta_contents)} meta files in the array.")

            # Example: Access the first file's data
            if meta_contents:
                print(f"First meta file starts with: {meta_contents[0][:50]}...")

            print(meta_contents)
            return meta_contents



        except subprocess.CalledProcessError as e:
            print(f"Error: tim.exe failed with exit code {e.returncode}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
