"""The battle files a tool's BattleScenePreview draws, opened as side files (only read, never edited).

A host (JumboCactuar, Alexander) offers them in the header's Import read-only menu (entries()),
Open folder (load_folder) and Auto-upload (auto_import_source); they are listed under one summary
entry of the Opened files panel (`registry_key`) and closing it there forgets them. The preview
finds them by name (path) and stands the party among the opened characters and weapons.
"""
import fnmatch
import os

from PyQt6.QtWidgets import QFileDialog

from Common.autoimport import AutoImportSource
from Common.fileregistry import FileRegistry

BATTLE_FILE_PATTERNS = ("a0stg*.x", "c0m*.dat", "d?c*.dat", "d?w*.dat")
MODEL_FOLDER_KEY = "battle model (.dat)"   # the monsters' folder, remembered with Ifrit's and Xu's
STAGE_FOLDER_KEY = "battle stage (.x)"


class BattleSideFiles:
    def __init__(self, parent_widget, file_registry, registry_key, preview, patterns=BATTLE_FILE_PATTERNS):
        self.parent_widget = parent_widget
        self.file_registry = file_registry
        self.registry_key = registry_key
        self.preview = preview
        self.patterns = patterns
        self.files = {}   # lower-case file name -> path
        file_registry.file_closed.connect(self._on_registry_closed)

    def path(self, name):
        return self.files.get(name.lower())

    def entries(self):
        """The header's Import read-only menu entries."""
        entries = [("Monsters: c0m###.dat (several, Ctrl+A for all)", self.import_monsters),
                   ("Party: characters d?c###.dat and their weapons d?w###.dat (several, Ctrl+A for all)",
                    self.import_party)]
        if "a0stg*.x" in self.patterns:
            entries.append(("Battle stages: a0stg###.x (several, Ctrl+A for all)", self.import_stages))
        return entries

    def import_monsters(self):
        self._import("Monsters to show in the battle preview (Ctrl+A for all)", MODEL_FOLDER_KEY,
                     "Monster battle models (c0m*.dat)")

    def import_party(self):
        self._import("Characters and weapons to stand the party (Ctrl+A for all)", MODEL_FOLDER_KEY,
                     "Character and weapon battle models (d?c*.dat d?w*.dat)")

    def import_stages(self):
        self._import("Battle stages to show in the battle preview (Ctrl+A for all)", STAGE_FOLDER_KEY,
                     "Battle stages (a0stg*.x)")

    def _import(self, caption, folder_key, file_filter):
        file_paths = QFileDialog.getOpenFileNames(self.parent_widget, caption,
                                                  self.file_registry.last_folder(folder_key), file_filter)[0]
        if file_paths:
            self.file_registry.remember_folder(folder_key, os.path.dirname(file_paths[0]))
            self.add(file_paths)

    def load_folder(self, folder):
        """Every battle file found in the folder (and below; the first one of each name)."""
        found = {}
        for root, _folders, names in os.walk(folder):
            for name in names:
                if self._matches(name.lower()):
                    found.setdefault(name.lower(), os.path.join(root, name))
        if found:
            self.add(list(found.values()))

    def auto_import_source(self):
        """The header's Auto-upload: the battle files opened last time."""
        return AutoImportSource(self.registry_key, self.patterns, self.add, selection_only=True)

    def add(self, file_paths):
        for path in file_paths:
            name = os.path.basename(path).lower()
            if self._matches(name):
                self.files[name] = path
        paths = list(self.files.values())
        self.file_registry.remember_files(self.registry_key, paths)
        # No fixed FF8 name: one summary entry in the Opened files panel (as Alexander's stages)
        self.file_registry.open_file(self.registry_key, FileRegistry.summarize_paths(paths, "battle file"))
        self.preview.set_party_files(paths)
        self.preview.files_changed()

    def _matches(self, name):
        return any(fnmatch.fnmatch(name, pattern) for pattern in self.patterns)

    def _on_registry_closed(self, file_name, _path):
        if file_name == self.registry_key:   # removed from the Opened files panel
            self.files.clear()
            self.preview.set_party_files([])
            self.preview.files_changed()
