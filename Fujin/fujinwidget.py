import os
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap, QFont
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QTabWidget, QComboBox, QPlainTextEdit, QFormLayout,
                             QMessageBox, QScrollArea)

from Fujin.fujinmanager import FujinManager


class FujinWidget(QWidget):
    """Fujin: magic-animation (effect_id) explorer.

    FF8 spell animations are code in FF8_EN.exe, dispatched by effect_id (the kernel magic
    entry field +0x04). Fujin reads a pre-generated data file (magic_effect.json, made in IDA
    by Fujin/ResearchScript/dump_magic_effects.py and shipped in FF8GameData): handler
    addresses, the files each effect loads, and the decompiled logic of every spell. It also
    previews the spell textures you import from a de-archived magic.fs.
    See FF8ModdingWiki "Magic Effect Anatomy & Authoring" and "Case study: Firaga animation"."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.manager = FujinManager(game_data_folder=game_data_folder)

        self.setWindowTitle("Fujin")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.import_files_button = QPushButton("Import magic files")
        self.import_files_button.setToolTip("Import the spell files you extracted from magic.fs "
                                            "(de-archive it first, e.g. with the FS extract button of the "
                                            "main window).\nYou can pick several files at once; the TIM of "
                                            "the selected effect is then previewed in the Texture tab.")
        self.import_files_button.clicked.connect(self.import_files)

        self.reload_button = QPushButton("Reload data")
        self.reload_button.setToolTip("Reload magic_effect.json (regenerate it in IDA with "
                                      "Fujin/ResearchScript/dump_magic_effects.py).")
        self.reload_button.clicked.connect(self.reload_data)

        self.data_label = QLabel("")
        self._update_data_label()

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.import_files_button)
        file_section_layout.addWidget(self.reload_button)
        file_section_layout.addWidget(self.data_label)
        file_section_layout.addStretch(1)

        # Effect list (left side)
        self.effect_list = QListWidget()
        self.effect_list.setFixedWidth(320)
        for entry in self.manager.entries:
            self.effect_list.addItem("%3d - %s" % (entry.effect_id, entry.name))
        self.effect_list.currentRowChanged.connect(self.reload_selected_entry)

        # Tabs (right side)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_pseudocode_tab(), "Spell logic (read-only)")
        self.tabs.addTab(self._build_texture_tab(), "Texture")

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.effect_list)
        main_editor_layout.addWidget(self.tabs)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

        self.effect_list.setCurrentRow(0)

    # --- Tab builders -----------------------------------------------------------------

    def _build_overview_tab(self):
        self.overview_name = QLabel("")
        self.overview_name.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.overview_status = QLabel("")
        self.overview_logic = QLabel("")
        self.overview_fl = QLabel("")
        self.overview_files = QLabel("")
        self.overview_files.setWordWrap(True)
        for label in (self.overview_status, self.overview_logic, self.overview_fl, self.overview_files):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        how_it_works = QLabel(
            "How a spell animation works: the effect_id (kernel magic entry +0x04) indexes "
            "MagicList_Logic (0xC81774) and MagicList_TextureLoad (0xC81DB8) in FF8_EN.exe. "
            "The loader reads the textures from magic.fs; the init function builds the whole "
            "animation in code (camera, particles, sound, damage frame).\n\n"
            "To reuse an animation for a new spell (Tier 1): set the new spell's kernel field +0x04 "
            "to this effect_id (SolomonRing/Doomtrain) and optionally recolor its TIM in the Texture tab.\n"
            "Free slots for brand-new effects: 224, 225 and 346-400 (needs code, see the wiki)."
        )
        how_it_works.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.overview_name)
        form.addRow("Status:", self.overview_status)
        form.addRow("Init function:", self.overview_logic)
        form.addRow("Texture loader:", self.overview_fl)
        form.addRow("Files loaded:", self.overview_files)
        form.addRow(how_it_works)

        container = QWidget()
        container.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _build_pseudocode_tab(self):
        self.function_selector = QComboBox()
        self.function_selector.currentIndexChanged.connect(self._show_selected_function)

        self.pseudocode_view = QPlainTextEdit()
        self.pseudocode_view.setReadOnly(True)
        font = QFont("Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.pseudocode_view.setFont(font)

        layout = QVBoxLayout()
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Function:"))
        selector_layout.addWidget(self.function_selector)
        selector_layout.addStretch(1)
        layout.addLayout(selector_layout)
        layout.addWidget(self.pseudocode_view)

        container = QWidget()
        container.setLayout(layout)
        return container

    def _build_texture_tab(self):
        self.texture_info = QLabel("Import the spell files (from a de-archived magic.fs) to preview the texture.")
        self.texture_info.setWordWrap(True)

        self.texture_preview = QLabel("")
        self.texture_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.texture_preview)

        self.extract_tim_button = QPushButton("Extract TIM...")
        self.extract_tim_button.setToolTip("Copy this spell's imported TIM to another location")
        self.extract_tim_button.clicked.connect(self.extract_tim)
        self.replace_tim_button = QPushButton("Replace TIM...")
        self.replace_tim_button.setToolTip("Overwrite this spell's imported TIM with another file "
                                           "(irreversible; re-archive magic.fs afterwards, or use a "
                                           "direct-file mod loader like FFNx)")
        self.replace_tim_button.clicked.connect(self.replace_tim)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.extract_tim_button)
        buttons_layout.addWidget(self.replace_tim_button)
        buttons_layout.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.texture_info)
        layout.addLayout(buttons_layout)
        layout.addWidget(preview_scroll)

        container = QWidget()
        container.setLayout(layout)
        return container

    # --- File actions -----------------------------------------------------------------

    def _update_data_label(self):
        if self.manager.data_loaded:
            self.data_label.setText("Data: %s" % os.path.basename(self.manager.data_path))
        else:
            self.data_label.setText("No data - run Fujin/ResearchScript/dump_magic_effects.py in IDA")

    def import_files(self):
        file_names = self.file_dialog.getOpenFileNames(parent=self, caption="Import magic files",
                                                       directory=os.getcwd())[0]
        if not file_names:
            return
        self.manager.import_files(file_names)
        self._reload_texture()

    def reload_data(self):
        path = self.manager.default_dump_path
        if not os.path.exists(path):
            QMessageBox.information(self, "Fujin", "No magic_effect.json found at:\n%s\n\nGenerate it in IDA "
                                    "with Fujin/ResearchScript/dump_magic_effects.py." % path)
            return
        try:
            self.manager.load_dump(path)
        except (ValueError, KeyError, OSError) as error:
            QMessageBox.warning(self, "Fujin", "Could not load the data: %s" % error)
            return
        self._update_data_label()
        self.reload_selected_entry()

    # --- Selection --------------------------------------------------------------------

    def _selected_entry(self):
        index = self.effect_list.currentRow()
        if 0 <= index < len(self.manager.entries):
            return self.manager.entries[index]
        return None

    def reload_selected_entry(self):
        entry = self._selected_entry()
        if not entry:
            return
        self.overview_name.setText("Effect %d - %s" % (entry.effect_id, entry.name))
        if entry.free:
            self.overview_status.setText("FREE SLOT - available for a brand-new custom effect")
        elif 226 <= entry.effect_id <= 345:
            self.overview_status.setText("Used, undocumented (probably a monster attack or story cinematic)")
        else:
            self.overview_status.setText("Used")
        if entry.has_data and not entry.free:
            self.overview_logic.setText("%s @ %s" % (entry.logic_name, entry.logic_addr))
            self.overview_fl.setText("%s @ %s" % (entry.fl_name, entry.fl_addr))
            self.overview_files.setText(entry.files_text())
        else:
            self.overview_logic.setText("" if entry.free else "(no data - run the ResearchScript)")
            self.overview_fl.setText("")
            self.overview_files.setText(entry.files_text())

        self.function_selector.blockSignals(True)
        self.function_selector.clear()
        for function in entry.functions:
            self.function_selector.addItem("%s @ %s" % (function["name"], function["addr"]))
        self.function_selector.blockSignals(False)
        if entry.functions:
            self.function_selector.setCurrentIndex(0)
            self._show_selected_function()
        elif entry.free:
            self.pseudocode_view.setPlainText("(free slot)")
        elif self.manager.data_loaded:
            self.pseudocode_view.setPlainText("(no functions in the data for this effect)")
        else:
            self.pseudocode_view.setPlainText("Run Fujin/ResearchScript/dump_magic_effects.py in IDA to "
                                              "generate the spell-logic data.")
        self._reload_texture()

    def _show_selected_function(self):
        entry = self._selected_entry()
        index = self.function_selector.currentIndex()
        if entry and 0 <= index < len(entry.functions):
            self.pseudocode_view.setPlainText(entry.functions[index]["pseudocode"])

    # --- Texture ----------------------------------------------------------------------

    def _reload_texture(self):
        entry = self._selected_entry()
        tim_path = self.manager.find_imported_tim(entry) if entry and not entry.free else ""
        if not tim_path:
            self.texture_preview.setPixmap(QPixmap())
            if entry and entry.free:
                self.texture_info.setText("(free slot)")
            elif not self.manager.imported_files:
                self.texture_info.setText("Import the spell files (from a de-archived magic.fs) to preview the texture.")
            elif entry and entry.files_loaded:
                self.texture_info.setText("Import %s to preview this effect's texture."
                                          % ", ".join(entry.files_loaded))
            else:
                self.texture_info.setText("This effect's TIM is not among the imported files.")
            return
        try:
            width, height, rgb = self.manager.decode_tim(tim_path)
        except ValueError as error:
            self.texture_info.setText("%s: %s" % (os.path.basename(tim_path), error))
            self.texture_preview.setPixmap(QPixmap())
            return
        image = QImage(rgb, width, height, 3 * width, QImage.Format.Format_RGB888)
        # x2 zoom: the atlases are small (often 256x256 or less)
        pixmap = QPixmap.fromImage(image).scaled(width * 2, height * 2)
        self.texture_preview.setPixmap(pixmap)
        self.texture_info.setText("%s - %dx%d" % (os.path.basename(tim_path), width, height))

    def extract_tim(self):
        entry = self._selected_entry()
        tim_path = self.manager.find_imported_tim(entry) if entry else ""
        if not tim_path:
            QMessageBox.information(self, "Fujin", "No imported TIM for this effect (use Import magic files first).")
            return
        destination = self.file_dialog.getSaveFileName(parent=self, caption="Extract TIM to",
                                                       directory=os.path.basename(tim_path), filter="*.tim")[0]
        if destination:
            shutil.copyfile(tim_path, destination)

    def replace_tim(self):
        entry = self._selected_entry()
        tim_path = self.manager.find_imported_tim(entry) if entry else ""
        if not tim_path:
            QMessageBox.information(self, "Fujin", "No imported TIM for this effect (use Import magic files first).")
            return
        source = self.file_dialog.getOpenFileName(parent=self, caption="Replacement TIM",
                                                  filter="*.tim", directory=os.getcwd())[0]
        if not source:
            return
        original_size = os.path.getsize(tim_path)
        new_size = os.path.getsize(source)
        if new_size != original_size:
            answer = QMessageBox.question(
                self, "Fujin",
                "The replacement is %d bytes but the original is %d bytes.\n"
                "A different size is fine for a direct-file mod (FFNx), but a re-archived magic.fs "
                "must keep the archive consistent. Continue?" % (new_size, original_size))
            if answer != QMessageBox.StandardButton.Yes:
                return
        shutil.copyfile(source, tim_path)
        self._reload_texture()
