import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import psutil


def is_running(exe_path: Path) -> bool:
    """Whether the exe at exe_path runs. Only this installation's exe counts: another copy of the
    tool open elsewhere does not lock these files. process_iter with attrs skips the processes
    that end while being listed - the editor's own two processes are ending right now - where
    asking a gone process its name raised NoSuchProcess and crashed the Patcher before the copy.
    A process whose path cannot be read (AccessDenied) counts if it has the exe's name."""
    target = os.path.normcase(str(exe_path.resolve()))
    for process in psutil.process_iter(["name", "exe"]):
        path = process.info["exe"]
        if path:
            if os.path.normcase(path) == target:
                return True
        elif process.info["name"] == exe_path.name:
            return True
    return False


def wait_for_exit(exe_path: Path, timeout=60):
    """
    Wait until the exe at exe_path is no longer running.
    Returns True if exited within timeout, False otherwise.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_running(exe_path):
            return True
        time.sleep(0.5)
    return False


def notify(text, error=True):
    """Tell the user, and the log. The Windows Patcher is built without a console (--noconsole):
    there is no stdin, so input() crashes it ("lost sys.stdin") - a message box is the only way."""
    print(text)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "FF8UltimateEditor update", 0x10 if error else 0x40)


def main():
    temp_dir = Path("SelfUpdate")
    target_dir = Path(".")
    exe_name = "FF8UltimateEditor.exe" if sys.platform == "win32" else "FF8UltimateEditor"
    patcher_exe = "Patcher.exe" if sys.platform == "win32" else "Patcher"  # Name of the patcher executable to exclude

    # Wait for the main application to fully exit
    print(f"Waiting for {exe_name} to close...")
    if not wait_for_exit(target_dir / exe_name):
        notify(f"{exe_name} is still running. Update aborted.\n\n"
               "Close it, then use Self update again.")
        return

    try:
        # Create ignore function that excludes the patcher executable
        def ignore_func(dir, names):
            return {name for name in names if name == patcher_exe}

        # Use copytree with the ignore function
        if temp_dir.exists():
            shutil.copytree(temp_dir, target_dir, dirs_exist_ok=True, ignore=ignore_func)
            print(f"Copied all files from {temp_dir} to {target_dir} except {patcher_exe}")
        else:
            print(f"Source directory {temp_dir} does not exist")

    except Exception as e:
        notify(f"Update failed: {e}")
    else:
        # Launch the updated application independently
        exe_path = (target_dir / exe_name).resolve()
        try:
            subprocess.Popen([str(exe_path)], close_fds=True)
            print(f"{exe_name} launched successfully.")
        except OSError as e:
            # The update is in place, only the restart failed. WinError 4551: Windows' application
            # control (Smart App Control or an administrator policy) blocks a program it doesn't
            # know yet - a freshly downloaded build has no reputation.
            notify(f"The update is installed, but Windows refused to start {exe_name}:\n{e}\n\n"
                   f"Start it yourself:\n{exe_path}\n\n"
                   "If Windows blocks it again, its application control (Smart App Control, in Windows "
                   "Security > App & browser control) is refusing this new build.")
    # Clean up temporary folder
    shutil.rmtree(temp_dir, ignore_errors=True)


def setup_logging():
    # Create logs directory
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Log file with timestamp
    log_file = f"logs/Patcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Redirect stdout and stderr to file, line buffered: a Patcher that dies midway still leaves
    # the steps it went through (block buffered, its log was empty)
    sys.stdout = open(log_file, 'w', buffering=1)
    sys.stderr = sys.stdout



if __name__ == "__main__":
    # Call this at the start of your script
    if getattr(sys, 'frozen', False):  # Check if running as exe
        setup_logging()
    main()