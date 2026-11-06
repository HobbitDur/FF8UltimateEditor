"""Which monsters of a scene.out encounter stand in a battle preview: a check box per monster, shared by every
battle preview (Common.battlescenepreview, Ifrit.IfritCameraSeq.encounterpreview). An encounter can hold monsters that
are not there when the battle starts, for a script to bring in later. Rather than reading the scripts, the preview lets
you pick; by default it shows what scene.out says stands there."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QGroupBox

COLUMNS = 2


def _flags(slot):
    flags = [text for text, on in (("not enabled", not slot.enabled), ("not visible", not slot.visible),
                                   ("not loaded", not slot.loaded)) if on]
    return ", ".join(flags) or "there from the start"


class EncounterMonsterChecks(QGroupBox):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Monsters shown", parent)
        self.setToolTip("Tick the monsters the preview shows. By default, the ones scene.out has there when the battle "
                        "starts; the others come in during the battle.")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(6, 2, 6, 2)
        self._grid.setVerticalSpacing(0)
        self._checks = {}          # scene.out slot index -> its check box
        self._slots = []
        self._key = None
        self.setVisible(False)

    def show_encounter(self, encounter, name=None):
        """The check boxes of this encounter (None: none). The same encounter with the same flags keeps your picks."""
        slots = encounter.monster_slots() if encounter is not None else []
        key = (encounter.index, tuple((slot.slot_index, slot.com_file_id, slot.present) for slot in slots)) \
            if encounter is not None else None
        if key != self._key:
            self._key = key
            self._slots = slots
            for check in self._checks.values():
                self._grid.removeWidget(check)
                check.deleteLater()
            self._checks = {}
            for row, slot in enumerate(slots):
                check = QCheckBox()
                check.setChecked(slot.present)
                check.toggled.connect(lambda _checked: self.changed.emit())
                self._checks[slot.slot_index] = check
                self._grid.addWidget(check, row // COLUMNS, row % COLUMNS)
            self.setVisible(bool(slots))
        for slot in self._slots:
            label = name(slot.com_file_id) if name is not None else f"c0m{slot.com_file_id:03}"
            check = self._checks[slot.slot_index]
            check.setText(f"{slot.slot_index}: {label}")
            check.setToolTip(f"Slot {slot.slot_index}, c0m{slot.com_file_id:03}.dat. scene.out: {_flags(slot)}.")

    def require(self, slot_index=None):
        """This slot is the model the host films: always shown (None: no such slot)."""
        for index, check in self._checks.items():
            required = index == slot_index
            check.setEnabled(not required)
            if required and not check.isChecked():
                check.blockSignals(True)
                check.setChecked(True)
                check.blockSignals(False)

    def present(self, slot_index):
        check = self._checks.get(slot_index)
        return check is not None and check.isChecked()

    def present_slots(self):
        return [slot for slot in self._slots if self.present(slot.slot_index)]
