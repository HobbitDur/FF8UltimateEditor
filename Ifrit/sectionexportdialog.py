"""The section selection shared by all Ifrit model exports."""
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                             QLabel, QPushButton, QVBoxLayout)

from FF8GameData.dat.sectionfiles import SECTION_FILES
from FF8GameData.dat.monsteranalyser import MonsterAnalyser


_LABELS = {
    "skeleton": "Skeleton",
    "geometry": "Geometry",
    "animation": "Animations",
    "extra_animation": "Extra animations",
    "dynamic_texture": "Dynamic textures",
    "camera": "Camera",
    "sound": "Sound",
    "sound_bank": "Sound bank",
    "texture": "Textures (all TIM files)",
    "anim_seq": "Animation sequences",
    "info_stat": "Stats and battle texts",
    "ai": "AI",
}


class SectionExportDialog(QDialog):
    def __init__(self, parent, names, entity_type):
        super().__init__(parent)
        self.setWindowTitle("Define sections to export")
        layout = QVBoxLayout(self)
        description = QLabel("Choose the sections to extract. This choice is saved for all models, "
                             "including future sessions. Only this model's sections are shown; "
                             "choices for other model types are kept.")
        description.setWordWrap(True)
        layout.addWidget(description)

        controls = QHBoxLayout()
        select_all = QPushButton("Select all")
        clear_all = QPushButton("Clear all")
        for button in (select_all, clear_all):
            button.setAutoDefault(False)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)

        self._checks = {}
        section_indices = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[entity_type]
        sections = sorted((s for s in SECTION_FILES if s.section in section_indices),
                          key=lambda s: section_indices[s.section])
        for section in sections:
            filename = section.file_pattern or section.path_name
            section_id = section_indices[section.section]
            check = QCheckBox(f"Section {section_id} - {_LABELS.get(section.name, section.name)} ({filename})")
            check.setChecked(section.name in names)
            self._checks[section.name] = check
            layout.addWidget(check)

        layout.addWidget(QLabel("Select at least one section."))
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                         QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        for check in self._checks.values():
            check.toggled.connect(self._update_ok)
        select_all.clicked.connect(lambda: self._set_all(True))
        clear_all.clicked.connect(lambda: self._set_all(False))
        self._update_ok()
        self.resize(480, self.sizeHint().height())

    def selected_names(self):
        return [name for name, check in self._checks.items() if check.isChecked()]

    def _set_all(self, checked):
        for check in self._checks.values():
            check.setChecked(checked)

    def _update_ok(self):
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.selected_names()))
