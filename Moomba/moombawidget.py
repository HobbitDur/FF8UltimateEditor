import os

from PyQt6.QtCore import QSize, QSignalBlocker, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QSpinBox, QGroupBox, QFormLayout, QGridLayout, QScrollArea,
                             QMessageBox)

from FF8GameData.gamedata import GameData
from Moomba.moombamanager import MoombaManager, MagPageEntry


class MoombaWidget(QWidget):
    """mmag2.bin editor: the 12 pages of the save-point Chocobo World screen (the Mog story
    slides and the Solo RPG manual), sharing the 68-byte entry format of mmag.bin (Zone).

    If mngrp.bin (+ mngrphd.bin) is found next to the opened mmag2.bin (or loaded manually),
    the text overlay ids are previewed with their decoded strings from raw file 90."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        # GameData init already loads the sysfnt character table used for text decoding
        self.game_data = GameData(game_data_folder)
        self.manager = MoombaManager(self.game_data)

        self.setWindowTitle("Moomba")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a mmag2.bin file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened mmag2.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.load_mngrp_button = QPushButton("Load mngrp")
        self.load_mngrp_button.setToolTip("Load a mngrp.bin (with its mngrphd.bin next to it) to preview "
                                          "the text overlay strings (raw file 90).\nSearched automatically "
                                          "next to the opened mmag2.bin.")
        self.load_mngrp_button.clicked.connect(self.load_mngrp)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.load_mngrp_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Page list (left side)
        self.page_list = QListWidget()
        self.page_list.setFixedWidth(240)
        self.page_list.currentRowChanged.connect(self.reload_selected_entry)

        # Editor (right side)
        self.entry_name_label = QLabel("")
        self.entry_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        window_group = self._build_window_group()
        picture_group = self._build_picture_group()
        overlay_groups = self._build_overlay_groups()
        misc_group = self._build_misc_group()

        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.entry_name_label)
        editor_layout.addWidget(window_group)
        editor_layout.addWidget(picture_group)
        editor_layout.addWidget(overlay_groups)
        editor_layout.addWidget(misc_group)
        editor_layout.addStretch(1)

        self.editor_container = QWidget()
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(self.editor_container)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.page_list)
        main_editor_layout.addWidget(editor_scroll)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def _spinbox(self, minimum, maximum, tooltip=""):
        spinbox = QSpinBox()
        spinbox.setRange(minimum, maximum)
        if tooltip:
            spinbox.setToolTip(tooltip)
        spinbox.valueChanged.connect(self._on_data_changed)
        return spinbox

    def _int16_spinbox(self, tooltip=""):
        return self._spinbox(-32768, 32767, tooltip)

    def _byte_spinbox(self, tooltip=""):
        return self._spinbox(0, 255, tooltip)

    def _build_window_group(self):
        self.window_x = self._int16_spinbox("Text window X")
        self.window_y = self._int16_spinbox("Text window Y")
        self.window_width = self._int16_spinbox("Text window width")
        self.window_height = self._int16_spinbox("Text window height")
        group = QGroupBox("Text window")
        form = QFormLayout()
        form.addRow("X / Y:", self._pair(self.window_x, self.window_y))
        form.addRow("Width / Height:", self._pair(self.window_width, self.window_height))
        group.setLayout(form)
        return group

    def _build_picture_group(self):
        self.picture_x = self._int16_spinbox("Page picture X")
        self.picture_y = self._int16_spinbox("Page picture Y")
        self.picture_width = self._int16_spinbox("Page picture width (0 = no picture)")
        self.picture_height = self._int16_spinbox("Page picture height")
        self.picture_tint_r = self._byte_spinbox("Red of the paper mat rectangle drawn behind the page art "
                                                 "(multiplied by the zoom factor, /128)")
        self.picture_tint_g = self._byte_spinbox("Green of the paper mat rectangle")
        self.picture_tint_b = self._byte_spinbox("Blue of the paper mat rectangle")
        self.texture_category = self._byte_spinbox("Page texture category. The Chocobo World screen uses "
                                                   "category 6 = mngrp raw file 180 + page")
        self.texture_page = self._byte_spinbox("Page texture page number: with category 6, page 0 = raw 180 "
                                               "(story pictures), page 1 = raw 181 (manual pictures)")
        self.paper_e1 = self._byte_spinbox("Paper background parameter A (PS1 GPU E1 texture page bits)")
        self.paper_e2 = self._byte_spinbox("Paper background parameter B (PS1 GPU E2 texture window bits)")
        self.paper_e1.setDisplayIntegerBase(16)
        self.paper_e1.setPrefix("0x")
        self.paper_e2.setDisplayIntegerBase(16)
        self.paper_e2.setPrefix("0x")
        group = QGroupBox("Page picture (texture: category 6 → raw file 180 + page)")
        form = QFormLayout()
        form.addRow("X / Y:", self._pair(self.picture_x, self.picture_y))
        form.addRow("Width / Height:", self._pair(self.picture_width, self.picture_height))
        form.addRow("Mat tint R / G / B:", self._pair(self.picture_tint_r, self.picture_tint_g,
                                                   self.picture_tint_b))
        form.addRow("Texture category / page:", self._pair(self.texture_category, self.texture_page))
        form.addRow("Paper params A / B:", self._pair(self.paper_e1, self.paper_e2))
        group.setLayout(form)
        return group

    def _build_overlay_groups(self):
        # Picture overlays: SP2 sprite ids of mngrp Pos 4 (58-76 belong to this screen)
        self.picture_overlay_x = []
        self.picture_overlay_y = []
        self.picture_overlay_id = []
        picture_group = QGroupBox(f"Picture overlays (SP2 sprite ids {MoombaManager.SP2_SPRITE_FIRST}-"
                                  f"{MoombaManager.SP2_SPRITE_LAST} of mngrp Pos 4, 255 = unused)")
        picture_grid = QGridLayout()
        picture_grid.addWidget(QLabel("X"), 0, 1)
        picture_grid.addWidget(QLabel("Y"), 0, 2)
        picture_grid.addWidget(QLabel("Sprite id"), 0, 3)
        for i in range(MagPageEntry.NB_OVERLAY_SLOTS):
            x_spin = self._int16_spinbox("X position, relative to the window position")
            y_spin = self._byte_spinbox("Y position")
            id_spin = self._byte_spinbox("SP2 sprite id in mngrp Pos 4 (255 = slot unused)")
            self.picture_overlay_x.append(x_spin)
            self.picture_overlay_y.append(y_spin)
            self.picture_overlay_id.append(id_spin)
            picture_grid.addWidget(QLabel(f"Slot {i + 1}:"), i + 1, 0)
            picture_grid.addWidget(x_spin, i + 1, 1)
            picture_grid.addWidget(y_spin, i + 1, 2)
            picture_grid.addWidget(id_spin, i + 1, 3)
        picture_group.setLayout(picture_grid)

        # Text overlays: string ids of mngrp raw file 90
        self.text_overlay_x = []
        self.text_overlay_y = []
        self.text_overlay_id = []
        self.text_overlay_preview = []
        text_group = QGroupBox("Text overlays (string ids of mngrp raw file 90: story = 0-4, "
                               "manual = 5-14, 255 = unused)")
        text_grid = QGridLayout()
        text_grid.addWidget(QLabel("X"), 0, 1)
        text_grid.addWidget(QLabel("Y"), 0, 2)
        text_grid.addWidget(QLabel("String id"), 0, 3)
        text_grid.addWidget(QLabel("Preview"), 0, 4)
        for i in range(MagPageEntry.NB_OVERLAY_SLOTS):
            x_spin = self._int16_spinbox("X position, relative to the window position")
            y_spin = self._byte_spinbox("Y position")
            id_spin = self._byte_spinbox("String id in mngrp raw file 90 (255 = slot unused)")
            preview = QLabel("")
            preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_overlay_x.append(x_spin)
            self.text_overlay_y.append(y_spin)
            self.text_overlay_id.append(id_spin)
            self.text_overlay_preview.append(preview)
            text_grid.addWidget(QLabel(f"Slot {i + 1}:"), i + 1, 0)
            text_grid.addWidget(x_spin, i + 1, 1)
            text_grid.addWidget(y_spin, i + 1, 2)
            text_grid.addWidget(id_spin, i + 1, 3)
            text_grid.addWidget(preview, i + 1, 4)
        text_grid.setColumnStretch(4, 1)
        text_group.setLayout(text_grid)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(picture_group)
        layout.addWidget(text_group)
        container.setLayout(layout)
        return container

    def _build_misc_group(self):
        self.footer_flag = self._byte_spinbox("1 = draw the \"To be continued\"-style footer line")
        self.text_file_index = self._byte_spinbox("Book-text string section = raw file 87 + this value. "
                                                  "Unused by the Chocobo World screen (its text comes from "
                                                  "raw file 90), preserved as-is.")
        self.weapon_index = self._byte_spinbox("Weapon unlocked by the item-menu magazine reader (255 = none). "
                                               "Unused by the Chocobo World screen, preserved as-is.")
        self.weapon_line_spacing = self._byte_spinbox("Weapon remodel line spacing (unused here)")
        self.duel_move_id = self._byte_spinbox("Zell Duel move unlocked (255 = none, unused here)")
        self.angelo_move_id = self._byte_spinbox("Angelo move unlocked (255 = none, unused here)")
        self.weapon_list_x = self._int16_spinbox("Weapon list X (unused here)")
        self.weapon_list_y = self._byte_spinbox("Weapon list Y (unused here)")
        self.weapon_quantity_column_x = self._byte_spinbox("Weapon quantity column X offset (unused here)")
        self.duel_combo_x = self._int16_spinbox("Duel combo X (unused here)")
        self.duel_combo_y = self._byte_spinbox("Duel combo Y (unused here)")
        group = QGroupBox("Footer + fields unused by the Chocobo World screen (preserved byte-exact)")
        form = QFormLayout()
        form.addRow("Footer flag:", self.footer_flag)
        form.addRow("Text file index:", self.text_file_index)
        form.addRow("Weapon index / line spacing:", self._pair(self.weapon_index, self.weapon_line_spacing))
        form.addRow("Duel move / Angelo move:", self._pair(self.duel_move_id, self.angelo_move_id))
        form.addRow("Weapon list X / Y / qty col:", self._pair(self.weapon_list_x, self.weapon_list_y,
                                                               self.weapon_quantity_column_x))
        form.addRow("Duel combo X / Y:", self._pair(self.duel_combo_x, self.duel_combo_y))
        group.setLayout(form)
        return group

    @staticmethod
    def _pair(*widgets):
        layout = QHBoxLayout()
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mmag2.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_file(file_name)
        except ValueError as e:
            QMessageBox.warning(self, "Moomba", str(e))
            return
        self.file_label.setText(os.path.basename(file_name))
        self.editor_container.setEnabled(True)
        # The Chocobo World strings live in mngrp.bin, usually next to mmag2.bin
        mngrp_path = os.path.join(os.path.dirname(file_name), "mngrp.bin")
        if os.path.exists(mngrp_path):
            try:
                self.manager.load_mngrp(mngrp_path)
            except (FileNotFoundError, ValueError):
                pass
        with QSignalBlocker(self.page_list):
            self.page_list.clear()
            self.page_list.addItems([self.manager.get_entry_name(entry.entry_id)
                                     for entry in self.manager.entries])
        self.page_list.setCurrentRow(0)

    def load_mngrp(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mngrp.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_mngrp(file_name)
        except (FileNotFoundError, ValueError) as e:
            QMessageBox.warning(self, "Moomba", str(e))
            return
        self.reload_selected_entry()

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def reload_selected_entry(self):
        entry = self._selected_entry()
        if not entry:
            return
        self.entry_name_label.setText(self.manager.get_entry_name(entry.entry_id))
        values = [
            (self.window_x, entry.window_x), (self.window_y, entry.window_y),
            (self.window_width, entry.window_width), (self.window_height, entry.window_height),
            (self.picture_x, entry.picture_x), (self.picture_y, entry.picture_y),
            (self.picture_width, entry.picture_width), (self.picture_height, entry.picture_height),
            (self.picture_tint_r, entry.picture_tint_r), (self.picture_tint_g, entry.picture_tint_g),
            (self.picture_tint_b, entry.picture_tint_b),
            (self.paper_e1, entry.paper_e1), (self.paper_e2, entry.paper_e2),
            (self.text_file_index, entry.text_file_index),
            (self.texture_category, entry.texture_category), (self.texture_page, entry.texture_page),
            (self.weapon_index, entry.weapon_index), (self.weapon_line_spacing, entry.weapon_line_spacing),
            (self.duel_move_id, entry.duel_move_id), (self.angelo_move_id, entry.angelo_move_id),
            (self.weapon_list_x, entry.weapon_list_x), (self.weapon_list_y, entry.weapon_list_y),
            (self.weapon_quantity_column_x, entry.weapon_quantity_column_x),
            (self.duel_combo_x, entry.duel_combo_x), (self.duel_combo_y, entry.duel_combo_y),
            (self.footer_flag, entry.footer_flag),
        ]
        for i in range(MagPageEntry.NB_OVERLAY_SLOTS):
            values.extend([
                (self.picture_overlay_x[i], entry.picture_overlays[i].x),
                (self.picture_overlay_y[i], entry.picture_overlays[i].y),
                (self.picture_overlay_id[i], entry.picture_overlays[i].id),
                (self.text_overlay_x[i], entry.text_overlays[i].x),
                (self.text_overlay_y[i], entry.text_overlays[i].y),
                (self.text_overlay_id[i], entry.text_overlays[i].id),
            ])
        for spinbox, value in values:
            with QSignalBlocker(spinbox):
                spinbox.setValue(value)
        self._refresh_text_previews(entry)

    def _refresh_text_previews(self, entry):
        for i in range(MagPageEntry.NB_OVERLAY_SLOTS):
            slot = entry.text_overlays[i]
            if slot.unused:
                self.text_overlay_preview[i].setText("(unused)")
                self.text_overlay_preview[i].setToolTip("")
                continue
            text = self.manager.get_overlay_text(slot.id)
            if not text:
                self.text_overlay_preview[i].setText("(load mngrp.bin for preview)")
                self.text_overlay_preview[i].setToolTip("")
                continue
            first_line = text.split("\n")[0]
            if len(first_line) > 60:
                first_line = first_line[:57] + "..."
            self.text_overlay_preview[i].setText(first_line)
            self.text_overlay_preview[i].setToolTip(text)

    def _selected_entry(self):
        index = self.page_list.currentRow()
        if 0 <= index < len(self.manager.entries):
            return self.manager.entries[index]
        return None

    def _on_data_changed(self):
        entry = self._selected_entry()
        if not entry:
            return
        entry.window_x = self.window_x.value()
        entry.window_y = self.window_y.value()
        entry.window_width = self.window_width.value()
        entry.window_height = self.window_height.value()
        entry.picture_x = self.picture_x.value()
        entry.picture_y = self.picture_y.value()
        entry.picture_width = self.picture_width.value()
        entry.picture_height = self.picture_height.value()
        entry.picture_tint_r = self.picture_tint_r.value()
        entry.picture_tint_g = self.picture_tint_g.value()
        entry.picture_tint_b = self.picture_tint_b.value()
        entry.paper_e1 = self.paper_e1.value()
        entry.paper_e2 = self.paper_e2.value()
        entry.text_file_index = self.text_file_index.value()
        entry.texture_category = self.texture_category.value()
        entry.texture_page = self.texture_page.value()
        entry.weapon_index = self.weapon_index.value()
        entry.weapon_line_spacing = self.weapon_line_spacing.value()
        entry.duel_move_id = self.duel_move_id.value()
        entry.angelo_move_id = self.angelo_move_id.value()
        entry.weapon_list_x = self.weapon_list_x.value()
        entry.weapon_list_y = self.weapon_list_y.value()
        entry.weapon_quantity_column_x = self.weapon_quantity_column_x.value()
        entry.duel_combo_x = self.duel_combo_x.value()
        entry.duel_combo_y = self.duel_combo_y.value()
        entry.footer_flag = self.footer_flag.value()
        for i in range(MagPageEntry.NB_OVERLAY_SLOTS):
            entry.picture_overlays[i].x = self.picture_overlay_x[i].value()
            entry.picture_overlays[i].y = self.picture_overlay_y[i].value()
            entry.picture_overlays[i].id = self.picture_overlay_id[i].value()
            entry.text_overlays[i].x = self.text_overlay_x[i].value()
            entry.text_overlays[i].y = self.text_overlay_y[i].value()
            entry.text_overlays[i].id = self.text_overlay_id[i].value()
        self._refresh_text_previews(entry)
