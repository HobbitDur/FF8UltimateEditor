import os

from PyQt6.QtCore import QSignalBlocker, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QFontMetrics
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QGroupBox, QFormLayout, QSizePolicy)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Piet.pietmanager import PietManager


class PietWidget(QWidget):
    """mtmag.bin editor: the three books of the tutorial menu (battle tutorial, card rules,
    card icon explanation), each defined as a range of mmag.bin page entries.

    Named after Piet, the Esthar technician of the Lunar Base."""

    # Emitted with the mmag.bin entry index to jump to when "View in Zone" is clicked
    view_in_zone_requested = pyqtSignal(int)

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.manager = PietManager()

        self.setWindowTitle("Piet")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section: mtmag.bin, driven by the shared header toolbar (Import / Save).
        self.mtmag_binding = FileBinding("mtmag.bin", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # One group box per book, each with a first/last mmag entry spinbox pair
        self.first_spinboxes = []
        self.last_spinboxes = []
        self.page_labels = []
        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        for book_id in range(PietManager.NB_BOOK):
            first_spinbox = self._new_mmag_spinbox("First mmag.bin entry of the book")
            first_spinbox.valueChanged.connect(self._on_data_changed)

            last_spinbox = self._new_mmag_spinbox("Last mmag.bin entry of the book (inclusive)")
            last_spinbox.valueChanged.connect(self._on_data_changed)

            page_label = QLabel("0 pages")

            view_in_zone_button = QPushButton("View in Zone")
            view_in_zone_button.setToolTip("Jump to the Zone tool (mmag.bin editor) on this book's first page")
            view_in_zone_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            view_in_zone_button.clicked.connect(self._make_view_handler(book_id))

            book_group = QGroupBox(PietManager.BOOK_NAME_LIST[book_id])
            book_group.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            book_form = QFormLayout()
            book_form.setSizeConstraint(QFormLayout.SizeConstraint.SetMinimumSize)
            book_form.addRow("First mmag entry:", first_spinbox)
            book_form.addRow("Last mmag entry:", last_spinbox)
            book_form.addRow("Pages:", page_label)
            book_form.addRow("", view_in_zone_button)
            book_group.setLayout(book_form)

            self.first_spinboxes.append(first_spinbox)
            self.last_spinboxes.append(last_spinbox)
            self.page_labels.append(page_label)
            editor_layout.addWidget(book_group, alignment=Qt.AlignmentFlag.AlignLeft)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.editor_container)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self.mtmag_binding.load_opened_file()  # Another tool may have opened mtmag.bin already

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool (just mtmag.bin)."""
        return [self.mtmag_binding]

    @staticmethod
    def _new_mmag_spinbox(tooltip):
        spinbox = QSpinBox()
        spinbox.setRange(0, PietManager.MAX_MMAG_ENTRY)
        spinbox.setToolTip(tooltip)
        # Size to fit PietManager.MAX_MMAG_ENTRY exactly, no wider
        digits = len(str(PietManager.MAX_MMAG_ENTRY))
        text_width = QFontMetrics(spinbox.font()).horizontalAdvance("0" * digits)
        spinbox.setFixedWidth(text_width + 30)  # + spin arrows and frame margins
        return spinbox

    def _make_view_handler(self, book_id):
        return lambda *_args: self.view_in_zone_requested.emit(self.first_spinboxes[book_id].value())

    def load_file(self, file_name):
        self.manager.load_file(file_name)
        self.file_label.setText(os.path.basename(file_name))
        self.editor_container.setEnabled(True)
        self.reload_books()

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def reload_books(self):
        for book_id, book in enumerate(self.manager.books):
            with QSignalBlocker(self.first_spinboxes[book_id]):
                self.first_spinboxes[book_id].setValue(book.first_entry)
            with QSignalBlocker(self.last_spinboxes[book_id]):
                self.last_spinboxes[book_id].setValue(book.last_entry)
            self._update_bounds(book_id)
            self._update_page_label(book_id)

    def _on_data_changed(self):
        if not self.manager.books:
            return
        for book_id, book in enumerate(self.manager.books):
            book.first_entry = self.first_spinboxes[book_id].value()
            book.last_entry = self.last_spinboxes[book_id].value()
            self._update_bounds(book_id)
            self._update_page_label(book_id)

    def _update_bounds(self, book_id):
        # Keep first <= last: the first spinbox can't pass the last one and vice versa
        with QSignalBlocker(self.first_spinboxes[book_id]):
            self.first_spinboxes[book_id].setMaximum(self.last_spinboxes[book_id].value())
        with QSignalBlocker(self.last_spinboxes[book_id]):
            self.last_spinboxes[book_id].setMinimum(self.first_spinboxes[book_id].value())

    def _update_page_label(self, book_id):
        self.page_labels[book_id].setText(f"{self.manager.books[book_id].nb_page} pages")
