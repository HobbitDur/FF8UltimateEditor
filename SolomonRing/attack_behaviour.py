"""Combined presentation of the attack routine and ATTACK_FLAG & 3 category.

Protection rules describe the unmodified PC engine, not a simulated damage result.
Damage_DispatchByAttackType (0x4922B0) selects the routines; physical modifiers
(0x48F600) check Protect, magic/GF damage (0x491AD0) checks category 1 for Shell,
and curative magic (0x493280) checks Shell independently of the category.
"""
from dataclasses import dataclass
import textwrap

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QFormLayout, QGridLayout, QGroupBox, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


# Attack-type values, not reaction-category values. Percentage and special damage
# retain their routine's protection checks even when they do not use STR or MAG.
_PHYSICAL = {
    1: "Physical damage (STR / VIT)",
    7: "Percentage physical damage",
    9: "Physical damage — Renzokuken finisher",
    10: "Physical damage — Gunblade",
    18: "Kamikaze damage (attacker's max HP)",
    34: "Physical damage (target's kill count)",
    36: "Physical damage (ignores VIT)",
}
_MAGIC_GF = {
    2: "Magic damage (MAG / SPR)",
    8: "Percentage magic damage",
    11: "GF damage",
    15: "GF damage (ignores SPR)",
    20: "Percentage GF damage",
    22: "Magic damage (ignores SPR)",
    26: "Magic damage (level condition)",
    33: "Magic damage (step count)",
}
_CURATIVE_MAGIC = {3: "Curative magic", 21: "Percentage curative magic"}
_CURATIVE_SPECIAL = {
    4: "Curative item", 25: "White Wind healing", 32: "Percentage healing",
}
_OTHER_EFFECTS = {
    0: "No damage routine", 12: "Scan", 13: "LV Down", 16: "LV Up",
    17: "Card", 19: "Devour", 23: "Angelo Search", 24: "GF healing — Moogle Dance",
    27: "Fixed damage", 28: "Target current HP minus 1",
    29: "Fixed damage based on GF level", 30: "No damage routine",
    31: "No damage routine", 35: "1 HP damage",
}


@dataclass(frozen=True)
class AttackBehaviour:
    headline: str
    protect: str
    shell: str
    med_data: str = ""


def describe_attack_behaviour(attack_type, category):
    """Describe verified routine/category combinations without conflating the fields."""
    if attack_type in _PHYSICAL:
        return AttackBehaviour(_PHYSICAL[attack_type], "halves damage", "no effect")
    if attack_type in _MAGIC_GF:
        shell = "halves damage" if category == 1 else "no effect"
        return AttackBehaviour(_MAGIC_GF[attack_type], "no effect", shell)
    if attack_type in _CURATIVE_MAGIC:
        return AttackBehaviour(_CURATIVE_MAGIC[attack_type], "no effect", "halves healing")
    if attack_type in _CURATIVE_SPECIAL:
        med_data = "doubles healing for a player with Med Data" if category == 2 else "no effect"
        return AttackBehaviour(_CURATIVE_SPECIAL[attack_type], "no effect", "no effect", med_data)
    if attack_type in (5, 6):
        shell = "halves damage against Zombie targets" if category == 1 else "no effect"
        med_data = "can double revived HP for item commands" if attack_type == 5 else ""
        return AttackBehaviour("Revival" if attack_type == 5 else "Revival at full HP",
                               "no effect", shell, med_data)
    if attack_type == 14:
        return AttackBehaviour("Summon item", "depends on summoned action",
                               "depends on summoned action")
    if attack_type in _OTHER_EFFECTS:
        return AttackBehaviour(_OTHER_EFFECTS[attack_type], "no effect", "no effect")
    return AttackBehaviour("Unknown damage / effect routine", "unknown", "unknown")


