import csv

from PyQt6.QtCore import QRect, QSize, QSignalBlocker
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QLineEdit,
                             QListWidget, QComboBox, QPlainTextEdit, QGroupBox, QScrollArea, QMessageBox,
                             QSizePolicy)

from FF8GameData.gamedata import GameData
from Shiva.ShivaSeedTest.seedtest import SeedString, SeedTestSet
from SmallWidget.listsearchbar import ListSearchBar
from Shiva.ShivaSeedTest.seedscreen import (DISPLAY_SIZE, MAX_LINES, MAX_TEXT_WIDTH, SAMPLE_VALUES,
                                            render_seed_screen)


class NidaQuestionWidget(QGroupBox):
    """Editor of one SeeD test string: text, cursor stops (choices) and expected answer."""

    def __init__(self, title, seed_string: SeedString, preview_callback=None):
        QGroupBox.__init__(self, title)
        self._seed_string = seed_string
        self._preview_callback = preview_callback

        self.text_edit = QPlainTextEdit(seed_string.get_text())
        self.text_edit.setFixedHeight(90)
        self.text_edit.setToolTip("Question text: each {Cursor_location_id:0xnn} code is a selectable choice "
                                  "(nn = 0x20 + choice index), \\n is a line break")
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.focusInEvent = self._wrap_focus_in(self.text_edit.focusInEvent)

        self.answer_combo = QComboBox()
        self.answer_combo.setToolTip("The choice the game expects (the answer byte stored before the text)")
        self.answer_combo.activated.connect(self._on_answer_changed)

        self.stops_label = QLabel()
        self.stops_label.setStyleSheet("font-style: italic;")

        self.add_choice_button = QPushButton("Add choice")
        self.add_choice_button.setToolTip("Append a new cursor stop at the end of the text (the engine counts "
                                          "the stops, so this adds a selectable choice). To remove a choice, "
                                          "delete its {Cursor_location_id:0xnn} code from the text.")
        self.add_choice_button.clicked.connect(self._on_add_choice)

        answer_layout = QHBoxLayout()
        answer_layout.addWidget(QLabel("Expected answer:"))
        answer_layout.addWidget(self.answer_combo)
        answer_layout.addWidget(self.add_choice_button)
        answer_layout.addWidget(self.stops_label)
        answer_layout.addStretch(1)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(answer_layout)
        self.setLayout(main_layout)

        self._reload_choices()

    def _wrap_focus_in(self, original_handler):
        """Show this question in the shared preview when its text box gains focus."""
        def handler(event):
            self._notify_preview()
            original_handler(event)
        return handler

    def _notify_preview(self):
        if self._preview_callback:
            self._preview_callback(self._seed_string)

    def _on_text_changed(self):
        self._seed_string.set_text(self.text_edit.toPlainText())
        self._reload_choices()
        self._notify_preview()

    def _on_answer_changed(self, index):
        self._seed_string.answer = index
        self._notify_preview()

    def _on_add_choice(self):
        self._seed_string.add_choice()
        with QSignalBlocker(self.text_edit):
            self.text_edit.setPlainText(self._seed_string.get_text())
        self._reload_choices()
        self._notify_preview()

    def _reload_choices(self):
        """Rebuild the answer dropdown and the stop summary from the current text."""
        choices = self._seed_string.get_choices()
        with QSignalBlocker(self.answer_combo):
            self.answer_combo.clear()
            for index, (stop, snippet) in enumerate(choices):
                label = f"{index}: {snippet}" if snippet else f"{index}: (choice 0x{stop:02x})"
                self.answer_combo.addItem(label)
            if self._seed_string.answer >= len(choices):  # Out of range answer, keep it visible
                self.answer_combo.addItem(f"{self._seed_string.answer}: (out of range)")
                self.answer_combo.setCurrentIndex(self.answer_combo.count() - 1)
            else:
                self.answer_combo.setCurrentIndex(self._seed_string.answer)
        self.answer_combo.setEnabled(bool(choices))
        if choices:
            self.stops_label.setText("Cursor stops: " + ", ".join(f"0x{stop:02x}" for stop, _ in choices))
        else:
            self.stops_label.setText("No cursor stop (plain text)")


