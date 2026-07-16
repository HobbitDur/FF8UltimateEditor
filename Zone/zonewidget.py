import os

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QGroupBox, QMessageBox, QSpinBox, QComboBox, QCheckBox,
                             QGridLayout, QScrollArea, QFormLayout)

from FF8GameData.gamedata import GameData
from FF8GameData.menu.magpage import MagPageEntry, UNUSED_ID
from Zone.zonemanager import (ZoneManager, TEXTURE_CATEGORIES, DUEL_MOVE_NAMES,
                              ANGELO_MOVE_NAMES, BOOK_TEXT_FIRST_RAW_FILE)
from Zone.zonerender import (PageRenderer, BUTTON_STYLE_BOXES, BUTTON_STYLE_ICONS,
                             CANVAS_WIDTH, CANVAS_HEIGHT)

PREVIEW_SCALE = 2

# Every file Zone reads: exact name -> (loader method, what it adds, needs mmag.bin first).
# The open dialog filters on these names so they are all visible at once.
LOADABLE_FILES = {
    "mmag.bin": ("_load_mmag", "the magazine page entries this editor edits", False),
    "mngrp.bin": ("_load_mngrp", "the page art, the overlay sprites and the book text "
                                 "(needs mngrphd.bin beside it)", True),
    "kernel.bin": ("_load_kernel", "Zell's Duel button combos, drawn on the Combat King pages", True),
    "mwepon.bin": ("_load_mwepon", "the weapon remodel item lists, drawn on the "
                                   "Weapons Monthly pages", True),
    "icon.sp1": ("_load_icons", "the button and item icons of those two lists "
                                "(needs icon.TEX beside it)", True),
    "mitem.bin": ("_load_mitem", "which type icon each remodel item uses", True),
}
LOADABLE_FILTER = "FF8 magazine files (" + " ".join(LOADABLE_FILES) + ")"


