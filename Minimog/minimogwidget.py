import os

from PyQt6.QtCore import QSize, QSignalBlocker, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QSpinBox, QComboBox, QCheckBox, QGroupBox, QFormLayout)

from Minimog.minimogmanager import MinimogManager, Sp1Quad
from Minimog.texpalettedialog import TexPalettePickerDialog

PREVIEW_SCALE = 6


class MinimogWidget(QWidget):
    """icon.sp1 editor (menu icon UV table).

    Each icon the text engine can draw (control code 0x05+n) is a list of quads
    cropped from icon.TEX. Quads can be edited (UV, size, draw offsets, CLUT,
    flags), added or removed; the offset directory is rebuilt on save. Icon ids
    128-139 are the key-config button icons the engine redirects elsewhere, so
    they are shown read-only."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.manager = MinimogManager()
        self.tex_file = None  # decoded icon.TEX for the preview, when available

        self.setWindowTitle("Minimog")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open an icon.sp1 file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened icon.sp1 (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.tex_button = QPushButton("Load icon.TEX")
        self.tex_button.setToolTip("Load the icon texture for the preview "
                                   "(auto-loaded when icon.TEX sits next to the .sp1)")
        self.tex_button.clicked.connect(self.load_tex_dialog)

        self.export_tex_button = QPushButton("Export by palette")
        self.export_tex_button.setToolTip(
            "Convert the raw icon.TEX atlas to a PNG using one palette you pick -\n"
            "the file only stores palette indices, so the same pixels render as\n"
            "completely different colors depending which of the 16 palettes is\n"
            "chosen. Useful for inspecting/editing the raw texture. Needs icon.TEX loaded.")
        self.export_tex_button.setEnabled(False)
        self.export_tex_button.clicked.connect(self.export_tex_png)

        self.export_true_colors_button = QPushButton("Export by real color")
        self.export_true_colors_button.setToolTip(
            "Same layout, size and pixel positions as 'Export by palette' - but\n"
            "each region uses its OWN stored CLUT instead of one palette you pick,\n"
            "e.g. why the 'Target' glyph always comes out red. A handful of\n"
            "regions are reused by two icons with different colors (there is no\n"
            "single correct answer for those); everything not claimed by any\n"
            "current icon is left transparent. Needs icon.TEX loaded.")
        self.export_true_colors_button.setEnabled(False)
        self.export_true_colors_button.clicked.connect(self.export_true_colors)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.tex_button)
        file_section_layout.addWidget(self.export_tex_button)
        file_section_layout.addWidget(self.export_true_colors_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Icon list (left side)
        self.icon_list = QListWidget()
        self.icon_list.setFixedWidth(220)
        self.icon_list.currentRowChanged.connect(self.reload_selected_icon)

        # Quad list + add/remove (middle)
        self.quad_list = QListWidget()
        self.quad_list.setFixedWidth(120)
        self.quad_list.currentRowChanged.connect(self.reload_selected_quad)

        self.add_quad_button = QPushButton("Add quad")
        self.add_quad_button.setToolTip("Append a quad to this icon (the offset directory is rebuilt on save)")
        self.add_quad_button.clicked.connect(self.add_quad)
        self.remove_quad_button = QPushButton("Remove quad")
        self.remove_quad_button.clicked.connect(self.remove_quad)

        quad_side_layout = QVBoxLayout()
        quad_side_layout.addWidget(QLabel("Quads:"))
        quad_side_layout.addWidget(self.quad_list)
        quad_side_layout.addWidget(self.add_quad_button)
        quad_side_layout.addWidget(self.remove_quad_button)

        # Quad editor (right side)
        self.icon_name_label = QLabel("")
        self.icon_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.button_icon_label = QLabel(
            "Key-config button icon: the engine never draws these quads,\n"
            "it redirects ids 128-139 through the controller configuration.")
        self.button_icon_label.setStyleSheet("color: #b06000;")
        self.button_icon_label.hide()

        u_tooltip = "Texture U: X pixel in icon.TEX where the quad's crop starts."
        v_tooltip = "Texture V: Y pixel in icon.TEX where the quad's crop starts."
        width_tooltip = "Width in pixels of the crop taken from icon.TEX."
        height_tooltip = "Height in pixels of the crop taken from icon.TEX."
        dx_tooltip = ("Signed X offset (dword1 byte 1): shifts this quad from the icon's\n"
                      "draw cursor. Even a single-quad icon commonly uses this to align its\n"
                      "glyph on the text baseline (icons vary in height/width but share one\n"
                      "cursor position) - it is not just for multi-quad composites.")
        dy_tooltip = ("Signed Y offset (dword1 byte 3): same as X offset but vertical -\n"
                      "used to baseline-align glyphs of different heights, or to stack\n"
                      "multiple quads into one composite icon (e.g. the D-pad icons).")
        clut_tooltip = ("Raw CLUT selector (11 bits): the primitive CLUT is 0x3810 + this value.\n"
                        "Only multiples of 64 land on a real TEX palette row (selector / 64 =\n"
                        "palette index) - the low 6 bits are a fixed positional constant from\n"
                        "how the palette is packed in VRAM (every vanilla quad uses +32) rather\n"
                        "than a freely choosable value. Prefer editing TEX palette below; this\n"
                        "field is for exact/advanced control and stays in sync with it.")
        palette_tooltip = ("TEX palette used to render this quad. Editing this is the normal way\n"
                           "to recolor an icon: it sets the CLUT selector to palette * 64 + 32,\n"
                           "matching the offset every vanilla quad uses.")
        abe_tooltip = ("Semi-transparency / ABE (dword0 bit 27): tells the PSX GPU to alpha-\n"
                       "blend this quad with what's already drawn instead of overwriting it.\n"
                       "No vanilla icon.sp1 quad has it set. The preview approximates it at\n"
                       "~50% opacity since the actual blend equation (average/add/subtract)\n"
                       "is GPU state, not stored in the quad.")
        tpage_tooltip = ("Texture page (dword0 bits 30-31, PSX GPU E1 bits 5-6): which VRAM\n"
                         "page the primitive samples from - the engine does write this into the\n"
                         "real GPU draw command, it isn't ignored like the button-icon quads are.\n"
                         "Read-only here because all 329 vanilla icons render correctly while this\n"
                         "tool ignores the field entirely (icon.TEX's 256x256 atlas already fits\n"
                         "one 4bpp texpage), so editing it hasn't been verified to do anything\n"
                         "useful and could just point at unrelated VRAM content.")

        self.u_spinbox = QSpinBox()
        self.u_spinbox.setRange(0, 255)
        self.u_spinbox.setToolTip(u_tooltip)
        self.v_spinbox = QSpinBox()
        self.v_spinbox.setRange(0, 255)
        self.v_spinbox.setToolTip(v_tooltip)
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(0, 255)
        self.width_spinbox.setToolTip(width_tooltip)
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(0, 255)
        self.height_spinbox.setToolTip(height_tooltip)
        self.dx_spinbox = QSpinBox()
        self.dx_spinbox.setRange(-128, 127)
        self.dx_spinbox.setToolTip(dx_tooltip)
        self.dy_spinbox = QSpinBox()
        self.dy_spinbox.setRange(-128, 127)
        self.dy_spinbox.setToolTip(dy_tooltip)
        self.clut_spinbox = QSpinBox()
        self.clut_spinbox.setRange(0, 2047)
        self.clut_spinbox.setToolTip(clut_tooltip)
        self.palette_spinbox = QSpinBox()
        self.palette_spinbox.setRange(0, 31)  # widened to num_palettes-1 once icon.TEX loads
        self.palette_spinbox.setToolTip(palette_tooltip)
        self.semi_transparent_checkbox = QCheckBox("Semi-transparency (ABE, bit 27)")
        self.semi_transparent_checkbox.setToolTip(abe_tooltip)
        self.tpage_combobox = QComboBox()
        self.tpage_combobox.addItems([f"{i}" for i in range(4)])
        self.tpage_combobox.setToolTip(tpage_tooltip)
        self.tpage_combobox.setEnabled(False)  # read-only, see tpage_tooltip

        for spinbox in (self.u_spinbox, self.v_spinbox, self.width_spinbox, self.height_spinbox,
                        self.dx_spinbox, self.dy_spinbox, self.clut_spinbox):
            spinbox.valueChanged.connect(self._on_data_changed)
        self.palette_spinbox.valueChanged.connect(self._on_palette_changed)
        self.semi_transparent_checkbox.stateChanged.connect(self._on_data_changed)

        def labeled(text, tooltip):
            label = QLabel(text)
            label.setToolTip(tooltip)
            return label

        edit_group = QGroupBox("Quad")
        edit_form = QFormLayout()
        edit_form.addRow(labeled("Texture U:", u_tooltip), self.u_spinbox)
        edit_form.addRow(labeled("Texture V:", v_tooltip), self.v_spinbox)
        edit_form.addRow(labeled("Width:", width_tooltip), self.width_spinbox)
        edit_form.addRow(labeled("Height:", height_tooltip), self.height_spinbox)
        edit_form.addRow(labeled("X offset:", dx_tooltip), self.dx_spinbox)
        edit_form.addRow(labeled("Y offset:", dy_tooltip), self.dy_spinbox)
        edit_form.addRow(labeled("TEX palette:", palette_tooltip), self.palette_spinbox)
        edit_form.addRow(labeled("CLUT selector:", clut_tooltip), self.clut_spinbox)
        edit_form.addRow(self.semi_transparent_checkbox)
        edit_form.addRow(labeled("Texture page:", tpage_tooltip), self.tpage_combobox)
        edit_group.setLayout(edit_form)

        # Preview
        self.preview_label = QLabel("No texture loaded")
        # Left/top-aligned (not centered): render_icon_anchored() already keeps the
        # crosshair pixel stable within the image, but centering the label around a
        # pixmap whose size still varies would re-introduce that same jitter one
        # layer up. Anchoring the label the same way keeps the whole preview stable.
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.anchor_checkbox = QCheckBox("Show draw cursor")
        self.anchor_checkbox.setChecked(True)
        self.anchor_checkbox.setToolTip(
            "When on, the preview keeps (0,0) - the engine's draw cursor before X/Y\n"
            "offset is applied - in frame, marked with a red crosshair, so a single\n"
            "quad's offset is visible as a shift away from the crosshair.\n"
            "When off, the preview is tightly cropped to the quads themselves (what\n"
            "the engine actually draws) - shifting dx/dy re-centers the crop with it,\n"
            "so the offset has no visible effect in that mode.")
        self.anchor_checkbox.stateChanged.connect(self.reload_preview)
        preview_group = QGroupBox(f"Preview (x{PREVIEW_SCALE})")
        preview_group.setToolTip("Semi-transparent (ABE) quads are shown at ~50% opacity here "
                                 "as an approximation of the GPU blend - see the Semi-transparency "
                                 "tooltip for why the exact blend can't be reproduced.")
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.anchor_checkbox)
        preview_group.setLayout(preview_layout)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.icon_name_label)
        editor_layout.addWidget(self.button_icon_label)
        # AlignLeft/AlignTop so this column doesn't stretch to preview_group's
        # width when the preview grows - each keeps its own natural size.
        editor_layout.addWidget(edit_group, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        editor_layout.addWidget(preview_group, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.icon_list)
        main_editor_layout.addLayout(quad_side_layout)
        main_editor_layout.addWidget(self.editor_container)
        main_editor_layout.addStretch(1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    # ------------------------------------------------------------------ file
    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search icon.sp1 file",
                                                     filter="*.sp1", directory=os.getcwd())[0]
        if file_name:
            self.manager.load_file(file_name)
            self.file_label.setText(os.path.basename(file_name))
            self.editor_container.setEnabled(True)
            self._auto_load_tex(os.path.dirname(file_name))
            with QSignalBlocker(self.icon_list):
                self.icon_list.clear()
                self.icon_list.addItems(
                    [f"{icon.name} ({len(icon.quads)} quad{'s' if len(icon.quads) != 1 else ''})"
                     for icon in self.manager.icons])
            self.icon_list.setCurrentRow(0)

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def load_tex_dialog(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search icon.TEX file",
                                                     filter="*.TEX *.tex", directory=os.getcwd())[0]
        if file_name:
            self._load_tex(file_name)
            self.reload_preview()

    def _auto_load_tex(self, folder):
        if self.tex_file is not None:
            return
        for name in ("icon.TEX", "icon.tex"):
            tex_path = os.path.join(folder, name)
            if os.path.isfile(tex_path):
                self._load_tex(tex_path)
                return

    def _load_tex(self, tex_path):
        from FF8GameData.tex.texfile import TexFile
        self.tex_file = TexFile.read(tex_path)
        self.tex_button.setText(os.path.basename(tex_path))
        self.palette_spinbox.setRange(0, self.tex_file.num_palettes - 1)
        self.export_tex_button.setEnabled(True)
        self.export_true_colors_button.setEnabled(True)

    def export_true_colors(self):
        file_name = self.file_dialog.getSaveFileName(parent=self, caption="Export by real color",
                                                     filter="*.png", directory=os.getcwd())[0]
        if not file_name:
            return
        if not file_name.lower().endswith(".png"):
            file_name += ".png"
        self.manager.render_texture_true_colors(self.tex_file).save(file_name)

    def export_tex_png(self):
        quad = self._selected_quad()
        default_palette = quad.palette_index if quad else 0
        palette, chosen = TexPalettePickerDialog.get_palette(self, self.tex_file, default_palette)
        if not chosen:
            return
        file_name = self.file_dialog.getSaveFileName(parent=self, caption="Export by palette",
                                                     filter="*.png", directory=os.getcwd())[0]
        if not file_name:
            return
        if not file_name.lower().endswith(".png"):
            file_name += ".png"
        self.tex_file.to_image(palette).save(file_name)

    # ------------------------------------------------------------------- ui
    def _selected_icon(self):
        index = self.icon_list.currentRow()
        if 0 <= index < len(self.manager.icons):
            return self.manager.icons[index]
        return None

    def _selected_quad(self):
        icon = self._selected_icon()
        if not icon:
            return None
        index = self.quad_list.currentRow()
        if 0 <= index < len(icon.quads):
            return icon.quads[index]
        return None

    def reload_selected_icon(self):
        icon = self._selected_icon()
        if not icon:
            return
        self.icon_name_label.setText(icon.name)
        self.button_icon_label.setVisible(icon.is_button_icon)
        # Button icons 128-139 are informational only: the engine ignores their quads.
        # tpage_combobox is excluded here - it stays disabled regardless (see tpage_tooltip).
        for editor in (self.u_spinbox, self.v_spinbox, self.width_spinbox, self.height_spinbox,
                       self.dx_spinbox, self.dy_spinbox, self.clut_spinbox, self.palette_spinbox,
                       self.semi_transparent_checkbox,
                       self.add_quad_button, self.remove_quad_button):
            editor.setEnabled(not icon.is_button_icon)
        with QSignalBlocker(self.quad_list):
            self.quad_list.clear()
            self.quad_list.addItems([f"Quad {k}" for k in range(len(icon.quads))])
        if icon.quads:
            self.quad_list.setCurrentRow(0)
        else:
            self.reload_selected_quad()
        self.reload_preview()

    def reload_selected_quad(self):
        quad = self._selected_quad()
        if not quad:
            return
        editors_and_values = (
            (self.u_spinbox, quad.u), (self.v_spinbox, quad.v),
            (self.width_spinbox, quad.width), (self.height_spinbox, quad.height),
            (self.dx_spinbox, quad.dx), (self.dy_spinbox, quad.dy),
            (self.clut_spinbox, quad.clut), (self.palette_spinbox, quad.palette_index),
        )
        for editor, value in editors_and_values:
            with QSignalBlocker(editor):
                editor.setValue(value)
        with QSignalBlocker(self.semi_transparent_checkbox):
            self.semi_transparent_checkbox.setChecked(quad.semi_transparent)
        with QSignalBlocker(self.tpage_combobox):
            self.tpage_combobox.setCurrentIndex(quad.texture_page)

    def add_quad(self):
        icon = self._selected_icon()
        if not icon or icon.is_button_icon:
            return
        self.manager.add_quad(icon.icon_id)
        self._refresh_icon_row(icon)
        self.quad_list.addItem(f"Quad {len(icon.quads) - 1}")
        self.quad_list.setCurrentRow(len(icon.quads) - 1)

    def remove_quad(self):
        icon = self._selected_icon()
        quad_index = self.quad_list.currentRow()
        if not icon or icon.is_button_icon or not (0 <= quad_index < len(icon.quads)):
            return
        self.manager.remove_quad(icon.icon_id, quad_index)
        self._refresh_icon_row(icon)
        with QSignalBlocker(self.quad_list):
            self.quad_list.clear()
            self.quad_list.addItems([f"Quad {k}" for k in range(len(icon.quads))])
        self.quad_list.setCurrentRow(min(quad_index, len(icon.quads) - 1))
        self.reload_selected_quad()
        self.reload_preview()

    def _refresh_icon_row(self, icon):
        item = self.icon_list.item(icon.icon_id)
        if item:
            item.setText(f"{icon.name} ({len(icon.quads)} quad{'s' if len(icon.quads) != 1 else ''})")

    def _on_data_changed(self):
        quad = self._selected_quad()
        icon = self._selected_icon()
        if not quad or (icon and icon.is_button_icon):
            return
        quad.u = self.u_spinbox.value()
        quad.v = self.v_spinbox.value()
        quad.width = self.width_spinbox.value()
        quad.height = self.height_spinbox.value()
        quad.dx = self.dx_spinbox.value()
        quad.dy = self.dy_spinbox.value()
        quad.clut = self.clut_spinbox.value()
        quad.semi_transparent = self.semi_transparent_checkbox.isChecked()
        # texture_page is read-only here (tpage_combobox is disabled), left untouched
        with QSignalBlocker(self.palette_spinbox):
            self.palette_spinbox.setValue(quad.palette_index)
        self.reload_preview()

    def _on_palette_changed(self):
        """TEX palette is the friendly editor for CLUT; it writes the raw
        selector as palette * 64 + 32, matching every vanilla quad's low bits
        (see clut_tooltip) - use the CLUT selector field directly to deviate."""
        quad = self._selected_quad()
        icon = self._selected_icon()
        if not quad or (icon and icon.is_button_icon):
            return
        quad.clut = self.palette_spinbox.value() * 64 + 32
        with QSignalBlocker(self.clut_spinbox):
            self.clut_spinbox.setValue(quad.clut)
        self.reload_preview()

    def reload_preview(self):
        icon = self._selected_icon()
        if not icon:
            return
        if self.tex_file is None:
            self.preview_label.setText("No texture loaded\n(use the Load icon.TEX button)")
            self.preview_label.setPixmap(QPixmap())
            return
        if self.anchor_checkbox.isChecked():
            image = self.manager.render_icon_anchored(icon.icon_id, self.tex_file, scale=PREVIEW_SCALE)
        else:
            image = self.manager.render_icon(icon.icon_id, self.tex_file, scale=PREVIEW_SCALE)
        if image is None:
            self.preview_label.setText("Empty icon")
            self.preview_label.setPixmap(QPixmap())
            return
        qimage = QImage(image.tobytes(), image.width, image.height,
                        image.width * 4, QImage.Format.Format_RGBA8888)
        self.preview_label.setText("")
        self.preview_label.setPixmap(QPixmap.fromImage(qimage))
