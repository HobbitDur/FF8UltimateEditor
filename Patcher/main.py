import os
import shutil
import subprocess
import time
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
    temp_dir = Path("SelfUpdate")
    target_dir = Path(".")
    exe_name = "FF8UltimateEditor.exe"
    patcher_exe = "Patcher.exe"  # Name of the patcher executable to exclude

    # Wait for the main application to fully exit
    print(f"Waiting for {exe_name} to close...")
    if not wait_for_exit(exe_name):
        print(f"{exe_name} is still running. Update aborted.")
        input("Press Enter to exit...")
        return

    try:
        # Copy all files from temp_dir to target_dir, excluding the patcher
        for item in temp_dir.glob("*"):
            # Skip the patcher executable
            if item.name == patcher_exe:
                print(f"Skipping {patcher_exe} (protected file)")
                continue

            target = target_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    os.remove(target)
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

        # Launch the updated application independently
        subprocess.Popen([str(target_dir / exe_name)], close_fds=True)
        print(f"{exe_name} launched successfully.")

    except Exception as e:
        print(f"Update failed: {e}")
        input("Press Enter to exit...")

    # Clean up temporary folder
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()