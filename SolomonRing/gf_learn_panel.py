"""The G-Forces tab's learn list: 21 ability slots, each with what unlocks it, plus a learn tree.

The two raw unlock bytes of a slot (see gf_learn.py) are edited as choices: "GF level" with a
level, "After ability" with a slot of the same GF, or "Never"; then "Hidden once learned" with a
slot or None. The ability pickers stay the tab's ordinary "enum" fields (the renaming and
renumbering code finds them by that); the unlock editors register as "custom" fields, which
KernelSectionTab loads and saves through set_value()/value()."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QGroupBox,
                             QStackedWidget, QTreeWidget, QTreeWidgetItem)

from SmallWidget.nowheel import NoWheelComboBox, NoWheelSpinBox
from SolomonRing import gf_learn

UNLOCK_HELP = ("What this ability needs before the GF offers it (BuildGFAbilityList, the Junction "
               "menu's learn list):\n"
               "GF level = the GF must be at least this level (0 or 1 = from the start).\n"
               "After ability = another ability of this GF must be fully learned first, like "
               "SumMag+20% after SumMag+10%.\n"
               "Never = the game never offers it (a raw value above 121).\n"
               "Stored as one byte: the level, or 101 + the slot (Ability 1 = 101).")
HIDDEN_HELP = ("Only used with 'After ability': once the ability of the chosen slot is learned, "
               "this one is no longer offered (an either/or choice). None in every vanilla GF, but "
               "the engine supports it. Stored as the slot counted from 0, 0xFF = None.")
TREE_HELP = ("How this GF's abilities unlock: level abilities at the top, each ability that waits "
             "for another under it. Click one to jump to its row. Abilities the game can never "
             "offer are listed at the bottom.")


SLOT_COMBO_WIDTH = 210


def _fit_combo(combo, width):
    """A slot picker stays narrow when closed; its list opens wide enough for long names."""
    combo.setFixedWidth(width)
    combo.view().setMinimumWidth(width + 90)


class GfUnlockEditor(QWidget):
    """One slot's Level/prereq byte as a kind + a level or a slot."""

    changed = pyqtSignal()

    def __init__(self, slot):
        super().__init__()
        self.slot = slot
        self._never_raw = gf_learn.NEVER_DEFAULT
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.mode = NoWheelComboBox()
        self.mode.addItem("GF level", gf_learn.LEVEL)
        self.mode.addItem("After ability", gf_learn.AFTER)
        self.mode.addItem("Never", gf_learn.NEVER)
        self.level = NoWheelSpinBox()
        self.level.setRange(0, gf_learn.MAX_LEVEL)
        self.level.setToolTip("Minimum GF level (0 or 1 = available from the start)")
        self.after = NoWheelComboBox()
        for index in range(gf_learn.SLOT_COUNT):
            self.after.addItem(f"Ability {index + 1}", index)
        self.after.setToolTip("This ability is offered once that ability is fully learned")
        _fit_combo(self.after, SLOT_COMBO_WIDTH)
        self.level.setFixedWidth(self.level.fontMetrics().horizontalAdvance("100") + 36)
        self.never = QLabel()
        self.stack = QStackedWidget()
        for widget in (self.level, self.after, self.never):
            # Left-hugged in a holder: the stack is as wide as the slot picker, and a bare
            # spinbox or label would stretch across all of it.
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.addWidget(widget)
            holder_layout.addStretch(1)
            self.stack.addWidget(holder)
        self.stack.setFixedWidth(SLOT_COMBO_WIDTH)
        layout.addWidget(self.mode)
        layout.addWidget(self.stack)
        self.mode.currentIndexChanged.connect(self._show_mode)
        self.mode.activated.connect(lambda _index: self.changed.emit())
        self.level.valueChanged.connect(lambda _value: self.changed.emit())
        self.after.activated.connect(lambda _index: self.changed.emit())
        self._show_mode()

    def concrete_widgets(self):
        return [self.mode, self.level, self.after]

    def kind(self):
        return self.mode.currentData()

    def set_value(self, raw):
        kind, value = gf_learn.decode_unlock(raw)
        self.mode.setCurrentIndex(self.mode.findData(kind))
        if kind == gf_learn.LEVEL:
            self.level.setValue(value)
        elif kind == gf_learn.AFTER:
            self.after.setCurrentIndex(value)
        else:
            self._never_raw = raw
        self._show_mode()

    def value(self):
        kind = self.kind()
        if kind == gf_learn.LEVEL:
            return self.level.value()
        if kind == gf_learn.AFTER:
            return gf_learn.encode_unlock(gf_learn.AFTER, self.after.currentData())
        return self._never_raw

    def set_slot_names(self, names):
        for index, name in enumerate(names):
            suffix = " (this slot)" if index == self.slot else ""
            self.after.setItemText(index, f"Ability {index + 1} - {name}{suffix}")

    def _show_mode(self, _index=None):
        self.stack.setCurrentIndex(max(self.mode.currentIndex(), 0))
        self.never.setText(f"raw {self._never_raw}")


