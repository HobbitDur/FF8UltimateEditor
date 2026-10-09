"""Cronos extension: the elemental defense table of the NegativeElemDef DLL.

In the game, a spell junctioned to Elem-Def gives every element of its kernel.bin J-Elem defense
mask the same unsigned value. The Cronos NegativeElemDef DLL reads this table instead for every
spell it lists: one signed value per element (Fire +50 and Ice -50 from the same spell, a weakness
being a negative value). The game still applies value x stock / 100 per Elem-Def slot, on top of the
neutral 800, and the DLL clamps the total to -800% .. +200% (1000 = 100% absorb).

The file (cronos/elemdef.csv in the mod, served by Junction VIII from the game folder):

    # comment
    id;Fire;Ice;Thunder;Earth;Poison;Wind;Water;Holy    # anything after the 9 numbers is ignored

A spell without a line keeps its kernel.bin values, exactly as vanilla.
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QCheckBox, QWidget)

from SmallWidget.nowheel import NoWheelSpinBox

ELEMENTS = ["Fire", "Ice", "Thunder", "Earth", "Poison", "Wind", "Water", "Holy"]
VALUE_MIN, VALUE_MAX = -999, 999
FILE_FILTER = "Elemental defense table (*.csv);;All files (*)"
DEFAULT_FILE_NAME = "elemdef.csv"
SETTINGS_KEY = "solomonring/cronos_elemdef_path"


# ---- the file ---------------------------------------------------------------------------------------

def read_table(path):
    """{magic id: [8 values]} - the same rules as the DLL: '#' lines skipped, ';' ',' or tab between
    the numbers, a line needs an id 0-255 and 8 values, anything after them is ignored."""
    rows = {}
    with open(path, encoding="utf-8-sig") as file:
        for line in file:
            text = line.split("#", 1)[0].replace(",", ";").replace("\t", ";")
            fields = [part.strip() for part in text.split(";") if part.strip()]
            try:
                numbers = [int(part) for part in fields[:9]]
            except ValueError:
                continue
            if len(numbers) == 9 and 0 <= numbers[0] <= 255:
                rows[numbers[0]] = numbers[1:]
    return rows


def write_table(path, rows, names=None):
    names = names or {}
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("# Cronos elemental defense table, read by NegativeElemDef.dll (edit it in SolomonRing >\n"
                   "# Cronos extension). One line per magic id: the resistance % it gives each element when\n"
                   "# junctioned to Elem-Def (x stock / 100; +100 = immune, more = absorb, negative = weakness).\n"
                   "# A spell without a line keeps its kernel.bin J-Elem defense.\n"
                   "# id;" + ";".join(ELEMENTS) + "\n")
        for magic_id in sorted(rows):
            name = names.get(magic_id, "")
            file.write(f"{magic_id};" + ";".join(str(value) for value in rows[magic_id])
                       + (f"    # {name}" if name else "") + "\n")


def rows_from_kernel(entries):
    """The table that changes nothing: each spell's kernel mask/value written out per element.
    entries: {magic id: KernelEntry} of the Magic section."""
    rows = {}
    for magic_id, entry in entries.items():
        mask, value = entry.get("j_elem_defense"), entry.get("j_elem_defense_value")
        rows[magic_id] = [value if (mask >> element) & 1 else 0 for element in range(8)]
    return rows


# ---- the dialog -------------------------------------------------------------------------------------

class CronosElemDefDialog(QDialog):
    """Edit the table: one row per magic of the loaded kernel.bin, a value per element."""

    def __init__(self, parent, magic_entries, magic_names, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Cronos extension - Elemental defense table")
        self.resize(1000, 700)
        self._entries = magic_entries          # {id: KernelEntry}
        self._names = magic_names              # {id: name}
        self._settings = settings
        self._path = settings.value(SETTINGS_KEY, "") if settings is not None else ""
        self._dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        info = QLabel(
            "Needs the Cronos <b>NegativeElemDef.dll</b>. A <b>used</b> spell gives each element its own "
            "resistance % when junctioned to Elem-Def (x stock / 100): +100 = immune, above = absorb, "
            "<span style='color:#d04040'>negative = weakness</span> (-100 = x2 damage). An unused spell keeps "
            "its kernel.bin J-Elem defense. The total is clamped to -800% .. +200%.<br>"
            "Cronos ships the file as <i>CronosFiles/GameEnhancement/NegativeElemDef/cronos/elemdef.csv</i>.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._file_label = QLabel()
        self._file_label.setStyleSheet("color: gray;")
        layout.addWidget(self._file_label)

        self._table = QTableWidget(0, 3 + len(ELEMENTS))
        self._table.setHorizontalHeaderLabels(["Use", "Id", "Spell"] + ELEMENTS)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, 1)
        self._use = {}      # id -> QCheckBox
        self._spins = {}    # id -> [8 spinboxes]
        self._ids = []

        buttons = QHBoxLayout()
        for label, slot, tip in (
                ("Fill from kernel.bin", self._fill_from_kernel,
                 "Every spell, with the values its kernel.bin J-Elem defense gives today (changes nothing in game)"),
                ("Import...", self._import, "Open an existing table"),
                ("Save", self._save, "Save to the current file"),
                ("Save as...", self._save_as, "Save to a new file")):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._build_rows(sorted(set(self._names) | set(self._entries)))
        if self._path and os.path.isfile(self._path):
            self._load_rows(read_table(self._path))
        else:
            self._path = ""
        self._refresh_file_label()

    # ---- rows ------------------------------------------------------------------------------------
    def _build_rows(self, ids):
        for magic_id in ids:
            if magic_id in self._spins:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._ids.append(magic_id)
            use = QCheckBox()
            use.toggled.connect(lambda _on, i=magic_id: self._row_changed(i))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(6, 0, 0, 0)
            holder_layout.addWidget(use)
            self._table.setCellWidget(row, 0, holder)
            for column, text in ((1, str(magic_id)), (2, self._names.get(magic_id, "(not in this kernel.bin)"))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, column, item)
            spins = []
            for element in range(len(ELEMENTS)):
                spin = NoWheelSpinBox()
                spin.setRange(VALUE_MIN, VALUE_MAX)
                spin.setSuffix(" %")
                spin.valueChanged.connect(lambda _v, i=magic_id, s=spin: self._value_changed(i, s))
                self._table.setCellWidget(row, 3 + element, spin)
                spins.append(spin)
            self._use[magic_id] = use
            self._spins[magic_id] = spins

    def _value_changed(self, magic_id, spin):
        self._colour(spin)
        if self._loading:
            return
        if not self._use[magic_id].isChecked():
            self._use[magic_id].setChecked(True)   # editing a spell puts it in the table
        self._dirty = True

    def _row_changed(self, magic_id):
        enabled = self._use[magic_id].isChecked()
        for spin in self._spins[magic_id]:
            spin.setEnabled(enabled)
        if not self._loading:
            self._dirty = True

    @staticmethod
    def _colour(spin):
        value = spin.value()
        spin.setStyleSheet("color: #d04040;" if value < 0 else ("color: #2f9e44;" if value > 0 else ""))

    def _load_rows(self, rows):
        self._build_rows(sorted(set(rows) - set(self._spins)))
        self._loading = True
        try:
            for magic_id in self._ids:
                values = rows.get(magic_id)
                self._use[magic_id].setChecked(values is not None)
                for spin, value in zip(self._spins[magic_id], values or [0] * len(ELEMENTS)):
                    spin.setValue(max(VALUE_MIN, min(VALUE_MAX, value)))
                    self._colour(spin)
                self._row_changed(magic_id)
        finally:
            self._loading = False

    def rows(self):
        return {magic_id: [spin.value() for spin in self._spins[magic_id]]
                for magic_id in self._ids if self._use[magic_id].isChecked()}

    # ---- buttons ---------------------------------------------------------------------------------
    def _fill_from_kernel(self):
        if self.rows() and QMessageBox.question(
                self, "Fill from kernel.bin", "Replace every value with the kernel.bin ones?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._load_rows(rows_from_kernel(self._entries))
        self._dirty = True

    def _import(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open an elemental defense table", self._path, FILE_FILTER)
        if not path:
            return
        try:
            rows = read_table(path)
        except (OSError, UnicodeDecodeError) as error:
            QMessageBox.warning(self, "Import", f"Cannot read {path}:\n{error}")
            return
        self._load_rows(rows)
        self._set_path(path)
        self._dirty = False

    def _save(self):
        if not self._path:
            return self._save_as()
        try:
            write_table(self._path, self.rows(), self._names)
        except OSError as error:
            QMessageBox.warning(self, "Save", f"Cannot write {self._path}:\n{error}")
            return False
        self._dirty = False
        self._refresh_file_label()
        return True

    def _save_as(self):
        start = self._path or DEFAULT_FILE_NAME
        path, _ = QFileDialog.getSaveFileName(self, "Save the elemental defense table", start, FILE_FILTER)
        if not path:
            return False
        self._set_path(path)
        return self._save()

    def _set_path(self, path):
        self._path = path
        if self._settings is not None:
            self._settings.setValue(SETTINGS_KEY, path)
        self._refresh_file_label()

    def _refresh_file_label(self):
        self._file_label.setText(f"File: {self._path}" if self._path else "File: none yet (Save as... to create one)")

    def _confirm_discard(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved table", "Save the changes to the table first?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                      | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return bool(self._save())
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
