"""Fujin's effect recorder (Tools/fxrecorder/fxrecorder.exe) is built from its source and never
kept in git. The Windows release ships the one its CI builds; run from source, FF8UltimateEditor
builds it when it starts, in the background, whenever it is missing or older than its source
(a fresh clone, a pull that changed it, FFNx's effect sources updated), with the local Visual
Studio C++ tools (Tools/fxrecorder/build.bat). The effect preview waits for it and says why when it
cannot be built. FFNx's effect sources (ExternalTools/FFNx/fx, the updater's FFNxEffects) are
built in when present: the effects' C++ ports and their parameters (Choreography's part tabs). The
same build makes FujinEffects.dll (Tools/fxhost), which Save ships with the effects' programs.
"""
import subprocess
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from Common.apppaths import app_path

FOLDER = app_path("Tools", "fxrecorder")
RECORDER = FOLDER / "fxrecorder.exe"
# the effect runtime both run (Tools/fxhost): the recorder for program=, FujinEffects.dll in the game
# (the recorder's build.bat builds it too, with FFNx's effect sources)
HOST_FOLDER = app_path("Tools", "fxhost")
HOST_DLL = HOST_FOLDER / "FujinEffects.dll"
SOURCES = (FOLDER / "fxrecorder.cpp", FOLDER / "build.bat", HOST_FOLDER / "fxprogram.h", HOST_FOLDER / "fxhost.cpp",
           HOST_FOLDER / "build.bat")
FFNX_EFFECTS = app_path("ExternalTools", "FFNx", "fx")     # FFNx's effect sources (the updater)
NO_COMPILER = 9009                  # build.bat's exit code when no Visual Studio C++ tools are found
BUILD_TIMEOUT = 1200                # seconds


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


def _source_count():
    """How many files the compiler goes through: the module list build.bat wrote, and the recorder itself."""
    try:
        return 1 + len((FOLDER / "obj" / "lab.rsp").read_text(errors="replace").splitlines())
    except OSError:
        return 0


class RecorderBuild(QObject):
    """The one background build of the recorder; changed is emitted when it starts and ends."""
    changed = pyqtSignal()
    progress = pyqtSignal()                 # another file compiled (done, total, stage)
    _ended = pyqtSignal(int, str)
    _compiled = pyqtSignal(int, int, str)

    def __init__(self):
        super().__init__()
        self.building = False
        self.error = ""
        self.output = ""                    # the last build's log
        self.done, self.total, self.stage = 0, 0, "the effect recorder"
        self._ended.connect(self._end)
        self._compiled.connect(self._count)

    def start(self):
        if self.building or not needs_build():
            return False
        self.building, self.error = True, ""
        self.done, self.total, self.stage = 0, 0, "the effect recorder"
        threading.Thread(target=self._run, name="fxrecorder build", daemon=True).start()
        self.changed.emit()
        return True

    def _run(self):
        lines = []
        try:
            process = subprocess.Popen(["cmd", "/c", str(FOLDER / "build.bat")], cwd=str(FOLDER), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            limit = threading.Timer(BUILD_TIMEOUT, process.kill)
            limit.start()
            done, stage = 0, "the effect recorder"
            for line in process.stdout:         # the compiler says each file it starts
                lines.append(line)
                name = line.strip().lower()
                if name.endswith(".cpp"):
                    done += 1
                    self._compiled.emit(done, _source_count(), stage)
                elif name.startswith("build fxrecorder.exe exit"):
                    done, stage = 0, "the game's effect DLL"
            code = process.wait()
            limit.cancel()
            output = "".join(lines)
        except (OSError, subprocess.SubprocessError) as error:
            code, output = -1, "".join(lines) + str(error)
        self._ended.emit(code, output)          # queued to the main thread

    def _count(self, done, total, stage):
        self.done, self.total, self.stage = done, max(done, total), stage
        self.progress.emit()

    def _end(self, code, output):
        self.building = False
        self.output = output
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
