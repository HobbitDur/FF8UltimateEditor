from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)

from Joker.jokermanager import Sp2Quad


class Sp2EditorWidget(QWidget):
    """The sprite list and quad table of an SP2 quad-list table.

    An SP2 table maps sprite ids to lists of textured quads (UV/CLUT rectangle + draw offset);
    the texture itself is a TIM already uploaded to VRAM. The same table exists as a file
    (face.sp2, cardanm.sp2) and as a section inside mngrp.bin, so this editor knows nothing
    about files: it is given an Sp2File and edits it in place. Joker hosts it for a .sp2 file,
    Shiva for the section of mngrp.bin holding the magazine picture sprites.
    """

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

    def __init__(self):
        QWidget.__init__(self)
        self.sp2 = None

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

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(sprite_list_layout)
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

    def set_sp2(self, sp2, select_row=0):
        """Edit that SP2 table. It is modified in place, the host saves it where it came from."""
        self.sp2 = sp2
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.sprite_list):
            self.sprite_list.clear()
            self.sprite_list.addItems([self._sprite_label(sprite) for sprite in self.sp2.sprites])
        self.sprite_list.setCurrentRow(select_row)

    def add_sprite(self):
        if not self.sp2:
            return
        self.sp2.add_sprite()
        self.set_sp2(self.sp2, select_row=len(self.sp2.sprites) - 1)

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

    @staticmethod
    def _sprite_label(sprite):
        if not sprite.used:
            return f"ID {sprite.sprite_id} — unused"
        return f"ID {sprite.sprite_id} — {len(sprite.quads)} quad(s)"

    def _refresh_sprite_label(self, sprite):
        with QSignalBlocker(self.sprite_list):
            self.sprite_list.item(sprite.sprite_id).setText(self._sprite_label(sprite))

    def _selected_sprite(self):
        if not self.sp2:
            return None
        index = self.sprite_list.currentRow()
        if 0 <= index < len(self.sp2.sprites):
            return self.sp2.sprites[index]
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
