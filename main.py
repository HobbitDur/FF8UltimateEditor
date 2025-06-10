import sys

from PyQt6.QtWidgets import QApplication

from ff8ultimateeditorwidget import FF8UltimateEditorWidget
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys.__excepthook__(exctype, value, traceback)
    #sys.exit(1)

if __name__ == '__main__':
    sys.excepthook = exception_hook

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        if app.style().objectName() == "windows11":
            app.setStyle("Fusion")
    main_window = FF8UltimateEditorWidget()
    main_window.show()
    sys.exit(app.exec())
