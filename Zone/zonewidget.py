import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QGroupBox, QMessageBox, QSpinBox, QComboBox, QCheckBox,
                             QGridLayout, QScrollArea, QFormLayout, QPushButton, QPlainTextEdit,
                             QFileDialog)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.kernelnamesource import KernelNameSource
from Common.pagefontsource import PageFontSource
from FF8GameData.gamedata import GameData
from FF8GameData.menu.magpage import (MagPageEntry, UNUSED_ID, VANILLA_PAPER_E1, VANILLA_PAPER_E2,
                                      paper_tile_vram)
from FF8GameData.menu.magpicture import is_added_slot, pc_picture_file_name
from SmallWidget.listsearchbar import ListSearchBar
from SmallWidget.fitwidth import fit_combo, fit_combo_popup, fit_list_width
from SmallWidget.valuecombo import ValueComboBox
from Zone.zonemanager import (ZoneManager, TEXTURE_CATEGORIES, DUEL_MOVE_NAMES,
                              ANGELO_MOVE_NAMES, BOOK_TEXT_FIRST_RAW_FILE)
from Zone.zonerender import (PageRenderer, BUTTON_STYLE_BOXES, BUTTON_STYLE_ICONS,
                             CANVAS_WIDTH, CANVAS_HEIGHT)

PREVIEW_SCALE = 2

# The book text a page's text overlays read (mngrp raw file 87 + this). The Item menu's magazines
# always read 87, whatever the page says; the tutorial books read theirs.
BOOK_TEXT_FILES = [
    (0, "0: Book text (raw 87, the magazines)"),
    (1, "1: Battle tutorial (raw 88)"),
    (2, "2: Card rules and icons (raw 89)"),
    (3, "3: Chocobo World tutorial (raw 90)"),
]

# Menu_Magazine_LoadPageTexture adds a base slot only for the categories 0-6: any other value is
# "the page number is the slot". 7 is the first such value.
DIRECT_TEXTURE_CATEGORY = 7

# The file this editor edits. The open dialog filters on its exact name.
MAIN_FILE = "mmag.bin"

# The rest of the page is spread over other files, each edited in another tool and read
# here read-only through the registry (shared in every direction). Exact name -> what it
# adds. Each only fills in its own part of the manager, which the renderer reads as it draws.
COMPLEMENTARY_FILES = {
    "mngrp.bin": "the page art, the overlay sprites and the book text (needs mngrphd.bin beside it); "
                 "the book text and the pictures are edited here too",
    "kernel.bin": "Zell's Duel button combos, drawn on the Combat King pages",
    "mwepon.bin": "the weapon remodel item lists, drawn on the Weapons Monthly pages",
    "icon.sp1": "the button and item icons of those two lists (needs icon.TEX beside it)",
    "mitem.bin": "which type icon each remodel item uses",
    "sysfnt.TEX": "the menu font's glyphs, for the page text (boxes without it)",
    "sysfnt.tdw": "the menu font's glyph widths, for the page text",
}


