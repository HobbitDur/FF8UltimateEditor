import faulthandler
import sys
from PyQt6.QtWidgets import QApplication
from shumitranslator import ShumiTranslator

sys._excepthook = sys.excepthook


def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


if __name__ == '__main__':
    sys.excepthook = exception_hook
    faulthandler.enable()
    app = QApplication.instance()
    if not app:  # sinon on crée une instance de QApplication
        app = QApplication(sys.argv)
        if app.style().objectName() == "windows11":
            app.setStyle("Fusion")

    main_window = ShumiTranslator()
    main_window.show()
    sys.exit(app.exec())
