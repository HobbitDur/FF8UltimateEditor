import copy
import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QMessageBox

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.kernelnamesource import KernelNameSource
from FF8GameData.FF8HexReader.mngrphd import MngrpPairError
from FF8GameData.gamedata import GameData
from FF8GameData.menu.mngrp.m00x.refineabilities import (RefineKernelError, read_refine_abilities,
                                                         verify_refine_ranges, write_refine_ranges)
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
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

        # mngrp.bin is this tool's one editable file (its sub-tabs all edit the same file),
        # driven by the shared header toolbar (Import / Save) through the registry.
        self.mngrp_binding = FileBinding("mngrp.bin", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file)

        # One tab per kind of section. Each one edits its own sections of self.manager and is
        # added here with add_section_tab, so saving asks all of them in turn.
        self.tabs = QTabWidget()
        self.section_tabs = []
        self.tabs.setEnabled(False)

        self.refine_tab = ShivaRefineWidget(self.game_data)
        self.add_section_tab(self.refine_tab, "Refine")
        # kernel.bin, complementary: names the items a refine takes or gives, the ones a mod adds
        # with FFNx's AddMoreItems (199-255) included, and holds the range of recipes of each refine
        # ability - which Shiva writes back when recipes are added or removed (only those bytes).
        self.kernel_binding = FileBinding("kernel.bin", file_registry, file_filter="*kernel*.bin",
                                          complementary=True)
        self.kernel_names = KernelNameSource(self.game_data, file_registry, binding=self.kernel_binding)
        self.kernel_names.changed.connect(
            lambda: self.refine_tab.set_item_entries(self.kernel_names.item_entries()))
        self.kernel_path = ""
        self.kernel_binding.file_opened.connect(self._load_refine_abilities)
        self.kernel_binding.file_closed.connect(self._clear_refine_abilities)
        self.add_section_tab(ShivaSeedTestWidget(self.game_data), "SeeD tests")
        self.add_section_tab(ShivaSpriteWidget(), "Sprites")
        self.add_section_tab(ShivaTutorialWidget(self.game_data), "Tutorial demos")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.mngrp_binding.load_opened_file()  # Another tool may have opened mngrp.bin already
        self.kernel_binding.load_opened_file()  # ...or a kernel.bin

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool: mngrp.bin, and kernel.bin as
        a complementary file naming the items and holding the refine ranges."""
        return [self.mngrp_binding, self.kernel_binding]

    def _load_refine_abilities(self, kernel_path):
        try:
            abilities = read_refine_abilities(self.game_data, kernel_path)
        except Exception as error:  # noqa: BLE001 - a bad kernel.bin just gives no abilities
            print(f"[Shiva] could not read the refine abilities of {kernel_path}: {error}")
            abilities = None
        self.kernel_path = kernel_path if abilities is not None else ""
        self.refine_tab.set_kernel_abilities(abilities)

    def _clear_refine_abilities(self, _path=None):
        self.kernel_path = ""
        self.refine_tab.set_kernel_abilities(None)

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
        try:
            self.manager.load_file(mngrphd_path, mngrp_path)
        except MngrpPairError as error:
            QMessageBox.warning(self, "Shiva - mngrphd.bin does not match", str(error))
            return
        self.mngrp_path = mngrp_path
        self.mngrphd_path = mngrphd_path
        for tab in self.section_tabs:
            tab.load_from_mngrp(self.manager)
        self.tabs.setEnabled(True)

    def save_files(self):
        """The shared Save. False when nothing could be written, so the unsaved marker stays."""
        if not self.mngrp_binding.is_loaded:
            return None
        return self.save_file()

    def save_file(self):
        """Write every tab's sections back in one file, so no tab loses another one's work.

        Recipes added or removed move the refine ranges of kernel.bin: both files are written, and
        everything is checked before either is, so they cannot end up out of step."""
        if not self.mngrp_path:
            return False
        layout = self.refine_tab.layout
        errors = layout.check_game_limits() if layout else []
        if layout and layout.ranges_changed:
            if not self.kernel_path:
                errors.append("Recipes were added or removed, which moves the refine ranges kept in "
                              "kernel.bin, and no kernel.bin is open anymore.")
            else:
                try:
                    verify_refine_ranges(self.game_data, self.kernel_path, layout.abilities)
                except (RefineKernelError, OSError) as error:
                    errors.append(str(error))
        if errors:
            QMessageBox.critical(self, "Shiva - Nothing saved", "\n\n".join(errors))
            return False
        for tab in self.section_tabs:
            tab.save_to_mngrp(self.manager)
        self.manager.save_file(self.mngrp_path, self.mngrphd_path)
        if layout and layout.ranges_changed:
            try:
                write_refine_ranges(self.game_data, self.kernel_path, layout.abilities)
            except (RefineKernelError, OSError) as error:
                QMessageBox.critical(self, "Shiva - kernel.bin not saved",
                                     f"mngrp.bin was saved, but the refine ranges could not be written "
                                     f"into kernel.bin, so the two files no longer match:\n{error}")
                return False
            self.refine_tab.kernel_abilities = copy.deepcopy(layout.abilities)
            self._warn_other_kernel_editors()
        return True

    def _warn_other_kernel_editors(self):
        """A tool editing the whole kernel.bin (SolomonRing, ShumiTranslator) still holds the old
        ranges in memory: saving there would put them back."""
        others = [binding for binding in self.kernel_binding.registry.bindings
                  if binding is not self.kernel_binding and binding.file_name == "kernel.bin"
                  and not binding.read_only and binding.is_loaded]
        if others:
            QMessageBox.warning(self, "Shiva - kernel.bin also open elsewhere",
                                "The refine ranges were written into kernel.bin. Another tool has it open "
                                "(SolomonRing or ShumiTranslator): use Reload there before saving in it, "
                                "or it writes the old ranges back.")