class ZoneWidget(QWidget):
    """mmag.bin editor: the in-menu magazine page definitions (Weapons Monthly,
    Combat King, Pet Pals, Occult Fan and the tutorial-menu books). Each entry
    describes one page view: text window, page picture, unlock fields and up to
    4 picture + 4 text overlays. Load mngrp.bin to preview the overlay texts.

    Named after Zone, the Forest Owls member and devoted magazine collector."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_sysfnt_data()  # for the mngrp book-text preview
        self.manager = ZoneManager(self.game_data)
        self.current_entry_index = -1
        self.renderer = None  # Built once mngrp.bin is loaded (it carries the art)

        self.setWindowTitle("Zone")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened mmag.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addStretch(1)
        self._update_load_tooltip()

        # Entry list (left)
        self.entry_list = QListWidget()
        self.entry_list.setFixedWidth(240)
        self.entry_list.currentRowChanged.connect(self._entry_changed)

        # Entry form (right, scrollable)
        form_widget = QWidget()
        form_layout = QVBoxLayout()
        form_layout.addWidget(self._build_window_group())
        form_layout.addWidget(self._build_picture_group())
        form_layout.addWidget(self._build_text_and_texture_group())
        form_layout.addWidget(self._build_unlock_group())
        form_layout.addWidget(self._build_overlays_group())
        form_layout.addStretch(1)
        form_widget.setLayout(form_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)

        self.editor_container = QWidget()
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.entry_list)
        editor_layout.addWidget(scroll)
        editor_layout.addWidget(self._build_preview_group())
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

        self._connect_live_preview()

    def _build_preview_group(self):
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(CANVAS_WIDTH * PREVIEW_SCALE, CANVAS_HEIGHT * PREVIEW_SCALE)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setText("Load mngrp.bin to render the page")
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
        self.paper_a = self._spin8(hex_display=True)
        self.paper_a.setToolTip("PS1 GPU E1 primitive bits (texture page) of the paper background")
        self.paper_b = self._spin8(hex_display=True)
        self.paper_b.setToolTip("PS1 GPU E2 primitive bits (texture window) of the paper background")

        self.text_file = self._spin8()
        self.text_file.valueChanged.connect(self._update_resolved_labels)
        self.text_file_label = QLabel()

        self.texture_category = QComboBox()
        for category, (name, _base) in TEXTURE_CATEGORIES.items():
            self.texture_category.addItem(f"{category}: {name}", category)
        self.texture_category.currentIndexChanged.connect(self._update_resolved_labels)
        self.texture_page = self._spin8()
        self.texture_page.valueChanged.connect(self._update_resolved_labels)
        self.texture_label = QLabel()

        self.footer_flag = QCheckBox("Draw the footer line (the “to scroll” hint of the multi-page books)")

        group = QGroupBox("Paper, book text and page texture")
        layout = QFormLayout()
        paper_layout = QHBoxLayout()
        paper_layout.addWidget(QLabel("E1"))
        paper_layout.addWidget(self.paper_a)
        paper_layout.addWidget(QLabel("E2"))
        paper_layout.addWidget(self.paper_b)
        paper_layout.addStretch(1)
        layout.addRow("Paper background:", paper_layout)
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
        layout.addRow("", self.footer_flag)
        group.setLayout(layout)
        return group

    def _build_unlock_group(self):
        self.weapon_combo = QComboBox()
        self.weapon_combo.addItem("None", UNUSED_ID)
        for weapon_index, name in enumerate(self.manager.weapon_name_list):
            self.weapon_combo.addItem(f"{weapon_index}: {name}", weapon_index)

        self.duel_combo = QComboBox()
        self.duel_combo.addItem("None", UNUSED_ID)
        for move_id, name in enumerate(DUEL_MOVE_NAMES):
            self.duel_combo.addItem(f"{move_id}: {name}", move_id)

        self.angelo_combo = QComboBox()
        self.angelo_combo.addItem("None", UNUSED_ID)
        for move_id, name in enumerate(ANGELO_MOVE_NAMES):
            self.angelo_combo.addItem(f"{move_id}: {name}", move_id)

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
        return group

    def _build_overlays_group(self):
        group = QGroupBox("Overlays (id 255 = unused slot)")
        layout = QGridLayout()
        layout.addWidget(QLabel("<b>Picture overlays (SP2 sprite)</b>"), 0, 0, 1, 7)
        self.pic_overlay_spins = self._build_overlay_rows(layout, row_start=1)
        row = 1 + MagPageEntry.NB_OVERLAY_SLOTS
        layout.addWidget(QLabel("<b>Text overlays (book-text string)</b>"), row, 0, 1, 7)
        self.text_overlay_spins = self._build_overlay_rows(layout, row_start=row + 1,
                                                           with_preview=True)
        group.setLayout(layout)
        return group

    def _build_overlay_rows(self, layout, row_start, with_preview=False):
        spins = []
        for slot in range(MagPageEntry.NB_OVERLAY_SLOTS):
            row = row_start + slot
            x_spin = self._spin16()
            y_spin = self._spin8()
            id_spin = self._spin8()
            layout.addWidget(QLabel(f"Slot {slot + 1}"), row, 0)
            layout.addWidget(QLabel("X"), row, 1)
            layout.addWidget(x_spin, row, 2)
            layout.addWidget(QLabel("Y"), row, 3)
            layout.addWidget(y_spin, row, 4)
            layout.addWidget(QLabel("ID"), row, 5)
            layout.addWidget(id_spin, row, 6)
            preview = None
            if with_preview:
                preview = QLabel()
                layout.addWidget(preview, row, 7)
                id_spin.valueChanged.connect(self._update_resolved_labels)
            spins.append((x_spin, y_spin, id_spin, preview))
        return spins

    def load_file(self):
        """One dialog for every file Zone reads, listed by its exact name.

        Whichever one is picked is loaded into its own slot, so the files can be
        opened in any order and the dialog doubles as the list of what Zone wants."""
        file_name = self.file_dialog.getOpenFileName(
            parent=self, caption="Open an FF8 file used by the magazine pages",
            filter=LOADABLE_FILTER, directory=os.getcwd())[0]
        if not file_name:
            return
        loader = LOADABLE_FILES.get(os.path.basename(file_name).lower())
        if loader is None:
            QMessageBox.warning(
                self, "Unknown file",
                f"{os.path.basename(file_name)} is not one of the files Zone reads.\n\n"
                + "\n".join(f"• {name}: {what}" for name, (_, what, _) in LOADABLE_FILES.items()))
            return
        method, _what, needs_entries = loader
        if needs_entries and not self.manager.entries:
            QMessageBox.warning(self, "Load mmag.bin first",
                                "mmag.bin holds the page entries everything else decorates, "
                                "so load it before the others.")
            return
        try:
            getattr(self, method)(file_name)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Could not load {os.path.basename(file_name)}:\n{e}")
            return
        self._update_load_tooltip()
        self._refresh_preview()

    def _load_mmag(self, file_name):
        self.manager.load_file(file_name)
        self.editor_container.setEnabled(True)
        self.current_entry_index = -1
        self.entry_list.clear()
        for index in range(len(self.manager.entries)):
            self.entry_list.addItem(f"{index}: {self.manager.entry_name(index)}")
        self.entry_list.setCurrentRow(0)

    def _load_mngrp(self, file_name):
        self.manager.load_mngrp(file_name)
        # sysfnt.TEX/sysfnt.tdw sit in the same menu folder as mngrp.bin
        self.renderer = PageRenderer(self.manager, menu_folder=os.path.dirname(file_name),
                                     button_icon_style=self.button_icon_combo.currentData())
        self._update_resolved_labels()

    def _load_kernel(self, file_name):
        self.manager.load_kernel(file_name)

    def _load_mwepon(self, file_name):
        self.manager.load_mwepon(file_name)

    def _load_icons(self, file_name):
        self.manager.load_icons(file_name)

    def _load_mitem(self, file_name):
        self.manager.load_mitem(file_name)

    def _update_load_tooltip(self):
        """Hovering the open button says what each file adds and what is loaded."""
        loaded = {
            "mmag.bin": bool(self.manager.entries),
            "mngrp.bin": self.manager.mngrp_loaded,
            "kernel.bin": self.manager.kernel_loaded,
            "mwepon.bin": self.manager.mwepon_loaded,
            "icon.sp1": self.manager.icons_loaded,
            "mitem.bin": self.manager.mitem_loaded,
        }
        lines = ["<b>Open an FF8 file</b> (the dialog lists them all by name; "
                 "load them one at a time, in any order):<br>"]
        for name, (_method, what, _needs) in LOADABLE_FILES.items():
            mark = "✔" if loaded.get(name) else "–"
            lines.append(f"{mark} <b>{name}</b> — {what}<br>")
        lines.append("<br>mngrphd.bin, sysfnt.TEX and sysfnt.tdw are read from "
                     "the folder mngrp.bin is in.")
        self.load_button.setToolTip("".join(lines))

    def save_file(self):
        if not self.manager.file_path:
            return
        self._apply_form_to_entry()
        self.manager.save_file()

    def _refresh_preview(self):
        """Render the selected entry from the values currently in the form."""
        if self.renderer is None or not 0 <= self.current_entry_index < len(self.manager.entries):
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
        self._set_combo_data(self.texture_category, entry.texture_category,
                             f"{entry.texture_category}: Direct raw file")
        self.texture_page.setValue(entry.texture_page)
        self.footer_flag.setChecked(bool(entry.footer_flag))
        self._set_combo_data(self.weapon_combo, entry.weapon_index,
                             f"{entry.weapon_index}: Unknown weapon")
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
            f"= mngrp raw file {BOOK_TEXT_FIRST_RAW_FILE + self.text_file.value()}")
        category = self.texture_category.currentData()
        if category in TEXTURE_CATEGORIES:
            raw_file = TEXTURE_CATEGORIES[category][1] + self.texture_page.value()
        else:
            raw_file = self.texture_page.value()
        self.texture_label.setText(f"= mngrp raw file {raw_file}")

        if not self.manager.mngrp_loaded:
            return
        texts = self.manager.get_book_texts(self.text_file.value())
        for _x_spin, _y_spin, id_spin, preview in self.text_overlay_spins:
            if preview is None:
                continue
            slot_id = id_spin.value()
            if slot_id == UNUSED_ID:
                preview.setText("")
            elif 0 <= slot_id < len(texts):
                text = texts[slot_id].replace("\n", " / ")
                if len(text) > 60:
                    text = text[:57] + "..."
                preview.setText(text)
            else:
                preview.setText(f"(no string {slot_id})")
