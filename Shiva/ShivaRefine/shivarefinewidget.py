from functools import partial

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                             QComboBox, QSpinBox, QLineEdit, QTableWidget, QHeaderView)

from FF8GameData.m00x.dataclass import TypeId
from Shiva.ShivaRefine.refineview import build_refine_views


class ShivaRefineWidget(QWidget):
    """Refine abilities editor: the m00x sections of mngrp.bin (m000 to m004).

    Reads the entries and their text straight out of the shared mngrp, so it has no parsing of
    its own: saving needs nothing from it either, the entries are already the ones of the model
    and MngrpManager recomputes the text offsets of the m00x sections when it writes the file."""

    COLUMN_TEXT = 0
    COLUMN_INPUT = 1
    COLUMN_AMOUNT_REQUIRED = 2
    COLUMN_OUTPUT = 3
    COLUMN_AMOUNT_RECEIVED = 4
    COLUMN_UNK = 5

    def __init__(self, game_data):
        QWidget.__init__(self)
        self.game_data = game_data
        self.refine_views = []

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
        self.entry_table.setHorizontalHeaderLabels(["Text", "Input", "Amount required", "Output",
                                                    "Amount received", "Unknown"])
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

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.section_list)
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

    def owned_section_ids(self, manager):
        """The m00x bin and msg sections this tab edits, kept out of Shiva's raw-preserve pass."""
        return ({bin_section.id for bin_section in manager.m00_manager.get_bin_list()}
                | {msg_section.id for msg_section in manager.m00_manager.get_msg_list()})

    def load_from_mngrp(self, manager):
        self.refine_views = build_refine_views(manager)
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.section_list):
            self.section_list.clear()
            for refine_view in self.refine_views:
                self.section_list.addItem(f"{refine_view.bin_name} - {refine_view.name}")
            for index, refine_view in enumerate(self.refine_views):
                self.section_list.item(index).setToolTip(refine_view.description)
        self.section_list.setCurrentRow(0)

    def save_to_mngrp(self, manager):
        """Nothing to do: the entries and texts edited here are the ones of the shared mngrp,
        and their offsets are recomputed when the file is written."""

    def reload_selected_section(self):
        """Rebuild the entry table from the selected refine ability data."""
        refine_view = self._selected_refine_view()
        if not refine_view:
            return
        self.section_name_label.setText(refine_view.name)
        self.section_description_label.setText(refine_view.description)

        input_names = self._element_names(refine_view.input_type)
        output_names = self._element_names(refine_view.output_type)

        self.entry_table.clearContents()
        self.entry_table.setRowCount(len(refine_view.entries))
        for row, entry in enumerate(refine_view.entries):
            text = refine_view.texts[row]
            text_edit = QLineEdit(text.get_str())
            text_edit.setToolTip("Text shown in the refine menu, remember the game special characters (like \\n)")
            text_edit.textChanged.connect(partial(self._on_text_changed, text))
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

    def _selected_refine_view(self):
        index = self.section_list.currentRow()
        if 0 <= index < len(self.refine_views):
            return self.refine_views[index]
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
    def _on_text_changed(text, new_text):
        text.set_str(new_text)

    @staticmethod
    def _on_element_changed(entry, attribute_name, combo, index):
        if combo.itemText(index).startswith("Unknown ("):  # Temporary entry, keep the original unknown ID
            return
        setattr(entry, attribute_name, index)

    @staticmethod
    def _on_amount_changed(entry, attribute_name, value):
        setattr(entry, attribute_name, value)
