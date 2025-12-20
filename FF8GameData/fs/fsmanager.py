import glob
import inspect
import os
import pathlib
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Generator

from fs.lzs import Lzs


class FsFileType(Enum):
    MAIN = auto()
    MENU = auto()
    WORLD = auto()
    FIELD = auto()
    MAGIC = auto()
    BATTLE = auto()
    UNKNOWN = auto()


@dataclass
class FiSingleData:
    length_unpack_file: int
    packed_file_location: int
    compression_used: bool


class Archive:
    """
    An archive is a composition of 3 files: FS, FI and FL.
    The workflow to read is a follow:
    1) Create the archive with the path for each file (done by creating the class)
    2) Load the data (thus the data can be loaded only when needed) with load_data
    3) Analyse the archive (thus the data can be loaded but analysed at a later time, or unload after analysing) with analyse_data
    4) Retrieve the data with get_fs_data_analysed
    Normally there is no need to retrieve other info, but if needed the fi and fl data can be retrieved

    The part that takes the most time is decompressing the data during the analysis.
    The decoding use a C logic algorithm, which could be pretty fast if used with CPython (look pylzss in GitHub), but the code need to be compiled.
    The aim being to use this software in any machine, the decision was made to keep it in pure Python.
    To limit the impact, this class create a generator.
    The advantage of a generator is to load only what is necessary, but it will be done only when needed.
    The disadvantage is that if you decide to read it all, it will not be done in advance.
    """
    FILE_NAME_STR_LIST = ("main", "menu", "world", "field", "magic", "battle")
    FILE_NAME_LIST = (FsFileType.MAIN, FsFileType.MENU, FsFileType.WORLD, FsFileType.FIELD, FsFileType.MAGIC, FsFileType.BATTLE)
    OFFSET_SIZE = 4

    def __init__(self, fs_path: str, fi_path: str, fl_path: str):
        """
        The different path contains the name of the file
        """
        # Raw data
        self._fs_path = fs_path
        self._fi_path = fi_path
        self._fl_path = fl_path
        self._fs_data = bytearray()
        self._fi_data = bytearray()
        self._fl_data = []
        self.lzs = Lzs()

        # Data analysed now
        self.name = pathlib.Path(fs_path).name.replace(".fs", "")
        print(f"Creating archive for {self.name}")
        if self.name not in self.FILE_NAME_STR_LIST:
            # print(f"Type unknown, probably from nested archive: {self.name}")
            self.type = FsFileType.UNKNOWN
        else:
            self.type = self.FILE_NAME_LIST[self.FILE_NAME_STR_LIST.index(self.name)]

        # Data analysed later
        self._fl_data_list = []
        self._fs_data_list = []
        self._fi_data_list = []
        self._archive_list = [] # For nested archive
        self._nb_file = 0
        self._fs_file_size = 0

    def __str__(self):
        return f"Archive(name:{self.name}, loaded:{self.is_loaded()}, analysed:{self.is_analysed()})"

    def __repr__(self):
        return self.__str__()

    def is_loaded(self):
        return self._fl_data and self._fi_data and self._fs_data

    def is_analysed(self):
        return self._fl_data_list and self._nb_file > 0 and self._fi_data_list and self._fs_data_list

    @classmethod
    def from_folder_and_name(cls, folder_path, name):
        """
        Allow to create an archive from just a folder path and a common name for all 3 files fi fl and fs
        :param folder_path: The path to the folder containing the 3 files fs, fl and fi. The name of the 3 files need to be the same
        :param name: The name of the archive (the common name of the 3 files fs, fi and fl)
        :return: The instantiate Archive
        """
        return cls(os.path.join(folder_path, name + ".fs"), os.path.join(folder_path, name + ".fi"), os.path.join(folder_path, name + ".fl"))

    def load_data(self):
        """
        Read all data in memory
        No error management if the file path are invalid
        """
        with open(self._fs_path, "rb") as file:
            self._fs_data.extend(file.read())
        with open(self._fi_path, "rb") as file:
            self._fi_data.extend(file.read())
        with open(self._fl_path, "r", encoding="utf8") as file:
            self._fl_data = file.read().splitlines()

    def load_data_from_bytes(self, fs_data: bytearray, fi_data: bytearray, fl_data: bytearray):
        self._fs_data = fs_data
        self._fi_data = bytes(fi_data)
        self._fl_data = bytes(fl_data).decode(encoding="utf8").splitlines()

    def unload_data(self):
        """Removing the data from memory"""
        self._fs_data = bytearray()
        self._fi_data = bytearray()
        self._fl_data = bytearray()

    def analyse_data(self, nested=False):
        """
        Analysing the data already loaded
        If no data have been loaded, the data is loaded on itself
        First the Fl file is analysed, then the Fi then the Fs
        :param nested: If True, the sub archive will be analysed
        """
        # Checking if data have been loaded previously
        if not self._fs_data or not self._fi_data or not self._fl_data:
            print("Wasn't loaded")
            self.load_data()
        # For FL, the data is already a list of text
        self._fl_data_list = self._fl_data
        self._nb_file = len(self._fl_data_list)
        # FI analyse
        for current_offset in range(0, len(self._fi_data), 3 * self.OFFSET_SIZE):
            length_unpack_file = int.from_bytes(self._fi_data[current_offset:current_offset + self.OFFSET_SIZE], byteorder="little")
            packed_file_location = int.from_bytes(self._fi_data[current_offset + self.OFFSET_SIZE:current_offset + self.OFFSET_SIZE * 2], byteorder="little")
            compression_used = bool(
                int.from_bytes(self._fi_data[current_offset + self.OFFSET_SIZE * 2:current_offset + self.OFFSET_SIZE * 3], byteorder="little"))
            self._fi_data_list.append(FiSingleData(length_unpack_file, packed_file_location, compression_used))
        # FS analyse
        if inspect.isgenerator(self._fs_data):
            self._fs_data = bytes(self._fs_data)
        self._fs_file_size = int.from_bytes(self._fs_data[0:4], byteorder='little')
        nested_archive = {}
        for i in range(0, self._nb_file):
            if i == self._nb_file - 1:
                end_data = len(self._fs_data)
            else:
                end_data = self._fi_data_list[i + 1].packed_file_location
            start_data = self._fi_data_list[i].packed_file_location + 4  # 4 bytes for length of file at start

            if self._fi_data_list[i].compression_used:
                new_fs_data = self.lzs.decode(self._fs_data[start_data:end_data])
            else:
                new_fs_data = self._fs_data[start_data:end_data]
            self._fs_data_list.append(new_fs_data)

            if nested:
                extension = self._fl_data[i].split('.')[-1]
                name = self._fl_data[i].split('\\')[-1].split('.')[0]
                if extension in ("fs", "fi", "fl"):  # Means we have a nested archive
                    if name not in nested_archive:
                        nested_archive[name] = {}
                    nested_archive[name][extension + "_data"] = new_fs_data
                    nested_archive[name][extension + "_path"] = self._fl_data_list[i]
                    print("New archive soon")

        if nested:
            for key, item in nested_archive.items():
                if len(nested_archive[key]) != 6:
                    print(f"Archive missing some file for {key}")
                    continue
                nested_fs = None
                nested_fi = None
                nested_fl = None
                path_fs = None
                path_fi = None
                path_fl = None
                for extension, data in item.items():
                    if extension.split('_')[0] not in ("fs", "fi", "fl"):
                        print(f"Unexpected extension: {extension}")
                    elif extension == "fs_data":
                        nested_fs = data
                    elif extension == "fs_path":
                        path_fs = data
                    elif extension == "fi_data":
                        nested_fi = data
                    elif extension == "fi_path":
                        path_fi = data
                    elif extension == "fl_data":
                        nested_fl = data
                    elif extension == "fl_path":
                        path_fl = data

                new_archive = Archive(path_fs, path_fi, path_fl)
                new_archive.load_data_from_bytes(nested_fs, nested_fi, nested_fl)
                new_archive.analyse_data(nested=True)
                self._archive_list.append(new_archive)

    def get_fs_data_analysed(self) -> list[Generator[bytes, None, None]] | list[bytes] :
        """
        Give the previously analysed data (empty if no analysed have been done), which can contains generator
        if there is compressed data AND the generator hasn't been used
        :return: The FS data
        """
        return self._fs_data_list

    def get_fi_data_analysed(self) -> list[FiSingleData]:
        return self._fi_data_list

    def get_fl_data_analysed(self) -> list[str]:
        return self._fl_data_list

    def get_archive_list(self) -> list[type['Archive']]:
        return self._archive_list

    def get_all_data_by_name(self, name) -> list[(str, Generator[bytes, None, None])]:
        """
        Give all element with a specific name (the name being the last element of the path in the fl file)
        :param name: The name of the element searched
        :return: The list of all element found with this name. Each element of the list is a tuple of (fl string, fs data)
        """
        list_return = []
        if not self.is_analysed():
            print("get_all_data_by_name:Archive not analysed")
            return []
        fs_data = self.get_fs_data_analysed()
        fl_data = self.get_fl_data_analysed()
        archive_list = self.get_archive_list()
        for i, path_fl in enumerate(fl_data):
            if path_fl.split('\\')[-1] == name:
                list_return.append((path_fl, fs_data[i]))
        for archive in archive_list:
            list_return.extend(archive.get_all_data_by_name(name=name))
        return list_return


