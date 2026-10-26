import copy
from functools import partial

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton,
                             QComboBox, QSpinBox, QLineEdit, QTableWidget, QHeaderView, QFileDialog,
                             QMessageBox)

from Common.kernelnamesource import KernelNameSource
from FF8GameData.m00x.dataclass import TypeId
from FF8GameData.menu.mngrp.m00x.refineabilities import MAX_TABLE_ENTRIES
from Shiva.ShivaRefine.refinecsv import read_refine_csv, write_refine_csv
from Shiva.ShivaRefine.refineview import RefineLayout
from SmallWidget.listsearchbar import ListSearchBar


class ShivaRefineWidget(QWidget):
    """Refine abilities editor: the m00x sections of mngrp.bin (m000 to m004).

    Reads the entries and their text straight out of the shared mngrp, so it has no parsing of
    its own: saving needs nothing from it either, the entries are already the ones of the model
    and MngrpManager recomputes the text offsets of the m00x sections when it writes the file.

    Which recipes each ability offers comes from kernel.bin (a first and last entry per menu
    ability): with one open, recipes can be added and removed, and Shiva's save writes the moved
    ranges back into it. Without one there are no abilities to show: each table is listed whole,
    editable, with a fixed count."""

    TYPE_NAMES = {TypeId.ITEM: "Item", TypeId.SPELL: "Magic", TypeId.CARD: "Card"}

    KERNEL_NOTICE = ("No refine abilities: which recipes each one offers comes only from kernel.bin, so "
                     "every table is listed whole and recipes cannot be added or removed. Open one with "
                     "the toolbar's \"Import complementary\" button.")

    COLUMN_TEXT = 0
    COLUMN_INPUT = 1
    COLUMN_AMOUNT_REQUIRED = 2
    COLUMN_OUTPUT = 3
    COLUMN_AMOUNT_RECEIVED = 4
    COLUMN_GF_LEVEL = 5

    GF_LEVEL_TOOLTIP = ("Required GF level: the refine is only offered when a GF that learned this refine "
                        "ability is at this level or higher.\n"
                        "Vanilla: 1, except 100 for Curse Spike -> Dark Matter and Shaman Stone -> Hero-trial.\n"
                        "The PC game ignores it (every refine counts as level 100) unless FF8 Gameplay "
                        "Customizer's Archeology > Refine GF level option is on.")

    def __init__(self, game_data):
        QWidget.__init__(self)
        self.game_data = game_data
        self.manager = None
        self.layout = None            # RefineLayout of the loaded mngrp
        self.kernel_abilities = None  # kernel.bin's refine abilities as saved (None: no kernel.bin)
        # The items a refine can take or give: the game's 0-198 until set_item_entries hands over
        # those of an opened kernel.bin (renamed, and FFNx AddMoreItems' 199-255).
        self._item_entries = [{"value": item["id"], "name": item["name"]}
                              for item in self.game_data.item_data_json["items"] if item["id"] < 199]

        # Refine ability list (left side), with a Ctrl+F search bar filtering it
        self.section_list = QListWidget()
        self.section_list.setFixedWidth(180)
        self.section_list.currentRowChanged.connect(self.reload_selected_section)
        self.section_search = ListSearchBar.wrap(self.section_list)

        # Editor (right side)
        self.section_name_label = QLabel("")
        self.section_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.section_description_label = QLabel("")
        self.section_description_label.setStyleSheet("font-style: italic;")

        self.entry_table = QTableWidget()
        self.entry_table.setColumnCount(6)
        self.entry_table.setHorizontalHeaderLabels(["Text", "Input", "Amount required", "Output",
                                                    "Amount received", "Required GF level"])
        self.entry_table.horizontalHeaderItem(self.COLUMN_GF_LEVEL).setToolTip(self.GF_LEVEL_TOOLTIP)
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_TEXT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_INPUT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.horizontalHeader().setSectionResizeMode(self.COLUMN_OUTPUT, QHeaderView.ResizeMode.Stretch)
        self.entry_table.verticalHeader().setVisible(True)

        # CSV of every refine entry: same file as the shiva CLI export-refine-csv / import-refine-csv
        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setToolTip("Export every refine entry (all abilities) to a CSV file, editable in Excel")
        self.export_csv_button.clicked.connect(self.export_csv)
        self.import_csv_button = QPushButton("Import CSV")
        self.import_csv_button.setToolTip("Load a refine CSV (UTF-8) exported here or by the shiva CLI")
        self.import_csv_button.clicked.connect(self.import_csv)
        csv_layout = QHBoxLayout()
        csv_layout.addWidget(self.export_csv_button)
        csv_layout.addWidget(self.import_csv_button)
        csv_layout.addStretch(1)

        # Recipes in and out: the ranges of kernel.bin move with them
        self.add_recipe_button = QPushButton("Add recipe")
        self.add_recipe_button.setToolTip("Insert a copy of the selected recipe right after it")
        self.add_recipe_button.clicked.connect(self.add_recipe)
        self.remove_recipe_button = QPushButton("Remove recipe")
        self.remove_recipe_button.setToolTip("Remove the selected recipe")
        self.remove_recipe_button.clicked.connect(self.remove_recipe)
        self.range_label = QLabel("")
        recipe_layout = QHBoxLayout()
        recipe_layout.addWidget(self.add_recipe_button)
        recipe_layout.addWidget(self.remove_recipe_button)
        recipe_layout.addWidget(self.range_label, 1)
        self.kernel_notice = KernelNameSource.make_notice("")
        self.kernel_notice.setText(self.KERNEL_NOTICE)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color:#b9770e;")
        self.warning_label.setVisible(False)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addLayout(csv_layout)
        editor_layout.addWidget(self.section_name_label)
        editor_layout.addWidget(self.section_description_label)
        editor_layout.addLayout(recipe_layout)
        editor_layout.addWidget(self.kernel_notice)
        editor_layout.addWidget(self.entry_table)
        editor_layout.addWidget(self.warning_label)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.section_search.column)
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

    @property
    def refine_views(self):
        return self.layout.views if self.layout else []

    def load_from_mngrp(self, manager):
        self.manager = manager
        self._build_layout()
        self.editor_container.setEnabled(True)

    def set_kernel_abilities(self, abilities):
        """kernel.bin's refine abilities (read_refine_abilities), None when none is open.

        Recipes added or removed but not saved yet keep their ranges: only the names are taken,
        a kernel.bin re-read from disk holds the old ranges."""
        self.kernel_abilities = abilities
        if self.layout is not None and self.layout.ranges_changed:
            by_index = {ability.index: ability for ability in abilities or []}
            for ability in self.layout.abilities:
                if ability.index in by_index:
                    ability.name = by_index[ability.index].name
                    ability.description = by_index[ability.index].description
            self._fill_section_list(self._selected_refine_view())
            return
        if self.manager is not None:
            self._build_layout()
        else:
            self.kernel_notice.setVisible(abilities is None)

    def _build_layout(self):
        selected = self._selected_refine_view()
        place = selected.key if selected else None
        abilities = copy.deepcopy(self.kernel_abilities) if self.kernel_abilities is not None else None
        self.layout = RefineLayout(self.manager, abilities)
        keep = next((view for view in self.layout.views if view.key == place), None)
        self._fill_section_list(keep)

    def _fill_section_list(self, keep_view=None):
        """Rebuild the ability list, selecting the view of the same ability as keep_view."""
        views = self.refine_views
        row = 0
        if keep_view is not None:
            row = next((index for index, view in enumerate(views) if view.ability is keep_view.ability
                        or view.key == keep_view.key), 0)
        with QSignalBlocker(self.section_list):
            self.section_list.clear()
            for refine_view in views:
                self.section_list.addItem(f"{refine_view.bin_name} - {refine_view.name}")
            for index, refine_view in enumerate(views):
                self.section_list.item(index).setToolTip(refine_view.description)
            if views:
                self.section_list.setCurrentRow(row)
        self.kernel_notice.setVisible(not self.layout.from_kernel)
        self.reload_selected_section()

    def add_recipe(self):
        refine_view = self._selected_refine_view()
        if not refine_view:
            return
        row = self.entry_table.currentRow()
        try:
            new_row = self.layout.insert_entry(refine_view, row if row >= 0 else len(refine_view.entries) - 1)
        except ValueError as error:
            QMessageBox.warning(self, "Shiva - Refine", str(error))
            return
        self._fill_section_list(refine_view)
        self.entry_table.setCurrentCell(new_row, self.COLUMN_TEXT)

    def remove_recipe(self):
        refine_view = self._selected_refine_view()
        row = self.entry_table.currentRow()
        if not refine_view or row < 0:
            return
        try:
            self.layout.remove_entry(refine_view, row)
        except ValueError as error:
            QMessageBox.warning(self, "Shiva - Refine", str(error))
            return
        self._fill_section_list(refine_view)
        self.entry_table.setCurrentCell(min(row, self.entry_table.rowCount() - 1), self.COLUMN_TEXT)

    def set_item_entries(self, entries):
        """[{"value", "name"}] of the items offered (KernelNameSource.item_entries)."""
        self._item_entries = list(entries)
        self.reload_selected_section()

    def save_to_mngrp(self, manager):
        """Nothing to do: the entries and texts edited here are the ones of the shared mngrp,
        and their offsets are recomputed when the file is written."""

    def export_csv(self):
        if not self.refine_views:
            return
        file_name = QFileDialog.getSaveFileName(self, "Export refine entries to CSV", "refine.csv", "*.csv")[0]
        if file_name:
            write_refine_csv(file_name, self.layout)

    def import_csv(self):
        if not self.refine_views:
            return
        file_name = QFileDialog.getOpenFileName(self, "Import refine entries from CSV (UTF-8)", "", "*.csv")[0]
        if not file_name:
            return
        try:
            applied = read_refine_csv(file_name, self.layout)
        except (UnicodeDecodeError, ValueError, KeyError, IndexError) as error:
            QMessageBox.critical(self, "Shiva - Refine", f"Could not import the CSV:\n{error}")
            self._fill_section_list(self._selected_refine_view())  # the rows applied before the error
            return
        self._fill_section_list(self._selected_refine_view())
        QMessageBox.information(self, "Shiva - Refine",
                                f"{applied} refine entries imported. Use the save button to write them into mngrp.bin.")

    def reload_selected_section(self):
        """Rebuild the entry table from the selected refine ability data."""
        refine_view = self._selected_refine_view()
        if not refine_view:
            return
        self.section_name_label.setText(f"{refine_view.bin_name} - {refine_view.name}")
        self.section_description_label.setText(
            f"{self.TYPE_NAMES[refine_view.input_type]} -> {self.TYPE_NAMES[refine_view.output_type]}"
            + (f" - {refine_view.description}" if refine_view.description else ""))
        self.add_recipe_button.setEnabled(refine_view.editable_range)
        self.remove_recipe_button.setEnabled(refine_view.editable_range and len(refine_view.entries) > 1)
        owner = (f", menu ability {refine_view.ability.index} of kernel.bin"
                 if refine_view.kind == "ability" else "")
        self.range_label.setText(f"Entries {refine_view.first}-{refine_view.last} of {refine_view.bin_name}"
                                 f"{owner} - {len(refine_view.bin_section.entries)}/{MAX_TABLE_ENTRIES} "
                                 f"used in the table")

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
            input_combo.activated.connect(self._update_warnings)
            self.entry_table.setCellWidget(row, self.COLUMN_INPUT, input_combo)

            amount_required_spin = self._create_amount_spinbox(entry.amount_required)
            amount_required_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'amount_required'))
            self.entry_table.setCellWidget(row, self.COLUMN_AMOUNT_REQUIRED, amount_required_spin)

            output_combo = self._create_element_combo(output_names, entry.element_out_id)
            output_combo.activated.connect(partial(self._on_element_changed, entry, 'element_out_id', output_combo))
            self.entry_table.setCellWidget(row, self.COLUMN_OUTPUT, output_combo)

            amount_received_spin = self._create_amount_spinbox(entry.amount_received, 65535)
            amount_received_spin.setToolTip("Amount received (2 bytes in the file); the result is still capped at 100")
            amount_received_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'amount_received'))
            self.entry_table.setCellWidget(row, self.COLUMN_AMOUNT_RECEIVED, amount_received_spin)

            gf_level_spin = QSpinBox()
            gf_level_spin.setRange(0, 255)
            gf_level_spin.setValue(entry.required_gf_level)
            gf_level_spin.setToolTip(self.GF_LEVEL_TOOLTIP)
            gf_level_spin.valueChanged.connect(partial(self._on_amount_changed, entry, 'required_gf_level'))
            self.entry_table.setCellWidget(row, self.COLUMN_GF_LEVEL, gf_level_spin)
        self._update_warnings()

    def _update_warnings(self, *_):
        """The layout's warnings, and the recipes the menu never offers (an earlier one of the same
        ability takes the same input: the game uses the first match)."""
        refine_view = self._selected_refine_view()
        lines = list(self.layout.warnings) if self.layout else []
        if refine_view:
            for row, earlier in sorted(refine_view.duplicate_inputs().items()):
                lines.append(f"Recipe {row + 1} takes the same input as recipe {earlier + 1}: "
                             f"the game only uses the first one.")
        self.warning_label.setText("\n".join(lines))
        self.warning_label.setVisible(bool(lines))

    def _selected_refine_view(self):
        index = self.section_list.currentRow()
        if 0 <= index < len(self.refine_views):
            return self.refine_views[index]
        return None

    def _element_names(self, type_id):
        """[(game ID, name)] of the input/output elements of a refine section."""
        if type_id == TypeId.CARD:
            element_list = self.game_data.card_data_json["card_info"]
        elif type_id == TypeId.SPELL:
            element_list = self.game_data.magic_data_json["magic"]
        else:  # TypeId.ITEM
            return [(entry["value"], f"{entry['value']}: {entry['name']}" if entry["value"] >= 199
                     else entry["name"]) for entry in self._item_entries]
        return [(element["id"], element["name"]) for element in element_list]

    @staticmethod
    def _create_element_combo(names, element_id):
        combo = QComboBox()
        for game_id, name in names:
            combo.addItem(name, game_id)
        if combo.findData(element_id) < 0:  # Unknown value, add a temporary entry to not lose it
            combo.addItem(f"Unknown ({element_id})", element_id)
        combo.setCurrentIndex(combo.findData(element_id))
        return combo

    @staticmethod
    def _create_amount_spinbox(value, maximum=255):
        spinbox = QSpinBox()
        spinbox.setRange(0, maximum)
        spinbox.setValue(value)
        return spinbox

    @staticmethod
    def _on_text_changed(text, new_text):
        text.set_str(new_text)

    @staticmethod
    def _on_element_changed(entry, attribute_name, combo, index):
        setattr(entry, attribute_name, combo.itemData(index))

    @staticmethod
    def _on_amount_changed(entry, attribute_name, value):
        setattr(entry, attribute_name, value)