class GfHiddenEditor(NoWheelComboBox):
    """One slot's Excluded slot byte: None or a slot of the same GF (raw values kept)."""

    changed = pyqtSignal()

    def __init__(self, slot):
        super().__init__()
        self.slot = slot
        self.addItem("None", gf_learn.NO_HIDDEN)
        for index in range(gf_learn.SLOT_COUNT):
            self.addItem(f"Ability {index + 1}", index)
        _fit_combo(self, SLOT_COMBO_WIDTH)
        self.activated.connect(lambda _index: self.changed.emit())

    def concrete_widgets(self):
        return [self]

    def set_value(self, raw):
        position = self.findData(raw)
        if position < 0:
            self.addItem(f"0x{raw:02X} (raw)", raw)
            position = self.findData(raw)
        self.setCurrentIndex(position)

    def value(self):
        return self.currentData()

    def set_slot_names(self, names):
        for index, name in enumerate(names):
            suffix = " (this slot)" if index == self.slot else ""
            self.setItemText(index + 1, f"Ability {index + 1} - {name}{suffix}")


class GfLearnPanel(QWidget):
    """The 21 learn slots of the selected GF, one row each, beside the learn tree.

    ``rows`` = one {"ability", "unlock", "hidden"} field dict per slot, in slot order."""

    def __init__(self, tab, rows):
        super().__init__()
        self._tab = tab
        self._ability_combos = []
        self._unlock_editors = []
        self._hidden_editors = []
        self._hidden_labels = []
        self._warnings = []

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(3)
        headers = [("Ability", "The ability this slot teaches"),
                   ("Unlocks", UNLOCK_HELP), ("Hidden once learned", HIDDEN_HELP)]
        for column, (text, help_text) in enumerate(headers, start=1):
            header = QLabel(f"<b>{text}</b>")
            header.setToolTip(help_text)
            grid.addWidget(header, 0, column)

        for slot, row in enumerate(rows):
            line = slot + 1
            grid.addWidget(QLabel(f"{line}"), line, 0, Qt.AlignmentFlag.AlignRight)
            # The ability picker stays an ordinary enum field of the tab.
            _label, ability = tab._labeled_widget(row["ability"])
            ability.setMinimumWidth(170)
            grid.addWidget(ability, line, 1)
            self._ability_combos.append(tab._field_widgets[row["ability"]["name"]][2])

            unlock = GfUnlockEditor(slot)
            unlock.setToolTip(UNLOCK_HELP)
            tab._field_widgets[row["unlock"]["name"]] = ("custom", row["unlock"], unlock)
            grid.addWidget(unlock, line, 2)
            self._unlock_editors.append(unlock)

            hidden = GfHiddenEditor(slot)
            hidden.setToolTip(HIDDEN_HELP)
            tab._field_widgets[row["hidden"]["name"]] = ("custom", row["hidden"], hidden)
            grid.addWidget(hidden, line, 3)
            self._hidden_editors.append(hidden)

            warning = QLabel("⚠")
            warning.setStyleSheet("color: #d08000; font-weight: bold;")
            warning.setVisible(False)
            grid.addWidget(warning, line, 4)
            self._warnings.append(warning)

            ability.currentIndexChanged.connect(lambda _index: self.refresh())
            unlock.changed.connect(self.refresh)
            hidden.changed.connect(self.refresh)
        grid.setColumnStretch(5, 1)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setToolTip(TREE_HELP)
        self.tree.setMinimumWidth(240)
        self.tree.itemClicked.connect(self._jump_to_row)
        tree_box = QGroupBox("Learn tree")
        tree_box.setToolTip(TREE_HELP)
        tree_layout = QVBoxLayout(tree_box)
        tree_layout.addWidget(self.tree)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grid_host = QVBoxLayout()
        grid_host.addLayout(grid)
        grid_host.addStretch(1)
        layout.addLayout(grid_host)
        layout.addWidget(tree_box, 1)

    def slots(self):
        """(ability id, Level/prereq raw, Excluded slot raw) per slot, as currently shown."""
        return [(combo.currentData() or 0, unlock.value(), hidden.value())
                for combo, unlock, hidden in zip(self._ability_combos, self._unlock_editors,
                                                 self._hidden_editors)]

    def slot_names(self):
        return [combo.currentText() for combo in self._ability_combos]

    def refresh(self):
        """Re-label the slot pickers, grey "Hidden once learned" outside 'After ability',
        flag problems and rebuild the tree. Called after every edit and entry load."""
        names = self.slot_names()
        for unlock, hidden in zip(self._unlock_editors, self._hidden_editors):
            unlock.set_slot_names(names)
            hidden.set_slot_names(names)
            hidden.setEnabled(self._tab._unlock_all or unlock.kind() == gf_learn.AFTER)
        slots = self.slots()
        for warning, problems in zip(self._warnings, gf_learn.learnability(slots)):
            warning.setVisible(bool(problems))
            warning.setToolTip("\n".join(problems))
        self._rebuild_tree(slots, names)

    def _rebuild_tree(self, slots, names):
        self.tree.clear()
        problems = gf_learn.learnability(slots)
        forest, orphans = gf_learn.learn_tree(slots)

        def label(index):
            ability, raw, hidden = slots[index]
            text = f"{index + 1}. {names[index]}"
            kind, level = gf_learn.decode_unlock(raw)
            if kind == gf_learn.LEVEL and level > 1:
                text += f"  (Lv {level})"
            if kind == gf_learn.AFTER and hidden != gf_learn.NO_HIDDEN and hidden < len(slots):
                text += f"  (not once {names[hidden]})"
            return text

        def add(parent, node):
            index, children = node
            item = QTreeWidgetItem([label(index)])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            if problems[index]:
                item.setToolTip(0, "\n".join(problems[index]))
                item.setText(0, "⚠ " + item.text(0))
            parent.addChild(item)
            for child in children:
                add(item, child)

        root = self.tree.invisibleRootItem()
        for node in forest:
            add(root, node)
        if orphans:
            never = QTreeWidgetItem(["Never learnable"])
            root.addChild(never)
            for index in orphans:
                item = QTreeWidgetItem([f"{index + 1}. {names[index]}  "
                                        f"({gf_learn.describe_unlock(slots[index][1])})"])
                item.setData(0, Qt.ItemDataRole.UserRole, index)
                if problems[index]:
                    item.setToolTip(0, "\n".join(problems[index]))
                never.addChild(item)
        self.tree.expandAll()

    def _jump_to_row(self, item, _column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            combo = self._ability_combos[index]
            scroll = getattr(self._tab, "_form_scroll", None)
            if scroll is not None:
                scroll.ensureWidgetVisible(combo)
            combo.setFocus()