class AttackBehaviourPanel(QGroupBox):
    """Uses the tab's registered editors so loading, dirty tracking and saving stay intact."""

    def __init__(self, calculation_label, calculation, category_label, category, parent=None):
        super().__init__("Attack behaviour", parent)
        self.setObjectName("attackBehaviourPanel")
        self.calculation = calculation
        self.category = category
        self._category_names = {category.itemData(i): category.itemText(i)
                                for i in range(category.count())}
        for i in range(category.count()):
            category.setItemText(i, f"{category.itemText(i)} ({category.itemData(i)})")

        layout = QVBoxLayout(self)
        editors = QGridLayout()
        for column, (label, combo) in enumerate(((calculation_label, calculation),
                                                (category_label, category))):
            label.setWordWrap(True)
            combo.setMinimumWidth(0)
            combo.setMaximumWidth(16777215)
            combo.setSizeAdjustPolicy(combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setAccessibleName(label.text())
            label.setBuddy(combo)
            editors.addWidget(label, 0, column)
            editors.addWidget(combo, 1, column)
            editors.setColumnStretch(column, 1)
        editors.setHorizontalSpacing(16)
        layout.addLayout(editors)

        summary = QWidget()
        summary.setAutoFillBackground(True)
        summary.setBackgroundRole(QPalette.ColorRole.AlternateBase)
        result = QVBoxLayout(summary)
        self.headline = self._label()
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        self.protection = self._label()
        self.protection.setToolTip(textwrap.fill(
            "Protection checks for the selected routine in the unmodified game. "
            "They apply when the effect reaches that check; hit, immunity, status and "
            "command rules can still prevent or change the result. Engine patches may "
            "change these rules.", width=62, break_long_words=False, break_on_hyphens=False))
        result.addWidget(self.headline)
        result.addWidget(self.protection)
        layout.addWidget(summary)

        details = QFormLayout()
        details.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.statuses = self._label()
        self.statuses.setToolTip(textwrap.fill(
            "Category 0 removes the target's Sleep and Confusion before resolving "
            "the effect, and Back Attack afterwards. Other categories skip this "
            "clearing. The effect's own status fields can still change ailments.",
            width=62, break_long_words=False, break_on_hyphens=False))
        details.addRow(self._label("Sleep / Confusion"), self.statuses)
        ai_label = self._label("Enemy AI attack category (opcode 02)")
        # Let the form stack a long row when narrow instead of wrapping this label
        # into several short lines just to match the shorter Sleep label's width.
        ai_label.setWordWrap(False)
        self.enemy_ai = self._label()
        ai_help = (
            "Enemy AI opcode 0x02 (IF), subject 10, parameter 0: "
            "LAST ACTION DAMAGE TYPE. It compares ATTACK_FLAG & 3, independently "
            "of the damage calculation. Enemy scripts decide whether and how to "
            "react; this does not guarantee a counterattack.")
        ai_help = textwrap.fill(ai_help, width=62, break_long_words=False, break_on_hyphens=False)
        ai_label.setToolTip(ai_help)
        self.enemy_ai.setToolTip(ai_help)
        details.addRow(ai_label, self.enemy_ai)
        self.med_data_label = self._label("Med Data")
        self.med_data = self._label()
        details.addRow(self.med_data_label, self.med_data)
        layout.addLayout(details)
        calculation.currentIndexChanged.connect(self.refresh)
        category.currentIndexChanged.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _label(text=""):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def refresh(self, _=None):
        attack_type, category = self.calculation.currentData(), self.category.currentData()
        behaviour = describe_attack_behaviour(attack_type, category)
        self.headline.setText(behaviour.headline)
        self.protection.setText(f"Protect: {behaviour.protect} · Shell: {behaviour.shell}")
        if attack_type == 14:
            statuses = "Depends on summoned action"
        else:
            statuses = "Cleared before resolution" if category == 0 else "Preserved by this category"
        self.statuses.setText(statuses)
        name = self._category_names.get(category, "Unknown")
        self.enemy_ai.setText(f"{name} ({category})")
        self.med_data.setText(behaviour.med_data)
        self.med_data_label.setVisible(bool(behaviour.med_data))
        self.med_data.setVisible(bool(behaviour.med_data))