class SeedScreenCanvas(QWidget):
    """The test screen as the PC shows it (640x480, see seedscreen.DISPLAY_SIZE), fitted to the room
    it has: from half size (smoothed) up."""

    def __init__(self):
        QWidget.__init__(self)
        width, height = DISPLAY_SIZE
        self._size = (width, height)
        self.setMinimumSize(width // 2, height // 2)
        # As wide as the column allows, and only as tall as the screen needs at that width
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._pixmap = None

    def sizeHint(self):
        return QSize(*self._size)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(self._size[1] // 2, width * self._size[1] // self._size[0])

    def set_image(self, image):
        rgba = image.convert("RGBA")
        qimage = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
        self._pixmap = QPixmap.fromImage(qimage)
        self.update()

    def paintEvent(self, _event):
        if self._pixmap is None:
            return
        painter = QPainter(self)
        scale = min(self.width() / self._pixmap.width(), self.height() / self._pixmap.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, scale < 1)
        width, height = int(self._pixmap.width() * scale), int(self._pixmap.height() * scale)
        painter.drawPixmap(QRect(0, 0, width, height), self._pixmap)


class SeedPreviewWidget(QWidget):
    """The focused question on the SeeD test screen, as the game draws it (see seedscreen.py): the
    three windows, the text in the real menu font at the engine's pen positions and clipped where
    the game clips it, and a cursor hand at each choice (the expected answer's in green)."""

    def __init__(self, game_data: GameData):
        QWidget.__init__(self)
        self.game_data = game_data
        self.metrics = None  # sysfnt.tdw, when opened
        self.atlas = None    # sysfnt.TEX, when opened
        self.icons = None    # icon.sp1 + icon.TEX (MenuIcons), when opened
        self._notices = {}   # what is missing, per side file group
        self._seed_string = None

        self.canvas = SeedScreenCanvas()
        self.canvas.setToolTip("The SeeD test screen as the game draws it (positions from the exe). The text "
                               "is cut where the game cuts it;\nthe hands point at the choices, the expected "
                               "answer's in green. The title and help bars hold other menu text.")
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.font_notice = QLabel()
        self.font_notice.setWordWrap(True)
        self.font_notice.setStyleSheet("color: #c07000;")

        # The values the screen fills in when it opens: samples, so the lines get their real width
        self.value_edits = {}
        values_layout = QHBoxLayout()
        values_layout.addWidget(QLabel("Values shown:"))
        for name, label, tip in (
                ("SeedTestLevelOrScore", "level / score", "{SeedTestLevelOrScore}: the test level, or the AP "
                                                          "scored (10 per right answer) on a failed test"),
                ("NextSeedTestLevel", "next level", "{NextSeedTestLevel}: the level of the test offered"),
                ("SeedRank", "rank", "{SeedRank}: the SeeD rank, digits or \"A\"")):
            edit = QLineEdit(SAMPLE_VALUES[name])
            edit.setMaxLength(3)
            edit.setFixedWidth(40)
            edit.setToolTip(tip + " (only for this preview, not saved)")
            edit.textChanged.connect(self._redraw)
            values_layout.addWidget(QLabel(label))
            values_layout.addWidget(edit)
            self.value_edits[name] = edit
        values_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        layout.addWidget(self.status_label)
        layout.addLayout(values_layout)
        layout.addWidget(self.font_notice)
        layout.addStretch(1)
        self._redraw()

    def set_font(self, metrics, atlas, notice=""):
        """The opened menu font (None for a file not opened) and what to say about a missing one."""
        self.metrics = metrics
        self.atlas = atlas
        self._set_notice("font", notice)

    def set_icons(self, icons, notice=""):
        """The opened menu icons (MenuIcons: the hand and the window border), None when not opened."""
        self.icons = icons
        self._set_notice("icons", notice)

    def _set_notice(self, key, notice):
        self._notices[key] = notice
        text = "\n".join(text for text in self._notices.values() if text)
        self.font_notice.setText(text)
        self.font_notice.setVisible(bool(text))
        self._redraw()

    def show_string(self, seed_string):
        self._seed_string = seed_string
        self._redraw()

    def values(self):
        return {name: edit.text() for name, edit in self.value_edits.items()}

    def _redraw(self, *_args):
        text = self._seed_string.get_text() if self._seed_string is not None else ""
        answer = self._seed_string.answer if self._seed_string is not None else -1
        screen = render_seed_screen(text, answer, self.game_data, self.metrics, self.atlas, self.values(),
                                    icons=self.icons)
        self.screen = screen
        self.canvas.set_image(screen.displayed())
        if self._seed_string is None:
            self.status_label.setText("")
            return
        lines = screen.layout.line_count
        parts = [f"Widest line: {screen.ink_right} of {MAX_TEXT_WIDTH} px",
                 f"lines: {lines} of {MAX_LINES}",
                 f"choices: {len(screen.layout.stops)}"]
        status = ", ".join(parts) + "."
        cut = []
        if screen.cut_columns:
            cut.append(f"the last {screen.cut_columns} px of the widest line")
        if screen.cut_lines:
            cut.append(f"{screen.cut_lines} line(s) at the bottom")
        if cut:
            status += " The game cuts off " + " and ".join(cut) + "."
        no_answer = screen.layout.stops and answer >= len(screen.layout.stops)
        if no_answer:
            status += f" The expected answer ({answer}) is not one of the choices: no answer can be right."
        self.status_label.setText(status)
        self.status_label.setStyleSheet("color: #d04040;" if cut or no_answer else "")


class ShivaSeedTestWidget(QWidget):
    """SeeD written test editor: the string sections 95-126 of mngrp.bin.

    Reads its sections out of the shared mngrp, so it cannot overwrite the other tabs' sections.
    The CSV export/import stays here, on the tab, as it only concerns the SeeD test strings."""

    def __init__(self, game_data, font_source=None):
        """`font_source`: the menu font (sysfnt.TEX / sysfnt.tdw side files, Common.pagefontsource) the
        preview draws with; None draws boxes of a uniform width."""
        QWidget.__init__(self)
        self.game_data = game_data
        self.seed_tests = None
        self.font_source = font_source

        self.file_dialog = QFileDialog()

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setToolTip("Export every question (answer + text) to a CSV file, editable in Excel")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self.export_csv)

        self.import_csv_button = QPushButton("Import CSV")
        self.import_csv_button.setToolTip("Load a CSV file exported here (UTF-8) back onto the SeeD tests "
                                          "(use the save button to write it into mngrp.bin)")
        self.import_csv_button.setEnabled(False)
        self.import_csv_button.clicked.connect(self.import_csv)

        csv_layout = QHBoxLayout()
        csv_layout.addWidget(self.export_csv_button)
        csv_layout.addWidget(self.import_csv_button)
        csv_layout.addStretch(1)

        # Test list (left side), with a Ctrl+F search bar filtering it
        self.section_list = QListWidget()
        self.section_list.setFixedWidth(180)
        self.section_list.currentRowChanged.connect(self.reload_selected_section)
        self.section_search = ListSearchBar.wrap(self.section_list)

        # Question editors (middle, scrollable)
        self.question_container = QWidget()
        self.question_layout = QVBoxLayout()
        self.question_layout.addStretch(1)
        self.question_container.setLayout(self.question_layout)

        self.question_scroll = QScrollArea()
        self.question_scroll.setWidgetResizable(True)
        self.question_scroll.setWidget(self.question_container)
        self.question_scroll.setEnabled(False)

        # In-game preview (right side), follows the focused / edited question
        self.preview = SeedPreviewWidget(self.game_data)
        preview_title = QLabel("In-game preview")
        preview_title.setStyleSheet("font-weight: bold;")
        preview_column = QVBoxLayout()
        preview_column.addWidget(preview_title)
        preview_column.addWidget(self.preview, 1)
        if self.font_source is not None:
            self.font_source.changed.connect(self._apply_font)
        self._apply_font()

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.section_search.column)
        main_editor_layout.addWidget(self.question_scroll, 1)
        main_editor_layout.addLayout(preview_column, 1)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(csv_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def load_from_mngrp(self, manager):
        self.seed_tests = SeedTestSet.from_mngrp(self.game_data, manager.mngrp)
        self.question_scroll.setEnabled(True)
        self.export_csv_button.setEnabled(True)
        self.import_csv_button.setEnabled(True)
        with QSignalBlocker(self.section_list):
            self.section_list.clear()
            self.section_list.addItem(self.seed_tests.general_section.name)
            for seed_test in self.seed_tests.test_list:
                self.section_list.addItem(seed_test.name)
        self.section_list.setCurrentRow(1)  # Test 1
        self.reload_selected_section()

    def _apply_font(self):
        """sysfnt.TEX / sysfnt.tdw opened or removed: draw with what is open."""
        if self.font_source is None:
            self.preview.set_font(None, None, "No menu font: the text is drawn as boxes of a uniform width.")
            return
        self.preview.set_font(self.font_source.metrics, self.font_source.atlas, self.font_source.notice())

    def save_to_mngrp(self, manager):
        """Nothing to do: the strings edited here are the shared mngrp's own SeeD sections."""

    def export_csv(self):
        if not self.seed_tests:
            return
        file_name = self.file_dialog.getSaveFileName(parent=self, caption="Export SeeD tests to CSV",
                                                     filter="*.csv", directory="seed_test.csv")[0]
        if not file_name:
            return
        # Fixed "|" delimiter (same as the shiva CLI export), so GUI and CLI CSVs are interchangeable
        with open(file_name, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file, delimiter="|", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(SeedTestSet.CSV_HEADER)
            writer.writerows(self.seed_tests.to_csv_rows())

    def import_csv(self):
        if not self.seed_tests:
            return
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Import SeeD tests from CSV (UTF-8)",
                                                     filter="*.csv")[0]
        if not file_name:
            return
        try:
            delimiter = GameData.find_delimiter_from_csv_file(file_name)
            with open(file_name, newline="", encoding="utf-8") as csv_file:
                rows = list(csv.reader(csv_file, delimiter=delimiter, quotechar='"'))
            self.seed_tests.apply_csv_rows(rows[1:])  # skip the header row
        except (UnicodeDecodeError, ValueError, IndexError) as error:
            QMessageBox.critical(self, "Shiva - SeeD tests", f"Could not import the CSV:\n{error}")
            return
        self.reload_selected_section()
        QMessageBox.information(self, "Shiva - SeeD tests",
                                "CSV imported. Use the save button to write it into mngrp.bin.")

    def reload_selected_section(self):
        """Rebuild the question editors from the selected test."""
        seed_test = self._selected_test()
        if not seed_test:
            return
        while self.question_layout.count() > 1:  # Keep the trailing stretch
            item = self.question_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        general = seed_test is self.seed_tests.general_section
        for index, seed_string in enumerate(seed_test.strings):
            title = f"String {index}" if general else f"Question {index + 1}"
            self.question_layout.insertWidget(
                index, NidaQuestionWidget(title, seed_string, preview_callback=self.preview.show_string))
        self.preview.show_string(seed_test.strings[0] if seed_test.strings else None)

    def _selected_test(self):
        if not self.seed_tests:
            return None
        index = self.section_list.currentRow()
        if index == 0:
            return self.seed_tests.general_section
        if 1 <= index <= len(self.seed_tests.test_list):
            return self.seed_tests.test_list[index - 1]
        return None
