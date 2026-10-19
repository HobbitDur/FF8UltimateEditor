import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QSpinBox, QCheckBox, QPushButton,
                             QComboBox, QGroupBox, QSplitter, QFileDialog, QMessageBox, QTabWidget,
                             QPlainTextEdit, QDialog, QScrollArea, QDialogButtonBox)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Xu.xuhud import ScanHud
from Xu.xumanager import (XuManager, FILE_NAME, ROW_COUNT, ALTERNATE_ROWS, FIRST_MONSTER_ROW,
                          LAST_C0M_FILE, c0m_for_row, com_id_for_row)
from Xu.xupreview import XuPreviewPanel
from Xu.xutext import XuTextManager, FILE_NAME as TEXT_FILE_NAME

MODEL_FOLDER_KEY = "battle model (.dat)"  # same remembered folder as Ifrit's model dialog
TEXT_COUNT_FOR_ALL_MONSTERS = LAST_C0M_FILE + 16 + 1  # com_id 0..215

FIELD_HELP = {
    "distance": ("Distance", "How far the camera stands from the aim point.\n"
                             "Negative = in front of the target. Bigger targets need a bigger (more negative) value."),
    "offset_x": ("Side offset", "Moves the aim point sideways in the Scan screen, which puts the\n"
                                "model off-centre to leave room for the text."),
    "offset_y": ("Aim height", "Height of the aim point above the floor (negative = up)."),
    "model_offset_y": ("Turn pivot height", "Height of the point the model turns around when the player tilts it."),
    "aim_at_model": ("Aim at model", "On: aim at the model's centre bone (skeleton header byte 5).\n"
                                     "Off: aim at the target's position on the floor."),
    "view_offset_y": ("Moved-view height", "Height offset used while the player moves a target whose\n"
                                           "'Aim at model' is off."),
    "can_pitch": ("Player can tilt", "The player can tilt the model up/down in the Scan screen."),
    "can_yaw": ("Turns", "The model turns on its own in the Scan screen, and the player can turn it."),
    "short_scan_orbit": ("Circles in short scan", "The camera circles the target during the short scan: a repeat\n"
                                                  "scan of an already-scanned monster when the Config Scan option\n"
                                                  "is on short."),
}


def build_msd_from_exe(game_data, exe_path) -> bytes:
    """battle_scans.msd content made from an FF8 exe's own scan texts (one per com_id)."""
    from FF8GameData.ExeSection.exefile import SectionExeFile
    from FF8GameData.gamedata import MsdType
    if not getattr(game_data, "card_data_json", None):
        game_data.load_card_data()
    if not game_data.exe_data_json:
        game_data.load_exe_data()
    with open(exe_path, "rb") as file:
        section = SectionExeFile(game_data, bytearray(file.read()))
    return bytes(section.produce_msd(MsdType.SCAN_TEXT))


class _TextSection:
    """The surface ShumiTranslator's SectionWidget reads, over the scan texts."""
    id = 0
    name = f"{TEXT_FILE_NAME} (entry = com_id = c0m + 16)"

    def __init__(self, text_manager):
        self._manager = text_manager

    def get_text_list(self):
        return self._manager.texts

    def add_text(self, _data_hex):
        self._manager.ensure_count(len(self._manager.texts) + 1)


