import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMessageBox

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Joker.jokermanager import JokerManager
from Joker.sp2editorwidget import Sp2EditorWidget


class JokerWidget(QWidget):
    """SP2 sprite table editor for a .sp2 file (face.sp2, cardanm.sp2).

    The same table also exists inside mngrp.bin, holding the magazine picture sprites: that one
    is edited by Shiva, next to the other sections of that file, so the two cannot overwrite
    each other any more. Both use the same editor and the same Sp2File.

    The file edited here is whichever .sp2 is picked, not one precise FF8 file, so it can't share
    a single registry key the way e.g. price.bin does - like Ifrit's *.dat, the binding just keys
    itself generically and filters the open dialog on *.sp2.
    """

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.manager = JokerManager(self.game_data)

        self.setWindowTitle("Joker")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # Driven by the shared header toolbar (Import / Save).
        self.sp2_binding = FileBinding("sprite sheet (.sp2)", file_registry,
                                       load_callback=self.load_file, save_callback=self.save_file,
                                       file_filter="*.sp2")

        self.sp2_editor = Sp2EditorWidget()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.sp2_editor)
        self.setLayout(main_layout)

        self.sp2_binding.load_opened_file()  # another tool instance may have opened one already

    def file_bindings(self):
        """The file the shared header toolbar drives for this tool (the loaded .sp2)."""
        return [self.sp2_binding]

    def load_file(self, file_name):
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Joker", f"Not a valid SP2 file:\n{error}")
            return
        self.sp2_editor.set_sp2(self.manager.sp2)

    def save_file(self):
        if self.manager.sp2 and self.manager.file_path:
            self.manager.save_file()
