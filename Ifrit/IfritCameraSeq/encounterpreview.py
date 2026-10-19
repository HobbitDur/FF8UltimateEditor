"""Read-only encounter picker shared by monster and character camera previews."""
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.sceneout import read_encounters, ENCOUNTER_SIZE, NB_ENCOUNTER


class EncounterPicker(QWidget):
    changed = pyqtSignal()

    def __init__(self, manager, registry=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.encounters = []
        self.path = None
        self._model_key = None
        self.registry = registry if registry is not None else FileRegistry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        open_button = QPushButton('Open scene.out…')
        open_button.clicked.connect(self._choose)
        row.addWidget(open_button)
        self.encounter = QComboBox()
        self.encounter.setMinimumContentsLength(20)
        self.encounter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.encounter.addItem('Manual placement', None)
        self.encounter.setToolTip('Encounter IDs are zero-based scene.out record numbers.')
        row.addWidget(self.encounter, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.slot_label = QLabel('Enemy:')
        row.addWidget(self.slot_label)
        self.enemy_slot = QComboBox()
        row.addWidget(self.enemy_slot, 1)
        layout.addLayout(row)
        self.slot_row = row
        self.status = QLabel('Open scene.out to use encounter placement.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.encounter.currentIndexChanged.connect(self._picked)
        self.enemy_slot.currentIndexChanged.connect(lambda _i: self.changed.emit())
        self.binding = FileBinding('scene.out', self.registry, load_callback=self.load,
                                   read_only=True)
        self.binding.file_closed.connect(self._closed)
        self.binding.load_opened_file()
        self._picked()

    @property
    def is_monster(self):
        return getattr(self.manager.enemy.entity_type, 'name', '').startswith('MONSTER')

    @property
    def selected(self):
        return self.encounter.currentData()

    @property
    def selected_slot(self):
        return self.enemy_slot.currentData()

    def _choose(self):
        path = self.binding.open_dialog(self, self.registry.last_folder('scene.out'))
        if path:
            self.registry.remember_folder('scene.out', str(Path(path).parent))

    def load(self, path):
        try:
            raw = Path(path).read_bytes()
            if not raw or len(raw) % ENCOUNTER_SIZE or len(raw) > NB_ENCOUNTER * ENCOUNTER_SIZE:
                raise ValueError('expected complete 128-byte encounter records (up to 1024)')
            encounters = read_encounters(raw)
        except (OSError, ValueError) as error:
            self.status.setText(f'Cannot read scene.out: {error}')
            return False
        self.path = Path(path)
        self.encounters = encounters
        self.refresh_model(force=True)
        return True

    def _closed(self, _path):
        self.encounters = []
        self.path = None
        self.refresh_model(force=True)

    def refresh_model(self, force=False):
        key = (getattr(self.manager.enemy, 'origin_path', ''), self.is_monster,
               getattr(self.manager.enemy, 'id', None))
        if key == self._model_key and not force:
            return
        self._model_key = key
        self.encounter.blockSignals(True)
        self.encounter.clear()
        self.encounter.addItem('Manual placement', None)
        for encounter in self.encounters:
            slots = encounter.enabled_slots()
            if not slots:
                continue
            if self.is_monster and not any(s.com_file_id == key[2] for s in slots):
                continue
            names = ', '.join(f'c0m{s.com_file_id:03}' for s in slots)
            self.encounter.addItem(f'Encounter {encounter.index} · stage {encounter.stage_id} · {names}', encounter)
        self.encounter.blockSignals(False)
        self._picked()

    def _picked(self, _index=0):
        encounter = self.selected
        self.enemy_slot.blockSignals(True)
        self.enemy_slot.clear()
        if encounter is not None:
            for slot in encounter.enabled_slots():
                if self.is_monster and slot.com_file_id != self.manager.enemy.id:
                    continue
                self.enemy_slot.addItem(
                    f'Scene slot {slot.slot_index} · c0m{slot.com_file_id:03} · {slot.position}', slot)
        self.enemy_slot.blockSignals(False)
        self.slot_label.setText('Loaded monster:' if self.is_monster else 'Enemy opponent:')
        self.slot_label.setVisible(encounter is not None)
        self.enemy_slot.setVisible(encounter is not None)
        if encounter is None:
            count = self.encounter.count() - 1
            self.status.setText(f'{count} matching encounters. Manual placement.' if self.path else
                                'Open scene.out to use encounter placement.')
        else:
            self.status.setText(f'Encounter {encounter.index} · stage {encounter.stage_id} · '
                                'Enemy positions from scene.out; party placement is a preview assumption.')
        self.changed.emit()
