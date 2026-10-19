import csv
import json
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFileDialog, QPushButton, QHBoxLayout, QLabel, QComboBox,
                             QMessageBox, QSplitter, QTabWidget)

from Cid.draw import Draw
from Cid.drawwidget import DrawWidget
from Cid.drawillustrationwidget import DrawIllustrationWidget
from Cid.worlddrawsection import WorldDrawSection
from Cid.worlddrawgeometry import WorldDrawGeometry
from Cid.worlddrawphases import WorldDrawPhases
from Cid.drawgroupswidget import DrawGroupsWidget
from Cid.drawmapwidget import DrawMapWidget
from Cid.phasestory import PhaseStoryDialog
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData


class CidWidget(QWidget):
    """Unified draw-point editor.

    Field and world draw points (Draw ID 1..256) share the EXE ``DrawPointData``
    table for magic / refill / high-yield (exported as a ``.hext``). World draw
    points (129..256) additionally have a world-map position stored in wmset
    Section 34 (X, Y, Sub ID), editable here and on the map, saved back into
    ``wmsetxx.obj``. The Groups and phases tab edits the same section's five
    trigger ranges and the EXE's ordered phase searches, saved as wmset and Hext
    respectively.
    """

    GENERAL_OFFSET = 0x400000
    VERSION_LIST = ["OG (2013)"]
    NB_DRAW = 256
    WORLD_EXE_START_INDEX = 128  # 0-based index of the first world entry in DrawPointData
    APPROXIMATE_MAP_STATUS = (
        'Map: approximate block centres on an illustrative background; coastal points may appear in water. '
        'Load read-only wmx.obj for terrain and triangle positions. Numbers count overlapping records; '
        'click cycles them, drag moves, wheel zooms.')

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
        self.game_data.load_draw_data()
        self.game_data.load_kernel_data()

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
        self._phase_rules = WorldDrawPhases()
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
        self.kernel_binding = FileBinding("kernel.bin", file_registry, load_callback=self.load_kernel,
                                          read_only=True)
        self.wmx_binding = FileBinding("wmx.obj", file_registry, load_callback=self.load_wmx,
                                       read_only=True)
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

        self._phase_widget = QComboBox()
        for phase in range(5):
            self._phase_widget.addItem(f'World phase {phase}', phase)
        self._phase_widget.addItem('No phase (unused)', DrawMapWidget.NO_PHASE)
        self._phase_widget.setToolTip('Choose a world story phase, or No phase for records never searched. '
                                      'These are not disc numbers.')
        self._layout_top.addWidget(self._phase_widget)
        self._phase_info_label = QLabel('Phase info')
        self._phase_info_button = self._make_button(
            icon_path, 'info.png', 'When each world phase changes, with verified field-script references',
            self._show_phase_info)
        self._phase_info_button.setAccessibleName('Phase info')
        self._layout_top.addWidget(self._phase_info_label)
        self._layout_top.addWidget(self._phase_info_button)
        self._layout_top.addStretch(1)

        self._save_status = QLabel()
        self._save_status.setWordWrap(True)
        self._names_status = QLabel('Spell names: load complementary kernel.bin (read-only).')
        self._names_status.setWordWrap(True)
        self._map_status = QLabel(self.APPROXIMATE_MAP_STATUS)
        self._map_status.setWordWrap(True)

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
        self._illustration.map.selection_picked.connect(lambda row: self._draw_widget.setCurrentCell(row, 0))
        self._phase_widget.currentIndexChanged.connect(self._on_phase_selected)
        self._illustration.map.set_phase(self._phase_widget.currentData())

        # Wiring: edits mark the corresponding backing file dirty.
        self._draw_widget.exe_changed.connect(self._on_exe_edited)
        self._draw_widget.world_changed.connect(self._on_world_edited)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._draw_widget)
        self._splitter.addWidget(self._illustration)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)

        self._groups_widget = DrawGroupsWidget(self)
        self._groups_widget.set_sources(self._section, self._phase_rules, self._draw_list)
        self._groups_widget.world_changed.connect(self._on_group_ranges_edited)
        self._groups_widget.exe_changed.connect(self._on_phase_rules_edited)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._splitter, 'Draw points')
        self.tabs.addTab(self._groups_widget, 'Groups and phases')
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.window_layout.addLayout(self._layout_top)
        self.window_layout.addWidget(self._save_status)
        self.window_layout.addWidget(self._names_status)
        self.window_layout.addWidget(self._map_status)
        self.window_layout.addWidget(self.tabs)

        # Removing one of the two files from the Opened files panel drops its part of the table.
        self.exe_binding.file_closed.connect(self._on_exe_closed)
        self.wmset_binding.file_closed.connect(self._on_wmset_closed)
        self.kernel_binding.file_closed.connect(self._on_kernel_closed)
        self.wmx_binding.file_closed.connect(self._on_wmx_closed)

        self.exe_binding.load_opened_file()    # the exe may already be open (e.g. in CCGroup)
        self.wmset_binding.load_opened_file()
        self.kernel_binding.load_opened_file()
        self.wmx_binding.load_opened_file()
        self._update_save_status()

    def file_bindings(self):
        """Two edited sources and two optional read-only complementary files."""
        return [self.exe_binding, self.wmset_binding, self.kernel_binding, self.wmx_binding]

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
        self._groups_widget.refresh_members()
        self._update_save_status()

    def _show_phase_info(self):
        PhaseStoryDialog(self).exec()

    def _on_phase_selected(self):
        view = self._illustration.map
        view.set_phase(self._phase_widget.currentData())
        if 0 <= self._selected_row < len(self._draw_list) and view._visible(self._draw_list[self._selected_row]):
            return
        for row, draw in enumerate(self._draw_list):
            if view._visible(draw):
                self._draw_widget.setCurrentCell(row, 0)
                self._draw_widget.scrollToItem(self._draw_widget.item(row, 0))
                break

    def _on_world_edited(self):
        self._wmset_dirty = True
        self._update_save_status()

    def _update_save_status(self):
        exe = 'modified' if self._exe_dirty else ('loaded' if self.exe_loaded else 'not loaded')
        wm = 'modified' if self._wmset_dirty else ('loaded' if self._section.is_loaded() else 'not loaded')
        self._save_status.setText(f'.hext: magic ID, refill, high yield, phase searches ({exe}). '
                                  f'wmset: world X, Y, triangle, group ranges ({wm}). '
                                  'Save in the header writes the edited outputs. kernel.bin is read-only.')

    def _on_tab_changed(self, index):
        for widget in (self._csv_upload_button, self._csv_save_button, self._fullscreen_button,
                       self._phase_widget, self._map_status):
            widget.setVisible(index == 0)
        if index == 1:
            self._groups_widget.refresh()

    def _refresh_world_phases(self):
        for i, draw in enumerate(self._draw_list[self.WORLD_EXE_START_INDEX:]):
            draw.world_phases = (self._section.phases_for_record(i, self._phase_rules.phase_groups)
                                 if draw.position_loaded and self._section.is_loaded() else ())
        self._draw_widget.refresh_phases()
        self._illustration.refresh()
        self._groups_widget.set_sources(self._section, self._phase_rules, self._draw_list)
        for index in range(self._phase_widget.count()):
            phase = self._phase_widget.itemData(index)
            label = 'No phase (unused)' if phase == DrawMapWidget.NO_PHASE else f'World phase {phase}'
            if self._section.is_loaded():
                count = sum(draw.position_loaded and
                            (not draw.world_phases if phase == DrawMapWidget.NO_PHASE else phase in draw.world_phases)
                            for draw in self._draw_list[128:])
                label += f' - {count} record' + ('s' if count != 1 else '')
            self._phase_widget.setItemText(index, label)
        source = 'loaded EXE rules' if self._phase_rules.loaded else 'original OG rules (no EXE loaded)'
        self._phase_widget.setToolTip(f'Filter the world map using {source}. No phase shows loaded '
                                      'records never searched by any phase, including unused slots. '
                                      'World phases are story states, not disc numbers.')

    def _on_group_ranges_edited(self):
        self._refresh_world_phases()
        self._on_world_edited()

    def _on_phase_rules_edited(self):
        self._refresh_world_phases()
        self._on_exe_edited()

    # ---- table <-> illustration wiring ------------------------------------
    def _on_selection_changed(self, row):
        self._selected_row = row
        draw = self._draw_list[row] if 0 <= row < len(self._draw_list) else None
        self._illustration.set_selected(row, draw)

    def _on_map_position_picked(self, x, y, sub_id=-1):
        # Only world draw points have a map position to place.
        if self._selected_row < 0 or not self._draw_list[self._selected_row].is_world():
            return
        if not self._section.is_loaded():
            return
        self._draw_widget.set_row_position(self._selected_row, x, y, sub_id)
        self._illustration.refresh()

    def _on_fullscreen_toggled(self, checked):
        self._draw_widget.setVisible(not checked)

    # ---- loading -----------------------------------------------------------
    def load_exe(self, path):
        """Load the draw magic/refill/high-yield table from the FF8 exe (path from the toolbar)."""
        draw_offset = self.game_data.exe_data_json["draw_data_offset"]["og_eng_start"]
        try:
            with open(path, "rb") as in_file:
                file_data = in_file.read()
            if len(file_data) < draw_offset + self.NB_DRAW:
                raise ValueError('File is too short for the OG English 2013 draw table')
            rules = WorldDrawPhases()
            rules.load_exe_bytes(file_data)
        except (OSError, ValueError) as error:
            self._show_error('Cid - Failed to read FF8 EXE', str(error))
            return
        for i in range(self.NB_DRAW):
            self._draw_list[i].set_exe_byte(file_data[draw_offset + i])
        self.exe_loaded = True
        self._phase_rules = rules
        self._exe_dirty = False
        self._draw_widget._exe_loaded = True
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)
        self._refresh_world_phases()
        self._update_save_status()

    def load_kernel(self, path):
        from FF8GameData.kernelnames import read_names
        try:
            names = read_names(self.game_data, path, keep_unnamed=True)
            if not names.get('magic'):
                raise ValueError('No magic name entries found')
        except Exception as error:
            self._show_error('Cid - Failed to read kernel.bin', str(error))
            return
        self.game_data.kernel_names = names
        self._names_status.setText(f'Spell names: {path} (read-only). Draw magic IDs are limited to 0-63.')
        self._draw_widget.set_draw(self._draw_list)
        self._groups_widget.refresh_members()
        self._illustration.refresh()

    def _on_kernel_closed(self, _path):
        self.game_data.kernel_names = {}
        self._names_status.setText('Spell names: load complementary kernel.bin (read-only).')
        self._draw_widget.set_draw(self._draw_list)
        self._groups_widget.refresh_members()
        self._illustration.refresh()

    def load_wmx(self, path):
        try:
            geometry = WorldDrawGeometry(path)
            # Validate every referenced block before installing it in the painter.
            for draw in self._draw_list[self.WORLD_EXE_START_INDEX:]:
                if draw.position_loaded:
                    geometry.triangle(draw)
            overview = QPixmap()
            overview.loadFromData(geometry.overview_png())
        except Exception as error:
            self._show_error('Cid - Failed to read wmx.obj', str(error))
            return
        self._illustration.map.set_geometry(geometry, overview)
        self._map_status.setText('Map: base-world terrain and trigger triangles from wmx.obj. '
                                 'Story replacement terrain can differ. Numbers count overlapping records; '
                                 'click cycles them. Drag chooses a destination triangle; wheel zooms.')
        self._illustration.refresh()

    def _on_wmx_closed(self, _path):
        self._illustration.map.set_geometry(None)
        self._map_status.setText(self.APPROXIMATE_MAP_STATUS)
        self._illustration.refresh()

    def load_wmset(self, path):
        """Load the world-map draw positions (wmset Section 34) from a wmsetxx.obj."""
        try:
            self._section.load(path)
        except Exception as error:
            self._show_error("Draw Editor - Failed to read wmset",
                             f"Could not parse Section 34 of this file:<br>{error}")
            return
        self.wmset_file_path = path
        self._wmset_dirty = False
        for draw in self._draw_list[self.WORLD_EXE_START_INDEX:]:
            draw.position_loaded = False
            draw.world_phases = ()
            draw.x, draw.y, draw.sub_id = 0, 0, 0
        nb = min(self._section.get_nb_record(), self.NB_DRAW - self.WORLD_EXE_START_INDEX)
        for i in range(nb):
            x, y, sub_id, _pad = self._section.records[i]
            draw = self._draw_list[self.WORLD_EXE_START_INDEX + i]
            draw.x, draw.y, draw.sub_id = x, y, sub_id
            draw.position_loaded = True
            draw.world_phases = self._section.phases_for_record(i, self._phase_rules.phase_groups)
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)
        self._refresh_world_phases()
        self._update_save_status()

        # Extracted world archives keep the matching terrain beside wmset. Prefer
        # those exact triangles over approximate markers on the reference image.
        terrain_path = os.path.join(os.path.dirname(path), 'wmx.obj')
        if (self._illustration.map.geometry is None and not self.wmx_binding.current_path
                and os.path.isfile(terrain_path)):
            self.wmx_binding.open_path(terrain_path)

    def _on_exe_closed(self, _path):
        """Closing one source cannot discard edits belonging to the other source."""
        self.exe_loaded = False
        self._phase_rules = WorldDrawPhases()
        self._draw_widget._exe_loaded = False
        self._exe_dirty = False
        for draw in self._draw_list:
            draw.set_exe_byte(0)
        self._draw_widget.set_draw(self._draw_list)
        self._refresh_world_phases()
        self._illustration.refresh()
        self._update_save_status()

    def _on_wmset_closed(self, _path):
        self._section = WorldDrawSection()
        self.wmset_file_path = ""
        self._wmset_dirty = False
        for draw in self._draw_list:
            draw.x, draw.y, draw.sub_id = 0, 0, 0
            draw.position_loaded = False
            draw.world_phases = ()
        self._draw_widget.set_draw(self._draw_list)
        self._illustration.set_draw_list(self._draw_list)
        self._refresh_world_phases()
        self._update_save_status()

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
        self._update_save_status()

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
        phase_lines = self._phase_rules.hext_lines(self.GENERAL_OFFSET)
        if phase_lines:
            hext_str += '#World draw phase searches: ordered group IDs; FF ends a row\n'
            hext_str += '\n'.join(phase_lines) + '\n'
        with open(file_to_save, "w", encoding="utf-8") as hext_file:
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
        self._groups_widget.refresh()
        self._update_save_status()

    @staticmethod
    def _show_error(title, text):
        message_box = QMessageBox()
        message_box.setText(text)
        message_box.setIcon(QMessageBox.Icon.Critical)
        message_box.setWindowTitle(title)
        message_box.exec()
