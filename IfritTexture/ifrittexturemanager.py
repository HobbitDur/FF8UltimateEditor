import pathlib
import re
import shutil
import subprocess

from PIL import Image

from FF8GameData.dat.monsteranalyser import MonsterAnalyser
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
        self.temp_path = pathlib.Path(__file__).parent.resolve() / "temp_vincent_tim"

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
        self.temp_path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([
                str(self.vincent_tim_path),
                "--export-all",
                "--analysis",
                str(file_path_to_analyze),
                str( self.temp_path)
            ], check=True, capture_output=True)

            # --- COUNTING LOGIC ---
            # 1. Count all .meta files
            meta_files = list( self.temp_path.glob("*.meta"))
            meta_count = len(meta_files)

            # 2. Count files ending exactly in palette.png
            palette_files = list( self.temp_path.glob("*palette.png"))
            palette_count = len(palette_files)

            # 3. Count .png files that DO NOT contain "palette" in the name
            # We filter the list of all PNGs manually for precision
            # This creates a list of Path objects that don't have "palette" in the name
            texture_files = [f for f in  self.temp_path.glob("*.png") if "palette" not in f.name.lower()]
            # Now you can get the count easily
            texture_png_count = len(texture_files)

            palette_height = 0
            for palette_path in palette_files:
                # 1. Open and process the file
                with Image.open(palette_path) as img:
                    palette_height = img.height
                    if palette_height > 1:
                        self._cut_palette_file(img)
                        # Flag this file for deletion
                        should_delete = True
                    else:
                        should_delete = False

                # 2. The 'with' block is over; the file is now closed.
                # Now it is safe to delete it.
                if should_delete:
                    palette_path.unlink()

            for texture_path in texture_files:
                # This matches a digit (\d+) followed by '.png' at the end ($)
                # The (.+) matches everything before the index
                match = re.search(r'(\d+)\.png$', texture_path.name)

                if not match:
                    print(f"Skipping {texture_path.name}: No index found.")
                    continue

                target_index = int(match.group(1))

                with Image.open(texture_path) as img:
                    if img.width != img.height:
                        # Slicing logic
                        self._cut_texture_file(img, target_index, texture_path)

            for template_meta in meta_files:
                # Get the parts: ['mag290_h', '00', '0', 'meta']
                parts = template_meta.name.split('.')

                # We want to create copies for the remaining textures
                # range starts at 1 because index 0 already exists
                for i in range(1, texture_png_count):
                    # Create the new name: swap the index part (the one at index -2)
                    new_parts = parts.copy()
                    new_parts[-2] = str(i)
                    new_name = ".".join(new_parts)

                    target_path = template_meta.parent / new_name

                    if not target_path.exists():
                        shutil.copy2(template_meta, target_path)


            # 3. Read each file and store in an array (list)
            # This stores the literal text of every .meta file found
            # --- COUNTING LOGIC ---
            # 1. Count all .meta files
            meta_files = list( self.temp_path.glob("*.meta"))
            meta_count = len(meta_files)

            # 2. Count files ending exactly in palette.png
            palette_files = list( self.temp_path.glob("*palette.png"))
            palette_count = len(palette_files)

            # 3. Count .png files that DO NOT contain "palette" in the name
            # We filter the list of all PNGs manually for precision
            # This creates a list of Path objects that don't have "palette" in the name
            texture_files = [f for f in  self.temp_path.glob("*.png") if "palette" not in f.name.lower()]
            # Now you can get the count easily
            texture_png_count = len(texture_files)

            if meta_count == palette_count == texture_png_count:
                for i in range(meta_count):
                    self.texture_data.append(TextureData(meta=MetaData(meta_files[i]), texture_path=texture_files[i], palette_path=palette_files[i]))
            else:
                print("Still not the same count")
        except subprocess.CalledProcessError as e:
            print(f"Error: tim.exe failed with exit code {e.returncode}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    def _cut_texture_file(self, img: Image.Image, index: int, original_path: pathlib.Path) -> None:
        width, height = img.size

        if height > width:
            # Vertical stacking: Index 0 is top, Index 1 is below it
            square_size = width
            left = 0
            top = index * square_size
            right = width
            bottom = top + square_size
        else:
            # Horizontal stacking: Index 0 is left, Index 1 is right
            square_size = height
            left = index * square_size
            top = 0
            right = left + square_size
            bottom = height

        # Perform the crop
        # Note: If the index is out of bounds for the image size,
        # this might create an empty or error-prone crop.
        # Pillow handles it, but ensure your indices match your image dimensions!
        tile = img.crop((left, top, right, bottom))

        # Save the new square image over the original filename
        # (or a new one, but here we replace the original tall/wide one)
        tile.save(original_path)

    def _cut_palette_file(self, img: Image.Image) -> None:
        """
        Slices a tall palette image into multiple 1px height images.
        """
        width, height = img.size

        for y in range(height):
            # Define the 1px tall box
            box = (0, y, width, y + 1)
            row = img.crop(box)

            # Save each row
            row_path =  self.temp_path / f"{ self.temp_path.stem}_row_{y}_palette.png"
            row.save(row_path)

    def _create_tim_from_texture_data(self, folder_path_to_analyze:str):
        if not self.vincent_tim_path.exists():
            raise FileNotFoundError(f"Critical Error: 'tim.exe' not found at {self.vincent_tim_path}")
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # --- COUNTING LOGIC ---
        # 1. Count all .meta files
        meta_files = list(self.temp_path.glob("*.meta"))
        meta_count = len(meta_files)

        # 2. Count files ending exactly in palette.png
        palette_files = list(self.temp_path.glob("*palette.png"))
        palette_count = len(palette_files)

        # 3. Count .png files that DO NOT contain "palette" in the name
        # We filter the list of all PNGs manually for precision
        # This creates a list of Path objects that don't have "palette" in the name
        texture_files = [f for f in self.temp_path.glob("*.png") if "palette" not in f.name.lower()]
        # Now you can get the count easily
        texture_png_count = len(texture_files)

        if meta_count == palette_count == texture_png_count:
            for i in range(meta_count):
                subprocess.run([
                    str(self.vincent_tim_path),
                    "--input-format", "png",
                    "--output-format", "tim",
                    "--palette", "0",
                    "--input-path-palette",palette_files[i],
                    "--input-path-meta", meta_files[i],
                    texture_files[i],
                    str(self.temp_path)
                ], check=True, capture_output=True)

    def _inject_in_com(self, com_file_str:str):
        game_data = GameData()
        game_data.load_all()
        monster_analyser = MonsterAnalyser(game_data)
        monster_analyser.load_file_data(com_file_str, game_data)
        monster_analyser.analyse_loaded_data(game_data)
        tim_list = list(self.temp_path.glob("*.tim"))
        monster_analyser.texture_data["nb_texture"] = len(tim_list)
        monster_analyser.texture_data["tim_offset"] = []
        monster_analyser.texture_data["texture_data"] = []
        base_offset = 4+ len(tim_list*4)+ 4
        monster_analyser.texture_data["tim_offset"].append(base_offset)
        for i in range(len(tim_list)-1):
            base_offset = base_offset  + tim_list[i].stat().st_size
            monster_analyser.texture_data["tim_offset"].append(base_offset)
        monster_analyser.texture_data["eof_texture"] =  monster_analyser.texture_data["tim_offset"][-1] + tim_list[-1].stat().st_size
        for tim in tim_list:
            monster_analyser.texture_data["texture_data"].append(tim.read_bytes())
        monster_analyser.write_data_to_file(game_data, com_file_str)

    def inject(self, folder_path_to_analyze:str, com_file_str:str):
        self._create_tim_from_texture_data(folder_path_to_analyze)

        self._inject_in_com(com_file_str)


