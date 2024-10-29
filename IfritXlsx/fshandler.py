import glob
import os
import pathlib
import shutil
import subprocess

DELING_PATH = os.path.join("Resources", "ArchiveManagementCLI")
DELING_LIST_FILES = glob.glob(os.path.join(DELING_PATH, "*"))
DELING_OUTPUT_ROOT_PATH = os.path.join("OutputFiles", "battle")


def unpack(source_path, dest_path):
    os.makedirs(dest_path, exist_ok=True)
    subprocess.run(["Resources/ArchiveManagementCLI/deling-cli.exe", "export", os.path.join(source_path, "battle.fs"), dest_path])


def pack(source_path, dest_path, lang="eng"):
    """The deling-cli.exe create the .fl by taking the relative path of where the file is executed,
    which is not good for the "official" .fl file."""
    os.makedirs(dest_path, exist_ok=True)
    subprocess.run(["Resources/ArchiveManagementCLI/deling-cli.exe", "import", "-c", "lzs", source_path, os.path.join(dest_path,"battle.fs"), "-f", "--prefix", 'c:\\ff8\\data\\'+lang+'\\battle\\'])
