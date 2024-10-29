import sys

from PyQt6.QtWidgets import QApplication

from ifritai import IfritAI

sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys.__excepthook__(exctype, value, traceback)
    #sys.exit(1)

if __name__ == '__main__':
    sys.excepthook = exception_hook

    app = QApplication.instance()
    if not app:  # sinon on crée une instance de QApplication
        app = QApplication(sys.argv)
        if app.style().objectName() == "windows11":
            app.setStyle("Fusion")
    main_window = IfritAI()
    sys.exit(app.exec())
