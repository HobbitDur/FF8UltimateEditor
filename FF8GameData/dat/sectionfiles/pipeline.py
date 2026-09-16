"""The steps every section-file pipeline repeats: list the battle .dat files, parse one, read a
comma separated list of section names.

They live here so the Ifrit CLI (Cli/ifrit_model.py), the editor and a mod build script (the
Cronos tool) all run the same code instead of each keeping its own copy.
"""
import io
import pathlib
import re
import sys
from contextlib import redirect_stdout

from FF8GameData.dat.monsteranalyser import MonsterAnalyser, GarbageFileError
from .common import SectionFileError
from .sectionfolder import SECTION_FILE_NAMES, SectionTools

# A canonical monster file name: the xlsx manager and the mod tools derive the monster id from it.
MONSTER_FILE_PATTERN = re.compile(r"c0m\d{3}\.dat", re.IGNORECASE)


def monster_id_of(dat_path) -> int:
    """c0m071.dat -> 71."""
    return int(re.search(r'\d{3}', pathlib.Path(dat_path).name).group())


def list_monster_files(folder, monster_id_list=None) -> list:
    """Every c0mNNN.dat of `folder`, sorted, optionally restricted to these monster ids."""
    folder = pathlib.Path(folder)
    return sorted(path for path in folder.iterdir()
                  if MONSTER_FILE_PATTERN.fullmatch(path.name)
                  and (monster_id_list is None or monster_id_of(path) in monster_id_list))


def load_monster(dat_path, tools: SectionTools, verbose: bool = False):
    """Parse and analyse one battle .dat. Returns the monster, or None for a garbage file.

    The analysers print a lot of detail as they go; `verbose` decides whether that reaches the
    console or is swallowed."""
    monster = MonsterAnalyser(tools.game_data)
    output = sys.stdout if verbose else io.StringIO()
    try:
        with redirect_stdout(output):
            monster.load_file_data(str(dat_path), tools.game_data)
            monster.analyse_loaded_data(tools.game_data, tools.decompiler)
    except GarbageFileError:
        print(f"{pathlib.Path(dat_path).name}: garbage file, skipped")
        return None
    return monster


def parse_section_names(value) -> list:
    """'ai,camera' -> ['ai', 'camera']. Empty/None means "every section". Raises SectionFileError
    naming the unknown ones, so a typo is reported instead of silently doing nothing."""
    if not value:
        return None
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in SECTION_FILE_NAMES]
    if unknown:
        raise SectionFileError(f"Unknown section file names {unknown}, "
                               f"expected some of {SECTION_FILE_NAMES}")
    return names
