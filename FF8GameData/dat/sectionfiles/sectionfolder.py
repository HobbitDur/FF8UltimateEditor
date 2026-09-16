"""One folder of section files per .dat: export a .dat's sections to it, apply it onto a .dat.

    c0m071/
      skeleton.bin  geometry.bin  animation.bin  dynamic_texture.xml  anim_seq.xml  camera.xml
      info_stat.json  battle_text.txt  ai.md  sound.bin  sound_bank.bin
      texture_00.tim  texture_01.tim ...

Every section is a file of the folder, textures included (one per texture) - so selecting all the
files of a folder selects every section, with nothing hidden in a sub-folder.

Applying replaces each section that has a file and keeps every other section of the .dat as it
is: a folder can hold only the sections a mod changes. The same folder can be applied onto a fresh
vanilla .dat to rebuild the modded one.

Two kinds of section file:
- "bytes" files convert to and from the exact section bytes (raw .bin, TIM textures, camera,
  dynamic texture). Applying them swaps the section bytes in (MonsterAnalyser.replace_sections_bytes).
- "data" files read and write the parsed data (sequences, stats, battle texts, AI).
"""
import pathlib
from dataclasses import dataclass
from typing import Callable, Optional

from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from . import rawfile, texturefile, camerafile, dynamictexturefile, animseqfile, infostatfile, battletextfile, aifile
from .common import SectionFileError


@dataclass
class SectionFile:
    name: str               # Name of the section file, used to pick sections (--sections ai,camera)
    path_name: str          # File name inside the section folder (the first one, for the textures)
    section: str            # Building block it lives in (see MonsterAnalyser.SECTION_INDEX_BY_ENTITY)
    # "bytes" files: section bytes <-> file
    write_bytes: Optional[Callable] = None
    read_bytes: Optional[Callable] = None
    # "data" files: parsed data <-> file
    export_data: Optional[Callable] = None
    apply_data: Optional[Callable] = None
    # A section written as SEVERAL files (the textures: one TIM per texture) carries the glob that
    # matches them; its codec is then given the folder, not one file path.
    file_pattern: str = ""

    def is_bytes_file(self) -> bool:
        return self.write_bytes is not None

    def is_multi_file(self) -> bool:
        return bool(self.file_pattern)

    def path_in(self, folder):
        """Where this section file lives in `folder` - the folder itself when it is several files
        (their codec globs them)."""
        return pathlib.Path(folder) if self.is_multi_file() else pathlib.Path(folder) / self.path_name

    def exists_in(self, folder) -> bool:
        folder = pathlib.Path(folder)
        if self.is_multi_file():
            return any(folder.glob(self.file_pattern))
        return (folder / self.path_name).exists()


