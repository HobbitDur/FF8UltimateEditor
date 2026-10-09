"""Cronos extension: the elemental defense table of the NegativeElemDef DLL.

In the game, a spell junctioned to Elem-Def gives every element of its kernel.bin J-Elem defense
mask the same unsigned value, and a G-Force gives no elemental defense at all. The Cronos
NegativeElemDef DLL reads this table instead:
  - a spell line: one signed value per element (Fire +50 and Ice -50 from the same spell, a weakness
    being a negative value), applied x stock / 100 per Elem-Def slot like the kernel value;
  - a GF line: one signed value per element, given flat (no stock, no level) to the character the GF
    is junctioned to (Ifrit Fire +30 / Ice -30);
  - a character line: the character's own base resistance, flat, always (CH0 = Squall ... CH7 = Edea;
    Laguna, Kiros and Ward use Squall, Zell and Irvine's records in the dreams, so their lines too).
Everything adds up on top of the neutral 800 and the DLL clamps the total to -800% .. +200%.

The file (cronos/elemdef.csv in the mod, served by Junction VIII from the game folder):

    # comment
    id;Fire;Ice;Thunder;Earth;Poison;Wind;Water;Holy      a spell (magic id)
    GFid;Fire;Ice;Thunder;Earth;Poison;Wind;Water;Holy    a G-Force (GF0 = Quezacotl ... GF15 = Eden)
    CHid;Fire;Ice;Thunder;Earth;Poison;Wind;Water;Holy    a character (CH0 = Squall ... CH7 = Edea)
                                                          anything after the 9 numbers is ignored

A spell without a line keeps its kernel.bin values, exactly as vanilla; a GF or a character without a\nline gives nothing.
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QCheckBox, QWidget,
                             QTabWidget)

from SmallWidget.nowheel import NoWheelSpinBox

ELEMENTS = ["Fire", "Ice", "Thunder", "Earth", "Poison", "Wind", "Water", "Holy"]
GF_COUNT = 16
CHARA_COUNT = 8   # the save's character records; Laguna/Kiros/Ward use Squall/Zell/Irvine's in the dreams
VALUE_MIN, VALUE_MAX = -999, 999
FILE_FILTER = "Elemental defense table (*.csv);;All files (*)"
DEFAULT_FILE_NAME = "elemdef.csv"
SETTINGS_KEY = "solomonring/cronos_elemdef_path"
MAGIC_PAGE, GF_PAGE, CHARACTER_PAGE = 0, 1, 2


# ---- the file ---------------------------------------------------------------------------------------

def read_table(path):
    """(spell rows, GF rows, character rows), each {id: [8 values]} - the same rules as the DLL: '#'
    lines skipped, ; , or tab between the numbers, 9 numbers per line (a GF line starts with GF, a
    character line with CH, any case), spell id 0-255, GF id 0-15, character id 0-7, anything after the
    9 numbers ignored."""
    spells, gfs, characters = {}, {}, {}
    with open(path, encoding="utf-8-sig") as file:
        for line in file:
            text = line.split("#", 1)[0].strip()
            kind = text[:2].upper() if text[:2].upper() in ("GF", "CH") else ""
            if kind:
                text = text[2:]
            fields = [part.strip() for part in text.replace(",", ";").replace("\t", ";").split(";") if part.strip()]
            try:
                numbers = [int(part) for part in fields[:9]]
            except ValueError:
                continue
            if len(numbers) != 9:
                continue
            target, limit = {"GF": (gfs, GF_COUNT), "CH": (characters, CHARA_COUNT), "": (spells, 256)}[kind]
            if 0 <= numbers[0] < limit:
                target[numbers[0]] = numbers[1:]
    return spells, gfs, characters


def write_table(path, spells, gfs=None, characters=None, spell_names=None, gf_names=None, character_names=None):
    gfs, characters = gfs or {}, characters or {}
    spell_names, gf_names, character_names = spell_names or {}, gf_names or {}, character_names or {}
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("# Cronos elemental defense table, read by NegativeElemDef.dll (edit it in SolomonRing >\n"
                   "# Magic, G-Forces or Characters > Cronos extension). The resistance % given to each element:\n"
                   "#   spell line:     when junctioned to Elem-Def, x stock / 100 (no line = kernel.bin values)\n"
                   "#   GF line:        flat, to the character the GF is junctioned to (no line = nothing)\n"
                   "#   character line: flat, always - the character's base (no line = nothing)\n"
                   "# +100 = immune, more = absorb, negative = weakness.\n"
                   "# id;" + ";".join(ELEMENTS) + "\n")
        for magic_id in sorted(spells):
            file.write(_line(str(magic_id), spells[magic_id], spell_names.get(magic_id, "")))
        if gfs:
            file.write("\n# G-Forces: GFid;" + ";".join(ELEMENTS) + "\n")
            for gf_id in sorted(gfs):
                file.write(_line(f"GF{gf_id}", gfs[gf_id], gf_names.get(gf_id, "")))
        if characters:
            file.write("\n# Characters: CHid;" + ";".join(ELEMENTS) + "\n")
            for chara_id in sorted(characters):
                file.write(_line(f"CH{chara_id}", characters[chara_id], character_names.get(chara_id, "")))

def _line(key, values, name):
    return f"{key};" + ";".join(str(value) for value in values) + (f"    # {name}" if name else "") + "\n"


def rows_from_kernel(entries):
    """The spell lines that change nothing: each spell's kernel mask/value written out per element.
    entries: {magic id: KernelEntry} of the Magic section."""
    rows = {}
    for magic_id, entry in entries.items():
        mask, value = entry.get("j_elem_defense"), entry.get("j_elem_defense_value")
        rows[magic_id] = [value if (mask >> element) & 1 else 0 for element in range(8)]
    return rows


# ---- one grid (spells or GFs) -------------------------------------------------------------------------

class _ElemGrid(QTableWidget):
    """Use | Id | Name | Fire .. Holy. A row is written to the file only when Use is ticked;
    editing a value ticks it."""

    def __init__(self, names, id_label, missing_name, on_change):
        super().__init__(0, 3 + len(ELEMENTS))
        self.setHorizontalHeaderLabels(["Use", id_label, "Name"] + ELEMENTS)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._names, self._missing_name, self._on_change = names, missing_name, on_change
        self.use, self.spins, self.ids = {}, {}, []
        self._loading = False
        self.add_rows(sorted(names))

    def add_rows(self, ids):
        for row_id in ids:
            if row_id in self.spins:
                continue
            row = self.rowCount()
            self.insertRow(row)
            self.ids.append(row_id)
            use = QCheckBox()
            use.toggled.connect(lambda _on, i=row_id: self._row_changed(i))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(6, 0, 0, 0)
            holder_layout.addWidget(use)
            self.setCellWidget(row, 0, holder)
            for column, text in ((1, str(row_id)), (2, self._names.get(row_id, self._missing_name))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, column, item)
            spins = []
            for element in range(len(ELEMENTS)):
                spin = NoWheelSpinBox()
                spin.setRange(VALUE_MIN, VALUE_MAX)
                spin.setSuffix(" %")
                spin.valueChanged.connect(lambda _v, i=row_id, s=spin: self._value_changed(i, s))
                self.setCellWidget(row, 3 + element, spin)
                spins.append(spin)
            self.use[row_id] = use
            self.spins[row_id] = spins

    def _value_changed(self, row_id, spin):
        self._colour(spin)
        if self._loading:
            return
        if not self.use[row_id].isChecked():
            self.use[row_id].setChecked(True)   # editing a row puts it in the table
        self._on_change()

    def _row_changed(self, row_id):
        for spin in self.spins[row_id]:
            spin.setEnabled(self.use[row_id].isChecked())
        if not self._loading:
            self._on_change()

    @staticmethod
    def _colour(spin):
        value = spin.value()
        spin.setStyleSheet("color: #d04040;" if value < 0 else ("color: #2f9e44;" if value > 0 else ""))

    def load(self, rows):
        self.add_rows(sorted(set(rows) - set(self.spins)))
        self._loading = True
        try:
            for row_id in self.ids:
                values = rows.get(row_id)
                self.use[row_id].setChecked(values is not None)
                for spin, value in zip(self.spins[row_id], values or [0] * len(ELEMENTS)):
                    spin.setValue(max(VALUE_MIN, min(VALUE_MAX, value)))
                    self._colour(spin)
                self._row_changed(row_id)
        finally:
            self._loading = False

    def rows(self):
        return {row_id: [spin.value() for spin in self.spins[row_id]]
                for row_id in self.ids if self.use[row_id].isChecked()}


# ---- the dialog -------------------------------------------------------------------------------------

class CronosElemDefDialog(QDialog):
    """Edit the table: a Magic tab (the spells of the loaded kernel.bin) and a G-Forces tab."""

    def __init__(self, parent, magic_entries, magic_names, gf_names, character_names=None, settings=None,
                 page=MAGIC_PAGE):
        super().__init__(parent)
        self.setWindowTitle("Cronos extension - Elemental defense table")
        self.resize(1000, 720)
        self._entries = magic_entries          # {id: KernelEntry}
        self._magic_names = magic_names        # {id: name}
        self._gf_names = gf_names              # {GF id: name}
        self._character_names = character_names or {}   # {character id: name}
        self._settings = settings
        self._path = settings.value(SETTINGS_KEY, "") if settings is not None else ""
        self._dirty = False

        layout = QVBoxLayout(self)
        info = QLabel(
            "Needs the Cronos <b>NegativeElemDef.dll</b>. Values are resistance %: +100 = immune, above = absorb, "
            "<span style='color:#d04040'>negative = weakness</span> (-100 = x2 damage). "
            "<b>Magic</b>: what a <b>used</b> spell gives when junctioned to Elem-Def (x stock / 100); an unused "
            "spell keeps its kernel.bin J-Elem defense. <b>G-Forces</b>: what a GF gives, flat, to the character "
            "it is junctioned to. <b>Characters</b>: the character's own base, flat, always (Squall/Zell/Irvine "
            "also cover Laguna/Kiros/Ward). Everything adds up, clamped to -800% .. +200%.<br>"
            "Cronos ships the file as <i>CronosFiles/GameEnhancement/NegativeElemDef/cronos/elemdef.csv</i>.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._file_label = QLabel()
        self._file_label.setStyleSheet("color: gray;")
        layout.addWidget(self._file_label)

        self.pages = QTabWidget()
        self.magic_grid = _ElemGrid(magic_names, "Id", "(not in this kernel.bin)", self._changed)
        self.gf_grid = _ElemGrid(gf_names, "GF", "(unknown GF)", self._changed)
        self.pages.addTab(self.magic_grid, "Magic")
        self.character_grid = _ElemGrid(self._character_names, "CH", "(unknown character)", self._changed)
        self.pages.addTab(self.gf_grid, "G-Forces")
        self.pages.addTab(self.character_grid, "Characters")
        self.pages.setCurrentIndex(page)
        layout.addWidget(self.pages, 1)

        buttons = QHBoxLayout()
        for label, slot, tip in (
                ("Fill spells from kernel.bin", self._fill_from_kernel,
                 "Every spell, with the values its kernel.bin J-Elem defense gives today (changes nothing in game). "
                 "GFs and characters are not touched: the kernel.bin gives them no elemental defense."),
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

        if self._path and os.path.isfile(self._path):
            self._load(*read_table(self._path))
        else:
            self._path = ""
        self._refresh_file_label()

    def _changed(self):
        self._dirty = True

    def _load(self, spells, gfs, characters):
        self.magic_grid.load(spells)
        self.gf_grid.load(gfs)
        self.character_grid.load(characters)

    def rows(self):
        return self.magic_grid.rows()

    def gf_rows(self):
        return self.gf_grid.rows()

    def character_rows(self):
        return self.character_grid.rows()

    # ---- buttons ---------------------------------------------------------------------------------
    def _fill_from_kernel(self):
        if self.rows() and QMessageBox.question(
                self, "Fill from kernel.bin", "Replace every spell value with the kernel.bin ones?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.magic_grid.load(rows_from_kernel(self._entries))
        self._dirty = True

    def _import(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open an elemental defense table", self._path, FILE_FILTER)
        if not path:
            return
        try:
            tables = read_table(path)
        except (OSError, UnicodeDecodeError) as error:
            QMessageBox.warning(self, "Import", f"Cannot read {path}:\n{error}")
            return
        self._load(*tables)
        self._set_path(path)
        self._dirty = False

    def _save(self):
        if not self._path:
            return self._save_as()
        try:
            write_table(self._path, self.rows(), self.gf_rows(), self.character_rows(),
                        self._magic_names, self._gf_names, self._character_names)
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