class ZoneWidget(QWidget):
    """mmag.bin editor: the in-menu magazine page definitions (Weapons Monthly,
    Combat King, Pet Pals, Occult Fan and the tutorial-menu books). Each entry
    describes one page view: text window, page picture, unlock fields and up to
    4 picture + 4 text overlays. Load mngrp.bin to preview the overlay texts.

    Named after Zone, the Forest Owls member and devoted magazine collector."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry

        self.game_data = GameData(game_data_folder)
        self.game_data.load_sysfnt_data()  # for the mngrp book-text preview
        self.manager = ZoneManager(self.game_data)
        self.current_entry_index = -1
        self.renderer = None  # Built once mngrp.bin is loaded (it carries the art)

        self.setWindowTitle("Zone")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # Files, driven by the shared header toolbar. mmag.bin is the edited file. mngrp.bin is a
        # complementary file Zone also edits - the book text and the page pictures, so a whole book
        # is made here - written by the shared Save only when one of those changed. The four others
        # (kernel/mwepon/icon.sp1/mitem) only decorate the pages and are read-only here - each is
        # edited in another tool (SolomonRing/Junkshop/Minimog/Kadowaki) and shared in every
        # direction through the registry.
        self.mmag_binding = FileBinding(MAIN_FILE, file_registry,
                                        load_callback=self.load_file, save_callback=self.save_file)
        self.companion_bindings = {
            "mngrp.bin": FileBinding("mngrp.bin", file_registry, load_callback=self._apply_mngrp,
                                     save_callback=self._save_mngrp, complementary=True),
            "kernel.bin": FileBinding("kernel.bin", file_registry, load_callback=self._apply_kernel,
                                      read_only=True),
            "mwepon.bin": FileBinding("mwepon.bin", file_registry, load_callback=self._apply_mwepon,
                                      read_only=True),
            "icon.sp1": FileBinding("icon.sp1", file_registry, load_callback=self._apply_icons,
                                    read_only=True),
            "mitem.bin": FileBinding("mitem.bin", file_registry, load_callback=self._apply_mitem,
                                     read_only=True),
        }
        # The menu font: two more side files, opened like the others (never looked up elsewhere)
        self.font_source = PageFontSource(file_registry)
        self.companion_bindings["sysfnt.TEX"] = self.font_source.tex_binding
        self.companion_bindings["sysfnt.tdw"] = self.font_source.tdw_binding
        self.font_source.changed.connect(self._on_font_changed)
        # The same kernel.bin also names the weapons - the only source of those names.
        self.kernel_names = KernelNameSource(self.game_data, file_registry,
                                             binding=self.companion_bindings["kernel.bin"])
        self.kernel_names.changed.connect(self._on_kernel_names_changed)

        # Entry list (left), with a Ctrl+F search bar filtering it
        self.entry_list = QListWidget()
        self.entry_list.setFixedWidth(240)
        self.entry_list.currentRowChanged.connect(self._entry_changed)
        self.entry_search = ListSearchBar.wrap(self.entry_list)
        self.entry_search.column.layout().addWidget(self._build_page_buttons())

        # Entry form (right, scrollable)
        form_widget = QWidget()
        form_layout = QVBoxLayout()
        form_layout.addWidget(self._build_window_group())
        form_layout.addWidget(self._build_picture_group())
        form_layout.addWidget(self._build_text_and_texture_group())
        # Fields not studied enough to edit safely (only their retail values are known to work)
        # are greyed out by default, as in SolomonRing and the mmag2.bin tab; this box unlocks them.
        self.unlock_check = QCheckBox("Unlock fields not studied yet (paper tile E1 / E2)")
        self.unlock_check.setToolTip(
            "Off (default): the paper tile bytes E1 / E2 are shown, greyed out. Only the retail 0x00 / 0xC0\n"
            "(the parchment) is known to work: other values tile another part of VRAM (the page picture or\n"
            "the menu graphics, in the paper's palette, so in the wrong colours), and the PC port is untested.\n"
            "On: they become editable. Loading and saving are identical either way.")
        self.unlock_check.toggled.connect(self._set_unlock_unstudied)
        self._set_unlock_unstudied(False)
        form_layout.insertWidget(0, self.unlock_check)
        form_layout.addWidget(self._build_unlock_group())
        form_layout.addWidget(self._build_overlays_group())
        form_layout.addStretch(1)
        form_widget.setLayout(form_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)

        self.editor_container = QWidget()
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.entry_search.column)
        editor_layout.addWidget(scroll, 1)  # the form takes the spare width: the preview has a fixed size
        editor_layout.addWidget(self._build_preview_group())
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

        self._connect_live_preview()
        # Pick up anything another tool already opened: mmag.bin, or any of the shared companions
        # (e.g. mngrp.bin from Shiva, kernel.bin from SolomonRing).
        self.mmag_binding.load_opened_file()
        for binding in self.companion_bindings.values():
            binding.load_opened_file()

    def file_bindings(self):
        """The files the shared header toolbar drives for this tab: mmag.bin (edited) and the
        read-only complementary files it renders from (mngrp.bin's book text and pictures are
        edited here too)."""
        return [self.mmag_binding, *self.companion_bindings.values()]

    def _build_page_buttons(self):
        """"+ Add page" / "- Remove last page" under the page list: a new book's pages go at the end."""
        self.add_page_button = QPushButton("+ Add page (copy of this one)")
        self.remove_page_button = QPushButton("- Remove last page")
        self.page_count_label = QLabel()
        self.page_count_label.setStyleSheet("font-size: 9pt;")
        self.page_count_label.setWordWrap(True)
        tooltip = ("A new book is a range of pages at the end of mmag.bin: add them here, then point its\n"
                   "item at the first and last one (Kadowaki, item type \"Magazine\"). A page starts as a\n"
                   "copy of the selected one, so its layout, picture and texts are there to edit.\n"
                   f"Up to {ZoneManager.MAX_ENTRY_COUNT} pages (a page number is one byte). Only the pages "
                   f"added after the game's {ZoneManager.VANILLA_ENTRY_COUNT} can be removed, from the last one.")
        for widget in (self.add_page_button, self.remove_page_button, self.page_count_label):
            widget.setToolTip(tooltip)
        self.add_page_button.clicked.connect(self._add_page)
        self.remove_page_button.clicked.connect(self._remove_last_page)
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.add_page_button)
        layout.addWidget(self.remove_page_button)
        layout.addWidget(self.page_count_label)
        self._update_page_buttons()
        return box

    def _update_page_buttons(self):
        count = len(self.manager.entries)
        self.add_page_button.setEnabled(self.manager.can_add_entry())
        self.remove_page_button.setEnabled(self.manager.can_remove_entry())
        self.page_count_label.setText(f"{count} / {ZoneManager.MAX_ENTRY_COUNT} pages (0-{count - 1})"
                                      if count else "")

    def _add_page(self):
        self._apply_form_to_entry()
        index = self.manager.add_entry(copy_of=self.current_entry_index)
        if index is None:
            return
        self.entry_list.addItem(f"{index}: {self.manager.entry_name(index)}")
        fit_list_width(self.entry_list)
        self.entry_list.setCurrentRow(index)
        self._update_page_buttons()
        self._mark_edited()

    def _remove_last_page(self):
        self._apply_form_to_entry()
        if not self.manager.remove_last_entry():
            return
        last = self.entry_list.count() - 1
        if self.current_entry_index == last:
            self.current_entry_index = -1  # Its form must not be written into the page now gone
        self.entry_list.takeItem(last)
        self._update_page_buttons()
        self._mark_edited()

    def _mark_edited(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    def _build_preview_group(self):
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(CANVAS_WIDTH * PREVIEW_SCALE, CANVAS_HEIGHT * PREVIEW_SCALE)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setText("Open mmag.bin to render a page")
        self.preview_label.setToolTip(
            "The page as the menu draws it, redrawn as you edit. The art, the paper mat and the "
            "text are the real thing; the window background is a flat stand-in "
            "(see Zone/zonerender.py).")

        # The engine picks the Duel button glyph through the player's key config, so
        # there is no single right answer here: let whoever is looking decide.
        self.button_icon_combo = QComboBox()
        self.button_icon_combo.addItem("PlayStation pad (icon.sp1)", BUTTON_STYLE_ICONS)
        self.button_icon_combo.addItem("Plain boxes", BUTTON_STYLE_BOXES)
        self.button_icon_combo.setToolTip(
            "<b>Which glyph to draw for Zell's Duel combo.</b><br><br>"
            "This is a setup from the game, not something mmag.bin decides: the engine looks the "
            "button icons up through the player's <b>key config</b>, so two players can see "
            "different glyphs on the same Combat King page.<br><br>"
            "<b>PlayStation pad</b> draws what icon.sp1 ships with (ids 128-143), which is the "
            "default.<br>"
            "<b>Plain boxes</b> claims nothing and just shows where the buttons land.")
        self.button_icon_combo.currentIndexChanged.connect(self._button_icon_style_changed)

        # A render is ~5 ms, so this only coalesces bursts (holding a spin box arrow,
        # typing a value): 40 ms is well under the threshold where a redraw stops
        # feeling immediate.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(40)
        self._preview_timer.timeout.connect(self._refresh_preview)

        group = QGroupBox("Page preview")
        layout = QVBoxLayout()
        layout.addWidget(self.preview_label)
        # Says which font side file is missing (the text is boxes without them)
        self.font_notice = QLabel(self.font_source.notice())
        self.font_notice.setWordWrap(True)
        self.font_notice.setStyleSheet("color: #c07000;")
        self.font_notice.setMaximumWidth(CANVAS_WIDTH * PREVIEW_SCALE)
        layout.addWidget(self.font_notice)
        button_icon_layout = QHBoxLayout()
        button_icon_layout.addWidget(QLabel("Duel buttons:"))
        button_icon_layout.addWidget(self.button_icon_combo)
        button_icon_layout.addStretch(1)
        layout.addLayout(button_icon_layout)
        layout.addStretch(1)
        group.setLayout(layout)
        return group

    def _button_icon_style_changed(self):
        if self.renderer is not None:
            self.renderer.button_icon_style = self.button_icon_combo.currentData()
        self._refresh_preview()

    def _connect_live_preview(self):
        """Redraw the preview whenever any form value changes.

        _fill_form_from_entry blocks these signals while it repopulates the form,
        so switching entries redraws once (from _entry_changed) rather than once
        per field."""
        for widget in self._form_widgets():
            if isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._schedule_preview)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._schedule_preview)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._schedule_preview)

    def _schedule_preview(self):
        self._preview_timer.start()  # Restarts the countdown on every change

    @staticmethod
    def _spin16():
        spin = QSpinBox()
        spin.setRange(0, 0xFFFF)
        return spin

    @staticmethod
    def _spin8(hex_display=False):
        spin = QSpinBox()
        spin.setRange(0, 0xFF)
        if hex_display:
            spin.setDisplayIntegerBase(16)
            spin.setPrefix("0x")
        return spin

    def _build_window_group(self):
        self.window_x = self._spin16()
        self.window_y = self._spin16()
        self.window_w = self._spin16()
        self.window_h = self._spin16()
        group = QGroupBox("Text window (retail: 24,8 336x184/208)")
        layout = QHBoxLayout()
        for label, spin in (("X", self.window_x), ("Y", self.window_y),
                            ("Width", self.window_w), ("Height", self.window_h)):
            layout.addWidget(QLabel(label))
            layout.addWidget(spin)
        layout.addStretch(1)
        group.setLayout(layout)
        return group

    def _build_picture_group(self):
        self.pic_x = self._spin16()
        self.pic_y = self._spin16()
        self.pic_w = self._spin16()
        self.pic_h = self._spin16()
        self.pic_tint_r = self._spin8()
        self.pic_tint_g = self._spin8()
        self.pic_tint_b = self._spin8()
        group = QGroupBox("Paper mat: the tinted rectangle drawn behind the page art "
                          "(width/height 0 = not drawn; the tint is /128, multiplied by the zoom)")
        layout = QHBoxLayout()
        for label, spin in (("X", self.pic_x), ("Y", self.pic_y),
                            ("Width", self.pic_w), ("Height", self.pic_h),
                            ("Tint R", self.pic_tint_r), ("Tint G", self.pic_tint_g),
                            ("Tint B", self.pic_tint_b)):
            layout.addWidget(QLabel(label))
            layout.addWidget(spin)
        layout.addStretch(1)
        group.setLayout(layout)
        return group

    def _build_text_and_texture_group(self):
        paper_tip = (
            "Where the paper the window is tiled with is read from in VRAM: a 32x32 tile, repeated.\n"
            "E1 (byte 0x13) is its X, E2 (byte 0x14) its Y; the game builds the GPU texture page (E1)\n"
            "and texture window (E2) of the paper sprites from them. Every retail page has 0x00 / 0xC0:\n"
            "VRAM (896,192), the parchment tile (mngrp.bin raw file 12).\n"
            "Another value reads another part of VRAM (e.g. E2 0x00-0xA0: a piece of the page picture,\n"
            "with the paper's palette, so in the wrong colours). The preview always draws the parchment.")
        self.paper_a = self._spin8(hex_display=True)
        self.paper_a.setToolTip(paper_tip)
        self.paper_b = self._spin8(hex_display=True)
        self.paper_b.setToolTip(paper_tip)
        self.paper_label = QLabel()

        self.text_file = ValueComboBox(fallback="another mngrp.bin string section")
        self.text_file.set_choices(BOOK_TEXT_FILES)
        self.text_file.valueChanged.connect(self._text_file_changed)
        self.text_file_label = QLabel()

        self.texture_category = QComboBox()
        for category, (name, _base) in TEXTURE_CATEGORIES.items():
            self.texture_category.addItem(f"{category}: {name}", category)
        # Any other category takes the page number as the mngrp slot itself
        self.texture_category.addItem(f"{DIRECT_TEXTURE_CATEGORY}: Direct slot (page = mngrp raw file)",
                                      DIRECT_TEXTURE_CATEGORY)
        self.texture_category.setToolTip(
            "Which picture the page shows: a mngrp.bin slot, the category's first slot + the page.\n"
            "On PC only 30 slots have a picture (menu/mag00-19.TEX and mc00-09.TEX), plus the slots 185-255\n"
            "of the pictures added with FFNx's AddMorePictures; the page list shows those it can reach.")
        self.texture_category.currentIndexChanged.connect(self._texture_category_changed)
        fit_combo(self.texture_category, 18)
        self.texture_page = ValueComboBox(fallback="no picture on PC")
        self.texture_page.setToolTip("The pictures this category reaches (page = slot - its first slot). A value\n"
                                     "kept from the file but showing no picture on PC is marked so.")
        self.texture_page.valueChanged.connect(self._update_resolved_labels)
        self.texture_label = QLabel()

        self.footer_flag = QCheckBox("Draw the footer line (the “to scroll” hint of the multi-page books)")

        group = QGroupBox("Paper, book text and page texture")
        layout = QFormLayout()
        paper_layout = QHBoxLayout()
        paper_layout.addWidget(QLabel("E1 (X)"))
        paper_layout.addWidget(self.paper_a)
        paper_layout.addWidget(QLabel("E2 (Y)"))
        paper_layout.addWidget(self.paper_b)
        paper_layout.addWidget(self.paper_label)
        paper_layout.addStretch(1)
        layout.addRow("Paper tile in VRAM:", paper_layout)
        self.paper_a.valueChanged.connect(self._update_paper_label)
        self.paper_b.valueChanged.connect(self._update_paper_label)
        self._update_paper_label()
        text_layout = QHBoxLayout()
        text_layout.addWidget(self.text_file)
        text_layout.addWidget(self.text_file_label)
        text_layout.addStretch(1)
        layout.addRow("Text file index:", text_layout)
        texture_layout = QHBoxLayout()
        texture_layout.addWidget(self.texture_category)
        texture_layout.addWidget(QLabel("Page"))
        texture_layout.addWidget(self.texture_page)
        texture_layout.addWidget(self.texture_label)
        texture_layout.addStretch(1)
        layout.addRow("Page texture:", texture_layout)

        self.replace_picture_button = QPushButton("Replace picture from PNG...")
        self.replace_picture_button.setToolTip(
            "Put a 256x192 image (a 256x256 one is cropped to its top 192 rows) in this page's picture\n"
            "slot, reduced to 255 colours; alpha under 128 is transparent. Save writes the .TEX the PC\n"
            "game shows and the copy in mngrp.bin. Every page on this slot shows the new picture, the\n"
            "game's own pages included. The picture overlays crop it with the Sprites of Shiva.")
        self.replace_picture_button.clicked.connect(self._replace_picture)
        self.export_picture_button = QPushButton("Export picture...")
        self.export_picture_button.clicked.connect(self._export_picture)
        self.add_picture_button = QPushButton("Add new picture from PNG...")
        self.add_picture_button.setToolTip(
            "Add a picture of its own for this page (256x192), in the next free mngrp.bin slot (206-255),\n"
            "and point the page at it. Save writes its menu/magNNN.TEX and its copy in mngrp.bin.\n"
            "In game it needs FFNx with AddMorePictures: the game alone only shows its 30 pictures.")
        self.add_picture_button.clicked.connect(self._add_picture)
        picture_layout = QHBoxLayout()
        picture_layout.addWidget(self.add_picture_button)
        picture_layout.addWidget(self.replace_picture_button)
        picture_layout.addWidget(self.export_picture_button)
        picture_layout.addStretch(1)
        layout.addRow("", picture_layout)
        layout.addRow("", self.footer_flag)
        group.setLayout(layout)
        return group

    def _build_unlock_group(self):
        self.weapon_combo = QComboBox()
        self.weapon_notice = KernelNameSource.make_notice("weapon")

        self.duel_combo = QComboBox()
        self.duel_combo.addItem("None", UNUSED_ID)
        for move_id, name in enumerate(DUEL_MOVE_NAMES):
            self.duel_combo.addItem(f"{move_id}: {name}", move_id)

        self.angelo_combo = QComboBox()
        self.angelo_combo.addItem("None", UNUSED_ID)
        for move_id, name in enumerate(ANGELO_MOVE_NAMES):
            self.angelo_combo.addItem(f"{move_id}: {name}", move_id)
        fit_combo(self.weapon_combo, 18)  # the names in full (the weapon list is refilled later)
        fit_combo(self.duel_combo, 18)
        fit_combo(self.angelo_combo, 18)

        self.weapon_spacing = self._spin8()
        self.weapon_list_x = self._spin16()
        self.weapon_list_y = self._spin8()
        self.weapon_qty_x = self._spin8()
        self.duel_x = self._spin16()
        self.duel_y = self._spin8()

        group = QGroupBox("Unlocks (item-menu reader only: reading the page unlocks these)")
        layout = QFormLayout()
        weapon_layout = QHBoxLayout()
        weapon_layout.addWidget(self.weapon_combo)
        weapon_layout.addWidget(QLabel("List X"))
        weapon_layout.addWidget(self.weapon_list_x)
        weapon_layout.addWidget(QLabel("Y"))
        weapon_layout.addWidget(self.weapon_list_y)
        weapon_layout.addWidget(QLabel("Qty column +X"))
        weapon_layout.addWidget(self.weapon_qty_x)
        weapon_layout.addWidget(QLabel("Line spacing"))
        weapon_layout.addWidget(self.weapon_spacing)
        weapon_layout.addStretch(1)
        layout.addRow("Weapon (mwepon line):", weapon_layout)
        layout.addRow("", self.weapon_notice)
        duel_layout = QHBoxLayout()
        duel_layout.addWidget(self.duel_combo)
        duel_layout.addWidget(QLabel("Combo X"))
        duel_layout.addWidget(self.duel_x)
        duel_layout.addWidget(QLabel("Y"))
        duel_layout.addWidget(self.duel_y)
        duel_layout.addStretch(1)
        layout.addRow("Zell Duel move:", duel_layout)
        layout.addRow("Angelo move:", self.angelo_combo)
        group.setLayout(layout)
        # Only now: the notice is shown while no kernel.bin is open, and a label shown before it
        # has a parent pops up as its own little window for an instant at start-up
        self._fill_weapon_combo(UNUSED_ID)
        return group

    def _build_overlays_group(self):
        self.new_line_buttons = []
        group = QGroupBox("Overlays (id 255 = unused slot)")
        layout = QGridLayout()
        layout.addWidget(QLabel("<b>Picture overlays (SP2 sprite)</b>"), 0, 0, 1, 7)
        self.pic_overlay_spins = self._build_overlay_rows(layout, row_start=1)
        row = 1 + MagPageEntry.NB_OVERLAY_SLOTS
        layout.addWidget(QLabel("<b>Text overlays (book-text line, edited in place)</b>"), row, 0, 1, 7)
        self.text_overlay_spins = self._build_overlay_rows(layout, row_start=row + 1,
                                                           with_preview=True)
        group.setLayout(layout)
        return group

    def _build_overlay_rows(self, layout, row_start, with_preview=False):
        spins = []
        for slot in range(MagPageEntry.NB_OVERLAY_SLOTS):
            # A text slot takes two rows: its fields, then its line's editor under them
            row = row_start + slot * (2 if with_preview else 1)
            x_spin = self._spin16()
            y_spin = self._spin8()
            # The id picks a sprite of the picture (its size shown) or a book text line (its start)
            id_spin = ValueComboBox(fallback="no such line" if with_preview else "no such sprite")
            id_spin.setMinimumWidth(170)
            id_spin.set_choices([(UNUSED_ID, f"{UNUSED_ID}: unused")])
            id_spin.setToolTip("A book text line of the page's text file: its id and its start" if with_preview else
                               "A sprite of the SP2 table (Shiva, Sprites): a rectangle cropped out of the page's\n"
                               "picture, its id and its size. The size is the sprite's, not the page's: drawn 1:1.")
            layout.addWidget(QLabel(f"Slot {slot + 1}"), row, 0)
            layout.addWidget(QLabel("X"), row, 1)
            layout.addWidget(x_spin, row, 2)
            layout.addWidget(QLabel("Y"), row, 3)
            layout.addWidget(y_spin, row, 4)
            layout.addWidget(QLabel("ID"), row, 5)
            layout.addWidget(id_spin, row, 6)
            preview = None
            if with_preview:
                # The line itself, edited in place in mngrp.bin's book text
                preview = QPlainTextEdit()
                preview.setFixedHeight(56)
                preview.setMinimumWidth(240)
                preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                preview.setPlaceholderText("unused slot (id 255)")
                preview.setToolTip("The book text line this slot shows, edited in mngrp.bin (written at Save).\n"
                                   "A line can be shown by several pages: they all show the edit.")
                preview.textChanged.connect(lambda s=slot: self._text_edited(s))
                layout.addWidget(preview, row + 1, 1, 1, 6)
                new_line = QPushButton("New line")
                new_line.setToolTip("Add a line at the end of the book text (the next id) and show it here")
                new_line.clicked.connect(lambda _checked=False, s=slot: self._new_text_line(s))
                layout.addWidget(new_line, row, 7)
                self.new_line_buttons.append(new_line)
                id_spin.valueChanged.connect(self._update_resolved_labels)
            spins.append((x_spin, y_spin, id_spin, preview))
        return spins

    # --- the choice lists (filled from mngrp.bin: pictures, sprites, book text lines) ----------

    def _text_file_changed(self, _value):
        self._refresh_text_choices()
        self._update_resolved_labels()

    def _texture_category_changed(self, _index):
        self._refresh_page_choices()
        self._update_resolved_labels()

    def _refresh_choices(self):
        self._refresh_page_choices()
        self._refresh_sprite_choices()
        self._refresh_text_choices()

    def _refresh_page_choices(self):
        """The pages this category reaches that show a picture on PC: page = slot - its first slot."""
        category = self.texture_category.currentData()
        base = TEXTURE_CATEGORIES[category][1] if category in TEXTURE_CATEGORIES else 0
        choices = []
        for page in range(256):
            slot = base + page
            if slot > 255:
                break
            name = pc_picture_file_name(slot)
            if name is None or (is_added_slot(slot) and not self.manager.has_slot(slot)):
                continue
            added = " (added)" if is_added_slot(slot) else ""
            label = f"{page}: {name}{added}" if category in TEXTURE_CATEGORIES else f"{slot}: {name}{added}"
            choices.append((page, label))
        self.texture_page.set_choices(choices)

    def _refresh_sprite_choices(self):
        choices = [(UNUSED_ID, f"{UNUSED_ID}: unused")]
        sprites = self.manager.get_sp2_sprites() if self.manager.mngrp_loaded else None
        for sprite in sprites or []:
            if not sprite.used or not sprite.quads or sprite.sprite_id == UNUSED_ID:
                continue
            width = max(q.dx + q.width for q in sprite.quads) - min(q.dx for q in sprite.quads)
            height = max(q.dy + q.height for q in sprite.quads) - min(q.dy for q in sprite.quads)
            choices.append((sprite.sprite_id, f"{sprite.sprite_id}: {width}x{height}"))
        for _x_spin, _y_spin, id_spin, _preview in self.pic_overlay_spins:
            id_spin.set_choices(choices)

    @staticmethod
    def _line_label(text_id, text):
        text = " ".join(text.replace("\\n", " / ").split()) or "(empty)"  # the titles pad with spaces
        return f"{text_id}: {text[:36] + '...' if len(text) > 36 else text}"

    def _refresh_text_choices(self):
        texts = self.manager.get_book_texts(self.text_file.value()) if self.manager.mngrp_loaded else []
        choices = [(UNUSED_ID, f"{UNUSED_ID}: unused")]
        choices += [(text_id, self._line_label(text_id, text)) for text_id, text in enumerate(texts)
                    if text_id != UNUSED_ID]
        for _x_spin, _y_spin, id_spin, _preview in self.text_overlay_spins:
            id_spin.set_choices(choices)

    def _picture_slot(self):
        category = self.texture_category.currentData()
        if category in TEXTURE_CATEGORIES:
            return TEXTURE_CATEGORIES[category][1] + self.texture_page.value()
        return self.texture_page.value()

    def _replace_picture(self):
        path, _ = QFileDialog.getOpenFileName(self, "Picture for this page's slot", "", "Images (*.png *.bmp)")
        if path:
            self.replace_picture_from_file(path)

    def replace_picture_from_file(self, path):
        """Replace the picture of the selected page's slot from an image file. False (with a
        message) when the slot or the image cannot be."""
        from PIL import Image
        raw_file = self._picture_slot()
        try:
            with Image.open(path) as image:
                self.manager.replace_picture(raw_file, image)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Zone - page picture", f"Cannot use {os.path.basename(path)}:\n{error}")
            return False
        if self.renderer is not None:
            self.renderer._tim_cache.pop(raw_file, None)
        self._mark_edited()
        self._schedule_preview()
        return True

    def _add_picture(self):
        path, _ = QFileDialog.getOpenFileName(self, "New picture for this page", "", "Images (*.png *.bmp)")
        if path:
            self.add_picture_from_file(path)

    def add_picture_from_file(self, path):
        """Add a new picture from an image file and show it on the selected page. Its slot, None
        (with a message) when it cannot be added."""
        from PIL import Image
        try:
            with Image.open(path) as image:
                slot = self.manager.add_picture(image)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Zone - new picture", f"Cannot add {os.path.basename(path)}:\n{error}")
            return None
        if self.renderer is not None:
            self.renderer._tim_cache.pop(slot, None)
        self._set_combo_data(self.texture_category, DIRECT_TEXTURE_CATEGORY, "")
        self._refresh_page_choices()  # the new picture is one of them now
        self.texture_page.setValue(slot)  # -> the labels and the preview follow
        self._mark_edited()
        self._update_resolved_labels()
        self._schedule_preview()
        return slot

    def _export_picture(self):
        raw_file = self._picture_slot()
        image, _origin = self.manager.picture(raw_file)
        if image is None:
            return
        name = os.path.splitext(pc_picture_file_name(raw_file) or f"slot{raw_file}")[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export the picture", f"{name}.png", "PNG (*.png)")
        if path:
            image.save(path)

    def _text_edited(self, slot):
        """The user typed in a text overlay's line: write it into the book text and redraw."""
        _x_spin, _y_spin, id_spin, editor = self.text_overlay_spins[slot]
        text_id = id_spin.value()
        if text_id == UNUSED_ID or not self.manager.mngrp_loaded:
            return
        if self.manager.set_book_text(text_id, editor.toPlainText(), self.text_file.value()):
            label = self._line_label(text_id, self.manager.to_game_text(editor.toPlainText()))
            for _x, _y, other_id_spin, _editor in self.text_overlay_spins:
                other_id_spin.set_label(text_id, label)
            self._mark_edited()
            self._schedule_preview()

    def _new_text_line(self, slot):
        text_id = self.manager.add_book_text("", self.text_file.value())
        if text_id is None:
            QMessageBox.warning(self, "Zone - book text",
                                "No line can be added: open mngrp.bin, or this book text already holds the "
                                "256 lines the pages can point at.")
            return
        self._mark_edited()
        self._refresh_text_choices()  # the new line is one of them now
        _x_spin, _y_spin, id_spin, editor = self.text_overlay_spins[slot]
        id_spin.setValue(text_id)  # -> the labels and the preview follow
        editor.setFocus()

    def load_file(self, file_name):
        """Load mmag.bin, the file this editor edits (path from the shared file toolbar)."""
        try:
            self._load_mmag(file_name)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Could not load {os.path.basename(file_name)}:\n{e}")
            return
        self._refresh_preview()

    def _load_mmag(self, file_name):
        self.manager.load_file(file_name)
        self.editor_container.setEnabled(True)
        self.current_entry_index = -1
        self.entry_list.clear()
        for index in range(len(self.manager.entries)):
            self.entry_list.addItem(f"{index}: {self.manager.entry_name(index)}")
        fit_list_width(self.entry_list)  # every page name shown in full
        self._update_page_buttons()
        self.entry_search.select_first_match()  # Row 0, or the first match if a search is typed in
        self._autoload_complementary(file_name)

    def _autoload_complementary(self, main_path):
        """Share each complementary file that sits next to the opened mmag.bin, so a page renders
        straight away and the tool that edits each one picks it up too. One another tool already
        shared is kept (single source of truth)."""
        folder = os.path.dirname(main_path)
        for name, binding in self.companion_bindings.items():
            if binding.current_path:  # keep whatever another tool already shared
                continue
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                binding.open_path(candidate)  # publish -> load here and in the tool that edits it

    def _apply_mngrp(self, file_name):
        """Load a shared mngrp.bin (its binding's callback). The font is not taken from its
        folder: sysfnt.TEX / sysfnt.tdw are side files of their own (font_source)."""
        try:
            self.manager.load_mngrp(file_name)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Could not load mngrp.bin", str(e))
            return
        self.renderer = PageRenderer(self.manager, button_icon_style=self.button_icon_combo.currentData())
        self.font_source.apply_to(self.renderer)
        self._refresh_choices()
        self._update_resolved_labels()
        self._refresh_preview()

    def unstudied_widgets(self):
        """The fields greyed until unlocked: the paper tile bytes, whose only known-good value is
        the retail one (see paper_tile_vram)."""
        return [self.paper_a, self.paper_b]

    def _set_unlock_unstudied(self, unlocked):
        for widget in self.unstudied_widgets():
            widget.setEnabled(bool(unlocked))

    def _update_paper_label(self):
        """Say which 32x32 VRAM tile the paper bytes pick (paper_tile_vram)."""
        e1, e2 = self.paper_a.value(), self.paper_b.value()
        x, y = paper_tile_vram(e1, e2)
        if (e1, e2) == (VANILLA_PAPER_E1, VANILLA_PAPER_E2):
            self.paper_label.setText(f"= tile at ({x},{y}): the parchment (mngrp raw file 12)")
            self.paper_label.setStyleSheet("")
        else:
            self.paper_label.setText(f"= tile at ({x},{y}): not the parchment (retail: 0x00 / 0xC0); "
                                     "the preview still draws the parchment")
            self.paper_label.setStyleSheet("color: #c07000;")

    def _on_font_changed(self):
        """sysfnt.TEX or sysfnt.tdw was opened or removed: redraw the text with what is open."""
        self.font_source.apply_to(self.renderer)
        notice = self.font_source.notice()
        self.font_notice.setText(notice)
        self.font_notice.setVisible(bool(notice))
        self._refresh_preview()

    def _fill_weapon_combo(self, weapon_index):
        """The weapon choices: 'None' plus the kernel.bin's weapons. Without a kernel.bin there
        are no names - only the entry's own id is shown, greyed out, next to the notice."""
        names = self.kernel_names.weapons
        self.weapon_combo.blockSignals(True)
        self.weapon_combo.clear()
        self.weapon_combo.addItem("None", UNUSED_ID)
        if names:
            for index, name in enumerate(names):
                self.weapon_combo.addItem(f"{index}: {name or f'Weapon {index}'}", index)
        elif weapon_index != UNUSED_ID:
            self.weapon_combo.addItem(f"{weapon_index}: open kernel.bin to name it", weapon_index)
        self._set_combo_data(self.weapon_combo, weapon_index,
                             f"{weapon_index}: (not in kernel.bin)")
        self.weapon_combo.setEnabled(bool(names))
        fit_combo_popup(self.weapon_combo)
        self.weapon_combo.blockSignals(False)
        self.weapon_notice.setVisible(not names)

    def _on_kernel_names_changed(self):
        """A kernel.bin was opened or removed: re-label the weapons, keeping the value in the
        form (even an unsaved one)."""
        self.manager.set_weapon_names(self.kernel_names.weapons)
        current = self.weapon_combo.currentData()
        self._fill_weapon_combo(UNUSED_ID if current is None else current)

    def _apply_kernel(self, file_name):
        self._apply_companion(self.manager.load_kernel, "kernel.bin", file_name)

    def _apply_mwepon(self, file_name):
        self._apply_companion(self.manager.load_mwepon, "mwepon.bin", file_name)

    def _apply_icons(self, file_name):
        self._apply_companion(self.manager.load_icons, "icon.sp1", file_name)

    def _apply_mitem(self, file_name):
        self._apply_companion(self.manager.load_mitem, "mitem.bin", file_name)

    def _apply_companion(self, loader, label, file_name):
        """Load one non-mngrp complementary file and redraw (each read-only binding's callback)."""
        try:
            loader(file_name)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, f"Could not load {label}", str(e))
            return
        self._update_resolved_labels()
        self._refresh_preview()

    def save_file(self):
        if not self.manager.file_path:
            return
        self._apply_form_to_entry()
        self.manager.save_file()

    def save_files(self):
        """The shared Save: mmag.bin, then mngrp.bin (and the replaced pictures' .TEX) when its book
        text or pictures were edited here."""
        self.mmag_binding.save()
        self.companion_bindings["mngrp.bin"].save()
        return True

    def _save_mngrp(self):
        if not self.manager.mngrp_edited:
            return
        problems = self.manager.save_mngrp()
        if self.renderer is not None:
            self.renderer._tim_cache.clear()  # the pictures are read again from the saved file
        if problems:
            QMessageBox.warning(self, "Zone - mngrp.bin saved", "\n".join(problems))
        self._refresh_choices()
        self._refresh_other_mngrp_users()

    def _refresh_other_mngrp_users(self):
        """The other tools holding mngrp.bin still have the file as it was: the read-only ones
        (Moomba) read it again; an editor (Shiva, ShumiTranslator) would write its older copy back
        on its next save, so it is told to reload first."""
        mine = self.companion_bindings["mngrp.bin"]
        editors = []
        for binding in mine.registry.bindings:
            if binding is mine or binding.file_name != "mngrp.bin" or not binding.is_loaded:
                continue
            if binding.read_only:
                binding.reload_from_disk()
            else:
                editors.append(binding)
        if editors:
            QMessageBox.information(self, "Zone - mngrp.bin also open elsewhere",
                                    "mngrp.bin was saved with the book text and pictures edited here. Another "
                                    "tool has it open (Shiva or ShumiTranslator): use Reload there before saving "
                                    "in it, or it writes its older copy back.")

    def _refresh_preview(self):
        """Render the selected entry from the values currently in the form."""
        # The placeholder says what is actually missing: mngrp is shared, so it may already be
        # loaded (from the mmag2.bin tab or Shiva) and the tab only needs mmag.bin opened.
        if self.renderer is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Open mngrp.bin (or the mmag2.bin tab / Shiva) to render "
                                       "the page")
            return
        if not 0 <= self.current_entry_index < len(self.manager.entries):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("mngrp.bin ready — open mmag.bin to render a page")
            return
        self._apply_form_to_entry()
        image = self.renderer.render(self.manager.entries[self.current_entry_index])
        qt_image = QImage(image.tobytes("raw", "RGBA"), image.width, image.height,
                          QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qt_image).scaled(
            image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        self.preview_label.setPixmap(pixmap)

    def select_entry(self, index):
        """Select an mmag.bin entry by index, e.g. when jumping in from the Piet tool."""
        if 0 <= index < self.entry_list.count():
            self.entry_list.setCurrentRow(index)

    def _entry_changed(self, row):
        self._apply_form_to_entry()
        self.current_entry_index = row
        if row >= 0:
            self._fill_form_from_entry(self.manager.entries[row])
            self._refresh_preview()

    def _form_widgets(self):
        widgets = [self.window_x, self.window_y, self.window_w, self.window_h,
                   self.pic_x, self.pic_y, self.pic_w, self.pic_h,
                   self.pic_tint_r, self.pic_tint_g, self.pic_tint_b,
                   self.paper_a, self.paper_b, self.text_file,
                   self.texture_category, self.texture_page, self.footer_flag,
                   self.weapon_combo, self.duel_combo, self.angelo_combo,
                   self.weapon_spacing, self.weapon_list_x, self.weapon_list_y,
                   self.weapon_qty_x, self.duel_x, self.duel_y]
        widgets += [widget for spins in (self.pic_overlay_spins, self.text_overlay_spins)
                    for row in spins for widget in row[:3]]
        return widgets

    def _fill_form_from_entry(self, entry):
        for widget in self._form_widgets():
            widget.blockSignals(True)

        self.window_x.setValue(entry.window_x)
        self.window_y.setValue(entry.window_y)
        self.window_w.setValue(entry.window_width)
        self.window_h.setValue(entry.window_height)
        self.pic_x.setValue(entry.picture_x)
        self.pic_y.setValue(entry.picture_y)
        self.pic_w.setValue(entry.picture_width)
        self.pic_h.setValue(entry.picture_height)
        self.pic_tint_r.setValue(entry.picture_tint_r)
        self.pic_tint_g.setValue(entry.picture_tint_g)
        self.pic_tint_b.setValue(entry.picture_tint_b)
        self.paper_a.setValue(entry.paper_e1)
        self.paper_b.setValue(entry.paper_e2)
        self.text_file.setValue(entry.text_file_index)
        self._refresh_text_choices()  # the lines of this page's text file
        self._set_combo_data(self.texture_category, entry.texture_category,
                             f"{entry.texture_category}: Direct raw file")
        self._refresh_page_choices()  # the pictures of this page's category
        self.texture_page.setValue(entry.texture_page)
        self.footer_flag.setChecked(bool(entry.footer_flag))
        self._fill_weapon_combo(entry.weapon_index)
        self._set_combo_data(self.duel_combo, entry.duel_move_id,
                             f"{entry.duel_move_id}: Unknown duel move")
        self._set_combo_data(self.angelo_combo, entry.angelo_move_id,
                             f"{entry.angelo_move_id}: Unknown Angelo move")
        self.weapon_spacing.setValue(entry.weapon_line_spacing)
        self.weapon_list_x.setValue(entry.weapon_list_x)
        self.weapon_list_y.setValue(entry.weapon_list_y)
        self.weapon_qty_x.setValue(entry.weapon_quantity_column_x)
        self.duel_x.setValue(entry.duel_combo_x)
        self.duel_y.setValue(entry.duel_combo_y)
        for spins, overlays in ((self.pic_overlay_spins, entry.picture_overlays),
                                (self.text_overlay_spins, entry.text_overlays)):
            for (x_spin, y_spin, id_spin, _preview), overlay in zip(spins, overlays):
                x_spin.setValue(overlay.x)
                y_spin.setValue(overlay.y)
                id_spin.setValue(overlay.id)

        for widget in self._form_widgets():
            widget.blockSignals(False)
        self._update_resolved_labels()

    @staticmethod
    def _set_combo_data(combo, value, fallback_label):
        index = combo.findData(value)
        if index < 0:  # value outside the known list: keep it editable without losing it
            combo.addItem(fallback_label, value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    def _apply_form_to_entry(self):
        if not 0 <= self.current_entry_index < len(self.manager.entries):
            return
        entry = self.manager.entries[self.current_entry_index]
        entry.window_x = self.window_x.value()
        entry.window_y = self.window_y.value()
        entry.window_width = self.window_w.value()
        entry.window_height = self.window_h.value()
        entry.picture_x = self.pic_x.value()
        entry.picture_y = self.pic_y.value()
        entry.picture_width = self.pic_w.value()
        entry.picture_height = self.pic_h.value()
        entry.picture_tint_r = self.pic_tint_r.value()
        entry.picture_tint_g = self.pic_tint_g.value()
        entry.picture_tint_b = self.pic_tint_b.value()
        entry.paper_e1 = self.paper_a.value()
        entry.paper_e2 = self.paper_b.value()
        entry.text_file_index = self.text_file.value()
        entry.texture_category = self.texture_category.currentData()
        entry.texture_page = self.texture_page.value()
        entry.footer_flag = 1 if self.footer_flag.isChecked() else 0
        entry.weapon_index = self.weapon_combo.currentData()
        entry.duel_move_id = self.duel_combo.currentData()
        entry.angelo_move_id = self.angelo_combo.currentData()
        entry.weapon_line_spacing = self.weapon_spacing.value()
        entry.weapon_list_x = self.weapon_list_x.value()
        entry.weapon_list_y = self.weapon_list_y.value()
        entry.weapon_quantity_column_x = self.weapon_qty_x.value()
        entry.duel_combo_x = self.duel_x.value()
        entry.duel_combo_y = self.duel_y.value()
        for spins, overlays in ((self.pic_overlay_spins, entry.picture_overlays),
                                (self.text_overlay_spins, entry.text_overlays)):
            for (x_spin, y_spin, id_spin, _preview), overlay in zip(spins, overlays):
                overlay.x = x_spin.value()
                overlay.y = y_spin.value()
                overlay.id = id_spin.value()

    def _update_resolved_labels(self):
        self.text_file_label.setText(
            f"= mngrp raw file {BOOK_TEXT_FIRST_RAW_FILE + self.text_file.value()} "
            f"(tutorial books; the Item menu always reads {BOOK_TEXT_FIRST_RAW_FILE})")
        category = self.texture_category.currentData()
        if category in TEXTURE_CATEGORIES:
            raw_file = TEXTURE_CATEGORIES[category][1] + self.texture_page.value()
        else:
            raw_file = self.texture_page.value()
        pc_file = pc_picture_file_name(raw_file)
        if pc_file and is_added_slot(raw_file) and not self.manager.has_slot(raw_file):
            self.texture_label.setText(f"= mngrp raw file {raw_file}: empty slot, no picture (Add new picture "
                                       f"fills the next free one)")
            self.texture_label.setStyleSheet("color: #c06000;")
        elif pc_file and is_added_slot(raw_file):
            self.texture_label.setText(f"= mngrp raw file {raw_file}, in game (PC, FFNx with AddMorePictures): "
                                       f"menu/{pc_file}")
            self.texture_label.setStyleSheet("")
        elif pc_file:
            self.texture_label.setText(f"= mngrp raw file {raw_file}, in game (PC): menu/{pc_file}")
            self.texture_label.setStyleSheet("")
        else:
            self.texture_label.setText(f"= mngrp raw file {raw_file}: no picture on PC (no texture for "
                                       f"this slot)")
            self.texture_label.setStyleSheet("color: #c06000;")

        can_replace = self.manager.can_replace_picture(raw_file)
        self.replace_picture_button.setEnabled(can_replace)
        self.export_picture_button.setEnabled(self.manager.mngrp_loaded and pc_file is not None
                                              and (not is_added_slot(raw_file) or self.manager.has_slot(raw_file)))
        self.add_picture_button.setEnabled(bool(self.manager.free_picture_slots()))
        for button in self.new_line_buttons:
            button.setEnabled(self.manager.mngrp_loaded)

        texts = self.manager.get_book_texts(self.text_file.value()) if self.manager.mngrp_loaded else []
        for _x_spin, _y_spin, id_spin, editor in self.text_overlay_spins:
            if editor is None:
                continue
            slot_id = id_spin.value()
            editable = slot_id != UNUSED_ID and 0 <= slot_id < len(texts)
            if slot_id == UNUSED_ID or not self.manager.mngrp_loaded:
                text = ""
            elif editable:
                text = self.manager.to_editor_text(texts[slot_id])
            else:
                text = f"(no line {slot_id} in the book text)"
            editor.setReadOnly(not editable)
            if editor.toPlainText() != text:  # never reset what is being typed
                editor.blockSignals(True)
                editor.setPlainText(text)
                editor.blockSignals(False)
