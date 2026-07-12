import os
from functools import partial

from PyQt6.QtCore import QSize, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QListWidget,
                             QComboBox, QSpinBox, QLineEdit, QTableWidget, QHeaderView, QMessageBox)

from FF8GameData.gamedata import GameData
from FF8GameData.m00x.dataclass import TypeId
from Pandemona.pandemonamanager import PandemonaManager


class PandemonaWidget(QWidget):
    """Refine abilities editor (m00x data of mngrp.bin)."""

    COLUMN_TEXT = 0
    COLUMN_INPUT = 1
    COLUMN_AMOUNT_REQUIRED = 2
    COLUMN_OUTPUT = 3
    COLUMN_AMOUNT_RECEIVED = 4
    COLUMN_UNK = 5

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.game_data.load_magic_data()
        self.game_data.load_card_data()
        self.manager = PandemonaManager(self.game_data)

        self.setWindowTitle("Pandemona")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a mngrp.bin file (mngrphd.bin must be in the same folder)")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened mngrp.bin and mngrphd.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Refine ability list (left side)
        self.section_list = QListWidget()
        self.section_list.setFixedWidth(180)
        self.section_list.currentRowChanged.connect(self.reload_selected_section)

        # Editor (right side)
        self.section_name_label = QLabel("")
        self.section_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.section_description_label = QLabel("")
        self.section_description_label.setStyleSheet("font-style: italic;")

        self.entry_table = QTableWidget()
        self.entry_table.setColumnCount(6)
        self.entry_table.setHorizontalHeaderLabels(["Text", "Input", "Amount required", "Output", "Amount received",
                                                    "Unknown"])
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_TEXT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_INPUT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_OUTPUT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.verticalHeader().setVisible(True)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.section_name_label)
        editor_layout.addWidget(self.section_description_label)
        editor_layout.addWidget(self.entry_table)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.section_list)
        main_editor_layout.addWidget(self.editor_container)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search mngrp.bin file", filter="*.bin",
                                                     directory=os.getcwd())[0]
        if file_name:
            try:
                self.manager.load_file(file_name)
            except FileNotFoundError as error:
                QMessageBox.warning(self, "Pandemona", str(error))
                return
            self.file_label.setText(os.path.basename(file_name))
            self.editor_container.setEnabled(True)
            with QSignalBlocker(self.section_list):
                self.section_list.clear()
                for refine_section in self.manager.refine_sections:
                    self.section_list.addItem(f"{refine_section.bin_name} - {refine_section.name}")
                for index, refine_section in enumerate(self.manager.refine_sections):
                    self.section_list.item(index).setToolTip(refine_section.description)
            self.section_list.setCurrentRow(0)

    def save_file(self):
        if self.manager.mngrp_path:
            self.manager.save_file()

    def reload_selected_section(self):
        """Rebuild the entry table from the selected refine ability data."""
        refine_section = self._selected_refine_section()
        if not refine_section:
            return
        self.section_name_label.setText(refine_section.name)
        self.section_description_label.setText(refine_section.description)

        input_names = self._element_names(refine_section.input_type)
        output_names = self._element_names(refine_section.output_type)

        self.entry_table.clearContents()
        self.entry_table.setRowCount(len(refine_section.entries))
        for row, entry in enumerate(refine_section.entries):
            text_edit = QLineEdit(entry.text)
            text_edit.setToolTip("Text shown in the refine menu, remember the game special characters (like \\n)")
            text_edit.textChanged.connect(partial(self._on_text_changed, entry))
            self.entry_table.setCellWidget(row, self.COLUMN_TEXT, text_edit)

            input_combo = self._create_element_combo(input_names, entry.element_in_id)
            input_combo.activated.connect(partial(self._on_element_changed, entry, 'element_in_id', input_combo))
            self.entry_table.setCellWidget(row, self.COLUMN_INPUT, input_combo)

            amount_required_spin = self._create_amount_spinbox(entry.amount_required)
            amount_required_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'amount_required'))
            self.entry_table.setCellWidget(row, self.COLUMN_AMOUNT_REQUIRED, amount_required_spin)

            output_combo = self._create_element_combo(output_names, entry.element_out_id)
            output_combo.activated.connect(partial(self._on_element_changed, entry, 'element_out_id', output_combo))
            self.entry_table.setCellWidget(row, self.COLUMN_OUTPUT, output_combo)

            amount_received_spin = self._create_amount_spinbox(entry.amount_received)
            amount_received_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'amount_received'))
            self.entry_table.setCellWidget(row, self.COLUMN_AMOUNT_RECEIVED, amount_received_spin)

            unk_spin = QSpinBox()
            unk_spin.setRange(0, 65535)
            unk_spin.setValue(entry.unk)
            unk_spin.setToolTip("Unknown data")
            unk_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'unk'))
            self.entry_table.setCellWidget(row, self.COLUMN_UNK, unk_spin)

    def _selected_refine_section(self):
        index = self.section_list.currentRow()
        if 0 <= index < len(self.manager.refine_sections):
            return self.manager.refine_sections[index]
        return None

    def _element_names(self, type_id):
        """Names of the input/output elements of a refine section (index in the list == game ID)."""
        if type_id == TypeId.CARD:
            element_list = self.game_data.card_data_json["card_info"]
        elif type_id == TypeId.SPELL:
            element_list = self.game_data.magic_data_json["magic"]
        else:  # TypeId.ITEM
            element_list = self.game_data.item_data_json["items"]
        return [element["name"] for element in element_list]

    @staticmethod
    def _create_element_combo(names, element_id):
        combo = QComboBox()
        combo.addItems(names)
        if element_id >= len(names):  # Unknown value, add a temporary entry to not lose it
            combo.addItem(f"Unknown ({element_id})")
        combo.setCurrentIndex(min(element_id, combo.count() - 1))
        return combo

    @staticmethod
    def _create_amount_spinbox(value):
        spinbox = QSpinBox()
        spinbox.setRange(0, 255)
        spinbox.setValue(value)
        return spinbox

    @staticmethod
    def _on_text_changed(entry, text):
        entry.text = text

    @staticmethod
    def _on_element_changed(entry, attribute_name, combo, index):
        if combo.itemText(index).startswith("Unknown ("):  # Temporary entry, keep the original unknown ID
            return
        setattr(entry, attribute_name, index)

    @staticmethod
    def _on_amount_changed(entry, attribute_name, value):
        setattr(entry, attribute_name, value)
