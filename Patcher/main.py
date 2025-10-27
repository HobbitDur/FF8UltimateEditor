import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import psutil


def wait_for_exit(exe_name, timeout=30):
    """
    Wait until the process exe_name is no longer running.
    Returns True if exited within timeout, False otherwise.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        running = any(p.name() == exe_name for p in psutil.process_iter())
        if not running:
            return True
        time.sleep(0.5)
    return False


def main():
    temp_dir = Path("..") / "SelfUpdate"
    target_dir = Path("..")
    exe_name = "FF8UltimateEditor.exe"
    patcher_exe = "Patcher.exe"  # Name of the patcher executable to exclude

    # Wait for the main application to fully exit
    print(f"Waiting for {exe_name} to close...")
    if not wait_for_exit(exe_name):
        print(f"{exe_name} is still running. Update aborted.")
        input("Press Enter to exit...")
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

        # Launch the updated application independently
        subprocess.Popen([str(target_dir / exe_name)], close_fds=True)
        print(f"{exe_name} launched successfully.")

    except Exception as e:
        print(f"Update failed: {e}")
        input("Press Enter to exit...")
    # Clean up temporary folder
    shutil.rmtree(temp_dir, ignore_errors=True)


def setup_logging():
    # Create logs directory
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Log file with timestamp
    log_file = f"logs/FF8UltimateEditor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Redirect stdout and stderr to file
    sys.stdout = open(log_file, 'w')
    sys.stderr = sys.stdout



if __name__ == "__main__":
    print("Current directory: {}".format(os.getcwd()))
    # Call this at the start of your script
    if getattr(sys, 'frozen', False):  # Check if running as exe
        setup_logging()
    main()