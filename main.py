import argparse
import os
import pathlib
import sys

from PyQt6.QtWidgets import QApplication

# Where the app itself lives. Everything it needs (Resources, FF8GameData, ExternalTools) sits
# next to this file, so it can be started from anywhere - `python path/to/main.py`, a shortcut, or
# another project holding it as a submodule - and not only from its own folder.
APP_FOLDER = pathlib.Path(__file__).resolve().parent

from ff8ultimateeditorwidget import FF8UltimateEditorWidget
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys.__excepthook__(exctype, value, traceback)
    #sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser("FF8UltimateEditor")
    parser.add_argument("--resource_path", help="Resource path", type=str, default=str(APP_FOLDER / "Resources"))
    parser.add_argument("--ff8gamedata_path", help="FF8GameData path", type=str, default=str(APP_FOLDER / "FF8GameData"))
    args = parser.parse_args()

    # A path given on the command line is relative to where the user is; resolve it before moving
    # to the app folder, which the tools' own relative paths (icons, external tools) expect.
    resource_path = str(pathlib.Path(args.resource_path).resolve())
    ff8gamedata_path = str(pathlib.Path(args.ff8gamedata_path).resolve())
    os.chdir(APP_FOLDER)

    sys.excepthook = exception_hook

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        if app.style().objectName() == "windows11":
            app.setStyle("Fusion")
    main_window = FF8UltimateEditorWidget(resource_path, ff8gamedata_path)
    main_window.show()
    sys.exit(app.exec())
