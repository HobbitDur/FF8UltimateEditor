"""The 'field' folder the field tools open as a whole (CCGroup's NPC card players, Seed's fields).

A tool reading every map at once can't take a list of files, so it takes the field folder - and
checks it has the layout Deling extracts from field.fs and every FFNx mod uses:

    field\\
        mapdata\\<area>\\<map>\\<map>.jsm   (+ <map>.sym .msd .mim .map .ca .id, chara.one)
        model\\main_chr\\d0xx.mch

<area> is the two-letter map group (bc, bg, ti...), <map> the map name (bghall_1...). A mod's
field folder has the same layout with only the maps it changes.
"""
import os
from dataclasses import dataclass, field

from PyQt6.QtWidgets import QFileDialog, QMessageBox

MAPDATA = "mapdata"
# The full game has ~880 maps with a script: a folder with far fewer is a mod's (only its maps).
VANILLA_MIN_MAPS = 800
NEEDS_SCRIPTS = "jsm"       # CCGroup: the maps' field scripts
NEEDS_MODELS = "chara.one"  # Seed: the maps' character models
MAX_LISTED = 5

EXPECTED_LAYOUT = ("Expected layout (as Deling extracts it, and as FFNx mods use it):\n"
                   "    field\\\n"
                   "        mapdata\\<area>\\<map>\\<map>.jsm  (.sym, .msd, chara.one...)\n"
                   "        model\\main_chr\\d0xx.mch\n"
                   "e.g. field\\mapdata\\bg\\bghall_1\\bghall_1.jsm\n\n"
                   "Pick the 'field' folder itself (the one holding 'mapdata').")


@dataclass
class FieldFolderCheck:
    """What check_field_folder found. error is "" when the folder is usable."""
    root: str = ""        # the field folder (the one holding mapdata)
    maps: int = 0         # maps with their script at mapdata\<area>\<map>\<map>.jsm
    models: int = 0       # maps with a chara.one
    main_chr: str = ""    # field\model\main_chr, when it holds models
    misplaced: list = field(default_factory=list)  # .jsm found anywhere else (relative paths)
    error: str = ""

    @property
    def ok(self):
        return not self.error


def _listed(paths):
    shown = "\n".join(f"    {path}" for path in paths[:MAX_LISTED])
    more = f"\n    ... and {len(paths) - MAX_LISTED} more" if len(paths) > MAX_LISTED else ""
    return shown + more


def _wrong_pick_error(folder):
    """Why a folder without a mapdata subfolder is not a field folder, and which one to pick."""
    folder = os.path.normpath(folder)
    parts = folder.split(os.sep)
    lowered = [part.lower() for part in parts]
    if MAPDATA in lowered:  # picked mapdata itself, an area or a map folder: inside the field folder
        index = len(lowered) - 1 - lowered[::-1].index(MAPDATA)
        root = os.sep.join(parts[:index]) or os.sep
        inside = "the 'mapdata' folder" if index == len(parts) - 1 else f"'{parts[-1]}', inside 'mapdata'"
        return f"You picked {inside}, a folder inside the field folder.\n\nPick the field folder:\n    {root}"
    nested = os.path.join(folder, "field")
    if os.path.isdir(os.path.join(nested, MAPDATA)):
        return f"This folder holds a 'field' folder: pick that one instead:\n    {nested}"
    return f"No 'mapdata' folder in:\n    {folder}\n\n{EXPECTED_LAYOUT}"


def check_field_folder(folder, needs=NEEDS_SCRIPTS, complete=False) -> FieldFolderCheck:
    """Check a picked folder is a field folder with the expected layout.

    needs: NEEDS_SCRIPTS (at least one <map>.jsm, and no .jsm elsewhere, since every script found
    is read as a map) or NEEDS_MODELS (at least one chara.one). complete: it must be the whole game
    (a vanilla reference), not a mod folder holding only some maps."""
    check = FieldFolderCheck()
    if not folder or not os.path.isdir(folder):
        check.error = f"This folder does not exist:\n    {folder}"
        return check
    if not os.path.isdir(os.path.join(folder, MAPDATA)):
        check.error = _wrong_pick_error(folder)
        return check
    check.root = os.path.normpath(folder)
    main_chr = os.path.join(check.root, "model", "main_chr")
    if os.path.isdir(main_chr) and any(name.lower().endswith(".mch") for name in os.listdir(main_chr)):
        check.main_chr = main_chr
    for root, _dirs, files in os.walk(check.root):
        rel_parts = os.path.relpath(root, check.root).split(os.sep)
        # mapdata\<area>\<map>: the only place a map's files belong
        in_map_folder = len(rel_parts) == 3 and rel_parts[0].lower() == MAPDATA
        for name in files:
            lower = name.lower()
            if lower.endswith(".jsm"):
                if in_map_folder and lower == rel_parts[2].lower() + ".jsm":
                    check.maps += 1
                else:
                    check.misplaced.append(os.path.join(os.path.relpath(root, check.root), name))
            elif lower == "chara.one" and in_map_folder:
                check.models += 1

    where = f"\n    {check.root}"
    if needs == NEEDS_SCRIPTS:
        if check.misplaced:
            check.error = (f"{len(check.misplaced)} field script(s) (.jsm) are not where a map's script belongs "
                           f"(mapdata\\<area>\\<map>\\<map>.jsm) in:{where}\n{_listed(check.misplaced)}\n\n"
                           f"Every script found is read as a map: move or remove these files first.")
        elif not check.maps:
            check.error = f"No map script (mapdata\\<area>\\<map>\\<map>.jsm) in:{where}\n\n{EXPECTED_LAYOUT}"
    elif needs == NEEDS_MODELS and not check.models:
        check.error = f"No map model file (mapdata\\<area>\\<map>\\chara.one) in:{where}\n\n{EXPECTED_LAYOUT}"
    if not check.error and complete and check.maps < VANILLA_MIN_MAPS:
        check.error = (f"Only {check.maps} map(s) in:{where}\n\nThis looks like a mod's field folder (it holds only the "
                       f"maps it changes). The vanilla reference must be the whole game's field folder "
                       f"(about 880 maps), e.g. extracted from field.fs with Deling.")
    return check


def pick_field_folder(parent, tool_name, caption, start_dir="", needs=NEEDS_SCRIPTS, complete=False, remember=None):
    """Ask for a field folder and check it: the FieldFolderCheck of a usable one, else None (after a
    popup explaining what is wrong with the pick and what to pick instead). remember(folder) is
    called with the pick even when it is refused, so the next dialog opens there to fix it."""
    folder = QFileDialog.getExistingDirectory(parent, caption, start_dir or "")
    if not folder:
        return None
    if remember is not None:
        remember(os.path.normpath(folder))
    check = check_field_folder(folder, needs, complete)
    if not check.ok:
        QMessageBox.warning(parent, f"{tool_name} - not a usable field folder", check.error)
        return None
    return check
