import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox

from FF8GameData.menu.magpicture import (PC_PICTURE_FILES, is_added_slot, is_page_picture_tim, pc_picture_name,
                                         slot_picture)
from Joker.jokermanager import Sp2File, Sp2Quad

PAGE_QUAD_CLUT = 0x36A0     # CLUT at VRAM (512,218), the page pictures' palette
PAGE_QUAD_TEXPAGE = 0x00AE  # texture page at VRAM (896,0), 8bpp, where the page picture sits
from Joker.sp2editorwidget import Sp2EditorWidget
from SmallWidget.spritecanvas import SpriteView


class ShivaSpriteWidget(QWidget):
    """The magazine picture sprites of mngrp.bin: the SP2 quad-list table of section 4.

    Same table format as a .sp2 file, so it reuses Joker's editor and Sp2File. Only this
    section is read and written back, the rest of mngrp.bin belongs to the other tabs.

    Beside the editor, the sprites are drawn over a page picture (the same view as Zone's sprite
    picker): every sprite cuts its rectangles out of whatever picture the page shows, so any page
    picture can be picked to see them on. Clicking a rectangle selects its sprite in the editor;
    editing a quad redraws it.
    """

    MNGRP_SP2_SECTION_ID = 4
    GAME_SPRITE_COUNT = 79  # the game's sprite ids (0-78): never removed; a mod's added ones can be
    DEFAULT_PICTURE_SLOT = 28  # mag00, Weapons Monthly's first picture

    def __init__(self):
        QWidget.__init__(self)
        self.sp2 = None
        self.manager = None
        self.menu_folder = ""

        self.sp2_editor = Sp2EditorWidget()
        self.sp2_editor.fixed_count = self.GAME_SPRITE_COUNT
        self.sp2_editor.new_quad = self.new_page_quad

        self.picture_combo = QComboBox()
        self.picture_combo.setToolTip("The page picture the sprites are drawn over: a sprite cuts from whatever\n"
                                      "picture its page shows, so any of them shows where the rectangles fall.")
        self.picture_combo.currentIndexChanged.connect(self._picture_changed)
        # The same view as Zone's sprite picker, with the picture choice in its header row
        self.view = SpriteView()
        self.view.add_header_widget(QLabel("Drawn over:"))
        self.view.add_header_widget(self.picture_combo)
        self.view.picked.connect(self._canvas_picked)
        self.canvas = self.view.canvas

        # Every edit of the table redraws the view (the editor changes the Sp2File in place)
        editor = self.sp2_editor
        editor.sprite_list.currentRowChanged.connect(self._refresh_canvas)
        editor.quad_table.itemChanged.connect(self._refresh_canvas)
        editor.used_checkbox.toggled.connect(self._refresh_canvas)
        for button in (editor.add_sprite_button, editor.remove_sprite_button, editor.add_quad_button,
                       editor.remove_quad_button):
            button.clicked.connect(self._refresh_canvas)

        # The view goes in the editor's own column, under the quad table (a sprite has a few quads:
        # the table needs only a few rows), instead of beside an editor left mostly empty
        editor.quad_table.setMaximumHeight(180)
        editor_layout = editor.editor_container.layout()
        editor_layout.addWidget(self.view)
        editor_layout.addStretch(1)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.sp2_editor)
        self.setLayout(main_layout)

    @staticmethod
    def new_page_quad():
        """A new sprite's first quad: a 128x96 rectangle at the top left of the page picture, with the
        texture page (896,0 8bpp) and CLUT (512,218) every magazine sprite uses, so it shows at once."""
        return Sp2Quad(u=0, v=0, clut=PAGE_QUAD_CLUT, width=128, height=96, dx=0, dy=0,
                       texpage=PAGE_QUAD_TEXPAGE)

    def load_from_mngrp(self, manager):
        self.manager = manager
        self.menu_folder = os.path.dirname(manager.mngrp_path) if getattr(manager, "mngrp_path", "") else ""
        section = manager.mngrp.get_section_by_id(self.MNGRP_SP2_SECTION_ID)
        self.sp2 = Sp2File.from_bytes(bytes(section.get_data_hex()))
        self.sp2_editor.set_sp2(self.sp2)
        self._fill_pictures()
        self._refresh_canvas()

    def save_to_mngrp(self, manager):
        if not self.sp2:
            return
        manager.mngrp.set_section_by_id_and_bytearray(self.MNGRP_SP2_SECTION_ID,
                                                      bytearray(self.sp2.to_bytes()))

    # --- the view ----------------------------------------------------------------------------

    def _picture_slots(self):
        """The page pictures of this mngrp.bin: the game's 30, then the added ones it holds."""
        slots = sorted(PC_PICTURE_FILES)
        entries = self.manager.mngrphd.get_entry_list() if self.manager is not None else []
        sections = self.manager.mngrp.get_section_list() if self.manager is not None else []
        # Past 185 only the slots holding a page picture: the game's 188-205 are other data
        slots += [slot for slot in range(len(entries)) if is_added_slot(slot) and not entries[slot].invalid_value
                  and is_page_picture_tim(sections[slot].get_data_hex())]
        return slots

    def _fill_pictures(self):
        current = self.picture_combo.currentData()
        self.picture_combo.blockSignals(True)
        self.picture_combo.clear()
        for slot in self._picture_slots():
            added = " (added)" if is_added_slot(slot) else ""
            self.picture_combo.addItem(f"{slot}: {pc_picture_name(slot)}{added}", slot)
        index = self.picture_combo.findData(current if current is not None else self.DEFAULT_PICTURE_SLOT)
        self.picture_combo.setCurrentIndex(max(index, 0))
        self.picture_combo.blockSignals(False)
        self._picture_changed()

    def _picture_changed(self, _index=None):
        slot = self.picture_combo.currentData()
        picture = None
        if slot is not None and self.manager is not None:
            tim_bytes = bytes(self.manager.mngrp.get_section_list()[slot].get_data_hex())
            picture, _origin = slot_picture(self.menu_folder, slot, tim_bytes)
        self.view.set_picture(picture)

    def _refresh_canvas(self, *_args):
        sprite = self.sp2_editor._selected_sprite()
        self.canvas.selected_id = sprite.sprite_id if sprite is not None else -1
        self.view.set_sprites(self.sp2.sprites if self.sp2 else [])

    def _canvas_picked(self, sprite_id):
        """A rectangle clicked: select its sprite in the editor (its row is its id), which redraws."""
        if self.sp2 and 0 <= sprite_id < len(self.sp2.sprites):
            self.sp2_editor.sprite_list.setCurrentRow(sprite_id)
