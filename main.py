import argparse
import sys

from PyQt6.QtWidgets import QApplication

from ff8ultimateeditorwidget import FF8UltimateEditorWidget
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys.__excepthook__(exctype, value, traceback)
    #sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser("FF8UltimateEditor")
    parser.add_argument("--resource_path", help="Resource path", type=str, default="Resources")
    parser.add_argument("--ff8gamedata_path", help="FF8GameData path", type=str, default="FF8GameData")
    args = parser.parse_args()

    sys.excepthook = exception_hook

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        if app.style().objectName() == "windows11":
            app.setStyle("Fusion")
    main_window = FF8UltimateEditorWidget(args.resource_path , args.ff8gamedata_path)
    main_window.show()
    sys.exit(app.exec())
