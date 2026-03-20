import pathlib
import subprocess

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
            ], check=True)

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

            # 3. Read each file and store in an array (list)
            # This stores the literal text of every .meta file found

            if meta_count == palette_count == texture_png_count:
                for i in range(meta_count):
                    self.texture_data.append(TextureData(meta=MetaData(meta_files[i]), texture_path=texture_files[i], palette_path=palette_files[i]))






        except subprocess.CalledProcessError as e:
            print(f"Error: tim.exe failed with exit code {e.returncode}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

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
                ], check=True)

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


