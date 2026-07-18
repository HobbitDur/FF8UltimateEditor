"""Local editor for a monster's battle dialogue (section 8, ``battle_script_data
['battle_text']``).

Edits are applied to the loaded monster immediately, like the Stat tab; there is
no separate save_file() hook, the shared Save button writes them out via
``IfritManager.save_file`` -> ``MonsterAnalyser.write_data_to_file`` -> ``prepare_ai``.

Each dialogue line reuses ShumiTranslator's ``TranslationWidget``, bound directly
to the same ``FF8Text`` object read by ``MonsterAnalyser.analyze_battle_script_section``,
so edits here are the same edits ShumiTranslator would make.

The monster name (section 7) used to also be edited from here; it now has its own
Stat sub-tab (IfritMonsterNameWidget) so a section-8 tool doesn't also own section-7 data.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea,
)

from FF8GameData.GenericSection.ff8text import FF8Text
from ShumiTranslator.view.translationwidget import TranslationWidget


class IfritBattleTextWidget(QWidget):
    """Editor for a monster's in-battle dialogue lines."""

    def __init__(self, ifrit_manager):
        super().__init__()
        self.ifrit_manager = ifrit_manager
        self.game_data = ifrit_manager.game_data
        self._text_rows = []  # [TranslationWidget]

        root = QVBoxLayout(self)
        info = QLabel(
            "Local editor for the monster's in-battle dialogue lines (section 8). "
            "Edits are applied to the loaded monster immediately — press the "
            "<b>Save</b> button in the toolbar to write them to the .dat file.")
        info.setWordWrap(True)
        root.addWidget(info)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Battle text</b>"))
        header_layout.addStretch(1)
        self._add_btn = QPushButton("+ Add line")
        self._add_btn.setToolTip("Append a new, empty battle text line.")
        self._add_btn.clicked.connect(self._on_add_line)
        header_layout.addWidget(self._add_btn)
        root.addLayout(header_layout)

        self._lines_container = QWidget()
        self._lines_layout = QVBoxLayout(self._lines_container)
        self._lines_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._lines_container)
        root.addWidget(scroll, 1)

    # ── Loading ──────────────────────────────────────────────────────────

    def load_data(self):
        """Re-read the current enemy's battle text, rebuild every row."""
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None:
            return

        for row in self._text_rows:
            row.setParent(None)
        self._text_rows = []

        for index, text in enumerate(enemy.battle_script_data.get('battle_text', [])):
            self._add_row(index, text)

    def _add_row(self, index: int, text: FF8Text):
        row = TranslationWidget(text, index)
        self._lines_layout.insertWidget(self._lines_layout.count() - 1, row)
        self._text_rows.append(row)

    # ── Editing ──────────────────────────────────────────────────────────

    def _on_add_line(self):
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None:
            return
        battle_text = enemy.battle_script_data.setdefault('battle_text', [])
        new_text = FF8Text(game_data=self.game_data, own_offset=0, data_hex=bytearray(), id=len(battle_text))
        battle_text.append(new_text)
        self._add_row(len(battle_text) - 1, new_text)
