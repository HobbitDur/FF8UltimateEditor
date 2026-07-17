import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox

from FF8GameData.gamedata import GameData
from Joker.jokermanager import JokerManager
from Joker.sp2editorwidget import Sp2EditorWidget


class JokerWidget(QWidget):
    """SP2 sprite table editor for a .sp2 file (face.sp2, cardanm.sp2).

    The same table also exists inside mngrp.bin, holding the magazine picture sprites: that one
    is edited by Shiva, next to the other sections of that file, so the two cannot overwrite
    each other any more. Both use the same editor and the same Sp2File.

    The file edited here is whichever .sp2 is picked, not one precise FF8 file, and no other
    tool reads it: it has nothing to share and so keeps its own open button.
    """

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.manager = JokerManager(self.game_data)

        self.setWindowTitle("Joker")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a .sp2 file (face.sp2, cardanm.sp2)")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened file (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addStretch(1)

        self.sp2_editor = Sp2EditorWidget()

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.sp2_editor)
        self.setLayout(main_layout)

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search .sp2 file",
                                                     filter="*.sp2", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Joker", f"Not a valid SP2 file:\n{error}")
            return
        self.sp2_editor.set_sp2(self.manager.sp2)

    def save_file(self):
        if self.manager.sp2 and self.manager.file_path:
            self.manager.save_file()
