import csv
import os

from PyQt6.QtCore import QSize, QSignalBlocker, Qt, QRectF, QPointF
from PyQt6.QtGui import QIcon, QPainter, QColor, QFont, QPen, QBrush, QPolygonF
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QComboBox, QPlainTextEdit, QGroupBox, QScrollArea, QMessageBox)

from FF8GameData.gamedata import GameData
from Shiva.ShivaSeedTest.seedtest import SeedString, SeedTestSet
from Shiva.ShivaSeedTest.seedfont import (SeedFontMetrics, layout_text, overflows, LINE_HEIGHT,
                                          VANILLA_MAX_WIDTH, VANILLA_MAX_LINES)


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


class SeedPreviewWidget(QWidget):
    """In-game layout preview of one SeeD question, drawn with the real FF8 font
    widths: the box is the vanilla text envelope, glyphs sit at the exact pen
    positions the engine computes, and each choice cursor stop is marked (the
    expected answer in green)."""
    SCALE = 1.4  # Game pixels -> screen pixels
    MARGIN = 10

    BG_COLOR = QColor(20, 24, 48)
    BOX_COLOR = QColor(120, 140, 200)
    OVERFLOW_COLOR = QColor(220, 90, 90)
    TEXT_COLOR = QColor(240, 240, 240)
    STOP_COLOR = QColor(230, 200, 80)
    EXPECTED_COLOR = QColor(90, 210, 120)

    def __init__(self, game_data: GameData, metrics: SeedFontMetrics):
        QWidget.__init__(self)
        self.game_data = game_data
        self.metrics = metrics
        self._seed_string = None
        box_w = int(VANILLA_MAX_WIDTH * self.SCALE) + 2 * self.MARGIN
        box_h = int(VANILLA_MAX_LINES * LINE_HEIGHT * self.SCALE) + 2 * self.MARGIN
        self.setMinimumSize(box_w + 4, box_h + 4)
        self.setToolTip("Preview of how the question renders in game (real FF8 character widths). "
                        "The blue box is the vanilla size envelope; content past it (red) risks overflowing.")

    def set_metrics(self, metrics: SeedFontMetrics):
        self.metrics = metrics
        self.update()

    def show_string(self, seed_string):
        self._seed_string = seed_string
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.BG_COLOR)
        if self._seed_string is None:
            return

        layout = layout_text(self._seed_string.get_text(), self.game_data, self.metrics)
        overflow = overflows(layout)
        scale = self.SCALE
        origin_x = self.MARGIN
        origin_y = self.MARGIN

        # Vanilla envelope box
        box_w = VANILLA_MAX_WIDTH * scale
        box_h = VANILLA_MAX_LINES * LINE_HEIGHT * scale
        painter.setPen(QPen(self.OVERFLOW_COLOR if overflow else self.BOX_COLOR, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(origin_x, origin_y, box_w, box_h))

        # Glyphs at their true FF8 pen positions
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)  # Fall back to any monospace font
        font.setPixelSize(int(LINE_HEIGHT * scale * 0.8))
        painter.setFont(font)
        painter.setPen(self.TEXT_COLOR)
        for glyph in layout.glyphs:
            gx = origin_x + glyph.x * scale
            gy = origin_y + glyph.y * scale
            painter.drawText(QRectF(gx, gy, max(glyph.width, 1) * scale + scale, LINE_HEIGHT * scale),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), glyph.char)

        # Choice cursor stops (the pointing hand); the expected answer highlighted
        expected = self._seed_string.answer
        for stop in layout.stops:
            sx = origin_x + stop.x * scale
            sy = origin_y + stop.y * scale
            is_expected = stop.index == expected
            color = self.EXPECTED_COLOR if is_expected else self.STOP_COLOR
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            mid = sy + LINE_HEIGHT * scale / 2
            triangle = QPolygonF([QPointF(sx - 12, mid - 5), QPointF(sx - 12, mid + 5), QPointF(sx - 3, mid)])
            painter.drawPolygon(triangle)

        # Status line under the box
        painter.setPen(self.OVERFLOW_COLOR if overflow else self.BOX_COLOR)
        status_font = QFont()
        status_font.setPixelSize(12)
        painter.setFont(status_font)
        parts = [f"width {layout.max_width}px / {VANILLA_MAX_WIDTH}",
                 f"lines {layout.line_count} / {VANILLA_MAX_LINES}",
                 f"choices {len(layout.stops)}"]
        if overflow:
            parts.append("- may overflow in game")
        if not self.metrics.exact:
            parts.append("(approx widths: sysfnt.tdw not found)")
        painter.drawText(QRectF(origin_x, origin_y + box_h + 2, self.width() - 2 * self.MARGIN, 18),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "   ".join(parts))


class ShivaSeedTestWidget(QWidget):
    """SeeD written test editor: the string sections 95-126 of mngrp.bin.

    Reads its sections out of the shared mngrp, so it cannot overwrite the other tabs' sections.
    The CSV export/import stays here, on the tab, as it only concerns the SeeD test strings."""

    def __init__(self, game_data):
        QWidget.__init__(self)
        self.game_data = game_data
        self.seed_tests = None
        self.mngrp_folder = ""  # Where sysfnt.tdw is looked for, set on load

        self.file_dialog = QFileDialog()
        self.metrics = SeedFontMetrics.from_folder("")  # Real FF8 font widths for the preview

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

        # Test list (left side)
        self.section_list = QListWidget()
        self.section_list.setFixedWidth(180)
        self.section_list.currentRowChanged.connect(self.reload_selected_section)

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
        self.preview = SeedPreviewWidget(self.game_data, self.metrics)
        preview_title = QLabel("In-game preview")
        preview_title.setStyleSheet("font-weight: bold;")
        preview_column = QVBoxLayout()
        preview_column.addWidget(preview_title)
        preview_column.addWidget(self.preview)
        preview_column.addStretch(1)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.section_list)
        main_editor_layout.addWidget(self.question_scroll, 1)
        main_editor_layout.addLayout(preview_column)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(csv_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def owned_section_ids(self, manager):
        """The SeeD string sections this tab edits, kept out of Shiva's raw-preserve pass."""
        return {SeedTestSet.GENERAL_SECTION_POS} | {SeedTestSet.FIRST_TEST_POS + index
                                                    for index in range(SeedTestSet.NB_TESTS)}

    def load_from_mngrp(self, manager):
        self.seed_tests = SeedTestSet.from_mngrp(self.game_data, manager.mngrp)
        # sysfnt.tdw sits next to mngrp.bin, used for the exact preview widths
        self.mngrp_folder = os.path.dirname(manager.mngrp_path) if getattr(manager, "mngrp_path", "") else ""
        self.metrics = SeedFontMetrics.from_folder(self.mngrp_folder)
        self.preview.set_metrics(self.metrics)
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

    def save_to_mngrp(self, manager):
        if self.seed_tests:
            self.seed_tests.save_to_mngrp(manager.mngrp)

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
