"""File discovery for the shared toolbar's Auto-upload action."""
import os
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Callable


@dataclass
class AutoImportSource:
    """One independent import, with the same loader used by a tool's manual import.

    Only the remembered directory is searched. Single-file inputs prefer their exact
    FF8 name, then the last selected file; multiple matches otherwise need a manual pick.
    """

    key: str
    patterns: tuple[str, ...]
    loader: Callable[[list[str]], None]
    multiple: bool = True
    folder: str = ""
    exact_name: str = ""
    recursive: bool = False

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
