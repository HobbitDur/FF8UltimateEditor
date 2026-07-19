import csv
import json
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFileDialog, QPushButton, QHBoxLayout, QLabel, QComboBox,
                             QMessageBox, QSplitter)

from Cid.draw import Draw
from Cid.drawwidget import DrawWidget
from Cid.drawillustrationwidget import DrawIllustrationWidget
from Cid.worlddrawsection import WorldDrawSection
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData


class CidWidget(QWidget):
    """Unified draw-point editor.

    Field and world draw points (Draw ID 1..256) share the EXE ``DrawPointData``
    table for magic / refill / high-yield (exported as a ``.hext``). World draw
    points (129..256) additionally have a world-map position stored in wmset
    Section 34 (X, Y, Sub ID), editable here and on the map, saved back into
    ``wmsetxx.obj``.
    """

    GENERAL_OFFSET = 0x400000
    VERSION_LIST = ["OG (2013)"]
    NB_DRAW = 256
    WORLD_EXE_START_INDEX = 128  # 0-based index of the first world entry in DrawPointData

    def __init__(self, icon_path='Resources', game_data_folder="FF8GameData",
                 field_images_folder=None, file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()

        # Field screenshots (from the Deling image export) live under Resources by default.
        if field_images_folder is None:
            field_images_folder = os.path.join(icon_path, 'field_image')

        self.game_data = GameData(game_data_folder)
        self.game_data.load_field_data()
        self.game_data.load_exe_data()
        self.game_data.load_magic_data()
        self.game_data.load_draw_data()

        # Draw ID -> field internal name(s), used to show a field screenshot per draw point.
        self._draw_field_map = {}
        draw_field_path = os.path.join(game_data_folder, "Resources", "json", "draw_field.json")
        if os.path.exists(draw_field_path):
            with open(draw_field_path, encoding="utf-8") as draw_field_file:
                self._draw_field_map = json.load(draw_field_file)

        # State
        self.exe_loaded = False
        self.wmset_file_path = ""
        self._section = WorldDrawSection()
        self._selected_row = -1
        # Unsaved-change flags: which of the two backing files has edits to write.
        self._exe_dirty = False
        self._wmset_dirty = False

        # The two edited inputs run from the shared header toolbar: Import drops a menu (FF8 exe /
        # wmset), Save writes the .hext and/or the wmset (see save_folder). The exe shares its key
        # with the other exe tool (CCGroup): opening it once feeds both.
        self.exe_binding = FileBinding("FF8 exe", file_registry, load_callback=self.load_exe,
                                       file_filter="*.exe")
        self.wmset_binding = FileBinding("wmsetxx.obj", file_registry, load_callback=self.load_wmset,
                                         file_filter="wmset*.obj;;*.obj")
        # The save dialogs stay: each save writes to a path the user picks (.hext / wmset).
        self._save_hext_dialog = QFileDialog()
        self._save_wmset_dialog = QFileDialog()

        self.csv_dialog = QFileDialog()
        self._csv_upload_button = self._make_button(icon_path, 'csv_upload.png', "Upload csv", self._open_csv)
        self._csv_save_button = self._make_button(icon_path, 'csv_save.png', "Save to csv", self._save_csv)

        self._fullscreen_button = QPushButton("Illustration full screen")
        self._fullscreen_button.setCheckable(True)
        self._fullscreen_button.setToolTip("Hide the table and let the map / field image take all the space")
        self._fullscreen_button.toggled.connect(self._on_fullscreen_toggled)

        self._version_label = QLabel("Game version")
        self._version_widget = QComboBox(parent=self)
        self._version_widget.addItems(self.VERSION_LIST)
        self._version_widget.setToolTip("Select version of the game")

        self._layout_top = QHBoxLayout()
        self._layout_top.addWidget(self._csv_upload_button)
        self._layout_top.addWidget(self._csv_save_button)
        self._layout_top.addWidget(self._fullscreen_button)
        self._layout_top.addWidget(self._version_label)
        self._layout_top.addWidget(self._version_widget)
        self._layout_top.addStretch(1)

        # Model: full 256-entry list, kept alive and updated as files load.
        self._draw_list = [Draw(self.game_data, id=i + 1, data_hex=bytearray()) for i in range(self.NB_DRAW)]

        self._draw_widget = DrawWidget(self.game_data, self._draw_list, parent=self)
        self._illustration = DrawIllustrationWidget(os.path.join(icon_path, 'map2.png'), self._draw_field_map,
                                                    field_images_folder, parent=self)
        self._illustration.set_draw_list(self._draw_list)

        # Wiring: table <-> illustration
        self._draw_widget.selection_changed.connect(self._on_selection_changed)
        self._draw_widget.position_changed.connect(self._illustration.refresh)
        self._illustration.position_picked.connect(self._on_map_position_picked)

        # Wiring: edits mark the corresponding backing file dirty.
        self._draw_widget.exe_changed.connect(self._on_exe_edited)
        self._draw_widget.world_changed.connect(self._on_world_edited)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._draw_widget)
        self._splitter.addWidget(self._illustration)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)

        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.window_layout.addLayout(self._layout_top)
        self.window_layout.addWidget(self._splitter)

        self.exe_binding.load_opened_file()    # the exe may already be open (e.g. in CCGroup)
        self.wmset_binding.load_opened_file()

    def file_bindings(self):
        """The two inputs the shared header toolbar drives: the FF8 exe and the wmsetxx.obj."""
        return [self.exe_binding, self.wmset_binding]

    def save_folder(self):
        """The shared Save button: write the .hext and/or the wmset, whichever was edited."""
        self._save()

    def can_save_folder(self):
        """Save is enabled once either backing file is loaded (the click decides what to write)."""
        return self.exe_loaded or self._section.is_loaded()

    def _make_button(self, icon_path, icon_name, tooltip, callback):
        button = QPushButton()
        button.setIcon(QIcon(os.path.join(icon_path, icon_name)))
        button.setIconSize(QSize(30, 30))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def _on_exe_edited(self):
        self._exe_dirty = True

    def _on_world_edited(self):
        self._wmset_dirty = True

    # ---- table <-> illustration wiring ------------------------------------
    def _on_selection_changed(self, row):
        self._selected_row = row
        draw = self._draw_list[row] if 0 <= row < len(self._draw_list) else None
        self._illustration.set_selected(row, draw)

    def _on_map_position_picked(self, x, y):
        # Only world draw points have a map position to place.
        if self._selected_row < 0 or not self._draw_list[self._selected_row].is_world():
            return
        self._draw_widget.set_row_position(self._selected_row, x, y)
        self._illustration.refresh()

    def _on_fullscreen_toggled(self, checked):
        self._draw_widget.setVisible(not checked)

    # ---- loading -----------------------------------------------------------
    def load_exe(self, path):
        """Load the draw magic/refill/high-yield table from the FF8 exe (path from the toolbar)."""
        with open(path, "rb") as in_file:
            file_data = bytearray(in_file.read())
        draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
        for i in range(self.NB_DRAW):
            self._draw_list[i].set_exe_byte(file_data[draw_offset + i])
        self.exe_loaded = True
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)

    def load_wmset(self, path):
        """Load the world-map draw positions (wmset Section 34) from a wmsetxx.obj."""
        try:
            self._section.load(path)
        except Exception as error:
            self._show_error("Draw Editor - Failed to read wmset",
                             f"Could not parse Section 34 of this file:<br>{error}")
            return
        self.wmset_file_path = path
        nb = min(self._section.get_nb_record(), self.NB_DRAW - self.WORLD_EXE_START_INDEX)
        for i in range(nb):
            x, y, sub_id, _pad = self._section.records[i]
            draw = self._draw_list[self.WORLD_EXE_START_INDEX + i]
            draw.x, draw.y, draw.sub_id = x, y, sub_id
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)

    # ---- saving ------------------------------------------------------------
    def _save(self):
        """Save the EXE .hext and/or the wmset, writing only files that were edited.

        Falls back to writing every loaded file when nothing is flagged dirty, so a
        manual re-save (e.g. to a different path) still works.
        """
        save_exe = self.exe_loaded and (self._exe_dirty or not self._wmset_dirty)
        save_wmset = self._section.is_loaded() and (self._wmset_dirty or not self._exe_dirty)
        # When neither is dirty, both of the above are True for whatever is loaded (re-save all).

        if save_exe and self._save_hext():
            self._exe_dirty = False
        if save_wmset and self._save_wmset():
            self._wmset_dirty = False

    def _save_hext(self):
        if not self.exe_loaded:
            self._show_error("Draw Editor - No EXE loaded", "Load the FF8 exe before saving magic data.")
            return False
        default_file_name = os.path.join(os.getcwd(), "draw_data_injection.hext")
        file_to_save = self._save_hext_dialog.getSaveFileName(parent=self, caption="Save hext file", filter="*.hext",
                                                              directory=default_file_name)[0]
        if not file_to_save:
            return False
        draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
        hext_str = "#Offset to dynamic data\n"
        hext_str += "+{:X}\n\n".format(self.GENERAL_OFFSET)
        hext_str += "#Draw point data: MagicID (0x3F) | Refill (0x40) | HighYield (0x80), one byte per draw ID\n"
        hext_str += "#Start of draw data is at 0x{:X}\n\n".format(draw_offset)
        for draw_index, draw in enumerate(self._draw_list):
            address = draw_offset + draw_index
            hext_str += f"#Draw ID {draw.get_id()} ({draw.get_magic_name()})\n"
            hext_str += " {:X} = {:02X}\n\n".format(address, draw.get_exe_byte())
        with open(file_to_save, "w") as hext_file:
            hext_file.write(hext_str)
        return True

    def _save_wmset(self):
        if not self._section.is_loaded():
            self._show_error("Draw Editor - No wmset loaded", "Load a wmsetxx.obj before saving world positions.")
            return False
        default_file_name = self.wmset_file_path or os.path.join(os.getcwd(), "wmsetus.obj")
        file_to_save = self._save_wmset_dialog.getSaveFileName(parent=self, caption="Save wmsetxx.obj", filter="*.obj",
                                                               directory=default_file_name)[0]
        if not file_to_save:
            return False
        nb = min(self._section.get_nb_record(), self.NB_DRAW - self.WORLD_EXE_START_INDEX)
        for i in range(nb):
            draw = self._draw_list[self.WORLD_EXE_START_INDEX + i]
            self._section.set_position(i, draw.x, draw.y, draw.sub_id)
        try:
            self._section.save(file_to_save)
        except Exception as error:
            self._show_error("Draw Editor - Failed to save wmset", str(error))
            return False
        return True

    # ---- CSV ---------------------------------------------------------------
    def _save_csv(self):
        file_to_save = self.csv_dialog.getSaveFileName(parent=self, caption="Find csv file", filter="*.csv",
                                                       directory="draw_data")[0]
        if not file_to_save:
            return
        with open(file_to_save, 'w', newline='', encoding="utf-8") as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=GameData.find_delimiter_from_csv_file(file_to_save),
                                    quotechar='§', quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(['Draw ID', 'Magic ID', 'High Yield', 'Refill', 'X', 'Y', 'Sub ID'])
            for draw in self._draw_list:
                csv_writer.writerow([draw.get_id(), draw.magic_index, int(draw.high_yield), int(draw.refill),
                                     draw.x, draw.y, draw.sub_id])

    def _open_csv(self):
        csv_to_load = self.csv_dialog.getOpenFileName(parent=self, caption="Find csv file (in UTF8 format only)",
                                                      filter="*.csv")[0]
        if not csv_to_load:
            return
        has_positions = False
        try:
            with open(csv_to_load, newline='', encoding="utf-8") as csv_file:
                csv_data = csv.reader(csv_file, delimiter=GameData.find_delimiter_from_csv_file(csv_to_load),
                                      quotechar='§')
                for row_index, row in enumerate(csv_data):
                    if row_index == 0 or row_index > self.NB_DRAW:  # skip header, ignore overflow
                        continue
                    draw = self._draw_list[row_index - 1]
                    draw.magic_index = int(row[1])
                    draw.high_yield = bool(int(row[2]))
                    draw.refill = bool(int(row[3]))
                    if len(row) >= 7:  # position columns are optional (backward compatible)
                        draw.x, draw.y, draw.sub_id = int(row[4]), int(row[5]), int(row[6])
                        has_positions = True
        except UnicodeDecodeError:
            self._show_error("Draw Editor - Wrong CSV encoding",
                             "Wrong <b>encoding</b>, please use <b>UTF8</b> formating only.<br>"
                             "In excel, you can go to the \"Data tab\", \"Import text file\" and choose UTF8 encoding")
            return
        # A CSV import edits the model directly, so flag the affected file(s) as unsaved.
        self._exe_dirty = True
        if has_positions:
            self._wmset_dirty = True
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)

    @staticmethod
    def _show_error(title, text):
        message_box = QMessageBox()
        message_box.setText(text)
        message_box.setIcon(QMessageBox.Icon.Critical)
        message_box.setWindowTitle(title)
        message_box.exec()
