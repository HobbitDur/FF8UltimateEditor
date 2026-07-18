import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from Common.fileregistry import FileRegistry
from Moomba.moombawidget import MoombaWidget
from Zone.zonewidget import ZoneWidget


class ZoneTabsWidget(QWidget):
    """The magazine-page editor, one tool for the two files that share the 68-byte
    page format:

      * tab 1 — mmag.bin: the in-menu magazines and tutorial books (the ZoneWidget);
      * tab 2 — mmag2.bin: the save-point Chocobo World screen (the MoombaWidget).

    Both tabs share the one FileRegistry, so a mngrp.bin (or sysfnt.*) opened for
    one page family is picked up by the other without re-opening it. The shared header
    toolbar's Import/Save follow the active tab: file_bindings() returns the active tab's
    files, and file_bindings_changed tells the toolbar to refresh when the tab changes."""

    file_bindings_changed = pyqtSignal()  # the active tab (and so its files) changed

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.setWindowTitle("Zone")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.mmag_widget = ZoneWidget(icon_path, game_data_folder, file_registry)
        self.mmag2_widget = MoombaWidget(icon_path, game_data_folder, file_registry)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.mmag_widget, "mmag.bin — Magazines")
        self.tabs.addTab(self.mmag2_widget, "mmag2.bin — Chocobo World")
        self.tabs.currentChanged.connect(lambda _index: self.file_bindings_changed.emit())

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def file_bindings(self):
        """The shared toolbar drives the files of whichever tab is showing: mmag.bin (+ its five
        complementary files) on the Magazines tab, mmag2.bin (+ mngrp.bin) on the Chocobo World
        tab."""
        active = self.tabs.currentWidget()
        getter = getattr(active, "file_bindings", None)
        return getter() if callable(getter) else []
