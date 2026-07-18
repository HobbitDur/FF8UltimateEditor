"""Local editor for a monster's name (section 7, ``info_stat_data['monster_name']``).

Split out as its own Stat sub-tab so it has exactly one home: this used to be edited a
second time from the Battle text tab (section 8), which put section-7 data under a
section-8 tool. Edits are applied to the loaded monster immediately, like the rest of
Stat; press the shared Save button to write them to the .dat file.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGroupBox


class IfritMonsterNameWidget(QWidget):
    """Editor for a monster's name."""

    def __init__(self, ifrit_manager):
        super().__init__()
        self.ifrit_manager = ifrit_manager
        self._loading = False

        root = QVBoxLayout(self)
        info = QLabel(
            "Local editor for the monster name (section 7). Edits are applied to the "
            "loaded monster immediately — press the <b>Save</b> button in the toolbar "
            "to write them to the .dat file.")
        info.setWordWrap(True)
        root.addWidget(info)

        name_group = QGroupBox("Monster name")
        name_layout = QHBoxLayout(name_group)
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(24)
        self._name_edit.setToolTip("Monster name, max 24 bytes in the FF8 text encoding.")
        self._name_edit.textEdited.connect(self._on_name_edited)
        name_layout.addWidget(self._name_edit)
        root.addWidget(name_group)
        root.addStretch(1)

    # ── Loading ──────────────────────────────────────────────────────────

    def load_data(self):
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None or not enemy.info_stat_data:
            return
        self._loading = True
        try:
            name = enemy.info_stat_data.get('monster_name')
            self._name_edit.setText(name.get_str() if name is not None else "")
        finally:
            self._loading = False

    # ── Editing ──────────────────────────────────────────────────────────

    def _on_name_edited(self, text):
        if self._loading:
            return
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None or not enemy.info_stat_data:
            return
        enemy.info_stat_data['monster_name'].set_str(text)
