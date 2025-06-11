import os
import shutil
from FF8GameData.fs.delingclimanager import DelingCliManager
from FF8GameData.gamedata import GameData


class FieldFsManager:
    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self._file_path = ""
        self._deling_manager = DelingCliManager(os.path.join("FF8GameData", "fs", "DelingCli"))

    def save_file(self, dest_folder_path):
        self._deling_manager.unpack(self._file_path, os.path.join(dest_folder_path, "temp"))
        self.delete_non_msd_files(os.path.join(dest_folder_path, "temp"))
        self.move_contents_and_delete_parents(os.path.join(dest_folder_path, "temp"), os.path.join(dest_folder_path, "field") )

    def load_file(self, file_to_load):
        self._file_path = file_to_load

    def save_csv(self, csv_path):
        if csv_path:
            self._deling_manager.export_csv(self._file_path, csv_path)

    def load_csv(self, csv_to_load):
        if csv_to_load:
            self._deling_manager.import_csv(self._file_path, csv_to_load)

    @staticmethod
    def delete_non_msd_files(folder_path):
        """
        Recursively deletes all files in a folder and its subfolders
        if their extension is not .msd.

        :param folder_path: Path to the target folder.
        """
        # Verify the folder exists
        if not os.path.isdir(folder_path):
            print(f"The folder '{folder_path}' does not exist.")
            return

        # Walk through the folder and its subdirectories
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)

                # Check if the file does not end with .msd
                if not file.lower().endswith('.msd'):
                    if not file.lower().endswith('.jsm'):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

    @staticmethod
    def move_contents_and_delete_parents(base_folder, target_field_folder):
        """
        Moves all third-level subfolders to a specified target folder target_field_folder,
        then deletes the first two parent directories while preserving the content.

        :param base_folder: Path to the root directory to start searching.
        :param target_field_folder: Path to the target folder 'field' to move contents.
        """
        # Ensure the base folder exists
        if not os.path.isdir(base_folder):
            print(f"The base folder '{base_folder}' does not exist.")
            return

        # Create the target field folder if it doesn't exist
        os.makedirs(target_field_folder, exist_ok=True)

        # Traverse the base folder and process third-level subfolders
        for root, subdirs, _ in os.walk(base_folder):
            # Calculate depth relative to base_folder
            depth = root[len(base_folder):].count(os.sep)
            if depth == 2:  # Third-level folders appear at depth 2
                for subdir in subdirs:
                    source_path = os.path.join(root, subdir)
                    target_path = os.path.join(target_field_folder, subdir)

                    try:
                        # Move the folder (and its contents) to the target
                        shutil.move(source_path, target_path)
                    except Exception as e:
                        print(f"Error moving {source_path}: {e}")

        # Delete the two first parent directories after moving content
        for root, _, _ in os.walk(base_folder):
            # Calculate depth relative to base_folder
            depth = root[len(base_folder):].count(os.sep)
            if depth < 2:  # Only consider the top two levels
                try:
                    shutil.rmtree(root)
                except Exception as e:
                    print(f"Error deleting folder {root}: {e}")