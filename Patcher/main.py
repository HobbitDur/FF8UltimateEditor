import os
import shutil
import sys
import time
from pathlib import Path


def main():
    # Paths configuration
    temp_dir = Path("ToolDownload")  # Where new version was extracted
    target_dir = Path(".")  # Where main app lives
    exe_name = "ff8ultimateeditor.exe"  # Your main executable name

    # Wait a moment to ensure main app has closed
    time.sleep(2)

    try:
        # Copy all files from temp to target
        for item in temp_dir.glob("*"):
            target = target_dir / item.name

            # Skip the updater itself if it's in the temp folder
            if item.name == "updater.exe":
                continue

            # Remove existing file/dir if it exists
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    os.remove(target)

            # Copy new file/dir
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

        # Launch the updated application
        os.startfile(target_dir / exe_name)

    except Exception as e:
        print(f"Update failed: {e}")
        input("Press Enter to exit...")

    # Clean up
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()