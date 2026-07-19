import os

from PyQt6.QtCore import QObject, pyqtSignal


class FileRegistry(QObject):
    """The FF8 files currently opened, shared by every tool.

    A file is identified by its FF8 name ("price.bin", "mitem.bin", ...), not by the tool that
    opened it: several tools edit or read the same file (mngrp.bin alone is used by six of them),
    so it is only searched for once. Opening another file in any tool replaces the previous one
    for every tool using that name.
    """

    file_changed = pyqtSignal(str)  # FF8 file name: its path changed, tools must load it again
    reload_requested = pyqtSignal()  # every opened file must be re-read from disk (same paths)

    def __init__(self):
        QObject.__init__(self)
        self.paths = {}  # FF8 file name -> path of the file currently opened
        self.bindings = []  # every FileBinding created on this registry (registers itself)

    def accepted_file_names(self):
        """The concrete FF8 file names every tool can open (for the "Open folder" scan).

        Bindings whose filter is a wildcard (e.g. Ifrit's *.dat, CCGroup's *.exe) match no single
        name, so they are left out - a folder scan can't pick one file among many."""
        return {binding.file_name for binding in self.bindings if "*" not in binding.file_filter}

    def get_path(self, file_name):
        """Path currently opened for that FF8 file, or an empty string if no file is opened."""
        return self.paths.get(file_name, "")

    def open_file(self, file_name, file_path):
        """Set the file every tool using file_name must now work on."""
        self.paths[file_name] = file_path
        self.file_changed.emit(file_name)

    def reload_all(self):
        """Re-read every opened file from disk (e.g. after an external tool changed it), keeping
        the same paths. Each tool reloads its files through their FileBinding."""
        self.reload_requested.emit()

    @staticmethod
    def summarize_paths(paths, noun="file", max_listed=5):
        """A short description of several files under one registry entry, for a tool whose open
        files don't map to one fixed FF8 name (so they can't each get their own FileBinding) but
        still deserve a line in the Opened files panel - e.g. Alexander's multi-select of
        a0stgXXX.x. Lists each name when there are few; past max_listed, just the count and their
        common folder, so opening dozens at once doesn't flood the panel."""
        if not paths:
            return "none"
        if len(paths) == 1:
            return os.path.basename(paths[0])
        if len(paths) <= max_listed:
            return f"{len(paths)} {noun}s: " + ", ".join(os.path.basename(p) for p in paths)
        try:
            folder = os.path.commonpath(paths)
        except ValueError:  # e.g. paths on different drives - no common folder to show
            return f"{len(paths)} {noun}s"
        return f"{len(paths)} {noun}s in {folder}"
