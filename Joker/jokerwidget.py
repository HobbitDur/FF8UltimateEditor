import os

from PyQt6.QtCore import QSize, QSignalBlocker, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                             QMessageBox)

from FF8GameData.gamedata import GameData
from Joker.jokermanager import JokerManager, Sp2Quad


class JokerWidget(QWidget):
    """SP2 quad-list sprite table editor (face.sp2, cardanm.sp2, mngrp.bin Pos 4).

    An SP2 file maps sprite ids to lists of textured quads (UV/CLUT rectangle + draw offset);
    the texture itself is a TIM already uploaded to VRAM. The magazine/Chocobo World pictures
    live in mngrp.bin Pos 4 in the same format, loaded/saved in place through mngrphd.bin."""

    COLUMN_U = 0
    COLUMN_V = 1
    COLUMN_CLUT = 2
    COLUMN_WIDTH = 3
    COLUMN_HEIGHT = 4
    COLUMN_DX = 5
    COLUMN_DY = 6
    COLUMN_TEXPAGE = 7
    # (min, max, hexadecimal display) per column
    COLUMN_RULES = {
        COLUMN_U: (0, 255, False),
        COLUMN_V: (0, 255, False),
        COLUMN_CLUT: (0, 0xFFFF, True),
        COLUMN_WIDTH: (0, 0xFFFF, False),
        COLUMN_HEIGHT: (0, 0xFFFF, False),
        COLUMN_DX: (-128, 127, False),
        COLUMN_DY: (-128, 127, False),
        COLUMN_TEXPAGE: (0, 0xFFFF, True),
    }

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.manager = JokerManager(self.game_data)

        self.setWindowTitle("Joker")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a .sp2 file (face.sp2, cardanm.sp2)")
        self.load_button.clicked.connect(self.load_file)

        self.load_mngrp_button = QPushButton("mngrp")
        self.load_mngrp_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_mngrp_button.setIconSize(QSize(30, 30))
        self.load_mngrp_button.setFixedHeight(40)
        self.load_mngrp_button.setToolTip("Open the magazine picture sprites of a mngrp.bin (Pos 4 section, "
                                          "mngrphd.bin must be in the same folder)")
        self.load_mngrp_button.clicked.connect(self.load_mngrp)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened file (irreversible). "
                                    "In mngrp mode both mngrp.bin and mngrphd.bin are rewritten in place.")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.load_mngrp_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Sprite list (left side)
        self.sprite_list = QListWidget()
        self.sprite_list.setFixedWidth(180)
        self.sprite_list.currentRowChanged.connect(self.reload_selected_sprite)

        self.add_sprite_button = QPushButton("Add sprite id")
        self.add_sprite_button.setToolTip("Append a new sprite id at the end of the directory "
                                          "(the offset table is rebuilt on save)")
        self.add_sprite_button.clicked.connect(self.add_sprite)

        sprite_list_layout = QVBoxLayout()
        sprite_list_layout.addWidget(self.sprite_list)
        sprite_list_layout.addWidget(self.add_sprite_button)

        # Editor (right side)
        self.sprite_name_label = QLabel("")
        self.sprite_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.used_checkbox = QCheckBox("Sprite used")
        self.used_checkbox.setToolTip("Unchecked = unused id: its directory offset is written as 0 and no "
                                      "quads are saved (they are kept in memory until the file is closed)")
        self.used_checkbox.toggled.connect(self._on_used_toggled)

        self.quad_table = QTableWidget()
        self.quad_table.setColumnCount(8)
        self.quad_table.setHorizontalHeaderLabels(["U", "V", "CLUT", "Width", "Height",
                                                   "X offset", "Y offset", "Texpage"])
        self.quad_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.quad_table.verticalHeader().setVisible(True)
        self.quad_table.setToolTip("One row per quad. CLUT and Texpage are hexadecimal (the game masks "
                                   "Texpage with 0x9FF); X/Y offsets are signed bytes from the sprite "
                                   "draw position.")
        self.quad_table.itemChanged.connect(self._on_quad_item_changed)

        self.add_quad_button = QPushButton("Add quad")
        self.add_quad_button.clicked.connect(self.add_quad)
        self.remove_quad_button = QPushButton("Remove selected quad")
        self.remove_quad_button.clicked.connect(self.remove_quad)

        quad_button_layout = QHBoxLayout()
        quad_button_layout.addWidget(self.add_quad_button)
        quad_button_layout.addWidget(self.remove_quad_button)
        quad_button_layout.addStretch(1)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.sprite_name_label)
        editor_layout.addWidget(self.used_checkbox)
        editor_layout.addWidget(self.quad_table)
        editor_layout.addLayout(quad_button_layout)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addLayout(sprite_list_layout)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search .sp2 file",
                                                     filter="*.sp2", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_file(file_name)
        except ValueError as e:
            QMessageBox.critical(self, "Joker", f"Not a valid SP2 file:\n{e}")
            return
        self.file_label.setText(os.path.basename(file_name))
        self._reload_sprite_list()

    def load_mngrp(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mngrp.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_mngrp(file_name)
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, "Joker", f"Could not load the mngrp SP2 section:\n{e}")
            return
        self.file_label.setText(f"{os.path.basename(file_name)} (Pos 4 picture sprites)")
        self._reload_sprite_list()

    def save_file(self):
        if not self.manager.sp2:
            return
        if self.manager.is_mngrp_mode:
            self.manager.save_mngrp()
        elif self.manager.file_path:
            self.manager.save_file()

    def add_sprite(self):
        if not self.manager.sp2:
            return
        self.manager.sp2.add_sprite()
        self._reload_sprite_list(select_row=len(self.manager.sp2.sprites) - 1)

    def add_quad(self):
        sprite = self._selected_sprite()
        if not sprite:
            return
        # New quads start as a copy of the last one: SP2 quads of one sprite usually tile
        # the same texture region, so this is a better starting point than all zeros.
        if sprite.quads:
            last = sprite.quads[-1]
            sprite.quads.append(Sp2Quad(u=last.u, v=last.v, clut=last.clut, width=last.width,
                                        height=last.height, dx=last.dx, dy=last.dy, texpage=last.texpage))
        else:
            sprite.quads.append(Sp2Quad())
        self.reload_selected_sprite()
        self._refresh_sprite_label(sprite)

    def remove_quad(self):
        sprite = self._selected_sprite()
        if not sprite or not sprite.quads:
            return
        row = self.quad_table.currentRow()
        if row < 0:
            row = len(sprite.quads) - 1
        del sprite.quads[row]
        self.reload_selected_sprite()
        self._refresh_sprite_label(sprite)

    def reload_selected_sprite(self):
        sprite = self._selected_sprite()
        if not sprite:
            return
        self.sprite_name_label.setText(f"Sprite id {sprite.sprite_id}")
        with QSignalBlocker(self.used_checkbox):
            self.used_checkbox.setChecked(sprite.used)
        with QSignalBlocker(self.quad_table):
            self.quad_table.setRowCount(len(sprite.quads))
            for row, quad in enumerate(sprite.quads):
                values = [quad.u, quad.v, quad.clut, quad.width, quad.height, quad.dx, quad.dy, quad.texpage]
                for column, value in enumerate(values):
                    hexadecimal = self.COLUMN_RULES[column][2]
                    item = QTableWidgetItem(f"0x{value:04X}" if hexadecimal else str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.quad_table.setItem(row, column, item)
        self.quad_table.setEnabled(sprite.used)
        self.add_quad_button.setEnabled(sprite.used)
        self.remove_quad_button.setEnabled(sprite.used)

    def _reload_sprite_list(self, select_row=0):
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.sprite_list):
            self.sprite_list.clear()
            self.sprite_list.addItems([self._sprite_label(sprite) for sprite in self.manager.sp2.sprites])
        self.sprite_list.setCurrentRow(select_row)

    @staticmethod
    def _sprite_label(sprite):
        if not sprite.used:
            return f"ID {sprite.sprite_id} — unused"
        return f"ID {sprite.sprite_id} — {len(sprite.quads)} quad(s)"

    def _refresh_sprite_label(self, sprite):
        with QSignalBlocker(self.sprite_list):
            self.sprite_list.item(sprite.sprite_id).setText(self._sprite_label(sprite))

    def _selected_sprite(self):
        if not self.manager.sp2:
            return None
        index = self.sprite_list.currentRow()
        if 0 <= index < len(self.manager.sp2.sprites):
            return self.manager.sp2.sprites[index]
        return None

    def _on_used_toggled(self, checked):
        sprite = self._selected_sprite()
        if not sprite:
            return
        sprite.used = checked
        self._refresh_sprite_label(sprite)
        self.reload_selected_sprite()

    def _on_quad_item_changed(self, item):
        sprite = self._selected_sprite()
        if not sprite or item.row() >= len(sprite.quads):
            return
        minimum, maximum, hexadecimal = self.COLUMN_RULES[item.column()]
        try:
            value = int(item.text(), 0)  # base 0: accepts both decimal and 0x forms
        except ValueError:
            self.reload_selected_sprite()  # revert the bad input
            return
        value = max(minimum, min(maximum, value))
        quad = sprite.quads[item.row()]
        attribute = ["u", "v", "clut", "width", "height", "dx", "dy", "texpage"][item.column()]
        setattr(quad, attribute, value)
        with QSignalBlocker(self.quad_table):
            item.setText(f"0x{value:04X}" if hexadecimal else str(value))
