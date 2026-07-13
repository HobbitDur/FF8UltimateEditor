#!/usr/bin/env python3
"""Local smoke test you run by hand: download the canary (continuous pre-release) GUI build
from GitHub, unzip it, launch FF8UltimateEditor.exe, and verify it starts without crashing.

This is deliberately NOT a pytest test (no ``test_`` prefix): it needs the network and a real
Windows desktop, so it must never run in CI. It reuses the tool's own ``ToolDownloader`` so it
exercises the exact same download + unzip path the app uses to update itself.

Run it yourself (use the project venv so requests/PyQt are available):

    .venv/Scripts/python.exe tests/ToolUpdate/canary_launch_check.py            # canary build
    .venv/Scripts/python.exe tests/ToolUpdate/canary_launch_check.py --stable   # latest stable instead
    .venv/Scripts/python.exe tests/ToolUpdate/canary_launch_check.py --timeout 45  # watch longer
    .venv/Scripts/python.exe tests/ToolUpdate/canary_launch_check.py --keep-dir # don't delete the download
    .venv/Scripts/python.exe tests/ToolUpdate/canary_launch_check.py --from-dir path/to/build  # launch an
                                                                            # existing extracted build, no download

The build is windowed (PyInstaller --noconsole): a crash on startup pops a modal traceback dialog
instead of exiting, so a naive "is it still running?" check would wrongly pass. This checks three
crash signals: a non-zero exit, a Python traceback in the captured output, or a startup error dialog.

Exit code 0 = the exe launched and reached a healthy running state (or exited 0, no traceback).
Exit code 1 = download/unzip failed, the exe was missing, or it crashed on startup.
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ToolUpdate.toolupdate import ToolDownloader

EXE_NAME = "FF8UltimateEditor.exe"
SELF_UPDATE_DIR = "SelfUpdate"  # ToolDownloader.download_self extracts the GUI zip here


def _print_progress(downloaded, total):
    # Only emit when the reported step changes, so a piped/non-TTY run doesn't get one line per chunk.
    if total and total > 0:
        step, unit = downloaded * 100 // total, "%"
    else:
        step, unit = downloaded // (1024 * 1024), " MiB"  # fall back to whole MiB when size is unknown
    if step == getattr(_print_progress, "_last_step", None):
        return
    _print_progress._last_step = step
    if unit == "%":
        bar = "#" * (step // 4) + "-" * (25 - step // 4)
        print(f"\r  downloading [{bar}] {step:3d}%  ({downloaded // 1024} KiB)", end="", flush=True)
    else:
        print(f"\r  downloading {step}{unit}", end="", flush=True)


def download_build(canary: bool) -> pathlib.Path:
    """Download and unzip the release into an isolated temp dir, return the path to the exe.

    Runs ToolDownloader inside a throwaway working directory so it never touches the repo:
    download_self() reads ``ToolUpdate/list.json`` and writes ``SelfUpdate/`` relative to cwd.
    """
    work_dir = pathlib.Path(tempfile.mkdtemp(prefix="ff8ue_canary_"))
    (work_dir / "ToolUpdate").mkdir()
    shutil.copy(PROJECT_ROOT / "ToolUpdate" / "list.json", work_dir / "ToolUpdate" / "list.json")

    kind = "canary (continuous pre-release)" if canary else "latest stable release"
    print(f"==> Fetching {kind} of FF8UltimateEditor from GitHub")
    previous_cwd = os.getcwd()
    os.chdir(work_dir)
    try:
        ToolDownloader().download_self(download_update_func=_print_progress, canary=canary)
    finally:
        os.chdir(previous_cwd)
    print()  # end the progress line
    print(f"==> Extracted build to {work_dir / SELF_UPDATE_DIR}")
    return _require_exe(work_dir / SELF_UPDATE_DIR)


def _require_exe(build_dir: pathlib.Path) -> pathlib.Path:
    exe_path = build_dir / EXE_NAME
    if not exe_path.is_file():
        found = sorted(p.name for p in build_dir.glob("*")) if build_dir.exists() else ["<dir missing>"]
        raise FileNotFoundError(f"{EXE_NAME} not found in {build_dir}. Top-level entries: {found}")
    return exe_path


def _descendant_pids(root_pid: int):
    """The set of {root_pid} plus every process descended from it (Win32 only).

    The build is PyInstaller --onefile: the exe we launch is a bootloader that spawns the real app
    as a child, and the crash dialog belongs to that child, not to the pid we started. We also must
    scope to descendants so a leftover dialog from an earlier run can't cause a false failure.
    """
    if sys.platform != "win32":
        return {root_pid}
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    parent_of = {}
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(entry)
    ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
    while ok:
        parent_of[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    kernel32.CloseHandle(snapshot)

    descendants = {root_pid}
    changed = True
    while changed:  # transitively pull in children until the set stops growing
        changed = False
        for pid, parent in parent_of.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return descendants


def _find_crash_dialogs(pids):
    """Return [(title, error_text)] for PyInstaller crash dialogs owned by any pid in pids.

    The windowed bootloader shows the startup traceback in a standard dialog box (class #32770);
    its child controls carry the actual error message, which we harvest to report instead of the
    (empty, because --noconsole discards stderr) captured output.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    dialogs = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _on_window(hwnd, _lparam):
        win_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
        if win_pid.value not in pids or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value != "#32770":  # standard dialog box == PyInstaller fatal-error window
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        control_texts = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _on_control(child, _l):
            buffer = ctypes.create_unicode_buffer(2048)
            user32.GetWindowTextW(child, buffer, 2048)
            text = buffer.value.strip()
            if text and text.lower() not in ("close", "ok", "cancel", "&close", "&ok"):
                control_texts.append(text)
            return True

        user32.EnumChildWindows(hwnd, _on_control, 0)
        dialogs.append((title.value or "<untitled dialog>", " ".join(control_texts)))
        return True

    user32.EnumWindows(_on_window, 0)
    return dialogs


def _find_app_windows(pids):
    """Titles of visible, captioned, non-dialog top-level windows owned by any pid in pids.

    A healthy launch reaches this: the Qt main window (class != #32770, with a caption). Seeing one
    means the app got past startup, so we can pass early instead of waiting out the whole timeout.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _on_window(hwnd, _lparam):
        win_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
        if win_pid.value not in pids or not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetParent(hwnd):  # skip child/owned windows, keep genuine top-level ones
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "#32770":  # that's a dialog, handled by _find_crash_dialogs
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if title.value.strip():
            titles.append(title.value.strip())
        return True

    user32.EnumWindows(_on_window, 0)
    return titles


def launch_and_check(exe_path: pathlib.Path, timeout_seconds: float) -> bool:
    """Launch the exe and watch it. Returns True if it started without crashing.

    The build is PyInstaller --onefile --noconsole: the bootloader first unpacks a ~100 MB bundle
    (several seconds) before the real app starts, and a startup crash surfaces as a modal error
    dialog rather than a non-zero exit. So we watch up to timeout_seconds, exiting early on either
    the crash dialog (fail) or the main window appearing (pass).
    """
    if sys.platform != "win32":
        print(f"!! Skipping launch: {EXE_NAME} is a Windows executable and this is {sys.platform}.")
        print("   (The download + unzip step above still ran and passed.)")
        return True

    print(f"==> Launching {EXE_NAME} (watching up to {timeout_seconds:g}s for the window or a crash)")
    proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))  # needs its sibling folders as cwd
    crash_dialogs, app_windows = [], []
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            pids = _descendant_pids(proc.pid)
            crash_dialogs = _find_crash_dialogs(pids)
            if crash_dialogs:  # startup error box -> it won't recover
                break
            app_windows = _find_app_windows(pids)
            if app_windows:  # real window is up -> healthy launch
                break
            time.sleep(0.25)
        code = proc.poll()
    finally:
        _terminate_tree(proc)  # kill the whole tree (the onefile child + any error dialog)

    if crash_dialogs:
        print(f"!! FAIL: {EXE_NAME} crashed on startup ({crash_dialogs[0][0]}):")
        print(f"     {crash_dialogs[0][1] or '<no message text>'}")
        return False
    if code not in (None, 0):
        print(f"!! FAIL: {EXE_NAME} exited with code {code} (0x{code & 0xFFFFFFFF:08X}) while launching.")
        return False
    if app_windows:
        print(f"==> OK: main window opened ({app_windows[0]!r}), no startup crash.")
    elif code == 0:
        print("==> OK: process exited cleanly with code 0.")
    else:
        print(f"==> OK: still running after {timeout_seconds:g}s with no crash (window not detected).")
    return True


def _terminate_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # taskkill /T kills the onefile child too; plain terminate() would orphan it (and its dialog).
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the canary GUI build and check it launches.")
    parser.add_argument("--stable", action="store_true",
                        help="Use the latest stable release instead of the canary pre-release.")
    parser.add_argument("--timeout", type=float, default=30.0, metavar="SECONDS",
                        help="Max seconds to watch for the window or a crash dialog (default: 30). "
                             "The onefile bootloader needs ~7s to unpack before the app even starts.")
    parser.add_argument("--from-dir", metavar="DIR",
                        help="Skip the download and launch-check an already-extracted build in DIR.")
    parser.add_argument("--keep-dir", action="store_true",
                        help="Don't delete the downloaded build afterwards (prints its path).")
    args = parser.parse_args()

    temp_dir = None
    try:
        if args.from_dir:
            exe_path = _require_exe(pathlib.Path(args.from_dir))
        else:
            exe_path = download_build(canary=not args.stable)
            temp_dir = exe_path.parents[1]  # the temp dir created in download_build
        ok = launch_and_check(exe_path, args.timeout)
    except Exception as error:  # noqa: BLE001 - top-level smoke-test runner, report and exit
        print(f"!! FAIL: {type(error).__name__}: {error}")
        ok = False
    finally:
        if temp_dir and temp_dir.exists():
            if args.keep_dir:
                print(f"==> Kept downloaded build at {temp_dir}")
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
