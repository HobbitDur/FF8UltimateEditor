import os

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFileDialog, QHBoxLayout, QLabel, QComboBox, QSpinBox, \
    QTabWidget

from CCGroup.card import Card
from CCGroup.cardwidget import CardWidget
from CCGroup.npccardgamewidget import NpcCardGameWidget
from Common.filebinding import FileBinding
from Common.autoimport import AutoImportSource
from Common.fieldfolder import check_field_folder, pick_field_folder
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData


class CCGroupWidget(QWidget):
    file_bindings_changed = pyqtSignal()  # the active tab changed
    # The Opened files entries of the NPC tab's two field folders.
    NPC_REGISTRY_NAME = "CCGroup field folder (edited)"
    NPC_REFERENCE_REGISTRY_NAME = "CCGroup vanilla field folder (reference)"
    # Their remembered folders (FileRegistry.last_folder keys), which Auto-upload reopens too.
    EDITED_FOLDER_KEY = "CCGroup field folder"
    REFERENCE_FOLDER_KEY = "CCGroup vanilla field folder"
    CARD_DATA_SIZE = 8
    GENERAL_OFFSET = 0x400000
    LANG_LIST = ["en", "fr"]
    MOD_LIST = ["Original", "Tripod (Mcindus)", "Xylomod (ducladoncladon)"]

    def __init__(self, icon_path='Resources', game_data_path="FF8GameData", settings: QSettings = None,
                 file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        file_registry.file_closed.connect(self._on_registry_file_closed)
        if settings is None:
            settings = QSettings("HobbitDur", "FF8UltimateEditor")
        self.settings = settings

        # Window management
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.tab_widget = QTabWidget()
        self.window_layout.addWidget(self.tab_widget)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.tab_widget.addTab(self.scroll_area, "Card values")
        self.game_data = GameData(game_data_path)
        self.game_data.load_card_data()
        self.npc_card_game_widget = NpcCardGameWidget(icon_path=icon_path, settings=settings,
                                                      game_data=self.game_data)
        self.npc_card_game_widget.folders_changed.connect(self.__sync_opened_folders)
        self.tab_widget.addTab(self.npc_card_game_widget, "NPC card players")
        self.__migrate_folder_settings()
        self.tab_widget.currentChanged.connect(self.__tab_changed)
        self.tab_widget.setCurrentIndex(self.settings.value("ccgroup/current_tab", defaultValue=0, type=int))
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        self.__layout_main = QVBoxLayout()
        self.scroll_widget.setLayout(self.__layout_main)
        self.setWindowTitle("CC Group")
        #self.setMinimumSize(600, 600)
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'icon.ico')))

        # The FF8 exe holds the card values; the .hext export is its "save". Both run from the
        # shared header toolbar (Import, from either tab; Save acts on this tab only - see file_bindings).
        self.exe_binding = FileBinding("FF8 exe", file_registry, load_callback=self.load_file,
                                       save_callback=self.__save_file, file_filter="*.exe")
        self.__save_dialog = QFileDialog()

        self.__language_label_widget = QLabel(parent=self, text="FF8 language: ")
        self.__language_label_widget.setToolTip("The language you play on. It will affect the file output and the .exe to read")
        self.__language_widget = QComboBox(parent=self)
        self.__language_widget.addItems(self.LANG_LIST)
        self.__language_widget.setToolTip("The language you play on. It will affect the file output and the .exe to read")
        self.__language_layout = QHBoxLayout()
        self.__language_layout.addWidget(self.__language_label_widget)
        self.__language_layout.addWidget(self.__language_widget)
        self.__language_layout.wheelEvent = lambda event: None

        self.__mod_label_widget = QLabel("Remaster cards")
        self.__mod_widget = QComboBox(parent=self)
        self.__mod_widget.addItems(self.MOD_LIST)
        self.__mod_widget.currentIndexChanged.connect(self.__change_card_image)
        self.__mod_widget.setToolTip("Change the design of the card")
        self.__mod_widget.wheelEvent = lambda event: None
        self.__mod_layout = QHBoxLayout()
        self.__mod_layout.addWidget(self.__mod_label_widget)
        self.__mod_layout.addWidget(self.__mod_widget)

        self.__size_slider_label = QLabel("Card size:")
        self.__size_slider_label.setToolTip("Change card size (Min:64, Max:256)")
        self.__size_slider_widget = QSpinBox()
        self.__size_slider_widget.setMaximum(256)
        self.__size_slider_widget.setMinimum(64)
        self.__size_slider_widget.setValue(128)
        self.__size_slider_widget.setToolTip("Change card size (Min:64, Max:256)")
        self.__size_slider_widget.valueChanged.connect(self.__change_card_image)
        self.__size_slider_widget.wheelEvent = lambda event: None
        self.__size_card_layout = QHBoxLayout()
        self.__size_card_layout.addWidget(self.__size_slider_label)
        self.__size_card_layout.addWidget(self.__size_slider_widget)

        self.__layout_top = QHBoxLayout()
        self.__layout_top.addLayout(self.__language_layout)
        self.__layout_top.addWidget(self.__mod_widget)
        self.__layout_top.addLayout(self.__size_card_layout)
        self.__layout_top.addStretch(1)

        self.current_file_data = bytearray()
        self.game_data.load_exe_data()

        self.__layout_main.addLayout(self.__layout_top)
        self.__layout_main.addStretch(1)
        self.__card_widget_list = []
        self.__nb_card = len(self.game_data.card_data_json["card_info"]) - 1 # -1 for the immune

        self.exe_binding.load_opened_file()  # another tool may have opened the exe already

    def file_bindings(self):
        """What Save and Reload act on: the FF8 exe on the Card values tab. The NPC tab saves its
        field folder through save_folder."""
        if self.tab_widget.currentIndex() == 0:
            return [self.exe_binding]
        return []

    def import_entries(self):
        """Import, the same from either tab (each opens its tab): the FF8 exe for the card values, or
        the field folder you edit for the NPC card players - a folder, since they are read from
        every map of the game at once."""
        return [("FF8 exe (card values)", self.open_exe),
                (f"{NpcCardGameWidget.EDITED_TITLE} (NPC card players)", self.open_working_folder)]

    def complementary_entries(self):
        return [(f"{NpcCardGameWidget.REFERENCE_TITLE} (NPC card players, read-only)",
                 self.open_reference_folder)]

    def open_exe(self):
        if self.exe_binding.open_remembered(self):
            self.tab_widget.setCurrentIndex(0)

    def open_working_folder(self):
        check = pick_field_folder(self, "CC Group", f"{NpcCardGameWidget.EDITED_TITLE}: the 'field' folder"
                                  f" holding mapdata (a mod's, or a whole extracted one)",
                                  self.file_registry.last_folder(self.EDITED_FOLDER_KEY),
                                  remember=lambda folder: self.file_registry.remember_folder(self.EDITED_FOLDER_KEY,
                                                                                             folder))
        if check is not None:
            self.load_working_folder(check.root)

    def open_reference_folder(self):
        check = pick_field_folder(self, "CC Group", f"{NpcCardGameWidget.REFERENCE_TITLE}: the whole game's"
                                  f" 'field' folder holding mapdata", self.file_registry.last_folder(
                                      self.REFERENCE_FOLDER_KEY), complete=True,
                                  remember=lambda folder: self.file_registry.remember_folder(
                                      self.REFERENCE_FOLDER_KEY, folder))
        if check is not None:
            self.load_reference_folder(check.root)

    def load_working_folder(self, folder):
        """Use a checked field folder (Common.fieldfolder) as the one the NPC tab edits."""
        self.tab_widget.setCurrentWidget(self.npc_card_game_widget)
        if self.npc_card_game_widget.set_working_folder(folder):
            self.file_registry.remember_folder(self.EDITED_FOLDER_KEY, folder)

    def load_reference_folder(self, folder):
        """Use a checked complete field folder (Common.fieldfolder) as the NPC tab's vanilla reference."""
        self.tab_widget.setCurrentWidget(self.npc_card_game_widget)
        if self.npc_card_game_widget.set_reference_folder(folder):
            self.file_registry.remember_folder(self.REFERENCE_FOLDER_KEY, folder)

    def auto_import_bindings(self):
        return [self.exe_binding]  # from either tab, like Import

    def auto_import_sources(self):
        """Auto-upload also reopens the two field folders last opened (checked again: a folder
        moved or changed since is reported, not loaded)."""
        sources = []
        for key, loader, complete in ((self.REFERENCE_FOLDER_KEY, self.load_reference_folder, True),
                                      (self.EDITED_FOLDER_KEY, self.load_working_folder, False)):
            folder = self.file_registry.last_folder(key)
            if folder:
                sources.append(AutoImportSource(
                    key, ("*.jsm",), lambda _paths, f=folder, load=loader, c=complete: self.__reopen(f, load, c),
                    folder=folder, recursive=True))
        return sources

    @staticmethod
    def __reopen(folder, loader, complete):
        check = check_field_folder(folder, complete=complete)
        if not check.ok:
            raise ValueError(check.error)
        loader(check.root)

    def __migrate_folder_settings(self):
        """Folders remembered by versions that opened the field folder with the header's former
        Open-folder button: vanilla first (ccgroup/npc_last_folder), then a modified folder on top."""
        if self.file_registry.last_folder(self.EDITED_FOLDER_KEY) or \
                self.file_registry.last_folder(self.REFERENCE_FOLDER_KEY):
            return
        vanilla = self.settings.value("ccgroup/npc_last_folder", "", type=str)
        modified = self.settings.value("ccgroup/npc_modified_folder", "", type=str)
        if vanilla and modified:
            self.file_registry.remember_folder(self.REFERENCE_FOLDER_KEY, vanilla)
            self.file_registry.remember_folder(self.EDITED_FOLDER_KEY, modified)
        elif vanilla:
            self.file_registry.remember_folder(self.EDITED_FOLDER_KEY, vanilla)

    def __sync_opened_folders(self):
        """One Opened files entry per field folder the NPC tab uses."""
        npc = self.npc_card_game_widget
        for name, folder in ((self.NPC_REGISTRY_NAME, npc.working_folder),
                             (self.NPC_REFERENCE_REGISTRY_NAME, npc.reference_folder)):
            if folder and self.file_registry.get_path(name) != folder:
                self.file_registry.open_file(name, folder)
            elif not folder and self.file_registry.get_path(name):
                self.file_registry.close_file(name)
        self.file_bindings_changed.emit()  # Save may now have something to do

    def _on_registry_file_closed(self, file_name, _path):
        """A field folder was removed from the Opened files panel: stop using it."""
        npc = self.npc_card_game_widget
        if file_name == self.NPC_REGISTRY_NAME and npc.working_folder:
            npc.close_working_folder()
        elif file_name == self.NPC_REFERENCE_REGISTRY_NAME and npc.reference_folder:
            npc.close_reference_folder()

    def save_folder(self):
        """The header's Save button, multi-file side: on the NPC tab, save the patched .jsm files."""
        active = self.tab_widget.currentWidget()
        saver = getattr(active, "save_folder", None)
        if callable(saver):
            saver()

    def can_save_folder(self):
        active = self.tab_widget.currentWidget()
        predicate = getattr(active, "can_save_folder", None)
        return bool(predicate()) if callable(predicate) else False

    def __tab_changed(self, index: int):
        self.settings.setValue("ccgroup/current_tab", index)
        self.file_bindings_changed.emit()

    def __change_card_image(self):
        for card_widget in self.__card_widget_list:
            card_widget.change_card_mod(self.__mod_widget.currentIndex(), self.__size_slider_widget.value())

    def load_file(self, path):
        """Load the card values out of the FF8 exe (path from the shared header toolbar)."""
        if path:
            self.file_loaded = path

            self.current_file_data = bytearray()
            for card_widget in self.__card_widget_list:
                card_widget.setParent(None)
                card_widget.deleteLater()
            self.__card_widget_list = []
            with open(self.file_loaded, "rb") as in_file:
                self.current_file_data.extend(in_file.read())  # one read: byte by byte took seconds on the exe

            menu_offset = self.game_data.exe_data_json["card_data_offset"]["eng_menu"]
            menu_offset += self.__get_lang_offset()
            list_card = []
            id = 0
            for card_data_index in range(menu_offset, menu_offset + self.__nb_card * self.CARD_DATA_SIZE, self.CARD_DATA_SIZE):
                new_card = Card(game_data=self.game_data, id=id, offset=menu_offset + card_data_index * self.CARD_DATA_SIZE,
                                data_hex=self.current_file_data[card_data_index: card_data_index + self.CARD_DATA_SIZE],
                                mod=self.__mod_widget.currentIndex(), card_size=self.__size_slider_widget.value())
                list_card.append(new_card)
                id += 1

            for card in list_card:
                self.__card_widget_list.append(CardWidget(card))
                self.__layout_main.addWidget(self.__card_widget_list[-1])

    def __save_file(self):
        default_file_name = os.path.join(os.getcwd(), "monster_card_injection_" + self.__language_widget.currentText() + ".hext")
        file_to_save = self.__save_dialog.getSaveFileName(parent=self, caption="Save hext file", filter="*.hext",
                                                          directory=default_file_name)[0]
        hext_str = ""
        # First writing base data (not sure why necessary, but everyone does it)
        hext_str += "#Base writing (not sure why necessary)\n"
        hext_str += "600000:1000\n\n"
        # Then adding the offset of the data
        hext_str += "#Offset to dynamic data\n"
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET)

        menu_offset = self.game_data.exe_data_json["card_data_offset"]["eng_menu"]
        menu_offset += self.__get_lang_offset()

        game_offset = self.game_data.exe_data_json["card_data_offset"]["eng_game_data"]
        game_offset += self.__get_lang_offset()

        # Now adding the card data for the menu
        hext_str += "#Data represent the following values:\n"
        hext_str += "#Top value, Down value, Left value, Right value, Type value, Power value (followed by 2 zeros bytes)\n"
        hext_str += "#The type values have the following meaning:\n"
        hext_str += "#0:None, 1:Fire, 2:Ice, 4:Thunder, 8:Earth, 16:Bio, 32:Wind, 64:Water, 128:Holy\n"
        hext_str += "#The power value: When you lose a game card, the pnj will choose the card with the highest power value\n\n"

        hext_str += "#Start of menu card data is at 0x{:X}\n\n".format(menu_offset)

        for card_index, card_widget in enumerate(self.__card_widget_list):
            card = card_widget.card
            hext_str += f"#Address To Do Le Ri Ty Po for monster {card.get_name()} with id {card.get_id()}\n"
            hext_str += "{:X}".format(menu_offset + card_index * self.CARD_DATA_SIZE)
            hext_str += " = "
            hext_str += "{:02X}".format(card.top_value) + " " + "{:02X}".format(card.down_value) + " " + "{:02X}".format(
                card.left_value) + " " + "{:02X}".format(card.right_value) + " " + "{:02X}".format(card.get_type_int()) + " " + "{:02X}".format(
                card.power_value) + " 00 00"
            hext_str += "\n\n"

        hext_str += "\n\n"
        hext_str += "#Start of mini game card data is at 0x{:X}\n\n".format(game_offset)
        hext_str += "#To have the same code, we just move the pointer of 0x{:X}-0x{:X}=0x{:X}\n".format(game_offset, menu_offset, game_offset - menu_offset)
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET + (game_offset - menu_offset))

        # flemme, same code that up but don't want to lose time
        for card_index, card_widget in enumerate(self.__card_widget_list):
            card = card_widget.card
            hext_str += f"#Address To Do Le Ri Ty Po for monster {card.get_name()} with id {card.get_id()}\n"
            hext_str += "{:X}".format(menu_offset + card_index * self.CARD_DATA_SIZE)
            hext_str += " = "
            hext_str += "{:02X}".format(card.top_value) + " " + "{:02X}".format(card.down_value) + " " + "{:02X}".format(
                card.left_value) + " " + "{:02X}".format(card.right_value) + " " + "{:02X}".format(card.get_type_int()) + " " + "{:02X}".format(
                card.power_value) + " 00 00"
            hext_str += "\n\n"

        # Saving hext
        with open(file_to_save, "w") as hext_file:
            hext_file.write(hext_str)

    def __get_lang_offset(self):
        offset_lang = 0
        if self.__language_widget.currentText() != "en":
            offset_lang = [self.game_data.exe_data_json["card_data_offset"][x] for x in self.game_data.exe_data_json["card_data_offset"].keys() if
                           x == self.__language_widget.currentText() + '_offset']
            if offset_lang:
                offset_lang = offset_lang[self.__language_widget.currentText() + '_offset']
            else:
                print(f"Error, no offset found for lang {self.__language_widget.currentText()}")
        return offset_lang
