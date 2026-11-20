from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                             QSpinBox, QPushButton, QHeaderView)

from FF8GameData.menu.mngrp.m00x.refineabilities import RefineAbility, range_problems, table_growth


class RefineRangesDialog(QDialog):
    """The first and last entry of each refine ability, to write into kernel.bin.

    Opens with the ranges suggested after the recipes added and removed (RefineLayout.suggested_ranges),
    the values that differ from kernel.bin in bold. Every range is checked against the tables as
    they are now (range_problems): "Write to kernel.bin" is only possible when none has a problem
    and one changed. A range past its table's end grows the table: growth() says how many recipes
    each table gets (copies of the one before), the caller adds them. Only the ranges: what each
    ability is stays SolomonRing's to edit."""

    COLUMN_ABILITY = 0
    COLUMN_INDEX = 1
    COLUMN_TABLE = 2
    COLUMN_FIRST = 3
    COLUMN_LAST = 4
    COLUMN_COUNT = 5

    def __init__(self, parent, abilities, suggested, table_counts, table_names):
        """abilities: the RefineAbility list read from kernel.bin; suggested: {menu ability index:
        [first, last]}; table_counts / table_names: the recipe count and name of each table."""
        QDialog.__init__(self, parent)
        self.setWindowTitle("Shiva - Refine ranges in kernel.bin")
        self.abilities = sorted(abilities, key=lambda ability: (ability.table, suggested[ability.index][0]))
        self.table_counts = table_counts
        self.table_names = table_names

        explanation = QLabel("First and last entry of the refine table each ability offers (bytes 6-7 of its menu "
                             "ability in kernel.bin). Bold: not what kernel.bin holds now. Writing changes only "
                             "those bytes, at once; mngrp.bin is saved apart, with the toolbar.")
        explanation.setWordWrap(True)

        self.table = QTableWidget(len(self.abilities), 6)
        self.table.setHorizontalHeaderLabels(["Ability", "Menu ability", "Table", "First", "Last", "Recipes"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(self.COLUMN_ABILITY, QHeaderView.ResizeMode.Stretch)
        self.first_spins = []
        self.last_spins = []
        for row, ability in enumerate(self.abilities):
            first, last = suggested[ability.index]
            self.table.setItem(row, self.COLUMN_ABILITY, QTableWidgetItem(ability.name))
            self.table.setItem(row, self.COLUMN_INDEX, QTableWidgetItem(str(ability.index)))
            self.table.setItem(row, self.COLUMN_TABLE, QTableWidgetItem(table_names[ability.table]))
            self.table.setItem(row, self.COLUMN_COUNT, QTableWidgetItem(""))
            for column, value, spins in ((self.COLUMN_FIRST, first, self.first_spins),
                                         (self.COLUMN_LAST, last, self.last_spins)):
                spin = QSpinBox()
                spin.setRange(0, 255)
                spin.setValue(value)
                spin.valueChanged.connect(self._refresh)
                self.table.setCellWidget(row, column, spin)
                spins.append(spin)
            for column in (self.COLUMN_ABILITY, self.COLUMN_INDEX, self.COLUMN_TABLE, self.COLUMN_COUNT):
                item = self.table.item(row, column)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self.growth_label = QLabel("")
        self.growth_label.setWordWrap(True)
        self.problem_label = QLabel("")
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet("color:#ff6b6b;")
        self.write_button = QPushButton("Write to kernel.bin")
        self.write_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.write_button)
        buttons.addWidget(cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(explanation)
        layout.addWidget(self.table)
        layout.addWidget(self.growth_label)
        layout.addWidget(self.problem_label)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.resize(640, 520)
        self._refresh()

    def ranges(self):
        """{menu ability index: (first, last)} as set in the dialog."""
        return {ability.index: (self.first_spins[row].value(), self.last_spins[row].value())
                for row, ability in enumerate(self.abilities)}

    def changed(self):
        """The menu ability indexes whose range is not kernel.bin's."""
        return [ability.index for row, ability in enumerate(self.abilities)
                if (self.first_spins[row].value(), self.last_spins[row].value()) != (ability.first, ability.last)]

    def _proposed(self):
        return [RefineAbility(index=ability.index, table=ability.table, first=first, last=last, name=ability.name)
                for ability, (first, last) in zip(self.abilities, self.ranges().values())]

    def problems(self):
        """[(ability, reason)] of the ranges as set (range_problems, past the end allowed)."""
        return range_problems(self._proposed(), self.table_counts, can_grow=True)

    def growth(self):
        """{table: recipes to append} for the ranges as set to fit (table_growth)."""
        return table_growth(self._proposed(), self.table_counts)

    def _refresh(self, *_):
        problems = self.problems()
        rows_with_problem = {ability.index for ability, _ in problems}
        changed = set(self.changed())
        for row, ability in enumerate(self.abilities):
            first, last = self.first_spins[row].value(), self.last_spins[row].value()
            self.table.item(row, self.COLUMN_COUNT).setText(str(max(last - first + 1, 0)))
            for spin, kernel_value in ((self.first_spins[row], ability.first), (self.last_spins[row], ability.last)):
                font = QFont(spin.font())
                font.setBold(spin.value() != kernel_value)
                spin.setFont(font)
                spin.setToolTip(f"kernel.bin: {kernel_value}")
            mark = "⚠ " if ability.index in rows_with_problem else ""
            self.table.item(row, self.COLUMN_ABILITY).setText(mark + ability.name)
        self.growth_label.setText("\n".join(
            f"{self.table_names[table]} grows from {self.table_counts[table]} to {self.table_counts[table] + added} "
            f"recipes: {added} new one{'s' if added > 1 else ''} at the end, copies of the one before "
            f"(save mngrp.bin with the toolbar afterwards)."
            for table, added in sorted(self.growth().items())))
        self.problem_label.setText("\n".join(f"{ability.name}: {reason}" for ability, reason in problems))
        self.write_button.setEnabled(not problems and bool(changed))
