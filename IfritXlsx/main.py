import sys

from ifritmanager import IfritManager

sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)

if __name__ == "__main__":
    gui = True

    sys.excepthook = exception_hook

    ifrit_manager = IfritManager(gui)



