import os

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QFileDialog

from Common.fileregistry import FileRegistry


class FileBarWidget(QWidget):
    """The open/save buttons at the top of every tool.

    The tool says which FF8 file it edits and connects the two signals to its own loading and
    saving, which is all that differs between tools. The file itself is shared through the
    FileRegistry: opening one here opens it for every tool using the same file, and a file
    already opened by another tool is loaded silently, without asking anything.

    ``read_only=True`` drops the save button: the bar then only opens/shares a file this tool
    reads but never writes (e.g. mngrp.bin, edited only in Shiva but previewed by others). It
    still publishes what it opens and picks up what another tool opened, both through the
    registry, so the file is shared in every direction.
    """

    file_opened = pyqtSignal(str)  # path of the file to load
    save_requested = pyqtSignal()

    def __init__(self, file_name, registry: FileRegistry, icon_path="Resources", file_filter="*.bin",
                 read_only=False):
        QWidget.__init__(self)
        self.file_name = file_name
        self.registry = registry
        self.file_filter = file_filter
        self.read_only = read_only
        self.file_dialog = QFileDialog()

        self.open_button = QPushButton()
        self.open_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.open_button.setIconSize(QSize(30, 30))
        self.open_button.setFixedSize(40, 40)
        if read_only:
            self.open_button.setToolTip(f"Open a {file_name} file to read (shared with every tool "
                                        f"using it; never written by this tool)")
        else:
            self.open_button.setToolTip(f"Open a {file_name} file (every tool using it will open it too)")
        self.open_button.clicked.connect(self._open_clicked)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.open_button)

        self.save_button = None
        if not read_only:
            self.save_button = QPushButton()
            self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
            self.save_button.setIconSize(QSize(30, 30))
            self.save_button.setFixedSize(40, 40)
            self.save_button.setToolTip(f"Save all modifications in the opened {file_name} (irreversible)")
            self.save_button.setEnabled(False)
            self.save_button.clicked.connect(self.save_requested)
            layout.addWidget(self.save_button)

        layout.addStretch(1)
        self.setLayout(layout)

        self.registry.file_changed.connect(self._registry_file_changed)

    def load_opened_file(self):
        """Load the file if it is already opened, doing nothing otherwise.

        Called by the tool once it connected the signals, as a tool can be created after
        another one opened the file.
        """
        file_path = self.registry.get_path(self.file_name)
        if file_path:
            if self.save_button is not None:
                self.save_button.setEnabled(True)
            self.file_opened.emit(file_path)

    def _open_clicked(self):
        file_path = self.file_dialog.getOpenFileName(
            parent=self, caption=f"Search {self.file_name} file", filter=self.file_filter,
            directory=self.registry.get_path(self.file_name) or os.getcwd())[0]
        if file_path:
            self.registry.open_file(self.file_name, file_path)  # Loads it here too, through file_changed

    def _registry_file_changed(self, file_name):
        if file_name == self.file_name:
            self.load_opened_file()
