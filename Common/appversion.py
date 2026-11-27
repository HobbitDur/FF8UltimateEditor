"""Which build of the tool is running, shown in the window title so a user can tell which one they have.

The release workflow writes Common/_buildversion.py (not in git) just before PyInstaller runs:
the tag ("v5.2.0") for an official release, "canary <commit> (<date>)" for a continuous build.
From source there is no such file, so the version comes from git ("dev v5.1.0-430-g9387af3").
"""
import subprocess
import sys

from Common.apppaths import APP_FOLDER


def app_version() -> str:
    try:
        from Common._buildversion import BUILD_VERSION
        return BUILD_VERSION
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        return "unknown version"  # A build made without the release workflow
    try:
        described = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=APP_FOLDER,
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return "dev"
    return f"dev {described.stdout.strip()}" if described.returncode == 0 and described.stdout.strip() else "dev"
