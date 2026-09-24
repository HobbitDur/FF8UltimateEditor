"""Where the app's own files live, from source or from the release exe.

The release is a PyInstaller one-file exe: the code is unpacked into a temporary _MEIxxxx folder,
so `Path(__file__)` points there, not next to the exe where the release ships its folders
(Resources, FF8GameData, ExternalTools, ToolUpdate, Fujin, ...). APP_FOLDER is the exe's folder
in the release and the project root when run from source - the same layout in both cases.
"""
import pathlib
import sys

if getattr(sys, "frozen", False):
    APP_FOLDER = pathlib.Path(sys.executable).resolve().parent
else:
    APP_FOLDER = pathlib.Path(__file__).resolve().parent.parent


def app_path(*parts) -> pathlib.Path:
    """A path inside the app folder, e.g. app_path("ExternalTools", "VincentTim", "tim.exe")."""
    return APP_FOLDER.joinpath(*parts)
