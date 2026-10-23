"""Fujin's effect recorder (Tools/fxrecorder/fxrecorder.exe) is built from its source and never
kept in git. The Windows release ships the one its CI builds; run from source, FF8UltimateEditor
builds it when it starts, in the background, whenever it is missing or older than its source
(a fresh clone, a pull that changed it, FFNx's effect sources updated), with the local Visual
Studio C++ tools (Tools/fxrecorder/build.bat). The effect preview waits for it and says why when it
cannot be built. FFNx's effect sources (ExternalTools/FFNx/fx, the updater's FFNxEffects) are
built in when present: the effects' C++ ports and their parameters (Choreography's part tabs).
"""
import subprocess
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from Common.apppaths import app_path

FOLDER = app_path("Tools", "fxrecorder")
RECORDER = FOLDER / "fxrecorder.exe"
SOURCES = (FOLDER / "fxrecorder.cpp", FOLDER / "build.bat")
FFNX_EFFECTS = app_path("ExternalTools", "FFNx", "fx")     # FFNx's effect sources (the updater)
NO_COMPILER = 9009                  # build.bat's exit code when no Visual Studio C++ tools are found


def needs_build():
    """True when this is a source checkout on Windows whose recorder is missing or older than
    its source; never for the release (its recorder comes with it)."""
    if getattr(sys, "frozen", False) or sys.platform != "win32" or not SOURCES[0].is_file():
        return False
    try:
        built = RECORDER.stat().st_mtime
    except OSError:
        return True
    sources = list(SOURCES) + (list(FFNX_EFFECTS.iterdir()) if FFNX_EFFECTS.is_dir() else [])
    return any(source.is_file() and source.stat().st_mtime > built for source in sources)


class RecorderBuild(QObject):
    """The one background build of the recorder; changed is emitted when it starts and ends."""
    changed = pyqtSignal()
    _ended = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.building = False
        self.error = ""
        self._ended.connect(self._end)

    def start(self):
        if self.building or not needs_build():
            return False
        self.building, self.error = True, ""
        threading.Thread(target=self._run, name="fxrecorder build", daemon=True).start()
        self.changed.emit()
        return True

    def _run(self):
        try:
            run = subprocess.run(["cmd", "/c", str(FOLDER / "build.bat")], cwd=str(FOLDER), capture_output=True,
                                 text=True, errors="replace", timeout=600,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code, output = run.returncode, run.stdout + run.stderr
        except (OSError, subprocess.SubprocessError) as error:
            code, output = -1, str(error)
        self._ended.emit(code, output)          # queued to the main thread

    def _end(self, code, output):
        self.building = False
        if code == NO_COMPILER:
            self.error = ("it could not be built here: no Visual Studio C++ build tools (install Visual Studio "
                          "or its Build Tools with \"Desktop development with C++\", then restart)")
        elif code != 0 or not RECORDER.is_file():
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            details = [line for line in lines if "error" in line.lower()] or lines
            self.error = "its build failed: " + " / ".join(details[-3:])
        self.changed.emit()


_build = None


def recorder_build():
    global _build
    if _build is None:
        _build = RecorderBuild()
    return _build


def ensure_recorder():
    """At startup: build the recorder in the background if it needs it (True when started)."""
    return recorder_build().start()
