from PyQt6.QtWidgets import QPushButton, QMessageBox

from Common.fileregistry import FileRegistry


class OpenedFilesWidget(QPushButton):
    """Header button showing which FF8 files are currently opened and shared by the tools."""

    def __init__(self, registry: FileRegistry):
        QPushButton.__init__(self)
        self.registry = registry
        self.setToolTip("The FF8 files currently opened, shared by all the tools")
        self.clicked.connect(self._show_opened_files)
        self.registry.file_changed.connect(self._update_text)
        self._update_text()

    def _update_text(self):
        self.setText(f"Opened files ({len(self.registry.paths)})")

    def _show_opened_files(self):
        if self.registry.paths:
            text = "\n".join(f"{file_name}: {file_path}"
                             for file_name, file_path in sorted(self.registry.paths.items()))
        else:
            text = ("No file opened yet.\n"
                    "Open one from any tool: every tool using that file will open it too.")
        QMessageBox.information(self, "Opened files", text)
