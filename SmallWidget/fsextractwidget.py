import os

from PyQt6.QtCore import QThread, pyqtSignal, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton, QFileDialog, QMessageBox, QApplication

from FF8GameData.fs.delingclimanager import DelingCliManager


class _ExtractWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, deling_manager: DelingCliManager, fs_path: str, dest_path: str):
        QThread.__init__(self)
        self._deling_manager = deling_manager
        self._fs_path = fs_path
        self._dest_path = dest_path

    def run(self):
        try:
            result = self._deling_manager.unpack(self._fs_path, self._dest_path, recursive=True)
            if result is not None and result.returncode != 0:
                self.finished_signal.emit(False, f"deling-cli exited with error code {result.returncode}.")
            else:
                self.finished_signal.emit(True, self._dest_path)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class FsExtractWidget(QPushButton):
    """Shared header button that extracts a .fs archive recursively using deling-cli."""

    def __init__(self, icon_path: str, game_data_folder: str = "FF8GameData"):
        QPushButton.__init__(self)
        self._deling_manager = DelingCliManager(os.path.join(game_data_folder, "fs", "DelingCli"))
        self._worker = None

        self.setIcon(QIcon(os.path.join(icon_path, "uncompress.png")))
        self.setIconSize(QSize(30, 30))
        self.setText("Extract .fs")
        self.setToolTip("Select a .fs archive and extract its content recursively (deling-cli)")
        self.clicked.connect(self._on_click)

    def _on_click(self):
        fs_path, _ = QFileDialog.getOpenFileName(
            self, "Select a .fs archive to extract", "", "FS archives (*.fs);;All files (*)")
        if not fs_path:
            return

        dest_path = QFileDialog.getExistingDirectory(
            self, "Select destination folder", os.path.dirname(fs_path))
        if not dest_path:
            return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._worker = _ExtractWorker(self._deling_manager, fs_path, dest_path)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, success: bool, message: str):
        QApplication.restoreOverrideCursor()
        self.setEnabled(True)
        if success:
            QMessageBox.information(self, "Extraction complete", f"The archive was extracted to:\n{message}")
        else:
            QMessageBox.critical(self, "Extraction failed", f"Could not extract the archive:\n{message}")
        self._worker = None
