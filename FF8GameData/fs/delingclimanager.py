import os
import subprocess


class DelingCliManager:
    DEFAULT_DELING_PATH = os.path.join("fs", "DelingCli")

    def __init__(self, deling_path=None):
        if deling_path:
            self.__deling_path = deling_path
        else:
            self.__deling_path = self.DEFAULT_DELING_PATH

    def unpack(self, fs_path, folder_dest_path, recursive=True):
        os.makedirs(folder_dest_path, exist_ok=True)
        command = [os.path.join(self.__deling_path, "deling-cli.exe"), "unpack"]
        if recursive:
            command.append("-r")
        command += [fs_path, folder_dest_path]
        return subprocess.run(command)

    def pack(self, fs_path, folder_dest_path):
        os.makedirs(folder_dest_path, exist_ok=True)
        subprocess.run([os.path.join(self.__deling_path, "deling-cli.exe"), "pack", fs_path, folder_dest_path])

    def export_csv(self, fs_path, csv_path):
        subprocess.run([os.path.join(self.__deling_path, "deling-cli.exe"), "export-texts", "--force", fs_path, csv_path])

    def import_csv(self, fs_path, csv_path):
        subprocess.run([os.path.join(self.__deling_path, "deling-cli.exe"), "import-texts", fs_path, csv_path])
