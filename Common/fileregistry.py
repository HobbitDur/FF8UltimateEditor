from PyQt6.QtCore import QObject, pyqtSignal


class FileRegistry(QObject):
    """The FF8 files currently opened, shared by every tool.

    A file is identified by its FF8 name ("price.bin", "mitem.bin", ...), not by the tool that
    opened it: several tools edit or read the same file (mngrp.bin alone is used by six of them),
    so it is only searched for once. Opening another file in any tool replaces the previous one
    for every tool using that name.
    """

    file_changed = pyqtSignal(str)  # FF8 file name: its path changed, tools must load it again

    def __init__(self):
        QObject.__init__(self)
        self.paths = {}  # FF8 file name -> path of the file currently opened

    def get_path(self, file_name):
        """Path currently opened for that FF8 file, or an empty string if no file is opened."""
        return self.paths.get(file_name, "")

    def open_file(self, file_name, file_path):
        """Set the file every tool using file_name must now work on."""
        self.paths[file_name] = file_path
        self.file_changed.emit(file_name)
