"""The FFNx animation set files Fujin's previews play, Qt-free: effect_NNN.animset (effect_NNN_K.animset for the K-th set of an effect
that binds several, FF8GameData.dat.exeanimset). In the game FFNx loads them from direct/exe in place of the exe's sets (body animations,
sequences, weapon animations); here the recorder does (animset=address:file), so what the Overview and the part tabs record is what
the game plays. A new effect plays its own copy of the set (its Data tab), not these.
"""
import functools
import os

from FF8GameData.dat.exeanimset import MAX_FILE_SIZE, anim_set_error, info_from_file_name, locate_anim_sets

IMAGE_BASE = 0x400000


@functools.lru_cache(maxsize=1)
def _set_addresses(exe_path, _stamp):
    with open(exe_path, "rb") as file:
        return {info: offset + IMAGE_BASE for info, offset in locate_anim_sets(file.read()).items()}


def file_error(path):
    """Why FFNx would ignore this file, or None when it plays it."""
    info = info_from_file_name(path)
    if info is None:
        return "no animation set of the game has this name (effect_NNN.animset, effect_NNN_K.animset)"
    try:
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE:
            return f"bigger than {MAX_FILE_SIZE} bytes"
        with open(path, "rb") as file:
            return anim_set_error(file.read(), info.section_count)
    except OSError as error:
        return str(error)


class AnimSetFiles:
    """The imported files: one per set of the game."""

    def __init__(self):
        self.paths = {}                                 # AnimSetInfo -> path

    def load(self, paths):
        """(the effects of the files taken, [(path, why it was refused)])."""
        loaded, refused = [], []
        for path in paths:
            reason = file_error(path)
            if reason:
                refused.append((path, reason))
                continue
            info = info_from_file_name(path)
            self.paths[info] = path
            if info.effect_id not in loaded:
                loaded.append(info.effect_id)
        return loaded, refused

    def bindings(self, effect, exe_path):
        """((the exe address of a set, the file that plays instead), ...) of an effect, its files still there."""
        chosen = [(info, path) for info, path in self.paths.items() if info.effect_id == effect and os.path.isfile(path)]
        if not chosen or not exe_path or not os.path.isfile(exe_path):
            return ()
        addresses = _set_addresses(exe_path, os.stat(exe_path).st_mtime_ns)
        return tuple(sorted((addresses[info], path) for info, path in chosen if info in addresses))
