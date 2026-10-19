"""Edit the five wmset ranges and the EXE's ordered searches without changing story scripts."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QSpinBox, QCheckBox, QComboBox,
                             QSplitter, QHBoxLayout, QPushButton)

from Cid.phasestory import PhaseStoryDialog


class DrawGroupsWidget(QWidget):
    world_changed = pyqtSignal()
    exe_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._section = None
        self._rules = None
        self._draws = []
        self._loading = False
        layout = QVBoxLayout(self)
        intro = QLabel('World phases are story states, not disc numbers. This tab changes draw-point '
                       'availability; the scripts that advance the phase stay unchanged. The original '
                       'format has five groups (0-4) and up to four group searches per phase. '
                       'Adding more groups requires an engine patch.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.source_status = QLabel()
        self.source_status.setWordWrap(True)
        layout.addWidget(self.source_status)
        split = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(split, 1)

        group_box = QGroupBox('Group contents - saved in wmsetxx.obj')
        group_layout = QVBoxLayout(group_box)
        hint = QLabel('Each group contains a contiguous range of Draw IDs. Select a group to inspect '
                      'its members below. Ranges may overlap; the game searches groups in the order shown.')
        hint.setWordWrap(True)
        group_layout.addWidget(hint)
        self.groups = QTableWidget(5, 6)
        self.groups.setHorizontalHeaderLabels(['Group', 'Has members', 'First Draw ID', 'Last Draw ID',
                                               'Records', 'Searched in phases'])
        self.groups.verticalHeader().hide()
        self.groups.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.groups.setMinimumHeight(185)
        group_layout.addWidget(self.groups)
        self._enabled = []
        self._first = []
        self._last = []
        for group in range(5):
            self._item(self.groups, group, 0, str(group))
            enabled = QCheckBox()
            first, last = QSpinBox(), QSpinBox()
            for spin in (first, last):
                spin.setRange(129, 256)
                spin.setKeyboardTracking(False)
            self.groups.setCellWidget(group, 1, enabled)
            self.groups.setCellWidget(group, 2, first)
            self.groups.setCellWidget(group, 3, last)
            self._enabled.append(enabled)
            self._first.append(first)
            self._last.append(last)
            enabled.toggled.connect(lambda _value, g=group: self._range_edited(g, 'enabled'))
            first.valueChanged.connect(lambda _value, g=group: self._range_edited(g, 'first'))
            last.valueChanged.connect(lambda _value, g=group: self._range_edited(g, 'last'))
        self.groups.currentCellChanged.connect(lambda *_: self.refresh_members())
        split.addWidget(group_box)

        phase_box = QGroupBox('Phase searches - exported in the EXE .hext patch')
        phase_layout = QVBoxLayout(phase_box)
        hint = QLabel('Searches run left to right. The first record matching the player\'s block and '
                      'triangle wins. Choosing None removes that search and shifts later groups left.')
        hint.setWordWrap(True)
        phase_heading = QHBoxLayout()
        phase_heading.addWidget(hint, 1)
        self.phase_info_button = QPushButton('Phase info...')
        self.phase_info_button.setToolTip('When each world phase changes, with verified field-script references')
        self.phase_info_button.clicked.connect(self._show_phase_info)
        phase_heading.addWidget(self.phase_info_button)
        phase_layout.addLayout(phase_heading)
        self.phases = QTableWidget(5, 5)
        self.phases.setHorizontalHeaderLabels(['World phase', 'Search 1', 'Search 2', 'Search 3', 'Search 4'])
        self.phases.verticalHeader().hide()
        self.phases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.phases.setMinimumHeight(185)
        self._searches = []
        for phase in range(5):
            self._item(self.phases, phase, 0, str(phase))
            row = []
            for slot in range(4):
                combo = QComboBox()
                combo.addItem('None', None)
                for group in range(5):
                    combo.addItem(f'Group {group}', group)
                combo.currentIndexChanged.connect(lambda _value, p=phase: self._phase_edited(p))
                self.phases.setCellWidget(phase, slot + 1, combo)
                row.append(combo)
            self._searches.append(row)
        phase_layout.addWidget(self.phases)
        split.addWidget(phase_box)

        members_box = QGroupBox('Selected group members')
        members_layout = QVBoxLayout(members_box)
        self.members = QTableWidget(0, 4)
        self.members.setHorizontalHeaderLabels(['Draw ID', 'Magic', 'Default location', 'Scanned in phases'])
        self.members.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.members.verticalHeader().hide()
        members_layout.addWidget(self.members)
        split.addWidget(members_box)
        self.diagnostics = QLabel()
        self.diagnostics.setWordWrap(True)
        layout.addWidget(self.diagnostics)
        self.groups.setCurrentCell(0, 0)

    @staticmethod
    def _item(table, row, column, text):
        item = table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)
        item.setText(text)

    def _show_phase_info(self):
        PhaseStoryDialog(self).exec()

    def set_sources(self, section, rules, draws):
        self._section, self._rules, self._draws = section, rules, draws
        self.refresh()

    def refresh(self):
        self._loading = True
        loaded = self._section is not None and self._section.is_loaded()
        exe = self._rules is not None and self._rules.loaded
        self.groups.setEnabled(loaded and self._section.get_nb_record() > 0)
        self.phases.setEnabled(exe)
        self.source_status.setText(
            ('Group ranges: wmset loaded. ' if loaded else 'Load wmsetxx.obj to edit group ranges. ')
            + ('Phase searches: loaded from the EXE.' if exe else
               'Load the FF8 EXE to edit phase searches; preview uses original OG rules.'))
        for group in range(5):
            start, end = self._section.group_range(group) if loaded else (0, 0)
            self._enabled[group].setChecked(start != end)
            maximum = min(256, 128 + self._section.get_nb_record()) if loaded else 256
            for spin in (self._first[group], self._last[group]):
                spin.setMaximum(max(129, maximum))
                spin.setEnabled(loaded and start != end)
            self._first[group].setValue(129 + start)
            self._last[group].setValue(128 + end if end > start else 129 + start)
            self._item(self.groups, group, 4, str(end - start))
            phases = [str(p) for p, groups in enumerate(self._rules.phase_groups) if group in groups] if self._rules else []
            self._item(self.groups, group, 5, ', '.join(phases) or 'None')
        if self._rules:
            for phase, row in enumerate(self._searches):
                selected = self._rules.groups_for_phase(phase)
                for slot, combo in enumerate(row):
                    combo.setCurrentIndex(combo.findData(selected[slot]) if slot < len(selected) else 0)
        self._loading = False
        self.refresh_members()
        self._refresh_diagnostics()

    def _range_edited(self, group, edited):
        if (self._loading or self._section is None or not self._section.is_loaded()
                or not self._section.get_nb_record()):
            return
        self.groups.setCurrentCell(group, 0)
        start, end = self._first[group].value() - 129, self._last[group].value() - 128
        if not self._enabled[group].isChecked():
            end = start
        elif start >= end:
            if edited == 'first':
                end = start + 1
            else:
                start = end - 1
        if self._section.set_group_range(group, start, end):
            self.world_changed.emit()
        self.refresh()

    def _phase_edited(self, phase):
        if self._loading or self._rules is None or not self._rules.loaded:
            return
        groups = [combo.currentData() for combo in self._searches[phase] if combo.currentData() is not None]
        if self._rules.set_groups(phase, groups):
            self.exe_changed.emit()
        self.refresh()

    def refresh_members(self):
        group = max(0, self.groups.currentRow())
        start, end = self._section.group_range(group) if self._section and self._section.is_loaded() else (0, 0)
        members = self._draws[128 + start:128 + end]
        self.members.setRowCount(len(members))
        for row, draw in enumerate(members):
            name = draw.get_magic_name()
            values = (str(draw.get_id()), f'{draw.magic_index}: {name}' if name else str(draw.magic_index),
                      draw.get_location(), ', '.join(map(str, draw.world_phases)) or 'None')
            for column, value in enumerate(values):
                self._item(self.members, row, column, value)

    def _refresh_diagnostics(self):
        if not self._section or not self._section.is_loaded() or not self._rules:
            self.diagnostics.clear()
            return
        hidden = []
        for phase, groups in enumerate(self._rules.phase_groups):
            seen = {}
            for group in groups:
                start, end = self._section.group_range(group)
                for index in range(start, end):
                    draw = self._draws[128 + index]
                    key = (draw.x, draw.y, draw.sub_id)
                    previous = seen.setdefault(key, draw.get_id())
                    if previous != draw.get_id():
                        hidden.append(f'Phase {phase}: ID {previous} matches before ID {draw.get_id()} at the same trigger.')
        hidden = list(dict.fromkeys(hidden))
        text = ' '.join(hidden[:6])
        if len(hidden) > 6:
            text += f' ({len(hidden) - 6} more overlapping triggers.)'
        self.diagnostics.setText(text)
