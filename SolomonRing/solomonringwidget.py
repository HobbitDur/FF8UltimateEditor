import json
import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QFileDialog, QLabel
)

from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from SolomonRing.kernellookups import LookupRegistry
from SolomonRing.kernelsectiontab import KernelSectionTab


# Top-level layout: (tab title, [(section_id, sub-tab label), ...]).
# A single-section group is shown directly; multi-section groups get a nested tab bar.
TAB_LAYOUT = [
    ("Magic", [(2, "Magic")]),
    ("G-Forces", [(3, "G-Forces")]),
    ("GF Attacks", [(10, "Non-Junction GF")]),
    ("Enemy Attacks", [(4, "Enemy Attacks")]),
    ("Weapons", [(5, "Weapons")]),
    ("Characters", [(7, "Characters")]),
    ("Items", [(8, "Battle Items"), (9, "Item Names")]),
    ("Commands", [(1, "Battle Commands"), (11, "Command Ability Data")]),
    ("Abilities", [(13, "Command"), (12, "Junction"), (15, "Character"), (16, "Party"),
                   (17, "GF"), (18, "Menu"), (14, "Stat %")]),
    ("Limit Breaks", [(6, "Renzokuken"), (19, "T. Characters"), (20, "Blue Magic"),
                      (21, "Blue Magic Params"), (22, "Shot"), (23, "Duel"),
                      (24, "Duel Params"), (25, "Rinoa 1"), (26, "Rinoa 2"),
                      (27, "Slot Array"), (28, "Slot Sets")]),
    ("Devour", [(29, "Devour")]),
    ("Misc", [(30, "Misc"), (31, "Misc Text")]),
]


class SolomonRingWidget(QWidget):
    """kernel.bin editor with full doomtrain field parity, driven by JSON field defs."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        super().__init__()

        self.game_data_folder = game_data_folder
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()

        self.kernel_manager = KernelManager(self.game_data)
        self.registry = LookupRegistry(self.game_data, game_data_folder)
        self.loaded_filename = None

        with open(os.path.join(game_data_folder, "Resources", "json", "kernel_section_fields.json"),
                  encoding="utf-8") as f:
            self._section_configs = json.load(f)
        with open(os.path.join(game_data_folder, "Resources", "json", "kernel_bin_data.json"),
                  encoding="utf-8") as f:
            kernel_json = json.load(f)
        self._text_link = {s["id"]: s["section_id_text_linked"] for s in kernel_json["sections"]
                           if s["type"] == "data"}

        self._section_tabs = {}  # section_id -> KernelSectionTab

        main_layout = QVBoxLayout()

        # --- File toolbar -----------------------------------------------------
        file_layout = QHBoxLayout()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, "folder.png")))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.clicked.connect(self._load_kernel)
        self.load_button.setToolTip("Open a kernel.bin file")
        file_layout.addWidget(self.load_button)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, "save.svg")))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.clicked.connect(self._save_kernel)
        self.save_button.setToolTip("Save all modifications to the kernel.bin (irreversible)")
        file_layout.addWidget(self.save_button)

        self.compress_button = QPushButton()
        self.compress_button.setIcon(QIcon(os.path.join(icon_path, "compress.png")))
        self.compress_button.setIconSize(QSize(30, 30))
        self.compress_button.setFixedSize(40, 40)
        self.compress_button.clicked.connect(self._compress_all_text)
        self.compress_button.setToolTip(
            "Compress all kernel text: replaces common letter pairs with the game's built-in\n"
            "compression tokens (shown as {..}), shrinking every name/description. Mirrors\n"
            "ShumiTranslator; respects each section's compressibility.")
        file_layout.addWidget(self.compress_button)

        self.uncompress_button = QPushButton()
        self.uncompress_button.setIcon(QIcon(os.path.join(icon_path, "uncompress.png")))
        self.uncompress_button.setIconSize(QSize(30, 30))
        self.uncompress_button.setFixedSize(40, 40)
        self.uncompress_button.clicked.connect(self._uncompress_all_text)
        self.uncompress_button.setToolTip(
            "Uncompress all kernel text: expands the {..} compression tokens back to plain\n"
            "letters in every name/description (makes text readable / editable).")
        file_layout.addWidget(self.uncompress_button)

        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("color: gray; font-style: italic;")
        file_layout.addWidget(self.file_label)
        file_layout.addStretch()
        main_layout.addLayout(file_layout)

        # --- Section tabs -----------------------------------------------------
        self.tabs = QTabWidget()
        for title, entries in TAB_LAYOUT:
            self.tabs.addTab(self._build_group(entries), title)
        main_layout.addWidget(self.tabs)

        self.setLayout(main_layout)
        self.tabs.setEnabled(False)

    def _build_group(self, entries):
        if len(entries) == 1:
            section_id, _ = entries[0]
            return self._make_section_tab(section_id)
        inner = QTabWidget()
        inner.setTabPosition(QTabWidget.TabPosition.West)
        for section_id, label in entries:
            inner.addTab(self._make_section_tab(section_id), label)
        return inner

    def _make_section_tab(self, section_id):
        config = self._section_configs[str(section_id)]
        tab = KernelSectionTab(self.game_data, self.registry, config)
        self._section_tabs[section_id] = tab
        return tab

    # ------------------------------------------------------------------ file IO
    def _load_kernel(self):
        file_dialog = QFileDialog()
        filename = file_dialog.getOpenFileName(parent=self, caption="Open kernel.bin",
                                               filter="*kernel*.bin")[0]
        if filename:
            self.load_file(filename)

    def load_file(self, filename):
        self.loaded_filename = filename
        self.kernel_manager.load_file(filename)
        self._populate_tabs()
        self.tabs.setEnabled(True)
        self.file_label.setText(filename)
        self.file_label.setStyleSheet("color: black;")

    def _populate_tabs(self):
        by_id = {s.id: s for s in self.kernel_manager.section_list if s}
        for section_id, tab in self._section_tabs.items():
            section = by_id.get(section_id)
            text_id = self._text_link.get(section_id, 0)
            text_section = by_id.get(text_id) if text_id else None
            tab.load_section(section, text_section)

    def _compress_all_text(self):
        if not self.loaded_filename:
            return
        by_id = {s.id: s for s in self.kernel_manager.section_list if s}
        for data_id, text_id in self._text_link.items():
            text_section = by_id.get(text_id) if text_id else None
            config = self._section_configs.get(str(data_id))
            labels = config.get("text_labels", []) if config else []
            if not text_section or not labels:
                continue
            # Compress every string except plain "Name" fields (which ship uncompressed).
            for index, text in enumerate(text_section.get_text_list()):
                if labels[index % len(labels)] != "Name":
                    text.compress_str(3)
        self._populate_tabs()

    def _uncompress_all_text(self):
        if not self.loaded_filename:
            return
        for text_section in self._all_text_sections():
            for text in text_section.get_text_list():
                text.uncompress_str()
        self._populate_tabs()

    def _all_text_sections(self):
        linked_ids = {tid for tid in self._text_link.values() if tid}
        return [s for s in self.kernel_manager.section_list if s and s.id in linked_ids]

    def _save_kernel(self):
        if not self.loaded_filename:
            return
        for tab in self._section_tabs.values():
            tab.commit()
        self.kernel_manager.save_file(self.loaded_filename)
        print(f"Saved to {self.loaded_filename}")
        self.file_label.setText(f"{self.loaded_filename}  (saved)")
