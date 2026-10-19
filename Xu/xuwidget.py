import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QSpinBox, QCheckBox, QPushButton,
                             QComboBox, QGroupBox, QSplitter, QFileDialog, QMessageBox)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Xu.xumanager import (XuManager, FILE_NAME, ROW_COUNT, ALTERNATE_ROWS, FIRST_MONSTER_ROW,
                          LAST_C0M_FILE, c0m_for_row)
from Xu.xupreview import XuPreviewPanel

MODEL_FOLDER_KEY = "battle model (.dat)"  # same remembered folder as Ifrit's model dialog

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
    "unknown": ("Unknown (byte 0xE)", "Not read by the Scan code found so far; 1 in every vanilla row."),
}


class XuWidget(QWidget):
    """battle_scan_cameras.bin editor: how the Scan screen frames each monster.

    The game keeps the table inside FF8_EN.exe; FFNx reads it from direct/exe/ so it can be
    edited, and gives every monster from c0m144 on a row of its own.

    Named after Xu, the SeeD who briefs the squad on their target."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        self.setWindowTitle("Xu")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.manager = XuManager()
        self.binding = FileBinding(FILE_NAME, file_registry, load_callback=self.load_file,
                                   save_callback=self.save_file)
        self._spinboxes = {}
        self._checkboxes = {}
        self._pending_follow_row = None  # model to load once the tool is shown

        # Top bar
        self.new_button = QPushButton("New from vanilla...")
        self.new_button.setToolTip(f"Write a {FILE_NAME} with the vanilla rows (new monsters start with\n"
                                   "G-Soldier's framing) and open it. Put it in FFNx's direct/exe/ folder.")
        self.new_button.clicked.connect(self._create_from_vanilla)
        self.file_label = QLabel(f"No {FILE_NAME} loaded - browsing the vanilla rows")
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

        # Row editor
        self.row_title = QLabel("-")
        self.row_title.setWordWrap(True)
        self.row_title.setStyleSheet("font-weight: bold")
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
        for field in ("aim_at_model", "can_pitch", "can_yaw"):
            check = QCheckBox()
            label, tip = FIELD_HELP[field]
            check.setToolTip(tip)
            check.toggled.connect(lambda checked, f=field: self._on_field_edited(f, int(checked)))
            self._checkboxes[field] = check
            form.addRow(label + ":", check)
        unknown = QSpinBox()
        unknown.setRange(0, 0xFF)
        unknown.setToolTip(FIELD_HELP["unknown"][1])
        unknown.valueChanged.connect(lambda value: self._on_field_edited("unknown", value))
        self._spinboxes["unknown"] = unknown
        form.addRow(FIELD_HELP["unknown"][0] + ":", unknown)

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

        self.editor_group = QGroupBox("Scan camera row")
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.row_title)
        editor_layout.addLayout(form)
        editor_layout.addWidget(QLabel("Copy the framing of:"))
        editor_layout.addLayout(copy_row)
        editor_layout.addWidget(self.reset_button)
        editor_layout.addStretch(1)
        self.editor_group.setLayout(editor_layout)
        self.editor_group.setEnabled(False)

        # Preview
        self.preview = XuPreviewPanel(game_data_folder)
        self.model_button = QPushButton("Choose monster model...")
        self.model_button.setToolTip("Pick a c0m###.dat. Other rows then load their own c0m file "
                                     "from the same folder when it is there.")
        self.model_button.clicked.connect(self._choose_model)
        self.auto_model = QCheckBox("Follow the selected row")
        self.auto_model.setChecked(True)
        self.auto_model.setToolTip("Load the c0m###.dat of the selected row from the model folder")
        self.model_label = QLabel("")
        self.model_label.setStyleSheet("color: gray")
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_button)
        model_row.addWidget(self.auto_model)
        model_row.addWidget(self.model_label, 1)
        preview_holder = QWidget()
        preview_layout = QVBoxLayout(preview_holder)
        preview_layout.addLayout(model_row)
        preview_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_holder)
        splitter.addWidget(self.editor_group)
        splitter.addWidget(preview_holder)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 5)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_bar)
        main_layout.addWidget(splitter, 1)
        self.setLayout(main_layout)

        self._fill_row_list()
        self.row_list.setCurrentRow(87)
        self.binding.load_opened_file()  # Another tool may have opened the file already

    def file_bindings(self):
        """The file the shared header toolbar drives for this tool."""
        return [self.binding]

    # ------------------------------------------------------------------ file
    def load_file(self, path):
        try:
            self.manager.load_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot load {path}:\n{error}")
            return
        self.file_label.setText(path)
        self.file_label.setStyleSheet("")
        self.editor_group.setEnabled(True)
        self._fill_row_list()

    def save_file(self):
        try:
            self.manager.save_file(self.binding.current_path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Xu", f"Cannot save:\n{error}")

    def _create_from_vanilla(self):
        default = os.path.join(self.file_registry.last_folder(FILE_NAME) or os.getcwd(), FILE_NAME)
        path = QFileDialog.getSaveFileName(self, f"Create {FILE_NAME}", default, FILE_NAME)[0]
        if not path:
            return
        manager = XuManager()
        manager.save_file(path)
        self.file_registry.remember_folder(FILE_NAME, os.path.dirname(path))
        self.binding.open_path(path)

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
        self.preview.set_title(self.manager.row_label(row)[5:])
        self.preview.set_row(values)

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
        if getattr(self, "dirty_state", None) is not None:
            self.dirty_state.mark()

    # ------------------------------------------------------------------ model
    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_follow_row is not None:
            row, self._pending_follow_row = self._pending_follow_row, None
            self._follow_model(row)

    def _choose_model(self):
        folder = self.file_registry.last_folder(MODEL_FOLDER_KEY) or os.getcwd()
        path = QFileDialog.getOpenFileName(self, "Choose a monster model", folder,
                                           "Monster battle model (c0m*.dat)")[0]
        if not path:
            return
        self.file_registry.remember_folder(MODEL_FOLDER_KEY, os.path.dirname(path))
        self._load_model(path)

    def _follow_model(self, row):
        """Load the row's own c0m file from the model folder, when following is on."""
        if not self.auto_model.isChecked():
            return
        if not self.isVisible():  # the editor builds every tool at start: load nothing yet
            self._pending_follow_row = row
            return
        c0m = c0m_for_row(row)
        folder = self.file_registry.last_folder(MODEL_FOLDER_KEY)
        if c0m is None or c0m > LAST_C0M_FILE or not folder:
            return
        path = os.path.join(folder, f"c0m{c0m:03d}.dat")
        if os.path.normcase(path) != os.path.normcase(self.preview.model_path) and os.path.isfile(path):
            self._load_model(path)

    def _load_model(self, path):
        try:
            self.preview.load_model(path)
        except Exception as error:  # a file the 3D viewer cannot render
            self.model_label.setText(f"Cannot show {os.path.basename(path)}: {error}")
            return
        self.model_label.setText(os.path.basename(path))
        row = self.current_row()
        if 0 <= row < ROW_COUNT:
            self.preview.set_row(self.manager.rows[row])