class XuWidget(QWidget):
    """Scan editor: how the Scan screen frames each monster (battle_scan_cameras.bin) and
    what it says about it (battle_scans.msd).

    The game keeps both tables inside FF8_EN.exe; FFNx reads them from direct/exe/ so they can
    be edited, and gives every monster from c0m144 on a camera row and a text of its own.

    Named after Xu, the SeeD who briefs the squad on their target."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        self.setWindowTitle("Xu")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.manager = XuManager()
        self.game_data = GameData(game_data_folder)  # text encoding tables
        self.text_manager = XuTextManager(self.game_data)
        self.hud = ScanHud(self.game_data)
        self.binding = FileBinding(FILE_NAME, file_registry, load_callback=self.load_file,
                                   save_callback=self.save_file)
        self.text_binding = FileBinding(TEXT_FILE_NAME, file_registry, load_callback=self.load_text_file,
                                        save_callback=self.save_text_file)
        # mngrp.bin only matters for what sits next to it: sysfnt.TEX/.tdw, the game font
        # (the Zone/Moomba/IfritSeq convention - never a guessed folder).
        self.mngrp_binding = FileBinding("mngrp.bin", file_registry, load_callback=self._on_mngrp_opened,
                                         read_only=True)
        # The exe the default battle_scans.msd is extracted from - shared with Cid/ShumiTranslator
        self.exe_binding = FileBinding("FF8 exe", file_registry, read_only=True, file_filter="*.exe")
        self._spinboxes = {}
        self._checkboxes = {}
        self._pending_follow_row = None  # model to load once the tool is shown
        self._translation_widget = None

        # Top bar
        self.new_button = QPushButton("New camera file from vanilla...")
        self.new_button.setToolTip(f"Write a {FILE_NAME} with the vanilla rows (new monsters start with\n"
                                   "G-Soldier's framing) and open it. Put it in FFNx's direct/exe/ folder.")
        self.new_button.clicked.connect(self._create_from_vanilla)
        self.file_label = QLabel(f"No {FILE_NAME} opened: you edit the vanilla rows, Save asks where to "
                                 "write the file.")
        self.file_label.setStyleSheet("color: gray")
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.new_button)
        top_bar.addWidget(self.file_label, 1)

        # Row list
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter (name, c0m number, row)")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.changed_only = QCheckBox("Changed rows only")
        self.changed_only.stateChanged.connect(lambda _s: self._apply_filter())
        self.row_list = QListWidget()
        self.row_list.currentRowChanged.connect(self._on_row_selected)
        list_layout = QVBoxLayout()
        list_layout.addWidget(self.filter_edit)
        list_layout.addWidget(self.changed_only)
        list_layout.addWidget(self.row_list, 1)
        list_holder = QWidget()
        list_holder.setLayout(list_layout)

        # Middle: camera row + scan text tabs
        self.row_title = QLabel("-")
        self.row_title.setWordWrap(True)
        self.row_title.setStyleSheet("font-weight: bold")
        self.tabs = QTabWidget()
        self.editor_group = self._build_camera_tab()
        self.tabs.addTab(self.editor_group, "Camera")
        self.tabs.addTab(self._build_text_tab(), "Scan text")
        middle_layout = QVBoxLayout()
        middle_layout.addWidget(self.row_title)
        middle_layout.addWidget(self.tabs, 1)
        middle_holder = QWidget()
        middle_holder.setLayout(middle_layout)

        # Preview
        self.preview = XuPreviewPanel(game_data_folder, hud=self.hud)
        self.model_button = QPushButton("Battle folder...")
        self.model_button.setToolTip("The folder holding the c0m###.dat monster files: each row shows its "
                                     "own monster from it\n(the row gives the com_id, so the c0m number).")
        self.model_button.clicked.connect(self._choose_model_folder)
        self.font_button = QPushButton("Game font...")
        self.font_button.setToolTip("Open mngrp.bin: the scan text is then drawn with the game font\n"
                                    "(sysfnt.TEX/.tdw next to it) and its real character widths.")
        self.font_button.clicked.connect(lambda: self.mngrp_binding.open_dialog(self))
        self.model_label = QLabel("")
        self.model_label.setStyleSheet("color: gray")
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_button)
        model_row.addWidget(self.font_button)
        model_row.addWidget(self.model_label, 1)
        preview_holder = QWidget()
        preview_layout = QVBoxLayout(preview_holder)
        preview_layout.addLayout(model_row)
        preview_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_holder)
        splitter.addWidget(middle_holder)
        splitter.addWidget(preview_holder)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 5)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_bar)
        main_layout.addWidget(splitter, 1)
        self.setLayout(main_layout)

        self._fill_row_list()
        self.row_list.setCurrentRow(87)
        # Another tool may have opened the files already
        self.binding.load_opened_file()
        self.text_binding.load_opened_file()
        self.mngrp_binding.load_opened_file()

    def _build_camera_tab(self):
        form = QFormLayout()
        for field in ("distance", "offset_x", "offset_y", "model_offset_y", "view_offset_y"):
            spin = QSpinBox()
            spin.setRange(-0x8000, 0x7FFF)
            spin.setSingleStep(32)
            label, tip = FIELD_HELP[field]
            spin.setToolTip(tip)
            spin.valueChanged.connect(lambda value, f=field: self._on_field_edited(f, value))
            self._spinboxes[field] = spin
            form.addRow(label + ":", spin)
        for field in ("aim_at_model", "can_pitch", "can_yaw", "short_scan_orbit"):
            check = QCheckBox()
            label, tip = FIELD_HELP[field]
            check.setToolTip(tip)
            check.toggled.connect(lambda checked, f=field: self._on_field_edited(f, int(checked)))
            self._checkboxes[field] = check
            form.addRow(label + ":", check)

        self.copy_source = QComboBox()
        self.copy_source.setMinimumContentsLength(24)
        self.copy_source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.copy_source.setToolTip("Row to copy the framing from (e.g. a vanilla monster of a similar size)")
        self.copy_button = QPushButton("Copy into this row")
        self.copy_button.clicked.connect(self._copy_row)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copy_source, 1)
        copy_row.addWidget(self.copy_button)
        self.reset_button = QPushButton("Reset row to vanilla")
        self.reset_button.clicked.connect(self._reset_row)

        group = QGroupBox("Scan camera row")
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(QLabel("Copy the framing of:"))
        layout.addLayout(copy_row)
        layout.addWidget(self.reset_button)
        layout.addStretch(1)
        group.setLayout(layout)
        return group

    def _build_text_tab(self):
        self.text_file_label = QLabel(f"No {TEXT_FILE_NAME} loaded. Import one (header Import, or below) - "
                                      "FFNx makes it in direct/exe/ with save_exe_data.")
        self.text_file_label.setWordWrap(True)
        self.text_file_label.setStyleSheet("color: gray")
        self.text_open_button = QPushButton(f"Import {TEXT_FILE_NAME}...")
        self.text_open_button.clicked.connect(lambda: self.text_binding.open_dialog(self))
        self.text_from_exe_button = QPushButton("New from FF8 exe...")
        self.text_from_exe_button.setToolTip(f"Build a default {TEXT_FILE_NAME} from the scan texts of an FF8 exe\n"
                                             "(EN, FR, DE, IT or ES; the language is read from the exe) and open it.")
        self.text_from_exe_button.clicked.connect(self._create_text_from_exe)
        self.text_export_button = QPushButton("Export as...")
        self.text_export_button.setToolTip(f"Write the texts to another {TEXT_FILE_NAME}")
        self.text_export_button.clicked.connect(self._export_text)
        self.text_all_button = QPushButton("All texts (ShumiTranslator view)...")
        self.text_all_button.setToolTip("Edit every scan text in one list, like ShumiTranslator")
        self.text_all_button.clicked.connect(self._show_all_texts)
        buttons = QHBoxLayout()
        buttons.addWidget(self.text_open_button)
        buttons.addWidget(self.text_from_exe_button)
        buttons.addWidget(self.text_export_button)
        buttons.addWidget(self.text_all_button)
        buttons.addStretch(1)

        self.text_entry_label = QLabel("-")
        self.text_entry_label.setWordWrap(True)
        self.text_create_button = QPushButton("Create the text entry")
        self.text_create_button.setToolTip("The file stops before this monster's com_id: grow it with empty texts")
        self.text_create_button.clicked.connect(self._create_text_entry)
        self.text_warning = QLabel()
        self.text_warning.setWordWrap(True)
        self.text_warning.setStyleSheet("color: #c06000")

        self._text_holder = QVBoxLayout()  # hosts ShumiTranslator's TranslationWidget
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self.text_file_label)
        layout.addLayout(buttons)
        layout.addWidget(self.text_entry_label)
        layout.addWidget(self.text_create_button)
        layout.addLayout(self._text_holder)
        layout.addWidget(self.text_warning)
        layout.addStretch(1)
        self._update_text_buttons()
        return tab

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool."""
        return [self.binding, self.text_binding, self.mngrp_binding, self.exe_binding]

    def _camera_changed(self):
        return any(not self.manager.is_vanilla(row) for row in range(ROW_COUNT))

    def can_save_folder(self):
        """Save has work even with no camera file opened: the edited vanilla rows."""
        return not self.binding.is_loaded and self._camera_changed()

    def save_files(self):
        """The header Save: both files, asking where to write the camera rows the first time."""
        if self.binding.is_loaded:
            self.save_file()
        elif self._camera_changed():
            default = os.path.join(self.file_registry.last_folder(FILE_NAME) or os.getcwd(), FILE_NAME)
            path = QFileDialog.getSaveFileName(self, f"Save {FILE_NAME} (FFNx direct/exe/)", default, FILE_NAME)[0]
            if path:
                self.manager.save_file(path)
                self.file_registry.remember_folder(FILE_NAME, os.path.dirname(path))
                self.binding.open_path(path)
        self.save_text_file()

    # ------------------------------------------------------------------ camera file
    def load_file(self, path):
        try:
            self.manager.load_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot load {path}:\n{error}")
            return
        self.file_label.setText(path)
        self.file_label.setStyleSheet("")
        self._fill_row_list()

    def save_file(self):
        if not self.binding.is_loaded:  # the shared Save calls every binding of the tool
            return
        try:
            self.manager.save_file(self.binding.current_path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot save:\n{error}")

    def _create_from_vanilla(self):
        default = os.path.join(self.file_registry.last_folder(FILE_NAME) or os.getcwd(), FILE_NAME)
        path = QFileDialog.getSaveFileName(self, f"Create {FILE_NAME}", default, FILE_NAME)[0]
        if not path:
            return
        XuManager().save_file(path)
        self.file_registry.remember_folder(FILE_NAME, os.path.dirname(path))
        self.binding.open_path(path)

    # ------------------------------------------------------------------ text file
    def load_text_file(self, path):
        try:
            self.text_manager.load_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot load {path}:\n{error}")
            return
        self.text_file_label.setText(f"{path} - {len(self.text_manager.texts)} texts (com_id 0-"
                                     f"{len(self.text_manager.texts) - 1})")
        self.text_file_label.setStyleSheet("")
        self._update_text_buttons()
        self._show_row_text(self.current_row())

    def save_text_file(self):
        if not self.text_binding.is_loaded or not self.text_manager.loaded:
            return
        try:
            self.text_manager.save_file(self.text_binding.current_path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot save {TEXT_FILE_NAME}:\n{error}")

    def _export_text(self):
        if not self.text_manager.loaded:
            return
        folder = os.path.dirname(self.text_binding.current_path) or os.getcwd()
        path = QFileDialog.getSaveFileName(self, f"Export {TEXT_FILE_NAME}",
                                           os.path.join(folder, TEXT_FILE_NAME), "MSD file (*.msd)")[0]
        if path:
            self.text_manager.save_file(path)
            self.text_manager.file_path = self.text_binding.current_path  # Save keeps the opened file

    def _create_text_from_exe(self):
        """Extract the exe's scan texts (ShumiTranslator's exe parser) into a new msd."""
        exe_path = self.exe_binding.current_path or self.exe_binding.open_dialog(self)
        if not exe_path:
            return
        try:
            msd = build_msd_from_exe(self.game_data, exe_path)
        except Exception as error:  # not an FF8 exe, or a release the exe data does not cover
            QMessageBox.warning(self, "Xu", f"Cannot read the scan texts of {exe_path}:\n{error}")
            return
        default = os.path.join(self.file_registry.last_folder(TEXT_FILE_NAME) or os.getcwd(), TEXT_FILE_NAME)
        path = QFileDialog.getSaveFileName(self, f"Save the new {TEXT_FILE_NAME} (FFNx direct/exe/)",
                                           default, "MSD file (*.msd)")[0]
        if not path:
            return
        with open(path, "wb") as file:
            file.write(msd)
        self.file_registry.remember_folder(TEXT_FILE_NAME, os.path.dirname(path))
        self.text_binding.open_path(path)

    def _update_text_buttons(self):
        loaded = self.text_manager.loaded
        self.text_export_button.setEnabled(loaded)
        self.text_all_button.setEnabled(loaded)

    def _on_mngrp_opened(self, path):
        folder = os.path.dirname(path)
        self.hud.set_font_folder(folder if os.path.isfile(os.path.join(folder, "sysfnt.TEX")) else None)
        self._refresh_preview_text(self.current_row())

    def _text_com_id(self, row):
        """The msd entry a row's monster reads (alternate rows show their monster's text)."""
        com_id = com_id_for_row(row)
        if com_id is None and row in ALTERNATE_ROWS:
            com_id = ALTERNATE_ROWS[row][0] + FIRST_MONSTER_ROW
        return com_id

    def _show_row_text(self, row):
        from ShumiTranslator.view.translationwidget import TranslationWidget
        if self._translation_widget is not None:
            self._text_holder.removeWidget(self._translation_widget)
            self._translation_widget.deleteLater()
            self._translation_widget = None
        com_id = self._text_com_id(row) if 0 <= row < ROW_COUNT else None
        text = self.text_manager.text(com_id) if com_id is not None else None
        if com_id is None:
            self.text_entry_label.setText("No scan text for this row.")
        elif not self.text_manager.loaded:
            self.text_entry_label.setText(f"Entry {com_id} (com_id {com_id}).")
        else:
            suffix = f" - the text of c0m{com_id - FIRST_MONSTER_ROW:03d}" if row in ALTERNATE_ROWS else ""
            missing = "" if text is not None else (f" - not in the file yet (it has {len(self.text_manager.texts)} "
                                                   "texts): FFNx would read past its end.")
            self.text_entry_label.setText(f"Entry {com_id} (com_id {com_id}){suffix}{missing}")
        self.text_create_button.setVisible(self.text_manager.loaded and com_id is not None and text is None)
        if text is not None:
            self._translation_widget = TranslationWidget(text, com_id)
            editor = self._translation_widget.findChild(QPlainTextEdit)
            if editor is not None:
                editor.textChanged.connect(self._on_text_edited)
            self._text_holder.addWidget(self._translation_widget)
        self._refresh_preview_text(row)

    def _create_text_entry(self):
        com_id = self._text_com_id(self.current_row())
        if com_id is None:
            return
        # Reach every monster FFNx can load at once, so none of them reads past the file's end
        self.text_manager.ensure_count(max(com_id + 1, TEXT_COUNT_FOR_ALL_MONSTERS))
        self._mark_dirty()
        self.load_text_label_count()
        self._show_row_text(self.current_row())

    def load_text_label_count(self):
        path = self.text_binding.current_path
        self.text_file_label.setText(f"{path} - {len(self.text_manager.texts)} texts (com_id 0-"
                                     f"{len(self.text_manager.texts) - 1})")

    def _on_text_edited(self):
        self._mark_dirty()
        self._refresh_preview_text(self.current_row())

    def _show_all_texts(self):
        from ShumiTranslator.view.sectionwidget import SectionWidget
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Xu - all scan texts ({TEXT_FILE_NAME})")
        section_widget = SectionWidget(_TextSection(self.text_manager), 0, allow_add=True)
        for editor in section_widget.findChildren(QPlainTextEdit):
            editor.textChanged.connect(self._mark_dirty)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(section_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        dialog.resize(900, 700)
        dialog.exec()
        self.load_text_label_count()
        self._show_row_text(self.current_row())

    def _refresh_preview_text(self, row):
        if not 0 <= row < ROW_COUNT:
            return
        com_id = self._text_com_id(row)
        scan_text = self.text_manager.get_str(com_id) if com_id is not None else ""
        c0m = c0m_for_row(row)
        title = self.preview.model_name() if self.preview.has_model else ""
        if not title and c0m is not None:
            title = self.manager.monster_name(c0m)
        self.preview.set_texts(title, scan_text)
        too_wide = self.hud.too_wide_lines(scan_text) if scan_text else []
        pages = self.hud.page_count(scan_text) if scan_text else 1
        warnings = []
        if too_wide:
            warnings.append(f"Line(s) {', '.join(map(str, too_wide))} wider than the text box (124 px)"
                            + ("" if self.hud.atlas is not None else ", measured with the fallback widths"))
        if pages > 1:
            warnings.append(f"{pages} pages of 7 lines")
        self.text_warning.setText(" - ".join(warnings))

    def _mark_dirty(self):
        if getattr(self, "dirty_state", None) is not None:
            self.dirty_state.mark()

    # ------------------------------------------------------------------ list
    def _fill_row_list(self):
        current = max(self.row_list.currentRow(), 0)
        with QSignalBlocker(self.row_list):
            self.row_list.clear()
            for row in range(ROW_COUNT):
                self.row_list.addItem(QListWidgetItem(self._list_text(row)))
        with QSignalBlocker(self.copy_source):
            self.copy_source.clear()
            for row in range(FIRST_MONSTER_ROW, ROW_COUNT):
                self.copy_source.addItem(self.manager.row_label(row), row)
        self._apply_filter()
        self.row_list.setCurrentRow(current)
        self._on_row_selected(current)

    def _list_text(self, row):
        return ("* " if not self.manager.is_vanilla(row) else "  ") + self.manager.row_label(row)

    def _refresh_list_item(self, row):
        item = self.row_list.item(row)
        if item is not None:
            item.setText(self._list_text(row))

    def _apply_filter(self):
        text = self.filter_edit.text().strip().lower()
        for row in range(self.row_list.count()):
            item = self.row_list.item(row)
            hidden = bool(text) and text not in item.text().lower()
            if self.changed_only.isChecked() and self.manager.is_vanilla(row):
                hidden = True
            item.setHidden(hidden)

    # ------------------------------------------------------------------ row
    def current_row(self):
        return self.row_list.currentRow()

    def _on_row_selected(self, row):
        if not 0 <= row < ROW_COUNT:
            return
        values = self.manager.rows[row]
        title = self.manager.row_label(row)
        if row in ALTERNATE_ROWS:
            title += f"  (model: c0m{ALTERNATE_ROWS[row][0]:03d})"
        self.row_title.setText(title)
        for field, spin in self._spinboxes.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(values, field))
        for field, check in self._checkboxes.items():
            with QSignalBlocker(check):
                check.setChecked(bool(getattr(values, field)))
        self._follow_model(row)
        self.preview.set_row(values)
        self._show_row_text(row)

    def _on_field_edited(self, field, value):
        row = self.current_row()
        if not 0 <= row < ROW_COUNT:
            return
        self.manager.set_field(row, field, value)
        self._refresh_list_item(row)
        self.preview.set_row(self.manager.rows[row])

    def _copy_row(self):
        row, source = self.current_row(), self.copy_source.currentData()
        if source is None or not 0 <= row < ROW_COUNT:
            return
        self.manager.copy_row(source, row)
        self._after_row_replaced(row)

    def _reset_row(self):
        row = self.current_row()
        if not 0 <= row < ROW_COUNT:
            return
        self.manager.rows[row] = self.manager.vanilla_row(row)
        self._after_row_replaced(row)

    def _after_row_replaced(self, row):
        self._refresh_list_item(row)
        self._on_row_selected(row)
        self._mark_dirty()

    # ------------------------------------------------------------------ model
    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_follow_row is not None:
            row, self._pending_follow_row = self._pending_follow_row, None
            self._follow_model(row)
            self._refresh_preview_text(row)

    def _choose_model_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder holding the c0m###.dat monster files",
                                                  self.file_registry.last_folder(MODEL_FOLDER_KEY) or os.getcwd())
        if not folder:
            return
        self.file_registry.remember_folder(MODEL_FOLDER_KEY, folder)
        self._follow_model(self.current_row())

    def _follow_model(self, row):
        """Show the row's own monster: the row gives the com_id, so the c0m file to load."""
        if not self.isVisible():  # the editor builds every tool at start: load nothing yet
            self._pending_follow_row = row
            return
        c0m = c0m_for_row(row)
        folder = self.file_registry.last_folder(MODEL_FOLDER_KEY)
        if c0m is None or c0m > LAST_C0M_FILE:
            self._set_model_status("No monster model for this row.")
            return
        if not folder:
            self._set_model_status("Choose the battle folder to see the monsters.")
            return
        path = os.path.join(folder, f"c0m{c0m:03d}.dat")
        if not os.path.isfile(path):
            shown = f" (still showing {os.path.basename(self.preview.model_path)})" if self.preview.has_model else ""
            self._set_model_status(f"c0m{c0m:03d}.dat is not in {folder}{shown}.", warning=True)
            return
        if os.path.normcase(path) != os.path.normcase(self.preview.model_path):
            self._load_model(path)
        else:
            self._set_model_status(os.path.basename(path))

    def _set_model_status(self, text, warning=False):
        self.model_label.setText(text)
        self.model_label.setStyleSheet("color: #c06000" if warning else "color: gray")

    def _load_model(self, path):
        try:
            self.preview.load_model(path)
        except Exception as error:  # a file the 3D viewer cannot render
            self._set_model_status(f"Cannot show {os.path.basename(path)}: {error}", warning=True)
            return
        self._set_model_status(os.path.basename(path))
        row = self.current_row()
        if 0 <= row < ROW_COUNT:
            self.preview.set_row(self.manager.rows[row])
            self._refresh_preview_text(row)
