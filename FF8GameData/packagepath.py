"""Where the FF8GameData folder (and its Resources) lives, from source or from the release exe.

The release is a PyInstaller one-file exe: the code is unpacked into a temporary _MEIxxxx folder,
so a path built from `__file__` points there, where no Resources/ exist. The release ships
FF8GameData/Resources next to the exe instead, which is what this resolves to when frozen.
"""
import pathlib
import sys

if getattr(sys, "frozen", False):
    FF8GAMEDATA_FOLDER = pathlib.Path(sys.executable).resolve().parent / "FF8GameData"
else:
    FF8GAMEDATA_FOLDER = pathlib.Path(__file__).resolve().parent

RESOURCES_JSON_FOLDER = FF8GAMEDATA_FOLDER / "Resources" / "json"
