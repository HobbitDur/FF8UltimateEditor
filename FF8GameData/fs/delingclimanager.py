import os
import subprocess
import sys


class DelingCliManager:
    DEFAULT_DELING_PATH = os.path.join("fs", "DelingCli")
    DELING_CLI_NAME = "deling-cli.exe" if sys.platform == "win32" else "deling-cli"

    def __init__(self, deling_path=None):
        if deling_path:
            self.__deling_path = deling_path
        else:
            self.__deling_path = self.DEFAULT_DELING_PATH

    def cli_path(self):
        return os.path.join(self.__deling_path, self.DELING_CLI_NAME)

    def is_installed(self):
        """deling-cli is installed with the Deling tool update; without it nothing here can run."""
        return os.path.isfile(self.cli_path())

    def unpack(self, fs_path, folder_dest_path, recursive=True):
        os.makedirs(folder_dest_path, exist_ok=True)
        command = [os.path.join(self.__deling_path, self.DELING_CLI_NAME), "unpack"]
        if recursive:
            command.append("-r")
        command += [fs_path, folder_dest_path]
        return subprocess.run(command)

    def pack(self, fs_path, folder_dest_path):
        os.makedirs(folder_dest_path, exist_ok=True)
        subprocess.run([os.path.join(self.__deling_path, self.DELING_CLI_NAME), "pack", fs_path, folder_dest_path])

    def export_csv(self, fs_path, csv_path, game_data=None):
        """With game_data on a character table other than Latin (Japanese, Vietnamese), the CSV holds the
        text in that table (see delingjp)."""
        from FF8GameData.fs.delingjp import convert_csv, needs_conversion
        if game_data is not None and needs_conversion(game_data):
            latin_csv = csv_path + ".latin.tmp"
            self.__force_latin_encoding()
            subprocess.run([self.cli_path(), "export-texts", "--force", fs_path, latin_csv])
            try:
                convert_csv(game_data, latin_csv, csv_path, from_deling_csv=True)
            finally:
                if os.path.exists(latin_csv):
                    os.remove(latin_csv)
            return
        subprocess.run([os.path.join(self.__deling_path, self.DELING_CLI_NAME), "export-texts", "--force", fs_path, csv_path])

    def import_csv(self, fs_path, csv_path, game_data=None):
        """With game_data on a character table other than Latin (Japanese, Vietnamese), the CSV holds the
        text in that table (see delingjp)."""
        from FF8GameData.fs.delingjp import convert_csv, needs_conversion
        if game_data is not None and needs_conversion(game_data):
            latin_csv = csv_path + ".latin.tmp"
            convert_csv(game_data, csv_path, latin_csv, from_deling_csv=False)
            self.__force_latin_encoding()
            try:
                subprocess.run([self.cli_path(), "import-texts", fs_path, latin_csv])
            finally:
                os.remove(latin_csv)
            return
        subprocess.run([os.path.join(self.__deling_path, self.DELING_CLI_NAME), "import-texts", fs_path, csv_path])

    def __force_latin_encoding(self):
        """Deling's Japanese setting decodes world texts (not field texts) in Japanese; the conversion needs Latin."""
        with open(os.path.join(self.__deling_path, "Deling.ini"), "w", encoding="ascii") as ini:
            ini.write("[General]\nencoding=00\n")
