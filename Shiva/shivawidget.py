import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QMessageBox

from Common.filebarwidget import FileBarWidget
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from Shiva.mngrpsave import keep_unowned_sections_raw
from Shiva.ShivaRefine.shivarefinewidget import ShivaRefineWidget
from Shiva.ShivaSeedTest.shivaseedtestwidget import ShivaSeedTestWidget
from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget
from Shiva.ShivaTutorial.shivatutorialwidget import ShivaTutorialWidget


class ShivaWidget(QWidget):
    """mngrp.bin editor: one file, one model, one tab per kind of section.

    Built like Ifrit: the file is read once into a MngrpManager that every tab shares, each tab
    edits only its own sections of it, and saving writes the whole file back section per section.
    That is what keeps the tabs independent. The tools it replaces each kept their own copy of
    the whole file, so whichever saved last silently threw away the others' work.

    mngrp.bin cannot be read without mngrphd.bin, which holds the offset and size of every
    section, so it is searched next to it.
    """

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_sysfnt_data()  # To read the text of the section holding some
        self.game_data.load_mngrp_data()
        # The m00x sections name their refine entries from those
        self.game_data.load_item_data()
        self.game_data.load_magic_data()
        self.game_data.load_card_data()
        self.manager = MngrpManager(game_data=self.game_data)
        self.mngrp_path = ""
        self.mngrphd_path = ""

        self.setWindowTitle("Shiva")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.file_bar = FileBarWidget("mngrp.bin", file_registry, icon_path, "mngrp.bin;;*.bin")
        self.file_bar.file_opened.connect(self.load_file)
        self.file_bar.save_requested.connect(self.save_file)

        # One tab per kind of section. Each one edits its own sections of self.manager and is
        # added here with add_section_tab, so saving asks all of them in turn.
        self.tabs = QTabWidget()
        self.section_tabs = []
        self.tabs.setEnabled(False)

        self.add_section_tab(ShivaRefineWidget(self.game_data), "Refine")
        self.add_section_tab(ShivaSeedTestWidget(self.game_data), "SeeD tests")
        self.add_section_tab(ShivaSpriteWidget(), "Sprites")
        self.add_section_tab(ShivaTutorialWidget(self.game_data), "Tutorial demos")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.file_bar)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.file_bar.load_opened_file()  # Another tool may have opened mngrp.bin already

    def add_section_tab(self, tab, title):
        """Add a tab editing its own sections of the shared mngrp.

        The tab needs a load_from_mngrp(manager) to read its sections, and a
        save_to_mngrp(manager) to write them back into the shared model (not to a file:
        Shiva writes the file once, with every tab's sections in it)."""
        self.section_tabs.append(tab)
        self.tabs.addTab(tab, title)

    def load_file(self, mngrp_path):
        mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            QMessageBox.warning(self, "Shiva - mngrphd.bin not found",
                                f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                f"it is not next to it:\n{mngrphd_path}")
            return
        self.manager.load_file(mngrphd_path, mngrp_path)
        self.mngrp_path = mngrp_path
        self.mngrphd_path = mngrphd_path
        owned = set()
        for tab in self.section_tabs:
            tab.load_from_mngrp(self.manager)
            owned |= tab.owned_section_ids(self.manager)
        keep_unowned_sections_raw(self.game_data, self.manager.mngrp, owned)
        self.tabs.setEnabled(True)

    def save_file(self):
        """Write every tab's sections back in one file, so no tab loses another one's work."""
        if not self.mngrp_path:
            return
        for tab in self.section_tabs:
            tab.save_to_mngrp(self.manager)
        self.manager.save_file(self.mngrp_path, self.mngrphd_path)