# In apply order. The AI comes last: it is compiled against the stats and battle texts.
SECTION_FILES = [
    SectionFile("skeleton", "skeleton.bin", "skeleton", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("geometry", "geometry.bin", "geometry", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("animation", "animation.bin", "animation", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("extra_animation", "extra_animation.bin", "extra_animation", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("dynamic_texture", "dynamic_texture.xml", "dynamic_texture",
                dynamictexturefile.write_section_bytes, dynamictexturefile.read_section_bytes),
    SectionFile("camera", "camera.xml", "camera", camerafile.write_section_bytes, camerafile.read_section_bytes),
    SectionFile("sound", "sound.bin", "sound", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("sound_bank", "sound_bank.bin", "sound_bank", rawfile.write_section_bytes, rawfile.read_section_bytes),
    SectionFile("texture", texturefile.FILE_PREFIX + "00.tim", "texture",
                texturefile.write_section_bytes, texturefile.read_section_bytes,
                file_pattern=texturefile.FILE_PATTERN),
    SectionFile("anim_seq", "anim_seq.xml", "anim_seq", export_data=animseqfile.export_section, apply_data=animseqfile.apply_section),
    SectionFile("info_stat", "info_stat.json", "info_stat", export_data=infostatfile.export_section, apply_data=infostatfile.apply_section),
    SectionFile("battle_text", "battle_text.txt", "battle_script", export_data=battletextfile.export_section, apply_data=battletextfile.apply_section),
    SectionFile("ai", "ai.md", "battle_script", export_data=aifile.export_section, apply_data=aifile.apply_section),
]
SECTION_FILE_NAMES = [section_file.name for section_file in SECTION_FILES]


class SectionTools:
    """What the section files need besides the enemy: the game data and the AI (de)compiler."""

    def __init__(self, game_data, compiler=None, decompiler=None):
        from Ifrit.IfritAI.AICompiler.AICompiler import AICompiler
        from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler

        self.game_data = game_data
        empty_enemy = MonsterAnalyser(game_data)
        if compiler is None:
            compiler = AICompiler(game_data, empty_enemy.battle_script_data['battle_text'], empty_enemy.info_stat_data)
        if decompiler is None:
            decompiler = AIDecompiler(game_data, empty_enemy.battle_script_data['battle_text'], empty_enemy.info_stat_data)
        self.compiler = compiler
        self.decompiler = decompiler


def folder_name_for(dat_path) -> str:
    """c0m071.dat -> c0m071 (the name of its section folder)."""
    return pathlib.Path(dat_path).stem


def section_files_for(enemy: MonsterAnalyser, names=None) -> list:
    """The section files this enemy's file type has, optionally restricted to `names`, in apply order."""
    if names is not None:
        unknown = [name for name in names if name not in SECTION_FILE_NAMES]
        if unknown:
            raise SectionFileError(f"Unknown section file names {unknown}, expected some of {SECTION_FILE_NAMES}")
    layout = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[enemy.entity_type]
    return [section_file for section_file in SECTION_FILES
            if section_file.section in layout and (names is None or section_file.name in names)]


def _comparable_content(enemy: MonsterAnalyser, section_file: SectionFile) -> bytes:
    """Bytes that change exactly when this section file's content changes. The battle texts and
    the AI share one section, so they are compared on their own part of it."""
    if section_file.name == "battle_text":
        return b"".join(bytes(text.get_data_hex()) for text in enemy.battle_script_data['battle_text'])
    if section_file.name == "ai":
        ai_bytes = bytearray()
        for ai_section in enemy.battle_script_data['ai_data']:
            for command in ai_section.get('command', []):
                ai_bytes.append(command.get_id())
                ai_bytes.extend(command.get_op_code())
            ai_bytes.extend(b"|")  # Keeps the sub-section boundaries in the comparison
        return bytes(ai_bytes)
    section_index = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[enemy.entity_type][section_file.section]
    return bytes(enemy.section_raw_data[section_index])


def export_sections(enemy: MonsterAnalyser, folder, tools: SectionTools, names=None, reference_enemy: MonsterAnalyser = None) -> list:
    """Write the enemy's sections as section files into `folder`. Returns the names written.

    names: only these section files (default: every section the file type has).
    reference_enemy: only write the section files whose content differs from this one (typically
    the vanilla .dat), so the folder holds just what a mod changes."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    enemy.get_bytes(tools.game_data)  # Every section_raw_data entry now reflects the live model
    if reference_enemy is not None:
        reference_enemy.get_bytes(tools.game_data)

    written = []
    for section_file in section_files_for(enemy, names):
        if reference_enemy is not None and _comparable_content(enemy, section_file) == _comparable_content(reference_enemy, section_file):
            continue
        path = section_file.path_in(folder)
        if section_file.is_bytes_file():
            section_index = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[enemy.entity_type][section_file.section]
            section_file.write_bytes(enemy.section_raw_data[section_index], path)
        else:
            section_file.export_data(enemy, path, tools)
        written.append(section_file.name)
    return written


def apply_sections(enemy: MonsterAnalyser, folder, tools: SectionTools, names=None) -> list:
    """Apply every section file present in `folder` onto the enemy. Returns the names applied.

    names: only consider these section files (default: all). A section without a file is kept."""
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        raise SectionFileError(f"{folder}: section folder not found")
    paths = {section_file.name: section_file.path_in(folder)
             for section_file in section_files_for(enemy, names)
             if section_file.exists_in(folder)}
    return apply_section_files(enemy, paths, tools)


def apply_section_files(enemy: MonsterAnalyser, paths: dict, tools: SectionTools) -> list:
    """Apply chosen section files onto the enemy, each given by its own path:
    {'ai': 'somewhere/ai.md', 'texture': 'somewhere/texture'}. The files need not live in the same
    folder. Returns the names applied, in apply order (the AI last, see SECTION_FILES)."""
    layout = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[enemy.entity_type]
    unknown = [name for name in paths if name not in layout_names(enemy)]
    if unknown:
        raise SectionFileError(f"This file has no section {unknown} (its type is {enemy.entity_type.name})")
    chosen = [section_file for section_file in section_files_for(enemy) if section_file.name in paths]

    # All the bytes files first, swapped in with a single re-serialisation of the file
    new_section_bytes = {}
    for section_file in chosen:
        if section_file.is_bytes_file():
            new_section_bytes[layout[section_file.section]] = section_file.read_bytes(pathlib.Path(paths[section_file.name]))
    if new_section_bytes:
        enemy.replace_sections_bytes(new_section_bytes, tools.game_data, tools.decompiler)

    for section_file in chosen:
        if not section_file.is_bytes_file():
            section_file.apply_data(enemy, pathlib.Path(paths[section_file.name]), tools)
    return [section_file.name for section_file in chosen]


def layout_names(enemy: MonsterAnalyser) -> list:
    """The section file names this enemy's file type has."""
    return [section_file.name for section_file in section_files_for(enemy)]


def section_file_for_path(path) -> SectionFile:
    """The section file a chosen path is, recognised by its name (ai.md, camera.xml,
    texture_00.tim...), or None."""
    path = pathlib.Path(path)
    for section_file in SECTION_FILES:
        if section_file.is_multi_file():
            if path.match(section_file.file_pattern):
                return section_file
        elif section_file.path_name == path.name:
            return section_file
    return None
