"""The release exe must find its data files next to itself, not next to its code.

The release is a PyInstaller one-file exe: the code runs from a temporary _MEIxxxx unpack folder,
so a path built from `__file__` points there, where none of the shipped folders (Resources,
FF8GameData/Resources, ExternalTools, ToolUpdate, ...) exist. It works from source and only breaks
in the release - "No such file or directory" on a fresh download. Shipped code goes through
Common.apppaths (app_path) or FF8GameData.packagepath instead.
"""
import io
import pathlib
import subprocess
import tokenize

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Not part of the release: tests, dev/research scripts, and the two modules that resolve the
# frozen case themselves.
NOT_SHIPPED = ("tests/", "pipeline/", "GFtoDat/", "IDA/")
ALLOWED = {"conftest.py", "Common/apppaths.py", "FF8GameData/packagepath.py"}


def _shipped_python_files():
    listing = subprocess.run(["git", "ls-files", "*.py"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    for name in listing:
        if name in ALLOWED or name.startswith(NOT_SHIPPED) or "ResearchScript" in name:
            continue
        if pathlib.PurePosixPath(name).name.startswith("generate_"):
            continue
        yield name


def test_shipped_code_never_builds_a_path_from_file():
    offenders = []
    for name in _shipped_python_files():
        source = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):  # code only, not comments
            if token.type == tokenize.NAME and token.string == "__file__":
                offenders.append(f"{name}:{token.start[0]}")
    assert not offenders, ("__file__ is a temporary unpack folder in the release exe; use "
                           "Common.apppaths.app_path or FF8GameData.packagepath: " + ", ".join(offenders))
