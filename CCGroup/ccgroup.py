import os

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFileDialog, QHBoxLayout, QLabel, QComboBox, QSpinBox, \
    QTabWidget

from CCGroup.card import Card
from CCGroup.cardwidget import CardWidget
from CCGroup.npccardgamewidget import NpcCardGameWidget
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData


class CCGroupWidget(QWidget):
    file_bindings_changed = pyqtSignal()  # the active tab changed
    CARD_DATA_SIZE = 8
    GENERAL_OFFSET = 0x400000
    LANG_LIST = ["en", "fr"]
    MOD_LIST = ["Original", "Tripod (Mcindus)", "Xylomod (ducladoncladon)"]

    def __init__(self, icon_path='Resources', game_data_path="FF8GameData", settings: QSettings = None,
                 file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
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
        self.npc_card_game_widget = NpcCardGameWidget(icon_path=icon_path, settings=settings)
        self.tab_widget.addTab(self.npc_card_game_widget, "NPC card players")
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
        # shared header toolbar (Import / Save), which acts on this tab only (see file_bindings).
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
        self.game_data = GameData(game_data_path)
        self.game_data.load_card_data()
        self.game_data.load_exe_data()

        self.__layout_main.addLayout(self.__layout_top)
        self.__layout_main.addStretch(1)
        self.__card_widget_list = []
        self.__nb_card = len(self.game_data.card_data_json["card_info"]) - 1 # -1 for the immune

        self.exe_binding.load_opened_file()  # another tool may have opened the exe already

    def file_bindings(self):
        """The Card values tab edits the FF8 exe through the shared toolbar; the NPC tab is
        folder-based (see load_folder), so it offers no single-file binding here."""
        if self.tab_widget.currentIndex() == 0:
            return [self.exe_binding]
        return []

    def load_folder(self, folder_path):
        """The header's Open-folder button: on the NPC tab, load every .jsm/.sym card player found
        in the picked field folder. The Card values tab has nothing to load from a folder."""
        active = self.tab_widget.currentWidget()
        loader = getattr(active, "load_folder", None)
        if callable(loader):
            loader(folder_path)

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
                while el := in_file.read(1):
                    self.current_file_data.extend(el)

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