class FsManager:
    """
    The FsManager is a class that manage a list of archive.
    The aim is to provide an easy-to-use abstract of a list of archive
    It is totally possible to manager his own list as the Archive class works on its own.
    """

    def __init__(self, folder_path=None):
        self._archive_list = []
        if folder_path:
            self.preload_all_archive_in_folder(folder_path)

    def __str__(self):
        return_str = ""
        for archive in self._archive_list:
            return_str += str(archive) + "\n"
        return return_str

    def __repr__(self):
        return self.__str__()

    def preload_all_archive_by_default_name(self, folder_path: str):
        """
        Preload all default archive that are found in FF8
        :param folder_path: The path to the folder containing the 3 files fs, fl and fi. The name of the 3 files need to be the same
        """
        for file_name in Archive.FILE_NAME_STR_LIST:
            self._archive_list.append(Archive.from_folder_and_name(folder_path, file_name))

    def preload_all_archive_in_folder(self, folder_path: str):
        """
        Preload all archive found in a folder
        :param folder_path: The path to the folder containing the 3 files fs, fl and fi. The name of the 3 files need to be the same
        """
        fs_file_in_folder = glob.glob(os.path.join(folder_path, "*.fs"))
        for fs_file in fs_file_in_folder:
            if os.path.exists(fs_file.replace(".fs", ".fi")):
                if os.path.exists(fs_file.replace(".fs", ".fl")):
                    file_name = pathlib.Path(fs_file).name.replace(".fs", "")
                    self._archive_list.append(Archive.from_folder_and_name(folder_path, file_name))
                else:
                    print(f"File {fs_file.replace(".fs", ".fl")} doesn't exist")
            else:
                print(f"File {fs_file.replace(".fs", ".fi")} doesn't exist")

    def load_all_archive(self):
        """
        Load in memory the archive.
        """
        for archive in self._archive_list:
            archive.load_data()

    def analyse_all_archive(self, nested=False):
        """
        Analyse all archive
        :param nested: If True, the sub archive will be analysed
        """
        for archive in self._archive_list:
            archive.analyse_data(nested)

    def unload_all_archive(self):
        """
        This allows to remove from memory the previously loaded archive.
        """
        for archive in self._archive_list:
            archive.unload_data()

    def load_archive_by_name(self, name: str):
        self.get_archive_by_name(name).load_data()

    def analyse_archive_by_name(self, name, nested=False):
        """
        Analyse the archive by name
        :param name: The name of the archive (the common name of the 3 files fs, fi and fl)
        :param nested: If True, the sub archive will be analysed
        """
        self.get_archive_by_name(name).analyse_data(nested)

    def get_data_by_name(self, name: str):
        self.get_archive_by_name(name).get_fs_data_analysed()

    def get_archive_by_name(self, name: str) -> Archive:
        """
        Retrieve the archive, allowing to directly work on it instead of using the fs manager.
        :param name: The name of the archive (the common name of the 3 files fs, fi and fl)
        :return: The archive (None if no archive found)
        """
        for archive in self._archive_list:
            if archive.name == name:
                return archive
        print(f"Name not found in the archive: {name}")

    def get_all_data_by_name(self, name) -> list[(str, Generator[bytes, None, None])]:
        """
        Give all element with a specific name (the name being the last element of the path in the fl file)
        :param name: The name of the element searched
        :return: The list of all element found with this name. Each element of the list is a tuple of (fl string, fs data)
        """
        list_return = []
        for archive in self._archive_list:
            list_return.extend(archive.get_all_data_by_name(name))
        return list_return


