import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog

from Common.fileregistry import FileRegistry


class FileBinding(QObject):
    """Binds one FF8 file to a tool through the shared FileRegistry, with no UI of its own.

    A tool lists the files it works on as FileBinding objects; the shared header toolbar
    (FileToolbarWidget) draws the Import / Import read-only / Save buttons and drives them.
    The tool only says, per file, how to load it (load_callback) and, for the files it edits,
    how to save it (save_callback).

    Sharing goes through the registry in every direction: opening a file here publishes it, so
    every tool bound to the same FF8 name loads it too, and a file another tool already opened is
    picked up on load_opened_file(). A read-only binding is one this tool never writes - the file
    is edited in another tool (e.g. mngrp.bin, edited only in Shiva, read by Zone and Moomba) - so
    it carries no save.
    """

    file_opened = pyqtSignal(str)  # emitted with the path whenever the bound file must be loaded

    def __init__(self, file_name, registry: FileRegistry, load_callback=None, save_callback=None,
                 file_filter=None, read_only=False):
        QObject.__init__(self)
        self.file_name = file_name
        self.registry = registry
        self.file_filter = file_filter or file_name  # default: only the file's exact name
        self.read_only = read_only
        self._save_callback = save_callback
        self._loaded_path = ""
        if load_callback is not None:
            self.file_opened.connect(load_callback)
        registry.bindings.append(self)  # so "Open folder" knows every file the tools accept
        registry.file_changed.connect(self._on_registry_changed)
        registry.reload_requested.connect(self._reload_from_disk)

    @property
    def is_loaded(self):
        """Whether this tool has a file loaded for that binding (so Save has something to do)."""
        return bool(self._loaded_path)

    @property
    def current_path(self):
        """The path shared for this FF8 file across the tools ("" if none is open)."""
        return self.registry.get_path(self.file_name)

    def load_opened_file(self):
        """Load the bound file if another tool (or this one) already opened it.

        Called once by the tool after construction: a tool can be created after another one
        already opened the file, in which case its file_changed signal was missed."""
        self._on_registry_changed(self.file_name)

    def open_dialog(self, parent):
        """Ask for a path and share it: loads it here and offers it to every bound tool."""
        path = QFileDialog.getOpenFileName(
            parent=parent, caption=f"Open {self.file_name}", filter=self.file_filter,
            directory=self.current_path or os.getcwd())[0]
        if path:
            self.open_path(path)

    def open_path(self, path):
        """Share a path for this file: loads it here and offers it to every bound tool.

        Used both by open_dialog and by the toolbar when it routes a multi-file pick to the
        matching binding."""
        self._loaded_path = ""  # an explicit Import always (re)loads, even the same path
        self.registry.open_file(self.file_name, path)  # -> _on_registry_changed, here and elsewhere

    def save(self):
        if not self.read_only and self._save_callback is not None:
            self._save_callback()

    def _on_registry_changed(self, file_name):
        if file_name != self.file_name:
            return
        path = self.current_path
        if path and path != self._loaded_path:  # skip a redundant reload of the same path
            self._loaded_path = path
            self.file_opened.emit(path)

    def _reload_from_disk(self):
        """Re-read this file from disk even though its path is unchanged (registry.reload_all)."""
        path = self.current_path
        if path:
            self._loaded_path = path
            self.file_opened.emit(path)
