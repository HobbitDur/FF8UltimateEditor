import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QTabWidget, QWidget, QListWidget, QHBoxLayout, QPushButton, QVBoxLayout, QFileDialog

from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from solomonring.gfdata import GFData
from solomonring.junctionablegftabs.gfgeneraltab import GFGeneralTab


class SolomonRingWidget(QWidget):

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        super().__init__()

        self.game_data_folder = game_data_folder
        self.game_data = GameData(game_data_folder)
        self.game_data.load_kernel_data()

        self.kernel_manager = KernelManager(self.game_data)

        self.gf_data_list = []
        self.current_gf_index = -1

        #base_dir = os.path.dirname(os.path.abspath(__file__))
        #self.kernel_path = os.path.join(base_dir, "kernel.bin")
        #self.kernel_manager.load_file(self.kernel_path)

        # Main layout
        main_layout = QVBoxLayout()

        # File section
        file_section_layout = QHBoxLayout()

        # Load button
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.clicked.connect(self._load_kernel)
        self.load_button.setToolTip("Open a .dat file")
        file_section_layout.addWidget(self.load_button)

        # Save button
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.clicked.connect(self._save_kernel)
        self.layout_main = QVBoxLayout()
        self.save_button.setToolTip("Save all modification in the .dat (irreversible)")
        file_section_layout.addWidget(self.save_button)

        file_section_layout.addStretch()

        # Editor section
        editor_layout = QHBoxLayout()

        # GF list
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(140)
        self.list_widget.setStyleSheet("font-size: 12pt;")
        self.list_widget.addItems([
            "Quezacotl", "Shiva", "Ifrit", "Siren", "Brothers", "Diablos",
            "Carbuncle", "Leviathan", "Pandemona", "Cerberus", "Alexander",
            "Doomtrain", "Bahamut", "Cactuar", "Tonberry", "Eden"
        ])
        self.list_widget.currentRowChanged.connect(self._gf_selection_change)
        editor_layout.addWidget(self.list_widget)

        # Tabs
        self.tabs = QTabWidget()
        self.general_tab = GFGeneralTab(game_data_folder)
        self.abilities_tab = QWidget()
        self.gf_compatibility_tab = QWidget()
        self.tabs.addTab(self.general_tab, "General")
        self.tabs.addTab(self.abilities_tab, "Abilities")
        self.tabs.addTab(self.gf_compatibility_tab, "GFs Compatibility")
        editor_layout.addWidget(self.tabs)

        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(editor_layout)

        self.setLayout(main_layout)

    def _gf_selection_change(self, new_index):
        if not self.gf_data_list:
            return
        if self.current_gf_index >= 0:
            self.general_tab.save_gf_data(self.gf_data_list[self.current_gf_index])
        self.general_tab.load_gf_data(self.gf_data_list[new_index])
        self.current_gf_index = new_index

    def _load_kernel(self):
        file_dialog = QFileDialog()
        filename_to_load = file_dialog.getOpenFileName(parent=self, caption="Open kernel.bin", filter="*kernel*.bin")[0]
        if filename_to_load:
            self.loaded_filename = filename_to_load
            self.kernel_manager.load_file(self.loaded_filename)
            json_path = self.game_data_folder + "/Resources/json/kernel_junctionable_gf_data.json"
            self.gf_data_list = [
                GFData(subsection, json_path)
                for subsection in self.kernel_manager.section_list[3].get_subsection_list()
            ]
            self.current_gf_index = -1
            self.list_widget.setCurrentRow(0)
            self._gf_selection_change(0)

    def _save_kernel(self):
        if not self.gf_data_list:
            return
        # Make sure not to accidentally lose edits made on the currently selected GF
        self.general_tab.save_gf_data(self.gf_data_list[self.current_gf_index])
        self.kernel_manager.save_file(self.loaded_filename)
        print(f"Saved to {self.loaded_filename}")