if __name__ == "__main__":
    # First an example for reading one file in the fs

    # # Create the fsManager
    # fs_manager = FsManager()
    # # Now do the full workflow:
    # # 1. Preload (means reading the folder to find the different files)
    # fs_manager.preload_all_archive_in_folder(os.path.join("..", "FsTester"))
    # # 2. Load (means reading the data, which take memory and time)
    # fs_manager.load_archive_by_name("magic")
    # # 3. Analyse (means analysing the data previously loaded, take time)
    # fs_manager.analyse_archive_by_name("magic")
    #
    # # Retrieving as an example the archive for magic
    # archive_magic = fs_manager.get_archive_by_name("magic")
    # archive_fs_data = archive_magic.get_fs_data_analysed()
    # archive_fi_data = archive_magic.get_fi_data_analysed()
    # archive_fl_data = archive_magic.get_fl_data_analysed()
    #
    # # Printing the first info for magic
    # print(f"Fl path: {archive_fl_data[0]}")
    # print(f"Fi archive data: {archive_fi_data[0]}")
    # print(f"Fs hex: {bytes(archive_fs_data[0]).hex(" ")}")
    #
    # # Print the fs manager, which will show all the archive loaded
    # print(fs_manager)

    # Now an example retrieving all chara.one files
    # Create the fsManager
    fs_manager = FsManager()
    # Now do the full workflow:
    # 1. Preload (means reading the folder to find the different files)
    fs_manager.preload_all_archive_in_folder(os.path.join("..", "FsTester"))
    # 2. Load (means reading the data, which take memory and time)
    fs_manager.load_all_archive()
    # 3. Analyse (means analysing the data previously loaded, take time)
    # fs_manager.analyse_all_archive(True)
    fs_manager.analyse_all_archive(nested=True)
    # fs_manager.analyse_archive_by_name(name="field", nested=False)

    # Now finding all chara.one. Keep in mind that the fs data is a generator :)
    all_chara_one = fs_manager.get_all_data_by_name("chara.one")

    print(f"Nb chara one found: {len(all_chara_one)}")
    for fl, fs in all_chara_one:
        print(f"Fl: {fl}")
