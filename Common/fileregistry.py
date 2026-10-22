import os
from contextlib import contextmanager

from PyQt6.QtCore import QObject, pyqtSignal


class FileRegistry(QObject):
    """The FF8 files currently opened, shared by every tool.

    A file is identified by its FF8 name ("price.bin", "mitem.bin", ...), not by the tool that
    opened it: several tools edit or read the same file (mngrp.bin alone is used by six of them),
    so it is only searched for once. Opening another file in any tool replaces the previous one
    for every tool using that name.
    """

    file_changed = pyqtSignal(str)  # FF8 file name: its path changed, tools must load it again
    # (FF8 file name, path it had): the file was removed from the opened files - every tool must
    # stop using it (no save, no reload, no pick-up by a tool opened later).
    file_closed = pyqtSignal(str, str)
    # A batch of opens (batch()) ended: the views that skipped refreshing during it refresh now
    batch_finished = pyqtSignal()

    def __init__(self, settings=None):
        QObject.__init__(self)
        self.paths = {}  # FF8 file name -> path of the file currently opened
        self._batch_depth = 0
        self.bindings = []  # every FileBinding created on this registry (registers itself)
        # file name -> its bindings: a change goes straight to the bindings of that file. Every
        # binding listening to every change was quadratic - opening Fujin's 355 effect files made
        # 280 000 slot calls (seconds) for nothing
        self._routes = {}
        self.file_changed.connect(self._route_changed)
        self.file_closed.connect(self._route_closed)
        # Per-tool memory of the last folder an Open dialog was used in, so it re-opens there next
        # time - within the session and, when settings is a QSettings, across future sessions too.
        self.settings = settings
        self._last_folders = {}  # in-memory fallback when used without QSettings (tools alone)
        self._last_files = {}
        self._last_selections = {}
        # settings written during a batch, stored when it ends: QSettings writes the whole store
        # back after each change, and a progress bar's event processing after every file made
        # that 80 ms per file - most of the 50 s Fujin took to reopen its 355 effect files
        self._pending_settings = {}

    def route(self, binding):
        """Deliver this file's changes and closes to `binding` (FileBinding registers itself)."""
        self._routes.setdefault(binding.file_name, []).append(binding)

    def _routed(self, file_name):
        from PyQt6 import sip
        bindings = self._routes.get(file_name, [])
        alive = [binding for binding in bindings if not sip.isdeleted(binding)]
        if len(alive) != len(bindings):
            self._routes[file_name] = alive
        return list(alive)

    def _route_changed(self, file_name):
        for binding in self._routed(file_name):
            binding._on_registry_changed(file_name)

    def _route_closed(self, file_name, file_path):
        for binding in self._routed(file_name):
            binding._on_registry_closed(file_name, file_path)

    def last_files(self, file_key):
        """Last explicit selection, or None when this input has no saved selection yet."""
        if self.settings is not None:
            key = f"last_files/{file_key}"
            if key in self._pending_settings:
                return list(self._pending_settings[key])
            return self.settings.value(key, [], type=list) if self.settings.contains(key) else None
        paths = self._last_selections.get(file_key)
        return list(paths) if paths is not None else None

    def remember_files(self, file_key, paths):
        """Persist the exact last selection, preserving order and files in different folders."""
        selected, seen = [], set()
        for path in paths:
            absolute = os.path.abspath(path)
            normalized = os.path.normcase(absolute)
            if normalized not in seen:
                selected.append(absolute)
                seen.add(normalized)
        if not selected:
            return  # cancelling a picker must not erase the previous selection
        self.remember_folder(file_key, os.path.dirname(selected[0]))
        if self.settings is not None:
            self._store(f"last_files/{file_key}", selected)
            self._store(f"last_file/{file_key}", selected[0])
        else:
            self._last_selections[file_key] = selected
            self._last_files[file_key] = selected[0]

    def last_file(self, file_key):
        """Last selected path, used to disambiguate wildcard imports across sessions."""
        if self.settings is not None:
            return self._setting(f"last_file/{file_key}")
        return self._last_files.get(file_key, "")

    def last_folder(self, tool_key):
        """The folder an Open dialog for tool_key should start in (empty if none remembered yet)."""
        if self.settings is not None:
            return self._setting(f"last_folder/{tool_key}")
        return self._last_folders.get(tool_key, "")

    def remember_folder(self, tool_key, folder):
        """Store the folder a file was just opened from, keyed by tool, for next time."""
        if not folder:
            return
        if self.settings is not None:
            self._store(f"last_folder/{tool_key}", folder)
        else:
            self._last_folders[tool_key] = folder

    def _store(self, key, value):
        if self.batching:
            self._pending_settings[key] = value
        else:
            self.settings.setValue(key, value)

    def _setting(self, key):
        """A string setting, the batch's pending value first."""
        if key in self._pending_settings:
            return self._pending_settings[key]
        return self.settings.value(key, "", type=str)

    def accepted_file_names(self):
        """The concrete FF8 file names every tool can open (for the "Open folder" scan).

        Bindings whose filter is a wildcard (e.g. Ifrit's *.dat, CCGroup's *.exe) match no single
        name, so they are left out - a folder scan can't pick one file among many."""
        return {binding.file_name for binding in self.bindings if "*" not in binding.file_filter}

    @property
    def batching(self):
        """True while many files are being opened at once (see batch())."""
        return self._batch_depth > 0

    @contextmanager
    def batch(self):
        """Open many files at once: every binding still loads its own file as it opens, but the
        views that list or count the opened files (header toolbar, Opened files panel) skip their
        refresh until the batch ends, then refresh once (batch_finished). Without it, opening N
        files rebuilt those views N times."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                pending, self._pending_settings = self._pending_settings, {}
                for key, value in pending.items():
                    self.settings.setValue(key, value)
                self.batch_finished.emit()

    def get_path(self, file_name):
        """Path currently opened for that FF8 file, or an empty string if no file is opened."""
        return self.paths.get(file_name, "")

    def open_file(self, file_name, file_path):
        """Set the file every tool using file_name must now work on."""
        # Summary entries for multi-file tools are labels, not actual file paths.
        if os.path.isfile(file_path):
            self.remember_files(file_name, [file_path])
        self.paths[file_name] = file_path
        self.file_changed.emit(file_name)

    def close_file(self, file_name):
        """Remove a file from the opened files: file_closed tells every tool to drop it, then
        file_changed refreshes the views that list or count the opened files."""
        file_path = self.paths.pop(file_name, None)
        if file_path is None:
            return
        self.file_closed.emit(file_name, file_path)
        self.file_changed.emit(file_name)

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
