"""File discovery for the shared toolbar's Auto-upload action."""
import os
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Callable


@dataclass
class AutoImportSource:
    """One independent import, with the same loader used by a tool's manual import.

    Saved selections are reopened exactly, skipping missing files. Single-file inputs
    without selection history can discover their expected FF8 name in the remembered folder.
    """

    key: str
    patterns: tuple[str, ...]
    loader: Callable[[list[str]], None]
    multiple: bool = True
    folder: str = ""
    exact_name: str = ""
    recursive: bool = False
    selection_only: bool = False
    selection_key: str = ""

    @classmethod
    def for_binding(cls, binding, folder=""):
        # The first Qt filter is the intended file type; never use an "All files" fallback.
        first_filter = binding.file_filter.split(";;", 1)[0]
        match = re.search(r"\(([^)]+)\)", first_filter)
        patterns = tuple((match.group(1) if match else first_filter).split())
        return cls(binding.file_name, patterns,
                   lambda paths: binding.open_path(paths[0]), multiple=False,
                   folder=folder, exact_name=binding.file_name)

    def find_paths(self, registry):
        selected = registry.last_files(self.selection_key or self.key)
        if selected is None and not self.multiple and registry.last_file(self.key):
            selected = [registry.last_file(self.key)]  # selections saved by older versions
        if selected is not None:
            paths = [path for path in selected if os.path.isfile(path)
                     and any(fnmatchcase(os.path.basename(path).lower(), pattern.lower())
                             for pattern in self.patterns)]
            return paths if self.multiple else paths[:1]
        if self.selection_only:
            return []  # a legacy folder alone must never expand into hundreds of model files
        folder = registry.last_folder(self.key) or self.folder
        if not folder:
            return []
        try:
            if self.recursive:
                candidates = (os.path.join(root, name)
                              for root, _dirs, names in os.walk(folder) for name in names)
                paths = [path for path in candidates
                         if any(fnmatchcase(os.path.basename(path).lower(), pattern.lower())
                                for pattern in self.patterns)]
            else:
                with os.scandir(folder) as entries:
                    paths = [entry.path for entry in entries if entry.is_file()
                             and any(fnmatchcase(entry.name.lower(), pattern.lower())
                                     for pattern in self.patterns)]
            paths.sort(key=str.casefold)
        except FileNotFoundError:
            return []
        if self.multiple or len(paths) <= 1:
            return paths
        for preferred in (self.exact_name, os.path.basename(registry.last_file(self.key))):
            matches = [path for path in paths
                       if os.path.basename(path).lower() == preferred.lower()]
            if len(matches) == 1:
                return matches
        raise ValueError("Several matching files in " + folder + "; select one with Import first")
